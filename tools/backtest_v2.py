#!/usr/bin/env python3
"""Comprehensive arbitrage backtest with position tracking.

CORRECT MODEL:
  - BUY entropy / SELL hedge: opens a long-entropy position, fills with POSITIVE edge
    (you buy cheap, sell expensive simultaneously → immediate cash profit)
  - SELL entropy / BUY hedge: CLOSES the position, fills with NEGATIVE edge
    (you sell cheap, buy expensive → immediate cash cost)
  - Net round-trip PnL = buy_fill_edge + sell_fill_edge (sell is negative)
                       = (buy_edge_bps + sell_edge_bps) × notional / 10000
                       = spread_change × notional

  The sell direction is needed to RECYCLE the position so future buy trades
  can fire again. Without recycling, you hit position cap and stop.

  Position cap is the real binding constraint on how many trades you can do.

Columns printed per parameter sweep:
  - rt_per_day   completed round trips per day
  - buy_edge     avg bps captured on buy legs
  - sell_edge    avg bps paid on sell legs (positive = you paid this)
  - net_rt_bps   avg net bps per round trip (buy - sell - fees)
  - pnl_per_rt   avg USD PnL per round trip
  - daily_pnl    estimated daily PnL (rt_per_day × pnl_per_rt)
  - max_pos_usd  peak open position value seen during simulation
  - stuck_mins   minutes where both directions were blocked by position cap

Usage:
    python3 tools/backtest_v2.py
    python3 tools/backtest_v2.py --fees-bps 1.0 --notional 500 --cap 1000
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
import time

UPPER_SWEEP = [5.0, 8.0, 10.0, 12.0, 15.0, 20.0]
LOWER_SWEEP = [5.0, 8.0, 10.0, 12.0, 15.0, 20.0]
REF_PRICE   = 2160.0   # approximate price for position value calc


def pctl(vals: list, q: float) -> float:
    if not vals:
        return float("nan")
    s = sorted(vals)
    k = (len(s) - 1) * q / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] if lo == hi else s[lo] * (hi - k) + s[hi] * (k - lo)


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
                    "ts":         float(r["minute_ts"]),
                    "sell_max":   float(r["sell_edge_max_bps"]),
                    "sell_mean":  float(r["sell_edge_mean_bps"]),
                    "buy_max":    float(r["buy_edge_max_bps"]),
                    "buy_mean":   float(r["buy_edge_mean_bps"]),
                    "prem":       float(r["premium_close_bps"]),
                    "prem_mean":  float(r["premium_mean_bps"]),
                })
            except (KeyError, ValueError):
                continue
    return rows


def simulate(rows, midline, upper, lower, fees_bps, notional, cap_usd,
             cooldown_minutes=1, fill_at="mean"):
    """
    Simulate one param combination. Returns stats dict.

    fill_at: "mean" = use minute mean edge for fill (conservative),
             "max"  = use minute max edge (optimistic)
    """
    # Thresholds (bps)
    # BUY fires when buy_edge >= lower - midline + fees
    buy_thresh  = lower - midline + fees_bps
    # SELL fires when sell_edge >= midline + upper + fees
    # (sell_edge is negative; midline+upper is less negative → fires when spread is narrow)
    sell_thresh = midline + upper + fees_bps

    position_base = 0.0          # in base units (+ = long entropy)
    total_buy_pnl  = 0.0
    total_sell_pnl = 0.0
    n_buy = 0
    n_sell = 0
    n_round_trips = 0
    buy_edges = []
    sell_edges = []
    rt_pnls = []
    max_pos_usd = 0.0
    stuck_minutes = 0
    last_trade_minute_idx = -999

    # track open lots for matching
    open_buy_edges = []   # list of bps captured on each open buy leg

    for idx, r in enumerate(rows):
        pos_usd = abs(position_base) * REF_PRICE
        max_pos_usd = max(max_pos_usd, pos_usd)

        # cooldown
        if idx - last_trade_minute_idx < cooldown_minutes:
            continue

        fill_key = "mean" if fill_at == "mean" else "max"
        buy_fill_edge  = r["buy_" + fill_key]
        sell_fill_edge = r["sell_" + fill_key]

        # --- BUY entropy direction ---
        can_buy = (r["buy_max"] >= buy_thresh and
                   pos_usd + notional <= cap_usd)

        # --- SELL entropy direction ---
        can_sell = (r["sell_max"] >= sell_thresh and
                    pos_usd >= notional * 0.9)  # need open position to close

        if can_buy and can_sell:
            # both fire: prefer buy if edge is better (mean buy > |mean sell|)
            if abs(buy_fill_edge) >= abs(sell_fill_edge):
                can_sell = False
            else:
                can_buy = False

        if can_buy:
            qty = notional / REF_PRICE
            edge_bps = buy_fill_edge - fees_bps
            pnl = (edge_bps / 1e4) * notional
            position_base += qty
            total_buy_pnl += pnl
            n_buy += 1
            buy_edges.append(edge_bps)
            open_buy_edges.append(edge_bps)
            last_trade_minute_idx = idx

        elif can_sell:
            qty = notional / REF_PRICE
            # sell_fill_edge is negative bps; the "cost" = |sell_fill_edge| + fees
            edge_bps = sell_fill_edge - fees_bps   # will be negative
            pnl = (edge_bps / 1e4) * notional      # will be negative USD
            position_base -= qty
            if position_base < 0:
                position_base = 0.0   # don't go net short
            total_sell_pnl += pnl
            n_sell += 1
            sell_edges.append(edge_bps)
            last_trade_minute_idx = idx
            # complete a round trip if we have an open buy to match
            if open_buy_edges:
                open_bps = open_buy_edges.pop(0)   # FIFO matching
                rt_pnl = ((open_bps + edge_bps) / 1e4) * notional
                rt_pnls.append(rt_pnl)
                n_round_trips += 1

        else:
            # Check if we're stuck (signal present but blocked by cap)
            buy_signal  = r["buy_max"] >= buy_thresh
            sell_signal = r["sell_max"] >= sell_thresh
            if buy_signal and pos_usd + notional > cap_usd:
                stuck_minutes += 1
            elif sell_signal and pos_usd < notional * 0.9:
                stuck_minutes += 1

    span_h = ((rows[-1]["ts"] - rows[0]["ts"]) / 3600.0 + 1/60
              if len(rows) > 1 else 1.0)
    per_day = 24.0 / span_h

    total_pnl = total_buy_pnl + total_sell_pnl
    # Include unrealized PnL on remaining open position (assume closes at midline)
    unrealized_pnl = sum((open_bps / 1e4) * notional for open_bps in open_buy_edges)

    avg_buy_edge  = sum(buy_edges)  / len(buy_edges)  if buy_edges  else 0.0
    avg_sell_edge = sum(sell_edges) / len(sell_edges) if sell_edges else 0.0
    avg_rt_bps = (avg_buy_edge + avg_sell_edge) if buy_edges and sell_edges else avg_buy_edge
    avg_rt_pnl = sum(rt_pnls) / len(rt_pnls) if rt_pnls else 0.0

    return {
        "upper": upper, "lower": lower,
        "n_buy": n_buy, "n_sell": n_sell,
        "n_round_trips": n_round_trips,
        "rt_per_day":   n_round_trips * per_day,
        "buy_per_day":  n_buy * per_day,
        "sell_per_day": n_sell * per_day,
        "avg_buy_edge_bps":  avg_buy_edge,
        "avg_sell_edge_bps": avg_sell_edge,
        "avg_rt_bps": avg_rt_bps,
        "avg_rt_pnl": avg_rt_pnl,
        "total_pnl": total_pnl,
        "unrealized_pnl": unrealized_pnl,
        "daily_pnl": (total_pnl + unrealized_pnl) * per_day,
        "max_pos_usd": max_pos_usd,
        "stuck_mins": stuck_minutes,
        "stuck_pct": stuck_minutes / len(rows) * 100,
        "open_positions": len(open_buy_edges),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="logs/minutes.csv")
    p.add_argument("--hours", type=float, default=0.0)
    p.add_argument("--min-samples", type=int, default=5)
    p.add_argument("--fees-bps", type=float, default=1.0,
                   help="Total round-trip taker fees in bps (both legs)")
    p.add_argument("--notional", type=float, default=500.0,
                   help="Notional per trade in USD")
    p.add_argument("--cap", type=float, default=1000.0,
                   help="max_position_usd per venue (config: max_position_usd)")
    p.add_argument("--fill", choices=["mean", "max"], default="mean",
                   help="Use minute mean or max edge as fill price (mean=conservative)")
    args = p.parse_args()

    try:
        rows = load_rows(args.csv, args.hours, args.min_samples)
    except FileNotFoundError:
        print(f"File not found: {args.csv}", file=sys.stderr)
        sys.exit(1)
    if not rows:
        print("No rows.", file=sys.stderr)
        sys.exit(1)

    span_h = (rows[-1]["ts"] - rows[0]["ts"]) / 3600.0 + 1/60
    prems = sorted(r["prem"] for r in rows)
    midline = round(sum(prems) / len(prems), 1) or 0.0  # use mean for more stability
    midline_median = round(pctl(prems, 50), 1) or 0.0

    buy_maxes  = sorted(r["buy_max"]  for r in rows)
    sell_maxes = sorted(r["sell_max"] for r in rows)
    buy_means  = sorted(r["buy_mean"] for r in rows)

    print(f"\n{'='*90}")
    print(f" ARBITRAGE BACKTEST — {len(rows)} minutes ({span_h:.1f}h data)")
    print(f"{'='*90}")
    print(f"\n MARKET STRUCTURE (Entropy vs Hedge)")
    print(f"  Premium (mid-to-mid)  mean={sum(prems)/len(prems):+.2f}  "
          f"median={midline_median:+.2f}  std={math.sqrt(sum((x-sum(prems)/len(prems))**2 for x in prems)/len(prems)):.2f} bps")
    print(f"  Premium range:  p5={pctl(prems,5):+.2f}  p25={pctl(prems,25):+.2f}  "
          f"p75={pctl(prems,75):+.2f}  p95={pctl(prems,95):+.2f} bps")
    print(f"  Buy edge (max): p50={pctl(buy_maxes,50):.1f}  p75={pctl(buy_maxes,75):.1f}  "
          f"p90={pctl(buy_maxes,90):.1f}  p95={pctl(buy_maxes,95):.1f} bps")
    print(f"  Sell edge(max): p50={pctl(sell_maxes,50):.1f}  p75={pctl(sell_maxes,75):.1f}  "
          f"p90={pctl(sell_maxes,90):.1f}  p95={pctl(sell_maxes,95):.1f} bps")
    print(f"\n CONFIG:  midline={midline:+.1f} bps (mean) | "
          f"fees={args.fees_bps:.1f} bps | notional=${args.notional:.0f} | "
          f"cap=${args.cap:.0f} | fill={args.fill}")
    print(f"\n NOTE: Position cap ${args.cap:.0f} allows max "
          f"{int(args.cap/args.notional)} concurrent open positions. "
          f"Sell trades RECYCLE position for future buys.\n")

    results = []
    for upper in UPPER_SWEEP:
        for lower in LOWER_SWEEP:
            r = simulate(rows, midline, upper, lower, args.fees_bps,
                         args.notional, args.cap, fill_at=args.fill)
            results.append(r)

    # Sort by daily_pnl descending
    results.sort(key=lambda x: -x["daily_pnl"])

    hdr = (f"{'upper':>6} {'lower':>6} | {'rt/day':>7} {'buy/d':>6} {'sell/d':>6} | "
           f"{'buyEdge':>8} {'sellCost':>9} {'netBps':>7} | "
           f"{'$/rt':>6} {'$/day':>8} | {'maxPos':>7} {'stuck%':>7}")
    print(hdr)
    print("-" * len(hdr))

    for r in results:
        sell_cost_bps = -r["avg_sell_edge_bps"] if r["n_sell"] > 0 else 0.0
        print(f"{r['upper']:>6.1f} {r['lower']:>6.1f} | "
              f"{r['rt_per_day']:>7.1f} {r['buy_per_day']:>6.1f} {r['sell_per_day']:>6.1f} | "
              f"{r['avg_buy_edge_bps']:>7.1f}b {sell_cost_bps:>8.1f}b {r['avg_rt_bps']:>6.1f}b | "
              f"{r['avg_rt_pnl']:>6.2f} {r['daily_pnl']:>8.2f} | "
              f"${r['max_pos_usd']:>6.0f} {r['stuck_pct']:>6.1f}%")

    print()
    # Best overall
    best = results[0]
    # Best round-trip quality (highest net_rt_bps, min 1 rt/day)
    quality = [r for r in results if r["rt_per_day"] >= 1.0]
    quality.sort(key=lambda x: -x["avg_rt_bps"])
    best_quality = quality[0] if quality else best
    # Most conservative (lowest stuck%, still profitable)
    low_stuck = sorted([r for r in results if r["stuck_pct"] < 10], key=lambda x: -x["daily_pnl"])
    best_low_stuck = low_stuck[0] if low_stuck else best

    print("=" * len(hdr))
    print(f"\n ★ BEST DAILY PnL:          upper={best['upper']:.0f}  lower={best['lower']:.0f}"
          f"  → {best['rt_per_day']:.1f} rt/day  ${best['daily_pnl']:.2f}/day")
    print(f" ★ BEST PER-TRADE QUALITY:  upper={best_quality['upper']:.0f}  lower={best_quality['lower']:.0f}"
          f"  → {best_quality['rt_per_day']:.1f} rt/day  net {best_quality['avg_rt_bps']:.1f}bps/rt"
          f"  ${best_quality['daily_pnl']:.2f}/day")
    print(f" ★ LOWEST STUCK (< 10%):    upper={best_low_stuck['upper']:.0f}  lower={best_low_stuck['lower']:.0f}"
          f"  → {best_low_stuck['stuck_pct']:.1f}% stuck  ${best_low_stuck['daily_pnl']:.2f}/day")

    r = best_quality
    print(f"""
 RECOMMENDED STARTING CONFIG (best per-trade quality):
 ─────────────────────────────────────────────────────
 thresholds:
   midline_bps: {midline}
   upper_bps:   {r['upper']}
   lower_bps:   {r['lower']}

 Interpretation:
   BUY entropy fires when buy_edge  >= {r['lower']-midline+args.fees_bps:.1f} bps (lower-midline+fees)
   SELL entropy fires when sell_edge >= {midline+r['upper']+args.fees_bps:.1f} bps (midline+upper+fees)

   Est. {r['rt_per_day']:.1f} completed round trips/day
   Est. ${r['daily_pnl']:.2f}/day at ${args.notional:.0f}/trade notional
   Net edge per round trip: {r['avg_rt_bps']:.1f} bps (buy {r['avg_buy_edge_bps']:.1f} - sell {-r['avg_sell_edge_bps']:.1f} bps)
   Max position seen: ${r['max_pos_usd']:.0f} (cap=${args.cap:.0f})
   Stuck by cap: {r['stuck_pct']:.1f}% of minutes

 ⚠ Caveats:
   1. Based on {len(rows)} minutes ({span_h:.1f}h) — more data = more reliable
   2. 'mean' fill assumes you don't always get the best price of the minute
   3. If spread stays permanently wide (never narrows), sell leg never fires →
      position gets stuck at cap. Monitor midline drift and update config.yaml.
   4. Increase --cap to trade larger; increase --notional proportionally.
""")


if __name__ == "__main__":
    main()
