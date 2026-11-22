"""Acoustic inspector: print the full profile of any audio file (or 'debug'
to analyze your latest captured takes). Run:
    .venv/Scripts/python.exe tools/inspect_audio.py path/to/take.wav
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from src.recorder import load_audio_file  # noqa: E402

SR = 16000


def f0_autocorr(chunk: np.ndarray) -> float | None:
    """Rough pitch: autocorrelation peak in the human range 70-350Hz."""
    if len(chunk) < SR // 4:
        return None
    w = chunk[: SR // 2] * np.hanning(SR // 2)
    ac = np.correlate(w, w, "full")[len(w):]
    lo, hi = int(SR / 350), int(SR / 70)
    if hi >= len(ac):
        return None
    peak = ac[lo:hi].argmax() + lo
    if ac[peak] < 0.3 * ac.max():
        return None
    return SR / peak


def profile(name: str, a: np.ndarray) -> None:
    dur = len(a) / SR
    frames = [a[i:i + 400] for i in range(0, len(a) - 400, 400)]
    speech = [f for f in frames if np.abs(f).max() > 0.01]
    silent = [f for f in frames if np.abs(f).max() <= 0.01]
    rms_sp = np.sqrt(np.mean([f**2 for f in speech])) if speech else 0
    rms_si = np.sqrt(np.mean([f**2 for f in silent])) if silent else 1e-9
    snr = 20 * np.log10(rms_sp / (rms_si + 1e-12))
    f0s = [f0_autocorr(f) for f in speech]
    f0s = [f for f in f0s if f]
    # spectral centroid: brightness
    cents = []
    for f in speech:
        sp = np.abs(np.fft.rfft(f * np.hanning(400)))
        freqs = np.fft.rfftfreq(400, 1 / SR)
        cents.append((sp * freqs).sum() / (sp.sum() + 1e-9))
    print(f"\n=== {name} ===")
    print(f"duration      {dur:6.2f}s   ({len(a):,} samples @ 16kHz)")
    print(f"peak          {np.abs(a).max():6.3f}   (1.0 = full scale)")
    print(f"speech RMS    {rms_sp:6.4f}   loudness of your voice")
    print(f"silence RMS   {rms_si:6.4f}   noise floor between words")
    print(f"SNR           {snr:6.1f} dB  (tone tags off below 6)")
    print(f"pitch (F0)    {np.median(f0s):6.0f} Hz  +- {np.std(f0s):.0f}"
          f"  (spread = intonation)")
    print(f"centroid      {np.mean(cents):6.0f} Hz  (brightness/texture)")
    print(f"speech frames {len(speech)}/{len(frames)}"
          f"  ({len(speech)/max(len(frames),1):.0%} voiced-active)")


def main() -> int:
    args = sys.argv[1:] or ["debug"]
    files = []
    for arg in args:
        p = Path(arg)
        if p.is_dir():
            files += sorted(p.glob("*.wav"))
        elif arg == "debug":
            d = Path(__import__("os").environ["LOCALAPPDATA"]) / "EmoDict/debug"
            files += sorted(d.glob("*.wav")) if d.exists() else []
        else:
            files.append(p)
    for f in files[-6:]:
        profile(f.name, load_audio_file(str(f)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
