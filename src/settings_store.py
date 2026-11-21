"""Persistent settings in %APPDATA%/EmoDict/settings.json (survives updates).
The dictionary and history also live there once the app has run, so a user
can edit their dictionary without touching the install folder."""
import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Optional

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


# ---- dictionary editor serialization ---------------------------------------
def dict_to_text(d: dict) -> str:
    return "\n".join(f"{k} -> {v}" for k, v in d.items())


def text_to_dict(text: str) -> tuple[dict, int]:
    """Parse editor text. Returns (dict, skipped_line_count)."""
    out, skipped = {}, 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if " -> " not in line:
            skipped += 1
            continue
        wrong, right = (s.strip() for s in line.split(" -> ", 1))
        if wrong and right:
            out[wrong] = right
        else:
            skipped += 1
    return out, skipped


def save_user_dictionary(d: dict) -> None:
    user_dictionary_path().write_text(
        json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


# ---- start with Windows -----------------------------------------------------
def startup_vbs_path() -> Path:
    return (Path(os.getenv("APPDATA") or str(Path.home()))
            / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
            / "EmoDict.vbs")


def set_start_with_windows(enabled: bool, project_dir: Path, pythonw_exe: Path,
                           write: bool = True) -> Optional[Path]:
    """Create/remove the startup launcher. write=False = dry-run (returns the
    path it WOULD write, writes nothing) so tests never touch the real folder."""
    path = startup_vbs_path()
    if not enabled:
        if write and path.exists():
            path.unlink()
        return None
    vbs = (
        f'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.CurrentDirectory = "{project_dir}"\n'
        f'WshShell.Run """{pythonw_exe}"" -m src.main", 0, False\n'
    )
    if write:
        path.write_text(vbs, encoding="utf-8")
    return path
