# Dry-Run 操作手册 — HonestTrend 全家桶

**这是给你每天 5 分钟扫一眼用的文档。**
完整技术分析看 [`HONEST_TREND_REPORT.md`](HONEST_TREND_REPORT.md) 与 [`PHASE_B_FUTURES_SHORT.md`](PHASE_B_FUTURES_SHORT.md)。

> **2026-04-22 架构更新**：采纳 Phase A（BTC→DCA，trend → ETH/BNB/SOL alts）+ Phase B（futures L+S 对冲）。下面 pair list 和 port 分配反映最新状态。

---

## 一、当前运行的 bot（3 个 dry-run 并行）

| 策略 | Config | Market | 方向 | Pairs | Port |
|------|--------|--------|------|-------|-----:|
| `HonestTrend15mDry` | `config_dryrun_honest15m.json` | spot | long-only | ETH/BNB/SOL | 8082 |
| `HonestTrend1mMTF` | `config_dryrun_honest1mmtf.json` | spot 1m+4h gate | long-only | ETH/BNB/SOL | 8083 |
| `HonestTrendFutures` | `config_dryrun_honestfutures15m.json` | **futures** | **long+short** | ETH/BNB/SOL | **8084** |

所有三个共用参数：
- 父类 `HonestTrendGeneric`
- 模拟资金 **10,000 USDT**
- 最大同时持仓 3
- Stake 1500 USDT/trade（pyramid 后可达 3900）
- SQLite DB `user_data/tradesv3_<name>_dryrun.sqlite`
- 日志目录 `logs/<name>_dryrun_*.log`

**BTC 不在 trend 池子里** —— BTC 的 alpha 通过 Smart DCA 双通道累积（见本文最末节）。

---

## 二、策略逻辑（信号规则）

### 入场（**同时满足以下 6 个条件**才买）

1. **EMA 金叉**：EMA(94, 15m) 上穿 EMA(139, 15m)
   - 94 根 15m 蜡烛 = 23.5 小时
   - 139 根 15m 蜡烛 = 34.75 小时
   - 比率 1.48x（不是经典 2x，Stage 1-3 验证这个比率更 robust）
2. **+DI > −DI**（趋势方向确认）
3. **ADX > 18**（趋势强度足够）
4. **成交量 > 过去 24h 均值**（量能确认）
5. **恐惧贪婪指数 FnG < 80**（唯一被数据验证的情绪防御规则）
6. 当前 bar 成交量 > 0（非空 bar）

### 出场（**任一触发即卖**）

1. **EMA 死叉**：EMA(94) 下穿 EMA(139)
   - 同时要求持仓 ≥ 12 小时（避免 15m 噪声触发）
2. 手动 force exit（Telegram `/forcesell`）
3. **止损**：
   - Spot bots (15mDry / 1mMTF)：**无止损**（`stoploss = -0.99`），Stage 1 证明紧止损会抹杀趋势跟随 edge
   - Futures bot：**−8% 硬止损**（期货不能像 spot 那样裸奔，防强平）
4. 风控：`risk_manager.py` 的账户级别回撤 kill-switch（15% pause / 20% retire）

### Futures short 专属规则

只有 `HonestTrendFutures` 会做空：
- **空入场**：EMA 死叉 + `minus_di > plus_di` + ADX > 18 + FnG **< 70**
- **FnG > 70 禁空**（不在 euphoria 里被轧空）
- **FnG < 30 softly 放大**（恐慌底做空效率高）
- **杠杆 1x**（无强平风险，纯吃方向 alpha）
- **Funding 成本**：约年化 4% 拖累（backtest 已含）

---

## 三、预期数据（你接下来会看到什么）

基于 2024-01 到 2026-04 回测（OOS 段 2025-07 到 2026-04）：

| 指标 | 预期范围 |
|------|---------|
| 每周交易次数 | **1–3 笔**（大约） |
| 月交易次数 | 4–10 笔 |
| 平均单笔持仓 | **2–3 天** |
| 胜率 | **35–45%**（典型 40%） |
| 平均盈利交易 | +3% 到 +10% |
| 平均亏损交易 | −1% 到 −4% |
| 最差单笔 | **−23%**（历史极值，1% 概率） |
| 最长连败 | **7 笔**（历史极值） |
| 单月盈亏方差 | 很大 — **允许单月亏损**，看半年滚动 PF |

