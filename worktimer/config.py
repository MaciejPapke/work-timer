"""Configuration for WorkTimer. All settings are local; nothing leaves this machine."""
import os
from pathlib import Path

VERSION = "1.0.0"

# Poll interval for window/idle sampling, in seconds.
POLL_INTERVAL = 1.0

# After this many milliseconds with no keyboard/mouse input, time is counted
# as "idle" rather than app time.
IDLE_THRESHOLD_MS = 2 * 60 * 1000  # 2 minutes

# How often accumulated in-memory buckets are flushed to SQLite, in seconds.
FLUSH_INTERVAL = 30

# Local loopback only. The companion browser extension reports here and the
# dashboard is served here. No other interface is ever opened.
HOST = "127.0.0.1"
PORT = int(os.environ.get("WORKTIMER_PORT", "8765"))

# Data is stored in a single SQLite file under your home directory.
DB_PATH = os.environ.get(
    "WORKTIMER_DB", str(Path.home() / ".worktimer" / "data.db")
)

# Executables treated as "the browser" for per-page attribution.
BROWSER_EXES = ("brave.exe", "chrome.exe", "msedge.exe", "firefox.exe")
# The exe the companion extension reports tabs for.
BROWSER_EXE = "brave.exe"

# Categories
WORK = "work"
LEISURE = "leisure"
NEUTRAL = "neutral"
IDLE = "idle"

# Higher wins when one app has several windows in different states.
STATE_PRIORITY = {"focused": 3, "visible": 2, "minimized": 1}

# --- Classification -------------------------------------------------------
# Substring matches on lowercase exe name / url hostname.
WORK_APPS = (
    "code.exe", "devenv.exe", "pycharm64.exe", "idea64.exe", "rider64.exe",
    "eclipse.exe", "studio64.exe", "webstorm64.exe", "sublime_text.exe",
    "notepad++.exe", "vim.exe", "nvim.exe", "postman.exe", "insomnia.exe",
    "dbeaver.exe", "ssms.exe", "outlook.exe", "excel.exe", "winword.exe",
    "powerpnt.exe", "onenote.exe", "teams.exe", "slack.exe", "zoom.exe",
    "notion.exe", "obsidian.exe", "wsl.exe", "windowsterminal.exe",
    "windows terminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
    "putty.exe", "mstsc.exe", "git-bash.exe",
)

LEISURE_APPS = (
    "spotify.exe", "steam.exe", "steamwebhelper.exe", "discord.exe",
    "vlc.exe", "epicgameslauncher.exe", "battle.net.exe", "minecraft.exe",
)

WORK_DOMAINS = (
    "github.com", "gitlab.com", "bitbucket.org", "stackoverflow.com",
    "atlassian.net", "jira", "confluence", "docs.google.com", "docs.",
    "learn.microsoft.com", "localhost", "127.0.0.1", "chatgpt.com",
    "claude.ai", "gemini.google.com", "perplexity.ai", "figma.com",
    "linear.app", "notion.so", "slack.com",
)

LEISURE_DOMAINS = (
    "youtube.com", "reddit.com", "twitter.com", "x.com", "facebook.com",
    "instagram.com", "tiktok.com", "netflix.com", "twitch.tv", "hulu.com",
    "disneyplus.com", "primevideo.com", "spotify.com", "9gag.com",
    "imgur.com",
)

# --- Optional local AI classification -------------------------------------
# Leave MODEL empty to disable. Set it to your locally running model (e.g.
# "laya", "llama3", "mistral") and point OLLAMA_URL at its API. Uses the
# Ollama /api/generate shape; most local runners are compatible or expose an
# OpenAI-compatible endpoint you can adapt here.
MODEL = os.environ.get("WORKTIMER_MODEL", "")
OLLAMA_URL = os.environ.get("WORKTIMER_OLLAMA_URL", "http://127.0.0.1:11434")
LLM_TIMEOUT = 20
