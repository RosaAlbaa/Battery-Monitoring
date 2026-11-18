"""Razer BlackShark V3 family headsets over their 2.4 GHz dongle.

Protocol taken from Halo Battery's providers/blackshark_v3.py (MIT, see
THIRD_PARTY_NOTICES.md), where only the BlackShark V3 dongle (1532:057A) was tested on
hardware. This app also tries any Razer dongle whose product name contains "BlackShark"
and that exposes the same ff14:0001 collection.

Frame: 64 bytes, report id 0x02, [2]=0x60, [6]=4, [9] direction, [10] class,
[11] 0x00 request / 0x01 reply / 0x02 push, [12] argument count, [13] value,
[62] = XOR of bytes 0..61.
Classes: 0x21 battery (%), 0x2a charging (0/1), 0x20 link.

Polling the headset too often drops its radio link, so the collection stays open,
pushed values are read as they arrive, and the headset is queried at most every 5 minutes.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

try:
    import hid
except ImportError:  # pragma: no cover
    hid = None

from .model import KIND_HEADSET, Device

VID = 0x1532
KNOWN_PIDS = {0x057A: "Razer BlackShark V3"}
USAGE_PAGE = 0xFF14
USAGE = 0x0001

REPORT_ID = 0x02
REPORT_LEN = 64
TRANSACTION = 0x60
CHECKSUM_INDEX = 62

DIR_WAKE = 0x00
DIR_QUERY = 0x80

CLASS_INIT = 0x02
CLASS_LINK = 0x20
CLASS_BATTERY = 0x21
CLASS_CHARGING = 0x2A

KIND_REPLY = 0x01
KIND_PUSH = 0x02

REFRESH_S = 300.0
ATTEMPTS = 3
RETRY_S = 0.7
LINK_SETTLE_S = 0.6
WAKE_WAIT_S = 0.05
REPLY_WAIT_S = 0.3
READ_TIMEOUT_MS = 50
BUFFERED_TIMEOUT_MS = 1
MAX_BUFFERED = 128


def checksum(frame) -> int:
    crc = 0
    for b in frame[:CHECKSUM_INDEX]:
        crc ^= b
    return crc


def make_frame(cmd_class: int, direction: int = DIR_QUERY) -> bytes:
    b = bytearray(REPORT_LEN)
    b[0] = REPORT_ID
    b[2] = TRANSACTION
    b[6] = 4
    b[9] = direction
    b[10] = cmd_class
    b[CHECKSUM_INDEX] = checksum(b)
    return bytes(b)


def parse_frame(data) -> Optional[Tuple[int, int]]:
    d = list(data or [])
    if len(d) <= CHECKSUM_INDEX or d[0] != REPORT_ID or d[CHECKSUM_INDEX] != checksum(d):
        return None
    if d[11] not in (KIND_REPLY, KIND_PUSH) or d[12] < 1:
        return None
    return d[10], d[13]


def is_candidate(info: dict, extra_pids=()) -> bool:
    if info.get("usage_page") != USAGE_PAGE or info.get("usage") != USAGE:
        return False
    pid = info.get("product_id")
    product = (info.get("product_string") or "").lower()
    return pid in KNOWN_PIDS or pid in extra_pids or "blackshark" in product


class Session:
    def __init__(self, path: bytes):
        self.dev = hid.device()
        self.dev.open_path(path)
        self.level: Optional[int] = None
        self.charging = False
        self._woken = False
        self._link_up = False
        self._next_query = 0.0

    def close(self) -> None:
        try:
            self.dev.close()
        except Exception:
            pass

    def _handle(self, data, diag: List[str]) -> None:
        parsed = parse_frame(data)
        if parsed is None:
            return
        cmd_class, value = parsed
        diag.append(f"    received class {cmd_class:02x} value {value}")
        if cmd_class == CLASS_BATTERY and value <= 100:
            self.level = value
            self._next_query = time.monotonic() + REFRESH_S
        elif cmd_class == CLASS_CHARGING and value <= 1:
            self.charging = bool(value)
        elif cmd_class == CLASS_LINK and value == 1:
            self.level = None
            self.charging = False
            self._woken = False
            self._link_up = True
            self._next_query = 0.0

    def _listen(self, seconds: float, diag: List[str]) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            data = self.dev.read(REPORT_LEN, READ_TIMEOUT_MS)
            if data:
                self._handle(data, diag)
                if self.level is not None:
                    return

    def _write(self, frame: bytes) -> None:
        n = self.dev.write(frame)
        if n is None or n < 0:
            raise OSError(f"write failed ({n})")

    def _ask(self, diag: List[str]) -> None:
        if self._link_up:
            self._link_up = False
            time.sleep(LINK_SETTLE_S)
        self.level = None
        for attempt in range(ATTEMPTS):
            if attempt:
                time.sleep(RETRY_S)
            if not self._woken:
                self._write(make_frame(CLASS_INIT, DIR_WAKE))
                self._listen(WAKE_WAIT_S, diag)
                self._write(make_frame(CLASS_CHARGING, DIR_WAKE))
                self._listen(WAKE_WAIT_S, diag)
            self._write(make_frame(CLASS_CHARGING))
            self._listen(WAKE_WAIT_S, diag)
            self._write(make_frame(CLASS_BATTERY))
            self._listen(REPLY_WAIT_S, diag)
            if self.level is not None:
                self._woken = True
                return
        diag.append("    no battery reply (the headset may be off)")
        self._woken = False
        self._next_query = time.monotonic() + REFRESH_S

    def poll(self, diag: List[str]) -> Tuple[Optional[int], bool]:
        for _ in range(MAX_BUFFERED):
            data = self.dev.read(REPORT_LEN, BUFFERED_TIMEOUT_MS)
            if not data:
                break
            self._handle(data, diag)
        if time.monotonic() >= self._next_query:
            self._ask(diag)
        return self.level, self.charging


class RazerReader:
    name = "Razer"

    def __init__(self, extra_pids=()):
        self.extra_pids = set(extra_pids)
        self.diag: List[str] = []
        self._sessions: Dict[bytes, Session] = {}

    def read(self) -> List[Device]:
        self.diag = []
        if hid is None:
            self.diag.append("[Razer] hidapi is not installed")
            return []
        infos = hid.enumerate(VID)
        if not infos:
            self.diag.append("[Razer] no Razer device found")
        for d in infos:
            self.diag.append(f"[Razer] seen: pid={d['product_id']:04x} "
                             f"'{d.get('product_string') or ''}' interface={d.get('interface_number')} "
                             f"usage={d.get('usage_page', 0):04x}:{d.get('usage', 0):04x}")
        found: List[Device] = []
        present = set()
        for d in infos:
            if not is_candidate(d, self.extra_pids):
                continue
            path = d["path"]
            present.add(path)
            pid = d["product_id"]
            name = (d.get("product_string") or "").strip() or KNOWN_PIDS.get(pid, "Razer headset")
            self.diag.append(f"[Razer] pid={pid:04x} '{name}' interface={d.get('interface_number')}")
            try:
                session = self._sessions.get(path)
                if session is None:
                    session = self._sessions[path] = Session(path)
                level, charging = session.poll(self.diag)
            except (OSError, IOError, ValueError) as e:
                self.diag.append(f"    HID error: {e}")
                stale = self._sessions.pop(path, None)
                if stale is not None:
                    stale.close()
                continue
            found.append(Device(f"razer:{pid:04x}", name, KIND_HEADSET, level, charging,
                                level is not None, "Razer"))
        for path in list(self._sessions):
            if path not in present:
                self._sessions.pop(path).close()
        return found

    def close(self):
        for s in self._sessions.values():
            s.close()
        self._sessions.clear()
