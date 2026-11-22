"""Streaming STT verification: feed a REAL captured take as if spoken live,
compare the streaming result against the batch transcription, report the
latency win and the compute cost. Run: python -m src.test_streaming"""
import os
import sys
import time

sys.path.insert(0, ".")
from src.recorder import load_audio_file  # noqa: E402
from src.streaming import StreamingTranscriber  # noqa: E402
from src.transcriber import Transcriber  # noqa: E402


def words(s):
    return set(w.strip(".,!?").lower() for w in s.split())


def main() -> int:
    wav = os.path.join(os.environ["LOCALAPPDATA"], "EmoDict", "debug",
                       "take_114205.wav")
    if not os.path.exists(wav):
        print("no captured take available")
        return 1
    audio = load_audio_file(wav)
    dur = len(audio) / 16000
    print(f"take: {dur:.1f}s")

    stt = Transcriber()  # auto: cuda on this machine
    print(f"engine: {stt.model_size if hasattr(stt,'model_size') else ''} "
          f"device={stt.device}")

    # baseline: batch transcription of the whole take (what happens at stop today)
    t0 = time.perf_counter()
    base_segs = stt.transcribe(audio)
    base_s = time.perf_counter() - t0
    base_text = " ".join(s["text"] for s in base_segs)
    print(f"batch: {base_s:.2f}s at stop")

    # streaming: feed 0.5s chunks at real-time pace (compressed x4 to keep
    # the test short; the loop logic is pace-independent)
    st = StreamingTranscriber(stt)
    st.start()
    chunk = 8000
    t0 = time.perf_counter()
    for i in range(0, len(audio), chunk):
        st.push(audio[i:i + chunk].copy())
        time.sleep(0.5 / 4)  # x4 faster than real time
    segs = st.stop()
    wall = time.perf_counter() - t0
    stream_text = " ".join(s["text"] for s in segs)

    overlap = len(words(base_text) & words(stream_text)) / max(
        len(words(base_text)), 1)
    print(f"streaming wall: {wall:.1f}s | {st.stats}")
    print(f"word agreement vs batch: {overlap:.0%}")
    print(f"STREAM TEXT: {stream_text[:120]}")
    ok = overlap >= 0.7 and len(stream_text) > 10
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
