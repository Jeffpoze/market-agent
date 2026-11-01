"""Price data from Yahoo Finance's public chart endpoint (no API key needed)."""
import time
import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) market-agent/1.0"}
_cache: dict = {}


def history(symbol: str, years: int = 10) -> pd.Series:
    """Daily closing prices as a Series indexed by date (oldest first)."""
    key = (symbol, years)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    rng = "max" if years > 10 else f"{years}y"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    r = requests.get(url, params={"range": rng, "interval": "1d"}, headers=UA, timeout=30)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    closes = res["indicators"]["quote"][0]["close"]
    idx = pd.to_datetime(res["timestamp"], unit="s").normalize()
    s = pd.Series(closes, index=idx, name=symbol, dtype="float64").dropna()
    s = s[~s.index.duplicated(keep="last")]
    _cache[key] = (time.time(), s)
    return s
