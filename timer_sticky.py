"""Small, non-activating Windows countdown for use outside the app."""

from __future__ import annotations

import ctypes
import os
import tkinter as tk
from ctypes import wintypes


user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetWindowLongW.restype = wintypes.LONG
user32.SetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.LONG)
user32.SetWindowLongW.restype = wintypes.LONG


def another_app_is_active() -> bool:
    window = user32.GetForegroundWindow()
    if not window:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
    return bool(pid.value and pid.value != os.getpid())


class StickyClock:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.window: tk.Toplevel | None = None
        self.visible = False
        self.dismissed = False
        self.text: tk.Label | None = None
        self.drag = (0, 0)

    def create(self) -> None:
        window = tk.Toplevel(self.root)
        window.withdraw()
        window.overrideredirect(True)
        window.attributes("-toolwindow", True)
        window.attributes("-topmost", True)
        window.configure(bg="#424651")
        window.geometry(f"184x95+{max(16, window.winfo_screenwidth() - 208)}+24")
        window.title("Pomodoro countdown")
        body = tk.Frame(window, bg="#202125")
        body.pack(fill="both", expand=True, padx=1, pady=1)
        heading = tk.Label(body, text="Focus timer", bg="#202125", fg="#a8cdff",
                           font=("Segoe UI Semibold", -13), cursor="fleur")
        heading.place(x=14, y=8)
        heading.bind("<Button-1>", self.start_drag)
        heading.bind("<B1-Motion>", self.move)
        tk.Button(body, text="×", command=self.dismiss, bg="#202125", fg="#b1b4bd",
                  activebackground="#383b44", activeforeground="#ffffff", bd=0,
                  font=("Segoe UI", -19), cursor="hand2").place(relx=1, x=-8, y=4, anchor="ne")
        self.text = tk.Label(body, bg="#202125", fg="#f5f5f7",
                             font=("Segoe UI Semibold", -38), cursor="fleur")
        self.text.place(relx=0.5, y=55, anchor="center")
        self.text.bind("<Button-1>", self.start_drag)
        self.text.bind("<B1-Motion>", self.move)
        self.window = window
        window.update_idletasks()
        hwnd = int(str(window.tk.call("wm", "frame", window._w)), 0)
        style = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, style | 0x08000000)  # WS_EX_NOACTIVATE

    def start_drag(self, event: tk.Event) -> None:
        self.drag = (event.x_root - self.window.winfo_x(), event.y_root - self.window.winfo_y())

    def move(self, event: tk.Event) -> None:
        x, y = event.x_root - self.drag[0], event.y_root - self.drag[1]
        self.window.geometry(f"+{x}+{y}")

    def dismiss(self) -> None:
        self.dismissed = True
        self.hide()

    def hide(self) -> None:
        if self.visible:
            self.window.withdraw()
            self.visible = False

    def update(self, digits: str, running: bool, away: bool) -> None:
        if not away:
            self.dismissed = False
            self.hide()
            return
        if self.dismissed or not (running or self.visible):
            return
        if self.window is None:
            self.create()
        if self.text.cget("text") != digits:
            self.text.configure(text=digits)
        if not self.visible:
            # wm deiconify explicitly activates windows on Windows.
            self.window.state("normal")
            self.visible = True
