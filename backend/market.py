"""Twelve Data price lookups, with an in-memory cache so rate limits/outages degrade to a
stale-but-usable price instead of a hard failure. https://api.twelvedata.com/price accepts
both stock tickers ("AAPL") and crypto pairs ("BTC/USD") through the same endpoint.
"""

import time

import requests
from flask import current_app

CACHE_TTL_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 5

_cache = {}  # symbol -> (price: float, fetched_at: float)
_history_cache = {}  # (symbol, days) -> (history: list, fetched_at: float)
HISTORY_CACHE_TTL_SECONDS = 3600


def _twelvedata_symbol(symbol):
    # Holdings store crypto as "BTC-USD"; Twelve Data expects "BTC/USD".
    if "-" in symbol:
        base, quote = symbol.split("-", 1)
        return f"{base}/{quote}"
    return symbol


def get_price(symbol):
    """Returns (price, stale). Raises RuntimeError if no price is available at all."""
    now = time.time()
    cached = _cache.get(symbol)
    if cached and now - cached[1] < CACHE_TTL_SECONDS:
        return cached[0], False

    try:
        response = requests.get(
            "https://api.twelvedata.com/price",
            params={"symbol": _twelvedata_symbol(symbol), "apikey": current_app.config["MARKET_API_KEY"]},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        if "price" not in data:
            raise RuntimeError(data.get("message", "unexpected market API response"))

        price = float(data["price"])
        _cache[symbol] = (price, now)
        return price, False
    except Exception:
        if cached:
            return cached[0], True
        raise RuntimeError(f"no price available for {symbol}")


def _interval_for_range(days):
    # Keep the point count sane (and within free-tier outputsize limits) for long ranges by
    # coarsening the interval instead of asking for hundreds of daily candles.
    if days <= 180:
        return "1day", days
    if days <= 730:
        return "1week", -(-days // 7)  # ceil division
    return "1month", -(-days // 30)


def get_history(symbol, days=30):
    """Returns a chronological list of {"date", "close"} dicts for charting."""
    interval, outputsize = _interval_for_range(days)
    cache_key = (symbol, interval, outputsize)
    now = time.time()
    cached = _history_cache.get(cache_key)
    if cached and now - cached[1] < HISTORY_CACHE_TTL_SECONDS:
        return cached[0]

    response = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": _twelvedata_symbol(symbol),
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


def get_price_at_date(symbol, date_str, days=30):
    """Historical close for a specific date — looked up server-side (not client-supplied)
    so a "trade in the past" can't be faked with an arbitrary price. `days` must match
    whatever range the frontend charted the date from, since longer ranges bucket into
    weekly/monthly candles and the date strings won't line up otherwise.
    """
    history = get_history(symbol, days=days)
    target = date_str[:10]
    for entry in history:
        if entry["date"][:10] == target:
            return entry["close"]
    raise RuntimeError(f"no historical price for {symbol} on {target}")
