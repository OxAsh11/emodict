# emotion-dictation
Local-first dictation engine: global hotkey -> speech -> text, with an audio fork that extracts emotion and emits tone tags. Working name open. Product thesis: `../emotion-dictation-thesis.md`.

## Pipeline
```
hold Right-Ctrl -> mic capture (16k mono, RAM only)
  fork:
    Whisper branch  -> words + timestamps (faster-whisper)
    emotion branch  -> tone + confidence (emotion2vec, Weekend 4; stub today)
  -> timestamp alignment -> rule cleanup + custom dictionary -> inject at cursor
```

## Setup (Python 3.11 pinned via uv; ML wheels lag on newer)
```
cd emotion-dictation
uv venv --python 3.11
uv pip install -r requirements.txt        # run with venv active, or: uv pip install -p .venv -r requirements.txt
```

## Run
```
.venv/Scripts/python.exe -m src.main
```
Hold **Right-Ctrl**, speak, release. Text is pasted into whatever has focus. Esc-quit via tray later; for now Ctrl+C in the console. Global keyboard hook = it captures the hotkey everywhere; only Right-Ctrl is bound.

## Offline test (no hotkey, no injection)
```
powershell -File tools/make_test_wav.ps1          # synthesizes a test wav via Windows TTS
.venv/Scripts/python.exe -m src.test_offline --wav tools/test_input.wav --model base
```

## GPU (optional, RTX 3050 6GB tested target)
CPU int8 is the default fallback. For CUDA:
```
uv pip install -p .venv nvidia-cublas-cu12 nvidia-cudnn-cu12
```
then set `device: cuda` in config. Model `large-v3-turbo` fits in 6GB at int8_float16.

## Modules
- `src/recorder.py` sounddevice capture, RAM-only
- `src/transcriber.py` faster-whisper wrapper, auto device/compute
- `src/emotion.py` emotion2vec hook (stub until Weekend 4)
- `src/cleanup.py` filler rules, dictionary, tone-tag formatting
- `src/injector.py` clipboard-swap paste via ctypes, previous clipboard restored
- `src/main.py` hotkey wiring, worker thread, shutdown guard (no injection after quit begins)

## Status
See PLAN.md. Weekend 1 vertical slice: DONE (offline path verified end-to-end on real audio).
