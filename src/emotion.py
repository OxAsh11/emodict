"""Emotion branch (Weekend 4). Interface ships today so the pipeline is wired.

Install when ready:
    uv pip install -p .venv torch --index-url https://download.pytorch.org/whl/cpu
    uv pip install -p .venv funasr
Model: iic/emotion2vec_plus_base (downloads from ModelScope on first run).
"""
from typing import Optional, TypedDict

from .transcriber import Segment


class EmotionSpan(TypedDict):
    start: float
    end: float
    label: str      # e.g. frustrated / happy / neutral / sad / angry
    score: float    # confidence 0..1


class EmotionAnalyzer:
    def __init__(self, model_id: str = "iic/emotion2vec_plus_base", enabled: bool = False):
        self.model = None
        self.enabled = enabled
        if enabled:
            try:
                from funasr import AutoModel

                # disable_update: funasr phones home to check its own version
                # on every init; costs seconds and we never care
                self.model = AutoModel(model=model_id, disable_update=True)
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
                    best = max(zip(labels, scores), key=lambda x: x[1])
                    if best[0] not in ("<unk>",):
                        spans.append({"start": seg["start"], "end": seg["end"],
                                      "label": best[0], "score": best[1]})
            except Exception as e:  # noqa: BLE001
                print(f"[emotion] segment failed: {e}")
        return spans
