"""Main app: tray-hosted push-to-talk dictation.

Threading model:
- Main thread: hidden tkinter root mainloop (owns any settings window)
- pystray: detached thread; callbacks marshalled to main thread via root.after
- keyboard hooks: library-internal thread; transcription on a worker thread
- Shutdown guard: no recording starts and no injection happens once
  shutdown begins (the reference-build race that pasted into random windows).
Run with --console to keep the old console-only behaviour.
"""
import os
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
        self.recorder = None          # created after model load (persistent stream)
        self.root = None          # set by run(); tkinter main thread
        self.overlay = None       # set by run(); recording indicator
        self.tray = None          # set by run()
        self.mainwin = None       # set by run(); the visible main window
        self.welcome = None       # set by run(); first-run welcome card
        self._settings_win = None
        self._worker: threading.Thread | None = None
        self._hotkeys_bound = False

        print("[app] loading model...", flush=True)
        self.stt = Transcriber(cfg.model_size, cfg.device, cfg.compute_type,
                               cfg.language, cfg.beam_size)
        print(f"[app] STT ready: model={cfg.model_size} device={self.stt.device} "
              f"compute={self.stt.compute_type}", flush=True)
        self.emotion = EmotionAnalyzer(cfg.emotion_model, enabled=False)
        if cfg.emotion_enabled:  # big model: load off the startup path
            threading.Thread(target=self._load_emotion, daemon=True).start()
        self.cleaner = Cleaner(cfg)
        try:
            self.recorder = Recorder(device=cfg.mic_device)  # stream stays open
            print("[app] mic stream open (persistent, pre-roll armed)", flush=True)
        except Exception as e:  # noqa: BLE001 - app starts, hotkey will report
            self.recorder = None
            print(f"[app] MIC OPEN FAILED: {e}", flush=True)

    # ---- pipeline --------------------------------------------------------
    def process(self, audio) -> tuple[str | None, list, list]:
        """Returns (text, segments, emotions); logging happens in _dispatch
        where the latency is known."""
        if audio is None or len(audio) == 0:
            return None, [], []
        segments = self.stt.transcribe(audio)
        if not segments:
            return None, [], []
        # emotion is scored on the WHOLE take, not per segment: the prosodic
        # signal of desk-voice frustration lives in the full utterance and
        # collapses when chopped (measured: founder take angry=0.123 whole,
        # 0.000-0.009 per segment). The tag rides at the front of the output.
        emotions = self.emotion.analyze(audio, 16000, None)
        text = self.cleaner.format_output(segments, emotions)
        return (text or None), segments, emotions

    def _log_take(self, segments, emotions, text: str, elapsed: float | None) -> None:
        if not self.cfg.log_takes:
            return
        audio_s = sum(s["end"] - s["start"] for s in segments)
        tags = [e["label"] for e in emotions]
        try:
            p = Path(self.cfg.history_path)
            with p.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat(timespec='seconds')} | "
                        f"{f'{elapsed:.2f}' if elapsed is not None else 'FAIL'} | "
                        f"{audio_s:.1f} | {tags} | {text}\n")
        except OSError as e:
            print(f"[app] history write failed: {e}")

    # ---- worker ------------------------------------------------------------
    def _dispatch(self) -> None:
        self._overlay_show("processing")
        audio = self.recorder.stop()
        if audio is not None and len(audio) and os.environ.get("EMO_KEEP_AUDIO"):
            self._dump_take(audio)
        if self.shutdown.is_set():  # quit began while recording: drop the take
            return
        t0 = time.perf_counter()
        try:
            text, segments, emotions = self.process(audio)
        except Exception as e:  # noqa: BLE001 - one bad take never kills the app
            from .crash import log_exception

            log_exception("dictation worker", e)
            print(f"[app] take failed ({e.__class__.__name__}: {e}); "
                  f"continuing - see crash.log", flush=True)
            return
        elapsed = time.perf_counter() - t0
        self._log_take(segments, emotions, text or "", elapsed if text else None)
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
        self._overlay_hide()
        if self.mainwin is not None and self.root is not None:
            self.root.after(0, self.mainwin.refresh)
        if self.cfg.onboarding_pending and self.welcome is not None:
            self.root.after(0, self.welcome.finish)

    def _dump_take(self, audio) -> None:
        """Debug: save the raw take for offline tone-score analysis."""
        try:
            import soundfile as sf

            d = (Path(os.getenv("LOCALAPPDATA", ".")) / "EmoDict" / "debug")
            d.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%H%M%S")
            sf.write(str(d / f"take_{ts}.wav"), audio, 16000)
            print(f"[app] debug: saved take_{ts}.wav", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[app] debug dump failed: {e}", flush=True)

    def on_press(self, event) -> None:
        if self.shutdown.is_set() or self.paused or self._loading_model:
            return
        if self.recorder is not None and not self.recorder.recording:
            self.recorder.start()
            self._overlay_show("recording")
            print("[app] recording...", flush=True)

    def on_release(self, event) -> None:
        if self.shutdown.is_set() or self.recorder is None or not self.recorder.recording:
            return
        self._worker = threading.Thread(target=self._dispatch, daemon=True)
        self._worker.start()

    # ---- overlay (visible feedback while dictating) ---------------------------
    def _overlay_show(self, state: str) -> None:
        if self.overlay is not None and self.root is not None:
            self.root.after(0, lambda: self.overlay.show(state))

    def _overlay_hide(self) -> None:
        if self.overlay is not None and self.root is not None:
            self.root.after(0, self.overlay.hide)

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
        old_mic = self.cfg.mic_device
        old_emotion = self.cfg.emotion_enabled
        self.cfg = cfg
        self.cleaner = Cleaner(cfg)
        self._bind_hotkey()  # rebinds with the (possibly new) key
        if cfg.mic_device != old_mic:  # rebuild the persistent stream
            old_recorder = self.recorder
            try:
                self.recorder = Recorder(device=cfg.mic_device)
                if old_recorder is not None:
                    old_recorder.close()
                print("[app] mic stream rebuilt", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[app] mic switch FAILED ({e}); keeping old stream", flush=True)
        print(f"[app] settings applied (hotkey={cfg.hold_key}, mic={cfg.mic_device}, "
              f"inject={cfg.inject_mode})", flush=True)
        if cfg.model_size != old_model:
            threading.Thread(target=self._reload_model, daemon=True).start()
        if cfg.emotion_enabled and not old_emotion:
            threading.Thread(target=self._load_emotion, daemon=True).start()
        elif not cfg.emotion_enabled and old_emotion:
            self.emotion = EmotionAnalyzer(cfg.emotion_model, enabled=False)
            print("[app] emotion analysis off", flush=True)

    def _reload_model(self) -> None:
        with self._model_lock:
            self._loading_model = True
            try:
                print(f"[app] reloading model -> {self.cfg.model_size}...", flush=True)
                self.stt = Transcriber(self.cfg.model_size, self.cfg.device,
                                       self.cfg.compute_type, self.cfg.language,
                                       self.cfg.beam_size)
                print(f"[app] model ready (device={self.stt.device})", flush=True)
            except Exception as e:  # noqa: BLE001 - keep dictating on the old model
                print(f"[app] model reload FAILED ({e}); keeping previous model", flush=True)
            finally:
                self._loading_model = False

    def _load_emotion(self) -> None:
        t0 = time.perf_counter()
        ea = EmotionAnalyzer(self.cfg.emotion_model, enabled=True)
        if ea.enabled and not self.shutdown.is_set():
            self.emotion = ea
            print(f"[app] emotion model ready in {time.perf_counter()-t0:.1f}s "
                  f"(tone tags live)", flush=True)
        elif not ea.enabled:
            print("[app] emotion model unavailable; tags stay off", flush=True)
        if self.mainwin is not None and self.root is not None and not self.shutdown.is_set():
            self.root.after(0, self.mainwin.refresh)

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        if self.paused and self.recorder is not None and self.recorder.recording:
            self.recorder.stop()
        if self.tray is not None:
            self.tray.set_paused(self.paused)
        print(f"[app] {'paused' if self.paused else 'resumed'}", flush=True)

    def _onboarding_done(self) -> None:
        self.cfg.onboarding_pending = False
        try:
            from . import settings_store

            settings_store.save_settings(self.cfg)
            print("[app] onboarding complete (first dictation done)", flush=True)
        except Exception as e:  # noqa: BLE001 - never block on a settings write
            print(f"[app] could not clear onboarding flag: {e}", flush=True)

    # ---- dashboard -------------------------------------------------------------
    def open_dashboard(self) -> None:
        import webbrowser

        from . import dashboard
        from .update_check import VERSION

        url = dashboard.ensure_running(
            self.cfg.history_path, self.cfg.dashboard_port,
            model=self.cfg.model_size, device=self.stt.device, version=VERSION)
        print(f"[app] dashboard: {url}", flush=True)
        webbrowser.open(url)

    # ---- updates -------------------------------------------------------------
    def check_update_notify(self) -> None:
        from .update_check import check_for_update

        avail, latest, current = check_for_update()
        msg = (f"Update available: {latest} (you have {current})."
               if avail else f"You're up to date ({current}).")
        print(f"[app] {msg}", flush=True)
        if self.tray is not None:
            try:
                self.tray.icon.notify(msg, "EmoDict")
            except Exception:  # noqa: BLE001 - notifications can be disabled
                pass

    def _quiet_update_check(self) -> None:
        from .update_check import check_for_update

        avail, latest, current = check_for_update()
        if avail and self.tray is not None:
            try:
                self.tray.icon.notify(
                    f"EmoDict {latest} is available (you have {current}). "
                    f"Click 'Check for updates' in the tray menu.", "EmoDict")
            except Exception:  # noqa: BLE001
                pass

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
        from .overlay import RecordingOverlay
        from .tray import Tray

        self.overlay = RecordingOverlay(self.root)

        self.tray = Tray(on_settings=self.open_settings,
                         on_toggle_pause=self.toggle_pause,
                         on_update=self.check_update_notify,
                         on_dashboard=self.open_dashboard,
                         on_quit=lambda: self.root.after(0, self.root.quit))
        self.tray.start()
        self._bind_hotkey()
        threading.Thread(target=self._quiet_update_check, daemon=True).start()
        from .mainwindow import MainWindow

        self.mainwin = MainWindow(self.root, self)
        self.mainwin.show()
        if self.cfg.onboarding_pending:
            from .welcome import WelcomeCard

            self.welcome = WelcomeCard(self.root, on_finish=self._onboarding_done)
            self.welcome.show()
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
        if self.recorder is not None:
            if self.recorder.recording:
                self.recorder.stop()
            self.recorder.close()
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=10)
        if self.tray is not None:
            self.tray.stop()
        self._overlay_hide()
        print("[app] stopped clean; no injection can happen after this point.")


def main() -> int:
    from . import settings_store

    use_gui_wizard = getattr(sys, "frozen", False) or sys.stdin is None

    if settings_store.settings_exist():
        cfg = settings_store.load_settings()
    else:
        print("[app] no settings found, starting first-run setup\n", flush=True)
        if use_gui_wizard:  # packaged build: console input() would EOF-crash
            from .wizard_gui import run_wizard_gui

            cfg = run_wizard_gui(auto_yes="--yes" in sys.argv)
        else:
            from .wizard import run_wizard

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
