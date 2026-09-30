"""Sampling loop: attributes time to app/state pools and idle."""
import threading
import time
from collections import defaultdict

from . import classifier, config, storage, win32util


class Tracker:
    def __init__(self, page_state):
        self.page_state = page_state  # shared dict {exe: (url, title)} from server
        self._stop = threading.Event()
        self.paused = False
        self._acc = defaultdict(int)  # (app, state, page, url, category) -> ms

    def stop(self):
        self._stop.set()

    def _flush(self):
        rows = [
            (app, state, page, url, category, int(ms))
            for (app, state, page, url, category), ms in self._acc.items()
        ]
        self._acc.clear()
        storage.insert_buckets(rows)

    def _tick(self, seconds):
        ms = int(seconds * 1000)

        if win32util.idle_ms() >= config.IDLE_THRESHOLD_MS:
            app = win32util.foreground_exe() or "desktop"
            if app in config.IGNORE_EXES:
                app = "desktop"
            key = (app, config.IDLE, None, None, config.IDLE)
            self._acc[key] += ms
            return

        # Only ever count the active (foreground) app.
        app = win32util.foreground_exe()
        if not app or app in config.IGNORE_EXES:
            return

        page = url = None
        if app in config.BROWSER_EXES:
            entry = self.page_state.get(app)
            if entry:
                url, page = entry
        category = classifier.classify(app, url)
        key = (app, "focused", page, url, category)
        self._acc[key] += ms

    def run(self):
        prev = time.monotonic()
        last_flush = time.monotonic()
        while not self._stop.is_set():
            now = time.monotonic()
            elapsed = now - prev
            prev = now
            if not self.paused and elapsed > 0:
                # Cap catch-up after sleep/lock so a single long gap doesn't
                # dump a huge bucket.
                self._tick(min(elapsed, 5.0))
                if now - last_flush >= config.FLUSH_INTERVAL:
                    self._flush()
                    last_flush = now
            self._stop.wait(config.POLL_INTERVAL)
        self._flush()
