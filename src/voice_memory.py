"""Voice memory: rolling per-class score baselines for THIS user's voice.

Every take's emotion scores update running statistics (Welford) per class.
After ~10 takes the profile knows what is NORMAL for this voice; a take is
emotionally elevated when its score is a statistical outlier for the user
(z >= 4), independent of absolute values. Cold start falls back to the fixed
thresholds in calibration.json.

Stored at %APPDATA%/EmoDict/voice_memory.json. Local only.
"""
import json
import math
import os
from pathlib import Path

Z_TRIGGER = 4.0        # personal-outlier threshold
WARMUP = 8             # takes needed per class before z-scores are trusted
ABS_FLOOR = 0.02       # z alone can't fire on microscopic absolute scores
MIN_STD = 1e-4


def memory_path() -> Path:
    base = os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "EmoDict" / "voice_memory.json"


class VoiceMemory:
    def __init__(self):
        self.n = 0                 # takes seen
        self.stats: dict[str, dict] = {}   # class -> {n, mean, m2}

    # ---- persistence -----------------------------------------------------
    def load(self) -> "VoiceMemory":
        try:
            data = json.loads(memory_path().read_text(encoding="utf-8"))
            self.n = int(data.get("n", 0))
            self.stats = data.get("stats", {})
        except (OSError, json.JSONDecodeError):
            pass
        return self

    def save(self) -> None:
        p = memory_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"n": self.n, "stats": self.stats}, indent=2),
                     encoding="utf-8")

    # ---- Welford update ----------------------------------------------------
    def update(self, scores: dict[str, float]) -> None:
        self.n += 1
        for label, score in scores.items():
            s = self.stats.setdefault(label, {"n": 0, "mean": 0.0, "m2": 0.0})
            s["n"] += 1
            delta = score - s["mean"]
            s["mean"] += delta / s["n"]
            s["m2"] += delta * (score - s["mean"])
        self.save()

    # ---- queries ---------------------------------------------------------------
    def count(self, label: str) -> int:
        return self.stats.get(label, {}).get("n", 0)

    def mean(self, label: str) -> float:
        return self.stats.get(label, {}).get("mean", 0.0)

    def std(self, label: str) -> float:
        s = self.stats.get(label)
        if not s or s["n"] < 2:
            return MIN_STD
        return max(math.sqrt(s["m2"] / (s["n"] - 1)), MIN_STD)

    def zscore(self, label: str, score: float) -> float:
        return (score - self.mean(label)) / self.std(label)

    def is_elevated(self, label: str, score: float) -> bool:
        """Personal-outlier rule: warm per-class history + big z + real signal."""
        return (self.count(label) >= WARMUP
                and score >= ABS_FLOOR
                and self.zscore(label, score) >= Z_TRIGGER)

    def summary(self) -> str:
        parts = [f"n={self.n}"]
        for label in sorted(self.stats, key=lambda l: -self.count(l))[:4]:
            parts.append(f"{label}: {self.mean(label):.4f}+/-{self.std(label):.4f}"
                         f" (n={self.count(label)})")
        return "  ".join(parts)
