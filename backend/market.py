"""Twelve Data price lookups, with an in-memory cache so rate limits/outages degrade to a
stale-but-usable price instead of a hard failure. https://api.twelvedata.com/price accepts
both stock tickers ("AAPL") and crypto pairs ("BTC/USD") through the same endpoint.
"""

import time
from datetime import datetime, timezone

import requests
from flask import current_app

CACHE_TTL_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 5

_cache = {}  # ticker -> (price: float, fetched_at: float)
_history_cache = {}  # (ticker, interval, outputsize) -> (history: list, fetched_at: float)
HISTORY_CACHE_TTL_SECONDS = 3600

# Intraday intervals show recent bars rather than a calendar range — "last 120 bars of
# 5-minute candles" rather than "5-minute candles for the last 30 days" (which would be
# thousands of points). 120 bars is ~10 hours at 5min, ~1 day at 15min, ~2.5 days at 30min.
INTRADAY_INTERVALS = {"5min", "15min", "30min"}
INTRADAY_OUTPUTSIZE = 120


def _twelvedata_symbol(ticker):
    # Holdings store crypto as "BTC-USD"; Twelve Data expects "BTC/USD".
    if "-" in ticker:
        base, quote = ticker.split("-", 1)
        return f"{base}/{quote}"
    return ticker


def get_price(ticker):
    """Returns (price, stale). Raises RuntimeError if no price is available at all."""
    now = time.time()
    cached = _cache.get(ticker)
    if cached and now - cached[1] < CACHE_TTL_SECONDS:
        return cached[0], False

    try:
        response = requests.get(
            "https://api.twelvedata.com/price",
            params={"symbol": _twelvedata_symbol(ticker), "apikey": current_app.config["MARKET_API_KEY"]},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        if "price" not in data:
            raise RuntimeError(data.get("message", "unexpected market API response"))

        price = float(data["price"])
        _cache[ticker] = (price, now)
        return price, False
    except Exception:
        if cached:
            return cached[0], True
        raise RuntimeError(f"no price available for {ticker}")


def _interval_for_range(days):
    # Keep the point count sane (and within free-tier outputsize limits) for long ranges by
    # coarsening the interval instead of asking for hundreds of daily candles.
    if days <= 180:
        return "1day", days
    if days <= 730:
        return "1week", -(-days // 7)  # ceil division
    return "1month", -(-days // 30)


def get_history(ticker, days=30, interval=None):
    """Returns a chronological list of {"date", "close"} dicts for charting. `interval`
    overrides the day-range auto-bucketing with an explicit intraday granularity (see
    INTRADAY_INTERVALS) — the most recent INTRADAY_OUTPUTSIZE bars at that granularity,
    regardless of `days`.
    """
    if interval in INTRADAY_INTERVALS:
        outputsize = INTRADAY_OUTPUTSIZE
    elif interval == "1day":
        # Explicit daily override (used by get_price_on_date) — unlike the auto-bucketing
        # below, this must never coarsen to weekly/monthly just because `days` is large.
        outputsize = min(max(days, 1), 5000)
    else:
        interval, outputsize = _interval_for_range(days)
    cache_key = (ticker, interval, outputsize)
    now = time.time()
    cached = _history_cache.get(cache_key)
    if cached and now - cached[1] < HISTORY_CACHE_TTL_SECONDS:
        return cached[0]

    response = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": _twelvedata_symbol(ticker),
            "interval": interval,
            "outputsize": outputsize,
            "apikey": current_app.config["MARKET_API_KEY"],
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    if "values" not in data:
        raise RuntimeError(data.get("message", "unexpected market API response"))

    # Twelve Data returns newest-first; reverse to chronological order for charting.
    history = [{"date": v["datetime"], "close": float(v["close"])} for v in reversed(data["values"])]
    _history_cache[cache_key] = (history, now)
    return history


def get_price_on_date(ticker, date_str):
    """Daily close for a specific calendar date — looked up server-side (not
    client-supplied) so a "trade in the past" can't be faked with an arbitrary price.
    Always daily granularity regardless of what interval any chart is currently showing, so
    this works the same whether the date came from clicking a chart point or an exact date
    picker. Returns (price, actual_date) — actual_date can differ from the requested one if
    it fell on a weekend/holiday, in which case the nearest earlier trading day is used.
    """
    target = date_str[:10]
    target_date = datetime.strptime(target, "%Y-%m-%d").date()
    today = datetime.now(timezone.utc).date()
    if target_date > today:
        raise RuntimeError("date must be in the past")

    # A small buffer past the exact day count covers nearby weekends/holidays when walking
    # back for a fallback trading day, capped at Twelve Data's max outputsize.
    outputsize = min((today - target_date).days + 10, 5000)
    history = get_history(ticker, days=outputsize, interval="1day")

    for entry in history:
        if entry["date"][:10] == target:
            return entry["close"], entry["date"][:10]

    earlier = [e for e in history if e["date"][:10] <= target]
    if earlier:
        nearest = earlier[-1]
        return nearest["close"], nearest["date"][:10]

    raise RuntimeError(f"no historical price available near {target} for {ticker}")
