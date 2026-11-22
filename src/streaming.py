"""Streaming transcription: locked-prefix chunked decoding.

While recording, a background loop transcribes ONLY the audio that arrived
since the last pass (plus a 1s overlap), using stable-segment agreement to
lock finished sentences. At stop, only the final tail needs a pass.

COST MODEL (the reason this design): total compute stays proportional to
speech length. A 60s take costs ~60s of audio through the encoder once or
twice - NOT the O(n^2) blowup of naively re-transcribing the whole buffer.
GPU-only (device=='cuda'), adaptive interval.
"""
import threading
import time


class StreamingTranscriber:
    """Feed frames while recording; stop() returns the final transcript."""

    OVERLAP_S = 1.0      # audio before the lock point re-fed each pass
    STABLE_MARGIN_S = 1.5  # segments must end this far behind to lock
    MIN_CHUNK_S = 1.2    # don't run a pass for less than this new audio

    def __init__(self, stt, on_pass=None, poll_s: float = 1.2,
                 on_locked=None):
        self.stt = stt                 # shared Transcriber (calls serialized)
        self.on_pass = on_pass         # callback(partial_text) for UI
        self.on_locked = on_locked     # callback(newly_locked_segments)
        self.poll_s = poll_s
        self._buf: list = []
        self._n = 0                    # samples buffered
        self._lock_sample = 0          # samples locked as final
        self._locked_segs: list = []   # stable segments (absolute time)
        self._prev_segs: list = []
        self._passes = 0
        self._compute_s = 0.0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.final_segments: list = []
        self.wait_after_stop_s: float = 0.0

    # ---- producer (recorder callback thread) --------------------------------
    def push(self, frame) -> None:
        if frame.ndim > 1:  # sounddevice mono frames arrive as (N, 1)
            frame = frame.flatten()
        with self._lock:
            self._buf.append(frame)
            self._n += len(frame)

    def _snapshot(self):
        """Locked-prefix view of buffered audio."""
        import numpy as np

        with self._lock:
            start = max(0, self._lock_sample - int(self.OVERLAP_S * 16000))
            audio = np.concatenate(self._buf) if self._buf else np.zeros(0)
        return audio, start

    def snapshot_audio(self):
        """Full-buffer copy (for the emotion block worker)."""
        import numpy as np

        with self._lock:
            return np.concatenate(self._buf).copy() if self._buf else np.zeros(0, dtype="float32")

    # ---- consumer loop ---------------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(self.poll_s)
            if self._stop.is_set():
                return
            audio, start = self._snapshot()
            new_s = (len(audio) - (self._lock_sample - start)) / 16000
            if new_s < self.MIN_CHUNK_S:
                continue
            t0 = time.perf_counter()
            try:
                self._pass(audio, start)
            except Exception as e:  # noqa: BLE001 - one bad pass must never
                # kill the loop silently (the 2D-frame bug died silently and
                # every take fell back to batch for a whole day)
                print(f"[streaming] pass failed ({e.__class__.__name__}: "
                      f"{e}); continuing", flush=True)
            dt = time.perf_counter() - t0
            self._compute_s += dt
            # adaptive: never let passes consume more than ~50% of wall time
            if dt > self.poll_s:
                self.poll_s = min(4.0, dt * 1.3)

    def _pass(self, audio, start) -> None:
        tail = audio[max(0, start - 0):]  # snapshot already trimmed
        base = start / 16000.0
        segs = self.stt.transcribe(tail)
        abs_segs = [{"start": s["start"] + base, "end": s["end"] + base,
                     "text": s["text"]} for s in segs]
        now_end = len(audio) / 16000.0

        # stable segment = same (rounded) span AND same text in two passes,
        # ending far enough behind the live edge
        stable = []
        for s in abs_segs:
            if s["end"] > now_end - self.STABLE_MARGIN_S:
                continue
            for p in self._prev_segs:
                if (abs(p["start"] - s["start"]) < 0.6
                        and abs(p["end"] - s["end"]) < 0.6
                        and p["text"] == s["text"]):
                    stable.append(s)
                    break

        if stable:
            # extend the locked chain with stable segments in order
            newly = []
            for s in sorted(stable, key=lambda x: x["start"]):
                if not self._locked_segs or s["start"] >= self._locked_segs[-1]["end"] - 0.3:
                    self._locked_segs.append(s)
                    self._lock_sample = int(s["end"] * 16000)
                    newly.append(s)
            if newly and self.on_locked:
                try:
                    self.on_locked(newly)
                except Exception:  # noqa: BLE001
                    pass
        self._prev_segs = abs_segs
        self._passes += 1
        if self.on_pass:
            try:
                self.on_pass(" ".join(s["text"] for s in self._locked_segs))
            except Exception:  # noqa: BLE001 - UI callback must never break STT
                pass

    # ---- finish -------------------------------------------------------------------
    def stop(self) -> list:
        """Signal, run the final tail pass, return final segments."""
        t0 = time.perf_counter()
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=30)
        import numpy as np

        with self._lock:
            audio = np.concatenate(self._buf) if self._buf else np.zeros(0, dtype="float32")
        tail = audio[max(0, self._lock_sample - int(self.OVERLAP_S * 16000)):]
        base = max(0.0, (self._lock_sample - int(self.OVERLAP_S * 16000)) / 16000.0)
        if len(tail) > 16000 // 3:
            segs = self.stt.transcribe(tail)
            tail_segs = [{"start": s["start"] + base, "end": s["end"] + base,
                          "text": s["text"]} for s in segs]
        else:
            tail_segs = []
        # merge: locked segments + tail. Locked chain is authoritative; the
        # tail re-transcribes a 1s overlap, so drop segments fully covered
        # by locked time and TRIM shared words from partial overlaps (exact
        # text-equality dedup once duplicated boundary words: user saw
        # "Performance. Performance, right?" from one utterance).
        def trim_overlap(prev_text: str, new_text: str) -> str:
            a, b = prev_text.split(), new_text.split()
            for k in range(min(len(a), len(b), 12), 0, -1):
                if a[-k:] == b[:k]:
                    return " ".join(b[k:]).strip()
            return new_text.strip()

        merged = sorted(list(self._locked_segs) + [s for s in tail_segs],
                        key=lambda x: x["start"])
        out: list = []
        for s in merged:
            if not out:
                out.append(s)
                continue
            last_end = out[-1]["end"]
            if s["end"] <= last_end + 0.2:
                continue  # fully covered by the locked chain
            if s["start"] < last_end - 0.1:
                s = dict(s)
                s["text"] = trim_overlap(out[-1]["text"], s["text"])
                s["start"] = last_end
                if not s["text"]:
                    continue
            out.append(s)
        self.final_segments = out
        self.wait_after_stop_s = time.perf_counter() - t0
        return out

    @property
    def stats(self) -> str:
        return (f"passes={self._passes} compute={self._compute_s:.1f}s "
                f"final_wait={self.wait_after_stop_s:.2f}s")
