# WorkTimer

A private, local-first time tracker for Windows. It samples your active
windows in the background and pools your time per app and per page, so you can
see what you're actually spending your day on.

Everything stays on your machine. There is no cloud, no account, no telemetry,
and the only network traffic is a loopback connection between the app and a
small companion browser extension.

## What it tracks

- **Per-app time**, split by window state:
  - `focused` — the window you're actively using
  - `visible` — open on screen but not clicked
  - `minimized` — open but minimized
- **Idle time** — after 2 minutes with no keyboard/mouse input, time is
  counted as idle instead of app time.
- **Per-page time** in Brave (via the optional companion extension below).

Time is organized into pools per app, per state, and per page, then classified
as **work**, **leisure**, or **neutral** by a small local rules engine.

## How it works

1. A background process samples the foreground window and all visible windows
   once per second using the Win32 API.
2. It writes aggregated buckets to a single local SQLite file
   (`~/.worktimer/data.db`).
3. A localhost-only web dashboard shows your summary.

## Install & run

Requires Windows and Python 3.11+.

```powershell
pip install -r requirements.txt
python install.py            # one command: desktop shortcut + autostart + launch
python install.py --reset    # also clear tracked data first
python install.py --uninstall
```

`install.py` adds a desktop shortcut and a startup entry so WorkTimer launches
minimized (tray icon) when you log in. To run it manually instead:

```powershell
python -m worktimer.main            # foreground run (useful for a first check)
pythonw -m worktimer.main           # run without a console window
# or double-click start_hidden.vbs
```

Open the dashboard at <http://127.0.0.1:8765/> or from the tray icon
("Open dashboard").

## Companion browser extension (optional, for per-page data)

Per-page attribution needs a small extension loaded into Brave (or any
Chromium browser):

1. Open `brave://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked** and select the `extension/` folder in this repo.

The extension reports the active tab's title and URL to the local app over
`127.0.0.1` only. It has no cloud access and reports only your active tab.
Page data is only recorded while that browser is the focused window.

## Classification

`worktimer/config.py` holds editable rules mapping app names and domains to
work / leisure / neutral. Optionally set `MODEL` in `config.py` (or the
`WORKTIMER_MODEL` environment variable) to the name of a locally running model
and point `OLLAMA_URL` at its Ollama-compatible API to classify ambiguous
activity with a local model — no data leaves the machine.

## Privacy

- All data is stored in one SQLite file under your home directory.
- The app binds to `127.0.0.1` only and never connects to the internet.
- The companion extension talks only to `127.0.0.1`.
- No analytics, no telemetry, no accounts.

## Notes

- App/state time is tracked per window, so overlapping states (several windows
  visible at once) can sum to more than wall-clock time; idle time is
  exclusive.
- Sampling reads window titles and input-idle state locally, so it must run as
  your normal desktop user.

## License

MIT — see [LICENSE](LICENSE).
