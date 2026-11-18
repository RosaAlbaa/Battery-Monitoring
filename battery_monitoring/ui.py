from __future__ import annotations

import ctypes
import sys
import time
import tkinter as tk
from typing import List, Optional

from .i18n import LANGUAGES
from .model import Device, level_color

THEMES = {
    "dark": {"bg": "#1f1f1f", "card": "#2b2b2b", "fg": "#f3f3f3", "dim": "#a3a3a3",
             "track": "#3c3c3c", "border": "#3a3a3a", "hover": "#383838",
             "accent": "#4c9aff", "accent_fg": "#ffffff"},
    "light": {"bg": "#f3f3f3", "card": "#ffffff", "fg": "#1b1b1b", "dim": "#5f5f5f",
             "track": "#e3e3e3", "border": "#cfcfcf", "hover": "#ebebeb",
             "accent": "#0067c0", "accent_fg": "#ffffff"},
}

if sys.platform == "win32":
    _u32 = ctypes.windll.user32
    _u32.GetForegroundWindow.restype = ctypes.c_void_p
    _u32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    _u32.GetAncestor.restype = ctypes.c_void_p


def work_area(root: tk.Tk):
    if sys.platform == "win32":
        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
        r = RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):
            return r.left, r.top, r.right, r.bottom
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