### 触发后的典型交易流

```
[Telegram: Entry Fill] BTC/USDT at 93,250 USDT — 3,160 USDT stake (trend_15m tag)
    ↓
  (持仓 2–3 天，EMA 94 保持在 EMA 139 之上)
    ↓
[Telegram: Exit Fill] BTC/USDT at 95,800 USDT — +2.7% profit (trend_exit tag)
```

---

## 四、每日 5 分钟检查清单

**每天做**（1 分钟）：
- [ ] 扫一眼 Telegram，是否有 `🚨 Risk State Change` 告警？
  - 没有 → 继续。有 → 立刻看 §七
- [ ] 有 Entry/Exit 推送吗？大致符合预期频率（一周 1-3 笔）吗？

**每周做**（3 分钟）：
```bash
# 看当前状态
python $PROJECT_DIR/scripts/risk_monitor.py status

# 或者 Telegram 发 /status 给 bot，它会回：
#   Current balance / Open trades / Total profit
```

期望看到：
- Status: `ACTIVE`
- Drawdown: **< 10%**（正常）；10-15% → 警惕；≥15% → 自动 PAUSE
- Rolling PF (50 trades): **> 1.2** 后期；≥1.0 前期积累中；<1.0 警惕

**每月做**（10 分钟）：
- 1 号 06:00 会自动运行 walk-forward check，Telegram 告警如果 <50% 窗口盈利
- 主动对比：实盘 dry-run 统计 vs 最新 walk-forward backtest
  ```bash
  curl -s http://127.0.0.1:8082/api/v1/profit | jq
  ```

---

## 五、Telegram 能看到哪些消息

### Freqtrade bot 本身（由 HonestTrend15mDry 发）

| 触发 | 示例 |
|------|------|
| Startup | `Exchange: binance / Timeframe: 15m / Strategy: HonestTrend15mDry` |
| 入场（下单） | `Buying BTC/USDT at 93250 USDT, tag: trend` |
| 入场成交 | `New trade filled BTC/USDT at 93250 USDT — 3160 USDT stake` |
| 出场 | `Selling BTC/USDT at 95800 USDT — +2.7% profit, tag: trend_exit` |
| 出场成交 | `Trade closed BTC/USDT: +2.7% (+86 USDT)` |
| Warning | `Dry run is enabled. All trades are simulated.`（启动时一次） |
| Protection triggered | 某个 pair 被冷却（当前策略没有 protection 配置，不会出现） |

交互命令（发给 bot）：
- `/status` — 当前开仓
- `/profit` — 累计盈亏
- `/daily` / `/weekly` / `/monthly` — 周期统计
- `/trades` — 最近交易列表
- `/performance` — 按 pair 的表现
- `/balance` — 模拟钱包余额
- `/forceexit <trade_id>` — 强制平某笔（dry-run 也有效）
- `/stopentry` — 暂停开新仓（不影响现有持仓）
- `/help` — 完整命令列表

### Risk Monitor（由 `scripts/risk_monitor.py` 每 4h 发）

**只在状态变化时发**，正常不会刷屏。

| 触发 | 消息样式 |
|------|---------|
| DD 首次 ≥ 15% | `🚨 Risk State Change: ACTIVE → PAUSED. Drawdown 15.2% ≥ 15%...` |
| DD 恢复到 <10% | `🚨 Risk State Change: PAUSED → ACTIVE. Drawdown recovered to 9.0%...` |
| DD ≥ 20% | `🚨 Risk State Change: ACTIVE → RETIRED. Drawdown 21.3% ≥ 20%. Manual reset required.` |
| 6 个月 + PF<1.2 | `🚨 Risk State Change: ACTIVE → RETIRED. After 180d live, rolling PF 1.10 < 1.20.` |
| 手动 pause/retire | `⏸ Manual PAUSE` / `🛑 Manual RETIRE` |

