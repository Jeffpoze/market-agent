import os
import sqlite3
import threading

DB_PATH = os.environ.get("MARKET_AGENT_DB", "/data/market_agent.db")
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_positions (
  symbol TEXT, strategy TEXT, cash REAL, units REAL, last_signal INTEGER,
  updated TEXT, PRIMARY KEY (symbol, strategy));
CREATE TABLE IF NOT EXISTS paper_trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, symbol TEXT, strategy TEXT,
  side TEXT, price REAL, units REAL, value REAL);
CREATE TABLE IF NOT EXISTS signals (
  symbol TEXT, strategy TEXT, signal INTEGER, price REAL, asof TEXT,
  PRIMARY KEY (symbol, strategy));
CREATE TABLE IF NOT EXISTS backtests (
  symbol TEXT, strategy TEXT, result TEXT, ran TEXT, PRIMARY KEY (symbol, strategy));
CREATE TABLE IF NOT EXISTS radar_bets (
  id INTEGER PRIMARY KEY AUTOINCREMENT, rule TEXT, chain TEXT, token TEXT,
  symbol TEXT, name TEXT, url TEXT, opened TEXT, entry_price REAL,
  stake REAL, last_price REAL, status TEXT DEFAULT 'open', closed TEXT,
  exit_reason TEXT, pnl REAL, UNIQUE(rule, chain, token));
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, message TEXT);
"""


def connect():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def query(sql, args=()):
    with _lock:
        con = connect()
        try:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
        finally:
            con.close()


def execute(sql, args=()):
    with _lock:
        con = connect()
        try:
            cur = con.execute(sql, args)
            con.commit()
            return cur.rowcount
        finally:
            con.close()