class Popup:
    """The device window. `app` provides: t (translator), theme, threshold, refresh(),
    set_theme(), set_language(), set_threshold(), autostart(), set_autostart(),
    write_diagnostics()."""

    def __init__(self, root: tk.Tk, app):
        self.root = root
        self.app = app
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96)
        self.win: Optional[tk.Toplevel] = None
        self.view = "devices"
        self.devices: List[Device] = []
        self.last_scan = 0.0
        self.scanning = False
        self._auto_hidden_at = 0.0
        self._baseline = None

    def px(self, v: float) -> int:
        return round(v * self.scale)

    @property
    def c(self) -> dict:
        return THEMES.get(self.app.theme, THEMES["dark"])

    def font(self, size: int, bold: bool = False):
        return (self.app.t.font, size, "bold") if bold else (self.app.t.font, size)

    @property
    def visible(self) -> bool:
        return self.win is not None

    def toggle(self) -> None:
        if self.visible:
            self.hide()
        elif time.monotonic() - self._auto_hidden_at > 0.5:
            self.show()

    def show(self) -> None:
        if self.win is not None:
            self.win.destroy()
        self.view = "devices"
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.bind("<Escape>", lambda e: self.hide())
        self.win = win
        self.render()
        win.lift()
        win.focus_force()
        self._baseline = None
        self.root.after(300, self._watch_foreground)

    def hide(self) -> None:
        if self.win is not None:
            self.win.destroy()
            self.win = None

    def _own_hwnd(self) -> int:
        try:
            hwnd = int(self.win.frame(), 16)
        except (tk.TclError, ValueError):
            hwnd = self.win.winfo_id()
        return ctypes.windll.user32.GetAncestor(hwnd, 2) or hwnd

    def _watch_foreground(self) -> None:
        if self.win is None or sys.platform != "win32":
            return
        user32 = ctypes.windll.user32
        fg = user32.GetForegroundWindow()
        fg_root = user32.GetAncestor(fg, 2) or fg
        ours = fg_root == self._own_hwnd()
        if self._baseline is None:
            self._baseline = "ours" if ours else fg_root
        elif ours:
            self._baseline = "ours"
        elif self._baseline == "ours" or fg_root != self._baseline:
            self._auto_hidden_at = time.monotonic()
            self.hide()
            return
        self.root.after(200, self._watch_foreground)

    def update(self, devices: List[Device], last_scan: float, scanning: bool) -> None:
        self.devices = devices
        self.last_scan = last_scan
        self.scanning = scanning
        if self.win is not None and self.view == "devices":
            self.render()

    def set_view(self, view: str) -> None:
        self.view = view
        self.render()

    def render(self) -> None:
        win = self.win
        if win is None:
            return
        c = self.c
        win.configure(bg=c["bg"])
        for child in win.winfo_children():
            child.destroy()
        width = self.px(340)
        outer = tk.Frame(win, bg=c["bg"], padx=self.px(14), pady=self.px(12),
                         highlightthickness=1, highlightbackground=c["border"])
        outer.pack(fill="both", expand=True)
        if self.view == "settings":
            self._settings(outer, width - self.px(30))
        else:
            self._device_list(outer, width - self.px(30))

        win.update_idletasks()
        h = win.winfo_reqheight()
        left, top, right, bottom = work_area(self.root)
        win.geometry(f"{width}x{h}+{right - width - self.px(12)}+{bottom - h - self.px(12)}")

    def _link(self, parent, text, command, size=9, fg=None, bold=False, bg=None):
        c = self.c
        bg = bg or parent.cget("bg")
        lbl = tk.Label(parent, text=text, bg=bg, fg=fg or c["dim"], font=self.font(size, bold),
                       cursor="hand2", padx=self.px(4), pady=self.px(1))
        lbl.bind("<Button-1>", lambda e: command())
        lbl.bind("<Enter>", lambda e: lbl.configure(bg=c["hover"]))
        lbl.bind("<Leave>", lambda e: lbl.configure(bg=bg))
        return lbl

    def _header(self, parent, title, left_icon=None, left_cmd=None):
        c = self.c
        head = tk.Frame(parent, bg=c["bg"])
        head.pack(fill="x")
        if left_icon:
            self._link(head, left_icon, left_cmd, size=12, fg=c["fg"]).pack(side="left", padx=(0, self.px(4)))
        tk.Label(head, text=title, bg=c["bg"], fg=c["fg"], font=self.font(12, True)).pack(side="left")
        return head

    def _device_list(self, outer, inner_w):
        c, t = self.c, self.app.t
        head = self._header(outer, t("title.devices"))
        self._link(head, "⚙", lambda: self.set_view("settings"), size=12, fg=c["fg"]).pack(side="right")
        self._link(head, "⟳ " + t("btn.refresh"), self.app.refresh).pack(side="right", padx=(0, self.px(6)))

        if self.scanning:
            status = t("status.scanning")
        elif self.last_scan:
            status = t("status.last", t=time.strftime("%H:%M:%S", time.localtime(self.last_scan)))
        else:
            status = t("status.first")
        tk.Label(outer, text=status, bg=c["bg"], fg=c["dim"], font=self.font(8)).pack(
            anchor="w", pady=(0, self.px(8)))

        if not self.devices:
            tk.Label(outer, text=t("empty"), bg=c["bg"], fg=c["dim"],
                     font=self.font(10)).pack(anchor="w", pady=self.px(10))
        for d in self.devices:
            self._row(outer, d, inner_w)

    def _row(self, parent, d: Device, inner_w: int) -> None:
        c, t = self.c, self.app.t
        card = tk.Frame(parent, bg=c["card"], padx=self.px(10), pady=self.px(8))
        card.pack(fill="x", pady=(0, self.px(6)))
        fg = c["fg"] if d.online else c["dim"]
        threshold = self.app.threshold

        top = tk.Frame(card, bg=c["card"])
        top.pack(fill="x")
        tk.Label(top, text=d.name, bg=c["card"], fg=fg, font=self.font(10, True),
                 anchor="w").pack(side="left")
        pct = t.pct(d.level)
        tk.Label(top, text=pct, bg=c["card"],
                 fg=level_color(d.level, threshold) if d.online else c["dim"],
                 font=self.font(11, True)).pack(side="right")

        parts = [t(f"kind.{d.kind}"), d.source]
        if d.charging:
            parts.append("⚡ " + t("state.charging"))
        if not d.online:
            parts.append(t("state.offline"))
        if d.note:
            parts.append(t(d.note) if t.has(d.note) else d.note)
        tk.Label(card, text="  •  ".join(p for p in parts if p), bg=c["card"], fg=c["dim"],
                 font=self.font(8), anchor="w", justify="left",
                 wraplength=inner_w - self.px(20)).pack(fill="x", pady=(self.px(2), self.px(6)))

        bar_h = self.px(6)
        bar = tk.Canvas(card, height=bar_h, bg=c["card"], highlightthickness=0)
        bar.pack(fill="x")
        fill = level_color(d.level, threshold) if d.online else c["dim"]

        def draw(event, bar=bar, level=d.level, fill=fill):
            bar.delete("all")
            bar.create_rectangle(0, 0, event.width, bar_h, fill=c["track"], width=0)
            if level is not None:
                bar.create_rectangle(0, 0, round(event.width * max(0, min(level, 100)) / 100), bar_h,
                                     fill=fill, width=0)

        bar.bind("<Configure>", draw)

    def _section(self, parent, title):
        c = self.c
        tk.Label(parent, text=title, bg=c["bg"], fg=c["dim"], font=self.font(9)).pack(
            anchor="w", pady=(self.px(10), self.px(4)))
        box = tk.Frame(parent, bg=c["bg"])
        box.pack(fill="x")
        return box

    def _choices(self, parent, options, current, command):
        c = self.c
        row = tk.Frame(parent, bg=c["card"], padx=self.px(3), pady=self.px(3))
        row.pack(fill="x")
        for value, label in options:
            selected = value == current
            bg = c["accent"] if selected else c["card"]
            fg = c["accent_fg"] if selected else c["fg"]
            lbl = tk.Label(row, text=label, bg=bg, fg=fg, font=self.font(9, selected),
                           cursor="hand2", pady=self.px(5))
            lbl.pack(side="left", fill="x", expand=True, padx=self.px(1))
            if not selected:
                lbl.bind("<Button-1>", lambda e, v=value: command(v))
                lbl.bind("<Enter>", lambda e, l=lbl: l.configure(bg=c["hover"]))
                lbl.bind("<Leave>", lambda e, l=lbl: l.configure(bg=c["card"]))

    def _action(self, parent, text, command):
        c = self.c
        row = tk.Frame(parent, bg=c["card"], padx=self.px(10), pady=self.px(8), cursor="hand2")
        row.pack(fill="x", pady=(0, self.px(4)))
        lbl = tk.Label(row, text=text, bg=c["card"], fg=c["fg"], font=self.font(10), anchor="w")
        lbl.pack(side="left")
        arrow = tk.Label(row, text="›", bg=c["card"], fg=c["dim"], font=self.font(12))
        arrow.pack(side="right")
        for w in (row, lbl, arrow):
            w.bind("<Button-1>", lambda e: command())
            w.bind("<Enter>", lambda e: [x.configure(bg=c["hover"]) for x in (row, lbl, arrow)])
            w.bind("<Leave>", lambda e: [x.configure(bg=c["card"]) for x in (row, lbl, arrow)])
        return row, lbl

    def _settings(self, outer, inner_w):
        c, t, app = self.c, self.app.t, self.app
        self._header(outer, t("title.settings"), "←", lambda: self.set_view("devices"))

        box = self._section(outer, t("set.theme"))
        self._choices(box, [("dark", t("theme.dark")), ("light", t("theme.light"))],
                      app.theme, lambda v: (app.set_theme(v), self.render()))

        box = self._section(outer, t("set.language"))
        self._choices(box, list(LANGUAGES.items()), app.t.lang,
                      lambda v: (app.set_language(v), self.render()))

        box = self._section(outer, t("set.threshold"))
        row = tk.Frame(box, bg=c["card"], padx=self.px(6), pady=self.px(4))
        row.pack(fill="x")
        self._link(row, "−", lambda: (app.set_threshold(app.threshold - 5), self.render()),
                   size=13, fg=c["fg"]).pack(side="left")
        tk.Label(row, text=t.pct(app.threshold), bg=c["card"], fg=c["fg"],
                 font=self.font(11, True)).pack(side="left", expand=True)
        self._link(row, "+", lambda: (app.set_threshold(app.threshold + 5), self.render()),
                   size=13, fg=c["fg"]).pack(side="right")

        tk.Frame(outer, bg=c["bg"], height=self.px(10)).pack(fill="x")
        on = app.autostart()
        row, lbl = self._action(outer, ("☑  " if on else "☐  ") + t("set.autostart"),
                                lambda: (app.set_autostart(not on), self.render()))
        self._action(outer, t("set.diag"), app.write_diagnostics)
