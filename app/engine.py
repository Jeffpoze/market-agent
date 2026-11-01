"""Daily signal + paper-trading run, and the weekly backtest."""
import json
import logging
from datetime import datetime

from . import data, db, notify
from .backtest import doubling_odds, periods_for, run as run_backtest
from .strategies import STRATEGIES

log = logging.getLogger("engine")


def symbols(cfg):
    wl = cfg.get("watchlist", {})
    return list(wl.get("etfs", [])) + list(wl.get("crypto", []))


def now():
    return datetime.now().isoformat(timespec="seconds")


def event(kind, msg):
    log.info("%s: %s", kind, msg)
    db.execute("INSERT INTO events (ts, kind, message) VALUES (?,?,?)", (now(), kind, msg))


def backtest_all(cfg, fetch=data.history):
    years = cfg.get("backtest", {}).get("years", 10)
    fee = cfg.get("paper", {}).get("fee_pct", 0.5)
    for sym in symbols(cfg):
        try:
            close = fetch(sym, years)
        except Exception as e:  # network / bad symbol
            event("error", f"Backtest data for {sym} failed: {e}")
            continue
        for strat in list(cfg.get("strategies", [])) + ["buy_hold"]:
            res = run_backtest(close, strat, fee, periods_for(sym))
            db.execute("INSERT OR REPLACE INTO backtests VALUES (?,?,?,?)",
                       (sym, strat, json.dumps(res), now()))
        db.execute("INSERT OR REPLACE INTO odds VALUES (?,?,?)",
                   (sym, json.dumps(doubling_odds(close)), now()))
    event("backtest", "Backtests refreshed")


def daily_run(cfg, fetch=data.history):
    """Compute today's signal per symbol/strategy and update the paper portfolio."""
    syms, strats = symbols(cfg), list(cfg.get("strategies", []))
    paper = cfg.get("paper", {})
    reset_if_budget_changed(paper.get("starting_cash", 1000))
    fee = paper.get("fee_pct", 0.5) / 100
    slice_cash = paper.get("starting_cash", 1000) / max(len(syms) * len(strats), 1)
    changes = []

    for sym in syms:
        try:
            close = fetch(sym, 2)
        except Exception as e:
            event("error", f"Price data for {sym} failed: {e}")
            continue
        price, asof = float(close.iloc[-1]), close.index[-1].date().isoformat()
        for strat in strats:
            sig = int(STRATEGIES[strat](close).iloc[-1])
            prev = db.query("SELECT signal FROM signals WHERE symbol=? AND strategy=?", (sym, strat))
            db.execute("INSERT OR REPLACE INTO signals VALUES (?,?,?,?,?)", (sym, strat, sig, price, asof))

            pos = db.query("SELECT * FROM paper_positions WHERE symbol=? AND strategy=?", (sym, strat))
            if not pos:
                db.execute("INSERT INTO paper_positions VALUES (?,?,?,?,?,?)",
                           (sym, strat, slice_cash, 0.0, 0, now()))
                pos = [{"cash": slice_cash, "units": 0.0}]
            cash, units = pos[0]["cash"], pos[0]["units"]

            if sig == 1 and units == 0 and cash > 0:
                units, value, cash = cash * (1 - fee) / price, cash, 0.0
                _trade(sym, strat, "BUY", price, units, value)
            elif sig == 0 and units > 0:
                value = units * price * (1 - fee)
                _trade(sym, strat, "SELL", price, units, value)
                cash, units = value, 0.0
            db.execute("UPDATE paper_positions SET cash=?, units=?, last_signal=?, updated=? "
                       "WHERE symbol=? AND strategy=?", (cash, units, sig, now(), sym, strat))

            if prev and prev[0]["signal"] != sig:
                changes.append(f"{sym} {strat}: {'BUY' if sig else 'SELL'} @ {price:,.2f}")

    if changes:
        msg = "Signal changes (paper): " + "; ".join(changes)
        event("signal", msg)
        notify.home_assistant(cfg, "Market Agent", msg)
    else:
        event("daily", "Daily run done, no signal changes")


def reset_if_budget_changed(budget):
    """Start the paper portfolio over when the starting cash in the config changes."""
    row = db.query("SELECT value FROM meta WHERE key='starting_cash'")
    if row and float(row[0]["value"]) != float(budget):
        db.execute("DELETE FROM paper_positions")
        db.execute("DELETE FROM paper_trades")
        event("paper", f"Paper portfolio reset: budget changed from ${float(row[0]['value']):,.2f} to ${float(budget):,.2f}")
    db.execute("INSERT OR REPLACE INTO meta VALUES ('starting_cash', ?)", (str(budget),))


def _trade(sym, strat, side, price, units, value):
    db.execute("INSERT INTO paper_trades (ts, symbol, strategy, side, price, units, value) "
               "VALUES (?,?,?,?,?,?,?)", (now(), sym, strat, side, price, units, value))


def portfolio():
    rows = db.query("SELECT p.*, s.price FROM paper_positions p LEFT JOIN signals s "
                    "USING (symbol, strategy)")
    total = sum(r["cash"] + r["units"] * (r["price"] or 0) for r in rows)
    return rows, total
