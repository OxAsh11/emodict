"""Crash capture: every unhandled exception goes to
%LOCALAPPDATA%/EmoDict/logs/crash.log with context, never a bare vanishing
traceback (windowed exes swallow them silently)."""
import os
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path


def logs_dir() -> Path:
    base = (Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            / "EmoDict" / "logs")
    base.mkdir(parents=True, exist_ok=True)
    return base


def log_exception(where: str, exc: BaseException) -> Path:
    """Append a formatted crash entry; returns the log path (best effort)."""
    path = logs_dir() / "crash.log"
    entry = (f"\n===== CRASH {datetime.now().isoformat(timespec='seconds')} "
             f"in {where} =====\n"
             + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(entry)
    except OSError:
        pass
    return path


def install_hooks() -> None:
    """Route unhandled exceptions (any thread) into crash.log."""
    def _main_hook(t, v, tb):
        p = log_exception("main thread", v)
        print("".join(traceback.format_exception(t, v, tb)), flush=True)
        print(f"[crash] saved to {p}", flush=True)

    def _thread_hook(args):
        p = log_exception(f"thread {args.thread.name if args.thread else '?'}",
                          args.exc_value)
        print(f"[crash] in thread; saved to {p}", flush=True)

    sys.excepthook = _main_hook
    threading.excepthook = _thread_hook
