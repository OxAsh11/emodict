"""Mic capture: 16kHz mono float32, held in RAM only, nothing written to disk."""
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


class Recorder:
    def __init__(self, samplerate: int = SAMPLE_RATE, device: int = -1):
        self.samplerate = samplerate
        self.device = None if device is None or device < 0 else device
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self.recording = False

    def start(self) -> None:
        if self.recording:
            return
        self._frames = []

        def callback(indata, frames, time_info, status):
            self._frames.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self.samplerate, channels=1, dtype="float32",
            callback=callback, device=self.device,
        )
        self._stream.start()
        self.recording = True

    def stop(self) -> np.ndarray:
        """Stop and return the captured audio as a flat float32 array."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.recording = False
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._frames).flatten()


def load_audio_file(path: str) -> np.ndarray:
    """Read any audio file and return 16kHz mono float32 for Whisper."""
    import soundfile as sf
    import soxr

    data, sr = sf.read(path, dtype="float32", always_2d=True)
    data = data.mean(axis=1)  # mono mixdown
    if sr != SAMPLE_RATE:
        data = soxr.resample(data, sr, SAMPLE_RATE)
    return data.astype(np.float32)
