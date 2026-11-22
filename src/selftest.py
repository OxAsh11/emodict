"""Self-test for packaged builds: full offline pipeline on the bundled test wav.
No hotkey, no mic, no injection. Exit 0 = pass.

    EmoDict.exe --selftest
    EMO_SELFTEST_MODEL=base EmoDict.exe --selftest      (force a model)
"""
import os
import sys
import time
from pathlib import Path

from .config import PROJECT_ROOT


def _wav_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
    p = base / "tools" / "test_input.wav"
    return p if p.exists() else PROJECT_ROOT / "tools" / "test_input.wav"


def run_selftest() -> int:
    from . import settings_store
    from .cleanup import Cleaner
    from .config import Config
    from .emotion import EmotionAnalyzer
    from .recorder import load_audio_file
    from .transcriber import Transcriber

    cfg = settings_store.load_settings() if settings_store.settings_exist() else Config()
    override = os.environ.get("EMO_SELFTEST_MODEL")
    if override:
        cfg.model_size = override

    print(f"[selftest] frozen={bool(getattr(sys, 'frozen', False))} "
          f"model={cfg.model_size}")
    wav = _wav_path()
    print(f"[selftest] wav: {wav}")
    audio = load_audio_file(str(wav))
    print(f"[selftest] audio: {len(audio)/16000:.1f}s @16kHz")

    t0 = time.perf_counter()
    stt = Transcriber(cfg.model_size, cfg.device, cfg.compute_type, cfg.language)
    print(f"[selftest] model loaded in {time.perf_counter()-t0:.1f}s "
          f"(device={stt.device}, compute={stt.compute_type})")

    t0 = time.perf_counter()
    segments = stt.transcribe(audio)
    output = Cleaner(cfg).format_output(segments, None)
    print(f"[selftest] transcribed in {time.perf_counter()-t0:.2f}s")
    print(f"[selftest] output: {output}")

    ok = "dictation" in output.lower() and "pipeline" in output.lower()
    print(f"[selftest] STT {'PASS' if ok else 'FAIL'}")

    # Emotion fork: run when funasr is importable (bundled builds and venv)
    emo_ok = None
    try:
        import funasr  # noqa: F401

        have_funasr = True
    except ImportError:
        have_funasr = False
    if have_funasr:
        t0 = time.perf_counter()
        analyzer = EmotionAnalyzer(cfg.emotion_model, enabled=True)
        if analyzer.enabled:
            spans = analyzer.analyze(audio, 16000, segments)
            dt = time.perf_counter() - t0
            labels = {s["label"] for s in spans}
            print(f"[selftest] emotion: {len(spans)} spans in {dt:.1f}s, "
                  f"labels={sorted(labels)}")
            emo_ok = len(spans) > 0
        else:
            print("[selftest] emotion: model failed to load")
            emo_ok = False
    else:
        print("[selftest] emotion: funasr not importable, skipped")

    print(f"[selftest] emotion {'PASS' if emo_ok else 'FAIL' if emo_ok is not None else 'SKIPPED'}")

    # Windowed exes swallow stdout: also write results to a marker file the
    # build chain can read (exit code alone once hid a broken emotion build).
    try:
        from pathlib import Path

        marker = (Path(__import__("os").environ["LOCALAPPDATA"])
                  / "EmoDict" / "logs" / "selftest.txt")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"STT {'PASS' if ok else 'FAIL'}\n"
                          f"emotion {'PASS' if emo_ok else 'FAIL' if emo_ok is not None else 'SKIPPED'}\n")
    except Exception:  # noqa: BLE001
        pass
    return 0 if (ok and emo_ok is not False) else 1
