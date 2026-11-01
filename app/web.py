"""Small built-in web dashboard (no framework needed)."""
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import coinbase_ro, db, engine, radar
from .strategies import DESCRIPTIONS

CSS = """
:root{--bg:#0b0f17;--card:#141a26;--line:#232c3d;--text:#e8ecf3;--muted:#8a96ab;
--up:#3ecf8e;--down:#ff6b6b;--accent:#6aa8ff}
@media (prefers-color-scheme: light){:root{--bg:#f4f6fa;--card:#fff;--line:#e2e7ef;
--text:#121826;--muted:#5b6678;--up:#119a5c;--down:#d43c3c;--accent:#2563eb}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.45 Inter,system-ui,-apple-system,sans-serif}
header{padding:20px 16px 8px;max-width:980px;margin:auto}
h1{font:700 22px/1.2 Inter,system-ui;margin:0;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:13px;margin-top:4px}
nav{display:flex;gap:6px;padding:10px 16px;max-width:980px;margin:auto;overflow-x:auto}
nav a{color:var(--muted);text-decoration:none;padding:7px 14px;border:1px solid var(--line);
border-radius:999px;white-space:nowrap;font-size:14px}
nav a.on{color:var(--text);border-color:var(--accent);background:color-mix(in srgb,var(--accent) 14%,transparent)}
main{max-width:980px;margin:auto;padding:8px 16px 40px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:12px 0}
.card h2{font-size:15px;margin:0 0 10px;font-weight:650}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px}
.kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums;margin-top:2px}
.kpi span{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--muted);font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.03em}
td.n{text-align:right;font-variant-numeric:tabular-nums}th.n{text-align:right}
.up{color:var(--up)}.down{color:var(--down)}.muted{color:var(--muted)}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600}
.pill.hold{background:color-mix(in srgb,var(--up) 18%,transparent);color:var(--up)}
.pill.cash{background:color-mix(in srgb,var(--muted) 18%,transparent);color:var(--muted)}
.note{color:var(--muted);font-size:13px}a{color:var(--accent)}
"""


def esc(x):
    return html.escape(str(x))


def money(x, cur="$"):
    return f"{cur}{x:,.2f}"


def pct(x):
    if x is None:
        return '<span class="muted">—</span>'
    cls = "up" if x > 0 else "down" if x < 0 else ""
    return f'<span class="{cls}">{x:+.1f}%</span>'


def page(title, active, body):
    tabs = [("/", "Overview"), ("/backtests", "Backtests"), ("/radar", "Memecoin radar"),
            ("/log", "Log")]
    nav = "".join(f'<a href="{h}" class="{"on" if h == active else ""}">{t}</a>' for h, t in tabs)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>{CSS}</style></head><body>
<header><h1>Market Agent</h1><div class="sub">Paper trading only — no real money is moved.</div></header>
<nav>{nav}</nav><main>{body}</main></body></html>"""


def overview(cfg):
    rows, total = engine.portfolio()
    start = cfg.get("paper", {}).get("starting_cash", 1000)
    ret = (total / start - 1) * 100 if rows else None
    holding = sum(1 for r in rows if r["units"] > 0)
    rstats = radar.stats()
    rbets = sum(s["bets"] for s in rstats)
    kpis = f"""<div class="kpis">
