"""Version + update check. Prompt-only: fetches a plain-text version from the
project repo (404 = repo not public yet -> silent no-op), compares, and the
tray notifies. Never downloads anything by itself."""
import json
import urllib.request

VERSION = "0.3.0"
# Becomes live the day the repo exists; until then every check 404s silently.
UPDATE_URL = "https://raw.githubusercontent.com/OxAsh11/emodict/main/VERSION.txt"


def _parse(v: str):
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except ValueError:
        return None


def check_for_update(timeout: float = 4.0) -> tuple[bool, str, str]:
    """Returns (update_available, latest_version, current_version)."""
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
