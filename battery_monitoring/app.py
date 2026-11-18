from __future__ import annotations

import ctypes
import json
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
from logging.handlers import RotatingFileHandler

import pystray

from . import __version__
from .bluetooth import BluetoothReader
from .i18n import LANGUAGES, Translator
from .logitech import LogitechReader
from .razer import RazerReader
from .scanner import Alerts, Scanner
from .tray import (autostart_enabled, draw_icon, lowest, repair_autostart, set_autostart,
                   taskbar_is_light, tooltip)
from .ui import THEMES, Popup

log = logging.getLogger("battery_monitoring")

APP_NAME = "Battery Monitoring"
DATA_FOLDER = "BatteryMonitoring"
MUTEX_NAME = "Local\\BatteryMonitoring.SingleInstance"

DEFAULTS = {
    "threshold": 20,
    "theme": "dark",
    "language": "en",
    "scan_seconds": 60,
    "bluetooth": True,
    "logitech": True,
    "razer": True,
    "razer_extra_pids": [],
}
THRESHOLD_MIN, THRESHOLD_MAX = 5, 50


def data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, DATA_FOLDER)
    os.makedirs(path, exist_ok=True)
    return path


def config_path() -> str:
    return os.path.join(data_dir(), "settings.json")


def system_language() -> str:
    if sys.platform != "win32":
        return "en"
    try:
        primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
    except (AttributeError, OSError):
        return "en"
    return {0x1F: "tr", 0x04: "zh", 0x0A: "es"}.get(primary, "en")


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(config_path(), encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        cfg["language"] = system_language()
    except (OSError, ValueError) as e:
        log.warning("settings.json could not be read: %s", e)
    save_config(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError as e:
        log.warning("settings.json could not be written: %s", e)


def parse_pids(values) -> list:
    out = []
    for v in values or []:
        try:
            out.append(int(v, 16) if isinstance(v, str) else int(v))
        except ValueError:
            log.warning("invalid PID: %r", v)
    return out


def single_instance() -> bool:
    if sys.platform != "win32":
        return True
    ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return ctypes.windll.kernel32.GetLastError() != 183


def enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


class App:
    def __init__(self):
        self.cfg = load_config()
        self.threshold = max(THRESHOLD_MIN, min(THRESHOLD_MAX, int(self.cfg["threshold"])))
        self.theme = self.cfg["theme"] if self.cfg.get("theme") in THEMES else "dark"
        self.t = Translator(self.cfg.get("language", "en"))
        readers = []
        if self.cfg.get("logitech", True):
            readers.append(LogitechReader())
        if self.cfg.get("razer", True):
            readers.append(RazerReader(parse_pids(self.cfg.get("razer_extra_pids"))))
        if self.cfg.get("bluetooth", True):
            readers.append(BluetoothReader())
        self.scanner = Scanner(readers)
        self.alerts = Alerts(self.threshold)
        self.events: "queue.Queue" = queue.Queue()
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.scanning = False
        self.devices = []

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.popup = Popup(self.root, self)

        self.icon = pystray.Icon(
            "BatteryMonitoring",
            icon=draw_icon(None, False, self.threshold, taskbar_is_light()),
            title=APP_NAME,
            menu=pystray.Menu(
                pystray.MenuItem(lambda item: self.t("menu.show"),
                                 lambda: self.events.put(("toggle",)), default=True),
                pystray.MenuItem(lambda item: self.t("menu.quit"),
                                 lambda: self.events.put(("quit",))),
            ),
        )

    def refresh(self) -> None:
        self.wake.set()

    def set_theme(self, theme: str) -> None:
        if theme in THEMES:
            self.theme = self.cfg["theme"] = theme
            save_config(self.cfg)

    def set_language(self, lang: str) -> None:
        if lang in LANGUAGES:
            self.t = Translator(lang)
            self.cfg["language"] = lang
            save_config(self.cfg)
            self.icon.update_menu()
            self.update_icon()

    def set_threshold(self, value: int) -> None:
        value = max(THRESHOLD_MIN, min(THRESHOLD_MAX, value))
        self.threshold = self.alerts.threshold = self.cfg["threshold"] = value
        save_config(self.cfg)
        self.update_icon()

    def autostart(self) -> bool:
        return autostart_enabled()

    def set_autostart(self, enabled: bool) -> None:
        try:
            set_autostart(enabled)
        except OSError as e:
            log.warning("could not change the startup entry: %s", e)

    def worker(self) -> None:
        interval = max(15, int(self.cfg["scan_seconds"]))
        while not self.stop.is_set():
            self.scanning = True
            self.events.put(("scanning",))
            try:
                devices = self.scanner.scan()
            except Exception:
                log.exception("scan failed")
                devices = self.scanner.snapshot()
            self.scanning = False
            self.events.put(("devices", devices))
            self.wake.wait(interval)
            self.wake.clear()

    def pump(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "devices":
                    self.on_devices(event[1])
                elif kind == "scanning":
                    self.popup.update(self.popup.devices, self.scanner.last_scan, True)
                elif kind == "toggle":
                    self.popup.update(self.scanner.snapshot(), self.scanner.last_scan, self.scanning)
                    self.popup.toggle()
                    if self.popup.visible and not self.scanning \
                            and time.time() - self.scanner.last_scan > 15:
                        self.refresh()
                elif kind == "quit":
                    self.quit()
                    return
        except queue.Empty:
            pass
        self.root.after(150, self.pump)

    def update_icon(self) -> None:
        low = lowest(self.devices)
        charging = any(d.charging and d.online for d in self.devices)
        self.icon.icon = draw_icon(low.level if low else None, charging, self.threshold,
                                   taskbar_is_light())
        self.icon.title = tooltip(self.devices, self.t.pct)

    def on_devices(self, devices) -> None:
        self.devices = devices
        self.popup.update(devices, self.scanner.last_scan, False)
        self.update_icon()
        if not self.icon.visible:
            return
        alerts = self.alerts.check(devices)
        if alerts:
            body = "\n".join(f"{d.name}: {self.t.pct(d.level)}" for d in alerts)
            try:
                self.icon.notify(body + "\n" + self.t("notify.body"), self.t("notify.title"))
            except Exception:
                log.exception("could not show the notification")

    def write_diagnostics(self) -> None:
        path = os.path.join(data_dir(), "diagnostics.txt")
        lines = [f"{APP_NAME} {__version__}", time.strftime("%Y-%m-%d %H:%M:%S"),
                 f"Python {sys.version.split()[0]} {sys.platform}", f"Settings: {self.cfg}", ""]
        lines += self.scanner.diag
        lines += ["", "Devices:"]
        lines += [f"  {d.key} | {d.name} | {d.kind} | {d.level} | charging={d.charging} | "
                  f"online={d.online} | {d.note}" for d in self.scanner.snapshot()]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        try:
            os.startfile(path)
        except (AttributeError, OSError):
            pass

    def quit(self) -> None:
        self.stop.set()
        self.wake.set()
        try:
            self.icon.stop()
        except Exception:
            pass
        self.scanner.close()
        self.root.destroy()

    def run(self) -> None:
        try:
            repair_autostart()
        except OSError as e:
            log.warning("could not update the startup entry: %s", e)
        self.icon.run_detached()
        threading.Thread(target=self.worker, daemon=True).start()
        self.root.after(150, self.pump)
        self.root.mainloop()


def setup_logging() -> None:
    handler = RotatingFileHandler(os.path.join(data_dir(), "log.txt"), maxBytes=500_000,
                                  backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def main() -> None:
    setup_logging()
    if not single_instance():
        return
    enable_dpi_awareness()
    try:
        App().run()
    except Exception:
        log.exception("the app crashed")
        raise
    logging.shutdown()
    os._exit(0)
