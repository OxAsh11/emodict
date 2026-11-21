"""Text injection: clipboard swap + Ctrl+V, previous clipboard restored.

Disclosed behaviour (same as the reference implementations): dictated text sits
in the clipboard for <1s before your previous clipboard content is restored.
Uses raw ctypes so no extra dependency is needed.
"""
import ctypes
import time
from ctypes import wintypes

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# 64-bit safety: without explicit prototypes, ctypes truncates HANDLE/HGLOBAL
# pointers to 32-bit ints and you get access violations.
_user32.GetClipboardData.restype = ctypes.c_void_p
_user32.GetClipboardData.argtypes = [wintypes.UINT]
_user32.SetClipboardData.restype = ctypes.c_void_p
_user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
_kernel32.GlobalAlloc.restype = ctypes.c_void_p
_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
_kernel32.GlobalUnlock.restype = wintypes.BOOL
_kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]


def _open_clipboard(retries: int = 10, delay: float = 0.05) -> bool:
    for _ in range(retries):
        if _user32.OpenClipboard(None):
            return True
        time.sleep(delay)
    return False


def get_clipboard_text() -> str | None:
    if not _open_clipboard():
        return None
    try:
        handle = _user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = _kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.cast(ptr, ctypes.c_wchar_p).value
        finally:
            _kernel32.GlobalUnlock(handle)
    finally:
        _user32.CloseClipboard()


def set_clipboard_text(text: str) -> bool:
    if not _open_clipboard():
        return False
    try:
        _user32.EmptyClipboard()
        buf = ctypes.create_unicode_buffer(text)
        h_global = _kernel32.GlobalAlloc(GMEM_MOVEABLE, ctypes.sizeof(buf))
        if not h_global:
            return False
        ptr = _kernel32.GlobalLock(h_global)
        ctypes.memmove(ptr, buf, ctypes.sizeof(buf))
        _kernel32.GlobalUnlock(h_global)
        return bool(_user32.SetClipboardData(CF_UNICODETEXT, h_global))
    finally:
        _user32.CloseClipboard()


def inject(text: str, settle_s: float = 0.15, dry_run: bool = False) -> bool:
    """Paste `text` at the cursor. dry_run prints instead of touching anything."""
    if dry_run:
        print(f"[inject:dry-run] {text!r}")
        return True
    prev = get_clipboard_text()
    if not set_clipboard_text(text):
        print("[inject] could not open/set clipboard")
        return False
    import keyboard

    keyboard.send("ctrl+v")
    time.sleep(settle_s)
    if prev is not None:
        set_clipboard_text(prev)  # restore user's clipboard
    return True
