"""Entry point: python -m app — runs the scheduler and the dashboard."""
import logging
import os
import shutil
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml

from . import db, engine, radar, web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("main")


def load_config():
    path = os.environ.get("MARKET_AGENT_CONFIG", "/data/config.yaml")
    if not os.path.exists(path):  # first start: drop an editable copy next to the database
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.copy(os.path.join(os.path.dirname(__file__), "default_config.yaml"), path)
        log.info("Wrote default config to %s", path)
    with open(path) as f:
        return yaml.safe_load(f) or {}


def safe(fn, *a):
    try:
        fn(*a)
    except Exception as e:
        log.exception("job failed")
        engine.event("error", f"{fn.__module__}.{fn.__name__} failed: {e}")


def scheduler(cfg):
    tz = ZoneInfo(cfg.get("timezone", "America/Toronto"))
    radar_every = cfg.get("radar", {}).get("every_minutes", 60) * 60
    radar_on = cfg.get("radar", {}).get("enabled", True)

    # First start: fill everything so the dashboard isn't empty.
    if not db.query("SELECT 1 FROM backtests LIMIT 1") or not db.query("SELECT 1 FROM odds LIMIT 1"):
        safe(engine.backtest_all, cfg)
    safe(engine.daily_run, cfg)
    last_radar = 0.0
    done_today = {datetime.now(tz).date().isoformat() + "-daily"}

    while True:
        now = datetime.now(tz)
        day = now.date().isoformat()
        # Daily signals after the TSX close (crypto uses the latest daily close too).
        if now.hour == 17 and now.minute >= 30 and f"{day}-daily" not in done_today:
            done_today.add(f"{day}-daily")
            safe(engine.daily_run, cfg)
        # Weekly backtest refresh, Sunday evening.
        if now.weekday() == 6 and now.hour == 19 and f"{day}-bt" not in done_today:
            done_today.add(f"{day}-bt")
            safe(engine.backtest_all, cfg)
        if radar_on and time.time() - last_radar >= radar_every:
            last_radar = time.time()
            # If the first backtest/daily run failed (e.g. no network at boot), retry hourly.
            if not db.query("SELECT 1 FROM backtests LIMIT 1"):
                safe(engine.backtest_all, cfg)
            if not db.query("SELECT 1 FROM signals LIMIT 1"):
                safe(engine.daily_run, cfg)
            safe(radar.run, cfg)
        time.sleep(30)


def main():
    cfg = load_config()
    threading.Thread(target=scheduler, args=(cfg,), daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    log.info("Dashboard on port %d", port)
    web.serve(cfg, port=port)


if __name__ == "__main__":
    main()
