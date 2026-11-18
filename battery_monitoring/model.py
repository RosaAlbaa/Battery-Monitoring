from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

KIND_MOUSE = "mouse"
KIND_KEYBOARD = "keyboard"
KIND_HEADSET = "headset"
KIND_GAMEPAD = "gamepad"
KIND_OTHER = "device"


@dataclass
class Device:
    key: str
    name: str
    kind: str = KIND_OTHER
    level: Optional[int] = None
    charging: bool = False
    online: bool = True
    source: str = ""
    note: str = ""
    seen: float = 0.0


def level_color(level: Optional[int], threshold: int) -> str:
    if level is None:
        return "#8a8a8a"
    if level < threshold:
        return "#f85149"
    if level < threshold + 20:
        return "#d29922"
    return "#3fb950"
