"""Bluetooth devices whose battery level Windows itself knows
(the ones that show a percentage in Settings > Bluetooth & devices).

Battery:    DEVPKEY_Bluetooth_Battery {104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2
Connection: WinRT BluetoothDevice / BluetoothLEDevice.ConnectionStatus (by MAC address)

Approach and PowerShell script simplified from Halo Battery's providers/bluetooth.py
(MIT, see THIRD_PARTY_NOTICES.md).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Dict, List, Optional

from .model import KIND_GAMEPAD, KIND_HEADSET, KIND_KEYBOARD, KIND_MOUSE, KIND_OTHER, Device

K_BAT = "{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2"

PS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$winrtErr = $null
try {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
  $tClassic = [Windows.Devices.Bluetooth.BluetoothDevice, Windows.Devices.Bluetooth, ContentType = WindowsRuntime]
  $tLE = [Windows.Devices.Bluetooth.BluetoothLEDevice, Windows.Devices.Bluetooth, ContentType = WindowsRuntime]
} catch { $winrtErr = "$_" }

$devs = @(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match '^(BTHENUM|BTHLE|BTHLEDEVICE)\\' })
$props = @()
if ($devs.Count -gt 0) {
  $props = @(Get-PnpDeviceProperty -InstanceId $devs.InstanceId -KeyName '%BAT%' |
             Where-Object { $_.Data -ne $null } |
             ForEach-Object { [pscustomobject]@{ id = $_.InstanceId; data = $_.Data } })
}
$list = @($devs | ForEach-Object { [pscustomobject]@{ id = $_.InstanceId; name = $_.FriendlyName } })
$roots = @($devs | Where-Object { $_.InstanceId -match '^(BTHENUM|BTHLE)\\DEV_([0-9A-F]{12})' } |
           ForEach-Object { $null = $_.InstanceId -match '^(BTHENUM|BTHLE)\\DEV_([0-9A-F]{12})'
                            [pscustomobject]@{ le = ($Matches[1] -eq 'BTHLE'); mac = $Matches[2] } })
$conn = @()
if (-not $winrtErr) {
  foreach ($r in $roots) {
    $c = $null; $cls = $null; $err = $null
    try {
      $addr = [Convert]::ToUInt64($r.mac, 16)
      if ($r.le) { $t = $tLE; $op = [Windows.Devices.Bluetooth.BluetoothLEDevice]::FromBluetoothAddressAsync($addr) }
      else       { $t = $tClassic; $op = [Windows.Devices.Bluetooth.BluetoothDevice]::FromBluetoothAddressAsync($addr) }
      $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op))
      if ($task.Wait(3000)) {
        $d = $task.Result
        if ($d) {
          $c = ("$($d.ConnectionStatus)" -eq 'Connected')
          try { if ($r.le) { $cls = [int]$d.Appearance.RawValue } else { $cls = [int]$d.ClassOfDevice.RawValue } } catch { }
          $d.Dispose()
        }
      } else { $err = 'timeout' }
    } catch { $err = "$_" }
    $conn += [pscustomobject]@{ addr = $r.mac; conn = $c; le = $r.le; cls = $cls; err = $err }
  }
}
ConvertTo-Json -InputObject ([pscustomobject]@{ devs = $list; props = $props; conn = $conn; winrt_error = $winrtErr }) -Compress -Depth 4
""".replace("%BAT%", K_BAT)

_HEX12 = re.compile(r"(?<![0-9A-F])([0-9A-F]{12})(?![0-9A-F])")
AUDIO_SERVICES = ("0000110b-", "0000111e-", "00001108-", "00001131-")


def mac_of(instance_id: str) -> Optional[str]:
    s = (instance_id or "").upper()
    m = re.search(r"DEV_([0-9A-F]{12})(?![0-9A-F])", s)
    if m:
        return m.group(1)
    found = _HEX12.findall(s)
    return found[-1] if found else None


def is_root(instance_id: str) -> bool:
    return bool(re.match(r"^(BTHENUM|BTHLE)\\DEV_[0-9A-F]{12}", (instance_id or "").upper()))


