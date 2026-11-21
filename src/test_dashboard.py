"""Dashboard verification: stats parser on synthetic history (v2, v1, FAIL,
malformed lines), metrics math, and a live HTTP fetch of the rendered page.
Run: python -m src.test_dashboard"""
import sys
import tempfile
import urllib.request
from pathlib import Path

from src import dashboard, stats

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


# 1. synthetic history: 3 good v2 takes, 1 FAIL, 1 old v1 line, 1 garbage line
tmp = Path(tempfile.mkdtemp()) / "history.log"
tmp.write_text(
    "2026-11-21T10:00:00 | 0.60 | 1.2 | ['happy'] | Hello world from EmoDict\n"
    "2026-11-21T10:05:00 | 0.80 | 2.4 | [] | Second take with more words here\n"
    "2026-11-21T10:10:00 | 1.40 | 5.0 | [] | Third take\n"
    "2026-11-21T10:15:00 | FAIL | 0.4 | [] | \n"
    "2026-11-20T09:00:00 | 3.4s | [] | old format line\n"
    "this line is garbage\n",
    encoding="utf-8")
takes = stats.parse_history(tmp)
check("parse: 5 valid takes, 1 garbage skipped", len(takes) == 5, f"got {len(takes)}")
check("v2 take parses elapsed", takes[0].elapsed == 0.60)
check("FAIL take has elapsed None", takes[3].elapsed is None)
check("v1 line tolerated (elapsed None)", takes[4].elapsed is None and takes[4].audio_s == 3.4)

m = stats.compute(takes)
check("total_takes", m.total_takes == 5)
check("failed_takes", m.failed_takes == 2, f"got {m.failed_takes}")
lat_ok = [0.60, 0.80, 1.40]
check("avg_latency", abs(m.avg_latency_s - sum(lat_ok) / 3) < 1e-9,
      f"{m.avg_latency_s:.3f}")
check("p95 == max of 3", m.p95_latency_s == 1.40)
check("tone tag counted", m.tone_counts.get("happy") == 1)
check("tag_rate", abs(m.tag_rate - 0.2) < 1e-9, f"{m.tag_rate}")
check("realtime_factor positive", m.realtime_factor > 0,
      f"{m.realtime_factor:.2f}x")

# 2. live server: render over HTTP and sanity-check the page
url = dashboard.ensure_running(str(tmp), port=8417,
                               model="test-model", device="cpu", version="9.9")
with urllib.request.urlopen(url, timeout=5) as r:
    html = r.read().decode("utf-8")
check("http 200 page served", "EmoDict performance" in html)
check("cards show totals", ">5<" in html and "words dictated" in html)
check("p95 rendered", "p95 latency" in html)
check("engine line", "test-model" in html and "v9.9" in html)
check("recent table has FAIL row", "FAIL" in html)
check("tone tag rendered", "happy" in html)

fails = sum(1 for _, ok, _ in results if not ok)
for n, ok, d in results:
    print(f"{'PASS' if ok else 'FAIL'}  {n}" + (f"  [{d}]" if d else ""))
print(f"\n{len(results)-fails}/{len(results)} passed")
sys.exit(1 if fails else 0)
