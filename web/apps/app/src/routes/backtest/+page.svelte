<script lang="ts">
	// Self-service backtest playground (Phase 1 MVP). Auth-gated: a logged-in user picks a
	// predefined strategy + params, submits a job (PostgREST insert, RLS-scoped), and the
	// game-box runner executes it and writes results we poll for. See PLAYGROUND_PLAN.md.
	import { page } from '$app/stores';
	import { user } from '$lib/auth';
	import { type Lang } from '$lib/i18n';
	import {
		STRATEGIES,
		COMMODITY_ASSETS,
		CRYPTO_ASSETS,
		PORTFOLIO_PRESETS,
		PORTFOLIO_COMPONENTS,
		submitBacktest,
		myJobs,
		jobResult,
		type Strategy,
		type BacktestJob,
		type BacktestResult,
		type PortfolioPresetKey
	} from '$lib/backtests';
	import { createSignal, signalsVersion, type NewSignal } from '$lib/signals';
	import { onMount, onDestroy } from 'svelte';
	import AlertSubscribe from '$lib/components/alert-subscribe.svelte';
	import MySignals from '$lib/components/my-signals.svelte';
	import { track } from '$lib/track';

	const lang = $derived<Lang>($page.data.lang ?? 'zh');
	const en = $derived(lang === 'en');

	// ── Dynamic per-strategy form state ──────────────────────────────────────
	// We keep one bag of param values keyed by the param name; switching strategy
	// re-seeds it from that strategy's defaults so the inputs always render valid.
	type StratKey = keyof typeof STRATEGIES;
	type NumParam = { min: number; max: number; default: number; step?: number };
	type ChoiceParam = { choices: readonly string[]; default: string };
	type AnyParam = NumParam | ChoiceParam;

	const isChoice = (p: AnyParam): p is ChoiceParam => 'choices' in p;

	let strategy = $state<StratKey>('honest_trend');
	const cfg = $derived(STRATEGIES[strategy]);

	let asset = $state<string>(STRATEGIES.honest_trend.assets[0]);
	let tf = $state<string>(STRATEGIES.honest_trend.timeframes[0]);
	let params = $state<Record<string, number | string>>(seedParams('honest_trend'));
	// Data window: 0 = 全部历史 (omit period_years from the payload); 1/2/3/5 = trailing years.
	let periodSel = $state(0);

	// honest_trend accepts ANY US ticker (runner validates against its ~9.5k-symbol list
	// server-side) plus the commodity continuous futures; the suggested trio additionally
	// has hourly bars, everything else — commodities included — is 1d only.
	const HONEST_SUGGESTED = STRATEGIES.honest_trend.assets as readonly string[];
	const commodity = $derived(COMMODITY_ASSETS.find((c) => c.sym === asset));
	const isCatalogAsset = $derived(strategy !== 'honest_trend' || HONEST_SUGGESTED.includes(asset));
	// master_portfolio has no timeframes (multi-asset daily) — empty list, controls hidden.
	const tfChoices = $derived<readonly string[]>(
		'timeframes' in cfg ? (isCatalogAsset ? cfg.timeframes : ['1d']) : []
	);
	// Force tf back into range when a non-catalog ticker or commodity (1d only) is typed.
	$effect(() => {
		if (tfChoices.length > 0 && !tfChoices.includes(tf)) tf = tfChoices[0];
	});

	function seedParams(s: StratKey): Record<string, number | string> {
		const out: Record<string, number | string> = {};
		const ps = STRATEGIES[s].params as Record<string, AnyParam>;
		for (const [k, p] of Object.entries(ps)) out[k] = p.default;
		return out;
	}

	// Re-seed asset/tf/params whenever the selected strategy changes.
	function onStrategyChange(s: StratKey) {
		strategy = s;
		const c = STRATEGIES[s];
		if ('assets' in c) {
			asset = c.assets[0];
			tf = c.timeframes[0];
		}
		params = seedParams(s);
		err = '';
	}

	// Friendly labels for param keys (fallback: prettified key).
	const PARAM_LABELS: Record<string, [zh: string, en: string]> = {
		ema_fast: ['快线 EMA', 'EMA fast'],
		ema_slow: ['慢线 EMA', 'EMA slow'],
		entry_lb: ['入场回看', 'Entry lookback'],
		exit_lb: ['离场回看', 'Exit lookback'],
		risk_frac: ['风险比例', 'Risk fraction'],
		base_buy_usd: ['每次买入 (USD)', 'Base buy (USD)'],
		interval_bars: ['间隔 (天)', 'Interval (days)'],
		mode: ['模式', 'Mode'],
		preset: ['配方', 'Recipe'],
		rebalance_months: ['再平衡', 'Rebalance']
	};
	function paramLabel(k: string): string {
		const l = PARAM_LABELS[k];
		if (l) return en ? l[1] : l[0];
		return k.replace(/_/g, ' ');
	}

	// Display label for a choice-param option: preset keys → recipe names, rebalance
	// months → 每月/每季/每年; everything else (e.g. mode smart/naive) stays raw.
	const REBALANCE_LABELS: Record<string, [zh: string, en: string]> = {
		'1': ['每月', 'Monthly'],
		'3': ['每季', 'Quarterly'],
		'12': ['每年', 'Yearly']
	};
	function choiceLabel(k: string, c: string): string {
		if (k === 'preset') {
			const p = PORTFOLIO_PRESETS[c as PortfolioPresetKey];
			if (p) return en ? p.en : p.zh;
		}
		if (k === 'rebalance_months') {
			const m = REBALANCE_LABELS[c];
			if (m) return en ? m[1] : m[0];
		}
		return c;
	}

	// ── master_portfolio display helpers ──────────────────────────────────────
	// Weight chips: 'SPY 美股大盘 30%' per component (unknown tickers fall back to raw).
	function weightChips(weights: Record<string, number>): string[] {
		return Object.entries(weights).map(([sym, w]) => {
			const l = PORTFOLIO_COMPONENTS[sym];
			return l ? `${sym} ${en ? l[1] : l[0]} ${w}%` : `${sym} ${w}%`;
		});
	}
	// Recipe of the preset currently picked in the form (undefined for other strategies).
	const selectedPreset = $derived(
		strategy === 'master_portfolio'
			? PORTFOLIO_PRESETS[params.preset as PortfolioPresetKey]
			: undefined
	);
	// metrics.config.weights for a finished master_portfolio run; null on other rows.
	function portfolioWeights(m: BacktestResult['metrics']): Record<string, number> | null {
		const c = m.config as { weights?: Record<string, number> } | undefined;
		return c?.weights ?? null;
	}
	// Component asset-class label for one ticker ('美股大盘'); '' for unknown tickers.
	function componentName(sym: string): string {
		const l = PORTFOLIO_COMPONENTS[sym];
		return l ? (en ? l[1] : l[0]) : '';
	}
	// 份额: up to 6dp with trailing zeros trimmed ('12.340000' → '12.34', '7.000000' → '7').
	function fmtUnits(u: number): string {
		return u.toFixed(6).replace(/\.?0+$/, '');
	}
	function fmtUsd(v: number): string {
		return v.toLocaleString('en-US', { maximumFractionDigits: 0 });
	}
	function fmtPrice(p: number): string {
		return p.toLocaleString('en-US', { maximumFractionDigits: 2 });
	}

	// Plain-language one-liner for a param input (from STRATEGIES.paramHints); null when none.
	function paramHint(k: string): string | null {
		const h = (cfg.paramHints as Record<string, readonly [string, string]>)[k];
		return h ? (en ? h[1] : h[0]) : null;
	}

	// 白话 strategy name for display ('突破追涨'); falls back to the raw key.
	function strategyName(s: string): string {
		const c = (STRATEGIES as Record<string, (typeof STRATEGIES)[StratKey]>)[s];
		return c ? (en ? c.name[1] : c.name[0]) : s;
	}

	let busy = $state(false);
	let err = $state('');
	let jobs = $state<BacktestJob[]>([]);
	let results = $state<Record<string, BacktestResult>>({});
	let openId = $state<string | null>(null);
	// Trade-log expansion (master_portfolio): render only the latest 24 events until
	// the user asks for all (~181 cards would jank mobile). Reset on panel toggle.
	let showAllTrades = $state(false);

	// Build SVG polyline points for a compact equity sparkline (normalized min→max).
	function spark(curve: number[] | null, w = 96, h = 24): string {
		if (!curve || curve.length < 2) return '';
		const lo = Math.min(...curve);
		const hi = Math.max(...curve);
		const span = hi - lo || 1;
		const dx = w / (curve.length - 1);
		return curve
			.map((v, i) => `${(i * dx).toFixed(1)},${(h - ((v - lo) / span) * h).toFixed(1)}`)
			.join(' ');
	}

	// Larger equity chart geometry for the expanded detail panel: a baseline at the
	// starting equity, min/max gridlines, and the value polyline. Reuses spark()'s
	// normalization but exposes coordinates so we can place labels + the baseline.
	function bigChart(curve: number[] | null, w = 480, h = 140, pad = 8) {
		if (!curve || curve.length < 2) return null;
		const lo = Math.min(...curve);
		const hi = Math.max(...curve);
		const span = hi - lo || 1;
		const start = curve[0];
		const toX = (i: number) => pad + (i / (curve.length - 1)) * (w - pad * 2);
		const toY = (v: number) => pad + (1 - (v - lo) / span) * (h - pad * 2);
		const poly = curve.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
		// Area under the line, closed to the bottom of the plot box.
		const area = `${pad},${(h - pad).toFixed(1)} ${poly} ${(w - pad).toFixed(1)},${(h - pad).toFixed(1)}`;
		return {
			w,
			h,
			pad,
			lo,
			hi,
			start,
			poly,
			area,
			baselineY: toY(start),
			up: curve[curve.length - 1] >= start
		};
	}

	// Hardcoded teaser for logged-out visitors. The METRICS are real — HonestTrend NVDA 1d
	// EMA 20/50 from our logged backtest (public via api.nautilus_backtests: +33.98%,
	// DD -29.31%, Sharpe 2.59, 2 trades, 2023-06→2026-06). The curve SHAPE is illustrative
	// (labelled 示意曲线): 100k start, ~-29% dip mid-way, 133,980 finish.
	const SAMPLE_CURVE = [
		100000, 100400, 101900, 104100, 107600, 111800, 115900, 119400, 122300, 124100, 124600, 121800,
		117200, 111300, 104600, 97900, 92400, 89100, 88100, 90600, 94800, 99700, 105200, 110900, 116500,
		121600, 126000, 129600, 132300, 133980
	];
	const sampleChart = bigChart(SAMPLE_CURVE);

	async function refresh() {
		if (!$user) return;
		try {
			// Quant Lab jobs surface on /quant-lab, not in the regular backtest list.
			jobs = (await myJobs()).filter((j) => j.strategy !== 'quant_lab');
			for (const j of jobs) {
				if (j.status === 'done' && !results[j.id]) {
					const r = await jobResult(j.id);
					if (r) results = { ...results, [j.id]: r };
				}
			}
		} catch (e) {
			err = (e as Error).message;
		}
	}

	// Per-strategy client-side validation (the runner re-validates server-side).
	function validate(): string | null {
		// Free-text asset strategies (honest_trend + accumulator): basic symbol shape only.
		if (strategy === 'honest_trend' || strategy === 'accumulator') {
			if (!/^[A-Z0-9]{1,6}$/.test(asset))
				return en
					? 'Symbol must be 1-6 letters/digits, e.g. TSLA or GC.'
					: '标的代码须为 1-6 位字母/数字，如 TSLA 或 GC。';
		}
		if (strategy === 'honest_trend') {
			if (!((params.ema_fast as number) < (params.ema_slow as number)))
				return en ? 'Fast EMA must be < slow EMA.' : '快线 EMA 必须小于慢线。';
		}
		if (strategy === 'donchian') {
			if (!((params.exit_lb as number) <= (params.entry_lb as number)))
				return en ? 'Exit lookback must be ≤ entry lookback.' : '离场回看必须 ≤ 入场回看。';
		}
		// master_portfolio: both params are fixed-choice selects — always valid client-side.
		return null;
	}

	async function submit() {
		if (!$user?.sub) return;
		const v = validate();
		if (v) {
			err = v;
			return;
		}
		busy = true;
		err = '';
		try {
			// period_years goes in ONLY for a trailing window — 全部历史 omits the key entirely.
			// master_portfolio is multi-asset daily: NO asset/tf keys, rebalance as a number.
			const payload =
				strategy === 'master_portfolio'
					? { preset: params.preset, rebalance_months: Number(params.rebalance_months) }
					: { asset, tf, ...params };
			await submitBacktest(
				strategy as Strategy,
				{ ...payload, ...(periodSel > 0 ? { period_years: periodSel } : {}) },
				$user.sub
			);
			track('backtest_submit');
			await refresh();
		} catch (e) {
			err = (e as Error).message;
		} finally {
			busy = false;
		}
	}

	// One-click presets: seed the form through the normal strategy-change path (so all
	// inputs render valid), apply the preset's asset/tf/param overrides, then submit.
	type Preset = {
		zh: string;
		en: string;
		strategy: StratKey;
		asset?: string; // absent for no-asset strategies (master_portfolio)
		tf?: string;
		overrides?: Record<string, number | string>;
	};
	const PRESETS: Preset[] = [
		{
			zh: 'BTC 恐慌加仓定投 (推荐新手)',
			en: 'BTC fear-boosted DCA (beginner pick)',
			strategy: 'accumulator',
			asset: 'BTC',
			tf: '1d'
		},
		{
			zh: 'NVDA 美股趋势跟随',
			en: 'NVDA US trend following',
			strategy: 'honest_trend',
			asset: 'NVDA',
			tf: '1d',
			overrides: { ema_fast: 20, ema_slow: 50 }
		},
		{ zh: 'ETH 突破追涨', en: 'ETH breakout', strategy: 'donchian', asset: 'ETH', tf: '1h' },
		// Long EMAs suit gold's slow macro trends (50/200 = the classic golden-cross pair).
		{
			zh: 'GC 黄金趋势',
			en: 'Gold trend',
			strategy: 'honest_trend',
			asset: 'GC',
			tf: '1d',
			overrides: { ema_fast: 50, ema_slow: 200 }
		},
		{
			zh: '全天候组合',
			en: 'All Weather',
			strategy: 'master_portfolio',
			overrides: { preset: 'all_weather', rebalance_months: '3' }
		}
	];

	async function runPreset(p: Preset) {
		onStrategyChange(p.strategy);
		if (p.asset) asset = p.asset;
		if (p.tf) tf = p.tf;
		periodSel = 0; // presets always run full history (no period_years)
		if (p.overrides) params = { ...params, ...p.overrides };
		await submit();
	}

	function badge(s: BacktestJob['status']): string {
		return (
			{
				queued: 'border-muted-foreground/40 text-muted-foreground',
				running: 'border-amber-500/50 text-amber-600',
				done: 'border-emerald-500/50 text-emerald-600',
				error: 'border-red-500/50 text-red-600'
			}[s] ?? ''
		);
	}

	// Asset for display: commodities get their name — '黄金(GC)' — others stay as-is.
	function assetLabel(a: unknown): string {
		if (!a) return '—';
		const c = COMMODITY_ASSETS.find((x) => x.sym === a);
		return c ? `${en ? c.en : c.zh}(${c.sym})` : String(a);
	}

	// Plain-language title line for a job: '突破追涨 · BTC · 1h' ('—' when a field is absent);
	// master_portfolio has no asset/tf → recipe name instead: '全天候(桥水风格) · 组合'.
	function jobTitle(j: BacktestJob): string {
		const p = j.params;
		if (j.strategy === 'master_portfolio') {
			const pp = PORTFOLIO_PRESETS[String(p.preset) as PortfolioPresetKey];
			const name = pp ? (en ? pp.en : pp.zh) : String(p.preset ?? '—');
			return `${name} · ${en ? 'portfolio' : '组合'}`;
		}
		return `${strategyName(j.strategy)} · ${assetLabel(p.asset)} · ${p.tf || '—'}`;
	}

	// Raw config string — kept for precision, demoted to a small mono sub-line.
	function jobConfig(j: BacktestJob): string {
		const rest = Object.entries(j.params)
			.filter(([k]) => k !== 'asset' && k !== 'tf')
			.map(([k, v]) => `${k}=${v}`)
			.join(' ');
		return rest ? `${j.strategy} · ${rest}` : j.strategy;
	}

	// Collapsed-row data window: '2017-08→2026-06' from metrics.period_start/_end;
	// null when either bound is missing (legacy rows — the runner only added them later).
	function periodRange(m: BacktestResult['metrics']): string | null {
		return m.period_start && m.period_end
			? `${m.period_start.slice(0, 7)}→${m.period_end.slice(0, 7)}`
			: null;
	}

	// '2023-06 → 2026-06' → 3 (years, 1 decimal); null when period is missing/unparseable.
	function periodYears(period: unknown): number | null {
		if (typeof period !== 'string') return null;
		const m = period.match(/(\d{4})-(\d{2}).*?(\d{4})-(\d{2})/);
		if (!m) return null;
		const months = (+m[3] - +m[1]) * 12 + (+m[4] - +m[2]);
		return months > 0 ? Math.round((months / 12) * 10) / 10 : null;
	}

	// Generated honest one-liner from the metrics — descriptive only, no advice wording.
	function honestLine(m: BacktestResult['metrics']): string {
		if (m.return_pct < 0)
			return en
				? 'This config lost money historically — the whole point of a backtest is telling you in advance.'
				: '这个配置在历史上亏钱 —— 回测的价值就是提前告诉你。';
		const yrs = periodYears(m.period);
		const zhSpan = yrs != null ? `${yrs} 年` : '';
		const enSpan = yrs != null ? ` over ${yrs} years` : '';
		const dd = m.max_dd_pct as number | null; // accumulator runs have null DD
		if (dd == null)
			return en
				? `+${m.return_pct}% cumulative${enSpan} — backtest ≠ live.`
				: `${zhSpan}累计 +${m.return_pct}% —— 回测 ≠ 实盘。`;
		return en
			? `+${m.return_pct}% cumulative${enSpan}, but the deepest dip on the way was ${Math.abs(dd)}% — could you have held on? Backtest ≠ live.`
			: `${zhSpan}累计 +${m.return_pct}%,但路上最深跌过 ${Math.abs(dd)}% —— 你能拿住吗?回测 ≠ 实盘。`;
	}

	// Format a possibly-null metric (crypto accumulator has null DD/Sharpe/Calmar).
	function num(v: unknown, suffix = ''): string {
		if (v == null || (typeof v === 'number' && !isFinite(v))) return '—';
		return `${v}${suffix}`;
	}

	function toggle(id: string) {
		openId = openId === id ? null : id;
		showAllTrades = false; // trade-log expansion is per opened panel
	}

	// ── One-click "turn this backtest into a live signal" ─────────────────────
	// Maps a completed job's config onto a user signal: honest_trend → ema_cross
	// (both crossings), donchian → donchian_breakout (both sides), accumulator →
	// market-wide fng_threshold below 25 (its fear-buy trigger).
	let sigBusy = $state<string | null>(null);
	let sigMsg = $state<Record<string, { ok: boolean; text: string }>>({});

	function mapJobToSignal(j: BacktestJob, userId: string): NewSignal {
		const p = j.params as Record<string, string | number>;
		const asset = String(p.asset ?? 'BTC');
		const tf = String(p.tf ?? '1d');
		if (j.strategy === 'honest_trend') {
			const f = Number(p.ema_fast);
			const s = Number(p.ema_slow);
			const sigTf = '1d'; // honest_trend assets (US equity + commodities) signal at 1d only
			return {
				user_id: userId,
				name: `${asset} ${sigTf} EMA${f}/${s} ${en ? 'cross' : '金叉死叉'}`,
				kind: 'ema_cross',
				asset,
				timeframe: sigTf,
				params: { ema_fast: f, ema_slow: s, direction: 'both' }
			};
		}
		if (j.strategy === 'donchian') {
			const e = Number(p.entry_lb);
			const x = Number(p.exit_lb);
			return {
				user_id: userId,
				name: `${asset} ${tf} ${en ? 'Donchian' : '唐奇安'}${e}/${x} ${en ? 'breakout' : '突破'}`,
				kind: 'donchian_breakout',
				asset,
				timeframe: tf,
				params: { entry_lb: e, exit_lb: x, side: 'both' }
			};
		}
		// accumulator — the live analogue depends on the asset class: crypto's smart boost
		// is FNG (market-wide), while commodities/US stocks boost below the 200d SMA, whose
		// closest live alert is a 50/200 cross on that asset.
		if (CRYPTO_ASSETS.includes(asset as (typeof CRYPTO_ASSETS)[number])) {
			return {
				user_id: userId,
				name: en ? 'FNG<25 market fear alert' : 'FNG<25 全市场恐慌提醒',
				kind: 'fng_threshold',
				asset: '*',
				timeframe: '1d',
				params: { below: 25 }
			};
		}
		return {
			user_id: userId,
			name: en ? `${asset} 50/200 cross alert` : `${asset} 200日均线金叉死叉`,
			kind: 'ema_cross',
			asset,
			timeframe: '1d',
			params: { ema_fast: 50, ema_slow: 200, direction: 'both' }
		};
	}

	async function toSignal(j: BacktestJob) {
		const sub = $user?.sub;
		if (!sub || sigBusy) return;
		sigBusy = j.id;
		try {
			await createSignal(mapJobToSignal(j, sub));
			signalsVersion.update((n) => n + 1); // <MySignals /> below re-fetches
			sigMsg = {
				...sigMsg,
				[j.id]: { ok: true, text: en ? 'Created — manage it below.' : '已创建,在下方管理' }
			};
		} catch (e) {
			sigMsg = { ...sigMsg, [j.id]: { ok: false, text: (e as Error).message } };
		} finally {
			sigBusy = null;
		}
	}

	let timer: ReturnType<typeof setInterval>;
	onMount(() => {
		// Deep-link prefill (e.g. /backtest?strategy=honest_trend&asset=GC from
		// /commodities): fill the form only — never auto-submit. Strategy first
		// (it re-seeds asset/tf/params), then asset; the tf-forcing $effect above
		// snaps tf to 1d for non-catalog assets on its own.
		const sp = $page.url.searchParams;
		const s = sp.get('strategy');
		if (s && s in STRATEGIES) onStrategyChange(s as StratKey);
		const a = sp.get('asset');
		if (a) asset = a.toUpperCase().trim();
		refresh();
		timer = setInterval(refresh, 4000); // poll while jobs are queued/running
	});
	onDestroy(() => clearInterval(timer));
