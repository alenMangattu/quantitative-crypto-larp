#!/usr/bin/env python3
"""
btc_collector.py
================
Fetches BTCUSDT 1-second klines from Binance for the last N months and
saves one Parquet file per UTC day into ./btc_data/.

Features
--------
- Resumable: already-saved days are skipped — just re-run to top up.
- Retry with exponential back-off on any network/HTTP error.
- Handles Binance 429 rate-limit responses automatically.
- Gracefully skips a day if it genuinely has no data (e.g. too far back).

Usage
-----
    python btc_collector.py            # fetch last 4 months
    python btc_collector.py --months 2 # fetch last 2 months

Loading in your notebook
------------------------
    from btc_collector import load_btc_price
    df = load_btc_price()              # returns 0.5s interpolated DataFrame
    df = load_btc_price(grid_freq="1s") # keep 1s resolution
"""

import argparse
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

# ── CONFIG ────────────────────────────────────────────────────────────────────
SYMBOL          = "BTCUSDT"
LOOKBACK_MONTHS = 4
OUTPUT_DIR      = Path(__file__).parent / "btc_data"
DEFAULT_GRID    = "500ms"

BINANCE_URL     = "https://api.binance.com/api/v3/klines"
PAGE_LIMIT      = 1000       # max candles per request (Binance hard cap)
INTER_REQUEST_SLEEP = 0.15   # seconds between pages (stays well under rate limit)
MAX_RETRIES     = 6
BACKOFF_BASE    = 2.0        # exponential back-off base in seconds
# ─────────────────────────────────────────────────────────────────────────────


# ── HTTP layer ────────────────────────────────────────────────────────────────

