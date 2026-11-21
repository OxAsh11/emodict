# Build plan and status

## Weekend 1: vertical slice (DONE 2026-11-21)
- [x] Project scaffold, venv (Python 3.11 via uv), requirements, git
- [x] Recorder: sounddevice, 16k mono float32, RAM-only
- [x] Transcriber: faster-whisper, auto CPU-int8 fallback, GPU-ready
- [x] Cleanup: filler removal, sentence case, custom dictionary
- [x] Injector: clipboard swap + Ctrl+V, previous clipboard restored
- [x] Main: hold Right-Ctrl push-to-talk, worker thread, shutdown race guard
- [x] Offline test harness: Windows TTS wav -> full pipeline, no hotkey/injection
- [x] Verified on real audio: see PLAN bottom for the run log

Two tracks. Track A = the shippable local product (priority: one download, basic settings, run). Track B = the differentiating intelligence. A1-A3 get a friend-installable build; everything else can follow.

## TRACK A: shippable local product (priority)

### A1. First-run experience (DONE 2026-11-21)
- [x] Model auto-download with visible progress (HF hub progress; first fetch verified: large-v3-turbo in 323s)
- [x] Hardware probe on first launch: GPU/CPU/RAM -> auto-pick model (verified: RTX 3050 6GB -> large-v3-turbo)
- [x] Mic check: list devices (verified, 9 inputs listed); level meter code shipped, live test pending user run
- [x] Settings live in %APPDATA%/EmoDict/settings.json + user-editable dictionary copy

### A2. Settings window (the "basic settings" a user needs)
- [ ] Small window (tkinter/customtkinter): hotkey, model, mic, inject mode, tone tags on/off, start-with-Windows
- [ ] Dictionary editor (add/remove corrections)
- [ ] System tray (pystray): start/stop, settings, quit; close = hide to tray

### A3. Package as one download
- [ ] PyInstaller onedir build (onedir over onefile: faster start, fewer antivirus false positives)
- [ ] Bundle ctranslate2 + CUDA runtime + keyboard-hook deps; hidden-imports checklist
- [ ] CPU build ~200MB zip: unzip -> EmoDict.exe -> hold Right-Ctrl; no Python, no venv, no terminal
- [ ] Install test on a clean Windows user (the real gate)
- [ ] Antivirus check; code-sign cert before public release

### A4. Beta hardening
- [ ] Crash log to %LOCALAPPDATA% + friendly errors (never a bare traceback)
- [ ] Update check (prompt, not silent); one-page quickstart; 3-5 friend beta

## TRACK B: intelligence (after A3, interleavable)

### B1. Quality
- [ ] Real mic latency calibration; hold vs toggle modes
- [ ] Mine history.log for recurring mishearings -> dictionary suggestions

### B2. LLM cleanup
- [ ] Ollama (llama3.2:3b, CPU) cleanup parallel to STT; punctuation, self-corrections, raw mode
- [ ] AI-edit mode (select text + hold Right-Alt + speak instruction)

### B3. Emotion layer (the thesis)
- [ ] emotion2vec fork aligned to Whisper timestamps; [tone: label, score], threshold 0.6
- [ ] Per-user calibration (50 own clips, Indian-English baseline)
- [ ] Packaged product: optional add-on download (keeps base installer small)
- [ ] Dogfood vs Hermes; then emotion-to-action hooks + preference memory (anti-sycophancy guards)

### B4. Cloud tier (only if users with weak hardware show up)
- [ ] Thin-client streaming -> serverless GPU (Mumbai/Singapore), one warm instance; WebGPU demo page

## Run log
2026-11-21: offline pipeline test VERIFIED. Model=base, device=cuda (RTX 3050), compute=int8_float16.
Input: Windows TTS wav, 10.8s. Transcription: 1.35s (8x real-time).
Output: "This is a test of the emotion dictation pipeline. You know, it should transcribe just fine. Flytbase drone operations."
Bugs found and fixed during verification:
1. nvidia pip DLLs (cublas/cudnn) not on DLL search path -> _register_nvidia_dlls() in transcriber.py (add_dll_directory + PATH prepend)
2. dictionary replace without word boundaries ("FLYT based" -> "Flytbased") -> \b-anchored regex
3. ctypes 64-bit pointer truncation in clipboard code (access violation) -> explicit restype/argtypes prototypes
Clipboard round-trip test: set_ok=True, roundtrip_ok=True, restored=True (no paste sent during test).
2026-11-21 (A1): first-run wizard VERIFIED scripted (--yes --skip-meter). Probe: RTX 3050 6GB, 12 cores, 15.7GB RAM -> large-v3-turbo. Model download+load 323s. Settings + dictionary persisted to %APPDATA%\EmoDict. main.py auto-runs wizard when settings absent; load_settings() returns persisted model.
Re-test with large-v3-turbo on the same wav: 10.8s audio -> 3.2s transcription (3.4x real-time). Note: turbo drops punctuation on TTS audio (periods missing); sentence-case has nothing to key on. Known limitation -> LLM cleanup (B2) or punctuation post-pass; not chased now.

