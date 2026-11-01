"""Memecoin radar: fake bets on newly listed tokens, to measure how they really turn out.

Data: DexScreener public API (no key). Each rule is a filter; every new token
that passes a rule gets a pretend bet of `bet_usd`. Bets close after
`hold_days`, at take-profit, at stop-loss, or as a rug (-100%) when liquidity
disappears.
"""
import logging
from datetime import datetime, timedelta

import requests

from . import db

log = logging.getLogger("radar")
API = "https://api.dexscreener.com"

# rule name -> (description, filter on the best trading pair)
RULES = {
    "any_new": ("Every newly promoted token, no filter",
                lambda p: True),
    "liq_50k": ("Liquidity at least $50k",
                lambda p: _liq(p) >= 50_000),
    "liq_50k_vol_250k": ("Liquidity ≥ $50k and 24h volume ≥ $250k",
                         lambda p: _liq(p) >= 50_000 and _vol(p) >= 250_000),
    "established_3d": ("At least 3 days old and liquidity ≥ $100k (survivors only)",
                       lambda p: _age_h(p) >= 72 and _liq(p) >= 100_000),
}


def _liq(p): return float((p.get("liquidity") or {}).get("usd") or 0)
def _vol(p): return float((p.get("volume") or {}).get("h24") or 0)
def _price(p):
    try:
        return float(p.get("priceUsd") or 0)
    except (TypeError, ValueError):
        return 0.0
def _age_h(p):
    created = p.get("pairCreatedAt")
    if not created:
        return 0
    return (datetime.now().timestamp() * 1000 - created) / 3_600_000


def _get(path):
    r = requests.get(API + path, timeout=30)
    r.raise_for_status()
    return r.json()


def latest_tokens():
    """Newly promoted tokens: [(chainId, tokenAddress, url)]."""
    out = []
    for path in ("/token-profiles/latest/v1", "/token-boosts/latest/v1"):
        try:
            for t in _get(path) or []:
                if t.get("chainId") and t.get("tokenAddress"):
                    out.append((t["chainId"], t["tokenAddress"], t.get("url", "")))
        except Exception as e:
            log.warning("DexScreener %s failed: %s", path, e)
    return list(dict.fromkeys(out))


def pairs_for(chain, addresses):
    """Best (highest-liquidity) pair per token address."""
    best = {}
    for i in range(0, len(addresses), 30):
        chunk = addresses[i:i + 30]
        try:
            pairs = _get(f"/tokens/v1/{chain}/{','.join(chunk)}") or []
        except Exception as e:
            log.warning("DexScreener pairs %s failed: %s", chain, e)
            continue
        for p in pairs:
            addr = (p.get("baseToken") or {}).get("address", "")
            key = next((a for a in chunk if a.lower() == addr.lower()), None)
            if key and _liq(p) >= _liq(best.get(key, {})):
                best[key] = p
    return best


def _group(items):
    by_chain = {}
    for chain, addr, *_ in items:
        by_chain.setdefault(chain, []).append(addr)
    return by_chain


def run(cfg, tokens_fn=latest_tokens, pairs_fn=pairs_for, now=None):
    rc = cfg.get("radar", {})
    stake = rc.get("bet_usd", 5)
    now = now or datetime.now()
    ts = now.isoformat(timespec="seconds")

    # 1) Open new bets.
    tokens = tokens_fn()
    urls = {(c, a): u for c, a, u in tokens}
    opened = 0
    for chain, addrs in _group(tokens).items():
        best = pairs_fn(chain, addrs)
        for rule, (_, ok) in RULES.items():
            n = 0
            for addr in addrs:
                p = best.get(addr)
                if not p or _price(p) <= 0 or not ok(p) or n >= rc.get("max_new_bets_per_run", 10):
                    continue
                base = p.get("baseToken") or {}
                added = db.execute(
                    "INSERT OR IGNORE INTO radar_bets (rule, chain, token, symbol, name, url, opened, "
                    "entry_price, stake, last_price) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (rule, chain, addr, base.get("symbol", "?"), base.get("name", ""),
                     p.get("url") or urls.get((chain, addr), ""), ts, _price(p), stake, _price(p)))
                n += added
                opened += added

    # 2) Mark open bets to market and close the ones that are done.
    open_bets = db.query("SELECT * FROM radar_bets WHERE status='open'")
    closed = 0
    for chain, addrs in _group([(b["chain"], b["token"]) for b in open_bets]).items():
        best = pairs_fn(chain, list(dict.fromkeys(addrs)))
        for b in (x for x in open_bets if x["chain"] == chain):
            p = best.get(b["token"])
            price = _price(p) if p else 0.0
            change = (price / b["entry_price"] - 1) * 100 if b["entry_price"] else -100
            age = now - datetime.fromisoformat(b["opened"])
            reason = None
            if not p or _liq(p) < 1_000 or price <= 0:
                reason, change = "rug / liquidity gone", -100.0
            elif change >= rc.get("take_profit_pct", 100):
                reason = "take profit"
            elif change <= rc.get("stop_loss_pct", -50):
                reason = "stop loss"
            elif age >= timedelta(days=rc.get("hold_days", 7)):
                reason = "time limit"
            if reason:
                pnl = b["stake"] * change / 100
                db.execute("UPDATE radar_bets SET status='closed', closed=?, exit_reason=?, pnl=?, "
                           "last_price=? WHERE id=?", (ts, reason, pnl, price, b["id"]))
                closed += 1
            else:
                db.execute("UPDATE radar_bets SET last_price=? WHERE id=?", (price, b["id"]))

    log.info("radar: opened %d, closed %d", opened, closed)
    return opened, closed


def stats():
    out = []
    for rule, (desc, _) in RULES.items():
        rows = db.query("SELECT * FROM radar_bets WHERE rule=?", (rule,))
        done = [r for r in rows if r["status"] == "closed"]
        open_ = [r for r in rows if r["status"] == "open"]
        unreal = sum(r["stake"] * (r["last_price"] / r["entry_price"] - 1)
                     for r in open_ if r["entry_price"])
        realized = sum(r["pnl"] or 0 for r in done)
        staked = sum(r["stake"] for r in rows)
        out.append({
            "rule": rule, "description": desc, "bets": len(rows), "open": len(open_),
            "closed": len(done),
            "winners": sum(1 for r in done if (r["pnl"] or 0) > 0),
            "rugs": sum(1 for r in done if (r["exit_reason"] or "").startswith("rug")),
            "doubled": sum(1 for r in done if r["exit_reason"] == "take profit"),
            "staked": staked, "realized": realized, "unrealized": unreal,
            "roi_pct": 100 * (realized + unreal) / staked if staked else 0.0,
        })
    return out
