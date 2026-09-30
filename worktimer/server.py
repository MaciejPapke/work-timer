"""Localhost-only HTTP server.

Receives active-tab reports from the companion browser extension and serves a
private dashboard. Binds to 127.0.0.1 only.
"""
import calendar as _cal
import json
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import config, storage

PAGE_STATE = {}          # exe -> (url, title)
PAGE_LOCK = threading.Lock()

WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# Category -> CSS class used to tint calendar cells.
CAT_CLASS = {
    config.WORK: "work",
    config.LEISURE: "leisure",
    config.IDLE: "idle",
    config.NEUTRAL: "neutral",
}


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


def _app_name(exe):
    exe_l = (exe or "").lower()
    for key, label in config.APP_NAMES.items():
        if key in exe_l:
            return label
    return exe or "?"


def _site_label(url):
    if not url:
        return ""
    host = (urlparse(url).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (urlparse(url).path or "").lower()
    for domain, label in config.SITE_LABELS.items():
        if host == domain or host.endswith("." + domain):
            if label == "Facebook" and "/messages" in path:
                return "Messenger"
            return label
    return host


# --- date helpers ---------------------------------------------------------

def _days_in_month(y, m):
    return _cal.monthrange(y, m)[1]


def _add_months(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, _days_in_month(y, m)))


def _ts(d):
    return int(datetime(d.year, d.month, d.day).timestamp())


def _period_from_query(path):
    q = parse_qs(urlparse(path).query)
    today = date.today()
    if "m" in q:
        y, mo = q["m"][0].split("-")
        anchor = date(int(y), int(mo), 1)
        kind = "month"
    elif "w" in q:
        anchor = date.fromisoformat(q["w"][0])
        kind = "week"
    elif "d" in q:
        anchor = date.fromisoformat(q["d"][0])
        kind = "day"
    else:
        anchor = today
        kind = "day"

    if kind == "month":
        start = date(anchor.year, anchor.month, 1)
        end = _add_months(start, 1)
        label = start.strftime("%B %Y")
        cal_month = start
    elif kind == "week":
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=7)
        label = f"{start.strftime('%b %d')} – {(end - timedelta(days=1)).strftime('%b %d, %Y')}"
        cal_month = anchor
    else:
        start = anchor
        end = anchor + timedelta(days=1)
        label = anchor.strftime("%A, %B %d, %Y")
        cal_month = anchor
    return kind, start, end, label, cal_month, anchor


def _daily_map(since, until):
    """date-iso -> {category: ms}."""
    out = defaultdict(lambda: defaultdict(int))
    for day, cat, ms in storage.daily_totals(since, until):
        out[day][cat] += ms
    return out


def _weekday_weekend(start, end, daily):
    wd = we = 0
    d = start
    while d < end:
        total = sum(daily[d.strftime("%Y-%m-%d")].values())
        if d.weekday() >= 5:
            we += total
        else:
            wd += total
        d += timedelta(days=1)
    return wd, we


def _calendar_html(cal_month, kind, anchor):
    today = date.today()
    first = date(cal_month.year, cal_month.month, 1)
    grid_start = first - timedelta(days=first.weekday())  # back to Monday

    if kind == "month":
        prev_link = f"?m={_add_months(cal_month, -1).strftime('%Y-%m')}"
        next_link = f"?m={_add_months(cal_month, 1).strftime('%Y-%m')}"
    elif kind == "week":
        prev_link = f"?w={_add_months(anchor, -1).strftime('%Y-%m-%d')}"
        next_link = f"?w={_add_months(anchor, 1).strftime('%Y-%m-%d')}"
    else:
        prev_link = f"?d={_add_months(anchor, -1).strftime('%Y-%m-%d')}"
        next_link = f"?d={_add_months(anchor, 1).strftime('%Y-%m-%d')}"

    since = _ts(grid_start)
    until = _ts(grid_start + timedelta(days=42))
    daily = _daily_map(since, until)
    highlight = today if kind == "month" else anchor

    cells = []
    for i in range(42):
        d = grid_start + timedelta(days=i)
        key = d.strftime("%Y-%m-%d")
        total = sum(daily[key].values())
        in_month = d.year == cal_month.year and d.month == cal_month.month
        cls = "day"
        if not in_month:
            cls += " out"
        if key == highlight.strftime("%Y-%m-%d"):
            cls += " sel"
        if key == today.strftime("%Y-%m-%d"):
            cls += " today"
        cat = CAT_CLASS.get(max(daily[key], key=daily[key].get), "") if daily[key] else ""
        text = _fmt_ms(total) if total else ""
        cells.append(
            f"<td class='{cls} cat-{cat}'>"
            f"<a href='?d={key}'><span class='dn'>{d.day}</span>"
            f"<span class='dt'>{text}</span></a></td>"
        )

    rows = "".join(
        "<tr>" + "".join(cells[r * 7:(r + 1) * 7]) + "</tr>" for r in range(6)
    )
    header = "".join(f"<th>{w}</th>" for w in WEEKDAY_NAMES)
    return (
        f"<div class='cal'><div class='cal-nav'>"
        f"<a class='nav' href='{prev_link}'>&#8592;</a>"
        f"<span class='cal-title'>{cal_month.strftime('%B %Y')}</span>"
        f"<a class='nav' href='{next_link}'>&#8594;</a></div>"
        f"<table class='cal'><tr>{header}</tr>{rows}</table></div>"
    )


