"""Input state machine test: hold-to-talk, double-tap toggle, stop-press,
stray tap. Drives App.on_press/on_release with a stub recorder and fake clock
(no models loaded, no real keys). Run: python -m src.test_input"""
import threading
import types
from types import SimpleNamespace

import sys

sys.path.insert(0, ".")
import src.main as main_mod  # noqa: E402
from src.main import App  # noqa: E402

T = [0.0]
main_mod.time.perf_counter = lambda: T[0]  # fake clock for the state machine

results = []


def check(name, cond):
    results.append((name, bool(cond)))


class FakeRecorder:
    def __init__(self):
        self.recording = False
        self.starts = 0

    def start(self):
        self.recording = True
        self.starts += 1

    def stop(self):
        self.recording = False
        return None


def make_app():
    a = SimpleNamespace(
        shutdown=threading.Event(), paused=False, _loading_model=False,
        recorder=FakeRecorder(), overlay=None, root=None,
        dispatched=0,
        _worker=None, _tap_timer=None,
        TAP_S=App.TAP_S, DBL_S=App.DBL_S,
        _press_time=0.0, _last_tap_end=0.0,
        _toggle_active=False, _swallow_until=0.0,
    )
    a.on_press = types.MethodType(App.on_press, a)
    a.on_release = types.MethodType(App.on_release, a)
    a._tap_timeout = types.MethodType(App._tap_timeout, a)
    a._cancel_tap_timer = types.MethodType(App._cancel_tap_timer, a)
    a._spawn_dispatch = types.MethodType(
        lambda self: (App._cancel_tap_timer(self),
                      setattr(self, "dispatched", self.dispatched + 1)), a)
    a._overlay_show = types.MethodType(lambda self, s: None, a)
    a._start_streaming = types.MethodType(lambda self: None, a)
    return a


T[0] = 0.0


def press(a):
    T[0] += 0.05
    a.on_press(None)


def release(a, hold):
    T[0] += hold
    a.on_release(None)
    T[0] += 0.05


# 1. classic hold-to-talk: hold 1s -> exactly one dispatch
a = make_app()
press(a)
check("hold: recording started", a.recorder.recording)
release(a, 1.0)
check("hold: dispatched once", a.dispatched == 1)
check("hold: not toggle", not a._toggle_active)

# 2. double-tap toggle: tap, tap -> recording continues; press -> dispatch
a = make_app()
press(a); release(a, 0.10)   # first tap
press(a); release(a, 0.10)   # second tap within window
check("dbl-tap: toggle active", a._toggle_active)
check("dbl-tap: still recording", a.recorder.recording)
check("dbl-tap: not dispatched yet", a.dispatched == 0)
T[0] += 0.6                  # beyond swallow window
press(a)                     # stop press
check("toggle stop: dispatched", a.dispatched == 1)
check("toggle stop: toggle cleared", not a._toggle_active)

# 3. stray single tap: dispatches after the DBL window via timer
a = make_app()
press(a); release(a, 0.10)
check("stray tap: waiting, still recording", a.recorder.recording)
a._tap_timeout()             # simulate timer fire
check("stray tap: dispatched after timeout", a.dispatched == 1)

# 4. swallow window: press right after toggle start does NOT stop
a = make_app()
press(a); release(a, 0.10)
press(a); release(a, 0.10)
press(a)                     # inside swallow window (immediate)
check("swallow: no dispatch", a.dispatched == 0)
check("swallow: still toggle", a._toggle_active)
check("swallow: still recording", a.recorder.recording)

fails = sum(1 for _, ok in results if not ok)
for n, ok in results:
    print(f"{'PASS' if ok else 'FAIL'}  {n}")
print(f"\n{len(results)-fails}/{len(results)} passed")
sys.exit(1 if fails else 0)
