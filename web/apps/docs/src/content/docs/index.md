---
title: Crypto Quant 文档
description: 一个覆盖趋势跟随、智能 DCA、期权监控、风控的加密货币量化交易系统
template: splash
hero:
  tagline: BTC 走 DCA，ETH/BNB/SOL 走 trend，futures 做空对冲。<br/>2017-2026 全历史回测验证，所有数据可视化。
  actions:
    - text: 📊 Dashboard
      link: https://quant.panda.qzz.io
      icon: external
      variant: primary
    - text: 🧭 架构总览
      link: /docs/architecture/
      icon: right-arrow
    - text: ⚙️ GitHub
      link: https://github.com/xiongchenyu6/freqtrade-strategies
      icon: external
      variant: minimal
---

## 系统组成

| 组件 | 文档 |
|------|------|
| HonestTrend 家族（15mDry / 1mMTF / Futures） | [策略](/docs/strategies/honest-trend-report/) |
| Phase B 期货 L+S 对冲 | [Phase B](/docs/strategies/phase-b-futures-short/) |
| Walk-Forward 验证方法 | [WF](/docs/research/walk-forward-full-history/) |
| Hyperopt 参数调优 | [Hyperopt](/docs/research/hyperopt-pyramid-tuning/) |

## 核心原则

- 🎯 **信号驱动，不择时**：EMA 交叉 + ADX + FnG 三重确认
- 🛡️ **20% DD kill-switch**：超过就 RETIRE，永不 Martingale
- 🔄 **Walk-forward 跨 regime 验证**：不止看"全历史好"，要看每个独立市场窗口
- 📊 **所有决策可追溯**：每次回测、每次 DCA、每次告警都在 DB 里

## 现在什么在跑

访问 [🎯 Dashboard](https://quant.panda.qzz.io) 看实时数据。
