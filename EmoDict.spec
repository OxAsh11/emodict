# -*- mode: python ; coding: utf-8 -*-
# EmoDict build spec.
#   CPU build (default, small zip):  pyinstaller EmoDict.spec
#   GPU build (bundles CUDA):        EMO_BUILD_GPU=1 pyinstaller EmoDict.spec
import os
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

gpu = os.environ.get("EMO_BUILD_GPU", "0") == "1"

binaries = collect_dynamic_libs("ctranslate2")
datas = [("tools/test_input.wav", "tools")]
# faster_whisper ships its Silero VAD onnx model as package data; without it
# every transcribe() dies with NoSuchFile in the frozen build.
datas += collect_data_files("faster_whisper", include_py_files=False)
if gpu:
    for pkg in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc"):
        binaries += collect_dynamic_libs(pkg)

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "src", "src.main", "src.wizard", "src.settings_window", "src.tray",
        "src.hardware", "src.settings_store", "src.selftest",
        "src.recorder", "src.transcriber", "src.cleanup", "src.injector",
        "src.emotion", "src.config",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["torch", "matplotlib", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="EmoDict",
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
