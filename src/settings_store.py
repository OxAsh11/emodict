"""Persistent settings in %APPDATA%/EmoDict/settings.json (survives updates).
The dictionary and history also live there once the app has run, so a user
can edit their dictionary without touching the install folder."""
import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path

from .config import Config, PROJECT_ROOT

APP_NAME = "EmoDict"


def appdata_dir() -> Path:
    base = os.getenv("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def settings_path() -> Path:
    return appdata_dir() / "settings.json"


def user_dictionary_path() -> Path:
    return appdata_dir() / "dictionary.json"


def user_history_path() -> Path:
    return appdata_dir() / "history.log"


def _seed_user_files() -> None:
    """Copy the project's default dictionary next to settings on first run."""
    src = PROJECT_ROOT / "dictionary.json"
    dst = user_dictionary_path()
    if src.exists() and not dst.exists():
        shutil.copy(src, dst)


def settings_exist() -> bool:
    return settings_path().exists()


def save_settings(cfg: Config) -> None:
    _seed_user_files()
    cfg.dictionary_path = str(user_dictionary_path())
    cfg.history_path = str(user_history_path())
    settings_path().write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")


def load_settings() -> Config:
    """Config from APPDATA if present, else defaults (paths pointed at APPDATA
    only after a save; defaults stay portable for repo use)."""
    cfg = Config()
    p = settings_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[settings] could not read {p}: {e}; using defaults")
    return cfg
