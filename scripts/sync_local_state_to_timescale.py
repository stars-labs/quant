#!/usr/bin/env python3
"""
Incremental sync of local state files → TimescaleDB.
Runs quickly (seconds) so safe to invoke every few minutes via systemd timer.

One source (quant.nautilus_trades is the execution source of truth, written in-node):
  1. walk_forward_history/*.json → quant.wf_results

All upserts are idempotent by natural key.

Usage:
  sops exec-env secrets.env 'python scripts/sync_local_state_to_timescale.py'
  sops exec-env secrets.env 'python scripts/sync_local_state_to_timescale.py --only wf'
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras


PROJECT_DIR = Path(__file__).resolve().parent.parent
SCHEMA      = os.environ.get("TIMESCALE_SCHEMA", "quant")
DB_URL      = os.environ.get("TIMESCALE_URL")


def connect():
    if not DB_URL:
        sys.exit("TIMESCALE_URL not set")
    return psycopg2.connect(DB_URL)


# ---------------------------------------------------------------------------
# 1. walk_forward_history/*.json → quant.wf_results
# ---------------------------------------------------------------------------
def sync_wf(conn) -> dict:
    wf_dir = PROJECT_DIR / "walk_forward_history"
    if not wf_dir.exists():
        return {"total": 0, "note": "no dir"}

    rows = []
    skipped = 0
    for f in sorted(wf_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        # Older WF JSONs (pre-2026-04) didn't include `strategy`/`timeframe` at
        # the top level; skip those rather than crashing the whole sync.
        if not all(k in data for k in ("run_date", "strategy", "timeframe")):
            skipped += 1
            continue
        run_date = datetime.fromisoformat(
            str(data["run_date"]).replace("Z", "+00:00"))
        strategy = data["strategy"]
        timeframe = data["timeframe"]
        for r in data.get("results", []):
            rows.append((
                run_date, strategy, timeframe, r["label"],
                datetime.strptime(r["start"], "%Y%m%d").date(),
                datetime.strptime(r["end"],   "%Y%m%d").date(),
                r.get("status", "ok"),
                r.get("trades"),
                r.get("avg_profit_pct"),
                r.get("tot_profit_usdt"),
                r.get("tot_profit_pct"),
                str(f),
            ))

    if not rows:
        return {"total": 0}
    with conn.cursor() as cur:
        # wf_results has no natural unique key in schema, so we DELETE+INSERT per source file
        # to keep idempotent without duplicates.
        # For efficiency we just insert; later we can dedupe.
        # Dedup: keep last one per (run_date, strategy, timeframe, window_label)
        cur.execute(f"""
          DELETE FROM {SCHEMA}.wf_results
          WHERE json_source = ANY(%s)
        """, ([r[11] for r in rows],))
        psycopg2.extras.execute_values(cur, f"""
            INSERT INTO {SCHEMA}.wf_results
              (run_date, strategy, timeframe, window_label,
               window_start, window_end, status,
               trades, avg_profit_pct, tot_profit_usdt, tot_profit_pct,
               json_source)
            VALUES %s
        """, rows)
        conn.commit()
    return {"total": len(rows)}


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["wf"],
                    help="Run only one stage.")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    started = datetime.now(timezone.utc)
    out = {"started_at": started.isoformat(), "stages": {}}
    with connect() as conn:
        if not args.only or args.only == "wf":
            out["stages"]["wf"] = sync_wf(conn)
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    out["elapsed_sec"] = round(elapsed, 2)

    if args.quiet:
        print(json.dumps(out))
    else:
        print(f"sync complete in {elapsed:.2f}s")
        for stage, r in out["stages"].items():
            print(f"  {stage}: {r}")


if __name__ == "__main__":
    main()
