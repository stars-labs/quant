# BearDawnVerse Quant

[English](README.md) · **中文**

> 基于 **[NautilusTrader](https://nautilustrader.io)** 的加密 + 美股量化交易与研究系统，带一个在线公开仪表盘。
> 面向研究与学习——**不是**"一键致富"按钮。所有交易默认跑在 **testnet / 模拟盘**。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org)
[![NautilusTrader 1.227](https://img.shields.io/badge/NautilusTrader-1.227-green.svg)](https://nautilustrader.io)
[![Dashboard](https://img.shields.io/badge/在线-starslab.qzz.io-8a5cf6.svg)](https://starslab.qzz.io)

> **沿革：** 本仓库最初是一套 freqtrade 策略集，2026 年完整迁移到单一 NautilusTrader 技术栈（freqtrade 已移除）。部分历史目录保留作历史数据/报告。

---

## ⚠️ 免责声明

- **仅供教育与研究用途。** 交易有高风险，可能损失全部本金。
- 所有策略参数、回测结果、架构决策基于作者个人风险偏好——不构成投资建议，未必适合你。
- **不要在不理解代码的前提下实盘。** 用户自托管 HTX 执行器默认模拟，实盘必须在用户机器上明确授权并确认资金；Binance 研究节点仍为 testnet，IB 仍为 paper。
- 这是工具 / 信号 / 仪表盘项目——绝不代客理财、绝不资金池。

---

## ✨ 包含什么

- **用户自托管 HTX 实盘**（`runner/`）—— 密钥、下单、SQLite 账本和月度资金确认都留在用户的电脑或服务器，平台通过仅上传令牌展示账户数据。[安装与运行](runner/README.md)，[接入账户展示](https://starslab.qzz.io/execution)。
- **加密引擎**（`nautilus_crypto/`，Binance testnet）—— 智能定投 **accumulator**（按恐惧贪婪指数加权买入）、**Donchian** 趋势跟随、以及一个用主网公开数据推送暴涨/暴跌 Telegram 告警的**信号层**。
- **美股引擎**（`nautilus_equity/`，Interactive Brokers 模拟盘）—— **HonestTrend** EMA/ADX 策略在 IB 模拟盘实时运行（延迟行情），经 walk-forward 验证。
- **期权研究**（`nautilus_options/`）—— Deribit 现金担保看跌（CSP）回测（已研究，未部署）。
- **独立机器人与采集器**（`strategies/`）—— Kelly 仓位、风控管理器（回撤 kill-switch）、DCA 执行器、Deribit 监控、Telegram 告警分发，以及给仪表盘供数的采集器（行情、精选全球快讯、市场压力指数）。
- **量化实验室**（`strategies/quant_lab.py`、`quant_models.py`）—— 依赖极轻的研究模型（BSM、协整、GARCH、HMM、Markowitz、PCA…），可从仪表盘运行。
- **在线公开仪表盘** —— [starslab.qzz.io](https://starslab.qzz.io)：实时执行、回测沙盒、半导体供应链视图、3D 市场地球、市场压力指数、自助回测运行器。SvelteKit 跑在 Cloudflare Workers，中文默认双语。

---

## 🏗️ 架构

外部行情 API **绝不从浏览器/Cloudflare 直连**（Binance 同时封锁 Cloudflare 出口和大陆浏览器）。数据流分三层：

```
采集器 (Python)                 TimescaleDB @ oracle-arm-002          网页 (Cloudflare Workers)
strategies/*_collector.py  ──▶  quant.*  ──(PostgREST api.* 视图)──▶  SvelteKit 只读 api.panda.qzz.io
nautilus 实时节点               (+ Supabase：认证 + 实时)              starslab.qzz.io
```

- **实时交易节点**以系统服务跑在 **oracle-arm-002**（加密：accumulator / trend / signal，全 testnet）和一台本地机（美股 IB 模拟盘节点 + 监控定时器）。
- **数据层**：TimescaleDB（schema `quant`）通过 **PostgREST** `api.*` 视图只读暴露；**Supabase** 提供认证（GoTrue）+ Realtime。
- **用户交易所密钥**留在用户机器，网页不保存交易所密钥、不提供下单或远程启停。平台采集和数据库凭据由 SOPS 管理，与用户执行器分开。

---

## 📁 项目结构

```
runner/            用户自托管 HTX 执行器、安装、SQLite 账本、测试与展示上报
nautilus_crypto/    加密引擎（Nautilus）：accumulator.py、donchian.py、signal_*.py、live_*/run_* 节点
nautilus_equity/    经 Interactive Brokers 的美股引擎（独立 .venv，装了 nautilus_trader[ib]）
nautilus_options/   Deribit CSP 回测
strategies/         独立机器人 + 采集器（kelly_sizer、deribit_monitor、health_check、
                   news_collector、stress_index、market_collector、quant_lab…）
scripts/            运维脚本（TimescaleDB 同步、Binance 数据下载、testnet USDT 回收器…）
migrations/         TimescaleDB schema（库 `api`、schema `quant`）→ PostgREST `api.*` 视图
web/apps/app/       SvelteKit 仪表盘（Cloudflare Workers）· web/apps/docs/ = Astro 文档站
tests/              pytest 风格测试（直接用 venv 解释器跑）
```

关键文档：[`CLAUDE.md`](CLAUDE.md) / [`AGENTS.md`](AGENTS.md)（贡献者与 agent 指南）、[`STRATEGY_LEADERBOARD.md`](STRATEGY_LEADERBOARD.md)（策略研究日志）、[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)。

---

## 🚀 快速开始

Python 用本地 `uv` 虚拟环境（无 Makefile，无全局 pytest——直接调 venv 解释器）：

```bash
# nautilus venv（含 nautilus_trader 1.227 + ib）；加密和美股回测都用它
P=nautilus_equity/.venv/bin/python

# 跑加密回测
$P nautilus_crypto/run_accumulation.py        # 或 run_trend_crypto.py / run_portfolio_trend.py

# 跑美股回测
$P nautilus_equity/run_honest_equity.py

# 刷新行情数据（ccxt → user_data/data/ 下的 feather）
$P nautilus_crypto/download_binance.py

# 跑单个测试模块（无 pytest 收集器——直接驱动 test_* 函数）
$P -c "import sys; sys.path.insert(0,'nautilus_crypto'); import test_signal_detect as t; \
  [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"
```

网页仪表盘（`cd web/apps/app`，用 [pnpm](https://pnpm.io)）：

```bash
pnpm run dev       # 本地开发服务器
pnpm run check     # svelte-check 类型检查
pnpm run lint      # prettier --check + eslint
pnpm run deploy    # vite build && wrangler deploy   （不是 `pnpm deploy`）
```

密钥（sops + GPG）：

```bash
sops -d secrets.env                              # 查看
sops exec-env secrets.env '<你的命令>'           # 把密钥注入某条命令的环境
```

---

## 🔐 硬性护栏

- 用户自托管 HTX 执行器默认模拟；实盘必须本地授权并确认资金。Binance 仍为 testnet，IB 仍为 paper。
- Binance 在 Nautilus 上执行需要 **Ed25519** 密钥；纯数据的主网节点**不传**任何密钥。
- 绝不提交明文密钥、虚拟环境、或生成的数据/catalog/报告。

---

## 📜 许可证

[MIT](LICENSE)。按原样提供，不附带任何担保——见上方免责声明。
