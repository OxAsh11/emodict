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
        self._streamer = None        # live StreamingTranscriber while recording

        print("[app] loading model...", flush=True)
        try:
            self.stt = Transcriber(cfg.model_size, cfg.device, cfg.compute_type,
                                   cfg.language, cfg.beam_size)
        except Exception as e:  # noqa: BLE001 - a broken model cache must
            # degrade, never kill the app
            print(f"[app] model {cfg.model_size} FAILED to load ({e}); "
                  f"falling back", flush=True)
            for fallback in ("base", "tiny"):
                try:
                    self.stt = Transcriber(fallback, "cpu", "int8",
                                           cfg.language, cfg.beam_size)
                    print(f"[app] running on fallback model '{fallback}'", flush=True)
                    break
                except Exception:  # noqa: BLE001
                    continue
            else:
                raise
        print(f"[app] STT ready: model={cfg.model_size} device={self.stt.device} "
              f"compute={self.stt.compute_type}", flush=True)
        self.emotion = EmotionAnalyzer(cfg.emotion_model, enabled=False)
        if cfg.emotion_enabled:  # big model: load off the startup path
            threading.Thread(target=self._load_emotion, daemon=True).start()
        from .voice_lock import VoiceLock

        self.voice_lock = VoiceLock()  # armed automatically once enrolled
        self.cleaner = Cleaner(cfg)
        try:
            self.recorder = Recorder(device=cfg.mic_device,
                                     on_frame=self._on_frame)  # stream stays open
            print("[app] mic stream open (persistent, pre-roll armed)", flush=True)
        except Exception as e:  # noqa: BLE001 - app starts, hotkey will report
            self.recorder = None
            print(f"[app] MIC OPEN FAILED: {e}", flush=True)

    # ---- streaming hook -----------------------------------------------------
    def _on_frame(self, frame) -> None:
        if self._streamer is not None:
            self._streamer.push(frame)

    def _start_streaming(self) -> None:
        """GPU-only locked-prefix streaming; CPU builds keep end-of-take STT.
        Emotion blocks are scored live too (length-independent latency)."""
        self._streamer = None
        self._emo_worker = None
        self._emo_grouping: list = []
        if not getattr(self.cfg, "streaming_enabled", True):
            return
        if self.stt.device != "cuda":
            return
        try:
            from .streaming import StreamingTranscriber

            if self.emotion.enabled and self.emotion.model is not None:
                from .emo_stream import EmotionStreamWorker

                self._emo_worker = EmotionStreamWorker(
                    self.emotion, self.voice_lock, lambda: self._streamer.snapshot_audio())
                self._emo_worker.start()

            def on_locked(newly):
                # group locked sentences into 6-15s prosodic blocks; submit
                # each completed block for live tone scoring
                for s in newly:
                    g = self._emo_grouping
                    if g and s["end"] - g[0]["start"] > self.GROUP_MAX_S:
                        if self._emo_worker:
                            self._emo_worker.submit(g)
                        self._emo_grouping = [s]
                        continue
                    g.append(s)
                    if s["end"] - g[0]["start"] >= self.GROUP_MIN_S:
                        if self._emo_worker:
                            self._emo_worker.submit(g)
                        self._emo_grouping = []

            self._streamer = StreamingTranscriber(self.stt, on_locked=on_locked)
            self._streamer.start()
            print("[app] streaming STT active (locked-prefix, live tone blocks)",
                  flush=True)
        except Exception as e:  # noqa: BLE001 - streaming is an optimization
            self._streamer = None
            self._emo_worker = None
            print(f"[app] streaming unavailable: {e}", flush=True)

    def _collect_streaming(self):
        st = self._streamer
        self._streamer = None
        ew = self._emo_worker
        self._emo_worker = None
        if st is None:
            return None, None
        try:
            segs = st.stop()
            live_spans = ew.stop(timeout=15) if ew is not None else None
            print(f"[app] streaming: {st.stats}"
                  + (f" | live tone blocks: {len(live_spans)}"
                     if live_spans is not None else ""), flush=True)
            return (segs if segs else None), live_spans
        except Exception as e:  # noqa: BLE001
            print(f"[app] streaming stop failed: {e}", flush=True)
            return None, None

    # ---- pipeline --------------------------------------------------------
    @staticmethod
    def _speech_and_snr(audio, segments, sr: int = 16000):
        """Concatenate only the VAD speech spans, and measure SNR against the
        noise floor in the gaps. Returns (speech_audio, snr_db)."""
        import numpy as np

        mask = np.zeros(len(audio), dtype=bool)
        for s in segments:
            mask[int(s["start"] * sr):int(s["end"] * sr)] = True
        speech = audio[mask]
        if len(speech) < sr // 2:
            return None, -99.0
        speech_rms = float(np.sqrt((speech ** 2).mean()))
        noise = audio[~mask]
        noise_rms = (float(np.sqrt((noise ** 2).mean()))
                     if len(noise) > sr // 4 else 1e-6)
        snr_db = 20.0 * np.log10(speech_rms / (noise_rms + 1e-9))
        return speech, float(snr_db)

    def process(self, audio, pre_segments=None, live_spans=None):
        """pre_segments/live_spans: from the streaming loops (if they ran) -
        blocks scored during recording are reused, so post-stop work shrinks
        to the final tail, independent of take length."""
        import numpy as np

        if audio is None or len(audio) == 0:
            return None, [], []
        has_sound = float(np.abs(audio).max()) > 0.01
        if pre_segments is not None:
            segments = pre_segments
        else:
            segments = self.stt.transcribe(audio) if has_sound else []
        if not segments:
            return None, segments, []

        # voice lock: keep only segments that match the enrolled voice; other
        # speakers (TV, radio, people nearby) never reach text or tone
        if self.voice_lock is not None and self.voice_lock.armed:
            kept = []
            for s in segments:
                i0, i1 = int(s["start"] * 16000), int(s["end"] * 16000)
                if self.voice_lock.is_me(audio[i0:i1]):
                    kept.append(s)
            dropped = len(segments) - len(kept)
            if dropped:
                print(f"[voice-lock] dropped {dropped} segment(s) not matching "
                      f"your voice", flush=True)
            if not kept:
                return None, segments, []
            segments = kept

        emotions: list = []
        speech, snr = self._speech_and_snr(audio, segments)
        if speech is None:
            pass  # sub-half-second speech: nothing to judge
        elif live_spans is not None:
            # streaming: every live block already passed its own windowed
            # SNR gate during recording. The whole-take gate measures TV /
            # dropped-voice regions as "noise" (user's 90s take: 8 good
            # blocks vetoed by a -1.2dB global reading) - trust the blocks.
            emotions = self._merge_live_emotions(audio, segments, live_spans)
        elif snr < self.cfg.tone_min_snr_db:
            print(f"[app] noisy environment (SNR {snr:.1f}dB < "
                  f"{self.cfg.tone_min_snr_db}dB): tone suppressed", flush=True)
        else:
            emotions = self._grouped_emotions(audio, segments)

        text = self.cleaner.format_output(segments, emotions)
        return (text or None), segments, emotions

    GROUP_MIN_S = 6.0   # merge consecutive sentences up to at least this
    GROUP_MAX_S = 15.0  # ...but never score more than this per block

    @staticmethod
    def _groups(segments, min_s: float = 6.0, max_s: float = 15.0) -> list:
        groups, cur = [], []
        for s in segments:
            if cur and s["end"] - cur[0]["start"] > max_s:
                groups.append(cur)
                cur = []
            cur.append(s)
            if s["end"] - cur[0]["start"] >= min_s:
                groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)
        return groups

    def _score_group(self, audio, g) -> dict | None:
        import numpy as np

        mask = np.zeros(len(audio), dtype=bool)
        for s in g:
            mask[int(s["start"] * 16000):int(s["end"] * 16000)] = True
        gaudio = audio[mask]
        if len(gaudio) < 16000 // 2:
            return None
        got = self.emotion.analyze(gaudio, 16000, None)
        if not got:
            return None
        return {"start": g[0]["start"], "end": g[-1]["end"],
                "label": got[0]["label"], "score": got[0]["score"]}

    def _grouped_emotions(self, audio, segments) -> list:
        """Per-block tone (batch path): consecutive segments merged into
        6-15s prosodic blocks, each scored on its own concatenated speech."""
        spans = []
        for g in self._groups(segments, self.GROUP_MIN_S, self.GROUP_MAX_S):
            span = self._score_group(audio, g)
            if span:
                spans.append(span)
        return spans

    def _merge_live_emotions(self, audio, segments, live_spans) -> list:
        """Streaming path: reuse blocks scored DURING recording; score only
        the unscored (final partial) blocks now. This is what makes latency
        independent of take length."""
        spans = []
        for g in self._groups(segments, self.GROUP_MIN_S, self.GROUP_MAX_S):
            match = None
            for sp in live_spans:
                if abs(sp["start"] - g[0]["start"]) < 1.0:
                    match = sp
                    break
            if match is not None:
                spans.append(match)
            else:
                span = self._score_group(audio, g)
                if span:
                    spans.append(span)
        return spans

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
        try:
            self._dispatch_inner()
        finally:
            # every exit path (empty take, failure, quit, success) hides the
            # chip - the stuck-'transcribing' bug was a return that skipped this
            self._overlay_hide()

    def _dispatch_inner(self) -> None:
        audio = self.recorder.stop()
        if audio is not None and len(audio):
            stream_segs, live_spans = self._collect_streaming()
        else:
            stream_segs, live_spans = None, None
        if audio is not None and len(audio) and os.environ.get("EMO_KEEP_AUDIO"):
            self._dump_take(audio)
        if self.shutdown.is_set():  # quit began while recording: drop the take
            return
        t0 = time.perf_counter()
        try:
            text, segments, emotions = self.process(
                audio, pre_segments=stream_segs, live_spans=live_spans)
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
            inject(text, settle_s=self.cfg.paste_settle_s,
                   target_hwnd=getattr(self, "_target_hwnd", 0))
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

    # ---- input state (hold-to-talk + double-tap toggle) ----------------------
    TAP_S = 0.30      # max hold that counts as a tap
    DBL_S = 0.50      # window between taps of a double-tap
    _press_time = 0.0
    _last_tap_end = 0.0
    _toggle_active = False
    _swallow_until = 0.0
    _tap_timer: threading.Timer | None = None

    def on_press(self, event) -> None:
        if self.shutdown.is_set() or self.paused or self._loading_model:
            return
        now = time.perf_counter()
        if self._toggle_active:
            if now >= self._swallow_until:  # this press = STOP
                self._toggle_active = False
                self._spawn_dispatch()
            return  # presses inside the swallow window are the dblclick itself
        if self.recorder is not None and not self.recorder.recording:
            from .injector import get_foreground_hwnd

            self._target_hwnd = get_foreground_hwnd()  # where a long take must land
            self.recorder.start()
            self._start_streaming()
            self._overlay_show("recording")
            print("[app] recording...", flush=True)
        self._cancel_tap_timer()
        self._press_time = now

    def on_release(self, event) -> None:
        if self.shutdown.is_set() or self.recorder is None or not self.recorder.recording:
            return
        if self._toggle_active:
            return  # swallowed release (part of the toggle start or mid-take)
        held = time.perf_counter() - self._press_time
        if held < self.TAP_S:
            # a tap: either the first half of a double-tap, or a stray short
            # press. Keep recording; decide shortly.
            if self._last_tap_end and time.perf_counter() - self._last_tap_end < self.DBL_S:
                self._last_tap_end = 0.0
                self._toggle_active = True  # double-tap: hands-free mode ON
                self._swallow_until = time.perf_counter() + 0.45
                print("[app] toggle mode: recording until next press", flush=True)
            else:
                self._last_tap_end = time.perf_counter()
                self._tap_timer = threading.Timer(self.DBL_S, self._tap_timeout)
                self._tap_timer.daemon = True
                self._tap_timer.start()
        else:
            self._last_tap_end = 0.0
            self._spawn_dispatch()  # classic hold-to-talk

    def _tap_timeout(self) -> None:
        # no second tap came: treat the short press as a (tiny) hold
        self._last_tap_end = 0.0
        if self.recorder is not None and self.recorder.recording:
            self._spawn_dispatch()

    def _cancel_tap_timer(self) -> None:
        if self._tap_timer is not None:
            self._tap_timer.cancel()
            self._tap_timer = None

    def _spawn_dispatch(self) -> None:
        self._cancel_tap_timer()
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
        # suppress=True: while a key is designated as the dictation key, its
        # ORIGINAL OS function (e.g. Win key opening Start) is blocked. The
        # function returns automatically when the key is changed, the app
        # quits, or it is uninstalled (the hook dies with the process).
        keyboard.on_press_key(self.cfg.hold_key, self.on_press, suppress=True)
        keyboard.on_release_key(self.cfg.hold_key, self.on_release, suppress=True)
        self._hotkeys_bound = True
        print(f"[app] holding '{self.cfg.hold_key}' to dictate "
              f"(its normal function is suspended while EmoDict runs). "
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
        self._toggle_active = False
        self._cancel_tap_timer()
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
        self._cancel_tap_timer()
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


def _single_instance() -> bool:
    """Windows named mutex: only one EmoDict may run. Without this, an
    install-while-running or double-launch left TWO instances fighting over
    the hotkey (user hit exactly this)."""
    import ctypes

    ctypes.windll.kernel32.CreateMutexW(None, False, "EmoDict_SingleInstance")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main() -> int:
    if not _single_instance():
        try:
            import tkinter as tk
            from tkinter import messagebox

            r = tk.Tk()
            r.withdraw()
            messagebox.showinfo(
                "EmoDict", "EmoDict is already running - check the tray "
                "(hidden-icons arrow).")
            r.destroy()
        except Exception:  # noqa: BLE001
            pass
        return 0
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
