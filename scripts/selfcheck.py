"""Runnable self-check. Run: python scripts/selfcheck.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from worktimer import classifier, config, storage


def main():
    # Rules engine
    assert classifier.classify("Code.exe") == "work"
    assert classifier.classify("spotify.exe") == "leisure"
    assert classifier.classify("brave.exe", "https://www.youtube.com/watch?v=x") == "leisure"
    assert classifier.classify("brave.exe", "https://github.com/maciejpapke") == "work"
    assert classifier.classify("brave.exe", "https://example.com/") == "neutral"
    assert classifier.classify("unknownapp.exe") == "neutral"
    assert classifier.classify_idle() == "idle"

    # State priority and idle threshold
    assert config.STATE_PRIORITY["focused"] > config.STATE_PRIORITY["visible"] > config.STATE_PRIORITY["minimized"]
    assert config.IDLE_THRESHOLD_MS == 120000

    # Storage round-trip (temp db)
    tmp = os.path.join(os.environ.get("TEMP", "/tmp"), "worktimer_selfcheck.db")
    if os.path.exists(tmp):
        os.remove(tmp)
    config.DB_PATH = tmp
    storage.init()
    storage.insert_buckets([("Code.exe", "focused", None, None, "work", 60000)])
    rows = storage.aggregate(0)
    assert any(r[0] == "Code.exe" and r[5] == 60000 for r in rows), rows
    os.remove(tmp)

    # Live sample (optional; requires pywin32)
    try:
        from worktimer import win32util
        print(f"foreground exe : {win32util.foreground_exe()}")
        print(f"idle ms        : {win32util.idle_ms()}")
        print(f"top-level wins : {len(win32util.enumerate_states())}")
    except ImportError:
        print("pywin32 not installed; skipped live window sample.")

    print("selfcheck OK")


if __name__ == "__main__":
    main()