def _get(params: dict) -> list:
    """GET with retry + exponential back-off + 429 handling."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(BINANCE_URL, params=params, timeout=20)

            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 30))
                print(f"  [rate-limit] waiting {wait}s …", flush=True)
                time.sleep(wait)
                continue

            if resp.status_code == 400:
                # Typically means the interval is too far back and has no data
                return []

            resp.raise_for_status()
            return resp.json()

        except requests.RequestException as exc:
            wait = BACKOFF_BASE ** attempt
            print(f"  [retry {attempt + 1}/{MAX_RETRIES}] {exc} — sleeping {wait:.0f}s", flush=True)
            time.sleep(wait)

    print(f"  [skip] gave up after {MAX_RETRIES} retries", flush=True)
    return []


# ── Fetch one calendar day ────────────────────────────────────────────────────

def fetch_day(symbol: str, day: date) -> pd.DataFrame:
    """
    Fetch all 1-second klines for a UTC calendar day.
    Returns a DataFrame with columns [timestamp, close].
    Returns an empty DataFrame if Binance has no data for that day.
    """
    start_ms   = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * 1000)
    end_ms     = start_ms + 24 * 3600 * 1000 - 1
    pages_exp  = (24 * 3600) // PAGE_LIMIT + 1  # ~87 pages per full day

    all_rows: list = []
    cursor = start_ms
    page   = 0

    while cursor < end_ms:
        batch = _get({
            "symbol":    symbol,
            "interval":  "1s",
            "startTime": cursor,
            "endTime":   end_ms,
            "limit":     PAGE_LIMIT,
        })
        if not batch:
            break

        page += 1
        all_rows.extend(batch)
        cursor = int(batch[-1][6]) + 1   # close_time of last candle + 1 ms

        # Print a live page counter so the user sees activity
        print(f"    page {page:>2}/{pages_exp}  rows so far: {len(all_rows):>6,}", flush=True)

        if len(batch) < PAGE_LIMIT:
            break                         # reached end of available data for this day

        time.sleep(INTER_REQUEST_SLEEP)

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "trades", "taker_base", "taker_quote", "_ignore",
    ])
    df = df.drop_duplicates(subset=["open_time"])
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close"]     = df["close"].astype(float)
    return (
        df[["timestamp", "close"]]
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


# ── Interpolation ─────────────────────────────────────────────────────────────

def interpolate_to_grid(df_1s: pd.DataFrame, grid_freq: str = DEFAULT_GRID) -> pd.DataFrame:
    """
    Linearly interpolate 1-second closes onto a uniform time grid.
    grid_freq = "500ms" gives the 0.5-second series used in the notebook.
    """
    ts = df_1s.set_index("timestamp")[["close"]]
    grid = pd.date_range(
        start=ts.index.min(),
        end=ts.index.max() + pd.Timedelta(grid_freq),
        freq=grid_freq,
        tz="UTC",
    )
    ts = ts.reindex(ts.index.union(grid)).sort_index()
    ts["close"] = ts["close"].interpolate(method="time")
    return (
        ts.loc[grid]
        .dropna()
        .reset_index()
        .rename(columns={"index": "timestamp"})
    )


# ── Public loader (for use in notebook) ──────────────────────────────────────

def load_btc_price(
    data_dir: Path = OUTPUT_DIR,
    grid_freq: str = DEFAULT_GRID,
    start: str | None = None,
    end:   str | None = None,
) -> pd.DataFrame:
    """
    Load all saved daily Parquet files, merge, and interpolate.

    Parameters
    ----------
    data_dir  : directory containing the daily .parquet files
    grid_freq : output time grid, e.g. "500ms" (default) or "1s"
    start     : optional ISO date string "YYYY-MM-DD" to slice from
    end       : optional ISO date string "YYYY-MM-DD" to slice to

    Returns
    -------
    DataFrame with columns [timestamp, close]
    """
    files = sorted(Path(data_dir).glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet files found in {data_dir}. Run btc_collector.py first.")

    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = (
        df.drop_duplicates(subset=["timestamp"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    if start:
        df = df[df["timestamp"] >= pd.Timestamp(start, tz="UTC")]
    if end:
        df = df[df["timestamp"] <= pd.Timestamp(end, tz="UTC") + pd.Timedelta("1d")]

    print(f"Loaded {len(df):,} raw 1s rows from {len(files)} files — interpolating to {grid_freq} …")
    result = interpolate_to_grid(df, grid_freq)
    print(f"  → {len(result):,} {grid_freq} samples  "
          f"({result['timestamp'].min()}  →  {result['timestamp'].max()})")
    return result


# ── Progress helpers ──────────────────────────────────────────────────────────

def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem  = divmod(seconds, 3600)
    m, s    = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _progress_bar(done: int, total: int, width: int = 28) -> str:
    filled = int(width * done / total)
    return f"[{'█' * filled}{'░' * (width - filled)}]"


def _print_progress(
    i: int,
    total: int,
    day: date,
    rows: int,
    elapsed: float,
    total_rows: int,
) -> None:
    pct          = i / total * 100
    bar          = _progress_bar(i, total)
    avg_sec      = elapsed / i
    eta_sec      = avg_sec * (total - i)
    rows_per_sec = total_rows / elapsed if elapsed > 0 else 0

    print(
        f"{bar} {pct:5.1f}%  [{i}/{total}]  {day}  "
        f"{rows:>6,} rows  |  "
        f"elapsed {_fmt_duration(elapsed)}  "
        f"ETA {_fmt_duration(eta_sec)}  "
        f"({rows_per_sec:,.0f} rows/s)",
        flush=True,
    )


# ── Main collector ────────────────────────────────────────────────────────────

def main(lookback_months: int = LOOKBACK_MONTHS) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    today     = datetime.now(timezone.utc).date()
    start_day = today - timedelta(days=int(lookback_months * 30.44))
    all_days  = [start_day + timedelta(days=i) for i in range((today - start_day).days)]

    already_done = {f.stem for f in OUTPUT_DIR.glob("*.parquet")}
    pending      = [d for d in all_days if str(d) not in already_done]

    est_requests = len(pending) * 90   # ~90 pages per day at 1000 rows/page
    est_minutes  = est_requests * INTER_REQUEST_SLEEP / 60

    print("=" * 70)
    print(f"  BTCUSDT 1s collector — last {lookback_months} months")
    print(f"  Output  : {OUTPUT_DIR.resolve()}")
    print(f"  Range   : {start_day}  →  {today}")
    print(f"  Days    : {len(all_days)} total | {len(already_done)} already cached | {len(pending)} to fetch")
    print(f"  Est.    : ~{est_minutes:.0f} min  (~{est_requests:,} API requests)")
    print("=" * 70)

    if not pending:
        print("Nothing to do — all days already saved.")
        return

    run_start  = time.monotonic()
    total_rows = 0

    for i, day in enumerate(pending, 1):
        print(f"\n── [{i}/{len(pending)}] fetching {day} ──", flush=True)
        try:
            df = fetch_day(SYMBOL, day)

            if df.empty:
                print(f"  no data returned — skipping (will retry next run)")
                continue

            out_path = OUTPUT_DIR / f"{day}.parquet"
            df.to_parquet(out_path, index=False)
            total_rows += len(df)
            elapsed     = time.monotonic() - run_start

            _print_progress(i, len(pending), day, len(df), elapsed, total_rows)

        except Exception as exc:
            print(f"  [ERROR] {exc}  (skipping, will retry next run)", flush=True)

        time.sleep(INTER_REQUEST_SLEEP)

    elapsed = time.monotonic() - run_start
    print()
    print("=" * 70)
    print(f"  Done!  {len(pending)} days  |  {total_rows:,} rows  |  {_fmt_duration(elapsed)}")
    print(f"  Load in notebook:  from btc_collector import load_btc_price")
    print(f"                     df = load_btc_price()   # → {DEFAULT_GRID} series")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch BTCUSDT 1s history from Binance")
    parser.add_argument("--months", type=int, default=LOOKBACK_MONTHS,
                        help=f"months of history to fetch (default: {LOOKBACK_MONTHS})")
    args = parser.parse_args()
    main(lookback_months=args.months)
