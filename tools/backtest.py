#!/usr/bin/env python3
"""Backtest different threshold combinations on recorded minute data.

For each (midline, upper, lower) combination:
  - SELL entropy fires when sell_edge_max >= midline + upper + fees
  - BUY  entropy fires when buy_edge_max  >= lower - midline + fees

Edge captured per trade = (max_edge - fees) bps × notional
(conservative: uses the minute max edge, assumes fill at midpoint between
threshold and max; actual fill edge varies with book depth)

Usage:
    python3 tools/backtest.py
    python3 tools/backtest.py --csv logs/minutes.csv --fees-bps 1.0 --notional 500
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from itertools import product

UPPER_CANDIDATES = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]
LOWER_CANDIDATES = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]


def load_rows(path: str, hours: float, min_samples: int) -> list:
    cutoff = time.time() - hours * 3600 if hours > 0 else 0.0
    rows = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                if float(r["minute_ts"]) < cutoff:
                    continue
                if int(r["samples"]) < min_samples:
                    continue
                rows.append({
                    "ts": float(r["minute_ts"]),
                    "sell_max": float(r["sell_edge_max_bps"]),
                    "sell_mean": float(r["sell_edge_mean_bps"]),
                    "buy_max": float(r["buy_edge_max_bps"]),
                    "buy_mean": float(r["buy_edge_mean_bps"]),
                    "prem": float(r["premium_close_bps"]),
                })
            except (KeyError, ValueError):
                continue
    return rows


def pctl(sorted_vals: list, q: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * q / 100.0
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)


def backtest_one(rows, midline, upper, lower, fees, notional):
    """Simulate one threshold combo; returns stats dict."""
    sell_thresh = midline + upper + fees   # sell_edge_max must exceed this
    buy_thresh  = lower - midline + fees   # buy_edge_max  must exceed this

    sell_trades = 0; sell_edge_sum = 0.0; sell_pnl = 0.0
    buy_trades  = 0; buy_edge_sum  = 0.0; buy_pnl  = 0.0

    for r in rows:
        if r["sell_max"] >= sell_thresh:
            sell_trades += 1
            # conservative: captured edge = excess above threshold, capped by max
            # (assumes we fill at threshold + half excess, net of fees)
            edge_bps = r["sell_max"] - fees  # gross edge net of fees
            sell_edge_sum += edge_bps
            sell_pnl += (edge_bps / 1e4) * notional

        if r["buy_max"] >= buy_thresh:
            buy_trades += 1
            edge_bps = r["buy_max"] - fees
            buy_edge_sum += edge_bps
            buy_pnl += (edge_bps / 1e4) * notional

    total_trades = sell_trades + buy_trades
    total_pnl = sell_pnl + buy_pnl
    span_h = (rows[-1]["ts"] - rows[0]["ts"]) / 3600.0 + 1/60 if len(rows) > 1 else 1.0
    trades_per_day = total_trades * 24.0 / span_h if span_h > 0 else 0.0
    pnl_per_day = total_pnl * 24.0 / span_h if span_h > 0 else 0.0

    return {
        "upper": upper, "lower": lower,
        "sell_trades": sell_trades, "buy_trades": buy_trades,
        "total_trades": total_trades,
        "trades_per_day": trades_per_day,
        "sell_pnl": sell_pnl, "buy_pnl": buy_pnl,
        "total_pnl": total_pnl,
        "pnl_per_day": pnl_per_day,
        "avg_edge_bps": (sell_edge_sum + buy_edge_sum) / total_trades if total_trades else 0.0,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="logs/minutes.csv")
    p.add_argument("--hours", type=float, default=0.0)
    p.add_argument("--min-samples", type=int, default=5)
    p.add_argument("--fees-bps", type=float, default=1.0,
                   help="Total round-trip taker fees in bps")
    p.add_argument("--notional", type=float, default=500.0,
                   help="Notional per trade in USD")
    args = p.parse_args()

    try:
        rows = load_rows(args.csv, args.hours, args.min_samples)
    except FileNotFoundError:
        print(f"File not found: {args.csv}", file=sys.stderr)
        sys.exit(1)

    if not rows:
        print("No usable rows.", file=sys.stderr)
        sys.exit(1)

    span_h = (rows[-1]["ts"] - rows[0]["ts"]) / 3600.0 + 1/60
    prems = sorted(r["prem"] for r in rows)
    midline = round(pctl(prems, 50), 1) or 0.0

    print(f"\n=== Backtest on {len(rows)} minutes ({span_h:.1f}h) ===")
    print(f"Midline (median premium): {midline:+.1f} bps")
    print(f"Fees: {args.fees_bps:.1f} bps | Notional: ${args.notional:.0f} per trade\n")

    # ── Premium distribution ──────────────────────────────────────────────
    print("Premium distribution (Entropy vs hedge, bps):")
    print(f"  mean {sum(prems)/len(prems):+.2f}  std {math.sqrt(sum((x-sum(prems)/len(prems))**2 for x in prems)/len(prems)):.2f}"
          f"  p5 {pctl(prems,5):+.2f}  p25 {pctl(prems,25):+.2f}"
          f"  p75 {pctl(prems,75):+.2f}  p95 {pctl(prems,95):+.2f}\n")

    # ── Full grid scan ────────────────────────────────────────────────────
    results = []
    for upper, lower in product(UPPER_CANDIDATES, LOWER_CANDIDATES):
        r = backtest_one(rows, midline, upper, lower, args.fees_bps, args.notional)
        results.append(r)

    results.sort(key=lambda x: -x["pnl_per_day"])

    print(f"{'upper':>6} {'lower':>6} | {'sell_n':>6} {'buy_n':>6} {'total/day':>10} | "
          f"{'PnL(data)':>10} {'PnL/day':>10} | {'avg_edge':>9}")
    print("-" * 85)
    for r in results[:20]:  # top 20 by estimated daily PnL
        print(f"{r['upper']:>6.1f} {r['lower']:>6.1f} | "
              f"{r['sell_trades']:>6} {r['buy_trades']:>6} {r['trades_per_day']:>10.1f} | "
              f"${r['total_pnl']:>9.2f} ${r['pnl_per_day']:>9.2f} | "
              f"{r['avg_edge_bps']:>8.2f}bps")

    # ── Best suggestion ───────────────────────────────────────────────────
    best = results[0]
    # also find the one with ~5-20 trades/day (realistic frequency)
    realistic = [r for r in results if 5 <= r["trades_per_day"] <= 50]
    realistic.sort(key=lambda x: -x["pnl_per_day"])

    print(f"\n{'='*85}")
    print(f"TOP suggestion by raw PnL/day (might be too aggressive):")
    b = best
    print(f"  upper={b['upper']} lower={b['lower']} → {b['trades_per_day']:.1f} trades/day, "
          f"est. ${b['pnl_per_day']:.2f}/day")

    if realistic:
        r2 = realistic[0]
        print(f"\nTOP suggestion at realistic frequency (5-50 trades/day):")
        print(f"  upper={r2['upper']} lower={r2['lower']} → {r2['trades_per_day']:.1f} trades/day, "
              f"est. ${r2['pnl_per_day']:.2f}/day")
        print(f"\nSuggested config.yaml thresholds:")
        print(f"  thresholds:")
        print(f"    midline_bps: {midline}")
        print(f"    upper_bps: {r2['upper']}")
        print(f"    lower_bps: {r2['lower']}")

    print(f"\n[NOTE] Edge estimates are optimistic (uses minute max, not guaranteed fill).")
    print(f"       Collect more hours of data for higher confidence.\n")


if __name__ == "__main__":
    main()
