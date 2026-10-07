# Cost-aware trend research, October 2026

Research checked on 2026-10-07. The owner HTX account currently pays 0.2% per
side. Its trend allocation is 100 USDT per confirmed month, with 20 USDT entries
and reusable sale proceeds. The existing public record instead describes
independent equal-weight sleeves at 0.1% per side.

## Recent primary sources

- [Bysik and Ślepaczuk, 2026](https://arxiv.org/html/2606.00060v1): hourly BTC
  forecasting evaluated chronologically with execution costs. Their cost-aware
  forecast threshold reduces turnover; it is not evidence that our Donchian
  signals forecast enough profit to pay fees.
- [Yu et al., September 2026](https://arxiv.org/html/2609.34510v1): a common
  evaluation framework spanning historical replay, exchange paper trading and
  live trading. The applicable lesson is to measure execution and temporal
  transfer separately, with fixed candidate configurations.
- [Qu et al., September 2026](https://arxiv.org/html/2609.27051v1): separates
  adaptive factor proposals from statistical admission based on subsequent
  outcomes. Our three-rule comparison is descriptive; it does not implement
  their statistical referee or certify an edge.

These papers are research evidence, not a profitability guarantee for this
account. We have not reproduced their complete experiments.

## Implemented evaluation

`scripts/download_research_bars.py` collects public closed hourly OHLC into an
external cache. It needs no account credentials. `scripts/research_trend_costs.py`
uses `strategies/trend_replay.py` to compare these fixed candidates:

1. Existing 168/72 hourly Donchian rule.
2. Slower 336/144 rule.
3. 168/72 with a breakout buffer equal to the reference round-trip break-even
   price rise at 0.2% fees and 5 basis points adverse slippage per side.

The buffer is an experimental channel-distance requirement. Channel distance
is not an expected-return forecast, so clearing it does not guarantee profitable
execution. The buffer remains fixed across cost stresses to avoid changing
candidate definitions after inspecting results.

Signals use only the preceding closed candle and its prior high/low channel.
Execution occurs at the next candle's open with adverse slippage. Purchases lose
base currency to fees; sales lose quote currency. The model prioritises exits,
then entries in the existing asset order. It reserves the live adapter's 0.3%
fee allowance and caps an entry at 20 USDT. A skipped target may be retried while
it remains active; an already filled target cannot be bought twice.

The model assumes an initial 100 USDT trend deposit and another 100 at each
subsequent UTC month boundary. These are explicit simulated deposits, not
calendar credits to the live journal. Contributions buy valuation units at the
current open before trading; time-weighted return and drawdown use unit NAV,
so deposits cannot masquerade as profits or heal drawdowns. Hourly equity includes
cash and unrealised holdings. An additional end liquidation estimate deducts
future exit fees and slippage. BTC DCA is unchanged and excluded here.

Missing hours, insufficient warmup, duplicate timestamps and invalid OHLC fail
the replay. The downloader records its source and requested boundaries. It does
not fabricate missing observations. All generated bars, fills and reports remain
outside Git.

## Limits and promotion

Prices are Binance research OHLC, not HTX historical quotes. A uniform 5 USDT
minimum and fractional quantities approximate execution; exchange rounding,
dust, spread variation, outages and partial fills are not reproduced. Drawdown
is measured at hourly closes rather than intrahour extremes. The fixed current
universe has historical availability and survivorship limitations.

2024, 2025 and 2026 replays are separate descriptive windows. The universe was
selected using 2024–2025; those years are not out-of-sample for that selection.
Current research proposals have seen prior project results, so 2026 comparisons
are not untouched prospective tests of the new rules. Report every candidate
and cost stress, including failures; do not optimise a new grid on these results.

A historical winner is not automatically promoted. Promotion requires future
shadow observations with frozen rules, account-compatible costs, and evidence
that any improvement survives execution constraints and costs. This change adds
research tools and leaves the current live rule and funding policy intact.

## Commands

```sh
.venv-bots/bin/python scripts/download_research_bars.py /tmp/quant-cost-research-bars \
  --end 2026-10-07T13:00:00Z
.venv-bots/bin/python scripts/research_trend_costs.py /tmp/quant-cost-research-bars \
  --end 2026-10-07T13:00:00Z --output /tmp/quant-cost-research-2026.json
uv run --no-project --python .venv-bots/bin/python --with pytest -m pytest -q \
  tests/test_trend_replay.py tests/test_trend_fee_analysis.py
```

## Verification on 2026-10-07

- Thirteen focused tests passed, including a contribution arriving during a
  drawdown: the contribution changes cash and units but does not erase the loss.
  Baseline signal timestamps also match the public Donchian state machine.
- All 13 assets downloaded successfully for the requested historical interval;
  the replay accepted their full hourly coverage and lookback warmup.
- All 45 combinations completed: three fixed rules, five cost scenarios and
  three separate calendar windows (2024, 2025, 2026 through October 7).
- The existing fixed-signal sensitivity calculation independently reproduced
  all 13 public-record sleeve returns at the published fee before cost stresses.
- The replay's results did not support live promotion of either candidate:
  neither improved the baseline consistently across the evaluated windows.

Generated outputs are `/tmp/quant-cost-research-{2024,2025,2026}.json` and
`/tmp/quant-rule-cost-analysis.json`; download log is
`/tmp/quant-cost-research-download.log`. These files are local research artifacts,
not deployed private account reports. No live orders, credits or settings were
written by this research.

## Frozen prospective evaluation on Oracle

`research/trend-shadow-plan.json` registers the same three candidates at the
reference cost and the higher-cost stress before 2026-10-07 18:00 UTC. The
research process refuses first registration at or after that time. The plan
includes the replay source SHA256; changing its rules, costs, asset order or
implementation after registration aborts rather than rewriting the experiment.

`quant-trend-shadow.timer` runs hourly at :05 UTC on oracle-arm-002 under a
separate systemd DynamicUser. It has no account credentials, exchange order
adapter, private journal access or Telegram polling. State lives under
`/var/lib/quant-trend-shadow/`. `latest.json` is the current research status;
`checkpoints/` preserves each completed hourly evaluation. Repeating a checkpoint
returns its original result. Previously observed bar prefixes are hashed; a
subsequent upstream revision aborts instead of silently changing past evidence.

This is **prospective hourly OHLC replay with simulated fills**, not exchange
paper execution or an HTX quotation test. It starts flat with simulated funding;
it does not replicate the owner's existing holdings. During an outage it can
catch up from historical bars; this does not establish that an order could have
been executed at the assumed price in real time. The first complete-hour report
is expected at 19:05 UTC (03:05 Singapore on October 8). Until then, `waiting` is
the correct status. Candidate evaluation cannot change the live rule.

The replay also now matches the owner's engine when an old position is below
the minimum sell value: that residual position does not block a new target in
the same asset. Separate target holdings retain their own basis and proceeds.
A focused regression covers that case.
