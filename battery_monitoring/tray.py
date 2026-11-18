from __future__ import annotations

import os
import sys
from typing import List, Optional

from PIL import Image, ImageDraw

from .model import Device, level_color

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "BatteryMonitoring"


def taskbar_is_light() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "SystemUsesLightTheme")[0] == 1
    except OSError:
        return False


def lowest(devices: List[Device]) -> Optional[Device]:
    live = [d for d in devices if d.online and d.level is not None]
    return min(live, key=lambda d: d.level) if live else None


def draw_icon(level: Optional[int], charging: bool, threshold: int, light: bool, size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    line = (30, 30, 30, 255) if light else (255, 255, 255, 255)
    w = max(2, round(5 * s))
    body = (round(3 * s), round(16 * s), round(53 * s), round(48 * s))
    d.rounded_rectangle(body, radius=round(6 * s), outline=line, width=w)
    d.rounded_rectangle((round(54 * s), round(25 * s), round(61 * s), round(39 * s)),
                        radius=round(2 * s), fill=line)
    if level is not None:
        pad = w + round(3 * s)
        x0, y0, x1, y1 = body[0] + pad, body[1] + pad, body[2] - pad, body[3] - pad
        fill_w = max(round(3 * s), round((x1 - x0) * max(0, min(level, 100)) / 100))
        d.rectangle((x0, y0, x0 + fill_w, y1), fill=level_color(level, threshold))
    if charging:
        cx, cy = 28 * s, 32 * s
        bolt = [(cx + 3 * s, cy - 13 * s), (cx - 7 * s, cy + 2 * s), (cx - 1 * s, cy + 2 * s),
                (cx - 4 * s, cy + 13 * s), (cx + 7 * s, cy - 2 * s), (cx + 1 * s, cy - 2 * s)]
        d.polygon(bolt, fill=(255, 214, 10, 255), outline=(0, 0, 0, 255))
    return img


def tooltip(devices: List[Device], pct=lambda v: "?" if v is None else f"%{v}") -> str:
    lines = ["Battery Monitoring"]
    for d in devices:
        if not d.online:
            continue
        lines.append(f"{d.name}: {pct(d.level)}{' ⚡' if d.charging else ''}")
    text = "\n".join(lines)
    return text if len(text) <= 120 else text[:117] + "..."


def launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):
        exe = pyw
    script = os.path.abspath(sys.argv[0])
    return f'"{exe}" "{script}"'


def autostart_value():
    if sys.platform != "win32":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, RUN_VALUE_NAME)[0]
    except OSError:
        return None


def autostart_enabled() -> bool:
    return autostart_value() is not None


def repair_autostart() -> None:
    value = autostart_value()
    if value is not None and value != launch_command():
        set_autostart(True)


def set_autostart(enabled: bool) -> None:
    if sys.platform != "win32":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, RUN_VALUE_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_VALUE_NAME)
            except OSError:
                pass