<div class="kpi"><span>Paper portfolio</span><b>{money(total) if rows else '—'}</b></div>
<div class="kpi"><span>Return</span><b>{pct(ret)}</b></div>
<div class="kpi"><span>Positions held</span><b>{holding} / {len(rows)}</b></div>
<div class="kpi"><span>Radar bets</span><b>{rbets}</b></div></div>"""

    sigs = db.query("SELECT * FROM signals ORDER BY symbol, strategy")
    srows = "".join(
        f"<tr><td>{esc(s['symbol'])}</td><td>{esc(s['strategy'])}</td>"
        f"<td><span class='pill {'hold' if s['signal'] else 'cash'}'>{'HOLD' if s['signal'] else 'CASH'}</span></td>"
        f"<td class='n'>{s['price']:,.2f}</td><td class='muted'>{esc(s['asof'])}</td></tr>" for s in sigs)
    sig_card = (f"<div class='card'><h2>Today's signals</h2><div class='scroll'><table>"
                f"<tr><th>Symbol</th><th>Strategy</th><th>Signal</th><th class='n'>Price</th><th>As of</th></tr>"
                f"{srows}</table></div></div>") if sigs else \
        "<div class='card'><h2>Today's signals</h2><p class='note'>Waiting for the first daily run.</p></div>"

    trades = db.query("SELECT * FROM paper_trades ORDER BY id DESC LIMIT 15")
    trows = "".join(
        f"<tr><td class='muted'>{esc(t['ts'][:10])}</td><td>{esc(t['symbol'])}</td><td>{esc(t['strategy'])}</td>"
        f"<td class='{'up' if t['side'] == 'BUY' else 'down'}'>{t['side']}</td>"
        f"<td class='n'>{t['price']:,.2f}</td><td class='n'>{money(t['value'])}</td></tr>" for t in trades)
    trade_card = (f"<div class='card'><h2>Recent paper trades</h2><div class='scroll'><table>"
                  f"<tr><th>Date</th><th>Symbol</th><th>Strategy</th><th>Side</th><th class='n'>Price</th>"
                  f"<th class='n'>Value</th></tr>{trows}</table></div></div>") if trades else ""

    cb_rows, cb_err = coinbase_ro.balances() if cfg.get("coinbase", {}).get("enabled") else (None, None)
    cb = ""
    if cb_rows is not None:
        cb = "<div class='card'><h2>Coinbase (read-only)</h2><table>" + "".join(
            f"<tr><td>{esc(r['currency'])}</td><td class='n'>{r['amount']:.8g}</td></tr>" for r in cb_rows
        ) + "</table></div>"
    elif cb_err:
        cb = f"<div class='card'><h2>Coinbase</h2><p class='note'>{esc(cb_err)}</p></div>"
    return page("Market Agent", "/", kpis + odds_card() + sig_card + trade_card + cb)


def odds_card():
    rows = db.query("SELECT * FROM odds ORDER BY symbol")
    if not rows:
        return ""
    trs = ""
    for r in rows:
        o = json.loads(r["result"])
        def cell(v, good):
            if v is None:
                return "<td class='n muted'>—</td>"
            cls = ("up" if v >= 20 else "") if good else ("down" if v >= 10 else "")
            return f"<td class='n {cls}'>{v:.0f}%</td>"
        trs += (f"<tr><td>{esc(r['symbol'])}</td>{cell(o.get('double_6m'), True)}"
                f"{cell(o.get('double_12m'), True)}{cell(o.get('halve_12m'), False)}"
                f"<td class='n'>{pct(o.get('median_12m'))}</td></tr>")
    return (f"<div class='card'><h2>Could it double?</h2>"
            f"<p class='note'>From every day in the last ~10 years: how often the price doubled at some point "
            f"in the next 6 or 12 months, how often it got cut in half, and the typical 1-year result. "
            f"History, not a promise.</p><div class='scroll'><table><tr><th>Symbol</th>"
            f"<th class='n'>Doubled 6m</th><th class='n'>Doubled 12m</th><th class='n'>Halved 12m</th>"
            f"<th class='n'>Typical 1y</th></tr>{trs}</table></div></div>")


def backtests_page():
    rows = db.query("SELECT * FROM backtests ORDER BY symbol")
    if not rows:
        return page("Backtests", "/backtests",
                    "<div class='card'><p class='note'>Backtests run at startup and every Sunday.</p></div>")
    by_sym = {}
    for r in rows:
        by_sym.setdefault(r["symbol"], []).append(json.loads(r["result"]))
    cards = ["<p class='note'>Each strategy vs. simply buying and holding, after an assumed cost per trade. "
             "Past results don't predict future ones; a strategy that loses here won't be saved by hope.</p>"]
    for sym, res in by_sym.items():
        bench = next((x for x in res if x["strategy"] == "buy_hold"), None)
        res.sort(key=lambda x: (x["strategy"] != "buy_hold", -x["cagr_pct"]))
        trs = ""
        for x in res:
            beat = ""
            if bench and x["strategy"] != "buy_hold":
                beat = " ✓" if x["cagr_pct"] > bench["cagr_pct"] else ""
            trs += (f"<tr><td title='{esc(DESCRIPTIONS.get(x['strategy'], ''))}'>{esc(x['strategy'])}{beat}</td>"
                    f"<td class='n'>{pct(x['cagr_pct'])}</td><td class='n'>{pct(x['max_drawdown_pct'])}</td>"
                    f"<td class='n'>{x['sharpe']}</td><td class='n'>{x['trades']}</td>"
                    f"<td class='n'>{'—' if x['win_rate_pct'] is None else str(int(x['win_rate_pct'])) + '%'}</td>"
                    f"<td class='n'>{int(x['time_in_market_pct'])}%</td></tr>")
        yrs = res[0]["years"]
        cards.append(f"<div class='card'><h2>{esc(sym)} <span class='muted'>· {yrs} yrs</span></h2>"
                     f"<div class='scroll'><table><tr><th>Strategy</th><th class='n'>Yearly</th>"
                     f"<th class='n'>Worst drop</th><th class='n'>Sharpe</th><th class='n'>Trades</th>"
                     f"<th class='n'>Win rate</th><th class='n'>In market</th></tr>{trs}</table></div></div>")
    cards.append("<p class='note'>✓ = beat buy-and-hold on yearly return. Worst drop = largest peak-to-trough loss.</p>")
    return page("Backtests", "/backtests", "".join(cards))


def radar_page():
    st = radar.stats()
    trs = "".join(
        f"<tr><td title='{esc(s['description'])}'>{esc(s['rule'])}</td><td class='n'>{s['bets']}</td>"
        f"<td class='n'>{s['open']}</td><td class='n'>{s['rugs']}</td><td class='n'>{s['doubled']}</td>"
        f"<td class='n'>{money(s['staked'])}</td><td class='n'>{pct(s['roi_pct'])}</td></tr>" for s in st)
    rules = "".join(f"<li><b>{esc(s['rule'])}</b>: {esc(s['description'])}</li>" for s in st)
    recent = db.query("SELECT * FROM radar_bets ORDER BY id DESC LIMIT 40")
    rrows = ""
    for b in recent:
        chg = (b["last_price"] / b["entry_price"] - 1) * 100 if b["entry_price"] else None
        if b["status"] == "closed" and b["exit_reason"] and b["exit_reason"].startswith("rug"):
            chg = -100.0
        link = f"<a href='{esc(b['url'])}' target='_blank' rel='noopener'>{esc(b['symbol'])}</a>" if b["url"] else esc(b["symbol"])
        rrows += (f"<tr><td>{link}</td><td class='muted'>{esc(b['chain'])}</td><td>{esc(b['rule'])}</td>"
                  f"<td class='n'>{pct(chg)}</td><td class='muted'>{esc(b['exit_reason'] or 'open')}</td>"
                  f"<td class='muted'>{esc(b['opened'][:16].replace('T', ' '))}</td></tr>")
    body = (f"<p class='note'>Pretend $5 bets on newly promoted tokens. The point is to measure how often "
            f"memecoins actually pay off before risking real money.</p>"
            f"<div class='card'><h2>Results by rule</h2><div class='scroll'><table><tr><th>Rule</th>"
            f"<th class='n'>Bets</th><th class='n'>Open</th><th class='n'>Rugs</th><th class='n'>Doubled</th>"
            f"<th class='n'>Staked</th><th class='n'>Return</th></tr>{trs}</table></div>"
            f"<ul class='note'>{rules}</ul></div>")
    if recent:
        body += (f"<div class='card'><h2>Recent bets</h2><div class='scroll'><table><tr><th>Token</th><th>Chain</th>"
                 f"<th>Rule</th><th class='n'>Change</th><th>Status</th><th>Opened</th></tr>{rrows}</table></div></div>")
    return page("Memecoin radar", "/radar", body)


def log_page():
    ev = db.query("SELECT * FROM events ORDER BY id DESC LIMIT 100")
    trs = "".join(f"<tr><td class='muted'>{esc(e['ts'].replace('T', ' '))}</td><td>{esc(e['kind'])}</td>"
                  f"<td style='white-space:normal'>{esc(e['message'])}</td></tr>" for e in ev)
    return page("Log", "/log", f"<div class='card'><div class='scroll'><table>{trs}</table></div></div>")


def summary_json(cfg):
    rows, total = engine.portfolio()
    return {"paper_value": round(total, 2),
            "starting_cash": cfg.get("paper", {}).get("starting_cash", 1000),
            "signals": db.query("SELECT symbol, strategy, signal, price, asof FROM signals"),
            "radar": radar.stats()}


def serve(cfg, host="0.0.0.0", port=8080):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlparse(self.path).path
            try:
                if path == "/":
                    out, ctype = overview(cfg), "text/html"
                elif path == "/backtests":
                    out, ctype = backtests_page(), "text/html"
                elif path == "/radar":
                    out, ctype = radar_page(), "text/html"
                elif path == "/log":
                    out, ctype = log_page(), "text/html"
                elif path == "/api/summary":
                    out, ctype = json.dumps(summary_json(cfg)), "application/json"
                elif path == "/health":
                    out, ctype = "ok", "text/plain"
                else:
                    self.send_error(404)
                    return
                body = out.encode()
                self.send_response(200)
                self.send_header("Content-Type", ctype + "; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_error(500, str(e))

        def log_message(self, *a):
            pass

    ThreadingHTTPServer((host, port), H).serve_forever()
