"""Optional read-only Coinbase balances via the Advanced Trade API.

Create a key at https://portal.cdp.coinbase.com with ONLY the "View" permission
(never Trade or Transfer), then set COINBASE_API_KEY and COINBASE_API_SECRET
in the .env file.
"""
import logging
import os
import time

log = logging.getLogger("coinbase")
_cache = {"t": 0, "rows": None, "error": None}


def balances():
    key, secret = os.environ.get("COINBASE_API_KEY"), os.environ.get("COINBASE_API_SECRET")
    if not key or not secret:
        return None, "Not connected (add a view-only key to .env)"
    if time.time() - _cache["t"] < 300:
        return _cache["rows"], _cache["error"]
    try:
        from coinbase.rest import RESTClient
        client = RESTClient(api_key=key, api_secret=secret.replace("\\n", "\n"))
        resp = client.get_accounts(limit=250)
        data = resp.to_dict() if hasattr(resp, "to_dict") else resp
        rows = []
        for a in data.get("accounts", []):
            bal = float((a.get("available_balance") or {}).get("value") or 0)
            hold = float((a.get("hold") or {}).get("value") or 0)
            if bal + hold > 0:
                rows.append({"currency": a.get("currency"), "amount": bal + hold})
        _cache.update(t=time.time(), rows=rows, error=None)
    except Exception as e:
        log.warning("Coinbase balances failed: %s", e)
        _cache.update(t=time.time(), rows=None, error=f"Coinbase error: {e}")
    return _cache["rows"], _cache["error"]
