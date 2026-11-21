"""GUI first-run onboarding (used in packaged builds; console wizard stays for
dev). One window: hardware probe + model pick, mic pick + live test, one-click
install (model download with status), then hand off to the tray app.

run_wizard_gui(auto_yes=True) is the scripted path (agent/tests/CI): probe,
download recommended model, write settings, no window.
"""
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from . import settings_store
from .config import Config
from .hardware import probe, recommend_model
from .wizard import list_mics

MODELS = ["tiny", "base", "small", "medium", "large-v3-turbo"]


def _scripted_wizard() -> Config:
    hw = probe()
    model, _reason = recommend_model(hw)
    print(f"[wizard] scripted: model={model} gpu={hw['gpu']['name'] if hw['gpu'] else 'none'}")
    from .transcriber import Transcriber

    t0 = time.perf_counter()
    stt = Transcriber(model, "auto", "auto")
    print(f"[wizard] model ready in {time.perf_counter()-t0:.1f}s "
          f"(device={stt.device})")
    cfg = Config()
    cfg.model_size = model
    cfg.onboarding_pending = True
    settings_store.save_settings(cfg)
    return cfg


class WizardGUI:
    def __init__(self):
        self.cfg_done: Config | None = None
        self.q: queue.Queue = queue.Queue()
        self.root = tk.Tk()
        self.root.title("EmoDict setup")
        self.root.geometry("520x430")
        self._apply_icon()
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)
        self._build()
        self.root.after(100, self._poll)

    def _apply_icon(self) -> None:
        import sys
        from pathlib import Path

        from .config import PROJECT_ROOT

        icon = PROJECT_ROOT / "assets" / "icon.ico"
        if not icon.exists():
            icon = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT)) / "assets" / "icon.ico"
        if icon.exists():
            try:
                self.root.iconbitmap(str(icon))
            except Exception:  # noqa: BLE001
                pass

    # ---- UI --------------------------------------------------------------
    def _build(self) -> None:
        f = ttk.Frame(self.root, padding=16)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Welcome to EmoDict", font=("Segoe UI", 16, "bold")
                  ).pack(anchor="w")
        ttk.Label(f, text="Takes about a minute. Then: hold Right-Ctrl, speak, "
                          "release - everywhere on your PC.",
                  foreground="#666").pack(anchor="w", pady=(0, 14))

        hw = probe()
        gpu = hw["gpu"]["name"] if hw["gpu"] else None
        ttk.Label(f, text=f"Hardware: {gpu or 'no NVIDIA GPU'} - "
                          f"{hw['cpu_cores']} cores, {hw['ram_gb']}GB RAM"
                  ).pack(anchor="w")

        model, reason = recommend_model(hw)
        row = ttk.Frame(f); row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="Speech model:").pack(side="left")
        self.model_var = tk.StringVar(value=model)
        ttk.Combobox(row, textvariable=self.model_var, values=MODELS,
                     state="readonly", width=18).pack(side="right")
        ttk.Label(f, text=reason, foreground="#666",
                  wraplength=480).pack(anchor="w", pady=(0, 10))

        ttk.Label(f, text="Microphone:").pack(anchor="w")
        self.mic_names = ["System default"] + list_mics()
        self.mic_var = tk.StringVar(value="System default")
        ttk.Combobox(f, textvariable=self.mic_var, values=self.mic_names,
                     state="readonly").pack(fill="x")
        self.test_btn = ttk.Button(f, text="Test microphone (speak for 3s)",
                                   command=self._test_mic)
        self.test_btn.pack(anchor="w", pady=4)
        self.level = ttk.Progressbar(f, length=260, mode="determinate",
                                     maximum=100)
        self.level.pack(anchor="w", pady=(0, 10))

        self.status = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.status, foreground="#0a7").pack(anchor="w")

        self.go_btn = ttk.Button(f, text="Install and start dictating",
                                 command=self._install)
        self.go_btn.pack(anchor="w", pady=10)

    # ---- actions -----------------------------------------------------------
    def _test_mic(self) -> None:
        self.test_btn.state(["disabled"])
        self.status.set("")
        threading.Thread(target=self._meter, daemon=True).start()

    def _meter(self) -> None:
        import numpy as np
        import sounddevice as sd

        peak = [0.0]

        def cb(indata, frames, t, status):
            peak[0] = max(peak[0], float(np.abs(indata).max()))

        try:
            with sd.InputStream(samplerate=16000, channels=1, callback=cb):
                t0 = time.perf_counter()
                while time.perf_counter() - t0 < 3.0:
                    time.sleep(0.05)
                    self.q.put(("level", min(int(peak[0] * 300), 100)))
            self.q.put(("level_msg", "heard you" if peak[0] > 0.01
                        else "near-zero input - check mic / privacy settings"))
        except Exception as e:  # noqa: BLE001
            self.q.put(("level_msg", f"mic test failed: {e}"))
        self.q.put(("test_done", None))

    def _install(self) -> None:
        self.go_btn.state(["disabled"])
        self.status.set("Preparing...")
        threading.Thread(target=self._install_worker, daemon=True).start()

    def _install_worker(self) -> None:
        try:
            from .transcriber import Transcriber

            t0 = time.perf_counter()
            self.q.put(("status", "Downloading speech model (one time, "
                                  "150-800MB)..."))
            stt = Transcriber(self.model_var.get(), "auto", "auto")
            self.q.put(("status", f"Model ready ({time.perf_counter()-t0:.0f}s, "
                                  f"{stt.device}). Saving settings..."))
            cfg = Config()
            cfg.model_size = self.model_var.get()
            cfg.onboarding_pending = True
            settings_store.save_settings(cfg)
            self.cfg_done = cfg
            self.q.put(("done", None))
        except Exception as e:  # noqa: BLE001
            self.q.put(("error", f"{e.__class__.__name__}: {e}"))

    # ---- plumbing ------------------------------------------------------------
    def _poll(self) -> None:
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "level":
                    self.level["value"] = val
                elif kind == "level_msg":
                    self.status.set(val)
                elif kind == "test_done":
                    self.test_btn.state(["!disabled"])
                elif kind == "status":
                    self.status.set(val)
                elif kind == "error":
                    self.status.set(f"Setup failed: {val}")
                    self.go_btn.state(["!disabled"])
                elif kind == "done":
                    self.status.set("Setup complete. Starting EmoDict - "
                                    "hold Right-Ctrl to dictate.")
                    self.root.after(1500, self.root.destroy)
        except queue.Empty:
            pass
        if not self._closing:
            self.root.after(100, self._poll)

    _closing = False

    def _cancel(self) -> None:
        self._closing = True
        self.root.destroy()

    def run(self) -> Config | None:
        self.root.mainloop()
        return self.cfg_done


def run_wizard_gui(auto_yes: bool = False) -> Config:
    if auto_yes or "--yes" in __import__("sys").argv:
        return _scripted_wizard()
    result = WizardGUI().run()
    if result is None:  # user closed the window: safe defaults, no mic test
        result = Config()
        model, _ = recommend_model(probe())
        result.model_size = model
        settings_store.save_settings(result)
    return result
