# EmoDict

[![Release](https://img.shields.io/github/v/release/OxAsh11/emodict)](https://github.com/OxAsh11/emodict/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Local-first voice dictation for Windows, with emotion-aware tone tags.**

Hold a key, speak, release. Your words are typed into whatever app has focus.
An optional emotion fork reads the tone of your voice and annotates the output
with machine-parseable tags like `[tone: happy, 0.98]`. Everything runs on
your machine. Nothing you say ever leaves it.

```
hold Right-Ctrl -> mic capture -> fork:
    Whisper (faster-whisper)     -> words + timestamps
    emotion2vec (optional)       -> tone + confidence
-> alignment -> cleanup + custom dictionary -> paste at cursor
```

## Download

Grab `EmoDict-CPU-win64.zip` from the [latest release](https://github.com/OxAsh11/emodict/releases/latest),
unzip, double-click `EmoDict.exe`. No Python, no installer, no account.
First run downloads a speech model (150-800MB, one time) and walks you through
mic setup. See `docs/QUICKSTART.md` inside the zip.

Two builds:
- **CPU** (106MB): any Windows 10/11 machine
- **GPU** (1.4GB): bundles the CUDA runtime; NVIDIA GPUs transcribe ~8x faster

## Features

- Push-to-talk anywhere: hold Right-Ctrl, speak, release. Pre-roll buffer so
  your first word is never cut
- 100% offline after the one-time model download (faster-whisper, int8)
- First-run wizard: hardware probe, model pick, mic check with level meter
- Tray app: settings window, pause, quit; start-with-Windows
- Custom dictionary ("flyt base -> Flytbase") - fix a mishearing once, forever
- Optional emotion fork: `[tone: label, confidence]` tags per segment,
  neutral suppressed (calm speech is not information)
- Built-in health check: `EmoDict.exe --selftest`
- Crash logs + friendly errors; prompt-only update check

## Privacy

Audio lives in RAM only, transcription runs locally, and the only network
call is the one-time model download (plus the optional manual update check).
The codebase has no other networking.

## Development

Python 3.11 pinned via [uv](https://docs.astral.sh/uv/) (ML wheels lag on
newer Pythons):

```bash
uv venv --python 3.11
uv pip install -p .venv -r requirements.txt

# offline pipeline test (no hotkey, no injection, uses a bundled wav)
powershell -File tools/make_test_wav.ps1
.venv/Scripts/python.exe -m src.test_offline --wav tools/test_input.wav --model base

# widget/tray/settings smoke test
.venv/Scripts/python.exe -m src.test_smoke

# run (tray app; --dry prints instead of pasting)
.venv/Scripts/python.exe -m src.main --dry
```

Emotion fork (optional): `uv pip install -p .venv torch --index-url
https://download.pytorch.org/whl/cpu && uv pip install -p .venv funasr`,
then enable "Analyze tone" in Settings.

Build (PyInstaller, onedir, UPX off):

```bash
pyinstaller EmoDict.spec                  # CPU build
EMO_BUILD_GPU=1 pyinstaller EmoDict.spec  # GPU build
```

## Status

v0.1.x beta. Roadmap and verified run log in [PLAN.md](PLAN.md): LLM cleanup
stage, per-user emotion calibration, emotion-to-action hooks (tone changes how
the receiving AI processes your request, not just the text it returns).

## License

[MIT](LICENSE)
