"""Per-user tone calibration.

emotion2vec's default decision rule (argmax, tag above 0.6) is calibrated on
acted/theatrical speech. Real users at a desk score far lower on their
genuine emotions while their calm baseline is near zero - the separation is
large but the absolute numbers are small. Calibration stores a personal
threshold per emotion class, measured from the user's own labeled clips.

Evidence from the founder's voice (2026-11-22, iic/emotion2vec_plus_base):
  calm takes (6 samples): angry 0.0001 - 0.0078
  frustrated take (16.5s): angry 0.1232   -> 17x separation
Chosen threshold 0.04: ~5x above his calm max, ~3x below his real signal.
"""
import json
import os
from pathlib import Path

DEFAULT_CLASS_THRESHOLD = 0.60  # uncalibrated classes stay strict


def calibration_path() -> Path:
    base = os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "EmoDict" / "calibration.json"


def load_thresholds() -> dict:
    p = calibration_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return dict(data.get("thresholds", {}))
    except (json.JSONDecodeError, OSError):
        return {}


def save_calibration(thresholds: dict, samples: dict | None = None) -> Path:
    p = calibration_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(
        {"version": 1, "thresholds": thresholds, "samples": samples or {}},
        indent=2), encoding="utf-8")
    return p
