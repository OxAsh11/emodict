"""Offline end-to-end test: wav file -> transcribe -> cleanup -> printed output.
No hotkey, no injection. Verifies the pipeline on real audio, safely.

    .venv/Scripts/python.exe -m src.test_offline --wav tools/test_input.wav --model base
"""
import argparse
import json
import time

from .cleanup import Cleaner
from .config import Config
from .emotion import EmotionAnalyzer
from .recorder import load_audio_file
from .transcriber import Transcriber


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--model", default=None, help="override config model size")
    ap.add_argument("--device", default=None)
    args = ap.parse_args()

    cfg = Config()
    if args.model:
        cfg.model_size = args.model
    if args.device:
        cfg.device = args.device

    audio = load_audio_file(args.wav)
    print(f"[test] {args.wav}: {len(audio)/16000:.1f}s of 16kHz mono")

    t0 = time.perf_counter()
    stt = Transcriber(cfg.model_size, cfg.device, cfg.compute_type, cfg.language)
    print(f"[test] model loaded in {time.perf_counter()-t0:.1f}s "
          f"(device={stt.device}, compute={stt.compute_type})")

    t0 = time.perf_counter()
    segments = stt.transcribe(audio)
    print(f"[test] transcribed in {time.perf_counter()-t0:.2f}s")

    emotions = EmotionAnalyzer(cfg.emotion_model, enabled=cfg.emotion_enabled).analyze(
        audio, 16000, segments)

    cleaner = Cleaner(cfg)
    final = cleaner.format_output(segments, emotions)

    print("\n--- segments ---")
    for s in segments:
        print(f"  [{s['start']:6.2f} -> {s['end']:6.2f}] {s['text']}")
    if emotions:
        print("--- emotions ---")
        for e in emotions:
            print(f"  [{e['start']:6.2f} -> {e['end']:6.2f}] {e['label']} ({e['score']:.2f})")
    print("\n--- final output ---")
    print(final)
    print("\n--- machine-readable ---")
    print(json.dumps({"segments": segments, "emotions": emotions, "output": final}, indent=2))
    return 0 if final else 1


if __name__ == "__main__":
    raise SystemExit(main())
