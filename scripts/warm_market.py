#!/usr/bin/env python3
"""Warm or clear the market quote cache before a recording chunk.

    .venv/bin/python scripts/warm_market.py --warm      # deterministic fan-out
    .venv/bin/python scripts/warm_market.py --clear     # force a live fetch

Why both directions are needed, and why neither is a fake:

* Scene 5 narrates two agents running concurrently. With a cold quote cache the
  market agent spends ~17s on a network fetch and the turn takes 18.7s; with a
  warm one it takes 2.5s. The scene has to be driven to a fixed clock, so the
  cache is warmed first and the timing becomes deterministic. The answer is
  still computed; only the quote comes from disk, and the UI says so.

* Scene 7 narrates "market data is live, and keyless", and the page carries a
  freshness marker that reads "Saved copy" whenever a quote came from cache
  inside the 1800s TTL. So the cache is CLEARED before that chunk and the page
  fetches for real. Recording a live claim over a cached marker would be the
  dishonest option; so would editing the marker.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

SYMBOLS = ["NVDA", "VTI", "BND", "TLT", "SPY"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--warm", action="store_true")
    g.add_argument("--clear", action="store_true")
    args = ap.parse_args()

    db = REPO / "data" / "cache" / "market.db"

    if args.clear:
        if db.exists():
            con = sqlite3.connect(db)
            n = con.execute("select count(*) from kv").fetchone()[0]
            con.execute("delete from kv")
            con.commit()
            con.close()
            print(f"market.db cleared ({n} rows) - next fetch is live")
        else:
            print("market.db absent - next fetch is live")
        return 0

    from src.container import build
    deps = build()
    quotes = deps.market.quotes(SYMBOLS)
    print(f"warmed {len(quotes)} quotes, status={deps.market.last_status}")
    # History, not just quotes: the dual-intent question asks how an index has
    # performed, and that leg is the slow one - 17 of the 18.7s measured on a
    # cold run. Warming quotes alone changed nothing.
    for sym in SYMBOLS:
        rows, status = deps.market.history(sym)
        print(f"  history {sym}: {len(rows)} rows ({status})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
