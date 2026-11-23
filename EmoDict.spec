# -*- mode: python ; coding: utf-8 -*-
# EmoDict build spec.
#   CPU build (default):            pyinstaller EmoDict.spec
#   GPU build (bundles CUDA):       EMO_BUILD_GPU=1 pyinstaller EmoDict.spec
# Emotion (torch+funasr, ~700MB) is ALWAYS bundled - it is the product's thesis.
import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

gpu = os.environ.get("EMO_BUILD_GPU", "0") == "1"

binaries = collect_dynamic_libs("ctranslate2")
datas = [("tools/test_input.wav", "tools"), ("docs/QUICKSTART.md", "docs"),
         ("assets/icon.ico", "assets"),
         # update_check reads the app version from here (one bump per release)
         ("VERSION.txt", ".")]
# faster_whisper ships its Silero VAD onnx model as package data; without it
# every transcribe() dies with NoSuchFile in the frozen build.
datas += collect_data_files("faster_whisper", include_py_files=False)
# speechbrain (voice lock) loads model classes dynamically + hyperpyyaml
datas += collect_data_files("funasr", include_py_files=True)
hiddenimports = (collect_submodules("funasr")
                 + collect_submodules("speechbrain")
                 + ["torchaudio", "hyperpyyaml"])
if gpu:
    for pkg in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc"):
        binaries += collect_dynamic_libs(pkg)

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "src", "src.main", "src.wizard", "src.wizard_gui", "src.settings_window",
        "src.tray", "src.hardware", "src.settings_store", "src.selftest",
        "src.recorder", "src.transcriber", "src.cleanup", "src.injector",
        "src.emotion", "src.config", "src.overlay", "src.welcome",
        "src.dashboard", "src.stats", "src.crash", "src.update_check",
    ] + hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "pytest", "umap", "numba", "llvmlite"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="EmoDict",
    icon="assets/icon.ico",
    debug=False,
    console=False,          # tray app; logs go to %LOCALAPPDATA%/EmoDict/logs
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,              # UPX triggers antivirus false positives
    name="EmoDict",
)
