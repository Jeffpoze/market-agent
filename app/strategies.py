"""Each strategy turns a price series into a position series: 1 = hold, 0 = cash.

Positions are decided on day t's close and applied from day t+1, so there is
no look-ahead in the backtest.
"""
import numpy as np
import pandas as pd

DESCRIPTIONS = {
    "trend_200": "Hold when price is above its 200-day average",
    "golden_cross": "Hold when 50-day average is above 200-day average",
    "rsi_dip": "Buy RSI<30 dips in an uptrend, sell at RSI>70",
    "buy_hold": "Benchmark: buy once and never sell",
}


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def trend_200(close):
    sma = close.rolling(200).mean()
    return (close > sma).astype(int).where(sma.notna(), 0)


def golden_cross(close):
    fast, slow = close.rolling(50).mean(), close.rolling(200).mean()
    return (fast > slow).astype(int).where(slow.notna(), 0)


def rsi_dip(close):
    r = rsi(close)
    uptrend = close > close.rolling(200).mean()
    pos, holding = [], 0
    for rv, up in zip(r.values, uptrend.values):
        if not holding and rv < 30 and up:
            holding = 1
        elif holding and rv > 70:
            holding = 0
        pos.append(holding)
    return pd.Series(pos, index=close.index)


def buy_hold(close):
    return pd.Series(1, index=close.index)


STRATEGIES = {
    "trend_200": trend_200,
    "golden_cross": golden_cross,
    "rsi_dip": rsi_dip,
    "buy_hold": buy_hold,
}
