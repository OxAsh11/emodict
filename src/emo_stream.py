"""Streaming emotion: score prosodic blocks WHILE recording, not after stop.

The locked-prefix STT loop emits sentences as they stabilize; consecutive
sentences are grouped into 6-15s prosodic blocks and each block is scored the
moment it completes (CPU, parallel with Whisper on GPU). At stop, only the
final partial block needs scoring - post-stop latency becomes independent of
take length. Voice-locked and SNR-gated per block, same rules as batch mode.
"""
import queue
import threading


class EmotionStreamWorker:
    def __init__(self, emotion, voice_lock, audio_src, min_s=6.0, max_s=15.0):
        self.emotion = emotion
        self.voice_lock = voice_lock
        self.audio_src = audio_src     # callable -> full audio snapshot
        self.min_s, self.max_s = min_s, max_s
        self.spans: list = []
        self._q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def submit(self, group: list) -> None:
        if group:
            self._q.put(group)

    def _loop(self) -> None:
        import numpy as np

        while True:
            try:
                group = self._q.get(timeout=0.3)
            except queue.Empty:
                if self._stop.is_set():
                    return
                continue
            try:
                audio = self.audio_src()
                # voice lock: keep only the user's segments in this block
                if self.voice_lock is not None and self.voice_lock.armed:
                    group = [s for s in group
                             if self.voice_lock.is_me(
                                 audio[int(s["start"] * 16000):
                                       int(s["end"] * 16000)])]
                if not group:
                    continue
                # score ONLY this block's time window - the noise floor must
                # come from pauses INSIDE the block, never from later speech
                # (the whole-buffer version measured future speech as noise
                # and silently dropped every live block)
                b0 = int(group[0]["start"] * 16000)
                b1 = int(group[-1]["end"] * 16000)
                window = audio[b0:b1]
                mask = np.zeros(len(window), dtype=bool)
                for s in group:
                    mask[max(0, int(s["start"] * 16000) - b0):
                         max(0, int(s["end"] * 16000) - b0)] = True
                speech = window[mask]
                noise = window[~mask]
                if len(speech) < 16000 // 2:
                    continue
                speech_rms = float(np.sqrt((speech ** 2).mean()))
                noise_rms = (float(np.sqrt((noise ** 2).mean()))
                             if len(noise) > 4000 else 1e-6)
                snr = 10 * float(np.log10((speech_rms / (noise_rms + 1e-9)) ** 2))
                if snr < 6.0:
                    continue  # noisy block: no tone call
                got = self.emotion.analyze(speech, 16000, None)
                if got:
                    self.spans.append({
                        "start": group[0]["start"], "end": group[-1]["end"],
                        "label": got[0]["label"], "score": got[0]["score"]})
            except Exception as e:  # noqa: BLE001 - one bad block never stops
                print(f"[emo-stream] block failed ({e.__class__.__name__}: "
                      f"{e})", flush=True)

    def stop(self, timeout: float = 20.0) -> list:
        """Drain and return scored spans (blocks submitted but unscored are
        dropped; the caller scores the final partial block inline)."""
        self._stop.set()
        self._thread.join(timeout=timeout)
        return list(self.spans)
