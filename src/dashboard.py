"""Local performance dashboard: stdlib http.server on 127.0.0.1, opened from
the tray. No dependencies, no CDN - one self-contained auto-refreshing page."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import stats

PORT_DEFAULT = 8417

_style = """
body{font-family:'Segoe UI',system-ui,sans-serif;background:#0f1419;color:#e6e6e6;
     margin:0;padding:24px;max-width:960px;margin-inline:auto}
h1{font-size:20px;margin:0 0 2px} .sub{color:#7f8c98;font-size:13px;margin-bottom:20px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;
       margin-bottom:24px}
.card{background:#161d24;border:1px solid #232d37;border-radius:10px;padding:14px}
.card .v{font-size:26px;font-weight:600;color:#4cc2ff}
.card .l{font-size:12px;color:#7f8c98;margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{color:#7f8c98;text-align:left;font-weight:500;padding:6px 8px;border-bottom:1px solid #232d37}
td{padding:6px 8px;border-bottom:1px solid #1a232c;max-width:480px;
   overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tag{color:#ffb454} .fail{color:#ff6b6b} .ok{color:#7ee787}
h2{font-size:14px;color:#9fb0bc;font-weight:600;margin:24px 0 8px;text-transform:
   uppercase;letter-spacing:.06em}
svg text{fill:#7f8c98;font-size:10px}
"""


def _cards(m: stats.Metrics, model: str, device: str, version: str) -> str:
    def card(v, l):
        return f'<div class="card"><div class="v">{v}</div><div class="l">{l}</div></div>'
    return "".join([
        card(m.total_takes, "takes"),
        card(m.total_words, "words dictated"),
        card(f"{m.avg_latency_s:.2f}s", "avg latency"),
        card(f"{m.p95_latency_s:.2f}s", "p95 latency"),
        card(f"{m.realtime_factor:.1f}x", "real-time factor"),
        card(f"{m.failed_takes}", "failed takes"),
        card(m.takes_24h, "takes (24h)"),
        card(f"{int(m.tag_rate * 100)}%", "takes with tone tags"),
        card(f"{model} · {device} · v{version}", "engine"),
    ])


def _bars(by_day: dict) -> str:
    if not by_day:
        return "<p class='sub'>No history yet. Dictate something.</p>"
    days = sorted(by_day.items())[-30:]
    mx = max(v for _, v in days) or 1
    n = len(days)
    bw, gap, h = min(28, 800 // max(n, 1)), 4, 90
    w = n * (bw + gap)
    parts = [f'<svg width="{w}" height="{h + 16}" xmlns="http://www.w3.org/2000/svg">']
    for i, (day, v) in enumerate(days):
        bh = int(v / mx * h)
        x = i * (bw + gap)
        parts.append(f'<rect x="{x}" y="{h - bh}" width="{bw}" height="{bh}" '
                     f'rx="3" fill="#4cc2ff" fill-opacity="0.85"/>')
        parts.append(f'<text x="{x}" y="{h + 12}">{day}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _recent(takes: list[stats.Take]) -> str:
    rows = []
    for t in takes[-20:][::-1]:
        tags = " ".join(f'<span class="tag">{x}</span>' for x in t.tags) or "<span class='ok'>calm</span>"
        lat = f"{t.elapsed:.2f}s" if t.elapsed is not None else '<span class="fail">FAIL</span>'
        rows.append(
            f"<tr><td>{t.ts.strftime('%H:%M:%S')}</td><td>{t.audio_s:.1f}s</td>"
            f"<td>{lat}</td><td>{tags}</td><td>{t.text or '-'}</td></tr>")
    return ("<table><tr><th>time</th><th>audio</th><th>latency</th>"
            "<th>tone</th><th>text</th></tr>" + "".join(rows) + "</table>")


def render_page(history_path: str, model="?", device="?", version="?") -> str:
    takes = stats.parse_history(history_path)
    m = stats.compute(takes)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="5">
<title>EmoDict performance</title><style>{_style}</style></head><body>
<h1>EmoDict performance</h1>
<div class="sub">local only - refreshes every 5s - {m.total_audio_min:.1f} minutes of
speech processed since install</div>
<div class="cards">{_cards(m, model, device, version)}</div>
<h2>Takes per day</h2>{_bars(m.by_day)}
<h2>Recent takes</h2>{_recent(takes)}
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    history_path = "history.log"
    info = ("?", "?", "?")

    def do_GET(self):  # noqa: N802 - http.server API
        try:
            body = render_page(self.history_path, *self.info).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:  # noqa: BLE001 - dashboard must never take the app down
            self.send_error(500)

    def log_message(self, *args):  # silence per-request console spam
        pass


_server: ThreadingHTTPServer | None = None
_lock = threading.Lock()


def ensure_running(history_path: str, port: int = PORT_DEFAULT,
                   model="?", device="?", version="?") -> str:
    """Start the server once (idempotent); return the URL."""
    global _server
    with _lock:
        if _server is None:
            _Handler.history_path = history_path
            _Handler.info = (model, device, version)
            _server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
            threading.Thread(target=_server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}"