def _period_tables(since, until):
    rows = storage.aggregate(since, until)

    by_cat = defaultdict(int)
    by_app = defaultdict(lambda: defaultdict(int))
    by_site = defaultdict(int)
    pages = defaultdict(int)
    for app, state, cat, page, url, ms in rows:
        by_cat[cat] += ms
        by_app[app][state] += ms
        if app.lower() in config.BROWSER_EXES and url:
            by_site[_site_label(url)] += ms
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
            f"<tr><td>{_escape(_app_name(app))}</td>"
            f"<td class='num'>{_fmt_ms(total)}</td>{cells}</tr>"
        )

    site_rows = "".join(
        f"<tr><td>{_escape(s)}</td><td class='num'>{_fmt_ms(v)}</td></tr>"
        for s, v in sorted(by_site.items(), key=lambda kv: -kv[1])[:25]
    )

    page_rows = "".join(
        f"<tr><td>{_escape(_app_name(a))}</td><td>{_escape(_site_label(u))}</td>"
        f"<td>{_escape(p)}</td><td class='mono'>{_escape(u)}</td>"
        f"<td class='num'>{_fmt_ms(v)}</td></tr>"
        for (a, p, u), v in sorted(pages.items(), key=lambda kv: -kv[1])[:50]
    )

    return f"""<h2>By category</h2>
<table><tr><th>Category</th><th>Time</th></tr>{cat_rows}</table>
<h2>By app</h2>
<table><tr><th>App</th><th>Total</th><th>Focused</th><th>Visible</th><th>Minimized</th><th>Idle</th></tr>{''.join(app_rows)}</table>
<h2>Browser sites</h2>
<table><tr><th>Site</th><th>Time</th></tr>{site_rows}</table>
<h2>Top pages</h2>
<table><tr><th>App</th><th>Site</th><th>Page</th><th>URL</th><th>Time</th></tr>{page_rows}</table>"""


def _dashboard_html(path):
    kind, start, end, label, cal_month, anchor = _period_from_query(path)
    since, until = _ts(start), _ts(end)
    daily = _daily_map(since, until)
    wd, we = _weekday_weekend(start, end, daily)
    total = sum(ms for cats in daily.values() for ms in cats.values())

    tabs = "".join(
        f"<a class='tab{' on' if k == kind else ''}' href='{href}'>{name}</a>"
        for name, href, k in (
            ("Day", f"?d={anchor.strftime('%Y-%m-%d')}", "day"),
            ("Week", f"?w={anchor.strftime('%Y-%m-%d')}", "week"),
            ("Month", f"?m={anchor.strftime('%Y-%m')}", "month"),
        )
    )

    calendar = _calendar_html(cal_month, kind, anchor)
    period = _period_tables(since, until)

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>WorkTimer</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 2rem; color:#111; background:#fafafa; }}
 h1 {{ font-size:1.4rem; margin-bottom:0; }}
 .sub {{ color:#666; margin:.25rem 0 1rem; }}
 .tabs {{ margin: .5rem 0; }}
 .tab {{ display:inline-block; padding:4px 14px; margin-right:6px; border:1px solid #ccc;
        border-radius:999px; text-decoration:none; color:#333; background:#fff; }}
 .tab.on {{ background:#2563eb; color:#fff; border-color:#2563eb; }}
 .split {{ margin: .75rem 0 1rem; display:flex; gap:1rem; }}
 .split span {{ padding:6px 12px; border-radius:8px; font-size:.9rem; }}
 .wd {{ background:#e0e7ff; color:#3730a3; }}
 .we {{ background:#fef3c7; color:#92400e; }}
 .total {{ color:#444; margin:.25rem 0; }}
 table {{ border-collapse: collapse; margin:1rem 0; min-width:520px; background:#fff; }}
 th, td {{ border:1px solid #ddd; padding:6px 10px; text-align:left; }}
 th {{ background:#f0f0f0; }}
 .num {{ text-align:right; font-variant-numeric: tabular-nums; }}
 .mono {{ font-family: ui-monospace, monospace; font-size:0.85rem; color:#555; max-width:40em; word-break:break-all; }}
 .cal {{ display:inline-block; background:#fff; border:1px solid #ddd; border-radius:10px; padding:10px; }}
 .cal-nav {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; }}
 .cal-title {{ font-weight:600; }}
 .nav {{ text-decoration:none; padding:0 8px; color:#2563eb; font-size:1.1rem; }}
 table.cal {{ border:none; margin:0; min-width:0; background:none; }}
 table.cal th {{ background:none; border:none; font-weight:500; color:#888; font-size:.8rem; text-align:center; padding:2px 6px; }}
 table.cal td {{ border:none; padding:2px; }}
 .day {{ width:56px; height:52px; vertical-align:top; text-align:right; }}
 .day a {{ display:block; padding:4px 6px; border-radius:8px; text-decoration:none; color:#111; height:100%; }}
 .day .dn {{ display:block; font-size:.85rem; }}
 .day .dt {{ display:block; font-size:.62rem; color:#666; }}
 .day.out .dn {{ color:#c0c0c0; }}
 .day.sel a {{ outline:2px solid #2563eb; }}
 .day.today .dn {{ font-weight:700; color:#2563eb; }}
 .day.cat-work a {{ background:#dcfce7; }}
 .day.cat-leisure a {{ background:#ffedd5; }}
 .day.cat-idle a {{ background:#f3f4f6; }}
 .day.cat-neutral a {{ background:#dbeafe; }}
</style></head><body>
<h1>WorkTimer</h1>
<div class='sub'>Private, local-only. Nothing leaves this device.</div>
<div class='tabs'>{tabs}</div>
{calendar}
<div class='split'><span class='wd'>Weekdays (Mon–Fri): {_fmt_ms(wd)}</span><span class='we'>Weekends (Sat–Sun): {_fmt_ms(we)}</span></div>
<div class='total'>Total {label}: <b>{_fmt_ms(total)}</b></div>
{period}
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] not in ("/", "/index.html"):
            self.send_response(404)
            self.end_headers()
            return
        body = _dashboard_html(self.path).encode()
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