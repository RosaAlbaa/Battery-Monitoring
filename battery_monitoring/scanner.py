from __future__ import annotations

import logging
import threading
import time
from typing import Dict, List

from .model import Device

log = logging.getLogger("battery_monitoring")

KEEP_OFFLINE_S = 600


class Scanner:
    def __init__(self, readers):
        self.readers = readers
        self.devices: Dict[str, Device] = {}
        self.owner: Dict[str, str] = {}
        self.diag: List[str] = []
        self.last_scan = 0.0
        self._lock = threading.Lock()

    def scan(self) -> List[Device]:
        diag: List[str] = []
        now = time.time()
        with self._lock:
            for reader in self.readers:
                try:
                    fresh = reader.read()
                except Exception as e:
                    diag.extend(getattr(reader, "diag", []))
                    diag.append(f"[{reader.name}] read error: {e!r}")
                    log.exception("%s could not be read", reader.name)
                    continue
                diag.extend(reader.diag)
                keys = set()
                for dev in fresh:
                    dev.seen = now
                    if dev.level is None and dev.key in self.devices and dev.charging:
                        dev.level = self.devices[dev.key].level
                    self.devices[dev.key] = dev
                    self.owner[dev.key] = reader.name
                    keys.add(dev.key)
                for key, owner in list(self.owner.items()):
                    if owner != reader.name or key in keys:
                        continue
                    dev = self.devices[key]
                    if now - dev.seen > KEEP_OFFLINE_S:
                        del self.devices[key]
                        del self.owner[key]
                    else:
                        dev.online = False
            self.diag = diag
            self.last_scan = now
            return self.snapshot()

    def snapshot(self) -> List[Device]:
        order = {"mouse": 0, "keyboard": 1, "headset": 2, "gamepad": 3}
        return sorted((Device(**vars(d)) for d in self.devices.values()),
                      key=lambda d: (not d.online, order.get(d.kind, 9), d.name.lower()))

    def close(self):
        for reader in self.readers:
            try:
                reader.close()
            except Exception:
                pass


class Alerts:
    def __init__(self, threshold: int, rearm_margin: int = 5):
        self.threshold = threshold
        self.rearm_margin = rearm_margin
        self.warned: set = set()

    def check(self, devices: List[Device]) -> List[Device]:
        low = []
        for d in devices:
            if not d.online or d.level is None:
                continue
            if d.charging or d.level >= self.threshold + self.rearm_margin:
                self.warned.discard(d.key)
                continue
            if d.level < self.threshold and d.key not in self.warned:
                self.warned.add(d.key)
                low.append(d)
        return low
