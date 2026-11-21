"""First-run wizard: probe hardware, pick/download a model, check the mic,
write settings to %APPDATA%. Interactive for the user; --yes --skip-meter
for scripted/agent runs.

    .venv/Scripts/python.exe -m src.wizard            # interactive
    .venv/Scripts/python.exe -m src.wizard --yes --skip-meter
"""
import argparse
import sys
import time

from . import settings_store
from .config import Config
from .hardware import probe, recommend_model


def list_mics() -> list[str]:
    import sounddevice as sd

    mics = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            mics.append(f"[{i}] {d['name']} ({d['default_samplerate']:.0f}Hz)")
    return mics


def mic_level_meter(seconds: float = 3.0) -> None:
    """Three seconds of live input level so the user can confirm their mic."""
    import numpy as np
    import sounddevice as sd

    print("Say something for the next 3 seconds...")
    peak = [0.0]

    def callback(indata, frames, t, status):
        peak[0] = max(peak[0], float(np.abs(indata).max()))

    with sd.InputStream(samplerate=16000, channels=1, callback=callback):
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < seconds:
            time.sleep(0.1)
            bar = "#" * min(int(peak[0] * 80), 40)
            print(f"\r  level: {bar:<40} ", end="", flush=True)
    print()
    if peak[0] < 0.01:
        print("  WARNING: near-zero input. Check the selected mic / Windows privacy settings.")
    else:
        print("  Mic heard you. Good to go.")


def run_wizard(auto_yes: bool = False, skip_meter: bool = False) -> Config:
    print("=" * 60)
    print("EmoDict first-run setup")
    print("=" * 60)

    # 1. hardware probe
    hw = probe()
    gpu_txt = f"{hw['gpu']['name']} ({hw['gpu']['vram_mb']}MB)" if hw["gpu"] else "none detected"
    print(f"\n[1/4] Hardware: GPU={gpu_txt}, CPU cores={hw['cpu_cores']}, RAM={hw['ram_gb']}GB")
    model, reason = recommend_model(hw)
    print(f"      Recommended model: {model}")
    print(f"      Why: {reason}")
    if not auto_yes:
        choice = input(f"      Model to install [Enter = {model}]: ").strip()
        if choice:
            model = choice

    # 2. mic check
    print("\n[2/4] Microphones:")
    try:
        mics = list_mics()
        for m in mics:
            print(f"      {m}")
        if not mics:
            print("      WARNING: no input device found. Check Windows privacy settings.")
    except Exception as e:  # noqa: BLE001 - never block setup for a listing
        print(f"      (could not list devices: {e})")
    if not skip_meter:
        try:
            mic_level_meter()
        except Exception as e:  # noqa: BLE001
            print(f"      (level meter skipped: {e})")

    # 3. model download (faster-whisper shows a progress bar on first fetch)
    print(f"\n[3/4] Downloading model '{model}' (first time only; be patient)...")
    from .transcriber import Transcriber

    t0 = time.perf_counter()
    stt = Transcriber(model, "auto", "auto")
    print(f"      Model ready in {time.perf_counter()-t0:.1f}s "
          f"(device={stt.device}, compute={stt.compute_type})")

    # 4. persist settings
    print("\n[4/4] Saving settings...")
    cfg = Config()
    cfg.model_size = model
    settings_store.save_settings(cfg)
    print(f"      {settings_store.settings_path()}")
    print(f"      Your editable dictionary: {settings_store.user_dictionary_path()}")
    print("\nSetup complete. Run 'python -m src.main' and hold Right-Ctrl to dictate.")
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="accept all defaults, no prompts")
    ap.add_argument("--skip-meter", action="store_true", help="skip the live mic level meter")
    args = ap.parse_args()
    run_wizard(auto_yes=args.yes, skip_meter=args.skip_meter)
    return 0


if __name__ == "__main__":
    sys.exit(main())
