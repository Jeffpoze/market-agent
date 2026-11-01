"""Backtest a strategy on daily closes, with a cost charged on every position change."""
import numpy as np
import pandas as pd

from .strategies import STRATEGIES


def run(close: pd.Series, strategy: str, fee_pct: float = 0.5, periods_per_year: int = 252) -> dict:
    pos = STRATEGIES[strategy](close).shift(1).fillna(0)  # act the day after the signal
    rets = close.pct_change().fillna(0)
    trades = pos.diff().abs().fillna(pos.iloc[0])
    strat = pos * rets - trades * fee_pct / 100
    equity = (1 + strat).cumprod()

    years = max(len(close) / periods_per_year, 1e-9)
    total = equity.iloc[-1] - 1
    cagr = equity.iloc[-1] ** (1 / years) - 1 if equity.iloc[-1] > 0 else -1.0
    dd = (equity / equity.cummax() - 1).min()
    vol = strat.std() * np.sqrt(periods_per_year)
    sharpe = (strat.mean() * periods_per_year) / vol if vol > 0 else 0.0

    # Round-trip win rate: compare equity at entry vs exit of each holding period.
    wins = losses = 0
    entry = None
    for date, p in pos.items():
        if p == 1 and entry is None:
            entry = equity.loc[date]
        elif p == 0 and entry is not None:
            wins += equity.loc[date] > entry
            losses += equity.loc[date] <= entry
            entry = None
    rounds = wins + losses

    return {
        "strategy": strategy,
        "years": round(years, 1),
        "total_return_pct": round(total * 100, 1),
        "cagr_pct": round(cagr * 100, 1),
        "max_drawdown_pct": round(dd * 100, 1),
        "sharpe": round(float(sharpe), 2),
        "trades": int(trades.sum()),
        "win_rate_pct": round(100 * wins / rounds, 0) if rounds else None,
        "time_in_market_pct": round(100 * pos.mean(), 0),
    }


def periods_for(symbol: str) -> int:
    """Crypto trades every day; stocks ~252 days a year."""
    return 365 if "-" in symbol and symbol.split("-")[-1] in {"CAD", "USD", "USDT"} else 252


def doubling_odds(close: pd.Series) -> dict:
    """From every past day: how often did the price double (or halve) within 6 / 12 months?

    Uses calendar days so stocks and crypto are comparable. Only start days with a
    full window of future data are counted.
    """
    s = close.dropna()
    out = {"start": s.index[0].date().isoformat(), "years": round((s.index[-1] - s.index[0]).days / 365.25, 1)}
    vals, idx = s.values, s.index
    for label, days in (("6m", 182), ("12m", 365)):
        ends = idx.searchsorted(idx + pd.Timedelta(days=days), side="right")
        valid = ends < len(s)
        n = int(valid.sum())
        if n < 30:
            out.update({f"double_{label}": None, f"halve_{label}": None})
            continue
        dbl = hlf = 0
        rets = []
        for i in np.nonzero(valid)[0]:
            window = vals[i + 1:ends[i]]
            if window.size == 0:
                continue
            dbl += window.max() >= 2 * vals[i]
            hlf += window.min() <= 0.5 * vals[i]
            rets.append(vals[ends[i] - 1] / vals[i] - 1)
        out[f"double_{label}"] = round(100 * dbl / n, 1)
        out[f"halve_{label}"] = round(100 * hlf / n, 1)
        out[f"median_{label}"] = round(100 * float(np.median(rets)), 1) if rets else None
    return out
