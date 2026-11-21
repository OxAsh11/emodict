"""Main app: hold Right-Ctrl to talk, release to transcribe + inject.

Shutdown-race guard (the bug that bit the reference WhisperFlow build):
no new recording starts once shutdown begins, and every worker checks the
shutdown flag immediately before injecting, so text can never land in a
window that regained focus after we quit.
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
        self.recorder = Recorder()
        print("[app] loading model (first run downloads it)...", flush=True)
        self.stt = Transcriber(cfg.model_size, cfg.device, cfg.compute_type, cfg.language)
        print(f"[app] STT ready: model={cfg.model_size} device={self.stt.device} "
              f"compute={self.stt.compute_type}", flush=True)
        self.emotion = EmotionAnalyzer(cfg.emotion_model, enabled=cfg.emotion_enabled)
        self.cleaner = Cleaner(cfg)
        self._worker: threading.Thread | None = None

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
        else:
            print(f"[app] inject_mode={mode}, not injecting")

    def on_press(self, event) -> None:
        if self.shutdown.is_set() or self.recorder.recording:
            return
        self.recorder.start()
        print("[app] recording...", flush=True)

    def on_release(self, event) -> None:
        if self.shutdown.is_set() or not self.recorder.recording:
            return
        self._worker = threading.Thread(target=self._dispatch, daemon=True)
        self._worker.start()

    # ---- lifecycle ---------------------------------------------------------
    def run(self) -> None:
        key = self.cfg.hold_key
        keyboard.on_press_key(key, self.on_press, suppress=False)
        keyboard.on_release_key(key, self.on_release, suppress=False)
        print(f"[app] holding '{key}' to dictate. Ctrl+C here to quit.", flush=True)
        try:
            while not self.shutdown.is_set():
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        print("[app] shutting down...", flush=True)
        self.shutdown.set()
        keyboard.unhook_all()
        if self.recorder.recording:
            self.recorder.stop()
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=10)
        print("[app] stopped clean; no injection can happen after this point.")


def main() -> int:
    cfg = Config()
    if "--no-inject" in sys.argv:  # end-to-end run without pasting anywhere
        cfg.inject_mode = "none"
    if "--dry" in sys.argv:
        cfg.inject_mode = "dry"
    app = App(cfg)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
