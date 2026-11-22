"""Dump emotion2vec's FULL score vector for captured takes, so calibration
decisions are made on evidence, not vibes.

    .venv/Scripts/python.exe tools/analyze_tone.py "%LOCALAPPDATA%/EmoDict/debug"
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from funasr import AutoModel  # noqa: E402

LABELS = None


def analyze(model, wav: Path) -> None:
    import numpy as np
    import soundfile as sf

    audio, sr = sf.read(str(wav), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    res = model.generate(audio, granularity="utterance", extract_embedding=False)
    r = res[0]
    pairs = sorted(zip([str(x).split("/")[-1] for x in r["labels"]],
                       [float(s) for s in r["scores"]]), key=lambda x: -x[1])
    dur = len(audio) / sr
    print(f"\n{wav.name}  ({dur:.1f}s)")
    for label, score in pairs:
        bar = "#" * int(score * 50)
        print(f"  {label:12s} {score:.4f} {bar}")


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    wavs = sorted(target.glob("*.wav")) if target.is_dir() else [target]
    if not wavs:
        print(f"no wavs in {target}")
        return 1
    print("loading emotion2vec...")
    model = AutoModel(model="iic/emotion2vec_plus_base", disable_update=True)
    for w in wavs:
        try:
            analyze(model, w)
        except Exception as e:  # noqa: BLE001
            print(f"{w.name}: FAILED {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