def kind_from_class(raw, le: bool) -> str:
    try:
        raw = int(raw)
    except (TypeError, ValueError):
        return ""
    if le:
        cat, sub = raw >> 6, raw & 0x3F
        if cat == 0x0F:
            return {1: KIND_KEYBOARD, 2: KIND_MOUSE, 3: KIND_GAMEPAD, 4: KIND_GAMEPAD}.get(sub, "")
        if cat == 0x25:
            return KIND_HEADSET
        return ""
    major, minor = (raw >> 8) & 0x1F, (raw >> 2) & 0x3F
    if major == 4:
        return KIND_HEADSET if minor in (1, 2, 6) else ""
    if major == 5:
        if (minor & 0x0F) in (1, 2):
            return KIND_GAMEPAD
        return {1: KIND_KEYBOARD, 2: KIND_MOUSE, 3: KIND_KEYBOARD}.get(minor >> 4, "")
    return ""


def _as_list(v):
    if v is None:
        return []
    return [v] if isinstance(v, dict) else list(v)


def _as_bool(v) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.lower() in ("true", "false"):
        return v.lower() == "true"
    return None


def parse_snapshot(data: dict, diag: List[str]) -> List[Device]:
    devs = _as_list(data.get("devs"))
    groups: Dict[str, dict] = {}

    def slot(mac):
        return groups.setdefault(mac, {"level": None, "name": None, "root_name": None,
                                       "conn": None, "kind": "", "audio": False})

    names = {d.get("id"): d.get("name") for d in devs}
    for d in devs:
        mac = mac_of(d.get("id"))
        if not mac:
            continue
        g = slot(mac)
        if is_root(d.get("id")) and d.get("name"):
            g["root_name"] = d["name"]
        if any(u in (d.get("id") or "").lower() for u in AUDIO_SERVICES):
            g["audio"] = True
    for p in _as_list(data.get("props")):
        mac = mac_of(p.get("id"))
        if not mac:
            continue
        try:
            level = int(p.get("data"))
        except (TypeError, ValueError):
            continue
        g = slot(mac)
        g["level"] = level
        g["name"] = g["name"] or names.get(p.get("id"))
    for c in _as_list(data.get("conn")):
        mac = re.sub(r"[^0-9A-F]", "", str(c.get("addr") or "").upper())
        if len(mac) != 12:
            continue
        g = slot(mac)
        b = _as_bool(c.get("conn"))
        if b is not None:
            g["conn"] = bool(g["conn"]) or b
        g["kind"] = g["kind"] or kind_from_class(c.get("cls"), bool(_as_bool(c.get("le"))))
        if c.get("err"):
            diag.append(f"[Bluetooth] {mac}: WinRT error {str(c['err'])[:100]}")

    winrt_ok = not data.get("winrt_error")
    if not winrt_ok:
        diag.append(f"[Bluetooth] WinRT unavailable: {str(data['winrt_error'])[:150]}")
    out: List[Device] = []
    for mac, g in groups.items():
        name = (g["root_name"] or g["name"] or f"Bluetooth {mac}").strip()
        connected = g["conn"] if winrt_ok else True
        diag.append(f"[Bluetooth] {name} ({mac}): battery={g['level']} connected={g['conn']}")
        if g["level"] is None or not connected:
            continue
        kind = g["kind"] or (KIND_HEADSET if g["audio"] else KIND_OTHER)
        out.append(Device(f"bt:{mac}", name, kind, g["level"], False, True, "Bluetooth"))
    if not groups:
        diag.append("[Bluetooth] no Bluetooth devices")
    return out


class BluetoothReader:
    name = "Bluetooth"

    def __init__(self):
        self.diag: List[str] = []

    def read(self) -> List[Device]:
        self.diag = []
        if sys.platform != "win32":
            return []
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-Command", PS_SCRIPT],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=60,
                creationflags=0x08000000)
        except subprocess.TimeoutExpired:
            self.diag.append("[Bluetooth] PowerShell did not answer within 60 s")
            raise
        raw = proc.stdout.decode("utf-8", errors="replace").strip().lstrip("﻿")
        if not raw:
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"PowerShell returned no output: {err[:200]}")
        return parse_snapshot(json.loads(raw), self.diag)

    def close(self):
        pass
