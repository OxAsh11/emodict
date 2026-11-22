"""Post-processing: filler stripping, sentence case, custom dictionary, tone tags."""
import json
import re
from pathlib import Path
from typing import Optional

from .config import Config
from .emotion import EmotionSpan
from .transcriber import Segment

_FILLER_RE = re.compile(r"\b(um+|uh+|erm+|hmm+|mhm)\b[,.]?\s*", re.IGNORECASE)


class Cleaner:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.dictionary: dict[str, str] = {}
        p = Path(cfg.dictionary_path)
        if p.exists():
            try:
                self.dictionary = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                print(f"[cleanup] dictionary load failed: {e}")

    # ---- rules -----------------------------------------------------------
    def strip_fillers(self, text: str) -> str:
        return _FILLER_RE.sub(" ", text)

    def apply_dictionary(self, text: str) -> str:
        for wrong, right in self.dictionary.items():
            # word boundaries: "flyt base" must not match inside "flyt based"
            pattern = r"\b" + re.escape(wrong) + r"\b"
            text = re.sub(pattern, lambda _m, r=right: r, text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def sentence_case(text: str) -> str:
        out = list(text)
        capitalize_next = True
        for i, ch in enumerate(out):
            if capitalize_next and ch.isalpha():
                out[i] = ch.upper()
                capitalize_next = False
            elif ch in ".!?":
                capitalize_next = True
        return "".join(out).strip()

    def clean_text(self, text: str) -> str:
        if self.cfg.strip_fillers:
            text = self.strip_fillers(text)
        text = self.apply_dictionary(text)
        text = re.sub(r"\s+", " ", text).strip()
        return self.sentence_case(text)

    # ---- assembly --------------------------------------------------------
    def format_output(self, segments: list[Segment],
                      emotions: Optional[list[EmotionSpan]] = None) -> str:
        parts: list[str] = []
        last_tag = ""
        for seg in segments:
            text = self.clean_text(seg["text"])
            if not text:
                continue
            tag = self._tag_for(seg, emotions)
            if tag == last_tag and tag:
                tag = ""  # whole-take spans: tag once at the front, not per line
            last_tag = tag if tag else last_tag
            parts.append(f"{tag} {text}".strip())
        return " ".join(parts)

    def _tag_for(self, seg: Segment, emotions: Optional[list[EmotionSpan]]) -> str:
        if not emotions or not getattr(self.cfg, "show_tone_tags", True):
            return ""
        # decision authority lives in the calibrated analyzer (emotion.py);
        # any span that reaches here already crossed its personal threshold
        best: Optional[EmotionSpan] = None
        for e in emotions:
            overlap = min(seg["end"], e["end"]) - max(seg["start"], e["start"])
            if overlap > 0 and (best is None or e["score"] > best["score"]):
                best = e
        if best:
            return f"[tone: {best['label']}, {best['score']:.2f}]"
        return ""
