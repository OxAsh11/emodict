"""Version + update check. Prompt-only: fetches a plain-text version from the
project repo (404 = repo not public yet -> silent no-op), compares, and the
tray notifies. Never downloads anything by itself.

The local version comes from VERSION.txt (the same file the check reads
remotely), so a release only needs one bump. Frozen builds bundle it next to
the app (see EmoDict.spec). If it cannot be read, the version is unknown and
the check stays quiet rather than nagging about an update that may not exist."""
import json
import urllib.request
from pathlib import Path

UPDATE_URL = "https://raw.githubusercontent.com/OxAsh11/emodict/main/VERSION.txt"
VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION.txt"
UNKNOWN = "0.0.0"


def _parse(v: str):
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except ValueError:
        return None


def _read_local_version(path: Path = VERSION_FILE) -> str:
    try:
        first = path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    except (OSError, IndexError):
        return UNKNOWN
    return first if _parse(first) else UNKNOWN


VERSION = _read_local_version()


def check_for_update(timeout: float = 4.0) -> tuple[bool, str, str]:
    """Returns (update_available, latest_version, current_version)."""
    if VERSION == UNKNOWN:
        return False, VERSION, VERSION
    try:
        with urllib.request.urlopen(UPDATE_URL, timeout=timeout) as r:
            remote = r.read().decode("utf-8").strip().splitlines()[0]
    except Exception:  # noqa: BLE001 - offline / 404 / DNS: all mean "no check"
        return False, VERSION, VERSION
    a, b = _parse(remote), _parse(VERSION)
    if a is None or b is None:
        return False, VERSION, VERSION
    return a > b, remote, VERSION


if __name__ == "__main__":
    avail, latest, current = check_for_update()
    print(json.dumps({"update_available": avail,
                      "latest": latest, "current": current}))