</script>

<svelte:head>
	<title>{en ? 'Backtest playground' : '回测实验室'} · Crypto Quant</title>
	<meta
		name="description"
		content="免代码回测：加密货币 · 任意美股 · 黄金原油 — 真实数据，诚实回撤。"
	/>
	<meta property="og:title" content="{en ? 'Backtest playground' : '回测实验室'} · Crypto Quant" />
	<meta
		property="og:description"
		content="免代码回测：加密货币 · 任意美股 · 黄金原油 — 真实数据，诚实回撤。"
	/>
</svelte:head>

<main class="mx-auto mt-12 max-w-2xl px-5">
	<h1 class="text-2xl font-semibold tracking-tight">{en ? 'Backtest playground' : '回测实验室'}</h1>
	<p class="mt-2 text-sm text-muted-foreground">
		{en
			? 'Run your own backtest of a strategy with your own parameters. Results are private to your account.'
			: '用你自己的参数跑策略回测，结果只属于你的账号。'}
	</p>

	{#if !$user}
		<div class="mt-6 rounded-md border border-primary/50 bg-primary/5 p-4 text-sm">
			<div class="font-medium text-foreground">
				{en ? 'Sign in to run your own backtests' : '登录后即可跑你自己的回测'}
			</div>
			<p class="mt-1 text-muted-foreground">
				{en
					? 'Pick a strategy below, set your own parameters, and we run a real backtest on historical data. Results are private to your account.'
					: '选下面任意一个策略，设你自己的参数，我们用历史数据跑一次真实回测。结果只属于你的账号。'}
			</p>
			<p class="mt-2 text-xs font-medium text-primary">
				{en
					? 'Instant signup — no email verification, running in 10 seconds.'
					: '注册即用 —— 无需邮箱验证，10 秒开跑'}
			</p>
			<a
				href="/login?next=/backtest"
				class="mt-3 inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
			>
				{en ? 'Sign in' : '登录'}
			</a>
		</div>

		<!-- Read-only strategy preview so logged-out visitors see what's on offer. -->
		<div class="mt-4 grid gap-3 sm:grid-cols-2">
			{#each Object.keys(STRATEGIES) as s, _i (_i)}
				{@const c = STRATEGIES[s as StratKey]}
				<div class="rounded-md border border-border p-4">
					<div class="text-sm font-medium text-foreground">
						{en ? c.name[1] : c.name[0]}
						<span class="font-normal text-muted-foreground">· {c.tech}</span>
					</div>
					<p class="mt-1.5 text-xs text-muted-foreground">{en ? c.blurb[1] : c.blurb[0]}</p>
					<div class="mt-2 flex flex-wrap gap-1">
						{#if 'assets' in c}
							{#each c.assets.slice(0, 4) as a, _i (_i)}
								<span class="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
									>{a}</span
								>
							{/each}
							{#if c.assets.length > 4}
								<span class="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
									>+{c.assets.length - 4}</span
								>
							{/if}
						{:else}
							<!-- master_portfolio: recipe names instead of tickers -->
							{#each Object.values(PORTFOLIO_PRESETS).slice(0, 3) as pp (pp.zh)}
								<span class="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
									>{en ? pp.en : pp.zh}</span
								>
							{/each}
							<span class="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
								>+2</span
							>
						{/if}
					</div>
				</div>
			{/each}
		</div>

		<!-- Fully-rendered sample result so visitors see the payoff before the login wall.
		     Metrics are real (logged backtest); the curve shape is illustrative (示意曲线). -->
		<div class="mt-4 rounded-md border border-border p-4">
			<div class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
				<span class="text-sm font-medium text-foreground">{en ? 'Sample result' : '示例结果'}</span>
				<span class="text-xs text-muted-foreground"
					>{en ? '— sign up to run your own' : '— 注册后用你自己的参数跑'}</span
				>
			</div>
			<div class="mt-1 font-mono text-xs text-muted-foreground">
				HonestTrend · NVDA · 1d · ema_fast=20 ema_slow=50
			</div>

			{#if sampleChart}
				<svg
					viewBox="0 0 {sampleChart.w} {sampleChart.h}"
					width="100%"
					height={sampleChart.h}
					class="mt-3 max-w-[480px]"
					role="img"
					aria-label={en ? 'Sample equity curve (illustrative)' : '示例权益曲线（示意）'}
				>
					<!-- plot border -->
					<rect
						x={sampleChart.pad}
						y={sampleChart.pad}
						width={sampleChart.w - sampleChart.pad * 2}
						height={sampleChart.h - sampleChart.pad * 2}
						fill="none"
						class="stroke-border"
						stroke-width="1"
					/>
					<!-- baseline at starting equity -->
					<line
						x1={sampleChart.pad}
						x2={sampleChart.w - sampleChart.pad}
						y1={sampleChart.baselineY}
						y2={sampleChart.baselineY}
						class="stroke-muted-foreground/40"
						stroke-width="1"
						stroke-dasharray="3 3"
					/>
					<!-- area + line -->
					<polygon points={sampleChart.area} class="fill-emerald-500/10" />
					<polyline
						points={sampleChart.poly}
						fill="none"
						stroke-width="1.5"
						stroke-linejoin="round"
						stroke-linecap="round"
						class="stroke-emerald-500"
					/>
					<!-- honesty label: the shape is illustrative, the metrics below are real -->
					<text
						x={sampleChart.pad + 3}
						y={sampleChart.pad + 12}
						class="fill-muted-foreground"
						font-size="10">{en ? 'illustrative curve' : '示意曲线'}</text
					>
					<!-- min/max + start labels -->
					<text
						x={sampleChart.w - sampleChart.pad - 2}
						y={sampleChart.pad + 10}
						text-anchor="end"
						class="fill-muted-foreground"
						font-size="10">{sampleChart.hi.toFixed(0)}</text
					>
					<text
						x={sampleChart.w - sampleChart.pad - 2}
						y={sampleChart.h - sampleChart.pad - 3}
						text-anchor="end"
						class="fill-muted-foreground"
						font-size="10">{sampleChart.lo.toFixed(0)}</text
					>
					<text
						x={sampleChart.pad + 3}
						y={sampleChart.baselineY - 3}
						class="fill-muted-foreground"
						font-size="10">{en ? 'start' : '起点'} {sampleChart.start.toFixed(0)}</text
					>
				</svg>
			{/if}

			<dl class="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-3">
				<div>
					<dt class="text-muted-foreground">{en ? 'Return' : '收益'}</dt>
					<dd class="font-mono text-emerald-600">+33.98%</dd>
				</div>
				<div>
					<dt class="text-muted-foreground">{en ? 'Max drawdown' : '最大回撤'}</dt>
					<dd class="font-mono">-29.31%</dd>
				</div>
				<div>
					<dt class="text-muted-foreground">Sharpe</dt>
					<dd class="font-mono">2.59</dd>
				</div>
				<div>
					<dt class="text-muted-foreground">{en ? 'Trades' : '成交笔数'}</dt>
					<dd class="font-mono">2</dd>
				</div>
				<div class="col-span-2">
					<dt class="text-muted-foreground">{en ? 'Period' : '区间'}</dt>
					<dd class="font-mono">2023-06 → 2026-06</dd>
				</div>
			</dl>
			<p class="mt-3 text-[11px] text-muted-foreground">
				{en
					? 'Backtest on real historical data · backtest ≠ live trading · 2 trades is a small sample — demo only'
					: '真实历史数据回测 · 回测 ≠ 实盘 · 2 笔交易样本量小，仅供体验'}
			</p>
		</div>
	{:else}
		<!-- One-click presets: fill the form with a recommended config and submit immediately. -->
		<div class="mt-6">
			<div class="text-xs font-medium text-muted-foreground">
				{en ? 'Recommended configs — one-click backtest' : '推荐配置 一键回测'}
			</div>
			<div class="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
				{#each PRESETS as p, _i (_i)}
					<button
						type="button"
						onclick={() => runPreset(p)}
						disabled={busy}
						class="rounded-md border border-border p-3 text-left hover:border-primary/50 hover:bg-primary/5 disabled:opacity-50"
					>
						<div class="text-sm font-medium text-foreground">{en ? p.en : p.zh}</div>
						<div class="mt-1 text-xs text-muted-foreground">
							{en ? '~30s to results' : '~30 秒出结果'}
						</div>
					</button>
				{/each}
			</div>
		</div>

		<!-- Form: strategy row + plain-language explainer, then the asset/tf/params grid -->
		<div class="mt-4 rounded-md border border-border p-4">
			<label class="block text-xs">
				<span class="text-muted-foreground">{en ? 'Strategy' : '策略'}</span>
				<select
					value={strategy}
					onchange={(e) =>
						onStrategyChange((e.currentTarget as HTMLSelectElement).value as StratKey)}
					class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
				>
					{#each Object.keys(STRATEGIES) as s, _i (_i)}
						{@const c = STRATEGIES[s as StratKey]}
						<option value={s}>{en ? c.name[1] : c.name[0]} · {c.tech}</option>
					{/each}
				</select>
			</label>
			<!-- Explainer strip — what the selected strategy actually does, in plain language. -->
			<div class="mt-2 rounded bg-muted/30 p-2 text-xs text-muted-foreground">
				📖 {en ? cfg.explain[1] : cfg.explain[0]}
			</div>
			<div class="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-4">
				{#if 'assets' in cfg}
					<label class="text-xs">
						<span class="text-muted-foreground">{en ? 'Asset' : '标的'}</span>
						{#if strategy === 'honest_trend'}
							<!-- Combo: free-text US ticker + suggested trio + commodities via datalist
						     (uppercase-normalized). -->
							<input
								type="text"
								list="honest-trend-assets"
								value={asset}
								oninput={(e) =>
									(asset = (e.currentTarget as HTMLInputElement).value.toUpperCase().trim())}
								placeholder={en
									? 'Any US ticker e.g. TSLA, or GC'
									: '任意美股代码（如 TSLA）或商品（如 GC）'}
								maxlength="6"
								autocomplete="off"
								spellcheck="false"
								class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
							/>
							<datalist id="honest-trend-assets">
								{#each STRATEGIES.honest_trend.assets as a, _i (_i)}<option value={a}
									></option>{/each}
								{#each COMMODITY_ASSETS as c (c.sym)}<option value={c.sym}
										>{c.sym} — {en ? c.en : c.zh}</option
									>{/each}
							</datalist>
							{#if commodity}
								<p class="mt-1 text-[11px] text-muted-foreground">
									{en
										? 'Commodity continuous futures · daily only · 10y history'
										: '商品期货连续合约 · 仅日线 · 10 年历史'}
								</p>
							{:else if asset && !isCatalogAsset}
								<p class="mt-1 text-[11px] text-muted-foreground">
									{en ? STRATEGIES.honest_trend.note[1] : STRATEGIES.honest_trend.note[0]}
								</p>
							{/if}
						{:else if strategy === 'accumulator'}
							<!-- Combo: free-text — crypto majors (FNG smart boost) + any commodity sym or
						     US ticker (200d-SMA smart boost) — with suggestions via datalist. -->
							<input
								type="text"
								list="accumulator-assets"
								value={asset}
								oninput={(e) =>
									(asset = (e.currentTarget as HTMLInputElement).value.toUpperCase().trim())}
								placeholder={en
									? 'BTC, GC (gold) or any US ticker'
									: 'BTC、GC（黄金）或任意美股代码'}
								maxlength="6"
								autocomplete="off"
								spellcheck="false"
								class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
							/>
							<datalist id="accumulator-assets">
								{#each CRYPTO_ASSETS as a, _i (_i)}<option value={a}></option>{/each}
								{#each COMMODITY_ASSETS as c (c.sym)}<option value={c.sym}
										>{c.sym} — {en ? c.en : c.zh}</option
									>{/each}
								{#each STRATEGIES.honest_trend.assets as a, _i (_i)}<option value={a}
									></option>{/each}
							</datalist>
							<p class="mt-1 text-[11px] text-muted-foreground">
								{en
									? 'Crypto doubles on the Fear & Greed index; gold/US stocks double below the 200-day SMA — same discipline, different fear thermometer'
									: '币按恐慌指数加倍;黄金/美股按 200 日均线加倍 —— 同一纪律,不同恐慌温度计'}
							</p>
						{:else}
							<select
								bind:value={asset}
								class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
							>
								{#each cfg.assets as a, _i (_i)}<option value={a}>{a}</option>{/each}
							</select>
						{/if}
					</label>
					<label class="text-xs">
						<span class="text-muted-foreground">{en ? 'Timeframe' : '周期'}</span>
						<select
							bind:value={tf}
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						>
							{#each tfChoices as f, _i (_i)}<option value={f}>{f}</option>{/each}
						</select>
					</label>
				{/if}
				<label class="text-xs">
					<span class="text-muted-foreground">{en ? 'Data window' : '数据周期'}</span>
					<select
						bind:value={periodSel}
						class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
					>
						<option value={0}>{en ? 'Full history' : '全部历史'}</option>
						<option value={5}>{en ? 'Last 5 years' : '最近 5 年'}</option>
						<option value={3}>{en ? 'Last 3 years' : '最近 3 年'}</option>
						<option value={2}>{en ? 'Last 2 years' : '最近 2 年'}</option>
						<option value={1}>{en ? 'Last 1 year' : '最近 1 年'}</option>
					</select>
					<p class="mt-1 text-[10px] text-muted-foreground">
						{en
							? 'Short windows show recent fit; long windows span bull AND bear.'
							: '回测覆盖的历史范围 —— 短窗口看近况,长窗口看穿牛熊'}
					</p>
				</label>
				{#each Object.entries(cfg.params as Record<string, AnyParam>) as [k, p], _i (_i)}
					{@const hint = paramHint(k)}
					<label class="text-xs">
						<span class="text-muted-foreground">{paramLabel(k)}</span>
						{#if isChoice(p)}
							<select
								bind:value={params[k]}
								class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
							>
								{#each p.choices as c, _i (_i)}<option value={c}>{choiceLabel(k, c)}</option>{/each}
							</select>
						{:else}
							<input
								type="number"
								bind:value={params[k]}
								min={p.min}
								max={p.max}
								step={p.step ?? 1}
								class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
							/>
						{/if}
						{#if hint}<p class="mt-1 text-[10px] text-muted-foreground">{hint}</p>{/if}
					</label>
				{/each}
				{#if selectedPreset}
					<!-- Weights of the chosen recipe + honesty note (full-width row under the preset select). -->
					<div class="col-span-2 sm:col-span-4">
						<div class="flex flex-wrap gap-1">
							{#each weightChips(selectedPreset.weights) as chip (chip)}
								<span class="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
									>{chip}</span
								>
							{/each}
						</div>
						<p class="mt-1 text-[10px] text-muted-foreground">
							{en
								? 'Unofficial replica · public recipe · trading costs not modeled'
								: '非官方复刻 · 公开配方 · 未计交易成本'}
						</p>
					</div>
				{/if}
			</div>
		</div>

		<button
			type="button"
			onclick={submit}
			disabled={busy}
			class="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
		>
			{busy ? (en ? 'Submitting…' : '提交中…') : en ? 'Run backtest' : '跑回测'}
		</button>

		{#if err}<p class="mt-3 text-xs text-red-600">{err}</p>{/if}

		<!-- My jobs -->
		<h2 class="mt-8 text-sm font-medium">{en ? 'My backtests' : '我的回测'}</h2>
		{#if jobs.length === 0}
			<p class="mt-2 text-xs text-muted-foreground">
				{en ? 'No backtests yet — submit one above.' : '还没有回测，上面提交一个。'}
			</p>
		{:else}
			<div class="mt-2 divide-y divide-border rounded-md border border-border text-sm">
				{#each jobs as j (j.id)}
					{@const r = results[j.id]}
					{@const done = j.status === 'done' && r}
					<div>
						<!-- Collapsed row -->
						<button
							type="button"
							onclick={() => done && toggle(j.id)}
							class="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 text-left {done
								? 'cursor-pointer hover:bg-muted/30'
								: 'cursor-default'}"
						>
							<span class="flex min-w-0 flex-col">
								<span class="text-xs font-medium text-foreground">
									{jobTitle(j)}{#if done}{@const prange = periodRange(r.metrics)}{#if prange}<span
												class="font-normal text-muted-foreground"
											>
												· {prange}</span
											>{/if}{/if}
								</span>
								<span class="font-mono text-[10px] text-muted-foreground">{jobConfig(j)}</span>
							</span>
							<span class="rounded border px-1.5 py-0.5 text-[10px] {badge(j.status)}"
								>{j.status}</span
							>
							{#if done}
								{@const m = r.metrics}
								<span class="text-xs {m.return_pct >= 0 ? 'text-emerald-600' : 'text-red-600'}"
									>{m.return_pct >= 0 ? '+' : ''}{m.return_pct}%</span
								>
								<span class="text-xs text-muted-foreground"
									>DD {num(m.max_dd_pct, '%')} · Sharpe {num(m.sharpe)} · {m.trades}
									{en ? 'trades' : '笔'}</span
								>
								{#if r.equity_curve}
									<svg
										viewBox="0 0 96 24"
										width="96"
										height="24"
										class="ml-auto {m.return_pct >= 0 ? 'text-emerald-500' : 'text-red-500'}"
										aria-hidden="true"
									>
										<polyline
											points={spark(r.equity_curve)}
											fill="none"
											stroke="currentColor"
											stroke-width="1"
											stroke-linejoin="round"
										/>
									</svg>
								{/if}
								<span class="text-xs text-muted-foreground {r.equity_curve ? '' : 'ml-auto'}"
									>{openId === j.id ? '▲' : '▼'}</span
								>
							{:else if j.status === 'error'}
								<span class="text-xs text-red-600">{j.error}</span>
							{/if}
						</button>

						<!-- Expanded detail panel -->
						{#if done && openId === j.id}
							{@const m = r.metrics}
							{@const chart = bigChart(r.equity_curve)}
							{@const weights = portfolioWeights(m)}
							<div class="border-t border-border bg-muted/20 px-3 py-4">
								<!-- Title + generated honest summary — descriptive only, never advice. -->
								<div class="text-sm font-medium text-foreground">{jobTitle(j)}</div>
								<p class="mt-1 mb-3 text-xs text-muted-foreground">{honestLine(r.metrics)}</p>
								{#if chart}
									<svg
										viewBox="0 0 {chart.w} {chart.h}"
										width="100%"
										height={chart.h}
										class="max-w-[480px]"
										role="img"
										aria-label={en ? 'Equity curve' : '权益曲线'}
									>
										<!-- plot border -->
										<rect
											x={chart.pad}
											y={chart.pad}
											width={chart.w - chart.pad * 2}
											height={chart.h - chart.pad * 2}
											fill="none"
											class="stroke-border"
											stroke-width="1"
										/>
										<!-- baseline at starting equity -->
										<line
											x1={chart.pad}
											x2={chart.w - chart.pad}
											y1={chart.baselineY}
											y2={chart.baselineY}
											class="stroke-muted-foreground/40"
											stroke-width="1"
											stroke-dasharray="3 3"
										/>
										<!-- area + line -->
										<polygon
											points={chart.area}
											class={chart.up ? 'fill-emerald-500/10' : 'fill-red-500/10'}
										/>
										<polyline
											points={chart.poly}
											fill="none"
											stroke-width="1.5"
											stroke-linejoin="round"
											stroke-linecap="round"
											class={chart.up ? 'stroke-emerald-500' : 'stroke-red-500'}
										/>
										<!-- min/max + start labels -->
										<text
											x={chart.w - chart.pad - 2}
											y={chart.pad + 10}
											text-anchor="end"
											class="fill-muted-foreground"
											font-size="10">{chart.hi.toFixed(0)}</text
										>
										<text
											x={chart.w - chart.pad - 2}
											y={chart.h - chart.pad - 3}
											text-anchor="end"
											class="fill-muted-foreground"
											font-size="10">{chart.lo.toFixed(0)}</text
										>
										<text
											x={chart.pad + 3}
											y={chart.baselineY - 3}
											class="fill-muted-foreground"
											font-size="10">{en ? 'start' : '起点'} {chart.start.toFixed(0)}</text
										>
									</svg>
								{:else}
									<p class="text-xs text-muted-foreground">
										{en ? 'No equity curve for this run.' : '本次回测无权益曲线。'}
									</p>
								{/if}

								<!-- Metrics -->
								<dl class="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-3">
									<div>
										<dt class="text-muted-foreground">{en ? 'Return' : '收益'}</dt>
										<dd class="font-mono {m.return_pct >= 0 ? 'text-emerald-600' : 'text-red-600'}">
											{m.return_pct >= 0 ? '+' : ''}{m.return_pct}%
										</dd>
										<p class="text-[10px] text-muted-foreground">
											{en ? 'cumulative over the backtest' : '回测期累计'}
										</p>
									</div>
									<div>
										<dt class="text-muted-foreground">{en ? 'Max drawdown' : '最大回撤'}</dt>
										<dd class="font-mono">{num(m.max_dd_pct, '%')}</dd>
										<p class="text-[10px] text-muted-foreground">
											{en ? 'deepest dip — ask if you could hold' : '最深浮亏 — 问自己能否拿住'}
										</p>
									</div>
									<div>
										<dt class="text-muted-foreground">Sharpe</dt>
										<dd class="font-mono">{num(m.sharpe)}</dd>
										<p class="text-[10px] text-muted-foreground">
											{en ? 'risk-adjusted return; >1 is decent' : '风险调整后收益,>1 算不错'}
										</p>
									</div>
									<div>
										<dt class="text-muted-foreground">Calmar</dt>
										<dd class="font-mono">{num(m.calmar)}</dd>
										<p class="text-[10px] text-muted-foreground">
											{en
												? 'annual return ÷ max DD; higher = steadier'
												: '年化收益 ÷ 最大回撤,越高越稳'}
										</p>
									</div>
									{#if m.cagr_pct != null}
										<div>
											<dt class="text-muted-foreground">CAGR</dt>
											<dd class="font-mono">{num(m.cagr_pct, '%')}</dd>
											<p class="text-[10px] text-muted-foreground">
												{en ? 'compound annual growth' : '年化复合收益'}
											</p>
										</div>
									{/if}
									{#if j.strategy === 'master_portfolio'}
										<div>
											<dt class="text-muted-foreground">{en ? 'Rebalances' : '再平衡次数'}</dt>
											<dd class="font-mono">{num(m.trades)}</dd>
											<p class="text-[10px] text-muted-foreground">
												{en ? 'times weights were reset to target' : '把比例调回目标的次数'}
											</p>
										</div>
									{:else}
										<div>
											<dt class="text-muted-foreground">{en ? 'Trades' : '成交笔数'}</dt>
											<dd class="font-mono">{num(m.trades)}</dd>
											<p class="text-[10px] text-muted-foreground">
												{en ? 'too few = weak statistics' : '太少则统计意义有限'}
											</p>
										</div>
									{/if}
									{#if m.win_rate != null}
										<div>
											<dt class="text-muted-foreground">{en ? 'Win rate' : '胜率'}</dt>
											<dd class="font-mono">{num(m.win_rate, '%')}</dd>
										</div>
									{/if}
									{#if m.period_start && m.period_end}
										<div class="col-span-2">
											<dt class="text-muted-foreground">{en ? 'Period' : '区间'}</dt>
											<dd class="font-mono">{m.period_start} → {m.period_end}</dd>
											<p class="text-[10px] text-muted-foreground">
												{en
													? "spans bull and bear or it doesn't count"
													: '数据起止 —— 跨越牛熊才算数'}
											</p>
										</div>
									{:else if m.period != null}
										<!-- Legacy rows: only the coarse month-level period string exists. -->
										<div class="col-span-2">
											<dt class="text-muted-foreground">{en ? 'Period' : '区间'}</dt>
											<dd class="font-mono">{m.period}</dd>
										</div>
									{/if}
								</dl>

								<!-- Portfolio weights (master_portfolio rows: metrics.config.weights) -->
								{#if weights}
									<div class="mt-4">
										<div class="text-xs font-medium text-muted-foreground">
											{en ? 'Weights' : '权重'}
										</div>
										<div class="mt-1 flex flex-wrap gap-1">
											{#each weightChips(weights) as chip (chip)}
												<span
													class="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
													>{chip}</span
												>
											{/each}
										</div>
										<p class="mt-1 text-[10px] text-muted-foreground">
											{en
												? 'Unofficial replica · public recipe · trading costs not modeled'
												: '非官方复刻 · 公开配方 · 未计交易成本'}
										</p>
									</div>
								{/if}

								<!-- master_portfolio detail: final holdings + rebalance journal. The runner
								     emits both since 2026-06; legacy rows get a "re-run" hint instead. -->
								{#if j.strategy === 'master_portfolio'}
									{@const holdings = m.holdings ?? []}
									{@const tradeLog = m.trade_log ?? []}
									{#if holdings.length === 0 && tradeLog.length === 0}
										<p class="mt-4 text-[11px] text-muted-foreground">
											{en
												? 'This run predates the detail log — re-run it once to get holdings + the trade journal.'
												: '旧回测无明细 —— 重跑一次即可。'}
										</p>
									{/if}

									{#if holdings.length > 0}
										<div class="mt-4">
											<div class="text-xs font-medium text-muted-foreground">
												{en ? 'Final holdings' : '期末持仓'}
											</div>
											<div class="mt-1 overflow-x-auto">
												<div
													class="min-w-[440px] divide-y divide-border/60 rounded border border-border/60 text-xs"
												>
													<div
														class="grid grid-cols-[minmax(9rem,1.4fr)_1fr_1fr_1.2fr] gap-x-3 px-2 py-1 text-[10px] text-muted-foreground"
													>
														<span>{en ? 'Asset' : '标的'}</span>
														<span class="text-right">{en ? 'Units' : '份额'}</span>
														<span class="text-right">{en ? 'Value' : '市值'}</span>
														<span class="text-right">{en ? 'Weight / target' : '权重 / 目标'}</span>
													</div>
													{#each holdings as hld (hld.sym)}
														{@const target = weights?.[hld.sym]}
														{@const over = target != null && hld.weight_pct > target}
														{@const under = target != null && hld.weight_pct < target}
														<div
															class="grid grid-cols-[minmax(9rem,1.4fr)_1fr_1fr_1.2fr] items-baseline gap-x-3 px-2 py-1.5"
														>
															<span class="font-medium text-foreground">
																{hld.sym}<span class="ml-1 font-normal text-muted-foreground"
																	>{componentName(hld.sym)}</span
																>
															</span>
															<span class="text-right font-mono">{fmtUnits(hld.units)}</span>
															<span class="text-right font-mono">${fmtUsd(hld.value)}</span>
															<span
																class="text-right font-mono {over
																	? 'text-red-600/80'
																	: under
																		? 'text-emerald-600/80'
																		: ''}"
															>
																{hld.weight_pct.toFixed(1)}%{#if target != null}<span
																		class="text-muted-foreground"
																	>
																		/ {target}%</span
																	>{/if}
															</span>
														</div>
													{/each}
												</div>
											</div>
										</div>
									{/if}

									{#if tradeLog.length > 0}
										{@const events = [...tradeLog].reverse()}
										{@const shown = showAllTrades ? events : events.slice(0, 24)}
										<details class="mt-4">
											<summary
												class="cursor-pointer text-xs font-medium text-muted-foreground select-none hover:text-foreground"
											>
												{en ? 'Trade log (rebalance journal)' : '成交明细（再平衡日志）'} · {tradeLog.length}
												{en ? 'events' : '次'}
											</summary>
											<!-- The reason, stated ONCE — every event below is the same mechanical rule. -->
											<p class="mt-2 text-[11px] text-muted-foreground">
												{en
													? 'Why each trade: back to target weights — mechanical sell-high / buy-low. The "drift → target" on each line is the entire reason for that rebalance.'
													: '换仓理由：回到目标权重 —— 机械化高抛低吸，涨多了的卖、跌多了的买。每行的"偏离→目标"就是那次换仓的全部理由。'}
											</p>
											<div class="mt-2 space-y-2 overflow-x-auto">
												{#each shown as ev (ev.date + ev.kind)}
													{@const legs = ev.legs.filter((l) => Math.abs(l.delta_usd) >= 1)}
													<div class="min-w-[440px] rounded border border-border/60 p-2 text-xs">
														<div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
															<span class="font-mono font-medium text-foreground">{ev.date}</span>
															<span class="text-muted-foreground"
																>{en ? 'total' : '总值'} ${fmtUsd(ev.total)}</span
															>
															<span
																class="rounded border px-1 py-px text-[10px] {ev.kind === 'initial'
																	? 'border-sky-500/50 text-sky-600'
																	: 'border-border text-muted-foreground'}"
															>
																{ev.kind === 'initial'
																	? en
																		? 'initial'
																		: '建仓'
																	: en
																		? 'rebalance'
																		: '再平衡'}
															</span>
														</div>
														{#if legs.length > 0}
															<div class="mt-1.5 space-y-1">
																{#each legs as l (l.sym)}
																	<div
																		class="grid min-w-[420px] grid-cols-[3.5rem_7.5rem_1fr_auto] items-baseline gap-x-2 font-mono text-[11px]"
																	>
																		<span class="text-foreground">{l.sym}</span>
																		<!-- red = drifted above target (selling high); green = below (buying low) -->
																		<span
																			class={l.w_before > l.w_target
																				? 'text-red-600'
																				: l.w_before < l.w_target
																					? 'text-emerald-600'
																					: 'text-muted-foreground'}
																		>
																			{l.w_before.toFixed(1)}%→{l.w_target.toFixed(1)}%
																		</span>
																		<span class="text-muted-foreground">
																			{l.delta_usd < 0
																				? en
																					? 'sell'
																					: '卖出'
																				: en
																					? 'buy'
																					: '买入'} ${fmtUsd(Math.abs(l.delta_usd))}
																			<span class="opacity-70">@ {fmtPrice(l.price)}</span>
																		</span>
																		<span class="text-muted-foreground"
																			>{en ? 'after' : '期后'}
																			{fmtUnits(l.units_after)}
																			{en ? 'units' : '份'}</span
																		>
																	</div>
																{/each}
															</div>
														{:else}
															<p class="mt-1 text-[11px] text-muted-foreground">
																{en
																	? 'all drifts under $1 — nothing material traded'
																	: '偏离都不到 $1 —— 无实质换仓'}
															</p>
														{/if}
													</div>
												{/each}
											</div>
											{#if !showAllTrades && events.length > 24}
												<button
													type="button"
													onclick={() => (showAllTrades = true)}
													class="mt-2 rounded-md border border-border px-3 py-1.5 text-xs text-foreground hover:bg-muted/30"
												>
													{en ? `Show all ${events.length} events` : `展开全部 ${events.length} 次`}
												</button>
											{/if}
										</details>
									{/if}
								{/if}

								<!-- Full config -->
								<div class="mt-4">
									<div class="text-xs font-medium text-muted-foreground">
										{en ? 'Config' : '配置'}
									</div>
									<dl class="mt-1 grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
										<div>
											<dt class="text-muted-foreground">{en ? 'Strategy' : '策略'}</dt>
											<dd>
												{strategyName(j.strategy)}
												<span class="font-mono text-[10px] text-muted-foreground">{j.strategy}</span
												>
											</dd>
										</div>
										{#each Object.entries(j.params) as [k, v], _i (_i)}
											<div>
												<dt class="text-muted-foreground">{k}</dt>
												<dd class="font-mono">{v}</dd>
											</div>
										{/each}
									</dl>
								</div>

								<!-- Turn this exact config into a live signal alert. master_portfolio has no
								     sensible signal mapping (fixed-weight, no entries/exits) — button hidden. -->
								{#if j.strategy !== 'master_portfolio'}
									<div class="mt-4 flex flex-wrap items-center gap-3">
										<button
											type="button"
											onclick={() => toSignal(j)}
											disabled={sigBusy === j.id}
											class="rounded-md border border-border px-3 py-1.5 text-xs text-foreground hover:bg-muted/30 disabled:opacity-50"
										>
											🔔 {en ? 'Turn into a live signal' : '变成实时信号'}
										</button>
										{#if sigMsg[j.id]}
											<span class="text-xs {sigMsg[j.id].ok ? 'text-emerald-600' : 'text-red-600'}"
												>{sigMsg[j.id].text}</span
											>
										{/if}
									</div>
								{/if}
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}

		<!-- Post-aha moment: they've just seen real results — offer Telegram alerts. -->
		<div class="mt-8">
			<AlertSubscribe />
		</div>

		<!-- Manage user-defined signals: list/pause/delete, create new, recent fires. -->
		<div class="mt-4">
			<MySignals />
		</div>
	{/if}
</main>
