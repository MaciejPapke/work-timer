"""Localhost-only HTTP server.

Receives active-tab reports from the companion browser extension and serves a
private dashboard. Binds to 127.0.0.1 only.
"""
import json
import threading
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import config, storage

PAGE_STATE = {}          # exe -> (url, title)
PAGE_LOCK = threading.Lock()

DAYS = 7


def set_page(exe, url, title):
    with PAGE_LOCK:
        PAGE_STATE[exe] = (url, title)


def _escape(s):
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _fmt_ms(ms):
    s = int(ms / 1000)
    h, rem = divmod(s, 3600)
    m, s2 = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s2:02d}s"
    return f"{s2}s"


def _dashboard_html(since_ts):
    rows = storage.aggregate(since_ts)

    by_cat = defaultdict(int)
    by_app = defaultdict(lambda: defaultdict(int))
    pages = defaultdict(int)
    for app, state, cat, page, url, ms in rows:
        by_cat[cat] += ms
        by_app[app][state] += ms
        if page:
            pages[(app, page, url)] += ms

    cat_rows = "".join(
        f"<tr><td>{_escape(c)}</td><td class='num'>{_fmt_ms(v)}</td></tr>"
        for c, v in sorted(by_cat.items(), key=lambda kv: -kv[1])
    )

    app_rows = []
    for app, states in sorted(by_app.items(), key=lambda kv: -sum(kv[1].values())):
        total = sum(states.values())
        cells = "".join(
            f"<td class='num'>{_fmt_ms(states.get(s, 0))}</td>"
            for s in ("focused", "visible", "minimized", "idle")
        )
        app_rows.append(
            f"<tr><td>{_escape(app)}</td><td class='num'>{_fmt_ms(total)}</td>"
            f"{cells}</tr>"
        )
    app_rows = "".join(app_rows)

    page_rows = "".join(
        f"<tr><td>{_escape(a)}</td><td>{_escape(p)}</td>"
        f"<td class='mono'>{_escape(u)}</td><td class='num'>{_fmt_ms(v)}</td></tr>"
        for (a, p, u), v in sorted(pages.items(), key=lambda kv: -kv[1])[:50]
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>WorkTimer</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 2rem; color:#111; background:#fafafa; }}
 h1 {{ font-size:1.4rem; }}
 table {{ border-collapse: collapse; margin:1rem 0; min-width:520px; background:#fff; }}
 th, td {{ border:1px solid #ddd; padding:6px 10px; text-align:left; }}
 th {{ background:#f0f0f0; }}
 .num {{ text-align:right; font-variant-numeric: tabular-nums; }}
 .mono {{ font-family: ui-monospace, monospace; font-size:0.85rem; color:#555; max-width:40em; word-break:break-all; }}
</style></head><body>
<h1>WorkTimer</h1>
<p>Private, local-only activity summary for the last {DAYS} days. Data never leaves this device.</p>
<h2>By category</h2>
<table><tr><th>Category</th><th>Time</th></tr>{cat_rows}</table>
<h2>By app</h2>
<table><tr><th>App</th><th>Total</th><th>Focused</th><th>Visible</th><th>Minimized</th><th>Idle</th></tr>{app_rows}</table>
<h2>Top pages</h2>
<table><tr><th>App</th><th>Page</th><th>URL</th><th>Time</th></tr>{page_rows}</table>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_response(404)
            self.end_headers()
            return
        since = int(time.time()) - DAYS * 86400
        body = _dashboard_html(since).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/report":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            data = {}
        url = data.get("url", "")
        title = data.get("title", "")
        # Never record private sessions or non-web URLs.
        if data.get("incognito") or not urlparse(url).netloc:
            self.send_response(204)
            self.end_headers()
            return
        set_page(config.BROWSER_EXE, url, title)
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass  # silence request logging


def start():
    storage.init()
    server = ThreadingHTTPServer((config.HOST, config.PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
