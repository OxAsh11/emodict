"""Mic capture: 16kHz mono float32, RAM only.

Design (v2, fixes the 'cutting my words' bug): the InputStream is opened ONCE
at app start and kept open. Per-take stream open costs 100-300ms on Windows
and audio spoken during it is lost forever; an always-open stream plus a
pre-roll ring buffer means nothing at the start of a take is dropped, and a
tail drain on stop() catches trailing words still inside PortAudio's buffers.
"""
import time
from collections import deque

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


class Recorder:
    def __init__(self, samplerate: int = SAMPLE_RATE, device: int = -1,
                 preroll_s: float = 0.30, tail_s: float = 0.20):
        self.samplerate = samplerate
        self.device = None if device is None or device < 0 else device
        self.preroll_s = preroll_s
        self.tail_s = tail_s

        self._ring: deque[np.ndarray] = deque()
        self._ring_seconds = 0.0
        self._frames: list[np.ndarray] = []
        self._collecting = False
        self.recording = False
        self._stream: sd.InputStream | None = None

        self._stream = sd.InputStream(
            samplerate=samplerate, channels=1, dtype="float32",
            callback=self._callback, device=self.device,
        )
        self._stream.start()

    # called by PortAudio on its own thread
    def _callback(self, indata, frames, time_info, status):
        frame = indata.copy()
        # maintain the pre-roll ring (audio just before the key press)
        self._ring.append(frame)
        self._ring_seconds += frames / self.samplerate
        while self._ring_seconds > self.preroll_s and len(self._ring) > 1:
            dropped = self._ring.popleft()
            self._ring_seconds -= dropped.shape[0] / self.samplerate
        if self._collecting:
            self._frames.append(frame)

    def start(self) -> None:
        if self._collecting:
            return
        self._frames = list(self._ring)  # include the pre-roll
        self._collecting = True
        self.recording = True

    def stop(self) -> np.ndarray:
        """Stop collecting, drain the tail, return the take."""
        if not self._collecting:
            return np.zeros(0, dtype=np.float32)
        self._collecting = False
        self.recording = False
        time.sleep(self.tail_s)  # let buffered trailing audio arrive
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._frames).flatten()

    def close(self) -> None:
        """Shut the stream down (app quit or device change)."""
        self._collecting = False
        self.recording = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None


def load_audio_file(path: str) -> np.ndarray:
    """Read any audio file and return 16kHz mono float32 for Whisper."""
    import soundfile as sf
    import soxr

    data, sr = sf.read(path, dtype="float32", always_2d=True)
    data = data.mean(axis=1)  # mono mixdown
    if sr != SAMPLE_RATE:
        data = soxr.resample(data, sr, SAMPLE_RATE)
    return data.astype(np.float32)