### Walk-Forward（每月 1 号 06:00，`scripts/walk_forward_check.py`）

| 健康度 | 消息 |
|--------|-----|
| ≥50% 窗口盈利 | 不告警（静默通过） |
| <50% 窗口盈利 | `⚠️ EDGE DEGRADING: <50% windows profitable` |
| 0/4 窗口盈利 | `🚨 EDGE DEAD: 0 windows profitable. Consider retiring.` |

### KOL Alerts（独立于本策略，`strategies/telegram_alerts.py`）

每 30 分钟跑一次。**新的修复**：每条告警现在都是可点击链接 → 跳到原文 Google News 验证。

```
🟢 TRUMP (+0.50)
[Trump endorses crypto at rally](https://news.google.com/rss/articles/...)
```

---

## 六、什么是"正常"？

### ✅ 这些都正常（不要紧张）

- **连续 1-2 周没开仓** — EMA 还没交叉，市场没给信号。策略设计就是等好机会。
- **某一天 BTC 暴跌 10% 但 bot 没反应** — 只有 EMA 死叉时才退出。不设止损是刻意的。
- **单笔交易亏 5-10%** — 在分布范围内，CVaR 95% = −9.13%
- **某个月整体亏损** — 正常，看半年/年滚动
- **FnG > 80 时完全不开仓** — 这是规则，极度贪婪期更容易回撤
- **跟 BTC 同涨跌，但幅度小** — 策略偏 beta，不是全天候对冲

### ⚠️ 这些要关注（不一定马上行动）

| 现象 | 合理解释 / 行动 |
|------|-----------------|
| 连续 5 笔亏损 | 正常范围（历史最多 7 连亏），继续观察 |
| DD 10-15% | 接近 PAUSE 阈值，查一下 `risk_monitor.py status`，别干预 |
| 一个月没任何交易 | FnG 长期 > 80，或 ADX < 18。查 Fear & Greed 和 BTC 趋势 |
| 某笔持仓超过 10 天没动 | 极少见，检查 EMA 值 |
| 滑点 > 0.1%（实盘启动后） | 盘口深度不够，考虑降低交易对数量 |

### 🚨 这些是红线（必须立刻看）

| 现象 | 行动 |
|------|-----|
| Telegram 收到 `RETIRED` 告警 | 策略已自动退役，**不要直接 reset**，先调查原因 |
| DD ≥ 15% 且 PAUSED | 等自动 resume（DD 恢复到 <10%），不要手动 reset |
| 单笔亏 >25%（超过历史最差） | 有 black swan 事件，手动 pause，检查市场 |
| 连续 2+ 月 walk-forward 告警 | Edge 在衰退，考虑 retire |
| Bot 进程消失（`pgrep` 无结果） | 查日志，重启 bot，看 journald 看崩溃原因 |
| 实盘 vs dry-run 盈亏差 >3%/月 | 滑点/延迟比预期大，考虑减仓或换策略 |

---

## 七、如何干预（应急手册）

### 暂停新仓（不影响现有持仓）

```bash
# 方法 1：通过 risk manager（推荐，会发 Telegram 告警）
cd $PROJECT_DIR
python scripts/risk_monitor.py pause --note "你的原因"

# 方法 2：通过 Telegram 命令
# 给 bot 发：/stopentry
```

### 完全退役（需要手动 reset 才能恢复）

```bash
python scripts/risk_monitor.py retire --note "你的原因"
```

### 重置为 ACTIVE（慎用）

```bash
python scripts/risk_monitor.py reset --note "你的原因"
```

### 停止 bot 进程

```bash
pkill -TERM -f "config_dryrun_honest15m"
# 等待 5-10 秒完全退出
pgrep -af "config_dryrun_honest15m"  # 确认退出
```

### 重启 bot

```bash
cd $PROJECT_DIR
./scripts/start_honest_trend.sh dryrun
```

### 强平某笔交易

```bash
# Telegram 发：/forceexit <trade_id>
# 或 curl API：
curl -X POST http://127.0.0.1:8082/api/v1/forceexit \
  -H "Content-Type: application/json" \
  -d '{"tradeid": "1"}'
```

