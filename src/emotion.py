"""Emotion branch: emotion2vec fork, aligned to Whisper timestamps.

Decision rule: a non-neutral class is tagged when its score crosses the
USER's calibrated threshold for that class (calibration.json, measured from
their own clips); uncalibrated classes fall back to a strict 0.60. See
src/calibration.py for why argmax+0.6 fails real desk-voice frustration.
"""
import os
from typing import Optional, TypedDict

from .calibration import DEFAULT_CLASS_THRESHOLD, load_thresholds
from .transcriber import Segment
from .voice_memory import VoiceMemory

_NEVER_TAG = ("other", "<unk>")   # neutral IS taggable now: calm is information


class EmotionSpan(TypedDict):
    start: float
    end: float
    label: str      # e.g. frustrated / happy / neutral / sad / angry
    score: float    # confidence 0..1


class EmotionAnalyzer:
    def __init__(self, model_id: str = "iic/emotion2vec_plus_base", enabled: bool = False):
        self.model = None
        self.enabled = enabled
        self.thresholds: dict = load_thresholds()
        self.memory = VoiceMemory().load()
        if enabled:
            try:
                from funasr import AutoModel

                # Frozen apps fail hub-id resolution sometimes (registry then
                # rejects the raw id): pass the LOCAL snapshot path when it
                # exists; AutoModel reads config.yaml there -> "Emotion2vec",
                # which is always registered. Falls back to the id (venv dev).
                from pathlib import Path

                snap = (Path.home() / ".cache" / "modelscope" / "models"
                        / "iic--emotion2vec_plus_base" / "snapshots" / "master")
                model_arg = str(snap) if snap.exists() else model_id

                # disable_update: funasr phones home to check its own version
                # on every init; costs seconds and we never care
                self.model = AutoModel(model=model_arg, disable_update=True)
            except Exception as e:  # noqa: BLE001 - degrade, never block dictation
                print(f"[emotion] disabled ({e.__class__.__name__}: {e})")
                self.enabled = False

    def analyze(self, audio, sample_rate: int = 16000,
                segments: Optional[list[Segment]] = None) -> list[EmotionSpan]:
        """Run per-segment. Until the model is installed, returns []."""
        if not self.enabled or self.model is None or audio is None or len(audio) == 0:
            return []
        spans: list[EmotionSpan] = []
        chunk_list = segments or [{"start": 0.0, "end": len(audio) / sample_rate, "text": ""}]
        for seg in chunk_list:
            i0 = int(seg["start"] * sample_rate)
            i1 = min(int(seg["end"] * sample_rate), len(audio))
            if i1 - i0 < sample_rate // 2:  # <0.5s, too short to judge
                continue
            try:
                # ndarray in (NOT a list); labels come bilingual 'zh/en'
                res = self.model.generate(
                    audio[i0:i1], granularity="utterance", extract_embedding=False)
                r = res[0] if res else {}
                labels = [str(l).split("/")[-1] for l in r.get("labels", [])]
                scores = [float(s) for s in r.get("scores", [])]
                if labels and scores:
                    pick = self._decide(labels, scores)
                    if pick is not None:
                        label, score = pick
                        spans.append({"start": seg["start"], "end": seg["end"],
                                      "label": label, "score": score})
            except Exception as e:  # noqa: BLE001
                print(f"[emotion] segment failed: {e}")
        return spans

    def _decide(self, labels: list[str], scores: list[float]):
        """Every take gets a tag (calm is information too - the receiving AI
        must never wonder whether tone was measured). WHICH tag:
        a non-neutral class that crossed its personal threshold OR is a
        statistical outlier for this voice (memory z-score); otherwise the
        dominant class, usually neutral."""
        pairs = dict(zip(labels, scores))
        self.memory.update(pairs)
        best = None
        for label, score in pairs.items():
            if label in _NEVER_TAG:
                continue
            if ((score >= self.thresholds.get(label, DEFAULT_CLASS_THRESHOLD)
                 or self.memory.is_elevated(label, score))
                    and (best is None or score > best[1])):
                best = (label, score)
        if best is None:
            best = max(pairs.items(), key=lambda kv: kv[1])
        return best
