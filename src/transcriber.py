"""Whisper branch: faster-whisper wrapper with automatic device selection."""
import os
import site
from typing import TypedDict


def _register_nvidia_dlls() -> None:
    """Windows: the nvidia-* pip packages ship CUDA DLLs in
    site-packages/nvidia/*/bin, which is NOT on the DLL search path.
    ctranslate2 loads cublas/cudnn by name via legacy search, so both
    os.add_dll_directory AND PATH must cover these dirs."""
    dirs = []
    for sp in site.getsitepackages():
        for sub in ("cublas/bin", "cudnn/bin", "cuda_nvrtc/bin", "cufft/bin"):
            d = os.path.join(sp, "nvidia", sub.replace("/", os.sep))
            if os.path.isdir(d):
                dirs.append(d)
    for d in dirs:
        os.add_dll_directory(d)
    if dirs:
        os.environ["PATH"] = os.pathsep.join(dirs) + os.pathsep + os.environ.get("PATH", "")


_register_nvidia_dlls()


class Segment(TypedDict):
    start: float
    end: float
    text: str


def _cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


class Transcriber:
    def __init__(self, model_size: str = "small", device: str = "auto",
                 compute_type: str = "auto", language: str = "en"):
        from faster_whisper import WhisperModel

        if device == "auto":
            device = "cuda" if _cuda_available() else "cpu"
        if compute_type == "auto":
            compute_type = "int8_float16" if device == "cuda" else "int8"
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio) -> list[Segment]:
        """audio: float32 numpy array at 16kHz. Returns timestamped segments."""
        segments_iter, info = self.model.transcribe(
            audio,
            language=self.language,
            beam_size=5,
            vad_filter=True,
            word_timestamps=False,
        )
        return [
            {"start": s.start, "end": s.end, "text": s.text.strip()}
            for s in segments_iter
            if s.text.strip()
        ]