### 查看实时日志

```bash
tail -f $PROJECT_DIR/logs/honest15m_dryrun_*.log
```

---

## 八、从 dry-run 过渡到实盘（路线图）

**不要着急开实盘。先让 dry-run 跑至少 2-4 周验证以下条件**：

### 过渡检查清单

- [ ] dry-run 累计 ≥ **20 笔交易**（统计意义）
- [ ] Rolling PF ≥ **1.2**
- [ ] 最大 DD < **12%**
- [ ] 没有任何 RETIRED 事件
- [ ] 没有任何 "实盘 vs dry-run" 偏离（dry-run 只能拿来和回测对比）
- [ ] Walk-forward 月度 check 至少一次 4/4 通过

### 过渡步骤

1. **把 Binance API key 加入 SOPS**（见部署文档）
2. 启动实盘：`./scripts/start_honest_trend.sh live`
3. **保持 dry-run 同时运行** — 15m dry-run 作为 shadow validator，对比延迟/滑点
4. 实盘首月：**只用 1,000 USDT**（不要一开始就 10K）
5. 每月用 risk_monitor 检查，稳定才逐步增加到 10K

---

## 九、常见问题自问自答

**Q: 为什么 1 周了还没开仓？**
A: EMA 94/139 需要非常明确的上升趋势。看 BTC 15m 图，EMA 94 和 139 要从下方穿过上方。如果市场在震荡/下跌，就不会开仓。这是 feature，不是 bug。

**Q: FnG 目前是多少可以查？**
A: Dashboard `http://localhost:3000` 实时显示。或 `curl https://api.alternative.me/fng/?limit=1`。当前 ≥ 80 时 bot 完全不开仓。

**Q: Dry-run 和回测的差别会有多大？**
A: 理论上应该很小（都用同一套市场数据）。实盘才会有显著差别（真实成交延迟、盘口深度、手续费分层）。Dry-run 主要验证策略**逻辑没 bug**，而非盈亏精度。

**Q: 1m live 什么时候启动？**
A: 由你决定。建议等 dry-run 跑 2-4 周确认稳定后启动。命令已 ready：`./scripts/start_honest_trend.sh live`（前提 SOPS 有 Binance key）。

**Q: 如果 dry-run 持续亏钱怎么办？**
A: 看是哪种亏：
- **单月亏，半年 PF 仍 >1.2** → 正常，不动。
- **半年 PF < 1.0，交易数 > 50** → 实盘不要启动。考虑退役或换策略。
- **DD > 15%** → risk_monitor 自动 pause，看 state，不要人工 reset。

**Q: 我能同时跑多个策略吗？**
A: 可以，当前 3 个 bot 并行（15m spot 8082 / 1m MTF spot 8083 / 15m futures L+S 8084）+ 2 个 daemon（event_reactor + event_dca_bot）。每个 bot 独立端口 + 独立 SQLite DB。Telegram 共用一个 chat（各 bot 通过 bot_name 区分自己的消息）。

**Q: 为什么选 ETH/BNB/SOL？为啥不要 BTC？**
A: Phase A (2026-04-22) 采纳：BTC 走 DCA 累积（周+事件），不在 trend 池子里。原因：BTC 在 trend 策略上的回报低于它自己的 DCA baseline，且用户长期看涨 BTC（DCA 积累更合适）。ETH/BNB/SOL 是高 beta alts，trend 策略在这里发挥更好。

**Q: 之前说 SOL 不适合，为啥现在又加回来？**
A: 之前的结论是在老框架（BTC 为主）下。Phase A 切到 spot alts-only 后重新 walk-forward：SOL 作为高 beta alts 吃到更多 alpha（W4 2021 +143%）。另外 futures L+S 能对冲 SOL 的下行风险（W5 2022 LUNA，SOL spot 亏 17%，futures L+S 反赚 48%）。

---

## 十、相关文件索引

