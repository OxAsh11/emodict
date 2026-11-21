"""Welcome card shown after first-run setup; closes itself after the user's
first successful dictation (paste done)."""
import tkinter as tk
from tkinter import ttk


class WelcomeCard:
    def __init__(self, root: tk.Tk, on_finish):
        self.on_finish = on_finish
        self.win = tk.Toplevel(root)
        self.win.title("EmoDict - you're set")
        self.win.geometry("440x300")
        self.win.attributes("-topmost", True)
        self.win.protocol("WM_DELETE_WINDOW", self.finish)
        self._build()

    def _build(self) -> None:
        f = ttk.Frame(self.win, padding=20)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="You're set.", font=("Segoe UI", 16, "bold")
                  ).pack(anchor="w")
        ttk.Label(f, text="Hold Right-Ctrl, speak, release - your words "
                          "appear at your cursor. Works in every app.",
                  wraplength=390).pack(anchor="w", pady=(6, 12))
        ttk.Label(f, text="While you hold the key a red 'recording' chip "
                          "appears at the bottom of the screen; it turns "
                          "amber while your words are being written.",
                  wraplength=390, foreground="#555").pack(anchor="w")
        ttk.Label(f, text="Right-click the mic icon in the tray for settings, "
                          "the performance dashboard, pause and quit.",
                  wraplength=390, foreground="#555").pack(anchor="w", pady=(8, 0))
        ttk.Label(f, text="This window closes itself after your first "
                          "dictation. Go ahead - try it now.",
                  wraplength=390, foreground="#0a7").pack(anchor="w", pady=(12, 4))

    def show(self) -> None:
        self.win.deiconify()
        self.win.lift()

    def finish(self) -> None:
        try:
            self.win.destroy()
        finally:
            if self.on_finish is not None:
                self.on_finish()
                self.on_finish = None
