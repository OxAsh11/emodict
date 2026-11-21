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

## Weekend 2: quality
- [ ] Upgrade model default to large-v3-turbo on CUDA (install nvidia-cublas-cu12, nvidia-cudnn-cu12)
- [ ] Calibration: real mic latency measurement, hold-vs-toggle modes
- [ ] Dictionary UI pass: log every dictation, mine corrections (history.log)
- [ ] System tray (pystray) + pulsing overlay dot + hide-to-tray

## Weekend 3: LLM cleanup
- [ ] Ollama (llama3.2:3b, CPU) cleanup stage parallel to GPU STT
- [ ] Prompt: punctuation, self-corrections ("Monday, no wait, Tuesday"), raw mode
- [ ] AI-edit mode: select text + hold Right-Alt + speak instruction
- [ ] Voice command: "scratch that" cancels take

## Weekend 4: emotion layer
- [ ] pip install funasr (+ torch) in the venv; load iic/emotion2vec_plus_base
- [ ] Fork audio: emotion2vec per chunk, align to Whisper segment timestamps
- [ ] Emit [tone: label, confidence] per segment; threshold 0.6, hysteresis on
- [ ] Per-user calibration: label 50 own clips, bias classes (Indian-English baseline)
- [ ] Dogfood: dictate to Hermes with tags on; measure whether responses change

## Later: layer 3 + distribution
- [ ] Emotion-to-action hooks (see thesis: frustration -> context re-retrieval)
- [ ] Preference memory from delight signals, anti-sycophancy guards
- [ ] Packaging: PyInstaller exe, Tier 1 local-first installer
- [ ] Tier 2 serverless GPU backend (streaming during speech), Mumbai/Singapore region
- [ ] Tier 3 WebGPU browser demo

## Run log
2026-11-21: offline pipeline test VERIFIED. Model=base, device=cuda (RTX 3050), compute=int8_float16.
Input: Windows TTS wav, 10.8s. Transcription: 1.35s (8x real-time).
Output: "This is a test of the emotion dictation pipeline. You know, it should transcribe just fine. Flytbase drone operations."
Bugs found and fixed during verification:
1. nvidia pip DLLs (cublas/cudnn) not on DLL search path -> _register_nvidia_dlls() in transcriber.py (add_dll_directory + PATH prepend)
2. dictionary replace without word boundaries ("FLYT based" -> "Flytbased") -> \b-anchored regex
3. ctypes 64-bit pointer truncation in clipboard code (access violation) -> explicit restype/argtypes prototypes
Clipboard round-trip test: set_ok=True, roundtrip_ok=True, restored=True (no paste sent during test).

