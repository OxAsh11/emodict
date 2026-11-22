"""Voice lock: transcribe ONLY the enrolled user's voice.

A speaker d-vector (SpeechBrain ECAPA-TDNN) is enrolled from the user's own
captured takes. Every Whisper segment is then verified against the profile;
other speakers (TV, radio, people nearby) are dropped before cleanup, tone
scoring and paste. Profile: %APPDATA%/EmoDict/voice_profile.npy
"""
import os
from pathlib import Path

import numpy as np

SIM_THRESHOLD = 0.50   # cosine similarity to count as "me". Measured on the
                       # founder: his mixed-quality segments >= 0.66, TV voice
                       # <= 0.08 - 0.50 splits the gap with margin both ways


def profile_path() -> Path:
    base = os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "EmoDict" / "voice_profile.npy"


class VoiceLock:
    def __init__(self):
        self.model = None
        self.profile: np.ndarray | None = None
        p = profile_path()
        if p.exists():
            try:
                self.profile = np.load(p)
            except Exception:  # noqa: BLE001
                self.profile = None

    @property
    def armed(self) -> bool:
        return self.profile is not None

    def _ensure_model(self) -> bool:
        if self.model is None:
            try:
                from speechbrain.inference.speaker import EncoderClassifier

                self.model = EncoderClassifier.from_hparams(
                    source="speechbrain/spkrec-ecapa-voxceleb",
                    savedir=str(Path(os.getenv("LOCALAPPDATA", "."))
                                / "EmoDict" / "models" / "ecapa"),
                    run_opts={"device": "cpu"})
            except Exception as e:  # noqa: BLE001
                print(f"[voice-lock] embedder unavailable: {e}", flush=True)
                return False
        return True

    # ---- enrollment -------------------------------------------------------
    def enroll(self, wavs: list, sr: int = 16000) -> bool:
        """Average d-vector over clips of the user's voice."""
        if not wavs or not self._ensure_model():
            return False
        import torch

        with torch.no_grad():
            vecs = []
            for a in wavs:
                t = torch.from_numpy(np.asarray(a, dtype="float32"))
                if t.dim() == 1:
                    t = t.unsqueeze(0)
                if abs(len(t[0]) - sr) < sr // 10:  # <1.1s clips are weak
                    continue
                emb = self.model.encode_batch(t).squeeze().numpy()
                vecs.append(emb / np.linalg.norm(emb))
        if not vecs:
            return False
        prof = np.mean(vecs, axis=0)
        self.profile = prof / np.linalg.norm(prof)
        profile_path().parent.mkdir(parents=True, exist_ok=True)
        np.save(profile_path(), self.profile.astype("float32"))
        print(f"[voice-lock] enrolled from {len(vecs)} clips", flush=True)
        return True

    # ---- verification ---------------------------------------------------------
    def is_me(self, audio, sr: int = 16000) -> bool:
        if not self.armed or len(audio) < sr // 2:
            return True  # no profile / too short to judge: don't block text
        if not self._ensure_model():
            return True  # embedder down: fail open (text > silence)
        import torch

        with torch.no_grad():
            t = torch.from_numpy(np.asarray(audio, dtype="float32")).unsqueeze(0)
            emb = self.model.encode_batch(t).squeeze().numpy()
            emb = emb / np.linalg.norm(emb)
        sim = float(np.dot(emb, self.profile))
        return sim >= SIM_THRESHOLD

    def similarity(self, audio, sr: int = 16000) -> float:
        """For diagnostics/calibration."""
        if not self.armed or not self._ensure_model() or len(audio) < sr // 2:
            return -1.0
        import torch

        with torch.no_grad():
            t = torch.from_numpy(np.asarray(audio, dtype="float32")).unsqueeze(0)
            emb = self.model.encode_batch(t).squeeze().numpy()
            emb = emb / np.linalg.norm(emb)
        return float(np.dot(emb, self.profile))
