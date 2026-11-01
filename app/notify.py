import logging
import requests

log = logging.getLogger("notify")


def home_assistant(cfg, title, message):
    url = (cfg.get("home_assistant") or {}).get("webhook_url")
    if not url:
        return
    try:
        requests.post(url, json={"title": title, "message": message}, timeout=10)
    except Exception as e:
        log.warning("Home Assistant webhook failed: %s", e)
