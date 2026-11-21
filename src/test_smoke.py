"""Headless smoke test for A2 (settings window internals, tray, startup helper).
Builds a withdrawn tkinter root, constructs the real SettingsWindow, destroys
it immediately. Nothing is pasted; the startup folder is only touched via
dry-run (write=False). Run: python -m src.test_smoke"""
import json
import sys
import tempfile
from pathlib import Path

OK, FAIL = "PASS", "FAIL"
results = []


def check(name, cond, detail=""):
    results.append((name, OK if cond else FAIL, detail))


# 1. imports
try:
    from src import main as main_mod  # noqa: F401
    from src import settings_window, tray  # noqa: F401
    check("imports (main/tray/settings_window)", True)
except Exception as e:  # noqa: BLE001
    check("imports (main/tray/settings_window)", False, str(e))
    for n, _, d in results:
        print(f"{n}: {_} {d}")
    sys.exit(1)

from src import settings_store  # noqa: E402
from src.config import Config  # noqa: E402

# 2. dictionary text round-trip
d = {"flyt base": "Flytbase", "wispr flow": "Wispr Flow", "odd": "One"}
text = settings_store.dict_to_text(d)
back, skipped = settings_store.text_to_dict(text + "\ngarbage line\n")
check("dict_to_text/text_to_dict round-trip", back == d and skipped == 1,
      f"skipped={skipped}")

# 3. settings save/load with new fields
cfg = Config()
cfg.mic_device = 5
cfg.start_with_windows = False
cfg.show_tone_tags = False
settings_store.save_settings(cfg)
loaded = settings_store.load_settings()
check("settings round-trip (mic/startup/tone-tags)",
      loaded.mic_device == 5 and loaded.show_tone_tags is False)
check("settings paths point at APPDATA",
      loaded.dictionary_path == str(settings_store.user_dictionary_path()))

# 4. startup vbs dry-run: never writes
p = settings_store.set_start_with_windows(
    True, Path("C:/proj"), Path("C:/py/pythonw.exe"), write=False)
vbs_exists = p.exists() if p else True
check("startup vbs dry-run writes nothing", p is not None and not vbs_exists,
      f"would write: {p}")

# 5. tray icon construction (no run)
t = tray.Tray(on_settings=lambda: None, on_toggle_pause=lambda: None,
              on_quit=lambda: None)
img = tray._make_icon_image(True)
check("tray icon + menu built", t.icon is not None and img.size == (64, 64))
t.set_paused(True)
t.set_paused(False)

# 6. real SettingsWindow built on a withdrawn root, then destroyed
import tkinter as tk  # noqa: E402

root = tk.Tk()
root.withdraw()
win = settings_window.SettingsWindow(root, loaded, on_save=lambda c: None)
root.update_idletasks()  # realize widgets
values_ok = (win.hold_var.get() == loaded.hold_key
             and win.model_var.get() == loaded.model_size
             and win.tags_var.get() is False)
dict_editor = win.dict_text.get("1.0", "end").strip()
editor_ok = "flyt base -> Flytbase" in dict_editor
root.destroy()
check("settings window builds with persisted values", values_ok)
check("dictionary editor shows user dictionary", editor_ok)

print()
fails = 0
for n, s, d in results:
    print(f"{s}  {n}" + (f"  [{d}]" if d else ""))
    fails += s == FAIL
print(f"\n{len(results)-fails}/{len(results)} passed")
sys.exit(1 if fails else 0)
