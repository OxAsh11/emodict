"""Hardware probe + model recommendation. Used by the first-run wizard."""
import ctypes
import os
import subprocess
from typing import Optional


def _ram_gb() -> float:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    return stat.ullTotalPhys / (1024**3)


def _gpu_info() -> Optional[dict]:
    """nvidia-smi if present; None if no NVIDIA GPU or tool missing."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        name, vram = out.stdout.strip().split(",", 1)
        return {"name": name.strip(), "vram_mb": int(float(vram.strip().split()[0]))}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def _cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001
        return False


def probe() -> dict:
    gpu = _gpu_info() if _cuda_available() else None
    return {
        "cuda": gpu is not None,
        "gpu": gpu,
        "cpu_cores": os.cpu_count() or 2,
        "ram_gb": round(_ram_gb(), 1),
    }


def recommend_model(hw: dict) -> tuple[str, str]:
    """Returns (model_size, human reason). Budget: RTX 3050 6GB was verified
    with base int8_float16; large-v3-turbo needs ~3GB VRAM."""
    if hw["cuda"] and hw["gpu"] and hw["gpu"]["vram_mb"] >= 4500:
        name = hw["gpu"]["name"].removeprefix("NVIDIA ").strip()
        return "large-v3-turbo", (
            f"{name} with {hw['gpu']['vram_mb']}MB VRAM "
            "can run large-v3-turbo on GPU (fastest, most accurate)")
    if hw["cuda"]:
        return "small", (
            f"NVIDIA {hw['gpu']['name']} detected but VRAM is tight; "
            "small on GPU is the safe default")
    if hw["cpu_cores"] >= 8 and hw["ram_gb"] >= 8:
        return "small", (
            f"No usable GPU; {hw['cpu_cores']} CPU cores / {hw['ram_gb']}GB RAM "
            "run small faster than real-time on CPU")
    return "base", (
        f"Modest hardware ({hw['cpu_cores']} cores / {hw['ram_gb']}GB RAM); "
        "base on CPU keeps dictation snappy")


if __name__ == "__main__":
    import json

    hw = probe()
    print(json.dumps(hw, indent=2))
    model, reason = recommend_model(hw)
    print(f"recommended: {model}\nreason: {reason}")
