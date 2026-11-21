"""Parse history.log and compute performance metrics.

history.log line format (v2): `ISO | elapsed_s | audio_s | tags | text`
elapsed_s may be `FAIL` for takes that produced nothing. Old v1 lines
(`ISO | audio_s | tags | text`, no elapsed) are tolerated.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


@dataclass
class Take:
    ts: datetime
    elapsed: float | None
    audio_s: float
    tags: list[str]
    text: str

    @property
    def words(self) -> int:
        return len(self.text.split())


def _parse_tags(raw: str) -> list[str]:
    raw = raw.strip().strip("[]")
    return [t.strip(" '\"") for t in raw.split(",") if t.strip(" '\"")]


def parse_history(path: str | Path) -> list[Take]:
    takes: list[Take] = []
    p = Path(path)
    if not p.exists():
        return takes
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = [s.strip() for s in line.split(" | ", 4)]
        try:
            if len(parts) == 5:  # v2
                ts = datetime.fromisoformat(parts[0])
                elapsed = None if parts[1] == "FAIL" else float(parts[1].rstrip("s"))
                audio = float(parts[2].rstrip("s"))
                takes.append(Take(ts, elapsed, audio, _parse_tags(parts[3]), parts[4]))
            elif len(parts) == 4:  # v1
                ts = datetime.fromisoformat(parts[0])
                audio = float(parts[1].rstrip("s"))
                takes.append(Take(ts, None, audio, _parse_tags(parts[2]), parts[3]))
        except ValueError:
            continue  # malformed line: skip, never crash the dashboard
    return takes


def _pct(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    i = min(int(len(sorted_vals) * pct), len(sorted_vals) - 1)
    return sorted_vals[i]


@dataclass
class Metrics:
    total_takes: int = 0
    failed_takes: int = 0
    total_words: int = 0
    total_audio_min: float = 0.0
    total_stt_time_s: float = 0.0
    avg_latency_s: float = 0.0
    p95_latency_s: float = 0.0
    max_latency_s: float = 0.0
    words_per_minute_speech: float = 0.0
    realtime_factor: float = 0.0  # audio seconds processed per second of STT
    takes_24h: int = 0
    takes_7d: int = 0
    by_day: dict[str, int] = field(default_factory=dict)
    tone_counts: dict[str, int] = field(default_factory=dict)
    tag_rate: float = 0.0  # share of takes that carried a tone tag


def compute(takes: list[Take]) -> Metrics:
    m = Metrics()
    m.total_takes = len(takes)
    now = datetime.now()
    ok = [t for t in takes if t.elapsed is not None]
    m.failed_takes = m.total_takes - len(ok)
    m.total_words = sum(t.words for t in takes)
    m.total_audio_min = sum(t.audio_s for t in takes) / 60.0
    lat = sorted(t.elapsed for t in ok)
    if lat:
        m.total_stt_time_s = sum(lat)
        m.avg_latency_s = sum(lat) / len(lat)
        m.p95_latency_s = _pct(lat, 0.95)
        m.max_latency_s = lat[-1]
    if m.total_audio_min > 0 and m.total_stt_time_s > 0:
        audio_s = m.total_audio_min * 60
        m.words_per_minute_speech = m.total_words / m.total_audio_min
        m.realtime_factor = audio_s / m.total_stt_time_s
    m.takes_24h = sum(1 for t in takes if (now - t.ts) < timedelta(hours=24))
    m.takes_7d = sum(1 for t in takes if (now - t.ts) < timedelta(days=7))
    for t in takes:
        m.by_day[t.ts.strftime("%m-%d")] = m.by_day.get(t.ts.strftime("%m-%d"), 0) + 1
        for tag in t.tags:
            key = tag.split(":")[-1].strip().split(",")[0].strip() or tag
            m.tone_counts[key] = m.tone_counts.get(key, 0) + 1
    tagged = sum(1 for t in takes if t.tags)
    m.tag_rate = tagged / m.total_takes if m.total_takes else 0.0
    return m
