"""Logitech wireless devices (Lightspeed / Unifying / Bolt receiver or USB cable), HID++ 2.0.

Protocol and constants simplified from Halo Battery's providers/logitech.py
(MIT, see THIRD_PARTY_NOTICES.md), which in turn follows Solaar.

Request: 11 <slot> <feature index> <function << 4 | swid> <params...>
Error:   10/11 <slot> 8f/ff <feature index> <function|swid> <error code>
Battery features: 0x1004 (unified battery), 0x1000 (battery status), 0x1001 (voltage).
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

try:
    import hid
except ImportError:  # pragma: no cover
    hid = None

from .model import KIND_KEYBOARD, KIND_MOUSE, KIND_OTHER, Device

VID = 0x046D
SWIDS = (0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F)
TIMEOUT = 0.6
PING_TIMEOUT = 2.0

F_ROOT, F_INFO, F_NAME = 0x0000, 0x0003, 0x0005
F_UNIFIED, F_STATUS, F_VOLTAGE = 0x1004, 0x1000, 0x1001
BATTERY_FEATURES = (F_UNIFIED, F_STATUS, F_VOLTAGE)

RECEIVERS = {
    0xC548,
    0xC52B, 0xC532,
    0xC52F, 0xC518, 0xC51A, 0xC51B, 0xC521, 0xC525, 0xC526,
    0xC52E, 0xC531, 0xC534, 0xC535, 0xC537,
    0xC539, 0xC53A, 0xC53D, 0xC53F, 0xC541, 0xC545, 0xC547,
    0xC54D,
}

KINDS = {0: KIND_KEYBOARD, 2: KIND_KEYBOARD, 3: KIND_MOUSE, 4: KIND_MOUSE, 5: KIND_MOUSE}

VOLTAGE_CURVE = ((4186, 100), (4067, 90), (3989, 80), (3922, 70), (3859, 60), (3811, 50),
                 (3778, 40), (3751, 30), (3717, 20), (3671, 10), (3646, 5), (3579, 2), (3500, 0))
MAX_BATTERY_MV = 5000
ON_CHARGER = (1, 2, 3, 4)
APPROX_LEVELS = {8: 90, 4: 50, 2: 20, 1: 5}


def voltage_to_percent(mv: int) -> int:
    if mv >= VOLTAGE_CURVE[0][0]:
        return 100
    for (hi_mv, hi_p), (lo_mv, lo_p) in zip(VOLTAGE_CURVE, VOLTAGE_CURVE[1:]):
        if mv >= lo_mv:
            return round(lo_p + (mv - lo_mv) * (hi_p - lo_p) / (hi_mv - lo_mv))
    return 0


def parse_battery(feature: int, p) -> Tuple[Optional[int], bool]:
    """(level, charging) from the params of a battery reply. Level None: no valid reading."""
    if feature == F_UNIFIED:
        charging = p[2] in ON_CHARGER
        if 0 < p[0] <= 100:
            return p[0], charging
        if p[0] == 0 and p[1] in APPROX_LEVELS:
            return APPROX_LEVELS[p[1]], charging
        return None, False
    if feature == F_STATUS:
        return (p[0] if 0 < p[0] <= 100 else None), p[2] in ON_CHARGER
    if feature == F_VOLTAGE:
        mv = (p[0] << 8) | p[1]
        if not 2500 <= mv <= MAX_BATTERY_MV:
            return None, False
        return voltage_to_percent(mv), bool(p[2] & 0x80)
    return None, False


def instance_of(info: dict) -> str:
    p = info.get("path") or b""
    s = p.decode("ascii", "ignore") if isinstance(p, (bytes, bytearray)) else str(p)
    parts = s.split("#")
    inst = parts[2].lower() if len(parts) > 2 else ""
    return inst.rsplit("&", 1)[0]


def group_collections(infos: List[dict]) -> Dict[Tuple[int, str], Dict[int, bytes]]:
    """(pid, receiver instance) -> {1: short path, 2: long path}"""
    groups: Dict[Tuple[int, str], Dict[int, bytes]] = {}
    for d in infos:
        if d.get("usage_page") == 0xFF00 and d.get("usage") in (1, 2):
            groups.setdefault((d["product_id"], instance_of(d)), {})[d["usage"]] = d["path"]
    return groups


class Channel:
    def __init__(self, short_path: Optional[bytes], long_path: bytes):
        self.devs = []
        self.error = False
        self.error_code = 0
        self._swid = 0
        self.long = hid.device()
        self.long.open_path(long_path)
        self.long.set_nonblocking(True)
        self.devs.append(self.long)
        if short_path:
            try:
                s = hid.device()
                s.open_path(short_path)
                s.set_nonblocking(True)
                self.devs.append(s)
            except (OSError, IOError):
                pass

    def close(self):
        for d in self.devs:
            try:
                d.close()
            except Exception:
                pass

    def request(self, idx: int, feat: int, func: int, params=(),
                timeout: float = TIMEOUT) -> Optional[List[int]]:
        self.error, self.error_code = False, 0
        self._swid = (self._swid + 1) % len(SWIDS)
        fn = (func << 4) | SWIDS[self._swid]
        req = [0x11, idx, feat, fn] + list(params)
        self.long.write(req + [0] * (20 - len(req)))
        end = time.time() + timeout
        while time.time() < end:
            for d in self.devs:
                r = d.read(64)
                if not r or len(r) < 4 or r[1] != idx:
                    continue
                if r[2] in (0x8F, 0xFF) and len(r) >= 6 and r[3] == feat and r[4] == fn:
                    self.error, self.error_code = True, r[5]
                    return None
                if r[2] == feat and r[3] == fn:
                    return list(r[4:]) + [0] * 16
            time.sleep(0.005)
        return None

    def feature_index(self, idx: int, feature_id: int) -> int:
        r = self.request(idx, F_ROOT, 0, [feature_id >> 8, feature_id & 0xFF])
        return r[0] if r else 0

    def identity(self, idx: int) -> Tuple[str, str, str]:
        name = kind = unit = ""
        fi = self.feature_index(idx, F_NAME)
        if fi:
            r = self.request(idx, fi, 0)
            length = r[0] if r else 0
            raw = b""
            while len(raw) < length:
                r = self.request(idx, fi, 1, [len(raw)])
                if not r:
                    break
                raw += bytes(r[:16])
            name = raw[:length].decode("utf-8", "replace").strip()
            r = self.request(idx, fi, 2)
            kind = KINDS.get(r[0], "") if r else ""
        fi = self.feature_index(idx, F_INFO)
        if fi:
            r = self.request(idx, fi, 0)
            if r and any(r[1:5]):
                unit = bytes(r[1:5]).hex().upper()
        return name, kind, unit


class LogitechReader:
    name = "Logitech"

    def __init__(self):
        self.diag: List[str] = []
        self._ids: Dict[Tuple[int, str, int], Tuple[str, str, str]] = {}
        self._asleep: set = set()
        self._discharge: Dict[str, int] = {}

    def _read_slot(self, ch: Channel, pid: int, inst: str, idx: int) -> Optional[Device]:
        slot = (pid, inst, idx)
        timeout = TIMEOUT if slot in self._asleep else PING_TIMEOUT
        if ch.request(idx, F_ROOT, 1, timeout=timeout) is None:
            if not ch.error:
                self._asleep.add(slot)
                self.diag.append(f"  slot {idx}: no answer (asleep)")
            elif ch.error_code != 0x08:
                self.diag.append(f"  slot {idx}: error {ch.error_code:02x} (off or out of range)")
            return None
        self._asleep.discard(slot)

        if slot not in self._ids:
            ident = ch.identity(idx)
            if ident[0] or ident[2]:
                self._ids[slot] = ident
        name, kind, unit = self._ids.get(slot, ("", "", ""))
        name = name or "Logitech device"
        key = f"logitech:{unit}" if unit else f"logitech:{pid:04x}:{inst}:{idx}"

        for feature in BATTERY_FEATURES:
            fi = ch.feature_index(idx, feature)
            if not fi:
                continue
            r = ch.request(idx, fi, 1 if feature == F_UNIFIED else 0)
            if r is None:
                continue
            level, charging = parse_battery(feature, r)
            self.diag.append(f"  slot {idx} '{name}' feature {feature:04x}: "
                             f"{' '.join(f'{b:02x}' for b in r[:4])} -> {level}% charging={charging}")
            if level is None:
                continue
            note = ""
            if feature == F_VOLTAGE:
                if not charging:
                    self._discharge[key] = level
                else:
                    level = self._discharge.get(key)
                    note = "note.voltage_charging"
            return Device(key, name, kind or KIND_OTHER, level, charging, True, "Logitech", note)
        self.diag.append(f"  slot {idx} '{name}': no battery feature")
        return None

    def read(self) -> List[Device]:
        self.diag = []
        if hid is None:
            self.diag.append("[Logitech] hidapi is not installed")
            return []
        infos = hid.enumerate(VID)
        found: Dict[str, Device] = {}
        for (pid, inst), paths in group_collections(infos).items():
            if 2 not in paths:
                continue
            product = next((d.get("product_string") or "" for d in infos if d["product_id"] == pid), "")
            receiver = pid in RECEIVERS or "receiver" in product.lower()
            self.diag.append(f"[Logitech] pid={pid:04x} '{product}' {'receiver' if receiver else 'cable'}")
            try:
                ch = Channel(paths.get(1), paths[2])
            except (OSError, IOError) as e:
                self.diag.append(f"  cannot open: {e}")
                continue
            try:
                for idx in (range(1, 7) if receiver else (0xFF,)):
                    dev = self._read_slot(ch, pid, inst, idx)
                    if dev and (dev.key not in found or dev.charging):
                        found[dev.key] = dev
            except (OSError, IOError, ValueError) as e:
                self.diag.append(f"  error: {e}")
            finally:
                ch.close()
        return list(found.values())

    def close(self):
        pass
