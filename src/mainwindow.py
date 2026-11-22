"""Main window: the app's visible face. Shows on every launch.

- status: how to dictate, engine state (model/device, emotion ready or loading)
- ledger: every take ever (history.log) with time, latency, tone, text; searchable
- actions: Settings, Performance dashboard, Pause, Hide-to-tray

Closing the window hides it to the tray; the app keeps running.
"""
import tkinter as tk
from tkinter import ttk

from . import stats


class MainWindow:
    def __init__(self, root: tk.Tk, app):
        self.root = root
        self.app = app
        self.win = tk.Toplevel(root)
        self.win.title("EmoDict")
        self.win.geometry("760x520")
        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        self._apply_icon()
        self._build()
        self.refresh()

    def _apply_icon(self) -> None:
        import sys
        from pathlib import Path

        from .config import PROJECT_ROOT

        icon = PROJECT_ROOT / "assets" / "icon.ico"
        if not icon.exists():
            icon = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT)) / "assets" / "icon.ico"
        if icon.exists():
            try:
                self.win.iconbitmap(str(icon))
            except Exception:  # noqa: BLE001
                pass

    # ---- UI --------------------------------------------------------------
    def _build(self) -> None:
        top = ttk.Frame(self.win, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="Hold Right-Ctrl, speak, release.",
                  font=("Segoe UI", 15, "bold")).pack(anchor="w")
        self.status_var = tk.StringVar(value="starting...")
        ttk.Label(top, textvariable=self.status_var,
                  foreground="#555").pack(anchor="w", pady=(2, 8))

        btns = ttk.Frame(top)
        btns.pack(anchor="w")
        ttk.Button(btns, text="Settings", command=self._settings).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Performance dashboard",
                   command=self._dashboard).pack(side="left", padx=(0, 6))
        self.pause_btn = ttk.Button(btns, text="Pause", command=self._pause)
        self.pause_btn.pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Hide to tray", command=self.hide).pack(side="left")

        mid = ttk.Frame(self.win, padding=(12, 0))
        mid.pack(fill="both", expand=True)
        ttk.Label(mid, text="Dictation history").pack(anchor="w", pady=(6, 2))
        row = ttk.Frame(mid); row.pack(fill="x")
        ttk.Label(row, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh())
        ttk.Entry(row, textvariable=self.search_var).pack(side="left", fill="x",
                                                          expand=True, padx=6)
        cols = ("time", "latency", "tone", "text")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", height=14)
        for col, width, anchor in (("time", 120, "w"), ("latency", 70, "e"),
                                   ("tone", 90, "w"), ("text", 420, "w")):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=width, anchor=anchor, stretch=(col == "text"))
        # copy support: double-click or Ctrl+C copies the FULL take text
        self.tree.bind("<Double-1>", self._copy_selected)
        self.tree.bind("<Control-c>", self._copy_selected)
        self._takes = []
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True, pady=(4, 12))
        sb.pack(side="left", fill="y", pady=(4, 12))

    # ---- actions ------------------------------------------------------------
    def _settings(self) -> None:
        self.app.open_settings()

    def _dashboard(self) -> None:
        self.app.open_dashboard()

    def _pause(self) -> None:
        self.app.toggle_pause()
        self.pause_btn.configure(text="Resume" if self.app.paused else "Pause")

    # ---- data ------------------------------------------------------------------
    def refresh(self) -> None:
        stt = getattr(self.app, "stt", None)
        emo = getattr(self.app, "emotion", None)
        status = []
        if stt is not None:
            status.append(f"{stt.device} - {self.app.cfg.model_size}")
        status.append("tone tags ON" if (emo is not None and emo.enabled)
                      else "tone tags loading/off")
        if self.app.paused:
            status.append("PAUSED")
        self.status_var.set("   ".join(status))

        self.tree.delete(*self.tree.get_children())
        needle = self.search_var.get().strip().lower()
        try:
            takes = stats.parse_history(self.app.cfg.history_path)
        except Exception:  # noqa: BLE001
            takes = []
        self._takes = list(takes[-300:])
        shown = 0
        for idx, t in enumerate(reversed(self._takes)):  # newest first
            tone = ", ".join(t.tags) if t.tags else "-"
            lat = f"{t.elapsed:.1f}s" if t.elapsed is not None else "FAIL"
            text = t.text or "-"
            if needle and needle not in text.lower() and needle not in tone.lower():
                continue
            # iid maps the row back to the full (untruncated) take
            self.tree.insert("", "end", iid=str(len(self._takes) - 1 - idx),
                             values=(t.ts.strftime("%d %b %H:%M:%S"), lat, tone,
                                     text[:160]))
            shown += 1

    def _copy_selected(self, _event=None) -> None:
        """Double-click / Ctrl+C: full take text (untruncated) to clipboard."""
        sel = self.tree.selection()
        if not sel:
            return
        take = self._takes[int(sel[0])]
        self.win.clipboard_clear()
        self.win.clipboard_append(take.text or "")
        self.status_var.set(f"copied take from "
                            f"{take.ts.strftime('%H:%M:%S')} to clipboard")
        self.root.after(2500, lambda: None)

    # ---- lifecycle ----------------------------------------------------------
    def show(self) -> None:
        self.win.deiconify()
        self.win.lift()
        self.refresh()

    def hide(self) -> None:
        self.win.withdraw()
