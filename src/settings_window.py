"""Settings window (tkinter, stdlib-only). Owned by the App's hidden root;
opens from the tray. All changes apply live via the on_save callback."""
import tkinter as tk
from tkinter import messagebox, ttk

from . import settings_store
from .config import PROJECT_ROOT, Config
from .wizard import list_mics

MODELS = ["tiny", "base", "small", "medium", "large-v3-turbo"]
INJECT_MODES = [
    ("clipboard", "Paste at cursor (recommended)"),
    ("none", "Print to console only"),
    ("dry", "Dry run (print, mark as inject)"),
]


class SettingsWindow:
    def __init__(self, root: tk.Tk, cfg: Config, on_save):
        self.cfg = cfg
        self.on_save = on_save
        self.win = tk.Toplevel(root)
        self.win.title("EmoDict Settings")
        self.win.geometry("520x600")
        self._apply_icon()
        self.win.protocol("WM_DELETE_WINDOW", self.win.destroy)
        self._build()

    def _apply_icon(self) -> None:
        import sys
        from pathlib import Path

        icon = PROJECT_ROOT / "assets" / "icon.ico"
        if not icon.exists():
            icon = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT)) / "assets" / "icon.ico"
        if icon.exists():
            try:
                self.win.iconbitmap(str(icon))
            except Exception:  # noqa: BLE001 - cosmetic only
                pass

    # ---- UI ------------------------------------------------------------------
    def _build(self) -> None:
        pad = {"padx": 12, "pady": 4}
        f = ttk.Frame(self.win, padding=8)
        f.pack(fill="both", expand=True)

        # Hotkey
        row = ttk.Frame(f); row.pack(fill="x", **pad)
        ttk.Label(row, text="Push-to-talk key (hold to record)").pack(side="left")
        self.hold_var = tk.StringVar(value=self.cfg.hold_key)
        self.hotkey_entry = ttk.Entry(row, textvariable=self.hold_var, width=18,
                                      state="readonly")
        self.hotkey_entry.pack(side="right", padx=(8, 0))
        ttk.Button(row, text="Change", width=7,
                   command=self._capture_hotkey).pack(side="right")

        # Model
        row = ttk.Frame(f); row.pack(fill="x", **pad)
        ttk.Label(row, text="Model (applies after reload)").pack(side="left")
        self.model_var = tk.StringVar(value=self.cfg.model_size)
        ttk.Combobox(row, textvariable=self.model_var, values=MODELS,
                     state="readonly", width=18).pack(side="right")

        # Mic
        row = ttk.Frame(f); row.pack(fill="x", **pad)
        ttk.Label(row, text="Microphone").pack(side="left")
        self.mic_names = ["System default"] + list_mics()
        self.mic_var = tk.StringVar(
            value=self._mic_label(self.cfg.mic_device))
        ttk.Combobox(row, textvariable=self.mic_var, values=self.mic_names,
                     state="readonly", width=34).pack(side="right")

        # Inject mode
        row = ttk.Frame(f); row.pack(fill="x", **pad)
        ttk.Label(row, text="Text output").pack(side="left")
        self.inject_var = tk.StringVar(
            value=dict(INJECT_MODES).get(self.cfg.inject_mode, "clipboard"))
        ttk.Combobox(row, textvariable=self.inject_var,
                     values=[label for _, label in INJECT_MODES],
                     state="readonly", width=30).pack(side="right")

        # Checkboxes
        self.tags_var = tk.BooleanVar(value=self.cfg.show_tone_tags)
        ttk.Checkbutton(f, text="Show tone tags [tone: ...] when emotion data exists",
                        variable=self.tags_var).pack(fill="x", **pad)
        self.emotion_var = tk.BooleanVar(value=self.cfg.emotion_enabled)
        ttk.Checkbutton(f, text="Analyze tone while dictating (emotion2vec, ~600MB one-time)",
                        variable=self.emotion_var).pack(fill="x", **pad)
        self.fillers_var = tk.BooleanVar(value=self.cfg.strip_fillers)
        ttk.Checkbutton(f, text="Strip filler words (um, uh, hmm)",
                        variable=self.fillers_var).pack(fill="x", **pad)
        self.startup_var = tk.BooleanVar(value=self.cfg.start_with_windows)
        ttk.Checkbutton(f, text="Start EmoDict when Windows starts",
                        variable=self.startup_var).pack(fill="x", **pad)

        # Dictionary
        ttk.Label(f, text="Dictionary (one per line:  heard -> corrected)"
                  ).pack(anchor="w", padx=12, pady=(12, 2))
        self.dict_text = tk.Text(f, height=10, font=("Consolas", 10))
        self.dict_text.pack(fill="both", expand=True, padx=12)
        try:
            user_dict = settings_store.user_dictionary_path()
            import json as _json
            self.dict_text.insert("1.0", settings_store.dict_to_text(
                _json.loads(user_dict.read_text(encoding="utf-8"))))
        except Exception:  # noqa: BLE001 - empty editor beats a crash
            pass

        # Buttons
        btns = ttk.Frame(f); btns.pack(pady=10)
        ttk.Button(btns, text="Save", command=self._save).pack(side="left", padx=6)
        ttk.Button(btns, text="Cancel", command=self.win.destroy).pack(side="left")

    # ---- helpers ---------------------------------------------------------------
    def _mic_label(self, device_index: int) -> str:
        if device_index is None or device_index < 0:
            return "System default"
        for name in self.mic_names[1:]:
            if name.startswith(f"[{device_index}]"):
                return name
        return "System default"

    def _mic_index(self, label: str) -> int:
        if label == "System default" or not label.startswith("["):
            return -1
        try:
            return int(label.split("]", 1)[0].lstrip("["))
        except ValueError:
            return -1

    def _capture_hotkey(self) -> None:
        """Grab the next key press as the new push-to-talk key."""
        import threading
        import keyboard

        self.hotkey_entry.configure(state="normal")
        self.hotkey_entry.delete(0, "end")
        self.hotkey_entry.insert(0, "press a key...")
        self.win.update_idletasks()

        def grab():
            event = keyboard.read_event(suppress=False)
            name = event.name or "unknown"
            self.win.after(0, lambda: self._set_hotkey(name))

        threading.Thread(target=grab, daemon=True).start()

    def _set_hotkey(self, name: str) -> None:
        self.hold_var.set(name)
        self.hotkey_entry.configure(state="readonly")

    # ---- save --------------------------------------------------------------------
    def _save(self) -> None:
        cfg = self.cfg
        cfg.hold_key = self.hold_var.get().strip() or "right ctrl"
        cfg.model_size = self.model_var.get()
        cfg.mic_device = self._mic_index(self.mic_var.get())
        cfg.inject_mode = next(
            (k for k, label in INJECT_MODES if label == self.inject_var.get()),
            "clipboard")
        cfg.show_tone_tags = self.tags_var.get()
        cfg.emotion_enabled = self.emotion_var.get()
        cfg.strip_fillers = self.fillers_var.get()

        dictionary, skipped = settings_store.text_to_dict(
            self.dict_text.get("1.0", "end"))
        if skipped:
            if not messagebox.askyesno(
                    "Dictionary",
                    f"{skipped} line(s) couldn't be parsed (need 'heard -> corrected').\n"
                    "Save anyway and skip them?"):
                return
        settings_store.save_user_dictionary(dictionary)

        cfg.start_with_windows = self.startup_var.get()
        if cfg.start_with_windows:
            import sys
            pythonw = sys.executable.replace("python.exe", "pythonw.exe")
            settings_store.set_start_with_windows(
                True, PROJECT_ROOT, pythonw, write=True)
        else:
            settings_store.set_start_with_windows(False, PROJECT_ROOT, "", write=True)

        settings_store.save_settings(cfg)
        self.on_save(cfg)
        self.win.destroy()
