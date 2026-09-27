# Implementation Plan — superseded

> This document was originally the implementation plan for Phase 2 (SentimentTrend strategy).
> The plan has been superseded in whole by the 2026-04 HonestTrend family + Phase A/B architecture.

## Current actual architecture (2026-04-22)

- **Trend strategy family**: `HonestTrendGeneric` base class + 4 subclasses (15mDry / 1mMTF / 1mLive / Futures)
  - Phase A: spot long-only, pair list = ETH/BNB/SOL
  - Phase B: futures long+short, 1x leverage + FnG<70 short filter
- **Smart DCA**: dual-channel (weekly DCA + event-driven daemon) accumulating BTC
- **Risk control**: `risk_manager.py` 15%/20% kill-switch, shared by all bots
- **Monitoring**: Telegram + Supabase + Grafana dashboard + monthly walk-forward

## Full architecture and decision records

- [README.md](../README.md) — User-facing overview + documentation index
- [PHASE_B_FUTURES_SHORT.md](PHASE_B_FUTURES_SHORT.md) — Phase B design and backtest
- [HYPEROPT_PYRAMID_TUNING.md](HYPEROPT_PYRAMID_TUNING.md) — Parameter tuning history (including rejected experiments)
- [DRYRUN_HANDBOOK.md](DRYRUN_HANDBOOK.md) — Daily operations
- [GO_LIVE_CHECKLIST.md](GO_LIVE_CHECKLIST.md) — Live-switchover checklist
