"""Whisper branch: faster-whisper wrapper with automatic device selection."""
import os
import site
import sys
from pathlib import Path
from typing import TypedDict


def _register_nvidia_dlls() -> None:
    """Make CUDA DLLs findable. Two layouts:
    - venv: nvidia-* pip packages under site-packages/nvidia/*/bin
    - frozen (PyInstaller): collected next to the app in nvidia/<pkg>/
    ctranslate2 loads cublas/cudnn by name via legacy search, so both
    os.add_dll_directory AND PATH must cover these dirs."""
    dirs = []
    bases = []
    if not getattr(sys, "frozen", False):
        bases.extend(site.getsitepackages())
    else:
        bases.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)))
        bases.append(Path(sys.executable).parent)
    for base in bases:
        for sub in ("cublas/bin", "cudnn/bin", "cuda_nvrtc/bin", "cufft/bin",
                    "nvidia/cublas/bin", "nvidia/cudnn/bin", "nvidia/cuda_nvrtc/bin",
                    "nvidia/cublas", "nvidia/cudnn", "nvidia/cuda_nvrtc"):
            d = Path(base) / sub.replace("/", os.sep)
            if d.is_dir():
                dirs.append(d)
    for d in dirs:
        os.add_dll_directory(d)
    if dirs:
        os.environ["PATH"] = os.pathsep.join(str(d) for d in dirs) + os.pathsep + os.environ.get("PATH", "")


_register_nvidia_dlls()


class Segment(TypedDict):
    start: float
    end: float
    text: str


def _cuda_available() -> bool:
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() <= 0:
            return False
    except Exception:
        return False
    # A driver is not enough: ctranslate2 loads cublas lazily at the first
    # encode, far past any init-time fallback. Prove the runtime resolves
    # BEFORE cuda is chosen (CPU-only builds fail here -> cpu int8).
    import ctypes

    try:
        ctypes.CDLL("cublas64_12.dll")
        return True
    except OSError:
        return False


class Transcriber:
    def __init__(self, model_size: str = "small", device: str = "auto",
                 compute_type: str = "auto", language: str = "en",
                 beam_size: int = 1):
        from faster_whisper import WhisperModel

        self.beam_size = beam_size

        if device == "auto":
            device = "cuda" if _cuda_available() else "cpu"
        if compute_type == "auto":
            compute_type = "int8_float16" if device == "cuda" else "int8"
        try:
            self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        except Exception as e:  # noqa: BLE001 - broken/missing CUDA runtime -> CPU
            if device == "cuda":
                print(f"[stt] CUDA load failed ({e}); falling back to CPU int8")
                device, compute_type = "cpu", "int8"
                self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
            else:
                raise
        self.device = device
        self.compute_type = compute_type
        self.language = language

    def transcribe(self, audio) -> list[Segment]:
        """audio: float32 numpy array at 16kHz. Returns timestamped segments."""
        segments_iter, info = self.model.transcribe(
            audio,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=True,
            word_timestamps=False,
        )
        return [
            {"start": s.start, "end": s.end, "text": s.text.strip()}
            for s in segments_iter
            if s.text.strip()
        ]