```
主要文档
├── docs/HONEST_TREND_REPORT.md     完整技术分析（为什么选这个策略）
├── docs/DRYRUN_HANDBOOK.md         ← 你现在读的这个（日常操作）
├── risk_state.json                 当前 risk manager 状态（运行时生成）
├── walk_forward_history/           月度 walk-forward 归档

活跃策略
├── strategies/HonestTrendGeneric.py    基类（所有 HonestTrend* 继承）
├── strategies/HonestTrend15mDry.py     15m spot long-only（port 8082）
├── strategies/HonestTrend1mMTF.py      1m MTF spot long-only（port 8083）
├── strategies/HonestTrendFutures.py    15m futures L+S（port 8084，Phase B）
├── strategies/HonestTrend1mLive.py     1m 实盘（旧 pair list，待切 A5）
├── strategies/dca_executor.py          DCA 执行引擎（周/事件共用）
├── strategies/event_dca_bot.py         事件驱动 DCA daemon（WebSocket）
├── strategies/risk_manager.py          状态机
├── strategies/telegram_alerts.py       告警模块

Config
├── configs/config_dryrun_honest15m.json           A5 spot long
├── configs/config_dryrun_honest1mmtf.json         A5 spot 1m MTF
├── configs/config_dryrun_honestfutures15m.json    Phase B futures L+S
├── configs/config_live_honest1m.json              旧 live（未切 A5）
├── configs/backtest/config_backtest_15m_alts_a5.json     A5 回测
├── configs/backtest/config_backtest_15m_futures_a5.json  Phase B 回测
├── configs/backtest/config_backtest_*.json        其它

Scripts
├── scripts/start_honest_trend.sh       启动脚本
├── scripts/risk_monitor.py             监控 + CLI
├── scripts/walk_forward_check.py       月度验证

Systemd timers（每 4h / 每月）
├── ~/.config/systemd/user/crypto-risk-monitor.{service,timer}
├── ~/.config/systemd/user/crypto-walkforward.{service,timer}

归档（don't touch，且已 .gitignore 不进公共库）
├── docs/RETIRED_STRATEGIES.md          退役策略记录（代码已删，只留原因+教训）
```

---

## 十一、Smart DCA 双通道（BTC 专属）

Trend 策略不碰 BTC，BTC 由这套 DCA 组合负责累积：

### 周定投（时间驱动）
- 服务：`crypto-dca.timer` → `dca_executor.py`
- 频率：每周一 00:00 SGT
- 金额：`$500 base × multiplier (0.0-3.0)`，由 FnG + cycle factors + KOL 加权
- 状态：dry-run（`DCA_LIVE_ENABLED` 未设）
- 日志：`journalctl --user -u crypto-dca.service -f`

### 事件驱动（WebSocket daemon）
- 服务：`crypto-event-dca.service` → `event_dca_bot.py`
- 类型：always-on，监听 Binance aggTrade WebSocket
- 触发：4 层信号（FLASH 1m>3% / FAST 5m>5% / SUSTAIN 24h>10% / CAPITUL 30d DD>25%）
- 预算：每月 $2000 reserve，$700/trigger（FnG<20 ×1.5, >60 ×0.7）
- 限制：72h cooldown，最多 3 次/月
- 状态文件：`event_dca_state.json`
- 自检：`python strategies/event_dca_bot.py --self-test`

两个通道**预算独立**（不共享），都调 `dca_executor.py` 执行。**打开 live**：在 SOPS `secrets.env` 加 `DCA_LIVE_ENABLED=true` + Binance spot API key，两个通道同时生效。

---

## 十二、核心原则（一句话版）

1. **Dry-run 积累样本，不急着开实盘**
2. **每天扫 Telegram，每周看 status，每月看 walk-forward**
3. **规则已编码，不要手动优化**
4. **红线触发时相信状态机，不要急着 reset**
5. **单月亏损正常，半年 PF < 1.2 才是警报**

**记住 Taleb 的话：策略不会慢慢死，是断崖式失效。** 提前写好 kill-switch，断崖来时就是 kill-switch 救你，不是你的判断救你。

---

*最后更新: 2026-04-20. 出问题时先看这份文档，再看 `HONEST_TREND_REPORT.md` 里的背景。*
