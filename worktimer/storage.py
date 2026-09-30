"""Tiny SQLite layer. One local file, no network."""
import os
import sqlite3
import time

from . import config


def _connect():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init():
    conn = _connect()
    with conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS buckets (
                ts INTEGER NOT NULL,
                app TEXT NOT NULL,
                state TEXT NOT NULL,
                page TEXT,
                url TEXT,
                category TEXT NOT NULL,
                duration_ms INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_buckets_ts ON buckets(ts);
            CREATE TABLE IF NOT EXISTS classifications (
                key TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                ts INTEGER NOT NULL
            );
            """
        )
    conn.close()


def insert_buckets(rows):
    """rows: list of (app, state, page, url, category, duration_ms)."""
    if not rows:
        return
    ts = int(time.time())
    conn = _connect()
    with conn:
        conn.executemany(
            "INSERT INTO buckets(ts, app, state, page, url, category, duration_ms)"
            " VALUES (?,?,?,?,?,?,?)",
            [(ts, r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows],
        )
    conn.close()


def aggregate(since_ts, until_ts=None):
    sql = (
        "SELECT app, state, category, COALESCE(page, ''), COALESCE(url, ''),"
        " SUM(duration_ms) AS ms FROM buckets WHERE ts >= ?"
    )
    params = [since_ts]
    if until_ts is not None:
        sql += " AND ts < ?"
        params.append(until_ts)
    sql += " GROUP BY app, state, category, page, url ORDER BY ms DESC"
    conn = _connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def daily_totals(since_ts, until_ts):
    """Return (local_day_iso, category, ms) bucketed by calendar day."""
    conn = _connect()
    rows = conn.execute(
        "SELECT strftime('%Y-%m-%d', ts, 'unixepoch', 'localtime') AS d,"
        " category, SUM(duration_ms) AS ms"
        " FROM buckets WHERE ts >= ? AND ts < ? GROUP BY d, category",
        (since_ts, until_ts),
    ).fetchall()
    conn.close()
    return rows


def set_classification(key, category):
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO classifications(key, category, ts)"
            " VALUES (?,?,?)",
            (key, category, int(time.time())),
        )
    conn.close()


def get_classification(key):
    conn = _connect()
    row = conn.execute(
        "SELECT category FROM classifications WHERE key=?", (key,)
    ).fetchone()
    conn.close()
    return row[0] if row else None
