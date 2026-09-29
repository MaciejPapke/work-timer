"""Entry point: start the local server and tracker, then the tray icon."""
import argparse
import ctypes
import threading

from . import config, server, storage, tracker as tracker_mod, tray

_MUTEX_NAME = "Local\\WorkTimer.SingleInstance"
_mutex = None


def _already_running():
    """Return True if another WorkTimer instance is already tracking."""
    global _mutex
    kernel32 = ctypes.windll.kernel32
    _mutex = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    return kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def main():
    if _already_running():
        return  # one instance only; prevents double-counting

    ap = argparse.ArgumentParser(prog="worktimer", description="Private local activity tracker")
    ap.add_argument("--headless", action="store_true", help="run without a tray icon")
    args = ap.parse_args()

    storage.init()
    srv = server.start()

    tr = tracker_mod.Tracker(server.PAGE_STATE)
    threading.Thread(target=tr.run, daemon=True).start()

    if args.headless:
        print(f"Running headless. Dashboard: http://{config.HOST}:{config.PORT}/")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        tr.stop()
        srv.shutdown()
    else:
        tray.run(tr, srv)


if __name__ == "__main__":
    main()
