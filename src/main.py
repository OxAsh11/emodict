"""Main app: tray-hosted push-to-talk dictation.

Threading model:
- Main thread: hidden tkinter root mainloop (owns any settings window)
- pystray: detached thread; callbacks marshalled to main thread via root.after
- keyboard hooks: library-internal thread; transcription on a worker thread
- Shutdown guard: no recording starts and no injection happens once
  shutdown begins (the reference-build race that pasted into random windows).
Run with --console to keep the old console-only behaviour.
"""
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import keyboard

from .cleanup import Cleaner
from .config import Config
from .emotion import EmotionAnalyzer
from .injector import inject
from .recorder import Recorder
from .transcriber import Transcriber


class App:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.shutdown = threading.Event()
        self.paused = False
        self._model_lock = threading.Lock()
        self._loading_model = False
        self.recorder = Recorder(device=cfg.mic_device)
        self.root = None          # set by run(); tkinter main thread
        self.tray = None          # set by run()
        self._settings_win = None
        self._worker: threading.Thread | None = None
        self._hotkeys_bound = False

        print("[app] loading model...", flush=True)
        self.stt = Transcriber(cfg.model_size, cfg.device, cfg.compute_type, cfg.language)
        print(f"[app] STT ready: model={cfg.model_size} device={self.stt.device} "
              f"compute={self.stt.compute_type}", flush=True)
        self.emotion = EmotionAnalyzer(cfg.emotion_model, enabled=cfg.emotion_enabled)
        self.cleaner = Cleaner(cfg)

    # ---- pipeline --------------------------------------------------------
    def process(self, audio) -> str | None:
        if audio is None or len(audio) == 0:
            return None
        segments = self.stt.transcribe(audio)
        if not segments:
            return None
        emotions = self.emotion.analyze(audio, 16000, segments)
        text = self.cleaner.format_output(segments, emotions)
        self._log_take(segments, emotions, text)
        return text or None

    def _log_take(self, segments, emotions, text: str) -> None:
        if not self.cfg.log_takes:
            return
        try:
            p = Path(self.cfg.history_path)
            with p.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat(timespec='seconds')} | "
                        f"{sum(s['end'] - s['start'] for s in segments):.1f}s | "
                        f"{[e['label'] for e in emotions]} | {text}\n")
        except OSError as e:
            print(f"[app] history write failed: {e}")

    # ---- worker ------------------------------------------------------------
    def _dispatch(self) -> None:
        audio = self.recorder.stop()
        if self.shutdown.is_set():  # quit began while recording: drop the take
            return
        t0 = time.perf_counter()
        text = self.process(audio)
        elapsed = time.perf_counter() - t0
        if text is None:
            print(f"[app] nothing transcribed ({elapsed:.2f}s)")
            return
        if self.shutdown.is_set():  # re-check immediately before injecting
            return
        mode = self.cfg.inject_mode
        print(f"[app] {elapsed:.2f}s: {text}")
        if mode == "clipboard":
            inject(text, settle_s=self.cfg.paste_settle_s)
        elif mode == "dry":
            inject(text, dry_run=True)
        else:
            print(f"[app] inject_mode={mode}, not injecting")

    def on_press(self, event) -> None:
        if self.shutdown.is_set() or self.paused or self._loading_model:
            return
        if not self.recorder.recording:
            self.recorder = Recorder(device=self.cfg.mic_device)
            self.recorder.start()
            print("[app] recording...", flush=True)

    def on_release(self, event) -> None:
        if self.shutdown.is_set() or not self.recorder.recording:
            return
        self._worker = threading.Thread(target=self._dispatch, daemon=True)
        self._worker.start()

    # ---- hotkey binding ------------------------------------------------------
    def _bind_hotkey(self) -> None:
        if self._hotkeys_bound:
            keyboard.unhook_all()
        keyboard.on_press_key(self.cfg.hold_key, self.on_press, suppress=False)
        keyboard.on_release_key(self.cfg.hold_key, self.on_release, suppress=False)
        self._hotkeys_bound = True
        print(f"[app] holding '{self.cfg.hold_key}' to dictate. "
              f"Tray menu: Settings / Pause / Quit.", flush=True)

    # ---- settings / pause ------------------------------------------------------
    def open_settings(self) -> None:
        if self.root is None or self.shutdown.is_set():
            return
        self.root.after(0, self._open_settings_on_main)

    def _open_settings_on_main(self) -> None:
        if self._settings_win is not None and self._settings_win.win.winfo_exists():
            self._settings_win.win.lift()
            return
        from .settings_window import SettingsWindow

        self._settings_win = SettingsWindow(self.root, self.cfg, on_save=self.apply_settings)

    def apply_settings(self, cfg: Config) -> None:
        """Live-apply what was saved: hotkey + mic + cleaner now, model async."""
        old_model = self.cfg.model_size
        self.cfg = cfg
        self.cleaner = Cleaner(cfg)
        self._bind_hotkey()  # rebinds with the (possibly new) key
        print(f"[app] settings applied (hotkey={cfg.hold_key}, mic={cfg.mic_device}, "
              f"inject={cfg.inject_mode})", flush=True)
        if cfg.model_size != old_model:
            threading.Thread(target=self._reload_model, daemon=True).start()

    def _reload_model(self) -> None:
        with self._model_lock:
            self._loading_model = True
            try:
                print(f"[app] reloading model -> {self.cfg.model_size}...", flush=True)
                self.stt = Transcriber(self.cfg.model_size, self.cfg.device,
                                       self.cfg.compute_type, self.cfg.language)
                print(f"[app] model ready (device={self.stt.device})", flush=True)
            except Exception as e:  # noqa: BLE001 - keep dictating on the old model
                print(f"[app] model reload FAILED ({e}); keeping previous model", flush=True)
            finally:
                self._loading_model = False

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        if self.paused and self.recorder.recording:
            self.recorder.stop()
        if self.tray is not None:
            self.tray.set_paused(self.paused)
        print(f"[app] {'paused' if self.paused else 'resumed'}", flush=True)

    # ---- lifecycle ---------------------------------------------------------
    def run(self) -> None:
        if "--console" in sys.argv:
            self._bind_hotkey()
            try:
                while not self.shutdown.is_set():
                    time.sleep(0.2)
            except KeyboardInterrupt:
                pass
            finally:
                self.stop()
            return

        # GUI mode: hidden root owns windows; tray runs detached.
        import tkinter as tk

        self.root = tk.Tk()
        self.root.withdraw()
        from .tray import Tray

        self.tray = Tray(on_settings=self.open_settings,
                         on_toggle_pause=self.toggle_pause,
                         on_quit=lambda: self.root.after(0, self.root.quit))
        self.tray.start()
        self._bind_hotkey()
        try:
            self.root.mainloop()
        finally:
            self.stop()

    def stop(self) -> None:
        if self.shutdown.is_set():
            return
        print("[app] shutting down...", flush=True)
        self.shutdown.set()
        try:
            keyboard.unhook_all()
        except Exception:  # noqa: BLE001
            pass
        if self.recorder.recording:
            self.recorder.stop()
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=10)
        if self.tray is not None:
            self.tray.stop()
        print("[app] stopped clean; no injection can happen after this point.")


def main() -> int:
    from . import settings_store
    from .wizard import run_wizard

    if settings_store.settings_exist():
        cfg = settings_store.load_settings()
    else:
        print("[app] no settings found, starting first-run setup\n")
        cfg = run_wizard(auto_yes="--yes" in sys.argv)

    if "--no-inject" in sys.argv:  # end-to-end run without pasting anywhere
        cfg.inject_mode = "none"
    if "--dry" in sys.argv:
        cfg.inject_mode = "dry"
    app = App(cfg)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
