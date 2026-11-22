"""Enroll the voice lock from captured takes (EMO_KEEP_AUDIO debug captures).
Usage: .venv/Scripts/python.exe tools/enroll_voice.py [more.wav ...]
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os  # noqa: E402

from src.recorder import load_audio_file  # noqa: E402
from src.voice_lock import VoiceLock  # noqa: E402


def main() -> int:
    d = Path(os.environ["LOCALAPPDATA"]) / "EmoDict" / "debug"
    clips = []
    wavs = sorted(d.glob("*.wav")) if d.exists() else []
    for extra in sys.argv[1:]:
        wavs.append(Path(extra))
    for w in wavs:
        try:
            a = load_audio_file(str(w))
            if len(a) > 16000:  # >= 1s
                clips.append(a)
        except Exception as e:  # noqa: BLE001
            print(f"skip {w.name}: {e}")
    print(f"{len(clips)} clips of your voice ({len(wavs)} files found)")
    if len(clips) < 2:
        print("need at least 2 clips over 1s; dictate a few takes with "
              "EMO_KEEP_AUDIO=1 first")
        return 1
    vl = VoiceLock()
    ok = vl.enroll(clips)
    if ok:
        # self-check: similarity against one of the enrollment clips
        print("self-similarity (should be high, >0.7):",
              f"{vl.similarity(clips[-1]):.3f}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
