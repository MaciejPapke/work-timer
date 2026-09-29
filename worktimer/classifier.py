"""Rules-based (and optional local-AI) classification of activity."""
from urllib.parse import urlparse

from . import config


def classify(app, url=None):
    app_l = (app or "").lower()
    if any(a in app_l for a in config.WORK_APPS):
        return config.WORK
    if any(a in app_l for a in config.LEISURE_APPS):
        return config.LEISURE
    if app_l in config.BROWSER_EXES:
        host = (urlparse(url).netloc or "").lower() if url else ""
        for d in config.LEISURE_DOMAINS:
            if d in host:
                return config.LEISURE
        for d in config.WORK_DOMAINS:
            if d in host:
                return config.WORK
        return config.NEUTRAL
    return config.NEUTRAL


def classify_idle():
    return config.IDLE


def llm_classify(app, url=None):
    """Ask a locally running model to classify an activity.

    Uses the Ollama /api/generate shape with a configurable model. Returns a
    category string, or None if no model is configured or the model is down.
    """
    if not config.MODEL:
        return None
    import json
    import urllib.request

    prompt = (
        "Classify this computer activity into exactly one word: work, leisure "
        f"or neutral. App: {app or '-'}. URL: {url or '-'}. "
        "Reply with only that one word."
    )
    payload = json.dumps({
        "model": config.MODEL,
        "prompt": prompt,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{config.OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return None
    word = (data.get("response") or "").strip().lower()
    for cat in (config.WORK, config.LEISURE, config.NEUTRAL):
        if cat in word:
            return cat
    return config.NEUTRAL
