"""Localhost-only HTTP server.

Receives active-tab reports from the companion browser extension and serves a
private dashboard. Binds to 127.0.0.1 only.
"""
import calendar as _cal
import json
import math
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import config, storage

PAGE_STATE = {}          # exe -> (url, title)
PAGE_LOCK = threading.Lock()

WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

CAT_ORDER = (config.WORK, config.LEISURE, config.IDLE, config.NEUTRAL)
CAT_LABEL = {
    config.WORK: "Work",
    config.LEISURE: "Leisure",
    config.IDLE: "Idle",
    config.NEUTRAL: "Neutral",
}
# Grayscale, bright -> dark, so the monochrome palette still distinguishes.
CAT_COLOR = {
    config.WORK: "#f4f4f4",
    config.LEISURE: "#9a9a9a",
    config.IDLE: "#3d3d3d",
    config.NEUTRAL: "#6f6f6f",
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

    cat = q.get("cat", [None])[0]
    if cat not in CAT_COLOR:
        cat = None
    return kind, start, end, label, cal_month, anchor, cat


def _period_href(anchor, kind, cat=None):
    if kind == "month":
        base = f"?m={anchor.strftime('%Y-%m')}"
    elif kind == "week":
        base = f"?w={anchor.strftime('%Y-%m-%d')}"
    else:
        base = f"?d={anchor.strftime('%Y-%m-%d')}"
    if cat:
        base += f"&cat={cat}"
    return base


def _daily_map(since, until):
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


# --- circular SVG helpers -------------------------------------------------

def _donut(segments, size=240, stroke=20, links=None):
    """segments: list of (color, ms). links: optional href per segment."""
    r = (size - stroke) / 2
    c = 2 * math.pi * r
    cx = cy = size / 2
    total = sum(v for _, v in segments) or 0
    parts = []
    if total <= 0:
        parts.append(
            f"<circle cx='{cx}' cy='{cy}' r='{r}' fill='none' stroke='#242424' "
            f"stroke-width='{stroke}'/>"
        )
    else:
        off = 0.0
        for i, (color, v) in enumerate(segments):
            frac = v / total
            dash = frac * c
            gap = c - dash
            circle = (
                f"<circle cx='{cx}' cy='{cy}' r='{r}' fill='none' stroke='{color}' "
                f"stroke-width='{stroke}' stroke-dasharray='{dash:.3f} {gap:.3f}' "
                f"stroke-dashoffset='{-off:.3f}' transform='rotate(-90 {cx} {cy})'/>"
            )
            if links and links[i]:
                circle = f"<a href='{links[i]}'>{circle}</a>"
            parts.append(circle)
            off += dash
    return (
        f"<svg width='{size}' height='{size}' viewBox='0 0 {size} {size}'>{''.join(parts)}</svg>"
    )


def _mini_ring(frac, size=36, stroke=5):
    r = (size - stroke) / 2
    c = 2 * math.pi * r
    dash = max(0.0, min(1.0, frac)) * c
    return (
        f"<svg width='{size}' height='{size}' viewBox='0 0 {size} {size}'>"
        f"<circle cx='{size/2}' cy='{size/2}' r='{r}' fill='none' stroke='#242424' stroke-width='{stroke}'/>"
        f"<circle cx='{size/2}' cy='{size/2}' r='{r}' fill='none' stroke='#eaeaea' stroke-width='{stroke}' "
        f"stroke-dasharray='{dash:.3f} {c - dash:.3f}' transform='rotate(-90 {size/2} {size/2})' "
        f"stroke-linecap='round'/>"
        f"</svg>"
    )


# --- sections -------------------------------------------------------------

def _calendar_html(cal_month, kind, anchor):
    today = date.today()
    first = date(cal_month.year, cal_month.month, 1)
    grid_start = first - timedelta(days=first.weekday())

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
        daymap = daily[key]
        total = sum(daymap.values())
        in_month = d.year == cal_month.year and d.month == cal_month.month
        top = max(daymap, key=daymap.get) if daymap else None
        dot = (
            f"<span class='dot' style='background:{CAT_COLOR[top]}'></span>"
            if top
            else "<span class='dot'></span>"
        )
        cls = "day"
        if not in_month:
            cls += " out"
        if key == highlight.strftime("%Y-%m-%d"):
            cls += " sel"
        if key == today.strftime("%Y-%m-%d"):
            cls += " today"
        text = _fmt_ms(total) if total else ""
        cells.append(
            f"<td class='{cls}'>"
            f"<a href='?d={key}'>"
            f"<span class='dn'>{d.day}</span>{dot}"
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


def _rows(since, until):
    return storage.aggregate(since, until)


def _cat_totals(rows):
    d = defaultdict(int)
    for _app, _state, cat, _page, _url, ms in rows:
        d[cat] += ms
    return d


def _app_totals(rows, cat=None):
    d = defaultdict(lambda: defaultdict(int))
    for app, state, c, _page, _url, ms in rows:
        if cat and c != cat:
            continue
        d[app][state] += ms
    return d


def _site_totals(rows, cat=None):
    d = defaultdict(int)
    for app, _state, c, _page, url, ms in rows:
        if cat and c != cat:
            continue
        if app.lower() in config.BROWSER_EXES and url:
            d[_site_label(url)] += ms
    return d


def _page_totals(rows, cat=None):
    d = defaultdict(int)
    for app, _state, c, page, url, ms in rows:
        if cat and c != cat:
            continue
        if page:
            d[(app, page, url)] += ms
    return d


def _legend_html(anchor, kind, cat_totals, active):
    chips = [f"<a class='chip{' on' if active is None else ''}' href='{_period_href(anchor, kind)}'>All</a>"]
    for c in CAT_ORDER:
        ms = cat_totals.get(c, 0)
        if not ms and active != c:
            continue
        cls = "chip on" if active == c else "chip"
        chips.append(
            f"<a class='{cls}' href='{_period_href(anchor, kind, c)}'>"
            f"<span class='dot' style='background:{CAT_COLOR[c]}'></span>"
            f"{CAT_LABEL[c]} <span class='muted'>{_fmt_ms(ms)}</span></a>"
        )
    return f"<div class='legend'>{''.join(chips)}</div>"


def _apps_html(rows, cat=None):
    apps = _app_totals(rows, cat)
    grand = sum(sum(s.values()) for s in apps.values()) or 1
    items = []
    for app, states in sorted(apps.items(), key=lambda kv: -sum(kv[1].values())):
        total = sum(states.values())
        frac = total / grand
        state_rows = "".join(
            f"<div class='state'><span class='k'>{s}</span>"
            f"<span class='bar'><span style='width:{100 * states.get(s, 0) / total:.1f}%'></span></span>"
            f"<span class='v'>{_fmt_ms(states.get(s, 0))}</span></div>"
            for s in ("focused", "visible", "minimized", "idle")
            if total
        )
        items.append(
            f"<details class='app'>"
            f"<summary><span class='ring'>{_mini_ring(frac)}</span>"
            f"<span class='name'>{_escape(_app_name(app))}</span>"
            f"<span class='time'>{_fmt_ms(total)}</span></summary>"
            f"<div class='states'>{state_rows}</div></details>"
        )
    return f"<section><h3>Apps</h3>{''.join(items)}</section>"


def _sites_html(rows, cat=None):
    sites = _site_totals(rows, cat)
    grand = sum(sites.values()) or 1
    items = "".join(
        f"<div class='row'><span class='name'>{_escape(s)}</span>"
        f"<span class='bar'><span style='width:{100 * v / grand:.1f}%'></span></span>"
        f"<span class='time'>{_fmt_ms(v)}</span></div>"
        for s, v in sorted(sites.items(), key=lambda kv: -kv[1])[:25]
    )
    return f"<section><h3>Sites</h3>{items}</section>" if items else ""


def _pages_html(rows, cat=None):
    pages = _page_totals(rows, cat)
    items = "".join(
        f"<div class='row page'><span class='name'>{_escape(p)}</span>"
        f"<span class='sub'>{_escape(_site_label(u))}</span>"
        f"<span class='time'>{_fmt_ms(v)}</span></div>"
        for (a, p, u), v in sorted(pages.items(), key=lambda kv: -kv[1])[:40]
    )
    return f"<section><h3>Pages</h3>{items}</section>" if items else ""


_CSS = """
* { box-sizing: border-box; }
body {
  margin: 0; padding: 32px 20px 80px;
  background: #0a0a0a; color: #ededed;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 680px; margin: 0 auto; }
.brand { text-align: center; margin: 8px 0 4px; }
.brand h1 { font-size: 1.05rem; letter-spacing: .42em; font-weight: 600; margin: 0; text-transform: uppercase; }
.brand .sub { color: #6b6b6b; font-size: .75rem; letter-spacing: .18em; text-transform: uppercase; margin-top: 6px; }
a { color: inherit; text-decoration: none; }

.tabs { display: flex; justify-content: center; gap: 8px; margin: 22px 0 10px; }
.tab { padding: 7px 18px; border: 1px solid #2a2a2a; border-radius: 999px;
       color: #9a9a9a; font-size: .82rem; letter-spacing: .04em; transition: all .15s; }
.tab:hover { border-color: #555; color: #e5e5e5; }
.tab.on { background: #ededed; color: #0a0a0a; border-color: #ededed; font-weight: 600; }

.cal { margin: 8px auto 0; text-align: center; }
.cal-nav { display: flex; justify-content: space-between; align-items: center; max-width: 320px; margin: 0 auto 8px; }
.cal-title { font-size: .82rem; letter-spacing: .16em; text-transform: uppercase; color: #bdbdbd; }
.nav { width: 32px; height: 32px; line-height: 30px; border: 1px solid #2a2a2a; border-radius: 50%;
       color: #9a9a9a; font-size: 1rem; transition: all .15s; }
.nav:hover { border-color: #ededed; color: #ededed; }
table.cal { margin: 0 auto; border-collapse: separate; border-spacing: 4px; }
table.cal th { border: none; color: #555; font-weight: 500; font-size: .68rem;
               letter-spacing: .12em; text-transform: uppercase; padding: 2px 0 6px; }
table.cal td { border: none; padding: 0; }
.day { width: 56px; height: 60px; }
.day a { display: flex; flex-direction: column; align-items: center; justify-content: flex-start;
         height: 100%; border-radius: 14px; padding: 6px 2px; border: 1px solid transparent; transition: all .15s; }
.day .dn { font-size: .8rem; color: #d6d6d6; }
.day .dot { width: 5px; height: 5px; border-radius: 50%; margin: 4px 0 2px; background: #2a2a2a; }
.day .dt { font-size: .6rem; color: #6b6b6b; }
.day.out .dn { color: #3a3a3a; }
.day.out .dt { color: #333; }
.day a:hover { border-color: #3a3a3a; }
.day.sel a { border-color: #ededed; }
.day.today .dn { color: #ffffff; font-weight: 700; }

.hero { text-align: center; margin: 30px 0 4px; }
.ring-wrap { position: relative; width: 240px; height: 240px; margin: 0 auto; }
.ring-wrap svg { display: block; }
.ring-wrap a circle { cursor: pointer; transition: opacity .15s; }
.ring-wrap a:hover circle { opacity: .75; }
.ring-center { position: absolute; inset: 0; display: flex; flex-direction: column;
               align-items: center; justify-content: center; pointer-events: none; }
.rc-time { font-size: 1.9rem; font-weight: 300; letter-spacing: .02em; }
.rc-label { color: #6b6b6b; font-size: .72rem; letter-spacing: .14em; text-transform: uppercase; margin-top: 4px; }
.split { display: flex; justify-content: center; gap: 8px; margin-top: 14px; }
.chip { display: inline-flex; align-items: center; gap: 7px; padding: 6px 13px;
        border: 1px solid #2a2a2a; border-radius: 999px; color: #bdbdbd; font-size: .78rem; }
.chip .dot { width: 8px; height: 8px; border-radius: 50%; }
.chip.on { border-color: #ededed; color: #0a0a0a; background: #ededed; font-weight: 600; }
.chip.on .dot { outline: 1px solid #0a0a0a; }
.chip .muted { color: #7a7a7a; }
.chip.on .muted { color: #3a3a3a; }

.legend { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin: 22px 0 8px; }

section { margin: 30px 0; }
h3 { font-size: .72rem; letter-spacing: .2em; text-transform: uppercase; color: #6b6b6b;
     font-weight: 500; margin: 0 0 12px; text-align: center; }

.app { border: 1px solid #202020; border-radius: 16px; margin-bottom: 8px; background: #101010; overflow: hidden; }
.app summary { display: flex; align-items: center; gap: 14px; padding: 14px 18px; cursor: pointer; list-style: none; }
.app summary::-webkit-details-marker { display: none; }
.app .ring { flex: 0 0 auto; display: flex; }
.app .name { flex: 1; font-size: .95rem; }
.app .time { color: #bdbdbd; font-variant-numeric: tabular-nums; font-size: .9rem; }
.app summary::after { content: "+"; color: #6b6b6b; font-weight: 300; font-size: 1.1rem; }
.app[open] summary::after { content: "–"; }
.states { padding: 4px 18px 16px 66px; border-top: 1px solid #1c1c1c; }
.state { display: flex; align-items: center; gap: 10px; padding: 5px 0; font-size: .8rem; }
.state .k { width: 74px; color: #9a9a9a; text-transform: capitalize; }
.state .v { width: 64px; text-align: right; color: #bdbdbd; font-variant-numeric: tabular-nums; }
.bar { flex: 1; height: 4px; border-radius: 2px; background: #222; overflow: hidden; }
.bar span { display: block; height: 100%; background: #eaeaea; border-radius: 2px; }

.row { display: flex; align-items: center; gap: 12px; padding: 10px 14px;
       border-bottom: 1px solid #1c1c1c; font-size: .88rem; }
.row:last-child { border-bottom: none; }
.row .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row .sub { color: #6b6b6b; font-size: .74rem; }
.row .time { color: #bdbdbd; font-variant-numeric: tabular-nums; }
.row.page .name { font-weight: 500; }
.row.page .sub { flex: 0 0 auto; }
.row .bar { flex: 0 0 120px; }
section .row { border: 1px solid #202020; border-radius: 12px; margin-bottom: 6px; background: #101010; }

.footer { text-align: center; color: #4a4a4a; font-size: .7rem; letter-spacing: .08em;
          margin-top: 48px; text-transform: uppercase; }
"""


def _dashboard_html(path):
    kind, start, end, label, cal_month, anchor, cat = _period_from_query(path)
    since, until = _ts(start), _ts(end)
    daily = _daily_map(since, until)
    wd, we = _weekday_weekend(start, end, daily)
    total = sum(ms for cats in daily.values() for ms in cats.values())

    rows = _rows(since, until)
    cat_totals = _cat_totals(rows)
    present = [c for c in CAT_ORDER if cat_totals.get(c, 0) > 0]
    segments = [(CAT_COLOR[c], cat_totals[c]) for c in present]
    links = [_period_href(anchor, kind, c) for c in present]

    tabs = "".join(
        f"<a class='tab{' on' if k == kind else ''}' href='{_period_href(anchor, k, cat)}'>{name}</a>"
        for name, k in (("Day", "day"), ("Week", "week"), ("Month", "month"))
    )

    calendar = _calendar_html(cal_month, kind, anchor)
    legend = _legend_html(anchor, kind, cat_totals, cat)
    apps = _apps_html(rows, cat)
    sites = _sites_html(rows, cat)
    pages = _pages_html(rows, cat)

    body = f"""
<div class='wrap'>
  <div class='brand'><h1>WorkTimer</h1><div class='sub'>private &middot; local only</div></div>
  <div class='tabs'>{tabs}</div>
  {calendar}
  <div class='hero'>
    <div class='ring-wrap'>
      {_donut(segments, links=links)}
      <div class='ring-center'><span class='rc-time'>{_fmt_ms(total)}</span><span class='rc-label'>{label}</span></div>
    </div>
    <div class='split'>
      <span class='chip'><span class='dot' style='background:#f4f4f4'></span>Weekdays {_fmt_ms(wd)}</span>
      <span class='chip'><span class='dot' style='background:#3d3d3d'></span>Weekends {_fmt_ms(we)}</span>
    </div>
  </div>
  {legend}
  {apps}
  {sites}
  {pages}
  <div class='footer'>all data stays on this device</div>
</div>"""

    return f"<!doctype html>\n<html><head><meta charset='utf-8'>" \
           f"<meta name='viewport' content='width=device-width, initial-scale=1'>" \
           f"<title>WorkTimer</title><style>{_CSS}</style></head><body>{body}</body></html>"


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
