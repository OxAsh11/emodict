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

### A2. Settings window + tray (DONE 2026-11-21, live-use check pending user)
- [x] Settings window (tkinter, stdlib): hotkey capture, model, mic, inject mode, tone tags, fillers, start-with-Windows (built + smoke-tested on real widgets)
- [x] Dictionary editor with 'heard -> corrected' lines (round-trip verified)
- [x] System tray (pystray): Settings / Pause-Resume / Quit, dynamic label, paused icon state
- [x] Live-apply on save: hotkey rebind + mic + cleaner instant, model reload in background (keeps old model on failure)
- [x] Start with Windows: .vbs in shell:startup (dry-run tested; never auto-created)

### A3. Package as one download (BUILT + SELFTEST-VERIFIED 2026-11-21; friend install pending)
- [x] PyInstaller onedir, windowed (tray app), UPX off (AV), logs to %LOCALAPPDATA%/EmoDict/logs
- [x] EmoDict.spec: CPU build (285MB dir / 106MB zip) and GPU build EMO_BUILD_GPU=1 (2.2GB dir / 1.37GB zip, bundles cublas+cudnn+nvrtc)
- [x] run.py entry + --selftest mode: full offline pipeline on bundled wav, exit code
- [x] Fixed in packaging: silero VAD onnx missing (collect_data_files faster_whisper); CUDA chosen without runtime (lazy cublas load -> CDLL preflight check); frozen DLL dir layout nvidia/<pkg>/bin
- [x] CPU exe selftest PASS (cpu int8, 13.3s transcribe); GPU exe selftest PASS (cuda int8_float16, 1.56s, ~8.5x faster)
- [x] Clean-cache simulation PASS: empty HF_HOME -> exe downloaded its own model (54.9s), transcribed, exit 0
- [x] Zips: dist/EmoDict-CPU-win64.zip (106MB), dist/EmoDict-GPU-win64.zip (1.37GB)
- [ ] Real friend install: unzip on a machine that has never run the venv; run exe; wizard; dictate
- [ ] Antivirus spot check on the zip/exe (Defender + one third-party); code-sign cert before public
- [ ] One-page quickstart inside the zip

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
2026-11-21: LIVE mic path user-verified (dry mode): takes of 0.53-2.01s end-to-end, large-v3-turbo on CUDA, cleanups applied. First real dictations logged.
2026-11-21 (A2): smoke test 8/8 PASS (src.test_smoke): imports, dictionary text round-trip (skipped-line handling), settings round-trip incl. mic_device/show_tone_tags, APPDATA paths, startup vbs dry-run, tray icon+menu+pause state, real SettingsWindow built on withdrawn root with persisted values, dictionary editor content. Fixed during A2: pystray MenuItem.text is read-only -> dynamic label via callable.
2026-11-21 (live-session fixes): user reported cut words + empty takes + model silently downgraded to small.
Root causes + fixes, all verified:
1. Smoke test clobbered real %APPDATA% settings (model small, mic 5, tags off) -> test now backs up/restores; user settings restored to large-v3-turbo.
2. Per-take mic stream open costs 100-300ms on Windows and drops that audio -> Recorder v2: stream opened once at app start, pre-roll ring 0.3s, tail drain 0.2s on stop. Verified with real mic: 1.0s hold -> 1.27s capture, ring + drain working, settings intact after test.
3. main.py: recorder is persistent (no per-press recreation), rebuilt only on mic change, closed on shutdown; guards for recorder=None.
2026-11-21 (A3): PyInstaller builds verified end-to-end by RUNNING the packaged exes.
CPU exe: selftest PASS device=cpu int8, 10.8s wav -> 13.3s transcribe, 285MB dir, zip 106MB.
GPU exe: selftest PASS device=cuda int8_float16, 1.56s transcribe (8.5x CPU), 2.2GB dir, zip 1.37GB.
Clean-cache sim: empty HF_HOME -> exe downloaded model itself (54.9s), transcribed 1.05s, PASS.
Packaging bugs fixed: (1) silero VAD onnx not collected -> collect_data_files("faster_whisper"); (2) driver present but no cublas made CPU builds pick cuda and die at first encode (lazy load past init fallback) -> _cuda_available now CDLL("cublas64_12.dll") preflight; (3) frozen nvidia DLL layout is nvidia/<pkg>/bin under _MEIPASS -> registered.
Note: first GPU-build selftest ran on cpu because of (3); after fix, cuda verified. Quirk: base model spells "F-L-Y-T" on the TTS clip (model quirk, not pipeline).

