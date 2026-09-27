---
title: "架构演进（归档）"
description: "IMPLEMENTATION_PLAN"
---

# Implementation Plan — 已 superseded

> 本文档原为 Phase 2（SentimentTrend 策略）的实施计划。
> 该计划整体被 2026-04 的 HonestTrend 家族 + Phase A/B 架构替代。

## 当前实际架构（2026-04-22）

- **Trend 策略家族**：`HonestTrendGeneric` 基类 + 4 个子类（15mDry / 1mMTF / 1mLive / Futures）
  - Phase A：spot long-only，pair list = ETH/BNB/SOL
  - Phase B：futures long+short，1x 杠杆 + FnG<70 空单过滤
- **Smart DCA**：双通道（周定投 + 事件驱动 daemon）累积 BTC
- **风控**：`risk_manager.py` 15%/20% kill-switch，所有 bot 共用
- **监控**：Telegram + Supabase + Grafana dashboard + 月度 walk-forward

## 完整架构与决策记录

- [README.md](../README.md) — 用户视角总览 + 文档索引
- [PHASE_B_FUTURES_SHORT.md](PHASE_B_FUTURES_SHORT.md) — Phase B 设计与回测
- [HYPEROPT_PYRAMID_TUNING.md](HYPEROPT_PYRAMID_TUNING.md) — 参数调优历程（含被拒绝的实验）
- [DRYRUN_HANDBOOK.md](DRYRUN_HANDBOOK.md) — 日常运维
- [GO_LIVE_CHECKLIST.md](GO_LIVE_CHECKLIST.md) — 实盘切换清单
