"""System tray icon so the app can run minimized."""
import webbrowser

from . import config


def _make_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (64, 64), (30, 30, 60))
    d = ImageDraw.Draw(img)
    d.ellipse((12, 12, 52, 52), fill=(90, 200, 140))
    return img


def run(tracker, server):
    try:
        import pystray
    except ImportError:
        print("pystray not installed; running headless. Press Ctrl+C to stop.")
        return

    def open_dashboard():
        webbrowser.open(f"http://{config.HOST}:{config.PORT}/")

    def toggle_pause(icon, item):
        tracker.paused = not tracker.paused

    def quit_app(icon, item):
        tracker.stop()
        server.shutdown()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Open dashboard", lambda i, m: open_dashboard(), default=True),
        pystray.MenuItem("Pause / resume", toggle_pause, checked=lambda item: tracker.paused),
        pystray.MenuItem("Quit", quit_app),
    )
    icon = pystray.Icon("worktimer", _make_image(), "WorkTimer", menu)
    icon.run()
