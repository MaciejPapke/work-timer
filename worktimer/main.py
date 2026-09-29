"""Entry point: start the local server and tracker, then the tray icon."""
import argparse
import threading

from . import config, server, storage, tracker as tracker_mod, tray


def main():
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
