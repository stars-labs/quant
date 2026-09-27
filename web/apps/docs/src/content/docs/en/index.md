---
title: Crypto Quant Docs
description: A crypto quant trading system covering trend following, smart DCA, options monitoring, and risk
template: splash
hero:
  tagline: BTC runs DCA, ETH/BNB/SOL run trend, futures handle short hedging.<br/>Full-history backtest (2017–2026), every decision is visualized.
  actions:
    - text: 📊 Dashboard
      link: https://quant.panda.qzz.io
      icon: external
      variant: primary
    - text: 🧭 Architecture
      link: /docs/en/architecture/
      icon: right-arrow
    - text: ⚙️ GitHub
      link: https://github.com/xiongchenyu6/freqtrade-strategies
      icon: external
      variant: minimal
---

## System components

| Component | Docs |
|------|------|
| HonestTrend family (15mDry / 1mMTF / Futures) | [Strategies](/docs/en/strategies/honest-trend-report/) |
| Phase B futures L+S hedge | [Phase B](/docs/en/strategies/phase-b-futures-short/) |
| Walk-Forward methodology | [WF](/docs/en/research/walk-forward-full-history/) |
| Hyperopt parameter tuning | [Hyperopt](/docs/en/research/hyperopt-pyramid-tuning/) |

## Core principles

- 🎯 **Signal-driven, not timing-driven**: EMA crossover + ADX + FnG triple confirmation
- 🛡️ **20% DD kill-switch**: if breached, RETIRE — never Martingale
- 🔄 **Walk-forward regime validation**: not just "good in full history" — good in every independent window
- 📊 **Every decision is traceable**: every backtest, every DCA, every alert sits in the DB

## What's running now

Visit [🎯 Dashboard](https://quant.panda.qzz.io) for live data.
