# EmoDict

[![Release](https://img.shields.io/github/v/release/OxAsh11/emodict)](https://github.com/OxAsh11/emodict/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Local-first voice dictation for Windows that carries your tone, not just your words.**

Hold a key, speak, release. Your words are typed into whatever app has focus, with a tag that says *how* you said them:

```
[tone: angry, 0.81] This is the third time I'm explaining this.
```

Paste that into any AI chat and the model knows the mood behind the request. Everything runs on your machine. Your audio never leaves it.

---

## How it works

```
hotkey (hold, or double-tap for hands-free)
   │
   ▼
mic capture ── audio kept in RAM only
   │
   ├──► Whisper (faster-whisper) ── words + timestamps
   │       GPU builds stream while you speak, so the wait after release is short
   │
   └──► emotion2vec ── tone + confidence, scored per 6–15 s block of speech
   │
   ▼
voice lock ── keeps only your enrolled voice; drops the TV and other speakers
   ▼
cleanup ── filler words removed, your custom dictionary applied
   ▼
paste at the cursor, in the window you started in
```

---

## What's new in 0.4

- **Streaming transcription (GPU builds).** Whisper transcribes new audio while you are still talking and locks stable words as it goes. Measured on a 16.1-second take: 0.64 s wait after release, against 4.22 s for one pass at the end, with the same words.
- **Voice lock.** EmoDict learns your voice from your own takes and drops segments spoken by anyone else, such as a TV, a radio or people nearby.
- **Streaming tone.** Long takes are scored block by block as you speak, so tone tags no longer slow down with take length.
- **Sturdier start-up.** If a model fails to load, EmoDict falls back to a smaller one instead of crashing. A second copy refuses to start and points you to the one in the tray.

Full history: [Releases](https://github.com/OxAsh11/emodict/releases) and [PLAN.md](PLAN.md).

---

## Features

**Dictation**
- Hold the hotkey to talk, or double-tap it for hands-free recording; the next press stops and pastes.
- The hotkey is configurable (Right-Ctrl by default), and its normal function is suspended while EmoDict runs.
- A pre-roll buffer means your first word is never cut off.
- Long takes are pasted into the window you were in when you started, even if you clicked elsewhere.
- A custom dictionary fixes a mishearing once, for good (`"flyt base" → "Flytbase"`).

**Tone**
- The emotion engine is on by default and can be turned off in Settings.
- Voice memory: after about 8 takes per emotion, EmoDict judges tone against *your* normal, not an average voice.
- Noise-robust: tone is scored only on speech, and suppressed when the room is too noisy to judge (below 6 dB signal-to-noise).

**App**
- A first-run wizard checks your hardware, picks a model and tests your mic.
- The main window keeps a searchable log of every take, with a detail pane to copy the full text.
- A tray icon gives you settings, pause and quit, with optional start-with-Windows.
- A local performance dashboard shows takes, words, latency and failures (served on 127.0.0.1 only).
- Health check: `EmoDict.exe --selftest` proves both words and tone work on any install.

---

## Download

Get the latest build from [Releases](https://github.com/OxAsh11/emodict/releases/latest):

| File | For |
|---|---|
| `EmoDict-Setup-x.y.z.exe` | Recommended. Installer with Start-menu entry, uninstaller and optional autostart |
| `EmoDict-CPU-win64.zip` | Portable; any Windows 10/11 machine |
| `EmoDict-GPU-win64.zip` | NVIDIA GPUs; CUDA bundled; about 8x faster, with streaming transcription |

On first run EmoDict downloads its models once: a speech model (size depends on the model the wizard picks), the emotion model (about 600 MB) and a small speaker model for voice lock. After that it works offline.

The builds are unsigned during the beta, so Windows SmartScreen will warn you. Choose **More info → Run anyway**. Quit EmoDict from the tray before installing an update; your settings, dictionary and voice profile carry over.

> The source on `main` is v0.4.8. If the latest release is older, the 0.4 features above arrive with the next packaged release.

---

## Privacy

- Audio stays in RAM. Transcription, tone and voice lock all run on your machine.
- The only network traffic is the one-time model downloads and an update check, which reads `VERSION.txt` from this repo and tells you in the tray. It never downloads or installs anything by itself.
- The performance dashboard listens on 127.0.0.1 only.

---

## Development

Python 3.11, pinned with [uv](https://docs.astral.sh/uv/) (ML wheels lag on newer Pythons):

```bash
uv venv --python 3.11
uv pip install -p .venv -r requirements.txt

# offline pipeline test (no hotkey, no paste; uses a bundled wav)
powershell -File tools/make_test_wav.ps1
.venv/Scripts/python.exe -m src.test_offline --wav tools/test_input.wav --model base

# widget / tray / settings smoke test
.venv/Scripts/python.exe -m src.test_smoke

# run the tray app; --dry prints instead of pasting
.venv/Scripts/python.exe -m src.main --dry
```

Tone and voice lock need extra packages that are not in `requirements.txt`:

```bash
uv pip install -p .venv torch --index-url https://download.pytorch.org/whl/cpu
uv pip install -p .venv funasr speechbrain
```

Build with PyInstaller (onedir, UPX off):

```bash
pyinstaller EmoDict.spec                  # CPU build
EMO_BUILD_GPU=1 pyinstaller EmoDict.spec  # GPU build
```

The installer is built from `installer.iss` with Inno Setup; pass the version with `/DMyVersion=x.y.z`.

### Layout

| Path | What |
|---|---|
| `src/main.py` | App, hotkey and take lifecycle |
| `src/recorder.py`, `src/streaming.py` | Mic capture and streaming transcription |
| `src/transcriber.py` | faster-whisper wrapper with crash-proof model loading |
| `src/emotion.py`, `src/emo_stream.py`, `src/voice_memory.py`, `src/calibration.py` | Tone scoring, per-block streaming, per-user baselines |
| `src/voice_lock.py` | Speaker enrollment and filtering |
| `src/cleanup.py`, `dictionary.json` | Filler removal and custom dictionary |
| `src/injector.py` | Paste at the cursor and restore the clipboard |
| `src/mainwindow.py`, `src/tray.py`, `src/settings_window.py`, `src/wizard_gui.py` | UI |
| `src/dashboard.py`, `src/stats.py` | Local performance dashboard |
| `docs/` | Quick start and architecture |

---

## Status

v0.4.8 beta. Next on the roadmap ([PLAN.md](PLAN.md)): an LLM polish stage for transcripts, and emotion-to-action hooks, where tone changes how the receiving AI handles the request, not just the text it gets.

## License

[MIT](LICENSE)
