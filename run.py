"""PyInstaller entry point. Also the dev-friendly runner.

Frozen (windowed) apps have no console: stdout/stderr go to a log file in
%LOCALAPPDATA%/EmoDict/logs/emodict.log. --selftest runs the packaged offline
pipeline check and exits with a code (no hotkey, no injection, no mic).
"""
import os
import sys
from pathlib import Path


def _redirect_stdout_when_frozen() -> None:
    if not getattr(sys, "frozen", False):
        return
    base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "EmoDict"
    logdir = base / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    log = open(logdir / "emodict.log", "a", buffering=1, encoding="utf-8")
    sys.stdout = log
    sys.stderr = log
    print(f"\n===== EmoDict start (frozen) {sys.argv} =====", flush=True)


if __name__ == "__main__":
    _redirect_stdout_when_frozen()
    if "--selftest" in sys.argv:
        from src.selftest import run_selftest

        raise SystemExit(run_selftest())
    from src.main import main

    raise SystemExit(main())
