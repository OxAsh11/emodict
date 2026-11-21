"""Central config. Edit values here until a settings UI exists (Weekend 2)."""
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    # STT
    model_size: str = "small"          # tiny / base / small / medium / large-v3-turbo
    device: str = "auto"               # auto -> cuda if available else cpu
    compute_type: str = "auto"         # auto -> int8_float16 on cuda, int8 on cpu
    language: str = "en"

    # Hotkey (push-to-talk)
    hold_key: str = "right ctrl"       # keyboard-library key name
    mic_device: int = -1               # -1 = system default input

    # Injection
    inject_mode: str = "clipboard"     # clipboard (paste + restore) | none (print only)
    paste_settle_s: float = 0.15       # wait after Ctrl+V before restoring clipboard

    # Startup
    start_with_windows: bool = False

    # Cleanup
    strip_fillers: bool = True
    dictionary_path: str = str(PROJECT_ROOT / "dictionary.json")
    show_tone_tags: bool = True        # global kill-switch for [tone: ...] output

    # Emotion (Weekend 4)
    emotion_enabled: bool = False      # flip after funasr is installed
    emotion_model: str = "iic/emotion2vec_plus_base"
    tone_tag_threshold: float = 0.60   # below this, emit no tag

    # History
    log_takes: bool = True
    history_path: str = str(PROJECT_ROOT / "history.log")

    # Dashboard
    dashboard_port: int = 8417
