<script lang="ts">
	import type { PageData } from './$types';
	import { fmtTime, fmtPct } from '$lib/utils';
	import { vps } from '$lib/api';
	import type { BacktestTrade, BacktestRun } from '$lib/types';
	import { t, type Lang } from '$lib/i18n';
	import InfoTip from '$lib/components/info-tip.svelte';
	import ChartInfo from '$lib/components/chart-info.svelte';

	let { data }: { data: PageData } = $props();
	const lang = $derived<Lang>(data.lang ?? 'zh');

	// Hold-time metrics referenced by some optional charts are NOT part of the
	// api.backtest_runs row (legacy payloads only) — typed optional so those
	// charts degrade to "no data" instead of failing the type-check.
	type RunRow = BacktestRun & {
		holding_avg_hours?: number | null;
		avg_duration_minutes?: number | null;
		avg_duration?: number | null;
	};
	const runs = $derived(data.runs as RunRow[]);

	let strategy = $state('');
	let sort:
		| 'started_desc'
		| 'profit_desc'
		| 'dd_asc'
		| 'calmar_desc'
		| 'sharpe_desc'
		| 'sortino_desc'
		| 'pf_desc'
		| 'trades_desc'
		| 'quality_desc' = $state('started_desc');

	let selected = $state(new Set<number>());
	let detailId = $state<number | null>(null);
	let detailTrades = $state<BacktestTrade[]>([]);
	let detailRun = $state<BacktestRun | null>(null);

	const sortFn = {
		started_desc: (a: BacktestRun, b: BacktestRun) =>
			(b.started_at ?? '').localeCompare(a.started_at ?? ''),
		profit_desc: (a: BacktestRun, b: BacktestRun) =>
			(b.total_profit_pct ?? 0) - (a.total_profit_pct ?? 0),
		dd_asc: (a: BacktestRun, b: BacktestRun) =>
			(a.max_drawdown_pct ?? 99) - (b.max_drawdown_pct ?? 99),
		calmar_desc: (a: BacktestRun, b: BacktestRun) => (b.calmar ?? -99) - (a.calmar ?? -99),
		sharpe_desc: (a: BacktestRun, b: BacktestRun) => (b.sharpe ?? -99) - (a.sharpe ?? -99),
		sortino_desc: (a: BacktestRun, b: BacktestRun) => (b.sortino ?? -99) - (a.sortino ?? -99),
		pf_desc: (a: BacktestRun, b: BacktestRun) =>
			(b.profit_factor ?? -99) - (a.profit_factor ?? -99),
		trades_desc: (a: BacktestRun, b: BacktestRun) => (b.total_trades ?? 0) - (a.total_trades ?? 0),
		quality_desc: (a: BacktestRun, b: BacktestRun) =>
			(qualityScores.get(b.id) ?? 0) - (qualityScores.get(a.id) ?? 0)
	};

	let minProfit = $state<number | null>(null);
	let minSharpe = $state<number | null>(null);
	let maxDD = $state<number | null>(null);

	const profitRange = $derived.by(() => {
		const vals = data.runs.map((r) => r.total_profit_pct ?? 0);
		return { min: Math.floor(Math.min(...vals)), max: Math.ceil(Math.max(...vals)) };
	});
	const sharpeRange = $derived.by(() => {
		const vals = data.runs.map((r) => r.sharpe ?? 0).filter((v) => v > -100);
		return { min: Math.floor(Math.min(...vals, 0)), max: Math.ceil(Math.max(...vals, 5)) };
	});
	const ddRange = $derived.by(() => {
		const vals = data.runs.map((r) => r.max_drawdown_pct ?? 0);
		return { min: 0, max: Math.ceil(Math.max(...vals, 100)) };
	});

	// Composite quality score: z-normalize Sharpe + Profit% - MaxDD, then rescale 0-100
	const qualityScores = $derived.by(() => {
		const valid = data.runs.filter(
			(r) => r.sharpe != null && r.total_profit_pct != null && r.max_drawdown_pct != null
		);
		if (valid.length < 2) return new Map<number, number>();
		function zStats(vals: number[]) {
			const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
			const std = Math.sqrt(vals.reduce((s, v) => s + (v - mean) ** 2, 0) / vals.length) || 1;
			return { mean, std };
		}
		const sharpeS = zStats(valid.map((r) => r.sharpe!));
		const profitS = zStats(valid.map((r) => r.total_profit_pct!));
		const ddS = zStats(valid.map((r) => r.max_drawdown_pct!));
		const rawScores = valid.map((r) => ({
			id: r.id,
			raw:
				((r.sharpe! - sharpeS.mean) / sharpeS.std) * 0.4 +
				((r.total_profit_pct! - profitS.mean) / profitS.std) * 0.35 -
				((r.max_drawdown_pct! - ddS.mean) / ddS.std) * 0.25
		}));
		const mn = Math.min(...rawScores.map((s) => s.raw));
		const mx = Math.max(...rawScores.map((s) => s.raw));
		const range = mx - mn || 1;
		const m = new Map<number, number>();
		for (const s of rawScores) m.set(s.id, Math.round(((s.raw - mn) / range) * 100));
		return m;
	});

	// Best single run by composite quality score
	const goldenRun = $derived.by(() => {
		if (data.runs.length === 0 || qualityScores.size === 0) return null;
		const best = data.runs.reduce((a, b) =>
			(qualityScores.get(b.id) ?? 0) > (qualityScores.get(a.id) ?? 0) ? b : a
		);
		return { run: best, score: qualityScores.get(best.id) ?? 0 };
	});

	let rows = $derived.by(() => {
		let filtered = data.runs.slice();
		if (strategy) filtered = filtered.filter((r) => r.strategy === strategy);
		if (minProfit != null)
			filtered = filtered.filter((r) => (r.total_profit_pct ?? -Infinity) >= minProfit!);
		if (minSharpe != null) filtered = filtered.filter((r) => (r.sharpe ?? -Infinity) >= minSharpe!);
		if (maxDD != null)
			filtered = filtered.filter((r) => (r.max_drawdown_pct ?? Infinity) <= maxDD!);
		filtered.sort(sortFn[sort]);
		return filtered;
	});

	// Profit distribution histogram
	const profitHistogram = $derived.by(() => {
		const vals = data.runs.map((r) => r.total_profit_pct).filter((v): v is number => v != null);
		if (vals.length < 5) return null;
		const mn = Math.floor(Math.min(...vals) / 10) * 10;
		const mx = Math.ceil(Math.max(...vals) / 10) * 10;
		const BINS = 20;
		const step = Math.max(1, (mx - mn) / BINS);
		const buckets: { lo: number; hi: number; count: number }[] = [];
		for (let i = 0; i < BINS; i++) {
			const lo = mn + i * step;
			buckets.push({ lo, hi: lo + step, count: 0 });
		}
		for (const v of vals) {
			const idx = Math.min(BINS - 1, Math.max(0, Math.floor((v - mn) / step)));
			buckets[idx].count++;
		}
		const maxCount = Math.max(1, ...buckets.map((b) => b.count));
		const W = 560,
			H = 80;
		const bw = W / BINS;
		const bars = buckets.map((b, i) => ({
			x: i * bw,
			h: (b.count / maxCount) * (H - 16),
			positive: b.lo >= 0,
			lo: b.lo,
			hi: b.hi,
			count: b.count
		}));
		const zeroX = ((0 - mn) / (mx - mn)) * W;
		const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
		const meanX = ((mean - mn) / (mx - mn)) * W;
		return { bars, W, H, bw, zeroX, meanX, mean, mn, mx, total: vals.length };
	});

	// Run scatter: time × profit per strategy
	const runScatter = $derived.by(() => {
		const pts = data.runs.filter((r) => r.started_at && r.total_profit_pct != null);
		if (pts.length < 4) return null;
		const stratSet = [...new Set(pts.map((p) => p.strategy))];
		const COLORS = [
			'#4a9eff',
			'#34d399',
			'#f59e0b',
			'#f87171',
			'#a78bfa',
			'#fb923c',
			'#60a5fa',
			'#4ade80',
			'#e879f9',
			'#facc15'
		];
		const stratColor = Object.fromEntries(stratSet.map((s, i) => [s, COLORS[i % COLORS.length]]));
		const times = pts.map((p) => new Date(p.started_at!).getTime());
		const tMin = Math.min(...times),
			tMax = Math.max(...times);
		const profits = pts.map((p) => p.total_profit_pct!);
		const pMin = Math.min(...profits) * 1.05,
			pMax = Math.max(...profits) * 1.05;
		const W = 560,
			H = 140,
			PL = 4,
			PR = 4,
			PT = 4,
			PB = 16;
		const tRange = tMax - tMin || 1;
		const pRange = pMax - pMin || 1;
		const toX = (t: number) => PL + ((t - tMin) / tRange) * (W - PL - PR);
		const toY = (p: number) => PT + ((pMax - p) / pRange) * (H - PT - PB);
		const zeroY = toY(0);
		const dots = pts.map((p) => ({
			x: toX(new Date(p.started_at!).getTime()),
			y: toY(p.total_profit_pct!),
			color: stratColor[p.strategy],
			strategy: p.strategy,
			profit: p.total_profit_pct!,
			date: p.started_at!.slice(0, 10)
		}));
		return { dots, W, H, zeroY, stratColor, stratSet: stratSet.slice(0, 8) };
	});

	// Sharpe vs Profit bubble: x=profit%, y=sharpe, size=total_trades
	const sharpeProfitBubble = $derived.by(() => {
		const pts = data.runs.filter(
			(r) => r.total_profit_pct != null && r.sharpe != null && r.total_trades != null
		);
		if (pts.length < 4) return null;
		const xs = pts.map((r) => r.total_profit_pct!);
		const ys = pts.map((r) => r.sharpe!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys);
		const trades = pts.map((r) => r.total_trades!);
		const maxTrades = Math.max(1, ...trades);
		const W = 560,
			H = 140,
			PAD = 16;
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin || 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin || 1)) * (H - PAD * 2);
		const zeroX = toX(0),
			zeroY = toY(0);
		const dots = pts.map((r) => ({
			x: toX(r.total_profit_pct!),
			y: toY(r.sharpe!),
			r: Math.max(2, Math.sqrt(r.total_trades! / maxTrades) * 7),
			strategy: r.strategy,
			profit: r.total_profit_pct!,
			sharpe: r.sharpe!,
			trades: r.total_trades!,
			gold: r.total_profit_pct! > 0 && r.sharpe! > 0
		}));
		return { dots, W, H, PAD, zeroX, zeroY, xMin, xMax, yMin, yMax };
	});

	// Quality vs MaxDD scatter: risk/quality frontier across all runs
	const qualityDdScatter = $derived.by(() => {
		const pts = data.runs.filter(
			(r) => r.max_drawdown_pct != null && qualityScores.get(r.id) != null
		);
		if (pts.length < 4) return null;
		const dds = pts.map((r) => r.max_drawdown_pct!);
		const qs = pts.map((r) => qualityScores.get(r.id)!);
		const ddMax = Math.max(...dds),
			ddMin = Math.min(0, ...dds);
		const qMax = Math.max(...qs),
			qMin = Math.min(...qs);
		const W = 560,
			H = 130,
			PAD = 16;
		const toX = (v: number) => PAD + ((v - ddMin) / (ddMax - ddMin || 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - qMin) / (qMax - qMin || 1)) * (H - PAD * 2);
		const dots = pts.map((r) => ({
			x: toX(r.max_drawdown_pct!),
			y: toY(qualityScores.get(r.id)!),
			strategy: r.strategy,
			dd: r.max_drawdown_pct!,
			q: qualityScores.get(r.id)!,
			profit: r.total_profit_pct ?? null,
			id: r.id
		}));
		// Pareto-optimal frontier: low DD + high quality
		const paretoFront = [...dots]
			.filter((d) => {
				return !dots.some((o) => o.id !== d.id && o.dd <= d.dd && o.q >= d.q);
			})
			.sort((a, b) => a.dd - b.dd);
		const frontLine = paretoFront.map((d) => `${d.x.toFixed(1)},${d.y.toFixed(1)}`).join(' ');
		return { dots, W, H, PAD, frontLine, ddMin, ddMax, qMin, qMax };
	});

	// Top pairs across all runs: aggregate pair frequency
	// Win rate vs total trades scatter — more trades = more reliable signal?
	const winRateTradeScatter = $derived.by(() => {
		const pts = data.runs.filter(
			(r) => r.win_rate_pct != null && r.total_trades != null && r.total_trades > 0
		);
		if (pts.length < 6) return null;
		const xs = pts.map((r) => r.total_trades!);
		const ys = pts.map((r) => r.win_rate_pct!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs);
		const yMin = Math.min(...ys, 0),
			yMax = Math.max(...ys, 1);
		const W = 520,
			H = 120,
			PAD = 20;
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin || 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin || 1)) * (H - PAD * 2);
		const fiftyY = toY(50);
		const dots = pts.map((r) => ({
			x: toX(r.total_trades!),
			y: toY(r.win_rate_pct!),
			wr: r.win_rate_pct!,
			trades: r.total_trades!,
			profit: r.total_profit_pct,
			strategy: r.strategy
		}));
		return { dots, W, H, PAD, fiftyY, xMin, xMax, yMin, yMax };
	});

	// Sortino ratio histogram across all runs
	const sortinoHistogram = $derived.by(() => {
		const vals = data.runs
			.map((r) => r.sortino)
			.filter((v): v is number => v != null && v > -10 && v < 20);
		if (vals.length < 5) return null;
		const BUCKETS = [
			{ label: '<0', lo: -Infinity, hi: 0, count: 0, color: 'var(--ch-loss)' },
			{ label: '0–1', lo: 0, hi: 1, count: 0, color: 'var(--ch-warn-light)' },
			{ label: '1–2', lo: 1, hi: 2, count: 0, color: 'var(--ch-profit-light)' },
			{ label: '2–4', lo: 2, hi: 4, count: 0, color: 'var(--ch-profit)' },
			{ label: '4+', lo: 4, hi: Infinity, count: 0, color: 'var(--ch-profit-strong)' }
		];
		for (const v of vals) {
			const b = BUCKETS.find((bk) => v >= bk.lo && v < bk.hi);
			if (b) b.count++;
		}
		const maxCount = Math.max(1, ...BUCKETS.map((b) => b.count));
		const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
		return {
			buckets: BUCKETS.map((b) => ({ ...b, barPct: (b.count / maxCount) * 100 })),
			avg,
			total: vals.length
		};
	});

	// Profit Factor histogram across all runs
	const profitFactorHist = $derived.by(() => {
		const vals = data.runs
			.map((r) => r.profit_factor)
			.filter((v): v is number => v != null && v > 0 && v < 20);
		if (vals.length < 5) return null;
		const BUCKETS = [
			{ label: '<0.8', lo: 0, hi: 0.8, count: 0, color: 'var(--ch-loss)' },
			{ label: '0.8-1', lo: 0.8, hi: 1, count: 0, color: 'var(--ch-loss-light)' },
			{ label: '1-1.5', lo: 1, hi: 1.5, count: 0, color: 'var(--ch-warn-light)' },
			{ label: '1.5-2', lo: 1.5, hi: 2, count: 0, color: 'var(--ch-profit-light)' },
			{ label: '2-3', lo: 2, hi: 3, count: 0, color: 'var(--ch-profit)' },
			{ label: '3+', lo: 3, hi: Infinity, count: 0, color: 'var(--ch-profit-strong)' }
		];
		for (const v of vals) {
			const b = BUCKETS.find((bk) => v >= bk.lo && v < bk.hi);
			if (b) b.count++;
		}
		const maxCount = Math.max(1, ...BUCKETS.map((b) => b.count));
		const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
		return {
			buckets: BUCKETS.map((b) => ({ ...b, barPct: (b.count / maxCount) * 100 })),
			avg,
			total: vals.length
		};
	});

	const topPairsAcrossRuns = $derived.by(() => {
		const map = new Map<string, { runCount: number; strategies: Set<string> }>();
		for (const r of data.runs) {
			if (!r.pairs || r.pairs.length === 0) continue;
			for (const pair of r.pairs) {
				if (!map.has(pair)) map.set(pair, { runCount: 0, strategies: new Set() });
				const e = map.get(pair)!;
				e.runCount++;
				e.strategies.add(r.strategy);
			}
		}
		const rows = [...map.entries()]
			.map(([pair, v]) => ({ pair, runCount: v.runCount, stratCount: v.strategies.size }))
			.sort((a, b) => b.runCount - a.runCount)
			.slice(0, 16);
		if (rows.length < 3) return null;
		const maxRuns = Math.max(1, ...rows.map((r) => r.runCount));
		return rows.map((r) => ({ ...r, barPct: (r.runCount / maxRuns) * 100 }));
	});

	// Timeframe performance breakdown
	const timeframeBreakdown = $derived.by(() => {
		const TF_ORDER = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '8h', '1d'];
		const map = new Map<string, { count: number; profits: number[]; sharpes: number[] }>();
		for (const r of data.runs) {
			const tf = r.timeframe;
			if (!tf) continue;
			if (!map.has(tf)) map.set(tf, { count: 0, profits: [], sharpes: [] });
			const entry = map.get(tf)!;
			entry.count++;
			if (r.total_profit_pct != null) entry.profits.push(r.total_profit_pct);
			if (r.sharpe != null) entry.sharpes.push(r.sharpe);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([tf, v]) => ({
				tf,
				count: v.count,
				avgProfit: v.profits.length
					? v.profits.reduce((a, b) => a + b, 0) / v.profits.length
					: null,
				avgSharpe: v.sharpes.length ? v.sharpes.reduce((a, b) => a + b, 0) / v.sharpes.length : null
			}))
			.sort(
				(a, b) => ((TF_ORDER.indexOf(a.tf) + 99) % 100) - ((TF_ORDER.indexOf(b.tf) + 99) % 100)
			);
		const maxCount = Math.max(1, ...rows.map((r) => r.count));
		return rows.map((r) => ({ ...r, barPct: (r.count / maxCount) * 100 }));
	});

	// Monthly backtest activity bars
	const monthlyActivity = $derived.by(() => {
		const runs = data.runs.filter((r) => r.started_at);
		if (runs.length < 3) return null;
		const byMonth = new Map<string, number>();
		for (const r of runs) {
			const key = r.started_at!.slice(0, 7); // YYYY-MM
			byMonth.set(key, (byMonth.get(key) ?? 0) + 1);
		}
		const entries = [...byMonth.entries()].sort((a, b) => a[0].localeCompare(b[0])).slice(-18);
		if (entries.length < 2) return null;
		const maxCount = Math.max(1, ...entries.map(([, n]) => n));
		return entries.map(([month, count]) => ({ month, count, barPct: (count / maxCount) * 100 }));
	});

	// Strategy reliability: % of runs that are profitable per strategy
	const strategyReliability = $derived.by(() => {
		const byStrat = new Map<string, { total: number; profitable: number; avgProfit: number }>();
		for (const r of data.runs) {
			if (r.total_profit_pct == null) continue;
			const s = r.strategy;
			if (!byStrat.has(s)) byStrat.set(s, { total: 0, profitable: 0, avgProfit: 0 });
			const e = byStrat.get(s)!;
			e.total++;
			e.avgProfit += r.total_profit_pct;
			if (r.total_profit_pct > 0) e.profitable++;
		}
		const rows = [...byStrat.entries()]
			.filter(([, v]) => v.total >= 2)
			.map(([strategy, v]) => ({
				strategy,
				total: v.total,
				profitable: v.profitable,
				rate: v.profitable / v.total,
				avgProfit: v.avgProfit / v.total
			}))
			.sort((a, b) => b.rate - a.rate || b.profitable - a.profitable);
		if (rows.length < 2) return null;
		return rows;
	});

	// Best run per strategy: comparison matrix
	const strategyComparison = $derived.by(() => {
		const byStrat = new Map<string, BacktestRun>();
		for (const r of data.runs) {
			if (r.total_profit_pct == null) continue;
			const existing = byStrat.get(r.strategy);
			if (!existing || (qualityScores.get(r.id) ?? 0) > (qualityScores.get(existing.id) ?? 0)) {
				byStrat.set(r.strategy, r);
			}
		}
		const rows = [...byStrat.values()].sort(
			(a, b) => (qualityScores.get(b.id) ?? 0) - (qualityScores.get(a.id) ?? 0)
		);
		if (rows.length < 2) return null;
		const maxProfit = Math.max(1, ...rows.map((r) => Math.abs(r.total_profit_pct ?? 0)));
		const maxSharpe = Math.max(0.1, ...rows.map((r) => r.sharpe ?? 0));
		return rows.map((r) => ({
			strategy: r.strategy,
			profit: r.total_profit_pct ?? null,
			sharpe: r.sharpe ?? null,
			calmar: r.calmar ?? null,
			dd: r.max_drawdown_pct ?? null,
			trades: r.total_trades ?? null,
			score: qualityScores.get(r.id) ?? 0,
			profitBar: Math.min(100, (Math.abs(r.total_profit_pct ?? 0) / maxProfit) * 100),
			sharpeBar: Math.min(100, (Math.max(0, r.sharpe ?? 0) / maxSharpe) * 100),
			profitPos: (r.total_profit_pct ?? 0) >= 0
		}));
	});

	async function showDetail(id: number) {
		detailId = id;
		detailRun = data.runs.find((r) => r.id === id) ?? null;
		detailTrades = [];
		try {
			detailTrades = await vps.backtestTrades(fetch, id);
		} catch (e) {
			console.error(e);
		}
	}

	function toggle(id: number) {
		if (selected.has(id)) selected.delete(id);
		else if (selected.size < 2) selected.add(id);
		selected = new Set(selected); // force reactivity
	}

	// ── Comparison panel derived state ──────────────────────────────────────
	const compareRuns = $derived(data.runs.filter((r) => selected.has(r.id)));

	type MetricDef = {
		label: string;
		key: keyof BacktestRun;
		higherBetter: boolean;
		fmt: (v: number) => string;
	};

	const compareMetrics: MetricDef[] = [
		{
			label: 'Profit%',
			key: 'total_profit_pct',
			higherBetter: true,
			fmt: (v) => fmtPct(v)
		},
		{
			label: 'MaxDD%',
			key: 'max_drawdown_pct',
			higherBetter: false,
			fmt: (v) => v.toFixed(2) + '%'
		},
		{ label: 'Calmar', key: 'calmar', higherBetter: true, fmt: (v) => v.toFixed(2) },
		{ label: 'Sharpe', key: 'sharpe', higherBetter: true, fmt: (v) => v.toFixed(2) },
		{ label: 'Sortino', key: 'sortino', higherBetter: true, fmt: (v) => v.toFixed(2) },
		{
			label: 'Win Rate',
			key: 'win_rate_pct',
			higherBetter: true,
			fmt: (v) => v.toFixed(1) + '%'
		},
		{ label: 'Trades', key: 'total_trades', higherBetter: true, fmt: (v) => String(v) },
		{
			label: 'PF',
			key: 'profit_factor',
			higherBetter: true,
			fmt: (v) => v.toFixed(2)
		}
	];

	function getMetricValue(run: BacktestRun, key: keyof BacktestRun): number {
		const v = run[key];
		return typeof v === 'number' ? v : 0;
	}

	/** Returns fraction 0-1 for the bar width relative to the max absolute value across both runs */
	function barFraction(metric: MetricDef, runIndex: number): number {
		if (compareRuns.length < 2) return 0;
		const vals = compareRuns.map((r) => Math.abs(getMetricValue(r, metric.key)));
		const max = Math.max(...vals, 0.0001);
		return Math.abs(getMetricValue(compareRuns[runIndex], metric.key)) / max;
	}

	function isBetter(metric: MetricDef, runIndex: number): boolean {
		if (compareRuns.length < 2) return false;
		const a = getMetricValue(compareRuns[0], metric.key);
		const b = getMetricValue(compareRuns[1], metric.key);
		const val = runIndex === 0 ? a : b;
		const other = runIndex === 0 ? b : a;
		if (metric.higherBetter) return val >= other;
		return val <= other;
	}

	// ── Radar chart for compare panel ──────────────────────────────────────
	const RADAR_AXES = [
		{ label: 'Profit%', key: 'total_profit_pct' as keyof BacktestRun, higher: true },
		{ label: 'Sharpe', key: 'sharpe' as keyof BacktestRun, higher: true },
		{ label: 'Calmar', key: 'calmar' as keyof BacktestRun, higher: true },
		{ label: 'Win%', key: 'win_rate_pct' as keyof BacktestRun, higher: true },
		{ label: 'PF', key: 'profit_factor' as keyof BacktestRun, higher: true },
		{ label: 'LowDD', key: 'max_drawdown_pct' as keyof BacktestRun, higher: false }
	];
	const radarData = $derived.by(() => {
		if (compareRuns.length < 2) return null;
		const R = 80,
			CX = 110,
			CY = 95;
		const n = RADAR_AXES.length;
		const ranges = RADAR_AXES.map((ax) => {
			const vals = compareRuns.map((r) => {
				const v = r[ax.key];
				return typeof v === 'number' ? Math.abs(v) : 0;
			});
			return Math.max(0.001, ...vals);
		});
		function normalize(ax: (typeof RADAR_AXES)[0], run: BacktestRun, range: number) {
			const raw = run[ax.key];
			const v = typeof raw === 'number' ? (ax.higher ? raw : -raw) : 0;
			const minV = ax.higher ? 0 : -range;
			return Math.max(0, Math.min(1, (v - minV) / (range * (ax.higher ? 1 : 2) || 1)));
		}
		function poly(run: BacktestRun) {
			return RADAR_AXES.map((ax, i) => {
				const angle = (2 * Math.PI * i) / n - Math.PI / 2;
				const norm = normalize(ax, run, ranges[i]);
				return [CX + R * norm * Math.cos(angle), CY + R * norm * Math.sin(angle)];
			});
		}
		const spokes = RADAR_AXES.map((ax, i) => {
			const angle = (2 * Math.PI * i) / n - Math.PI / 2;
			return {
				x: CX + R * Math.cos(angle),
				y: CY + R * Math.sin(angle),
				label: ax.label,
				lx: CX + (R + 14) * Math.cos(angle),
				ly: CY + (R + 14) * Math.sin(angle)
			};
		});
		const grid = [0.25, 0.5, 0.75, 1].map((f) =>
			RADAR_AXES.map((_, i) => {
				const angle = (2 * Math.PI * i) / n - Math.PI / 2;
				return [CX + R * f * Math.cos(angle), CY + R * f * Math.sin(angle)];
			})
		);
		return { poly0: poly(compareRuns[0]), poly1: poly(compareRuns[1]), spokes, grid, CX, CY, R };
	});

	// ── Analysis tabs state ─────────────────────────────────────────────────
	let activeTab = $state<'pair' | 'exit'>('pair');

	type PairStat = {
		pair: string;
		total_profit_abs: number;
		mean_profit_pct: number;
		count: number;
		win_count: number;
		win_rate: number;
	};

	type ExitStat = {
		exit_reason: string;
		count: number;
		total_profit_abs: number;
		mean_profit_pct: number;
		win_rate: number;
	};

	const pairStats = $derived.by((): PairStat[] => {
		const map = new Map<string, { profit_abs: number[]; profit_pct: number[] }>();
		for (const trade of detailTrades) {
			const key = trade.pair;
			if (!map.has(key)) map.set(key, { profit_abs: [], profit_pct: [] });
			map.get(key)!.profit_abs.push(trade.profit_abs ?? 0);
			map.get(key)!.profit_pct.push(trade.profit_pct ?? 0);
		}
		const stats: PairStat[] = [];
		for (const [pair, d] of map) {
			const count = d.profit_abs.length;
			const total_profit_abs = d.profit_abs.reduce((s, v) => s + v, 0);
			const mean_profit_pct = d.profit_pct.reduce((s, v) => s + v, 0) / count;
			const win_count = d.profit_pct.filter((v) => v > 0).length;
			const win_rate = (win_count / count) * 100;
			stats.push({ pair, total_profit_abs, mean_profit_pct, count, win_count, win_rate });
		}
		return stats.sort((a, b) => b.total_profit_abs - a.total_profit_abs).slice(0, 15);
	});

	const pairBarMax = $derived.by(() => {
		if (pairStats.length === 0) return 1;
		return Math.max(...pairStats.map((s) => Math.abs(s.total_profit_abs)), 0.0001);
	});

	const exitStats = $derived.by((): ExitStat[] => {
		const map = new Map<string, { profit_abs: number[]; profit_pct: number[] }>();
		for (const trade of detailTrades) {
			const key = trade.exit_reason ?? 'unknown';
			if (!map.has(key)) map.set(key, { profit_abs: [], profit_pct: [] });
			map.get(key)!.profit_abs.push(trade.profit_abs ?? 0);
			map.get(key)!.profit_pct.push(trade.profit_pct ?? 0);
		}
		const stats: ExitStat[] = [];
		for (const [exit_reason, d] of map) {
			const count = d.profit_abs.length;
			const total_profit_abs = d.profit_abs.reduce((s, v) => s + v, 0);
			const mean_profit_pct = d.profit_pct.reduce((s, v) => s + v, 0) / count;
			const win_count = d.profit_pct.filter((v) => v > 0).length;
			const win_rate = (win_count / count) * 100;
			stats.push({ exit_reason, count, total_profit_abs, mean_profit_pct, win_rate });
		}
		return stats.sort((a, b) => b.total_profit_abs - a.total_profit_abs);
	});

	function exitReasonChipClass(reason: string): string {
		if (reason === 'roi' || reason === 'custom_exit')
			return 'bg-green-900/50 text-green-300 border border-green-700/50';
		if (reason === 'stop_loss' || reason === 'force_exit')
			return 'bg-red-900/50 text-red-300 border border-red-700/50';
		return 'bg-secondary text-secondary-foreground border border-border';
	}

	// ── Equity curve derived state ───────────────────────────────────────────
	// Strategy activity timeline: run count per month, grouped by strategy
	const strategyActivityTimeline = $derived.by(() => {
		const runs = data.runs.filter((r) => r.started_at && r.strategy);
		if (runs.length < 5) return null;
		const monthMap = new Map<string, Map<string, number>>();
		for (const r of runs) {
			const month = r.started_at!.slice(0, 7);
			if (!monthMap.has(month)) monthMap.set(month, new Map());
			const sm = monthMap.get(month)!;
			sm.set(r.strategy, (sm.get(r.strategy) ?? 0) + 1);
		}
		const months = [...monthMap.keys()].sort().slice(-12);
		if (months.length < 2) return null;
		const strategies = [...new Set(runs.map((r) => r.strategy))].slice(0, 10);
		const grid = strategies.map((s) => ({
			strategy: s,
			months: months.map((m) => ({ month: m, count: monthMap.get(m)?.get(s) ?? 0 }))
		}));
		const maxCount = Math.max(1, ...grid.flatMap((g) => g.months.map((m) => m.count)));
		return { grid, months, maxCount };
	});

	// Profit vs Calmar bubble scatter: raw return vs risk-adjusted return, size = trade count
	const profitCalmarBubble = $derived.by(() => {
		const pts = data.runs.filter(
			(r) =>
				r.total_profit_pct != null &&
				r.calmar != null &&
				r.calmar > -100 &&
				r.total_trades != null &&
				r.total_trades > 0
		);
		if (pts.length < 5) return null;
		const xs = pts.map((r) => r.total_profit_pct!);
		const ys = pts.map((r) => r.calmar!);
		const sizes = pts.map((r) => r.total_trades!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, 0.001);
		const yMin = Math.min(...ys, 0),
			yMax = Math.max(...ys, 0.001);
		const sMin = Math.min(...sizes),
			sMax = Math.max(...sizes, 1);
		const W = 520,
			H = 130,
			PAD = 24;
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin || 0.001)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin || 0.001)) * (H - PAD * 2);
		const toR = (v: number) => 3 + ((v - sMin) / (sMax - sMin || 1)) * 8;
		const zeroX = toX(0),
			zeroY = toY(0);
		const dots = pts.map((r) => ({
			x: toX(r.total_profit_pct!),
			y: toY(r.calmar!),
			r: toR(r.total_trades!),
			profit: r.total_profit_pct!,
			calmar: r.calmar!,
			trades: r.total_trades!,
			strategy: r.strategy
		}));
		return { dots, W, H, PAD, zeroX, zeroY, xMin, xMax, yMin, yMax };
	});

	// Timeframe × strategy win rate matrix: avg win rate per TF per strategy (top 8 strats)
	const timeframeWinRateMatrix = $derived.by(() => {
		const runs = data.runs.filter((r) => r.timeframe && r.strategy && r.win_rate_pct != null);
		if (runs.length < 6) return null;
		const timeframes = [...new Set(runs.map((r) => r.timeframe!))].sort();
		const stratCounts = new Map<string, number>();
		for (const r of runs) stratCounts.set(r.strategy, (stratCounts.get(r.strategy) ?? 0) + 1);
		const strategies = [...stratCounts.entries()]
			.sort((a, b) => b[1] - a[1])
			.slice(0, 8)
			.map((e) => e[0]);
		if (strategies.length < 2 || timeframes.length < 2) return null;
		const grid = strategies.map((s) => ({
			strategy: s,
			cells: timeframes.map((tf) => {
				const bucket = runs.filter((r) => r.strategy === s && r.timeframe === tf);
				if (bucket.length === 0) return null;
				const avg = bucket.reduce((sum, r) => sum + r.win_rate_pct!, 0) / bucket.length;
				return { avg, count: bucket.length };
			})
		}));
		return { grid, strategies, timeframes };
	});

	// Timeframe Calmar ranking: avg calmar, profit, and win rate per timeframe
	const timeframeCalmarRanking = $derived.by(() => {
		const valid = data.runs.filter(
			(r) => r.timeframe && r.calmar != null && r.calmar > -100 && r.calmar < 200
		);
		if (valid.length < 5) return null;
		const map = new Map<
			string,
			{ calmarSum: number; profitSum: number; wrSum: number; wrCount: number; count: number }
		>();
		for (const r of valid) {
			if (!map.has(r.timeframe!))
				map.set(r.timeframe!, { calmarSum: 0, profitSum: 0, wrSum: 0, wrCount: 0, count: 0 });
			const v = map.get(r.timeframe!)!;
			v.calmarSum += r.calmar!;
			v.profitSum += r.total_profit_pct ?? 0;
			v.count++;
			if (r.win_rate_pct != null) {
				v.wrSum += r.win_rate_pct;
				v.wrCount++;
			}
		}
		const TF_ORDER = [
			'1m',
			'3m',
			'5m',
			'15m',
			'30m',
			'1h',
			'2h',
			'4h',
			'6h',
			'8h',
			'12h',
			'1d',
			'3d',
			'1w'
		];
		const rows = [...map.entries()]
			.map(([tf, v]) => ({
				tf,
				avgCalmar: v.calmarSum / v.count,
				avgProfit: v.profitSum / v.count,
				avgWr: v.wrCount > 0 ? v.wrSum / v.wrCount : null,
				count: v.count
			}))
			.sort((a, b) => TF_ORDER.indexOf(a.tf) - TF_ORDER.indexOf(b.tf) || a.tf.localeCompare(b.tf));
		if (rows.length < 2) return null;
		const maxAbsCalmar = Math.max(0.01, ...rows.map((r) => Math.abs(r.avgCalmar)));
		return rows.map((r) => ({ ...r, calmarBarPct: (r.avgCalmar / maxAbsCalmar) * 100 }));
	});

	// Strategy run profit range: best vs worst run per strategy (min 3 runs)
	const strategyRunProfitRange = $derived.by(() => {
		const valid = data.runs.filter((r) => r.total_profit_pct != null);
		if (valid.length < 6) return null;
		const map = new Map<string, number[]>();
		for (const r of valid) {
			if (!map.has(r.strategy)) map.set(r.strategy, []);
			map.get(r.strategy)!.push(r.total_profit_pct!);
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.length >= 3)
			.map(([strategy, profits]) => {
				profits.sort((a, b) => a - b);
				const best = profits[profits.length - 1];
				const worst = profits[0];
				const median = profits[Math.floor(profits.length / 2)];
				return { strategy, best, worst, median, spread: best - worst, count: profits.length };
			})
			.sort((a, b) => b.best - a.best)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxSpread = Math.max(0.01, ...rows.map((r) => r.spread));
		const minVal = Math.min(...rows.map((r) => r.worst));
		const maxVal = Math.max(...rows.map((r) => r.best));
		const range = maxVal - minVal || 0.01;
		return rows.map((r) => ({
			...r,
			worstPct: ((r.worst - minVal) / range) * 100,
			bestPct: ((r.best - minVal) / range) * 100,
			medianPct: ((r.median - minVal) / range) * 100,
			spreadBarPct: (r.spread / maxSpread) * 100
		}));
	});

	// Profit vs Sortino scatter: colored by timeframe
	// Calmar vs Sortino scatter: do both risk-adjusted metrics agree on run quality?
	// Avg profit_factor per timeframe: distinct from timeframeCalmarRanking (Calmar) and timeframeWinRateMatrix (WR)
	const profitFactorByTimeframe = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const r of data.runs) {
			if (!r.timeframe || r.profit_factor == null || r.profit_factor <= 0 || r.profit_factor > 50)
				continue;
			if (!map.has(r.timeframe)) map.set(r.timeframe, []);
			map.get(r.timeframe)!.push(r.profit_factor);
		}
		const rows = [...map.entries()]
			.map(([tf, vals]) => ({
				tf,
				avg: vals.reduce((a, b) => a + b, 0) / vals.length,
				count: vals.length
			}))
			.filter((r) => r.count >= 3)
			.sort((a, b) => b.avg - a.avg);
		if (rows.length < 2) return null;
		const maxAvg = Math.max(0.01, ...rows.map((r) => r.avg));
		return rows.map((r) => ({ ...r, barPct: (r.avg / maxAvg) * 100 }));
	});

	const calmarVsSortino = $derived.by(() => {
		const pts = data.runs.filter(
			(r) =>
				r.calmar != null &&
				r.calmar > 0 &&
				r.calmar < 50 &&
				r.sortino != null &&
				r.sortino > -10 &&
				r.sortino < 50 &&
				r.total_profit_pct != null
		);
		if (pts.length < 6) return null;
		const xs = pts.map((r) => r.calmar!);
		const ys = pts.map((r) => r.sortino!);
		const profits = pts.map((r) => r.total_profit_pct!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 0.01);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.01);
		const pMin = Math.min(...profits),
			pMax = Math.max(...profits, pMin + 0.01);
		const W = 520,
			H = 130,
			PAD = 20;
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const colorFor = (p: number) => {
			const t = (p - pMin) / (pMax - pMin);
			if (t > 0.66) return 'var(--ch-profit)';
			if (t > 0.33) return 'var(--ch-warn-light)';
			return 'var(--ch-loss-light)';
		};
		const n = xs.length;
		const mx = xs.reduce((a, b) => a + b, 0) / n,
			my = ys.reduce((a, b) => a + b, 0) / n;
		const num = xs.reduce((s, x, i) => s + (x - mx) * (ys[i] - my), 0);
		const den = Math.sqrt(
			xs.reduce((s, x) => s + (x - mx) ** 2, 0) * ys.reduce((s, y) => s + (y - my) ** 2, 0)
		);
		const corr = den === 0 ? 0 : num / den;
		const dots = pts.map((r) => ({
			x: toX(r.calmar!),
			y: toY(r.sortino!),
			color: colorFor(r.total_profit_pct!),
			calmar: r.calmar!,
			sortino: r.sortino!,
			profit: r.total_profit_pct!,
			strategy: r.strategy,
			tf: r.timeframe ?? '?'
		}));
		return { dots, W, H, PAD, xMin, xMax, yMin, yMax, corr };
	});

	const profitVsSortino = $derived.by(() => {
		const pts = data.runs.filter(
			(r) =>
				r.total_profit_pct != null &&
				r.sortino != null &&
				r.sortino > -10 &&
				r.sortino < 50 &&
				r.timeframe
		);
		if (pts.length < 6) return null;
		const xs = pts.map((r) => r.sortino!);
		const ys = pts.map((r) => r.total_profit_pct!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 0.01);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.01);
		const W = 520,
			H = 130,
			PAD = 24;
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const tfs = [...new Set(pts.map((r) => r.timeframe!))].sort();
		const palette = [
			'var(--ch-violet)',
			'var(--ch-profit)',
			'var(--ch-warn)',
			'var(--ch-loss)',
			'var(--ch-violet-strong)',
			'var(--ch-teal)'
		];
		const tfColor = Object.fromEntries(tfs.map((tf, i) => [tf, palette[i % palette.length]]));
		const zeroX = toX(0),
			zeroY = toY(0);
		const dots = pts.map((r) => ({
			x: toX(r.sortino!),
			y: toY(r.total_profit_pct!),
			color: tfColor[r.timeframe!],
			tf: r.timeframe!,
			sortino: r.sortino!,
			profit: r.total_profit_pct!
		}));
		return { dots, W, H, PAD, zeroX, zeroY, tfs, tfColor };
	});

	const equitySeries = $derived.by(() => {
		const closed = detailTrades
			.filter((t) => t.close_date && t.profit_abs != null)
			.sort((a, b) => a.close_date!.localeCompare(b.close_date!));
		let cum = 0;
		return closed.map((t) => {
			cum += t.profit_abs!;
			return { date: t.close_date!, value: cum };
		});
	});

	/** Build the SVG polyline points string from equitySeries */
	const equitySvgData = $derived.by(() => {
		const series = equitySeries;
		if (series.length < 2) return null;

		const W = 600;
		const H = 120;
		const PAD = { top: 8, bottom: 24, left: 8, right: 8 };
		const innerW = W - PAD.left - PAD.right;
		const innerH = H - PAD.top - PAD.bottom;

		const values = series.map((s) => s.value);
		const minV = Math.min(...values);
		const maxV = Math.max(...values);
		const range = maxV - minV || 1;

		const toX = (i: number) => PAD.left + (i / (series.length - 1)) * innerW;
		const toY = (v: number) => PAD.top + (1 - (v - minV) / range) * innerH;

		const points = series
			.map((s, i) => `${toX(i).toFixed(1)},${toY(s.value).toFixed(1)}`)
			.join(' ');
		const areaPath =
			`M${toX(0).toFixed(1)},${toY(series[0].value).toFixed(1)} ` +
			series
				.slice(1)
				.map((s, i) => `L${toX(i + 1).toFixed(1)},${toY(s.value).toFixed(1)}`)
				.join(' ') +
			` L${toX(series.length - 1).toFixed(1)},${(PAD.top + innerH).toFixed(1)} L${PAD.left.toFixed(1)},${(PAD.top + innerH).toFixed(1)} Z`;

		const finalVal = series[series.length - 1].value;
		const isProfit = finalVal >= 0;
		const lineColor = isProfit ? '#22c55e' : '#ef4444';
		const gradId = `eq-grad-${detailId ?? 0}`;

		// Zero line Y
		const zeroY = minV < 0 && maxV > 0 ? toY(0) : null;

		// Max drawdown region: find peak then trough
		let peakI = 0;
		let peakVal = values[0];
		let worstDd = 0;
		let worstPeakI = 0;
		let worstTroughI = 0;
		for (let i = 1; i < values.length; i++) {
			if (values[i] > peakVal) {
				peakI = i;
				peakVal = values[i];
			}
			const dd = peakVal - values[i];
			if (dd > worstDd) {
				worstDd = dd;
				worstPeakI = peakI;
				worstTroughI = i;
			}
		}
		const ddX1 = toX(worstPeakI);
		const ddX2 = toX(worstTroughI);
		const ddRegion =
			worstDd > 0 ? { x: ddX1, width: ddX2 - ddX1, y: PAD.top, height: innerH } : null;

		const startLabel = series[0].value.toFixed(2);
		const endLabel = finalVal.toFixed(2);

		return {
			W,
			H,
			PAD,
			innerH,
			points,
			areaPath,
			lineColor,
			gradId,
			zeroY,
			ddRegion,
			startLabel,
			endLabel,
			finalVal,
			isProfit,
			firstX: toX(0),
			lastX: toX(series.length - 1)
		};
	});

	// Holding time vs profit scatter: shows if longer-held runs tend to be more/less profitable
	const holdingTimeVsProfit = $derived.by(() => {
		const pts = runs.filter(
			(r) =>
				r.holding_avg_hours != null &&
				r.holding_avg_hours > 0 &&
				r.holding_avg_hours < 5000 &&
				r.total_profit_pct != null
		);
		if (pts.length < 10) return null;
		const xs = pts.map((r) => r.holding_avg_hours!);
		const ys = pts.map((r) => r.total_profit_pct!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 1);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.01);
		const W = 520,
			H = 120,
			PAD = 20;
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const zeroY = toY(0);
		const n = xs.length;
		const mx = xs.reduce((a, b) => a + b, 0) / n,
			my = ys.reduce((a, b) => a + b, 0) / n;
		const num = xs.reduce((s, x, i) => s + (x - mx) * (ys[i] - my), 0);
		const den = Math.sqrt(
			xs.reduce((s, x) => s + (x - mx) ** 2, 0) * ys.reduce((s, y) => s + (y - my) ** 2, 0)
		);
		const corr = den === 0 ? 0 : num / den;
		const dots = pts.map((r) => ({
			cx: toX(r.holding_avg_hours!),
			cy: toY(r.total_profit_pct!),
			color: r.total_profit_pct! >= 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)',
			title: `${r.strategy} · ${r.holding_avg_hours!.toFixed(1)}h hold · ${r.total_profit_pct! >= 0 ? '+' : ''}${r.total_profit_pct!.toFixed(1)}%`
		}));
		return { dots, W, H, PAD, zeroY, xMin, xMax, corr };
	});

	const calmarVsWinRate = $derived.by(() => {
		const pts = data.runs.filter(
			(r) =>
				r.calmar != null &&
				isFinite(r.calmar) &&
				r.win_rate_pct != null &&
				isFinite(r.win_rate_pct) &&
				r.calmar > -20 &&
				r.calmar < 50
		);
		if (pts.length < 8) return null;
		const W = 560,
			H = 110,
			PAD = 10;
		const xs = pts.map((r) => r.calmar!),
			ys = pts.map((r) => r.win_rate_pct!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 0.1);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.1);
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const mx = xs.reduce((a, b) => a + b, 0) / pts.length,
			my = ys.reduce((a, b) => a + b, 0) / pts.length;
		const num = xs.reduce((s, x, i) => s + (x - mx) * (ys[i] - my), 0);
		const den = Math.sqrt(
			xs.reduce((s, x) => s + (x - mx) ** 2, 0) * ys.reduce((s, y) => s + (y - my) ** 2, 0)
		);
		const corr = den === 0 ? 0 : num / den;
		const dots = pts.map((r) => ({
			cx: toX(r.calmar!),
			cy: toY(r.win_rate_pct!),
			color:
				r.win_rate_pct! >= 55
					? 'var(--ch-profit-light)'
					: r.win_rate_pct! >= 45
						? 'var(--ch-warn-light)'
						: 'var(--ch-loss-light)',
			title: `${r.strategy} · calmar ${r.calmar!.toFixed(2)} · wr ${r.win_rate_pct!.toFixed(1)}%`
		}));
		return { dots, W, H, PAD, xMin, xMax, yMin, yMax, corr };
	});

	const sortinoVsHolding = $derived.by(() => {
		const pts = runs.filter(
			(r) =>
				r.sortino != null &&
				isFinite(r.sortino) &&
				r.sortino > -50 &&
				r.sortino < 200 &&
				r.holding_avg_hours != null &&
				isFinite(r.holding_avg_hours) &&
				r.holding_avg_hours > 0 &&
				r.holding_avg_hours < 10000
		);
		if (pts.length < 8) return null;
		const W = 560,
			H = 110,
			PAD = 10;
		const xs = pts.map((r) => r.sortino!),
			ys = pts.map((r) => r.holding_avg_hours!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 0.1);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.1);
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const mx = xs.reduce((a, b) => a + b, 0) / pts.length,
			my = ys.reduce((a, b) => a + b, 0) / pts.length;
		const num = xs.reduce((s, x, i) => s + (x - mx) * (ys[i] - my), 0);
		const den = Math.sqrt(
			xs.reduce((s, x) => s + (x - mx) ** 2, 0) * ys.reduce((s, y) => s + (y - my) ** 2, 0)
		);
		const corr = den === 0 ? 0 : num / den;
		const dots = pts.map((r) => ({
			cx: toX(r.sortino!),
			cy: toY(r.holding_avg_hours!),
			color:
				r.sortino! >= 2
					? 'var(--ch-profit-light)'
					: r.sortino! >= 0
						? 'var(--ch-warn-light)'
						: 'var(--ch-loss-light)',
			title: `${r.strategy} · sortino ${r.sortino!.toFixed(2)} · ${r.holding_avg_hours!.toFixed(1)}h hold`
		}));
		return { dots, W, H, PAD, xMin, xMax, yMin, yMax, corr };
	});

	const runCountByMonth = $derived.by(() => {
		const map = new Map<string, number>();
		for (const r of data.runs) {
			const ts = r.imported_at ?? r.started_at;
			if (!ts) continue;
			const ym = ts.slice(0, 7);
			map.set(ym, (map.get(ym) ?? 0) + 1);
		}
		const rows = [...map.entries()]
			.sort((a, b) => a[0].localeCompare(b[0]))
			.map(([ym, count]) => ({ ym, count }));
		if (rows.length < 3) return null;
		const maxCount = Math.max(1, ...rows.map((r) => r.count));
		return rows.map((r) => ({ ...r, barPct: (r.count / maxCount) * 100 }));
	});

	// Profit factor distribution: 10-bucket histogram of profit_factor across all runs (distinct from winRateHistogram win_rate_pct, profitFactorByTimeframe avg by TF)
	const profitFactorDistribution = $derived.by(() => {
		const vals = data.runs
			.filter(
				(r) =>
					r.profit_factor != null &&
					isFinite(r.profit_factor) &&
					r.profit_factor >= 0 &&
					r.profit_factor <= 10
			)
			.map((r) => r.profit_factor!);
		if (vals.length < 8) return null;
		const BUCKETS = [
			{ label: '<0.5', lo: 0, hi: 0.5 },
			{ label: '0.5–1', lo: 0.5, hi: 1 },
			{ label: '1–1.5', lo: 1, hi: 1.5 },
			{ label: '1.5–2', lo: 1.5, hi: 2 },
			{ label: '2–3', lo: 2, hi: 3 },
			{ label: '3–5', lo: 3, hi: 5 },
			{ label: '5–7', lo: 5, hi: 7 },
			{ label: '7–10', lo: 7, hi: 10 }
		];
		const buckets = BUCKETS.map((b) => ({ ...b, count: 0 }));
		for (const v of vals) {
			const idx = buckets.findIndex((b) => v >= b.lo && v < b.hi);
			if (idx >= 0) buckets[idx].count++;
		}
		const maxCount = Math.max(1, ...buckets.map((b) => b.count));
		const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
		const profitableShare = vals.filter((v) => v > 1).length / vals.length;
		return {
			buckets: buckets.map((b) => ({ ...b, barPct: (b.count / maxCount) * 100 })),
			avg,
			profitableShare,
			total: vals.length
		};
	});

	const winRateHistogram = $derived.by(() => {
		const vals = data.runs
			.filter((r) => r.win_rate_pct != null && isFinite(r.win_rate_pct))
			.map((r) => r.win_rate_pct!);
		if (vals.length < 10) return null;
		const buckets = Array.from({ length: 10 }, (_, i) => ({
			label: `${i * 10}–${i * 10 + 10}%`,
			count: 0,
			lo: i * 10,
			hi: i * 10 + 10
		}));
		for (const v of vals) {
			const idx = Math.min(9, Math.floor(v / 10));
			buckets[idx].count++;
		}
		const maxCount = Math.max(1, ...buckets.map((b) => b.count));
		return buckets.map((b) => ({ ...b, barPct: (b.count / maxCount) * 100 }));
	});

	const runDrawdownDistribution = $derived.by(() => {
		const vals = data.runs
			.filter(
				(r) => r.max_drawdown_pct != null && isFinite(r.max_drawdown_pct) && r.max_drawdown_pct >= 0
			)
			.map((r) => r.max_drawdown_pct!);
		if (vals.length < 8) return null;
		const bucketSize = 10;
		const buckets = Array.from({ length: 8 }, (_, i) => ({
			label: `${i * bucketSize}–${(i + 1) * bucketSize}%`,
			count: 0,
			lo: i * bucketSize,
			hi: (i + 1) * bucketSize
		}));
		for (const v of vals) {
			const idx = Math.min(7, Math.floor(v / bucketSize));
			buckets[idx].count++;
		}
		const maxCount = Math.max(1, ...buckets.map((b) => b.count));
		const median = [...vals].sort((a, b) => a - b)[Math.floor(vals.length / 2)];
		return {
			buckets: buckets.map((b) => ({ ...b, barPct: (b.count / maxCount) * 100 })),
			median,
			total: vals.length
		};
	});

	const strategyBestCalmarSortinoScatter = $derived.by(() => {
		const map = new Map<string, { calmar: number; sortino: number }>();
		for (const r of data.runs) {
			if (r.strategy == null || r.calmar == null || r.sortino == null) continue;
			if (!isFinite(r.calmar) || !isFinite(r.sortino) || r.calmar <= 0 || r.sortino <= 0) continue;
			const cur = map.get(r.strategy);
			if (!cur || r.calmar > cur.calmar)
				map.set(r.strategy, { calmar: r.calmar, sortino: r.sortino });
		}
		const pts = [...map.entries()].map(([s, v]) => ({ s, calmar: v.calmar, sortino: v.sortino }));
		if (pts.length < 5) return null;
		const maxC = Math.max(...pts.map((p) => p.calmar)),
			maxSo = Math.max(...pts.map((p) => p.sortino));
		const W = 300,
			H = 80,
			PAD = 12;
		const toX = (c: number) => PAD + (c / maxC) * (W - PAD * 2);
		const toY = (so: number) => H - PAD - (so / maxSo) * (H - PAD * 2);
		const mapped = pts.map((p) => ({
			cx: toX(p.calmar),
			cy: toY(p.sortino),
			calmar: p.calmar,
			sortino: p.sortino,
			label: p.s.slice(0, 8)
		}));
		return { mapped, W, H, PAD, maxC, maxSo };
	});

	const runImportDowDistribution = $derived.by(() => {
		const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
		const counts = Array(7).fill(0);
		let valid = 0;
		for (const r of data.runs) {
			const ts = r.imported_at ?? r.started_at;
			if (!ts) continue;
			const d = new Date(ts).getDay();
			counts[d]++;
			valid++;
		}
		if (valid < 10) return null;
		const maxCount = Math.max(1, ...counts);
		return DAYS.map((day, i) => ({ day, count: counts[i], barPct: (counts[i] / maxCount) * 100 }));
	});

	const strategyProfitSpread = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const r of data.runs) {
			if (!r.strategy || r.total_profit_pct == null || !isFinite(r.total_profit_pct)) continue;
			if (!map.has(r.strategy)) map.set(r.strategy, []);
			map.get(r.strategy)!.push(r.total_profit_pct);
		}
		const rows = [...map.entries()]
			.filter(([, pts]) => pts.length >= 3)
			.map(([name, pts]) => {
				const s = [...pts].sort((a, b) => a - b);
				const med =
					s.length % 2 ? s[Math.floor(s.length / 2)] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
				return {
					name,
					min: s[0],
					med,
					max: s[s.length - 1],
					runs: s.length,
					spread: s[s.length - 1] - s[0]
				};
			})
			.sort((a, b) => b.med - a.med)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const absMax = Math.max(0.01, ...rows.flatMap((r) => [Math.abs(r.min), Math.abs(r.max)]));
		const toBarPct = (v: number) => ((v + absMax) / (2 * absMax)) * 100;
		return { rows, absMax, toBarPct };
	});

	const strategyProfitByTimeframe = $derived.by(() => {
		const map = new Map<string, { sum: number; count: number }>();
		for (const r of data.runs) {
			if (!r.timeframe || r.total_profit_pct == null || !isFinite(r.total_profit_pct)) continue;
			if (!map.has(r.timeframe)) map.set(r.timeframe, { sum: 0, count: 0 });
			const e = map.get(r.timeframe)!;
			e.sum += r.total_profit_pct;
			e.count++;
		}
		if (map.size < 2) return null;
		const TF_ORDER = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d'];
		const rows = [...map.entries()]
			.filter(([, v]) => v.count >= 3)
			.map(([tf, v]) => ({ tf, avg: v.sum / v.count, count: v.count }))
			.sort((a, b) => TF_ORDER.indexOf(a.tf) - TF_ORDER.indexOf(b.tf));
		if (rows.length < 2) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.avg)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.avg) / maxAbs) * 100 }));
	});

	const runSortinoByTimeframe = $derived.by(() => {
		const map = new Map<string, { sum: number; count: number }>();
		for (const r of data.runs) {
			if (
				!r.timeframe ||
				r.sortino == null ||
				!isFinite(r.sortino) ||
				r.sortino < -50 ||
				r.sortino > 500
			)
				continue;
			if (!map.has(r.timeframe)) map.set(r.timeframe, { sum: 0, count: 0 });
			const e = map.get(r.timeframe)!;
			e.sum += r.sortino;
			e.count++;
		}
		if (map.size < 2) return null;
		const TF_ORDER = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d'];
		const rows = [...map.entries()]
			.filter(([, v]) => v.count >= 3)
			.map(([tf, v]) => ({ tf, avg: v.sum / v.count, count: v.count }))
			.sort((a, b) => TF_ORDER.indexOf(a.tf) - TF_ORDER.indexOf(b.tf));
		if (rows.length < 2) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.avg)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.avg) / maxAbs) * 100 }));
	});

	const runProfitCumulativeTimeline = $derived.by(() => {
		const sorted = data.runs
			.filter((r) => r.total_profit_pct != null && isFinite(r.total_profit_pct) && r.imported_at)
			.sort((a, b) => new Date(a.imported_at!).getTime() - new Date(b.imported_at!).getTime());
		if (sorted.length < 10) return null;
		let cum = 0;
		const pts = sorted.map((r) => {
			cum += r.total_profit_pct!;
			return cum;
		});
		const mn = Math.min(...pts),
			mx = Math.max(...pts);
		const range = mx - mn || 1;
		const W = 400,
			H = 60,
			PAD = 6;
		const toX = (i: number) => PAD + (i / Math.max(1, pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / range) * (H - PAD * 2);
		const poly = pts.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
		const final = pts[pts.length - 1];
		return { poly, W, H, PAD, mn, mx: final, positive: final > 0, total: sorted.length };
	});

	const runProfitFactorByTimeframe = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const r of data.runs) {
			if (
				!r.timeframe ||
				r.profit_factor == null ||
				!isFinite(r.profit_factor) ||
				r.profit_factor < 0 ||
				r.profit_factor > 50
			)
				continue;
			if (!map.has(r.timeframe)) map.set(r.timeframe, []);
			map.get(r.timeframe)!.push(r.profit_factor);
		}
		const TF_ORDER = [
			'1m',
			'3m',
			'5m',
			'15m',
			'30m',
			'1h',
			'2h',
			'4h',
			'6h',
			'8h',
			'12h',
			'1d',
			'3d',
			'1w'
		];
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 3)
			.map(([tf, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const med = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
				return { tf, med, count: vals.length };
			})
			.sort((a, b) => TF_ORDER.indexOf(a.tf) - TF_ORDER.indexOf(b.tf) || b.med - a.med);
		if (rows.length < 2) return null;
		const maxMed = Math.max(1, ...rows.map((r) => r.med));
		return rows.map((r) => ({ ...r, barPct: (r.med / maxMed) * 100, good: r.med >= 1.2 }));
	});

	const runWinRateByTimeframe = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const r of data.runs) {
			if (
				!r.timeframe ||
				r.win_rate_pct == null ||
				!isFinite(r.win_rate_pct) ||
				r.win_rate_pct < 0 ||
				r.win_rate_pct > 100
			)
				continue;
			if (!map.has(r.timeframe)) map.set(r.timeframe, []);
			map.get(r.timeframe)!.push(r.win_rate_pct);
		}
		const TF_ORDER = [
			'1m',
			'3m',
			'5m',
			'15m',
			'30m',
			'1h',
			'2h',
			'4h',
			'6h',
			'8h',
			'12h',
			'1d',
			'3d',
			'1w'
		];
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 3)
			.map(([tf, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const med = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
				return { tf, med, count: vals.length };
			})
			.sort((a, b) => TF_ORDER.indexOf(a.tf) - TF_ORDER.indexOf(b.tf) || b.med - a.med);
		if (rows.length < 2) return null;
		const maxMed = Math.max(1, ...rows.map((r) => r.med));
		return rows.map((r) => ({ ...r, barPct: (r.med / maxMed) * 100, good: r.med >= 50 }));
	});

	const runTradeCountByTimeframe = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const r of data.runs) {
			if (!r.timeframe || r.total_trades == null || !isFinite(r.total_trades) || r.total_trades < 1)
				continue;
			if (!map.has(r.timeframe)) map.set(r.timeframe, []);
			map.get(r.timeframe)!.push(r.total_trades);
		}
		const TF_ORDER = [
			'1m',
			'3m',
			'5m',
			'15m',
			'30m',
			'1h',
			'2h',
			'4h',
			'6h',
			'8h',
			'12h',
			'1d',
			'3d',
			'1w'
		];
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 3)
			.map(([tf, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const med = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
				return { tf, med, count: vals.length };
			})
			.sort((a, b) => TF_ORDER.indexOf(a.tf) - TF_ORDER.indexOf(b.tf) || b.med - a.med);
		if (rows.length < 2) return null;
		const maxMed = Math.max(1, ...rows.map((r) => r.med));
		return rows.map((r) => ({ ...r, barPct: (r.med / maxMed) * 100 }));
	});

	const runStrategyTimeframeHeatmap = $derived.by(() => {
		const map = new Map<string, Map<string, number[]>>();
		for (const r of data.runs) {
			if (
				!r.strategy ||
				!r.timeframe ||
				r.total_profit_pct == null ||
				!isFinite(r.total_profit_pct)
			)
				continue;
			if (!map.has(r.strategy)) map.set(r.strategy, new Map());
			const tm = map.get(r.strategy)!;
			if (!tm.has(r.timeframe)) tm.set(r.timeframe, []);
			tm.get(r.timeframe)!.push(r.total_profit_pct);
		}
		const TF_ORDER = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d'];
		const timeframes = [...new Set(data.runs.map((r) => r.timeframe).filter(Boolean))] as string[];
		const sortedTf = timeframes.sort((a, b) => {
			const ai = TF_ORDER.indexOf(a),
				bi = TF_ORDER.indexOf(b);
			return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
		});
		const strategies = [...map.entries()]
			.filter(([, tm]) => [...tm.values()].some((v) => v.length >= 2))
			.map(([s]) => s)
			.slice(0, 10);
		if (strategies.length < 2 || sortedTf.length < 2) return null;
		const median = (vals: number[]) => {
			const s = [...vals].sort((a, b) => a - b);
			const m = Math.floor(s.length / 2);
			return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
		};
		const allMeds = strategies
			.flatMap((s) =>
				sortedTf.map((tf) => {
					const vals = map.get(s)?.get(tf);
					return vals && vals.length >= 2 ? median(vals) : null;
				})
			)
			.filter((v): v is number => v !== null);
		if (allMeds.length < 4) return null;
		const absMax = Math.max(0.01, ...allMeds.map(Math.abs));
		const cells = strategies.map((s) => ({
			strategy: s,
			tfs: sortedTf.map((tf) => {
				const vals = map.get(s)?.get(tf);
				if (!vals || vals.length < 2) return { tf, med: null, n: 0 };
				const med = median(vals);
				const intensity = Math.min(1, Math.abs(med) / absMax);
				return { tf, med, n: vals.length, intensity, positive: med >= 0 };
			})
		}));
		return { cells, timeframes: sortedTf };
	});

	const runCalmarByStrategy = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const r of data.runs) {
			if (
				!r.strategy ||
				r.calmar == null ||
				!isFinite(r.calmar) ||
				r.calmar < -10 ||
				r.calmar > 100
			)
				continue;
			if (!map.has(r.strategy)) map.set(r.strategy, []);
			map.get(r.strategy)!.push(r.calmar);
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 3)
			.map(([strategy, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const med = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
				return { strategy, calmar: med, count: vals.length };
			})
			.sort((a, b) => b.calmar - a.calmar)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const absMax = Math.max(0.01, ...rows.map((r) => Math.abs(r.calmar)));
		return rows.map((r) => ({
			...r,
			barPct: (Math.abs(r.calmar) / absMax) * 100,
			positive: r.calmar > 0
		}));
	});

	const runSortinoByStrategy = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const r of data.runs) {
			if (
				!r.strategy ||
				r.sortino == null ||
				!isFinite(r.sortino) ||
				r.sortino < -10 ||
				r.sortino > 200
			)
				continue;
			if (!map.has(r.strategy)) map.set(r.strategy, []);
			map.get(r.strategy)!.push(r.sortino);
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 3)
			.map(([strategy, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const med = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
				return { strategy, sortino: med, count: vals.length };
			})
			.sort((a, b) => b.sortino - a.sortino)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const absMax = Math.max(0.01, ...rows.map((r) => Math.abs(r.sortino)));
		return rows.map((r) => ({
			...r,
			barPct: (Math.abs(r.sortino) / absMax) * 100,
			positive: r.sortino > 0
		}));
	});

	// Median profit_factor per strategy (distinct from calmar/sortino leaderboards)
	const runProfitFactorByStrategy = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const r of data.runs) {
			if (
				!r.strategy ||
				r.profit_factor == null ||
				!isFinite(r.profit_factor) ||
				r.profit_factor <= 0 ||
				r.profit_factor > 100
			)
				continue;
			if (!map.has(r.strategy)) map.set(r.strategy, []);
			map.get(r.strategy)!.push(r.profit_factor);
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 3)
			.map(([strategy, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const med = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
				return { strategy, pf: med, count: vals.length };
			})
			.sort((a, b) => b.pf - a.pf)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxPf = Math.max(0.01, ...rows.map((r) => r.pf));
		return rows.map((r) => ({ ...r, barPct: (r.pf / maxPf) * 100, good: r.pf >= 1.5 }));
	});

	// Median sharpe per strategy (distinct from calmar/sortino/profitfactor leaderboards)
	const runSharpeByStrategy = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const r of data.runs) {
			if (
				!r.strategy ||
				r.sharpe == null ||
				!isFinite(r.sharpe) ||
				r.sharpe < -10 ||
				r.sharpe > 100
			)
				continue;
			if (!map.has(r.strategy)) map.set(r.strategy, []);
			map.get(r.strategy)!.push(r.sharpe);
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 3)
			.map(([strategy, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const med = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
				return { strategy, sharpe: med, count: vals.length };
			})
			.sort((a, b) => b.sharpe - a.sharpe)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.sharpe)));
		return rows.map((r) => ({
			...r,
			barPct: (Math.abs(r.sharpe) / maxAbs) * 100,
			positive: r.sharpe > 0
		}));
	});

	const runNetProfitByStrategy = $derived.by(() => {
		const valid = data.runs.filter(
			(r) => r.strategy && r.total_profit_pct != null && isFinite(r.total_profit_pct)
		);
		if (valid.length < 4) return null;
		const map = new Map<string, { sum: number; count: number; wins: number }>();
		for (const r of valid) {
			if (!map.has(r.strategy)) map.set(r.strategy, { sum: 0, count: 0, wins: 0 });
			const e = map.get(r.strategy)!;
			e.sum += r.total_profit_pct!;
			e.count++;
			if (r.total_profit_pct! > 0) e.wins++;
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.count >= 2)
			.map(([strategy, v]) => ({ strategy, sum: v.sum, count: v.count, winRate: v.wins / v.count }))
			.sort((a, b) => b.sum - a.sum)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.sum)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.sum) / maxAbs) * 100 }));
	});

	const runCalmarDistribution = $derived.by(() => {
		const vals = data.runs
			.filter((r) => r.calmar != null && isFinite(r.calmar) && r.calmar > -50 && r.calmar < 200)
			.map((r) => r.calmar!);
		if (vals.length < 5) return null;
		const mn = Math.min(...vals),
			mx = Math.max(...vals);
		const range = mx - mn || 1;
		const BINS = 10;
		const step = range / BINS;
		const buckets = Array.from({ length: BINS }, (_, i) => ({
			lo: mn + i * step,
			hi: mn + (i + 1) * step,
			count: 0,
			label: (mn + i * step).toFixed(1)
		}));
		for (const v of vals) {
			const idx = Math.min(BINS - 1, Math.floor((v - mn) / step));
			buckets[idx].count++;
		}
		const maxCount = Math.max(1, ...buckets.map((b) => b.count));
		const sorted = [...vals].sort((a, b) => a - b);
		const median = sorted[Math.floor(sorted.length / 2)];
		const positive = vals.filter((v) => v > 0).length;
		return { buckets, maxCount, median, positive, total: vals.length, step };
	});

	const runProfitPerTradeByStrategy = $derived.by(() => {
		const valid = data.runs.filter(
			(r) =>
				r.strategy &&
				r.total_profit_pct != null &&
				isFinite(r.total_profit_pct) &&
				r.total_trades != null &&
				r.total_trades > 0
		);
		if (valid.length < 4) return null;
		const map = new Map<string, { effSum: number; count: number }>();
		for (const r of valid) {
			const eff = r.total_profit_pct! / r.total_trades!;
			if (!isFinite(eff)) continue;
			if (!map.has(r.strategy)) map.set(r.strategy, { effSum: 0, count: 0 });
			const e = map.get(r.strategy)!;
			e.effSum += eff;
			e.count++;
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.count >= 2)
			.map(([strategy, v]) => ({ strategy, avg: v.effSum / v.count, count: v.count }))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.avg)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.avg) / maxAbs) * 100 }));
	});

	const runSharpeVsWinRate = $derived.by(() => {
		const pts = runs
			.filter(
				(r) =>
					r.sharpe != null &&
					isFinite(r.sharpe) &&
					r.sharpe > -20 &&
					r.sharpe < 50 &&
					r.win_rate_pct != null &&
					isFinite(r.win_rate_pct) &&
					r.win_rate_pct >= 0 &&
					r.win_rate_pct <= 100
			)
			.map((r) => ({ sharpe: r.sharpe!, wr: r.win_rate_pct!, tf: r.timeframe ?? '' }));
		if (pts.length < 6) return null;
		const sMin = Math.min(...pts.map((p) => p.sharpe));
		const sMax = Math.max(...pts.map((p) => p.sharpe), sMin + 0.01);
		const wMin = Math.min(...pts.map((p) => p.wr));
		const wMax = Math.max(...pts.map((p) => p.wr), wMin + 1);
		const W = 560,
			H = 130,
			PAD = 10;
		const TF_COL: Record<string, string> = {
			'5m': 'var(--ch-violet)',
			'15m': 'var(--ch-profit)',
			'1h': 'var(--ch-warn)',
			'4h': 'var(--ch-loss)',
			'1d': 'var(--ch-teal)'
		};
		const toX = (w: number) => PAD + ((w - wMin) / (wMax - wMin)) * (W - PAD * 2);
		const toY = (s: number) => H - PAD - ((s - sMin) / (sMax - sMin)) * (H - PAD * 2);
		const zeroY = sMin < 0 && sMax > 0 ? toY(0) : null;
		const dots = pts.map((p) => ({
			cx: toX(p.wr),
			cy: toY(p.sharpe),
			color: TF_COL[p.tf] ?? 'var(--ch-axis-muted)'
		}));
		const positive = pts.filter((p) => p.sharpe > 0).length;
		return {
			W,
			H,
			dots,
			zeroY,
			wMin: wMin.toFixed(0),
			wMax: wMax.toFixed(0),
			sMin: sMin.toFixed(2),
			sMax: sMax.toFixed(2),
			total: pts.length,
			positive
		};
	});

	const runProfitCvByStrategy = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const r of runs) {
			if (r.total_profit_pct == null || !isFinite(r.total_profit_pct) || !r.strategy) continue;
			if (!map[r.strategy]) map[r.strategy] = [];
			map[r.strategy].push(r.total_profit_pct);
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.length >= 4)
			.map(([strategy, vals]) => {
				const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
				const variance = vals.reduce((s, v) => s + (v - mean) ** 2, 0) / vals.length;
				const std = Math.sqrt(variance);
				const cv = mean !== 0 ? Math.abs(std / mean) : Infinity;
				return { strategy, cv, mean, std, count: vals.length };
			})
			.filter((r) => isFinite(r.cv))
			.sort((a, b) => a.cv - b.cv)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxCv = Math.max(...rows.map((r) => r.cv), 0.01);
		return { rows, maxCv };
	});

	const runProfitVsTradeCount = $derived.by(() => {
		const pts = runs
			.filter(
				(r) =>
					r.total_profit_pct != null &&
					isFinite(r.total_profit_pct) &&
					r.total_trades != null &&
					r.total_trades > 0
			)
			.map((r) => ({
				profit: r.total_profit_pct!,
				trades: r.total_trades!,
				tf: r.timeframe ?? ''
			}));
		if (pts.length < 6) return null;
		const pMin = Math.min(...pts.map((p) => p.profit)),
			pMax = Math.max(...pts.map((p) => p.profit), pMin + 0.01);
		const tMin = Math.min(...pts.map((p) => p.trades)),
			tMax = Math.max(...pts.map((p) => p.trades), tMin + 1);
		const W = 560,
			H = 130,
			PAD = 10;
		const TF_COL: Record<string, string> = {
			'5m': 'var(--ch-violet)',
			'15m': 'var(--ch-profit)',
			'1h': 'var(--ch-warn)',
			'4h': 'var(--ch-loss)',
			'1d': 'var(--ch-teal)'
		};
		const toX = (t: number) => PAD + ((t - tMin) / (tMax - tMin)) * (W - PAD * 2);
		const toY = (p: number) => H - PAD - ((p - pMin) / (pMax - pMin)) * (H - PAD * 2);
		const zeroY = pMin < 0 && pMax > 0 ? toY(0) : null;
		const dots = pts.map((p) => ({
			cx: toX(p.trades),
			cy: toY(p.profit),
			color: TF_COL[p.tf] ?? 'var(--ch-axis-muted)'
		}));
		const positive = pts.filter((p) => p.profit > 0).length;
		return {
			W,
			H,
			dots,
			zeroY,
			tMin,
			tMax,
			pMin: pMin.toFixed(1),
			pMax: pMax.toFixed(1),
			total: pts.length,
			positive
		};
	});

	const runDrawdownVsSortino = $derived.by(() => {
		const pts = runs
			.filter(
				(r) =>
					r.max_drawdown_pct != null &&
					isFinite(r.max_drawdown_pct) &&
					r.sortino != null &&
					isFinite(r.sortino) &&
					Math.abs(r.sortino) < 100
			)
			.map((r) => ({ dd: r.max_drawdown_pct!, sortino: r.sortino!, tf: r.timeframe ?? '' }));
		if (pts.length < 6) return null;
		const dMin = Math.min(...pts.map((p) => p.dd)),
			dMax = Math.max(...pts.map((p) => p.dd), dMin + 0.01);
		const sMin = Math.min(...pts.map((p) => p.sortino)),
			sMax = Math.max(...pts.map((p) => p.sortino), sMin + 0.01);
		const W = 560,
			H = 130,
			PAD = 10;
		const TF_COL: Record<string, string> = {
			'5m': 'var(--ch-violet)',
			'15m': 'var(--ch-profit)',
			'1h': 'var(--ch-warn)',
			'4h': 'var(--ch-loss)',
			'1d': 'var(--ch-teal)'
		};
		const toX = (d: number) => PAD + ((d - dMin) / (dMax - dMin)) * (W - PAD * 2);
		const toY = (s: number) => H - PAD - ((s - sMin) / (sMax - sMin)) * (H - PAD * 2);
		const zeroY = sMin < 0 && sMax > 0 ? toY(0) : null;
		const dots = pts.map((p) => ({
			cx: toX(p.dd),
			cy: toY(p.sortino),
			color: TF_COL[p.tf] ?? 'var(--ch-axis-muted)'
		}));
		const elite = pts.filter(
			(p) => p.dd < dMin + (dMax - dMin) * 0.33 && p.sortino > sMin + (sMax - sMin) * 0.67
		).length;
		return {
			W,
			H,
			dots,
			zeroY,
			dMin: dMin.toFixed(1),
			dMax: dMax.toFixed(1),
			sMin: sMin.toFixed(2),
			sMax: sMax.toFixed(2),
			total: pts.length,
			elite
		};
	});

	const runWinRateByStrategy = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const r of runs) {
			if (!r.strategy || r.win_rate_pct == null || !isFinite(r.win_rate_pct)) continue;
			if (!map[r.strategy]) map[r.strategy] = [];
			map[r.strategy].push(r.win_rate_pct);
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.length >= 1)
			.map(([strategy, vals]) => ({
				strategy,
				avg: vals.reduce((a, b) => a + b, 0) / vals.length,
				best: Math.max(...vals),
				count: vals.length
			}))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxAvg = Math.max(...rows.map((r) => r.avg), 1);
		return { rows, maxAvg };
	});

	const runProfitSkewByTimeframe = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const r of runs) {
			if (!r.timeframe || r.total_profit_pct == null || !isFinite(r.total_profit_pct)) continue;
			if (!map[r.timeframe]) map[r.timeframe] = [];
			map[r.timeframe].push(r.total_profit_pct);
		}
		const TF_ORDER = [
			'1m',
			'3m',
			'5m',
			'15m',
			'30m',
			'1h',
			'2h',
			'4h',
			'6h',
			'8h',
			'12h',
			'1d',
			'3d',
			'1w'
		];
		const rows = Object.entries(map)
			.filter(([, v]) => v.length >= 5)
			.map(([tf, vals]) => {
				const n = vals.length;
				const mean = vals.reduce((a, b) => a + b, 0) / n;
				const std = Math.sqrt(vals.reduce((s, v) => s + (v - mean) ** 2, 0) / n);
				const skew = std > 0 ? vals.reduce((s, v) => s + ((v - mean) / std) ** 3, 0) / n : 0;
				return { tf, skew, count: n };
			})
			.filter((r) => isFinite(r.skew))
			.sort((a, b) => {
				const ai = TF_ORDER.indexOf(a.tf),
					bi = TF_ORDER.indexOf(b.tf);
				return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
			});
		if (rows.length < 2) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.skew)), 0.01);
		return { rows, maxAbs };
	});

	const runTopProfitByPairs = $derived.by(() => {
		const map: Record<string, { profits: number[]; strategy: string }> = {};
		for (const r of runs) {
			if (
				!r.pairs ||
				!Array.isArray(r.pairs) ||
				r.total_profit_pct == null ||
				!isFinite(r.total_profit_pct)
			)
				continue;
			for (const pair of r.pairs as string[]) {
				if (!map[pair]) map[pair] = { profits: [], strategy: r.strategy ?? '' };
				map[pair].profits.push(r.total_profit_pct);
			}
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.profits.length >= 3)
			.map(([pair, v]) => {
				const avg = v.profits.reduce((a, b) => a + b, 0) / v.profits.length;
				const best = Math.max(...v.profits);
				return { pair, avg, best, count: v.profits.length };
			})
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxAvg = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		return { rows, maxAvg };
	});

	const runSortinoRanking = $derived.by(() => {
		const map: Record<string, number> = {};
		for (const r of runs) {
			if (!r.strategy || r.sortino == null || !isFinite(r.sortino) || Math.abs(r.sortino) > 500)
				continue;
			if (map[r.strategy] == null || r.sortino > map[r.strategy]) map[r.strategy] = r.sortino;
		}
		const rows = Object.entries(map)
			.map(([strategy, sortino]) => ({ strategy, sortino }))
			.sort((a, b) => b.sortino - a.sortino)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.sortino)), 0.01);
		return { rows, maxAbs };
	});

	const runProfitVsDrawdownScatter = $derived.by(() => {
		const pts = runs
			.filter(
				(r) =>
					r.total_profit_pct != null &&
					isFinite(r.total_profit_pct) &&
					r.max_drawdown_pct != null &&
					isFinite(r.max_drawdown_pct) &&
					r.max_drawdown_pct >= 0
			)
			.map((r) => ({
				profit: r.total_profit_pct!,
				dd: r.max_drawdown_pct!,
				tf: r.timeframe ?? '',
				strategy: r.strategy ?? ''
			}));
		if (pts.length < 8) return null;
		const pMin = Math.min(...pts.map((p) => p.profit)),
			pMax = Math.max(...pts.map((p) => p.profit), pMin + 0.01);
		const dMax = Math.max(...pts.map((p) => p.dd), 0.01);
		const W = 560,
			H = 140,
			PAD = 12;
		const TF_COL: Record<string, string> = {
			'5m': 'var(--ch-violet)',
			'15m': 'var(--ch-profit)',
			'1h': 'var(--ch-warn)',
			'4h': 'var(--ch-loss)',
			'1d': 'var(--ch-teal)'
		};
		const toX = (d: number) => PAD + (d / dMax) * (W - PAD * 2);
		const toY = (p: number) => H - PAD - ((p - pMin) / (pMax - pMin)) * (H - PAD * 2);
		const zeroY = pMin < 0 && pMax > 0 ? toY(0) : null;
		const dots = pts.map((p) => ({
			cx: toX(p.dd),
			cy: toY(p.profit),
			color: TF_COL[p.tf] ?? 'var(--ch-axis-muted)'
		}));
		const ideal = pts.filter((p) => p.profit > 0 && p.dd < 20).length;
		return {
			W,
			H,
			dots,
			zeroY,
			dMax: dMax.toFixed(1),
			pMin: pMin.toFixed(1),
			pMax: pMax.toFixed(1),
			total: pts.length,
			ideal
		};
	});

	const runAvgTradeCountByTF = $derived.by(() => {
		const map: Record<string, { trades: number[]; profits: number[] }> = {};
		for (const r of data.runs) {
			if (!r.timeframe || r.total_trades == null) continue;
			if (!map[r.timeframe]) map[r.timeframe] = { trades: [], profits: [] };
			map[r.timeframe].trades.push(r.total_trades);
			if (r.total_profit_pct != null && isFinite(r.total_profit_pct))
				map[r.timeframe].profits.push(r.total_profit_pct);
		}
		const TF_ORDER = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d'];
		const rows = Object.entries(map)
			.map(([tf, v]) => {
				const avgTrades = v.trades.reduce((a, b) => a + b, 0) / v.trades.length;
				const avgProfit =
					v.profits.length > 0 ? v.profits.reduce((a, b) => a + b, 0) / v.profits.length : 0;
				return { tf, avgTrades, avgProfit, count: v.trades.length };
			})
			.sort(
				(a, b) =>
					(TF_ORDER.indexOf(a.tf) === -1 ? 99 : TF_ORDER.indexOf(a.tf)) -
					(TF_ORDER.indexOf(b.tf) === -1 ? 99 : TF_ORDER.indexOf(b.tf))
			);
		if (rows.length < 2) return null;
		const maxTrades = Math.max(...rows.map((r) => r.avgTrades), 1);
		const W = 480,
			H = 80,
			PAD = 8,
			barW = Math.min(50, Math.floor((W - PAD * 2) / rows.length) - 3);
		return { rows, maxTrades, W, H, PAD, barW };
	});

	const runHoldingTimeVsProfit = $derived.by(() => {
		const pts = runs
			.filter(
				(r) =>
					r.holding_avg_hours != null &&
					isFinite(r.holding_avg_hours!) &&
					r.total_profit_pct != null &&
					isFinite(r.total_profit_pct!)
			)
			.map((r) => ({
				hold: r.holding_avg_hours!,
				profit: r.total_profit_pct!,
				tf: r.timeframe ?? ''
			}));
		if (pts.length < 6) return null;
		const W = 520,
			H = 100,
			PAD = 10;
		const mnH = Math.min(...pts.map((p) => p.hold)),
			mxH = Math.max(...pts.map((p) => p.hold), mnH + 0.01);
		const mnP = Math.min(...pts.map((p) => p.profit)),
			mxP = Math.max(...pts.map((p) => p.profit), mnP + 0.01);
		const TF_COLORS: Record<string, string> = {
			'15m': 'var(--ch-violet-light)',
			'1h': 'var(--ch-profit-light)',
			'4h': 'var(--ch-warn-light)',
			'1d': 'var(--ch-loss-light)'
		};
		const toX = (v: number) => PAD + ((v - mnH) / (mxH - mnH)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mnP) / (mxP - mnP)) * (H - PAD * 2);
		const dots = pts.map((p) => ({
			cx: toX(p.hold),
			cy: toY(p.profit),
			color: TF_COLORS[p.tf] ?? 'var(--ch-axis-muted)'
		}));
		const zeroY = mnP <= 0 && mxP >= 0 ? toY(0) : null;
		return { W, H, dots, zeroY, count: pts.length };
	});

	const runProfitFactorLeaderboard = $derived.by(() => {
		const best: Record<string, { pf: number; tf: string }> = {};
		for (const r of data.runs) {
			if (
				!r.strategy ||
				r.profit_factor == null ||
				!isFinite(r.profit_factor) ||
				r.profit_factor <= 0 ||
				r.profit_factor > 20
			)
				continue;
			if (!best[r.strategy] || r.profit_factor > best[r.strategy].pf)
				best[r.strategy] = { pf: r.profit_factor, tf: r.timeframe ?? '' };
		}
		const rows = Object.entries(best)
			.map(([strategy, v]) => ({ strategy: strategy.slice(0, 22), pf: v.pf, tf: v.tf }))
			.sort((a, b) => b.pf - a.pf)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxPF = Math.max(...rows.map((r) => r.pf), 0.01);
		return { rows, maxPF };
	});

	const runSortinoLeaderboard = $derived.by(() => {
		const best: Record<string, { sortino: number; tf: string }> = {};
		for (const r of runs) {
			if (!r.strategy || r.sortino == null || !isFinite(r.sortino) || r.sortino <= 0) continue;
			if (!best[r.strategy] || r.sortino > best[r.strategy].sortino)
				best[r.strategy] = { sortino: r.sortino, tf: r.timeframe ?? '' };
		}
		const rows = Object.entries(best)
			.map(([strategy, v]) => ({ strategy: strategy.slice(0, 22), sortino: v.sortino, tf: v.tf }))
			.sort((a, b) => b.sortino - a.sortino)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxSortino = Math.max(...rows.map((r) => r.sortino), 0.01);
		return { rows, maxSortino };
	});

	const runWinRateHistogram = $derived.by(() => {
		const vals = runs
			.filter((r) => r.win_rate_pct != null && isFinite(r.win_rate_pct))
			.map((r) => r.win_rate_pct!);
		if (vals.length < 5) return null;
		const bins = 12,
			mn = Math.min(...vals),
			mx = Math.max(...vals);
		const step = (mx - mn) / bins || 1;
		const counts = Array.from({ length: bins }, (_, i) => {
			const lo = mn + i * step,
				hi = lo + step;
			return {
				lo,
				count: vals.filter((v) => v >= lo && (i === bins - 1 ? v <= hi : v < hi)).length
			};
		});
		const maxCount = Math.max(...counts.map((c) => c.count), 1);
		const W = 380,
			H = 75,
			PAD = 8,
			barW = Math.floor((W - PAD * 2) / bins) - 1;
		const avg = (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1);
		return {
			counts,
			maxCount,
			W,
			H,
			PAD,
			barW,
			mn: mn.toFixed(1),
			mx: mx.toFixed(1),
			avg,
			total: vals.length
		};
	});

	const runProfitDistribution = $derived.by(() => {
		const vals = runs
			.filter((r) => r.total_profit_pct != null && isFinite(r.total_profit_pct))
			.map((r) => r.total_profit_pct!);
		if (vals.length < 5) return null;
		const mn = Math.min(...vals),
			mx = Math.max(...vals);
		const bins = 14,
			step = (mx - mn) / bins || 1;
		const counts = Array.from({ length: bins }, (_, i) => {
			const lo = mn + i * step,
				hi = lo + step;
			return {
				lo,
				count: vals.filter((v) => v >= lo && (i === bins - 1 ? v <= hi : v < hi)).length
			};
		});
		const maxCount = Math.max(...counts.map((c) => c.count), 1);
		const W = 400,
			H = 75,
			PAD = 8,
			barW = Math.floor((W - PAD * 2) / bins) - 1;
		const avg = (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1);
		return {
			counts,
			maxCount,
			W,
			H,
			PAD,
			barW,
			mn: mn.toFixed(1),
			mx: mx.toFixed(1),
			avg,
			total: vals.length
		};
	});

	const runMaxDrawdownByStrategy = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const r of runs) {
			if (!r.strategy || r.max_drawdown_pct == null || !isFinite(r.max_drawdown_pct)) continue;
			if (!map[r.strategy]) map[r.strategy] = [];
			map[r.strategy].push(Math.abs(r.max_drawdown_pct));
		}
		const rows = Object.entries(map)
			.filter(([, vals]) => vals.length >= 2)
			.map(([strategy, vals]) => ({
				strategy: strategy.slice(0, 22),
				avg: vals.reduce((a, b) => a + b, 0) / vals.length,
				count: vals.length
			}))
			.sort((a, b) => a.avg - b.avg)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxDD = Math.max(...rows.map((r) => r.avg), 0.01);
		const W = 400,
			H = rows.length * 16 + 16,
			PAD = 8,
			barMaxW = W - PAD * 2 - 80;
		return { rows, maxDD, W, H, PAD, barMaxW };
	});

	const runTimeframePassRate = $derived.by(() => {
		const map: Record<string, { pass: number; total: number }> = {};
		for (const r of runs) {
			if (!r.timeframe) continue;
			if (!map[r.timeframe]) map[r.timeframe] = { pass: 0, total: 0 };
			map[r.timeframe].total++;
			if (r.total_profit_pct != null && r.total_profit_pct > 0) map[r.timeframe].pass++;
		}
		const TF_ORDER = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d'];
		const rows = Object.entries(map)
			.filter(([, v]) => v.total >= 3)
			.map(([tf, v]) => ({ tf, rate: (v.pass / v.total) * 100, pass: v.pass, total: v.total }))
			.sort(
				(a, b) =>
					(TF_ORDER.indexOf(a.tf) === -1 ? 99 : TF_ORDER.indexOf(a.tf)) -
					(TF_ORDER.indexOf(b.tf) === -1 ? 99 : TF_ORDER.indexOf(b.tf))
			);
		if (rows.length < 2) return null;
		const W = 400,
			H = 75,
			PAD = 8,
			barW = Math.max(18, Math.floor((W - PAD * 2) / rows.length) - 3);
		return { rows, W, H, PAD, barW };
	});

	const runCalmarLeaderboard = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.strategy || r.calmar == null || !isFinite(r.calmar) || r.calmar > 200) continue;
			if (!map.has(r.strategy)) map.set(r.strategy, []);
			map.get(r.strategy)!.push(r.calmar);
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 3)
			.map(([strategy, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const med = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
				return { strategy: strategy.slice(0, 20), calmar: med, count: vals.length };
			})
			.sort((a, b) => b.calmar - a.calmar)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxCalmar = Math.max(...rows.map((r) => r.calmar), 0.01);
		return { rows, maxCalmar };
	});

	const runStrategyWinLossProfile = $derived.by(() => {
		const map = new Map<string, { wins: number; losses: number; totalProfit: number }>();
		for (const r of runs) {
			if (!r.strategy || r.total_profit_pct == null || !isFinite(r.total_profit_pct)) continue;
			if (!map.has(r.strategy)) map.set(r.strategy, { wins: 0, losses: 0, totalProfit: 0 });
			const e = map.get(r.strategy)!;
			if (r.total_profit_pct >= 0) e.wins++;
			else e.losses++;
			e.totalProfit += r.total_profit_pct;
		}
		const rows = [...map.entries()]
			.filter(([, e]) => e.wins + e.losses >= 4)
			.map(([strategy, e]) => {
				const total = e.wins + e.losses;
				return {
					strategy: strategy.slice(0, 20),
					wins: e.wins,
					losses: e.losses,
					total,
					wr: (e.wins / total) * 100,
					avgProfit: e.totalProfit / total
				};
			})
			.sort((a, b) => b.wr - a.wr)
			.slice(0, 12);
		if (rows.length < 3) return null;
		return { rows };
	});

	const runSortinoVsCalmarScatter = $derived.by(() => {
		const pts = runs
			.filter(
				(r) =>
					r.sortino != null &&
					isFinite(r.sortino) &&
					r.sortino < 100 &&
					r.calmar != null &&
					isFinite(r.calmar) &&
					r.calmar < 100
			)
			.map((r) => ({ sortino: r.sortino!, calmar: r.calmar!, profit: r.total_profit_pct ?? 0 }));
		if (pts.length < 5) return null;
		const sMin = Math.min(...pts.map((p) => p.sortino)),
			sMax = Math.max(...pts.map((p) => p.sortino), sMin + 0.1);
		const cMin = Math.min(...pts.map((p) => p.calmar)),
			cMax = Math.max(...pts.map((p) => p.calmar), cMin + 0.1);
		const W = 380,
			H = 95,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - sMin) / (sMax - sMin)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - cMin) / (cMax - cMin)) * (H - PAD * 2);
		const dots = pts.map((p) => ({
			cx: toX(p.sortino),
			cy: toY(p.calmar),
			color: p.profit >= 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)'
		}));
		return {
			dots,
			W,
			H,
			PAD,
			sMin: sMin.toFixed(1),
			sMax: sMax.toFixed(1),
			cMin: cMin.toFixed(1),
			cMax: cMax.toFixed(1),
			count: pts.length
		};
	});

	const runProfitMonthlyHeatmap = $derived.by(() => {
		const stratTotals = new Map<string, number>();
		for (const r of runs) {
			if (!r.strategy || r.total_profit_pct == null) continue;
			stratTotals.set(r.strategy, (stratTotals.get(r.strategy) ?? 0) + 1);
		}
		const topStrats = [...stratTotals.entries()]
			.sort((a, b) => b[1] - a[1])
			.slice(0, 5)
			.map(([s]) => s);
		if (topStrats.length < 2) return null;
		const monthMap = new Map<string, Map<string, number[]>>();
		for (const r of runs) {
			if (
				!r.strategy ||
				!topStrats.includes(r.strategy) ||
				!r.imported_at ||
				r.total_profit_pct == null ||
				!isFinite(r.total_profit_pct)
			)
				continue;
			const mo = r.imported_at.slice(0, 7);
			if (!monthMap.has(mo)) monthMap.set(mo, new Map());
			const inner = monthMap.get(mo)!;
			if (!inner.has(r.strategy)) inner.set(r.strategy, []);
			inner.get(r.strategy)!.push(r.total_profit_pct);
		}
		const months = [...monthMap.keys()].sort().slice(-6);
		if (months.length < 2) return null;
		const cells = months.flatMap((mo, mi) =>
			topStrats.map((strat, si) => {
				const vals = monthMap.get(mo)?.get(strat) ?? [];
				const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
				return { mo: mo.slice(5), strat: strat.slice(0, 12), avg, mi, si };
			})
		);
		const allAvg = cells.map((c) => c.avg).filter((v): v is number => v !== null);
		const mx = Math.max(...allAvg.map(Math.abs), 0.01);
		const cW = 42,
			cH = 18,
			PAD = 14;
		return {
			cells,
			topStrats: topStrats.map((s) => s.slice(0, 12)),
			months: months.map((m) => m.slice(5)),
			cW,
			cH,
			PAD,
			mx,
			W: PAD + months.length * (cW + 2),
			H: PAD + topStrats.length * (cH + 2)
		};
	});

	const runDurationVsProfit = $derived.by(() => {
		const pts = runs
			.filter(
				(r) =>
					r.avg_duration_minutes != null &&
					isFinite(r.avg_duration_minutes) &&
					r.avg_duration_minutes > 0 &&
					r.total_profit_pct != null &&
					isFinite(r.total_profit_pct)
			)
			.map((r) => ({
				dur: r.avg_duration_minutes! / 60,
				profit: r.total_profit_pct!,
				strat: r.strategy ?? ''
			}));
		if (pts.length < 8) return null;
		const dMin = Math.min(...pts.map((p) => p.dur)),
			dMax = Math.max(...pts.map((p) => p.dur), dMin + 0.1);
		const pMin = Math.min(...pts.map((p) => p.profit)),
			pMax = Math.max(...pts.map((p) => p.profit), pMin + 0.1);
		const W = 380,
			H = 95,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - dMin) / (dMax - dMin)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - pMin) / (pMax - pMin)) * (H - PAD * 2);
		const zeroY = Math.max(PAD, Math.min(H - PAD, toY(0)));
		const dots = pts.map((p) => ({
			cx: toX(p.dur),
			cy: toY(p.profit),
			color:
				p.profit >= 10
					? 'var(--ch-profit-light)'
					: p.profit >= 0
						? 'var(--ch-warn-light)'
						: 'var(--ch-loss-light)'
		}));
		return {
			dots,
			W,
			H,
			PAD,
			zeroY,
			dMin: dMin.toFixed(0),
			dMax: dMax.toFixed(0),
			pMin: pMin.toFixed(0),
			pMax: pMax.toFixed(0),
			count: pts.length
		};
	});

	const runSharpeLeaderboard = $derived.by(() => {
		const byStrat = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.strategy || r.sharpe == null || !isFinite(r.sharpe)) continue;
			if (!byStrat.has(r.strategy)) byStrat.set(r.strategy, []);
			byStrat.get(r.strategy)!.push(r.sharpe);
		}
		const rows = [...byStrat.entries()]
			.map(([strat, vals]) => ({
				strat: strat.slice(0, 20),
				avg: vals.reduce((a, v) => a + v, 0) / vals.length,
				count: vals.length
			}))
			.filter((r) => r.count >= 2)
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 8);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 340,
			H = rows.length * 16 + 4,
			barMaxW = W - 130;
		return { rows, maxAbs, W, H, barMaxW };
	});

	const runWinRateIQRByTimeframe = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.timeframe || r.win_rate_pct == null || !isFinite(r.win_rate_pct)) continue;
			if (!map.has(r.timeframe)) map.set(r.timeframe, []);
			map.get(r.timeframe)!.push(r.win_rate_pct);
		}
		const TF_ORDER = ['5m', '15m', '30m', '1h', '2h', '4h', '8h', '1d'];
		const rows = TF_ORDER.filter((tf) => (map.get(tf)?.length ?? 0) >= 3).map((tf) => {
			const vals = map.get(tf)!;
			const sorted = [...vals].sort((a, b) => a - b);
			const med = sorted[Math.floor(sorted.length / 2)];
			const p25 = sorted[Math.floor(sorted.length * 0.25)];
			const p75 = sorted[Math.floor(sorted.length * 0.75)];
			return { tf, med, p25, p75, count: vals.length };
		});
		if (rows.length < 2) return null;
		const W = 320,
			H = rows.length * 18 + 12,
			PAD = 40,
			barMaxW = W - PAD - 30;
		return { rows, W, H, PAD, barMaxW };
	});

	const runProfitByTradeCountBucket = $derived.by(() => {
		const valid = runs.filter(
			(r) =>
				r.total_trades != null &&
				isFinite(r.total_trades) &&
				r.total_trades > 0 &&
				r.total_profit_pct != null &&
				isFinite(r.total_profit_pct)
		);
		if (valid.length < 10) return null;
		const trades = valid.map((r) => r.total_trades!);
		const mn = Math.min(...trades),
			mx = Math.max(...trades);
		const BINS = 6,
			step = Math.max(1, (mx - mn) / BINS);
		const bins = Array.from({ length: BINS }, (_, i) => ({
			lo: Math.round(mn + i * step),
			hi: Math.round(mn + (i + 1) * step),
			profits: [] as number[]
		}));
		for (const r of valid) {
			const bi = Math.min(BINS - 1, Math.floor((r.total_trades! - mn) / step));
			bins[bi].profits.push(r.total_profit_pct!);
		}
		const rows = bins
			.filter((b) => b.profits.length >= 2)
			.map((b) => ({
				label: `${b.lo}–${b.hi}`,
				avg: b.profits.reduce((a, v) => a + v, 0) / b.profits.length,
				count: b.profits.length
			}));
		if (rows.length < 2) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 340,
			H = 72,
			PAD = 8,
			barW = Math.floor((W - PAD * 2) / rows.length) - 3,
			midY = H / 2;
		return { rows, maxAbs, W, H, PAD, barW, midY };
	});

	const runSharpeVsSortinoArchiveScatter = $derived.by(() => {
		const pts = data.runs
			.filter(
				(r) =>
					r.sharpe != null &&
					isFinite(r.sharpe) &&
					Math.abs(r.sharpe) < 40 &&
					r.sortino != null &&
					isFinite(r.sortino) &&
					Math.abs(r.sortino) < 80 &&
					r.total_profit_pct != null &&
					isFinite(r.total_profit_pct)
			)
			.map((r) => ({ sharpe: r.sharpe!, sortino: r.sortino!, profit: r.total_profit_pct! }));
		if (pts.length < 8) return null;
		const sMin = Math.min(...pts.map((p) => p.sharpe)),
			sMax = Math.max(...pts.map((p) => p.sharpe), sMin + 0.1);
		const soMin = Math.min(...pts.map((p) => p.sortino)),
			soMax = Math.max(...pts.map((p) => p.sortino), soMin + 0.1);
		const W = 360,
			H = 92,
			PAD = 12;
		const toX = (v: number) => PAD + ((v - sMin) / (sMax - sMin)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - soMin) / (soMax - soMin)) * (H - PAD * 2);
		const zeroX = Math.max(PAD, Math.min(W - PAD, toX(0)));
		const zeroY = Math.max(PAD, Math.min(H - PAD, toY(0)));
		const dots = pts.map((p) => ({
			cx: toX(p.sharpe),
			cy: toY(p.sortino),
			color:
				p.profit >= 10
					? 'var(--ch-profit-light)'
					: p.profit >= 0
						? 'var(--ch-warn-light)'
						: 'var(--ch-loss-light)'
		}));
		return {
			dots,
			W,
			H,
			PAD,
			zeroX,
			zeroY,
			sMin: sMin.toFixed(1),
			sMax: sMax.toFixed(1),
			soMin: soMin.toFixed(1),
			soMax: soMax.toFixed(1),
			count: pts.length
		};
	});

	const runMonthlyRunCount = $derived.by(() => {
		const map = new Map<string, number>();
		for (const r of data.runs) {
			if (!r.imported_at) continue;
			const mo = r.imported_at.slice(0, 7);
			map.set(mo, (map.get(mo) ?? 0) + 1);
		}
		if (map.size < 3) return null;
		const months = [...map.keys()].sort();
		const counts = months.map((m) => ({ mo: m.slice(5), count: map.get(m)! }));
		const maxC = Math.max(...counts.map((c) => c.count), 1);
		const W = 360,
			H = 72,
			PAD = 10;
		const bw = Math.max(3, (W - PAD * 2) / counts.length - 2);
		const bars = counts.map((c, i) => ({
			x: PAD + i * ((W - PAD * 2) / counts.length),
			h: Math.max(2, (c.count / maxC) * (H - PAD - 14)),
			count: c.count,
			mo: c.mo,
			color: `rgba(99,102,241,${0.25 + (c.count / maxC) * 0.6})`
		}));
		return { bars, bw, W, H, PAD, maxC, total: counts.reduce((a, c) => a + c.count, 0) };
	});

	const runTopStrategiesByAvgProfit = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const r of data.runs) {
			if (!r.strategy || r.total_profit_pct == null || !isFinite(r.total_profit_pct)) continue;
			const arr = map.get(r.strategy) ?? [];
			arr.push(r.total_profit_pct);
			map.set(r.strategy, arr);
		}
		if (map.size < 3) return null;
		const rows = [...map.entries()]
			.map(([strat, profits]) => ({
				strat: strat.slice(0, 18),
				avg: profits.reduce((a, v) => a + v, 0) / profits.length,
				count: profits.length
			}))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 8);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 340,
			H = rows.length * 16 + 6,
			PAD = 8,
			barMaxW = W - 100,
			midX = PAD + barMaxW / 2;
		const zeroX = PAD + (maxAbs / (2 * maxAbs)) * barMaxW;
		return { rows, maxAbs, W, H, PAD, barMaxW, midX, zeroX };
	});

	const runSharpeVsDrawdownScatter = $derived.by(() => {
		const pts = data.runs
			.filter(
				(r) =>
					r.sharpe != null &&
					isFinite(r.sharpe) &&
					Math.abs(r.sharpe) < 100 &&
					r.max_drawdown_pct != null &&
					isFinite(r.max_drawdown_pct) &&
					r.max_drawdown_pct >= 0
			)
			.map((r) => ({ sharpe: r.sharpe!, dd: r.max_drawdown_pct! }));
		if (pts.length < 5) return null;
		const sMin = Math.min(...pts.map((p) => p.sharpe)),
			sMax = Math.max(...pts.map((p) => p.sharpe), sMin + 0.1);
		const ddMax = Math.max(...pts.map((p) => p.dd), 0.1);
		const W = 360,
			H = 88,
			PAD = 12;
		const toX = (v: number) => PAD + ((v - sMin) / (sMax - sMin)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (v / ddMax) * (H - PAD * 2);
		const zeroX = Math.max(PAD, Math.min(W - PAD, toX(0)));
		const dots = pts.map((p) => ({
			cx: toX(p.sharpe),
			cy: toY(p.dd),
			color:
				p.sharpe >= 1
					? 'var(--ch-profit-light)'
					: p.sharpe >= 0
						? 'var(--ch-warn-light)'
						: 'var(--ch-loss-light)'
		}));
		return {
			dots,
			W,
			H,
			PAD,
			zeroX,
			sMin: sMin.toFixed(1),
			sMax: sMax.toFixed(1),
			ddMax: ddMax.toFixed(1)
		};
	});

	const runProfitFactorHistogram = $derived.by(() => {
		const vals = data.runs
			.filter(
				(r) =>
					r.profit_factor != null &&
					isFinite(r.profit_factor) &&
					r.profit_factor > 0 &&
					r.profit_factor < 20
			)
			.map((r) => r.profit_factor!);
		if (vals.length < 8) return null;
		const mx = Math.min(Math.max(...vals), 10);
		const bins = 12;
		const binSize = mx / bins;
		const buckets = Array.from({ length: bins }, (_, i) => ({ lo: i * binSize, count: 0 }));
		for (const v of vals) {
			const bi = Math.min(bins - 1, Math.floor(v / binSize));
			buckets[bi].count++;
		}
		const maxC = Math.max(...buckets.map((b) => b.count), 1);
		const W = 360,
			H = 68,
			PAD = 10;
		const bw = (W - PAD * 2) / bins - 1;
		const x1 = PAD + (1 / mx) * (W - PAD * 2);
		const bars = buckets.map((b, i) => ({
			x: PAD + i * ((W - PAD * 2) / bins),
			h: Math.max(2, (b.count / maxC) * (H - PAD - 16)),
			color: b.lo >= 1 ? 'var(--ch-profit)' : 'var(--ch-loss-light)'
		}));
		return { bars, bw, W, H, PAD, x1, mx: mx.toFixed(0), total: vals.length };
	});

	const runAvgProfitByTimeframe = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const r of data.runs) {
			if (!r.timeframe || r.total_profit_pct == null || !isFinite(r.total_profit_pct)) continue;
			const arr = map.get(r.timeframe) ?? [];
			arr.push(r.total_profit_pct);
			map.set(r.timeframe, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([tf, profits]) => ({
				tf,
				avg: profits.reduce((a, v) => a + v, 0) / profits.length,
				count: profits.length
			}))
			.sort((a, b) => b.avg - a.avg);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 300,
			H = rows.length * 18 + 8,
			PAD = 8,
			barMaxW = W - 70,
			midX = PAD + barMaxW / 2;
		const toX = (v: number) => PAD + ((v + maxAbs) / (2 * maxAbs)) * barMaxW;
		const zeroX = toX(0);
		return { rows, maxAbs, W, H, PAD, barMaxW, midX, zeroX };
	});

	const runCalmarTimeline = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const r of data.runs) {
			if (!r.imported_at || r.calmar == null || !isFinite(r.calmar) || Math.abs(r.calmar) > 100)
				continue;
			const mo = r.imported_at.slice(0, 7);
			const arr = map.get(mo) ?? [];
			arr.push(r.calmar);
			map.set(mo, arr);
		}
		if (map.size < 3) return null;
		const months = [...map.keys()].sort();
		const pts = months.map((m) => ({
			m: m.slice(5),
			avg: map.get(m)!.reduce((a, v) => a + v, 0) / map.get(m)!.length
		}));
		const minV = Math.min(...pts.map((p) => p.avg));
		const maxV = Math.max(...pts.map((p) => p.avg));
		const range = maxV - minV || 1;
		const W = 360,
			H = 64,
			PAD = 10;
		const toX = (i: number) => PAD + (i / (pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + ((maxV - v) / range) * (H - PAD * 2);
		const polyline = pts.map((p, i) => `${toX(i)},${toY(p.avg)}`).join(' ');
		const zeroY = Math.max(PAD, Math.min(H - PAD, toY(0)));
		const area =
			`${toX(0)},${zeroY} ` +
			pts.map((p, i) => `${toX(i)},${toY(p.avg)}`).join(' ') +
			` ${toX(pts.length - 1)},${zeroY}`;
		const lastAvg = pts[pts.length - 1].avg;
		const color =
			lastAvg >= 1
				? 'var(--ch-profit-strong)'
				: lastAvg >= 0
					? 'var(--ch-warn)'
					: 'var(--ch-loss-strong)';
		const fillColor = lastAvg >= 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)';
		return {
			polyline,
			area,
			W,
			H,
			PAD,
			color,
			fillColor,
			zeroY,
			minV: minV.toFixed(2),
			maxV: maxV.toFixed(2),
			firstMo: pts[0].m,
			lastMo: pts[pts.length - 1].m,
			lastAvg: lastAvg.toFixed(2)
		};
	});

	const runWinRateTFBars = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const r of data.runs) {
			if (!r.timeframe || r.win_rate_pct == null || !isFinite(r.win_rate_pct)) continue;
			const arr = map.get(r.timeframe) ?? [];
			arr.push(r.win_rate_pct);
			map.set(r.timeframe, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([tf, vals]) => ({
				tf,
				avg: vals.reduce((a, v) => a + v, 0) / vals.length,
				count: vals.length
			}))
			.sort((a, b) => b.avg - a.avg);
		const maxAvg = Math.max(...rows.map((r) => r.avg), 0.01);
		const W = 320,
			H = 72,
			PAD = 10;
		const bw = Math.max(4, Math.floor((W - PAD * 2) / rows.length) - 4);
		const bars = rows.map((r, i) => ({
			x: PAD + i * ((W - PAD * 2) / rows.length) + 2,
			h: Math.max(2, (r.avg / maxAvg) * (H - PAD * 2 - 16)),
			tf: r.tf,
			avg: r.avg,
			count: r.count,
			color: r.avg >= 60 ? 'var(--ch-profit)' : r.avg >= 50 ? 'var(--ch-warn)' : 'var(--ch-loss)'
		}));
		return { bars, bw, W, H, PAD };
	});

	const runAvgTradeCountByMonth = $derived.by(() => {
		if (!runs || runs.length < 6) return null;
		const map = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.imported_at || r.total_trades == null) continue;
			const mo = (r.imported_at as string).slice(0, 7);
			const arr = map.get(mo) ?? [];
			arr.push(r.total_trades as number);
			map.set(mo, arr);
		}
		if (map.size < 3) return null;
		const months = [...map.keys()].sort();
		const pts = months.map((m) => {
			const arr = map.get(m)!;
			return { m: m.slice(5), avg: arr.reduce((a, v) => a + v, 0) / arr.length };
		});
		const maxV = Math.max(...pts.map((p) => p.avg), 1);
		const W = 380,
			H = 68,
			PAD = 10;
		const toX = (i: number) => PAD + (i / (pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - (v / maxV) * (H - PAD * 2);
		const polyline = pts.map((p, i) => `${toX(i)},${toY(p.avg)}`).join(' ');
		const area = `${toX(0)},${H - PAD} ${polyline} ${toX(pts.length - 1)},${H - PAD}`;
		return {
			pts,
			polyline,
			area,
			W,
			H,
			PAD,
			toX,
			maxV: Math.round(maxV),
			firstMo: pts[0].m,
			lastMo: pts[pts.length - 1].m
		};
	});

	const runDrawdownHistogram = $derived.by(() => {
		if (!runs || runs.length < 8) return null;
		const vals = runs
			.filter((r) => r.max_drawdown_pct != null)
			.map((r) => r.max_drawdown_pct as number);
		if (vals.length < 6) return null;
		const maxV = Math.max(...vals);
		const bins = 14;
		const step = maxV / bins || 1;
		const buckets = Array.from({ length: bins }, (_, i) => ({
			lo: i * step,
			hi: (i + 1) * step,
			count: 0
		}));
		for (const v of vals) {
			const bi = Math.min(bins - 1, Math.floor(v / step));
			buckets[bi].count++;
		}
		const maxC = Math.max(...buckets.map((b) => b.count), 1);
		const W = 340,
			H = 70,
			PAD = 10;
		const bw = (W - PAD * 2) / bins - 1;
		return {
			buckets,
			bw,
			W,
			H,
			PAD,
			maxC,
			step: step.toFixed(1),
			maxV: maxV.toFixed(1),
			total: vals.length
		};
	});

	const runAvgProfitByTF = $derived.by(() => {
		if (!runs || runs.length < 6) return null;
		const map = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.timeframe || r.total_profit_pct == null) continue;
			const arr = map.get(r.timeframe) ?? [];
			arr.push(r.total_profit_pct as number);
			map.set(r.timeframe, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([tf, vals]) => ({
				tf,
				avg: vals.reduce((a, v) => a + v, 0) / vals.length,
				count: vals.length
			}))
			.sort((a, b) => b.avg - a.avg);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 320,
			H = 80,
			PAD = 10;
		const bw = Math.max(6, (W - PAD * 2) / rows.length - 4);
		const midY = H / 2;
		const toH = (v: number) => (Math.abs(v) / maxAbs) * (midY - PAD - 2);
		const toX = (i: number) => PAD + i * ((W - PAD * 2) / rows.length) + 2;
		return { rows, W, H, PAD, bw, midY, toH, toX, maxAbs };
	});

	const runWinRateVsDrawdown = $derived.by(() => {
		if (!runs || runs.length < 8) return null;
		const pts = runs
			.filter(
				(r) =>
					r.wins != null &&
					r.total_trades != null &&
					(r.total_trades as number) > 0 &&
					r.max_drawdown_pct != null
			)
			.map((r) => ({
				wr: ((r.wins as number) / (r.total_trades as number)) * 100,
				dd: r.max_drawdown_pct as number
			}));
		if (pts.length < 6) return null;
		const wrMax = Math.max(...pts.map((p) => p.wr), 100);
		const ddMax = Math.max(...pts.map((p) => p.dd), 0.01);
		const W = 280,
			H = 90,
			PAD = 10;
		const toX = (wr: number) => PAD + (wr / wrMax) * (W - PAD * 2);
		const toY = (dd: number) => H - PAD - (1 - dd / ddMax) * (H - PAD * 2);
		return { pts, W, H, PAD, toX, toY, wrMax: wrMax.toFixed(0), ddMax: ddMax.toFixed(1) };
	});

	const runCalmarByPairCount = $derived.by(() => {
		if (!runs || runs.length < 6) return null;
		const map = new Map<number, number[]>();
		for (const r of runs) {
			if (r.pairs == null || r.calmar == null) continue;
			const pc = r.pairs.length;
			const bucket = Math.round(pc / 5) * 5;
			const arr = map.get(bucket) ?? [];
			arr.push(r.calmar as number);
			map.set(bucket, arr);
		}
		if (map.size < 3) return null;
		const buckets = [...map.keys()].sort((a, b) => a - b);
		const rows = buckets.map((b) => {
			const arr = map.get(b)!;
			return { b, avg: arr.reduce((a, v) => a + v, 0) / arr.length };
		});
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 320,
			H = 72,
			PAD = 8;
		const barW = (W - PAD * 2) / rows.length;
		const midY = H / 2;
		return { rows, maxAbs, W, H, PAD, barW, midY };
	});

	const runSortinoTimeline = $derived.by(() => {
		if (!runs || runs.length < 6) return null;
		const map = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.imported_at || r.sortino == null) continue;
			const mo = (r.imported_at as string).slice(0, 7);
			const arr = map.get(mo) ?? [];
			arr.push(r.sortino as number);
			map.set(mo, arr);
		}
		if (map.size < 3) return null;
		const months = [...map.keys()].sort();
		const pts = months.map((m) => {
			const arr = map.get(m)!;
			return { m: m.slice(5), avg: arr.reduce((a, v) => a + v, 0) / arr.length };
		});
		const maxV = Math.max(...pts.map((p) => p.avg), 0.01);
		const minV = Math.min(...pts.map((p) => p.avg), 0);
		const range = maxV - minV || 0.01;
		const W = 340,
			H = 68,
			PAD = 10;
		const toX = (i: number) => PAD + (i / (pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + ((maxV - v) / range) * (H - PAD * 2);
		const zeroY = Math.max(PAD, Math.min(H - PAD, toY(0)));
		const polyline = pts.map((p, i) => `${toX(i)},${toY(p.avg)}`).join(' ');
		const area = `${toX(0)},${zeroY} ${polyline} ${toX(pts.length - 1)},${zeroY}`;
		const last = pts[pts.length - 1].avg;
		const color =
			last >= 1
				? 'var(--ch-profit-strong)'
				: last >= 0
					? 'var(--ch-warn)'
					: 'var(--ch-loss-strong)';
		return {
			pts,
			polyline,
			area,
			W,
			H,
			PAD,
			toX,
			zeroY,
			color,
			fillColor: last >= 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)',
			last: last.toFixed(2),
			firstMo: pts[0].m,
			lastMo: pts[pts.length - 1].m
		};
	});

	const runTradeCountScatter = $derived.by(() => {
		if (!runs || runs.length < 8) return null;
		const pts = runs
			.filter(
				(r) =>
					r.total_trades != null && r.total_profit_pct != null && (r.total_trades as number) > 0
			)
			.map((r) => ({ tc: r.total_trades as number, profit: r.total_profit_pct as number }));
		if (pts.length < 6) return null;
		const tcMax = Math.max(...pts.map((p) => p.tc), 1);
		const profMin = Math.min(...pts.map((p) => p.profit), 0);
		const profMax = Math.max(...pts.map((p) => p.profit), 0.01);
		const range = profMax - profMin || 0.01;
		const W = 300,
			H = 90,
			PAD = 10;
		const toX = (tc: number) => PAD + (tc / tcMax) * (W - PAD * 2);
		const toY = (p: number) => H - PAD - ((p - profMin) / range) * (H - PAD * 2);
		const zeroY = toY(0);
		return {
			pts,
			W,
			H,
			PAD,
			toX,
			toY,
			zeroY,
			tcMax,
			profMax: profMax.toFixed(1),
			profMin: profMin.toFixed(1)
		};
	});

	const runProfitByPairGroup = $derived.by(() => {
		if (!runs || runs.length < 6) return null;
		const pairCounts = new Map<string, number[]>();
		for (const r of runs) {
			if (r.total_trades == null || r.total_profit_pct == null) continue;
			const bucket =
				(r.total_trades as number) <= 5
					? '1-5'
					: (r.total_trades as number) <= 15
						? '6-15'
						: (r.total_trades as number) <= 30
							? '16-30'
							: '30+';
			const arr = pairCounts.get(bucket) ?? [];
			arr.push(r.total_profit_pct as number);
			pairCounts.set(bucket, arr);
		}
		if (pairCounts.size < 2) return null;
		const ORDER = ['1-5', '6-15', '16-30', '30+'];
		const rows = ORDER.filter((k) => pairCounts.has(k)).map((k) => {
			const vals = pairCounts.get(k)!;
			return { k, avg: vals.reduce((a, v) => a + v, 0) / vals.length };
		});
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 340,
			H = 64,
			PAD = 8;
		const bw = (W - PAD * 2) / rows.length - 2;
		const midY = H / 2;
		return { rows, maxAbs, W, H, PAD, bw, midY };
	});

	const runAvgSortinoByTF = $derived.by(() => {
		if (!runs || runs.length < 6) return null;
		const map = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.timeframe || r.sortino == null) continue;
			const arr = map.get(r.timeframe as string) ?? [];
			arr.push(r.sortino as number);
			map.set(r.timeframe as string, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([tf, vals]) => ({ tf, avg: vals.reduce((a, v) => a + v, 0) / vals.length }))
			.sort((a, b) => b.avg - a.avg);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 300,
			H = rows.length * 20 + 6,
			PAD = 8,
			barMaxW = W - 40;
		const zeroX = PAD + barMaxW / 2;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const runSharpeCDF = $derived.by(() => {
		if (!runs || runs.length < 15) return null;
		const vals = runs
			.filter((r) => r.sharpe != null)
			.map((r) => r.sharpe as number)
			.sort((a, b) => a - b);
		if (vals.length < 15) return null;
		const minV = vals[0],
			maxV = vals[vals.length - 1];
		const range = maxV - minV || 0.01;
		const W = 300,
			H = 80,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - minV) / range) * (W - PAD * 2);
		const toY = (i: number) => H - PAD - (i / (vals.length - 1)) * (H - PAD * 2);
		const polyline = vals.map((v, i) => `${toX(v)},${toY(i)}`).join(' ');
		const zeroX = toX(0);
		const median = vals[Math.floor(vals.length * 0.5)];
		const p80 = vals[Math.floor(vals.length * 0.8)];
		return {
			polyline,
			W,
			H,
			PAD,
			zeroX,
			minV: minV.toFixed(2),
			maxV: maxV.toFixed(2),
			median: median.toFixed(2),
			p80: p80.toFixed(2)
		};
	});

	const runMonthlyStrategyCount = $derived.by(() => {
		if (!runs || runs.length < 8) return null;
		const map = new Map<string, Set<string>>();
		for (const r of runs) {
			if (!r.imported_at || !r.strategy) continue;
			const mo = (r.imported_at as string).slice(0, 7);
			const set = map.get(mo) ?? new Set();
			set.add(r.strategy as string);
			map.set(mo, set);
		}
		if (map.size < 3) return null;
		const months = [...map.keys()].sort();
		const pts = months.map((m) => ({ m: m.slice(5), count: map.get(m)!.size }));
		const maxCount = Math.max(...pts.map((p) => p.count), 1);
		const W = 300,
			H = 60,
			PAD = 8;
		const bw = (W - PAD * 2) / pts.length - 1;
		return { pts, maxCount, W, H, PAD, bw };
	});

	const runDrawdownCDF = $derived.by(() => {
		if (!runs || runs.length < 15) return null;
		const vals = runs
			.filter((r) => r.max_drawdown_pct != null)
			.map((r) => r.max_drawdown_pct as number)
			.sort((a, b) => a - b);
		if (vals.length < 15) return null;
		const minV = vals[0],
			maxV = vals[vals.length - 1];
		const range = maxV - minV || 0.01;
		const W = 300,
			H = 80,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - minV) / range) * (W - PAD * 2);
		const toY = (i: number) => H - PAD - (i / (vals.length - 1)) * (H - PAD * 2);
		const polyline = vals.map((v, i) => `${toX(v)},${toY(i)}`).join(' ');
		const median = vals[Math.floor(vals.length * 0.5)];
		const p20 = vals[Math.floor(vals.length * 0.2)];
		return {
			polyline,
			W,
			H,
			PAD,
			minV: minV.toFixed(1),
			maxV: maxV.toFixed(1),
			median: median.toFixed(1),
			p20: p20.toFixed(1)
		};
	});

	const runProfitByStrategyMonth = $derived.by(() => {
		if (!runs || runs.length < 8) return null;
		const strats = [
			...new Set(runs.filter((r) => r.strategy).map((r) => r.strategy as string))
		].slice(0, 5);
		const months = [
			...new Set(
				runs.filter((r) => r.imported_at).map((r) => (r.imported_at as string).slice(0, 7))
			)
		]
			.sort()
			.slice(-5);
		if (strats.length < 2 || months.length < 2) return null;
		const map = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.strategy || !r.imported_at || r.total_profit_pct == null) continue;
			const key = `${r.strategy}|${(r.imported_at as string).slice(0, 7)}`;
			const arr = map.get(key) ?? [];
			arr.push(r.total_profit_pct as number);
			map.set(key, arr);
		}
		const cellW = 36,
			cellH = 18,
			PAD = 4;
		const W = PAD + (months.length + 1) * cellW + PAD;
		const H = PAD + (strats.length + 1) * cellH + PAD;
		let maxAbs = 0.01;
		const cells = strats.flatMap((s, si) =>
			months.map((mo, mi) => {
				const arr = map.get(`${s}|${mo}`);
				const avg = arr ? arr.reduce((a, v) => a + v, 0) / arr.length : 0;
				maxAbs = Math.max(maxAbs, Math.abs(avg));
				return { x: PAD + (mi + 1) * cellW, y: PAD + (si + 1) * cellH, avg, s: s.slice(0, 10), mo };
			})
		);
		return {
			cells,
			strats: strats.map((s) => s.slice(0, 10)),
			months,
			cellW,
			cellH,
			PAD,
			W,
			H,
			maxAbs
		};
	});

	const runSortinoStrategyRanking = $derived.by(() => {
		if (!runs || runs.length < 5) return null;
		const map = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.strategy || r.sortino == null) continue;
			const arr = map.get(r.strategy as string) ?? [];
			arr.push(r.sortino as number);
			map.set(r.strategy as string, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([name, vals]) => ({
				name: name.slice(0, 20),
				avg: vals.reduce((s, v) => s + v, 0) / vals.length
			}))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 8);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 300,
			H = rows.length * 18 + 10,
			PAD = 8,
			barMaxW = W - PAD * 2 - 80;
		const zeroX = PAD + 80 + barMaxW / 2;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const runWinRateCDF = $derived.by(() => {
		if (!runs || runs.length < 10) return null;
		const vals = runs
			.filter((r) => r.win_rate_pct != null)
			.map((r) => r.win_rate_pct as number)
			.sort((a, b) => a - b);
		if (vals.length < 8) return null;
		const minV = vals[0],
			maxV = vals[vals.length - 1];
		if (maxV === minV) return null;
		const W = 300,
			H = 70,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - minV) / (maxV - minV)) * (W - PAD * 2);
		const toY = (i: number) => H - PAD - (i / (vals.length - 1)) * (H - PAD * 2);
		const polyline = vals.map((v, i) => `${toX(v).toFixed(1)},${toY(i).toFixed(1)}`).join(' ');
		const p50X = toX(vals[Math.floor(vals.length / 2)]);
		const median = vals[Math.floor(vals.length / 2)].toFixed(1);
		return { polyline, p50X, W, H, PAD, minV: minV.toFixed(1), maxV: maxV.toFixed(1), median };
	});

	const runProfitVsSharpeScatter = $derived.by(() => {
		if (!runs || runs.length < 8) return null;
		const pts = runs
			.filter((r) => r.total_profit_pct != null && r.sharpe != null)
			.map((r) => ({ p: r.total_profit_pct as number, s: r.sharpe as number }));
		if (pts.length < 6) return null;
		const minP = Math.min(...pts.map((p) => p.p)),
			maxP = Math.max(...pts.map((p) => p.p), minP + 0.1);
		const minS = Math.min(...pts.map((p) => p.s)),
			maxS = Math.max(...pts.map((p) => p.s), minS + 0.1);
		const W = 300,
			H = 80,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - minP) / (maxP - minP)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - minS) / (maxS - minS)) * (H - PAD * 2);
		const zeroX = toX(0),
			zeroY = toY(0);
		return { pts, toX, toY, zeroX, zeroY, W, H, PAD };
	});

	const runAvgTradeCountByTFBars = $derived.by(() => {
		if (!runs || runs.length < 5) return null;
		const map = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.timeframe || r.total_trades == null) continue;
			const arr = map.get(r.timeframe as string) ?? [];
			arr.push(r.total_trades as number);
			map.set(r.timeframe as string, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([tf, vals]) => ({ tf, avg: vals.reduce((s, v) => s + v, 0) / vals.length }))
			.sort((a, b) => b.avg - a.avg);
		const maxAvg = Math.max(...rows.map((r) => r.avg), 1);
		const W = 300,
			H = rows.length * 20 + 6,
			PAD = 8,
			barMaxW = W - PAD * 2 - 40;
		return { rows, maxAvg, W, H, PAD, barMaxW };
	});

	const runBestCalmarByStrategy = $derived.by(() => {
		if (!runs || runs.length < 5) return null;
		const map = new Map<string, number>();
		for (const r of runs) {
			if (!r.strategy || r.calmar == null) continue;
			const prev = map.get(r.strategy as string) ?? -Infinity;
			if ((r.calmar as number) > prev) map.set(r.strategy as string, r.calmar as number);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([name, best]) => ({ name: name.slice(0, 18), best }))
			.sort((a, b) => b.best - a.best)
			.slice(0, 8);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.best)), 0.01);
		const W = 320,
			H = rows.length * 18 + 10,
			PAD = 8,
			barMaxW = W - PAD * 2 - 80;
		const zeroX = PAD + 80 + barMaxW / 2;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const runSharpeByPairCount = $derived.by(() => {
		if (!runs || runs.length < 8) return null;
		const buckets = new Map<string, number[]>([
			['1-5', []],
			['6-15', []],
			['16-30', []],
			['30+', []]
		]);
		for (const r of runs) {
			const pc = Array.isArray(r.pairs) ? r.pairs.length : undefined;
			if (pc == null || r.sharpe == null) continue;
			const key = pc <= 5 ? '1-5' : pc <= 15 ? '6-15' : pc <= 30 ? '16-30' : '30+';
			buckets.get(key)!.push(r.sharpe as number);
		}
		const ORDER = ['1-5', '6-15', '16-30', '30+'];
		const rows = ORDER.filter((k) => (buckets.get(k)?.length ?? 0) >= 2).map((k) => {
			const arr = buckets.get(k)!;
			return { k, avg: arr.reduce((s, v) => s + v, 0) / arr.length };
		});
		if (rows.length < 2) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 280,
			H = rows.length * 22 + 8,
			PAD = 8,
			barMaxW = W - 50;
		const zeroX = PAD + 30 + barMaxW / 2;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const runProfitByDow = $derived.by(() => {
		if (!runs || runs.length < 7) return null;
		const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
		const map = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.imported_at || r.total_profit_pct == null) continue;
			const dow = DAYS[new Date(r.imported_at as string).getDay()];
			const arr = map.get(dow) ?? [];
			arr.push(r.total_profit_pct as number);
			map.set(dow, arr);
		}
		const rows = DAYS.filter((d) => map.has(d)).map((d) => {
			const arr = map.get(d)!;
			return { d, avg: arr.reduce((s, v) => s + v, 0) / arr.length };
		});
		if (rows.length < 3) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 280,
			H = 64,
			PAD = 8,
			midY = H / 2;
		const bw = (W - PAD * 2) / rows.length - 1;
		return { rows, maxAbs, bw, W, H, PAD, midY };
	});

	const runMonthlyTradeCount = $derived.by(() => {
		if (!runs || runs.length < 5) return null;
		const byMonth = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.imported_at || r.total_trades == null) continue;
			const mo = (r.imported_at as string).slice(0, 7);
			const arr = byMonth.get(mo) ?? [];
			arr.push(r.total_trades as number);
			byMonth.set(mo, arr);
		}
		if (byMonth.size < 3) return null;
		const pts = [...byMonth.entries()]
			.sort(([a], [b]) => a.localeCompare(b))
			.map(([mo, arr]) => ({ mo: mo.slice(5), avg: arr.reduce((s, v) => s + v, 0) / arr.length }));
		const maxAvg = Math.max(...pts.map((p) => p.avg), 1);
		const W = 300,
			H = 60,
			PAD = 8;
		const bw = Math.max(1, (W - PAD * 2) / pts.length - 0.5);
		return { pts, maxAvg, bw, W, H, PAD };
	});

	const runAvgHoldTimeByTF = $derived.by(() => {
		if (!runs || runs.length < 5) return null;
		const map = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.timeframe || r.avg_duration == null) continue;
			const arr = map.get(r.timeframe as string) ?? [];
			arr.push(r.avg_duration as number);
			map.set(r.timeframe as string, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.filter(([, arr]) => arr.length >= 2)
			.map(([tf, arr]) => ({ tf, avg: arr.reduce((s, v) => s + v, 0) / arr.length }))
			.sort((a, b) => a.avg - b.avg);
		const maxAvg = Math.max(...rows.map((r) => r.avg), 1);
		const W = 280,
			H = rows.length * 20 + 8,
			PAD = 8,
			barMaxW = W - PAD * 2 - 40;
		return { rows, maxAvg, W, H, PAD, barMaxW };
	});

	const runCalmarBySortinoQuartile = $derived.by(() => {
		if (!runs || runs.length < 12) return null;
		const vals = runs
			.filter((r) => r.sortino != null)
			.map((r) => r.sortino as number)
			.sort((a, b) => a - b);
		const q25 = vals[Math.floor(vals.length * 0.25)];
		const q50 = vals[Math.floor(vals.length * 0.5)];
		const q75 = vals[Math.floor(vals.length * 0.75)];
		const buckets = [
			{ label: 'Q1', min: -Infinity, max: q25 },
			{ label: 'Q2', min: q25, max: q50 },
			{ label: 'Q3', min: q50, max: q75 },
			{ label: 'Q4', min: q75, max: Infinity }
		];
		const rows = buckets
			.map((b) => {
				const bRuns = runs.filter(
					(r) =>
						r.sortino != null &&
						r.calmar != null &&
						(r.sortino as number) >= b.min &&
						(r.sortino as number) < b.max
				);
				const avg = bRuns.length
					? bRuns.reduce((s, r) => s + (r.calmar as number), 0) / bRuns.length
					: 0;
				return { label: b.label, avg, n: bRuns.length };
			})
			.filter((r) => r.n > 0);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 280,
			H = 80,
			PAD = 10,
			midY = H / 2;
		const bw = (W - PAD * 2) / rows.length - 2;
		return { rows, maxAbs, bw, W, H, PAD, midY };
	});

	const runAvgWinRateByStrategy = $derived.by(() => {
		if (!runs || runs.length < 5) return null;
		const map = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.strategy || r.win_rate_pct == null) continue;
			const arr = map.get(r.strategy as string) ?? [];
			arr.push(r.win_rate_pct as number);
			map.set(r.strategy as string, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.filter(([, arr]) => arr.length >= 2)
			.map(([name, arr]) => ({
				name: (name as string).slice(0, 18),
				avg: arr.reduce((s, v) => s + v, 0) / arr.length
			}))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 8);
		const W = 300,
			H = rows.length * 20 + 8,
			PAD = 8,
			barMaxW = W - PAD * 2 - 90;
		return { rows, W, H, PAD, barMaxW };
	});

	const runProfitVsCalmarScatter = $derived.by(() => {
		if (!runs || runs.length < 10) return null;
		const pts = runs
			.filter((r) => r.total_profit_pct != null && r.calmar != null)
			.map((r) => ({
				x: r.total_profit_pct as number,
				y: r.calmar as number,
				wr: (r.win_rate_pct as number) ?? 50
			}));
		if (pts.length < 10) return null;
		const maxX = Math.max(...pts.map((p) => Math.abs(p.x)), 0.01);
		const maxY = Math.max(...pts.map((p) => Math.abs(p.y)), 0.01);
		const W = 300,
			H = 100,
			PAD = 12,
			midX = W / 2,
			midY = H / 2;
		return { pts, maxX, maxY, W, H, PAD, midX, midY };
	});

	const runProfitByTimeRange = $derived.by(() => {
		if (!runs || runs.length < 10) return null;
		const byYear = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.timerange || r.total_profit_pct == null) continue;
			const year = (r.timerange as string).slice(0, 4);
			if (!/^\d{4}$/.test(year)) continue;
			const arr = byYear.get(year) ?? [];
			arr.push(r.total_profit_pct as number);
			byYear.set(year, arr);
		}
		if (byYear.size < 2) return null;
		const bars = [...byYear.entries()]
			.sort(([a], [b]) => a.localeCompare(b))
			.map(([yr, arr]) => ({
				yr,
				avg: arr.reduce((s, v) => s + v, 0) / arr.length,
				n: arr.length
			}));
		const maxAbs = Math.max(...bars.map((b) => Math.abs(b.avg)), 0.01);
		const W = 300,
			H = 70,
			PAD = 8,
			midY = H / 2;
		const bw = Math.max(8, (W - PAD * 2) / bars.length - 2);
		return { bars, maxAbs, W, H, PAD, midY, bw };
	});

	const runSortinoTrend = $derived.by(() => {
		if (!runs || runs.length < 15) return null;
		const sorted = [...runs]
			.filter((r) => r.started_at && r.sortino != null)
			.sort(
				(a, b) =>
					new Date(a.started_at as string).getTime() - new Date(b.started_at as string).getTime()
			);
		if (sorted.length < 15) return null;
		const win = 8;
		const smoothed = sorted.slice(win - 1).map((_, i) => {
			const slice = sorted.slice(i, i + win);
			return slice.reduce((s, r) => s + (r.sortino as number), 0) / slice.length;
		});
		const minV = Math.min(...smoothed),
			maxV = Math.max(...smoothed, minV + 0.01);
		const W = 300,
			H = 65,
			PAD = 8;
		const toX = (i: number) => PAD + (i / (smoothed.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - minV) / (maxV - minV)) * (H - PAD * 2);
		const polyline = smoothed.map((v, i) => `${toX(i)},${toY(v)}`).join(' ');
		const y0 = toY(0);
		return {
			polyline,
			W,
			H,
			PAD,
			y0,
			minV: minV.toFixed(2),
			maxV: maxV.toFixed(2),
			n: smoothed.length
		};
	});

	const runProfitByPairCount = $derived.by(() => {
		if (!runs || runs.length < 10) return null;
		const byBucket = new Map<string, number[]>();
		for (const r of runs) {
			if (r.pairs == null || r.profit_factor == null) continue;
			const cnt = r.pairs.length;
			const bucket = cnt <= 5 ? '1-5' : cnt <= 15 ? '6-15' : cnt <= 30 ? '16-30' : '30+';
			const arr = byBucket.get(bucket) ?? [];
			arr.push(((r.profit_factor as number) - 1) * 100);
			byBucket.set(bucket, arr);
		}
		const order = ['1-5', '6-15', '16-30', '30+'];
		const bars = order
			.filter((k) => byBucket.has(k) && (byBucket.get(k)?.length ?? 0) >= 2)
			.map((k) => {
				const arr = byBucket.get(k)!;
				return { label: k, avg: arr.reduce((s, v) => s + v, 0) / arr.length };
			});
		if (bars.length < 2) return null;
		const maxAbs = Math.max(...bars.map((b) => Math.abs(b.avg)), 1);
		const W = 280,
			H = 65,
			PAD = 8,
			midY = H / 2;
		const bw = Math.max(20, (W - PAD * 2) / bars.length - 4);
		return { bars, maxAbs, W, H, PAD, midY, bw };
	});

	const runAvgDrawdownCDF = $derived.by(() => {
		if (!runs || runs.length < 10) return null;
		const vals = runs
			.filter((r) => r.max_drawdown_pct != null && (r.max_drawdown_pct as number) >= 0)
			.map((r) => r.max_drawdown_pct as number)
			.sort((a, b) => a - b);
		if (vals.length < 8) return null;
		const minV = vals[0],
			maxV = vals[vals.length - 1],
			rng = maxV - minV || 1;
		const W = 300,
			H = 70,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - minV) / rng) * (W - PAD * 2);
		const toY = (i: number) => H - PAD - (i / Math.max(vals.length - 1, 1)) * (H - PAD * 2);
		const polyline = vals.map((v, i) => `${toX(v).toFixed(1)},${toY(i).toFixed(1)}`).join(' ');
		const median = vals[Math.floor(vals.length / 2)];
		return {
			polyline,
			toX,
			toY,
			W,
			H,
			PAD,
			minV: minV.toFixed(1),
			maxV: maxV.toFixed(1),
			median: median.toFixed(1)
		};
	});
</script>

<svelte:head><title>{t(lang, 'archive.title')} · Crypto Quant</title></svelte:head>

<main class="mx-auto w-full max-w-[1600px] px-4 py-8 sm:px-6">
	<h1 class="text-2xl font-semibold tracking-tight">{t(lang, 'archive.title')}</h1>
	<p class="mt-1 text-sm text-muted-foreground">{t(lang, 'archive.subtitle')}</p>

	<!-- Golden Run: best composite quality score across all runs -->
	{#if goldenRun}
		{@const gr = goldenRun.run}
		{@const gs = goldenRun.score}
		<div class="mt-4 mb-2 rounded-xl border border-yellow-600/40 bg-yellow-950/20 p-4">
			<div class="mb-2 flex items-center gap-2">
				<span class="text-lg leading-none">🏆</span>
				<span class="text-xs font-semibold tracking-widest text-yellow-400 uppercase"
					>Golden Run — Highest Quality Score</span
				>
				<span
					class="ml-auto rounded border border-yellow-600/50 bg-yellow-900/40 px-2 py-0.5 font-mono text-xs text-yellow-300"
					>{gs}/100</span
				>
			</div>
			<div class="flex flex-wrap items-center gap-4">
				<div>
					<a
						href={`/strategies/${gr.strategy}`}
						class="font-semibold text-foreground hover:text-primary hover:underline"
						>{gr.strategy}</a
					>
					<p class="mt-0.5 font-mono text-[11px] text-muted-foreground">
						{gr.timeframe} · {gr.timerange ?? '—'} · #{gr.id}
					</p>
				</div>
				<div class="flex flex-wrap gap-4 font-mono text-xs">
					<div>
						<span class="text-muted-foreground">Profit</span>
						<span
							class="ml-1.5 font-semibold"
							class:text-green-400={(gr.total_profit_pct ?? 0) > 0}
							class:text-red-400={(gr.total_profit_pct ?? 0) < 0}
							>{gr.total_profit_pct == null ? '—' : gr.total_profit_pct.toFixed(1) + '%'}</span
						>
					</div>
					<div>
						<span class="text-muted-foreground">Sharpe</span>
						<span class="ml-1.5 text-foreground"
							>{gr.sharpe == null ? '—' : gr.sharpe.toFixed(2)}</span
						>
					</div>
					<div>
						<span class="text-muted-foreground">Calmar</span>
						<span class="ml-1.5 text-foreground"
							>{gr.calmar == null ? '—' : gr.calmar.toFixed(2)}</span
						>
					</div>
					<div>
						<span class="text-muted-foreground">MaxDD</span>
						<span class="ml-1.5 text-red-400"
							>{gr.max_drawdown_pct == null ? '—' : gr.max_drawdown_pct.toFixed(1) + '%'}</span
						>
					</div>
					<div>
						<span class="text-muted-foreground">WR</span>
						<span class="ml-1.5 text-foreground"
							>{gr.win_rate_pct == null ? '—' : gr.win_rate_pct.toFixed(1) + '%'}</span
						>
					</div>
					<div>
						<span class="text-muted-foreground">Trades</span>
						<span class="ml-1.5 text-foreground">{gr.total_trades ?? '—'}</span>
					</div>
				</div>
			</div>
		</div>
	{/if}

	<div class="mt-4 mb-3 flex flex-wrap items-center gap-2 rounded-lg border bg-card p-3">
		<label class="flex items-center gap-2 text-xs text-muted-foreground">
			{t(lang, 'archive.filter.strategy')}
			<select
				bind:value={strategy}
				class="rounded-md border border-border bg-background px-3 py-1 text-sm"
			>
				<option value="">{t(lang, 'common.all')}</option>
				{#each data.strategies as s, _i (_i)}
					<option>{s}</option>
				{/each}
			</select>
		</label>
		<label class="flex items-center gap-2 text-xs text-muted-foreground">
			Sort
			<select
				bind:value={sort}
				class="rounded-md border border-border bg-background px-3 py-1 text-sm"
			>
				<option value="started_desc">Started ↓</option>
				<option value="profit_desc">Profit ↓</option>
				<option value="dd_asc">DD ↑</option>
				<option value="calmar_desc">Calmar ↓</option>
				<option value="sharpe_desc">Sharpe ↓</option>
				<option value="sortino_desc">Sortino ↓</option>
				<option value="pf_desc">PF ↓</option>
				<option value="trades_desc">Trades ↓</option>
				<option value="quality_desc">Quality ↓</option>
			</select>
		</label>
		<!-- Metric threshold sliders -->
		<div class="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
			<label class="flex items-center gap-1.5">
				Profit ≥
				<input
					type="range"
					min={profitRange.min}
					max={profitRange.max}
					step="5"
					value={minProfit ?? profitRange.min}
					oninput={(e) => {
						const v = parseFloat((e.target as HTMLInputElement).value);
						minProfit = v <= profitRange.min ? null : v;
					}}
					class="w-20 accent-primary"
				/>
				<span class="w-10 font-mono text-foreground"
					>{minProfit != null ? minProfit + '%' : 'any'}</span
				>
			</label>
			<label class="flex items-center gap-1.5">
				Sharpe ≥
				<input
					type="range"
					min={sharpeRange.min}
					max={sharpeRange.max}
					step="0.1"
					value={minSharpe ?? sharpeRange.min}
					oninput={(e) => {
						const v = parseFloat((e.target as HTMLInputElement).value);
						minSharpe = v <= sharpeRange.min ? null : v;
					}}
					class="w-20 accent-primary"
				/>
				<span class="w-10 font-mono text-foreground"
					>{minSharpe != null ? minSharpe.toFixed(1) : 'any'}</span
				>
			</label>
			<label class="flex items-center gap-1.5">
				DD ≤
				<input
					type="range"
					min={ddRange.min}
					max={ddRange.max}
					step="1"
					value={maxDD ?? ddRange.max}
					oninput={(e) => {
						const v = parseFloat((e.target as HTMLInputElement).value);
						maxDD = v >= ddRange.max ? null : v;
					}}
					class="w-20 accent-primary"
				/>
				<span class="w-10 font-mono text-foreground">{maxDD != null ? maxDD + '%' : 'any'}</span>
			</label>
			{#if minProfit != null || minSharpe != null || maxDD != null}
				<button
					type="button"
					onclick={() => {
						minProfit = null;
						minSharpe = null;
						maxDD = null;
					}}
					class="text-[11px] text-primary hover:underline">clear</button
				>
			{/if}
		</div>

		<span class="ml-auto font-mono text-xs text-muted-foreground"
			>{rows.length} / {data.runs.length}</span
		>
		<button
			type="button"
			onclick={() => {
				const cols = [
					'id',
					'strategy',
					'timeframe',
					'timerange',
					'started_at',
					'total_trades',
					'win_rate_pct',
					'total_profit_pct',
					'total_profit_abs',
					'max_drawdown_pct',
					'calmar',
					'sharpe',
					'sortino',
					'profit_factor'
				];
				const header = cols.join(',');
				const csvRows = rows.map((r) =>
					cols
						.map((c) => {
							const v = (r as unknown as Record<string, unknown>)[c];
							return v == null
								? ''
								: typeof v === 'string' && v.includes(',')
									? `"${v}"`
									: String(v);
						})
						.join(',')
				);
				const blob = new Blob([header + '\n' + csvRows.join('\n')], { type: 'text/csv' });
				const url = URL.createObjectURL(blob);
				const a = document.createElement('a');
				a.href = url;
				a.download = `backtest_runs_${new Date().toISOString().slice(0, 10)}.csv`;
				a.click();
				URL.revokeObjectURL(url);
			}}
			class="flex items-center gap-1 rounded-md border border-border bg-secondary px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
		>
			↓ CSV
		</button>
	</div>

	<div class="-mx-3 overflow-x-auto rounded-lg border bg-card sm:mx-0">
		<table class="w-full text-sm">
			<thead class="bg-secondary text-left text-[11px] text-muted-foreground uppercase">
				<tr>
					<th class="w-8 px-3 py-2.5"></th>
					<th class="px-3"
						><span class="inline-flex items-center"
							>Started<InfoTip text={t(lang, 'metric.tip.started')} /></span
						></th
					>
					<th class="px-3">Strategy</th>
					<th class="px-3"
						><span class="inline-flex items-center"
							>TF<InfoTip text={t(lang, 'metric.tip.tf')} /></span
						></th
					>
					<th class="px-3 text-right"
						><span class="inline-flex items-center"
							>Trades<InfoTip text={t(lang, 'metric.tip.trades')} /></span
						></th
					>
					<th class="px-3 text-right"
						><span class="inline-flex items-center"
							>WR<InfoTip text={t(lang, 'metric.tip.wr')} /></span
						></th
					>
					<th class="px-3 text-right"
						><span class="inline-flex items-center"
							>Profit %<InfoTip text={t(lang, 'metric.tip.profit')} /></span
						></th
					>
					<th class="px-3 text-right"
						><span class="inline-flex items-center"
							>Abs<InfoTip text={t(lang, 'metric.tip.abs')} /></span
						></th
					>
					<th class="px-3 text-right"
						><span class="inline-flex items-center"
							>Max DD<InfoTip text={t(lang, 'metric.tip.maxDd')} /></span
						></th
					>
					<th class="px-3 text-right"
						><span class="inline-flex items-center"
							>Calmar<InfoTip text={t(lang, 'metric.tip.calmar')} /></span
						></th
					>
					<th class="px-3 text-right"
						><span class="inline-flex items-center"
							>Sharpe<InfoTip text={t(lang, 'metric.tip.sharpe')} /></span
						></th
					>
					<th class="px-3 text-right"
						><span class="inline-flex items-center"
							>Sortino<InfoTip text={t(lang, 'metric.tip.sortino')} placement="top" /></span
						></th
					>
					<th class="px-3 text-right"
						><span class="inline-flex items-center"
							>PF<InfoTip text={t(lang, 'metric.tip.pf')} placement="top" /></span
						></th
					>
					<th class="px-3"
						><span class="inline-flex items-center"
							>Pairs<InfoTip text={t(lang, 'metric.tip.pairs')} placement="top" /></span
						></th
					>
					<th
						class="px-3 text-right"
						title="Composite quality score: 40% Sharpe + 35% Profit − 25% DD (z-normalized, 0-100)"
						>Quality</th
					>
				</tr>
			</thead>
			<tbody class="font-mono text-xs">
				{#each rows as r, _i (_i)}
					{@const qs = qualityScores.get(r.id)}
					<tr
						class="cursor-pointer border-t border-border hover:bg-accent/50"
						onclick={() => showDetail(r.id)}
					>
						<td class="px-3 py-2">
							<input
								type="checkbox"
								checked={selected.has(r.id)}
								onclick={(e) => e.stopPropagation()}
								onchange={() => toggle(r.id)}
							/>
						</td>
						<td class="px-3 text-muted-foreground">{fmtTime(r.started_at)}</td>
						<td class="px-3 font-semibold">{r.strategy}</td>
						<td class="px-3">{r.timeframe ?? '-'}</td>
						<td class="px-3 text-right">{r.total_trades ?? 0}</td>
						<td class="px-3 text-right">{(r.win_rate_pct ?? 0).toFixed(1)}</td>
						<td
							class="px-3 text-right"
							class:text-green-500={(r.total_profit_pct ?? 0) > 0}
							class:text-red-500={(r.total_profit_pct ?? 0) < 0}
						>
							{fmtPct(r.total_profit_pct)}
						</td>
						<td
							class="px-3 text-right"
							class:text-green-500={(r.total_profit_abs ?? 0) > 0}
							class:text-red-500={(r.total_profit_abs ?? 0) < 0}
							>${(r.total_profit_abs ?? 0).toFixed(0)}</td
						>
						<td class="px-3 text-right" class:text-red-500={(r.max_drawdown_pct ?? 0) > 20}>
							{(r.max_drawdown_pct ?? 0).toFixed(2)}%
						</td>
						<td class="px-3 text-right">{r.calmar == null ? '-' : r.calmar.toFixed(2)}</td>
						<td class="px-3 text-right">{r.sharpe == null ? '-' : r.sharpe.toFixed(2)}</td>
						<td class="px-3 text-right">{r.sortino == null ? '-' : r.sortino.toFixed(2)}</td>
						<td class="px-3 text-right"
							>{r.profit_factor == null ? '-' : r.profit_factor.toFixed(2)}</td
						>
						<td class="px-3">
							{#each (r.pairs ?? []).slice(0, 3) as p, _i (_i)}
								<span
									class="mr-1 inline-block rounded bg-secondary px-1.5 py-0.5 text-[10px] text-secondary-foreground"
									>{p}</span
								>
							{/each}
						</td>
						<td class="px-3 text-right">
							{#if qs != null}
								<span
									class="inline-block rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold
									{qs >= 75
										? 'bg-green-500/25 text-green-400'
										: qs >= 50
											? 'bg-yellow-500/20 text-yellow-400'
											: qs >= 25
												? 'bg-muted/30 text-muted-foreground'
												: 'bg-red-500/20 text-red-400'}"
									title="Quality = 40% Sharpe + 35% Profit − 25% DD (z-score composite)">{qs}</span
								>
							{:else}
								<span class="text-muted-foreground">—</span>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<!-- ── Run scatter ─────────────────────────────────────────────────── -->
	{#if runScatter}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<div class="mb-2 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Run Performance Over Time <span class="ml-1 text-xs font-normal text-muted-foreground"
						>({data.runs.length} runs · date vs profit%)</span
					>
					<ChartInfo metric="totalProfit" {lang} />
				</h2>
				<div class="flex flex-wrap gap-2">
					{#each runScatter.stratSet as s, _i (_i)}
						<span class="flex items-center gap-1 text-[10px] text-muted-foreground">
							<span
								class="inline-block h-2 w-2 rounded-full"
								style="background:{runScatter.stratColor[s]}"
							></span>
							{s}
						</span>
					{/each}
				</div>
			</div>
			<div class="overflow-x-auto">
				<svg
					viewBox="0 0 {runScatter.W} {runScatter.H}"
					class="w-full"
					style="height:140px;min-width:300px"
				>
					<line
						x1="4"
						y1={runScatter.zeroY}
						x2={runScatter.W - 4}
						y2={runScatter.zeroY}
						stroke="var(--ch-rule)"
						stroke-width="1"
						stroke-dasharray="4 3"
					/>
					{#each runScatter.dots as d, _i (_i)}
						<circle
							cx={d.x.toFixed(1)}
							cy={d.y.toFixed(1)}
							r="4"
							fill={d.color}
							fill-opacity="0.75"
							stroke={d.color}
							stroke-width="0.5"
						>
							<title
								>{d.strategy} · {d.date} · {d.profit >= 0 ? '+' : ''}{d.profit.toFixed(1)}%</title
							>
						</circle>
					{/each}
				</svg>
			</div>
			<div class="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground">
				<span>older →</span>
				<span>← newer</span>
			</div>
		</section>
	{/if}

	{#if monthlyActivity}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Backtest Activity by Month <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({data.runs.length} total runs · last 18 months)</span
				>
				<ChartInfo metric="tradeCount" {lang} />
			</h2>
			<div class="flex items-end gap-1">
				{#each monthlyActivity as bar, _i (_i)}
					<div
						class="flex flex-1 flex-col items-center gap-1"
						title="{bar.month}: {bar.count} runs"
					>
						<div
							class="w-full rounded-t-sm bg-blue-500/55 transition-colors hover:bg-blue-400/75"
							style="height:{Math.max(2, Math.round(bar.barPct * 0.72))}px"
						></div>
						{#if bar.count > 0}
							<span class="font-mono text-[8px] text-muted-foreground">{bar.count}</span>
						{/if}
						<span
							class="origin-top-left -translate-x-1 rotate-[-45deg] font-mono text-[8px] text-muted-foreground"
							>{bar.month.slice(5)}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-3 text-[10px] text-muted-foreground">
				Bar height = run count · label = month number
			</p>
		</section>
	{/if}

	{#if profitHistogram}
		{@const ph = profitHistogram}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<div class="mb-2 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Profit% Distribution <span class="ml-1 text-xs font-normal text-muted-foreground"
						>({ph.total} runs · {ph.mn.toFixed(0)}% to {ph.mx.toFixed(0)}%)</span
					>
					<ChartInfo metric="totalProfit" {lang} />
				</h2>
				<span class="font-mono text-xs {ph.mean >= 0 ? 'text-green-400' : 'text-red-400'}"
					>mean {ph.mean >= 0 ? '+' : ''}{ph.mean.toFixed(1)}%</span
				>
			</div>
			<svg viewBox="0 0 {ph.W} {ph.H}" class="w-full" style="height:80px;min-width:280px">
				<!-- zero line -->
				{#if ph.zeroX >= 0 && ph.zeroX <= ph.W}
					<line
						x1={ph.zeroX}
						y1="0"
						x2={ph.zeroX}
						y2={ph.H}
						stroke="var(--ch-rule)"
						stroke-width="1"
						stroke-dasharray="3 2"
					/>
					<text x={ph.zeroX + 2} y="10" font-size="8" fill="var(--ch-rule-strong)">0%</text>
				{/if}
				<!-- mean line -->
				<line
					x1={ph.meanX}
					y1="0"
					x2={ph.meanX}
					y2={ph.H - 16}
					stroke="var(--ch-warn)"
					stroke-width="1"
					stroke-dasharray="4 2"
				/>
				<!-- bars -->
				{#each ph.bars as b, _i (_i)}
					{#if b.count > 0}
						<rect
							x={b.x + 0.5}
							y={ph.H - 16 - b.h}
							width={Math.max(1, ph.bw - 1)}
							height={b.h}
							fill={b.positive ? 'var(--ch-profit)' : 'var(--ch-loss-light)'}
							rx="1"
						>
							<title>{b.lo.toFixed(0)}% – {b.hi.toFixed(0)}%: {b.count} runs</title>
						</rect>
					{/if}
				{/each}
				<!-- x-axis labels -->
				{#each [0, 0.25, 0.5, 0.75, 1] as f, _i (_i)}
					{@const label = (ph.mn + f * (ph.mx - ph.mn)).toFixed(0) + '%'}
					<text
						x={f * ph.W}
						y={ph.H}
						text-anchor="middle"
						font-size="8"
						fill="var(--ch-rule-strong)">{label}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Green = positive return · Red = negative · Amber line = mean · {ph.bars.filter(
					(b) => b.positive && b.count > 0
				).length} / {ph.bars.filter((b) => b.count > 0).length} bins above zero
			</p>
		</section>
	{/if}

	{#if topPairsAcrossRuns}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Top Pairs Across All Runs <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({topPairsAcrossRuns.length} pairs · ranked by run frequency)</span
				>
				<ChartInfo metric="leaderboard" {lang} />
			</h2>
			<div class="grid grid-cols-2 gap-x-4 gap-y-1.5">
				{#each topPairsAcrossRuns as row, _i (_i)}
					<div class="flex items-center gap-2 text-xs">
						<span class="w-24 shrink-0 truncate font-mono text-[10px]" title={row.pair}
							>{row.pair}</span
						>
						<div class="relative h-4 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm bg-blue-500/40 transition-all"
								style="width:{row.barPct.toFixed(1)}%"
							></div>
							<span class="absolute inset-y-0 left-1.5 flex items-center font-mono text-[9px]"
								>{row.runCount}r</span
							>
						</div>
						<span class="w-10 shrink-0 text-right font-mono text-[9px] text-muted-foreground"
							>{row.stratCount}s</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				r = run count · s = unique strategies testing this pair
			</p>
		</section>
	{/if}

	{#if timeframeBreakdown}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Timeframe Performance Breakdown <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({data.runs.length} runs)</span
				>
				<ChartInfo metric="timeframe" {lang} />
			</h2>
			<div class="space-y-2">
				{#each timeframeBreakdown as row, _i (_i)}
					<div class="flex items-center gap-2 text-xs">
						<span class="w-10 shrink-0 text-right font-mono font-semibold">{row.tf}</span>
						<div class="relative h-6 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm bg-blue-500/45 transition-all"
								style="width:{row.barPct.toFixed(1)}%"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]"
								>{row.count} runs</span
							>
						</div>
						<span
							class="w-20 shrink-0 text-right font-mono text-[10px]"
							class:text-green-400={(row.avgProfit ?? 0) >= 0}
							class:text-red-400={(row.avgProfit ?? 0) < 0}
							>{row.avgProfit != null
								? (row.avgProfit >= 0 ? '+' : '') + row.avgProfit.toFixed(1) + '% avg'
								: '—'}</span
						>
						<span class="w-16 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
							{row.avgSharpe != null ? 'S ' + row.avgSharpe.toFixed(2) : ''}
						</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Bar width = run count · avg = mean total_profit% across runs in that timeframe
			</p>
		</section>
	{/if}

	{#if sharpeProfitBubble}
		{@const spb = sharpeProfitBubble}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Sharpe vs Profit Bubble <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({spb.dots.length} runs · bubble size = trade count)</span
				>
				<ChartInfo metric="sharpe" {lang} />
			</h2>
			<svg viewBox="0 0 {spb.W} {spb.H}" class="w-full" style="height:{spb.H}px;min-width:240px">
				<!-- zero lines -->
				{#if spb.zeroX > spb.PAD && spb.zeroX < spb.W - spb.PAD}
					<line
						x1={spb.zeroX}
						y1={spb.PAD}
						x2={spb.zeroX}
						y2={spb.H - spb.PAD}
						stroke="var(--ch-rule)"
						stroke-width="1"
						stroke-dasharray="3 2"
					/>
				{/if}
				{#if spb.zeroY > spb.PAD && spb.zeroY < spb.H - spb.PAD}
					<line
						x1={spb.PAD}
						y1={spb.zeroY}
						x2={spb.W - spb.PAD}
						y2={spb.zeroY}
						stroke="var(--ch-rule)"
						stroke-width="1"
						stroke-dasharray="3 2"
					/>
					<text x={spb.PAD + 2} y={spb.zeroY - 2} font-size="7" fill="var(--ch-rule)">Sharpe 0</text
					>
				{/if}
				{#each spb.dots as d, _i (_i)}
					<circle
						cx={d.x.toFixed(1)}
						cy={d.y.toFixed(1)}
						r={d.r.toFixed(1)}
						fill={d.gold
							? 'var(--ch-warn-light)'
							: d.profit >= 0
								? 'var(--ch-profit-light)'
								: 'var(--ch-loss-light)'}
						stroke={d.gold ? '#fde047' : 'none'}
						stroke-width="0.5"
					>
						<title
							>{d.strategy} · profit {d.profit >= 0 ? '+' : ''}{d.profit.toFixed(1)}% · Sharpe {d.sharpe.toFixed(
								2
							)} · {d.trades} trades</title
						>
					</circle>
				{/each}
				<text x={spb.PAD} y={spb.H - 2} font-size="7" fill="var(--ch-rule)"
					>{spb.xMin.toFixed(0)}%</text
				>
				<text
					x={spb.W - spb.PAD}
					y={spb.H - 2}
					font-size="7"
					fill="var(--ch-rule)"
					text-anchor="end">{spb.xMax.toFixed(0)}% profit →</text
				>
				<text
					x={spb.W - spb.PAD}
					y="10"
					font-size="7"
					fill="var(--ch-rule-strong)"
					text-anchor="end">★ top-right = best</text
				>
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				x = profit% · y = Sharpe · bubble size ∝ trade count · yellow = positive Sharpe &amp; profit
				· top-right quadrant = high-quality runs
			</p>
		</section>
	{/if}

	{#if winRateTradeScatter}
		{@const wrts = winRateTradeScatter}
		<section class="mt-6 rounded-lg border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Win Rate vs Trade Count <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({wrts.dots.length} runs)</span
				>
				<ChartInfo metric="winRate" {lang} />
			</h2>
			<svg viewBox="0 0 {wrts.W} {wrts.H}" class="w-full" style="height:{wrts.H}px">
				{#if wrts.fiftyY > wrts.PAD && wrts.fiftyY < wrts.H - wrts.PAD}
					<line
						x1={wrts.PAD}
						y1={wrts.fiftyY}
						x2={wrts.W - wrts.PAD}
						y2={wrts.fiftyY}
						stroke="var(--ch-rule)"
						stroke-width="1"
						stroke-dasharray="3 2"
					/>
					<text x={wrts.PAD + 2} y={wrts.fiftyY - 2} font-size="7" fill="var(--ch-rule)"
						>WR 50%</text
					>
				{/if}
				{#each wrts.dots as d, _i (_i)}
					<circle
						cx={d.x.toFixed(1)}
						cy={d.y.toFixed(1)}
						r="2.5"
						fill={(d.profit ?? 0) > 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)'}
						stroke="none"
					>
						<title
							>{d.strategy} · {d.trades} trades · WR {d.wr.toFixed(1)}% · profit {d.profit != null
								? (d.profit >= 0 ? '+' : '') + d.profit.toFixed(1) + '%'
								: '—'}</title
						>
					</circle>
				{/each}
				<text x={wrts.PAD} y={wrts.H - 3} font-size="7" fill="var(--ch-rule)"
					>{wrts.xMin} trades</text
				>
				<text
					x={wrts.W - wrts.PAD}
					y={wrts.H - 3}
					font-size="7"
					fill="var(--ch-rule)"
					text-anchor="end">{wrts.xMax}</text
				>
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				x = trade count · y = win rate% · green = profitable run · more trades = more statistically
				reliable WR
			</p>
		</section>
	{/if}

	{#if sortinoHistogram}
		{@const sh = sortinoHistogram}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Sortino Distribution <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({sh.total} runs · avg {sh.avg.toFixed(2)})</span
				>
				<ChartInfo metric="sortino" {lang} />
			</h2>
			<div class="flex h-20 items-end gap-2">
				{#each sh.buckets as b, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-1">
						<span class="font-mono text-[9px] text-muted-foreground"
							>{b.count > 0 ? b.count : ''}</span
						>
						<div
							class="w-full rounded-t-sm transition-all"
							style="height:{Math.max(2, b.barPct * 0.64)}px; background:{b.color}"
						></div>
						<span class="text-center font-mono text-[9px] leading-tight text-muted-foreground"
							>{b.label}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Sortino = return / downside deviation · ≥2 considered strong · avg {sh.avg.toFixed(2)}
			</p>
		</section>
	{/if}

	{#if profitFactorHist}
		{@const pfh = profitFactorHist}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Profit Factor Distribution <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({pfh.total} runs · avg {pfh.avg.toFixed(2)})</span
				>
				<ChartInfo metric="profitFactor" {lang} />
			</h2>
			<div class="flex h-20 items-end gap-2">
				{#each pfh.buckets as b, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-1">
						<span class="font-mono text-[9px] text-muted-foreground"
							>{b.count > 0 ? b.count : ''}</span
						>
						<div
							class="w-full rounded-t-sm transition-all"
							style="height:{Math.max(2, b.barPct * 0.64)}px; background:{b.color}"
						></div>
						<span class="text-center font-mono text-[9px] leading-tight text-muted-foreground"
							>{b.label}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				PF distribution across all runs · red = losing (PF&lt;1) · yellow = marginal · green =
				healthy · avg PF {pfh.avg.toFixed(2)}
			</p>
		</section>
	{/if}

	{#if strategyReliability}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Strategy Reliability <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({strategyReliability.length} strategies · % of runs that are profitable)</span
				>
				<ChartInfo metric="leaderboard" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each strategyReliability as row, _i (_i)}
					<div class="flex items-center gap-2 text-xs">
						<span
							class="w-36 shrink-0 truncate font-mono text-[10px] text-muted-foreground"
							title={row.strategy}>{row.strategy}</span
						>
						<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm transition-all"
								style="width:{(row.rate * 100).toFixed(1)}%; background:hsl({Math.round(
									row.rate * 120
								)},55%,35%)"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]"
								>{row.profitable}/{row.total} runs</span
							>
						</div>
						<span
							class="w-12 shrink-0 text-right font-mono text-[10px] font-semibold"
							class:text-green-400={row.rate >= 0.6}
							class:text-amber-400={row.rate >= 0.4 && row.rate < 0.6}
							class:text-red-400={row.rate < 0.4}>{(row.rate * 100).toFixed(0)}%</span
						>
						<span
							class="w-20 shrink-0 text-right font-mono text-[10px]"
							class:text-green-400={row.avgProfit >= 0}
							class:text-red-400={row.avgProfit < 0}
							>{row.avgProfit >= 0 ? '+' : ''}{row.avgProfit.toFixed(1)}% avg</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				% profitable = runs where total_profit% > 0 · avg = mean profit across all runs · green
				≥60%, amber 40-60%, red &lt;40%
			</p>
		</section>
	{/if}

	{#if qualityDdScatter}
		{@const qds = qualityDdScatter}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Quality vs Max Drawdown <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({qds.dots.length} runs · Pareto frontier highlighted)</span
				>
				<ChartInfo metric="maxDrawdown" {lang} />
			</h2>
			<svg viewBox="0 0 {qds.W} {qds.H}" class="w-full" style="height:{qds.H}px;min-width:240px">
				<!-- grid -->
				<line
					x1={qds.PAD}
					y1={qds.PAD}
					x2={qds.PAD}
					y2={qds.H - qds.PAD}
					stroke="var(--ch-rule-faint)"
					stroke-width="1"
				/>
				<line
					x1={qds.PAD}
					y1={qds.H - qds.PAD}
					x2={qds.W - qds.PAD}
					y2={qds.H - qds.PAD}
					stroke="var(--ch-rule-faint)"
					stroke-width="1"
				/>
				<!-- dots -->
				{#each qds.dots as d, _i (_i)}
					<circle
						cx={d.x.toFixed(1)}
						cy={d.y.toFixed(1)}
						r="3"
						fill={(d.profit ?? 0) >= 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)'}
						stroke="none"
					>
						<title
							>{d.strategy} · DD {d.dd.toFixed(1)}% · quality {d.q.toFixed(0)} · profit {d.profit !=
							null
								? (d.profit >= 0 ? '+' : '') + d.profit.toFixed(1) + '%'
								: '—'}</title
						>
					</circle>
				{/each}
				<!-- Pareto frontier -->
				{#if qds.frontLine}
					<polyline
						points={qds.frontLine}
						fill="none"
						stroke="var(--ch-warn)"
						stroke-width="1.5"
						stroke-dasharray="5 2"
					/>
				{/if}
				<!-- axis labels -->
				<text x={qds.PAD} y={qds.H - 2} font-size="7" fill="var(--ch-rule-strong)"
					>{qds.ddMin.toFixed(0)}% DD</text
				>
				<text
					x={qds.W - qds.PAD}
					y={qds.H - 2}
					font-size="7"
					fill="var(--ch-rule-strong)"
					text-anchor="end">{qds.ddMax.toFixed(0)}% DD →</text
				>
				<text x={qds.PAD + 2} y={qds.PAD + 8} font-size="7" fill="var(--ch-rule-strong)"
					>quality ↑</text
				>
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				x = max drawdown% (lower=better) · y = quality score (higher=better) · amber =
				Pareto-efficient frontier · top-left = best
			</p>
		</section>
	{/if}

	{#if strategyComparison}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Strategy Best-Run Comparison <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({strategyComparison.length} strategies · ranked by quality score)</span
				>
				<ChartInfo metric="leaderboard" {lang} />
			</h2>
			<div class="overflow-x-auto">
				<table class="w-full text-[11px]">
					<thead>
						<tr class="border-b border-border text-muted-foreground">
							<th class="pb-2 text-left font-normal">Strategy</th>
							<th class="pr-3 pb-2 text-right font-normal">Profit%</th>
							<th class="pr-3 pb-2 text-right font-normal">Sharpe</th>
							<th class="pr-3 pb-2 text-right font-normal">Calmar</th>
							<th class="pr-3 pb-2 text-right font-normal">MaxDD%</th>
							<th class="pb-2 text-right font-normal">Quality</th>
						</tr>
					</thead>
					<tbody>
						{#each strategyComparison as row, i (i)}
							<tr class="border-b border-border/40 {i === 0 ? 'bg-yellow-950/20' : ''}">
								<td
									class="max-w-[140px] truncate py-1.5 pr-3 font-mono font-medium"
									title={row.strategy}>{row.strategy}</td
								>
								<td
									class="py-1.5 pr-3 text-right font-mono {(row.profit ?? 0) >= 0
										? 'text-green-400'
										: 'text-red-400'}"
								>
									{row.profit != null
										? (row.profit >= 0 ? '+' : '') + row.profit.toFixed(1) + '%'
										: '—'}
								</td>
								<td
									class="py-1.5 pr-3 text-right font-mono {(row.sharpe ?? 0) >= 1
										? 'text-green-400'
										: (row.sharpe ?? 0) >= 0
											? 'text-yellow-400'
											: 'text-red-400'}"
								>
									{row.sharpe != null ? row.sharpe.toFixed(2) : '—'}
								</td>
								<td
									class="py-1.5 pr-3 text-right font-mono {(row.calmar ?? 0) >= 1
										? 'text-green-400'
										: 'text-muted-foreground'}"
								>
									{row.calmar != null ? row.calmar.toFixed(2) : '—'}
								</td>
								<td
									class="py-1.5 pr-3 text-right font-mono {(row.dd ?? 0) <= 20
										? 'text-green-400'
										: (row.dd ?? 0) <= 40
											? 'text-yellow-400'
											: 'text-red-400'}"
								>
									{row.dd != null ? row.dd.toFixed(1) + '%' : '—'}
								</td>
								<td class="py-1.5 text-right">
									<span
										class="rounded px-1.5 py-0.5 font-mono text-[10px] font-bold"
										style="background:rgba(74,158,255,{((row.score / 100) * 0.5 + 0.1).toFixed(
											2
										)});color:#93c5fd"
									>
										{row.score}
									</span>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Each row = best-quality run for that strategy · Quality = composite z-score of Sharpe +
				Profit% − MaxDD
			</p>
		</section>
	{/if}

	<!-- ── Detail panel ──────────────────────────────────────────────────── -->
	{#if detailId && detailRun}
		<section class="mt-6 rounded-lg border bg-card p-6">
			<h3 class="text-lg font-semibold">
				{detailRun.strategy} · run #{detailRun.id}
			</h3>
			<p class="mt-1 text-sm text-muted-foreground">
				Started {fmtTime(detailRun.started_at)} · {detailRun.total_trades} trades · Profit
				{fmtPct(detailRun.total_profit_pct)} · Max DD {(detailRun.max_drawdown_pct ?? 0).toFixed(
					2
				)}%
			</p>

			<!-- Equity curve (pure SVG) -->
			<div class="mt-4">
				<h4 class="mb-2 text-sm font-semibold text-muted-foreground">
					{t(lang, 'archive.equity.title')}
				</h4>
				{#if equitySvgData}
					{@const d = equitySvgData}
					<div class="overflow-hidden rounded border">
						<svg
							viewBox="0 0 {d.W} {d.H}"
							width="100%"
							height="120"
							xmlns="http://www.w3.org/2000/svg"
							aria-label={t(lang, 'archive.equity.title')}
						>
							<defs>
								<linearGradient id={d.gradId} x1="0" y1="0" x2="0" y2="1">
									<stop offset="0%" stop-color={d.lineColor} stop-opacity="0.3" />
									<stop offset="100%" stop-color={d.lineColor} stop-opacity="0" />
								</linearGradient>
							</defs>

							<!-- Max drawdown shading -->
							{#if d.ddRegion && d.ddRegion.width > 0}
								<rect
									x={d.ddRegion.x}
									y={d.ddRegion.y}
									width={d.ddRegion.width}
									height={d.ddRegion.height}
									fill="var(--ch-loss-light)"
								/>
							{/if}

							<!-- Area fill -->
							<path d={d.areaPath} fill="url(#{d.gradId})" />

							<!-- Zero line -->
							{#if d.zeroY !== null}
								<line
									x1={d.PAD.left}
									y1={d.zeroY}
									x2={d.W - d.PAD.right}
									y2={d.zeroY}
									stroke="#ffffff20"
									stroke-width="1"
									stroke-dasharray="4 3"
								/>
							{/if}

							<!-- Equity line -->
							<polyline
								points={d.points}
								fill="none"
								stroke={d.lineColor}
								stroke-width="1.5"
								stroke-linejoin="round"
								stroke-linecap="round"
							/>

							<!-- Start label -->
							<text
								x={d.firstX + 4}
								y={d.H - d.PAD.bottom + 14}
								fill="#94a3b8"
								font-size="9"
								font-family="ui-monospace,monospace">${d.startLabel}</text
							>

							<!-- End label -->
							<text
								x={d.lastX - 4}
								y={d.H - d.PAD.bottom + 14}
								fill={d.isProfit ? '#22c55e' : '#ef4444'}
								font-size="9"
								font-family="ui-monospace,monospace"
								text-anchor="end">${d.endLabel}</text
							>
						</svg>
					</div>
				{:else if detailTrades.length === 0}
					<!-- still loading or no trades yet — show nothing -->
				{:else}
					<p class="rounded border px-4 py-3 text-sm text-muted-foreground">
						{t(lang, 'archive.equity.empty')}
					</p>
				{/if}
			</div>

			<!-- Analysis tabs -->
			{#if detailTrades.length > 0}
				<div class="mt-6">
					<!-- Tab buttons -->
					<div class="mb-4 flex gap-2">
						<button
							onclick={() => {
								activeTab = 'pair';
							}}
							class="rounded-full px-4 py-1.5 text-xs font-medium transition-colors {activeTab ===
							'pair'
								? 'bg-primary text-primary-foreground'
								: 'border border-border bg-secondary text-secondary-foreground hover:bg-accent'}"
						>
							By Pair
						</button>
						<button
							onclick={() => {
								activeTab = 'exit';
							}}
							class="rounded-full px-4 py-1.5 text-xs font-medium transition-colors {activeTab ===
							'exit'
								? 'bg-primary text-primary-foreground'
								: 'border border-border bg-secondary text-secondary-foreground hover:bg-accent'}"
						>
							By Exit
						</button>
					</div>

					{#if activeTab === 'pair'}
						<!-- By Pair: horizontal bar chart -->
						<div class="space-y-2">
							{#each pairStats as s, _i (_i)}
								{@const barPct = (Math.abs(s.total_profit_abs) / pairBarMax) * 100}
								{@const isProfit = s.total_profit_abs >= 0}
								<div class="flex items-center gap-3 font-mono text-xs">
									<span
										class="w-24 flex-shrink-0 truncate text-right text-muted-foreground"
										title={s.pair}>{s.pair}</span
									>
									<div class="h-5 flex-1 overflow-hidden rounded bg-secondary">
										<div
											class="h-full rounded transition-all"
											style="width:{barPct.toFixed(1)}%;background-color:{isProfit
												? '#22c55e'
												: '#ef4444'};opacity:0.75"
										></div>
									</div>
									<span class="w-28 flex-shrink-0 {isProfit ? 'text-green-400' : 'text-red-400'}">
										{isProfit ? '+' : ''}{s.total_profit_abs.toFixed(2)} USDT
									</span>
									<span class="w-16 flex-shrink-0 text-muted-foreground">{s.count} trades</span>
									<span
										class="w-14 flex-shrink-0 {s.win_rate >= 50
											? 'text-green-400'
											: 'text-red-400'}">{s.win_rate.toFixed(0)}% win</span
									>
								</div>
							{/each}
							{#if pairStats.length === 0}
								<p class="py-2 text-sm text-muted-foreground">No pair data available.</p>
							{/if}
						</div>
					{:else}
						<!-- By Exit: table -->
						<div class="overflow-x-auto rounded border">
							<table class="w-full text-xs">
								<thead class="bg-secondary text-left text-[10px] text-muted-foreground uppercase">
									<tr>
										<th class="px-3 py-2">Exit Reason</th>
										<th class="px-3 py-2 text-right">Trades</th>
										<th class="px-3 py-2 text-right">Total P&amp;L</th>
										<th class="px-3 py-2 text-right">Avg%</th>
										<th class="px-3 py-2 text-right">Win%</th>
									</tr>
								</thead>
								<tbody class="font-mono">
									{#each exitStats as s, _i (_i)}
										{@const isProfit = s.total_profit_abs >= 0}
										<tr class="border-t border-border">
											<td class="px-3 py-1.5">
												<span
													class="inline-block rounded px-2 py-0.5 text-[10px] font-medium {exitReasonChipClass(
														s.exit_reason
													)}"
												>
													{s.exit_reason}
												</span>
											</td>
											<td class="px-3 py-1.5 text-right text-muted-foreground">{s.count}</td>
											<td
												class="px-3 py-1.5 text-right {isProfit
													? 'text-green-400'
													: 'text-red-400'}"
											>
												{isProfit ? '+' : ''}${s.total_profit_abs.toFixed(2)}
											</td>
											<td
												class="px-3 py-1.5 text-right {s.mean_profit_pct >= 0
													? 'text-green-400'
													: 'text-red-400'}"
											>
												{s.mean_profit_pct >= 0 ? '+' : ''}{s.mean_profit_pct.toFixed(2)}%
											</td>
											<td
												class="px-3 py-1.5 text-right {s.win_rate >= 50
													? 'text-green-400'
													: 'text-red-400'}"
											>
												{s.win_rate.toFixed(0)}%
											</td>
										</tr>
									{/each}
									{#if exitStats.length === 0}
										<tr>
											<td colspan="5" class="px-3 py-3 text-center text-muted-foreground"
												>No exit data available.</td
											>
										</tr>
									{/if}
								</tbody>
							</table>
						</div>
					{/if}
				</div>
			{/if}

			<!-- Trades table -->
			{#if detailTrades.length}
				<h4 class="mt-6 mb-2 text-sm font-semibold">
					{lang === 'en' ? 'First 30 trades' : '前 30 笔'}
				</h4>
				<div class="overflow-x-auto rounded border">
					<table class="w-full text-xs">
						<thead class="bg-secondary text-left text-[10px] text-muted-foreground uppercase">
							<tr>
								<th class="px-3 py-2">#</th>
								<th class="px-3">Pair</th>
								<th class="px-3">Dir</th>
								<th class="px-3">Open</th>
								<th class="px-3">Close</th>
								<th class="px-3 text-right">P&L</th>
								<th class="px-3 text-right">%</th>
								<th class="px-3">Exit</th>
							</tr>
						</thead>
						<tbody class="font-mono">
							{#each detailTrades.slice(0, 30) as t, _i (_i)}
								<tr class="border-t border-border">
									<td class="px-3 py-1.5">{t.trade_id}</td>
									<td class="px-3">{t.pair}</td>
									<td class="px-3">{t.is_short ? '🔴S' : '🟢L'}</td>
									<td class="px-3 text-muted-foreground">{fmtTime(t.open_date)}</td>
									<td class="px-3 text-muted-foreground">{fmtTime(t.close_date)}</td>
									<td
										class="px-3 text-right"
										class:text-green-500={(t.profit_abs ?? 0) > 0}
										class:text-red-500={(t.profit_abs ?? 0) < 0}
									>
										${(t.profit_abs ?? 0).toFixed(2)}
									</td>
									<td
										class="px-3 text-right"
										class:text-green-500={(t.profit_pct ?? 0) > 0}
										class:text-red-500={(t.profit_pct ?? 0) < 0}
									>
										{(t.profit_pct ?? 0).toFixed(2)}%
									</td>
									<td class="px-3">{t.exit_reason ?? ''}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</section>
	{/if}

	{#if strategyActivityTimeline}
		{@const sat = strategyActivityTimeline}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Strategy Research Activity
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(run count per strategy per month · last 12 months)</span
				>
				<ChartInfo metric="tradeCount" {lang} />
			</h2>
			<div class="overflow-x-auto">
				<table class="w-full text-[10px]">
					<thead>
						<tr>
							<th class="w-36 pr-3 text-left font-normal text-muted-foreground">Strategy</th>
							{#each sat.months as m, _i (_i)}
								<th class="px-1 text-center font-normal text-muted-foreground">{m.slice(5)}</th>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each sat.grid as row, _i (_i)}
							<tr class="border-t border-border/20">
								<td
									class="max-w-[9rem] truncate py-1 pr-3 font-mono text-[10px] text-foreground"
									title={row.strategy}>{row.strategy}</td
								>
								{#each row.months as cell, _i (_i)}
									<td class="px-1 py-1 text-center">
										{#if cell.count > 0}
											<span
												class="inline-flex h-5 w-6 items-center justify-center rounded font-mono text-[9px]"
												style="background:rgba(99,102,241,{(
													(cell.count / sat.maxCount) * 0.75 +
													0.15
												).toFixed(2)}); color:white"
											>
												{cell.count}
											</span>
										{:else}
											<span class="text-muted-foreground/20">·</span>
										{/if}
									</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Darker = more backtest runs that month · shows research cadence per strategy
			</p>
		</section>
	{/if}

	{#if profitCalmarBubble}
		{@const pcb = profitCalmarBubble}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-2 text-sm font-semibold">
				Profit vs Calmar Bubble Chart
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>({pcb.dots.length} runs · bubble size = trade count)</span
				>
				<ChartInfo metric="calmar" {lang} />
			</h2>
			<svg viewBox="0 0 {pcb.W} {pcb.H}" class="w-full" style="height:{pcb.H}px">
				<line
					x1={pcb.zeroX.toFixed(1)}
					y1={pcb.PAD}
					x2={pcb.zeroX.toFixed(1)}
					y2={pcb.H - pcb.PAD}
					stroke="var(--ch-rule)"
					stroke-width="1"
					stroke-dasharray="3 2"
				/>
				<line
					x1={pcb.PAD}
					y1={pcb.zeroY.toFixed(1)}
					x2={pcb.W - pcb.PAD}
					y2={pcb.zeroY.toFixed(1)}
					stroke="var(--ch-rule)"
					stroke-width="1"
					stroke-dasharray="3 2"
				/>
				{#each pcb.dots as d, _i (_i)}
					<circle
						cx={d.x.toFixed(1)}
						cy={d.y.toFixed(1)}
						r={d.r.toFixed(1)}
						fill={d.profit >= 0 && d.calmar >= 0
							? 'var(--ch-profit-light)'
							: d.profit < 0
								? 'var(--ch-loss-light)'
								: 'var(--ch-warn-light)'}
						stroke="none"
					>
						<title
							>{d.strategy} · profit {d.profit >= 0 ? '+' : ''}{d.profit.toFixed(1)}% · calmar {d.calmar.toFixed(
								2
							)} · {d.trades} trades</title
						>
					</circle>
				{/each}
				<text x={pcb.PAD} y={pcb.H - 3} font-size="7" fill="var(--ch-rule)"
					>{pcb.xMin.toFixed(0)}%</text
				>
				<text
					x={pcb.W - pcb.PAD}
					y={pcb.H - 3}
					font-size="7"
					fill="var(--ch-rule)"
					text-anchor="end">{pcb.xMax.toFixed(0)}% profit</text
				>
				<text x={pcb.PAD + 2} y={pcb.PAD + 8} font-size="7" fill="var(--ch-rule)"
					>{pcb.yMax.toFixed(1)} calmar</text
				>
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				x = total profit% · y = Calmar ratio · bubble size = trade count · green = both positive ·
				hover for details
			</p>
		</section>
	{/if}

	{#if timeframeWinRateMatrix}
		{@const twm = timeframeWinRateMatrix}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Timeframe × Strategy Win Rate
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(avg win rate% per cell · top strategies)</span
				>
				<ChartInfo metric="winRate" {lang} />
			</h2>
			<div class="overflow-x-auto">
				<table class="w-full text-[10px]">
					<thead>
						<tr>
							<th class="w-36 pr-3 text-left font-normal text-muted-foreground">Strategy</th>
							{#each twm.timeframes as tf, _i (_i)}
								<th class="px-2 text-center font-normal text-muted-foreground">{tf}</th>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each twm.grid as row, _i (_i)}
							<tr class="border-t border-border/20">
								<td
									class="max-w-[9rem] truncate py-1 pr-3 font-mono text-[10px] text-foreground"
									title={row.strategy}>{row.strategy}</td
								>
								{#each row.cells as cell, _i (_i)}
									<td class="px-1 py-1 text-center">
										{#if cell}
											<span
												class="inline-flex h-6 w-10 items-center justify-center rounded font-mono text-[9px] font-semibold"
												style="background:{cell.avg >= 55
													? `rgba(34,197,94,${(((cell.avg - 50) / 50) * 0.7 + 0.15).toFixed(2)})`
													: `rgba(239,68,68,${(((50 - cell.avg) / 50) * 0.6 + 0.15).toFixed(2)})`}; color:white"
												title="{cell.count} runs"
											>
												{cell.avg.toFixed(0)}%
											</span>
										{:else}
											<span class="text-muted-foreground/20">·</span>
										{/if}
									</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Green &gt;55% win rate · red &lt;50% · hover for run count · blank = no data for that
				combination
			</p>
		</section>
	{/if}

	{#if holdingTimeVsProfit}
		{@const hvp = holdingTimeVsProfit}
		<section class="mt-6 rounded-lg border bg-card p-4">
			<h2 class="mb-1 text-sm font-semibold">
				Avg Hold Time vs Total Profit
				<span class="ml-2 font-mono text-xs text-muted-foreground">r = {hvp.corr.toFixed(2)}</span>
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(Pearson · does holding longer produce better outcomes?)</span
				>
				<ChartInfo metric="totalProfit" {lang} />
			</h2>
			<svg viewBox="0 0 {hvp.W} {hvp.H}" class="w-full" style="height:110px">
				<line
					x1={hvp.PAD}
					x2={hvp.W - hvp.PAD}
					y1={hvp.zeroY}
					y2={hvp.zeroY}
					stroke="var(--ch-rule)"
					stroke-width="1"
				/>
				{#each hvp.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="3" fill={d.color} opacity="0.8"
						><title>{d.title}</title></circle
					>
				{/each}
			</svg>
			<div class="flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{hvp.xMin.toFixed(0)}h hold</span><span>→ avg hold time →</span><span
					>{hvp.xMax.toFixed(0)}h</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Each dot = one backtest run · green = profitable · r &gt;0.2 = longer holds tend to be more
				profitable
			</p>
		</section>
	{/if}
	{#if winRateHistogram}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Win Rate Distribution
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(how runs spread across win rate buckets)</span
				>
				<ChartInfo metric="winRate" {lang} />
			</h2>
			<div class="mt-3 flex items-end gap-1" style="height:72px">
				{#each winRateHistogram as b, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-0.5">
						<span class="font-mono text-[8px] text-muted-foreground"
							>{b.count > 0 ? b.count : ''}</span
						>
						<div
							class="w-full rounded-t"
							style="height:{Math.max(2, b.barPct * 0.6)}px; background:{b.lo >= 60
								? 'var(--ch-profit-light)'
								: b.lo >= 40
									? 'var(--ch-warn-light)'
									: 'var(--ch-loss-light)'}"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>0%</span><span>→ win rate →</span><span>100%</span>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Green ≥60% · yellow 40–60% · red &lt;40% · shows how runs cluster by trade win rate
			</p>
		</section>
	{/if}
	{#if calmarVsWinRate}
		{@const cwr = calmarVsWinRate}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Calmar vs Win Rate
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(r = {cwr.corr.toFixed(2)} · do high-Calmar runs also have better win rates?)</span
				>
				<ChartInfo metric="calmar" {lang} />
			</h2>
			<svg viewBox="0 0 {cwr.W} {cwr.H}" class="w-full" style="height:110px">
				{#each cwr.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="3" fill={d.color} opacity="0.8"
						><title>{d.title}</title></circle
					>
				{/each}
			</svg>
			<div class="flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>Calmar {cwr.xMin.toFixed(1)}</span><span>→ Calmar ratio →</span><span
					>{cwr.xMax.toFixed(1)}</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Each dot = one run · green ≥55% wr · yellow 45–55% · red &lt;45% · r &gt;0.3 = higher Calmar
				tends to mean better win rate
			</p>
		</section>
	{/if}
	{#if sortinoVsHolding}
		{@const svh = sortinoVsHolding}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Sortino vs Holding Time
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(r = {svh.corr.toFixed(2)} · do longer-holding runs achieve better risk-adjusted returns?)</span
				>
				<ChartInfo metric="sortino" {lang} />
			</h2>
			<svg viewBox="0 0 {svh.W} {svh.H}" class="w-full" style="height:110px">
				{#each svh.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="3" fill={d.color} opacity="0.8"
						><title>{d.title}</title></circle
					>
				{/each}
			</svg>
			<div class="flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>Sortino {svh.xMin.toFixed(1)}</span><span>→ Sortino ratio →</span><span
					>{svh.xMax.toFixed(1)}</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Y-axis = avg holding hours · green Sortino ≥2 · yellow 0–2 · red &lt;0 · r &gt;0.2 = higher
				Sortino correlates with longer holds
			</p>
		</section>
	{/if}
	{#if profitFactorDistribution}
		{@const pfd = profitFactorDistribution}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Profit Factor Distribution
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(across {pfd.total} runs · avg {pfd.avg.toFixed(2)} · {(
						pfd.profitableShare * 100
					).toFixed(0)}% above 1.0)</span
				>
				<ChartInfo metric="profitFactor" {lang} />
			</h2>
			<div class="mt-3 flex items-end gap-1" style="height:72px">
				{#each pfd.buckets as b, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-0.5">
						<span class="font-mono text-[8px] text-muted-foreground"
							>{b.count > 0 ? b.count : ''}</span
						>
						<div
							class="w-full rounded-t"
							style="height:{Math.max(2, b.barPct * 0.62)}px; background:{b.lo >= 1
								? 'var(--ch-profit-light)'
								: 'var(--ch-loss-light)'}"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				{#each pfd.buckets as b, _i (_i)}
					<span class="flex-1 text-center">{b.label}</span>
				{/each}
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				PF &gt;1 = gross wins exceed losses (green) · PF &lt;1 = net loser (red) · ideal range is
				1.5–3
			</p>
		</section>
	{/if}
	{#if runCountByMonth}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Research Cadence — Runs per Month
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(how many backtest runs were imported each calendar month)</span
				>
				<ChartInfo metric="tradeCount" {lang} />
			</h2>
			<div class="mt-3 flex items-end gap-0.5" style="height:64px">
				{#each runCountByMonth as m, _i (_i)}
					<div class="flex flex-1 flex-col items-center">
						<div
							class="w-full rounded-t"
							style="height:{Math.max(2, m.barPct * 0.56)}px; background:var(--ch-violet)"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{runCountByMonth[0]?.ym}</span><span>→ month →</span><span
					>{runCountByMonth[runCountByMonth.length - 1]?.ym}</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Taller bar = more runs imported that month · reveals active research periods vs quiet months
			</p>
		</section>
	{/if}

	{#if runDrawdownDistribution}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Drawdown Distribution <ChartInfo metric="maxDrawdown" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Histogram of max drawdown % across {runDrawdownDistribution.total} runs · median {runDrawdownDistribution.median.toFixed(
					1
				)}%
			</p>
			<div class="mt-3 flex items-end gap-1" style="height:80px">
				{#each runDrawdownDistribution.buckets as b, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-0.5">
						<span class="font-mono text-[8px] text-muted-foreground"
							>{b.count > 0 ? b.count : ''}</span
						>
						<div
							class="w-full rounded-sm"
							style="height:{b.barPct}%; background:rgba({Math.round(
								180 + (b.lo / 70) * 60
							)},{Math.round(60 - (b.lo / 70) * 40)},60,0.75); min-height:{b.count > 0 ? 2 : 0}px"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[8px] text-muted-foreground">
				{#each runDrawdownDistribution.buckets as b, _i (_i)}
					<span class="flex-1 text-center">{b.lo}%</span>
				{/each}
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Left bars (green) = low drawdown runs · right bars (red) = high drawdown · shows overall
				risk profile of research corpus
			</p>
		</section>
	{/if}

	{#if strategyBestCalmarSortinoScatter}
		{@const sbcs = strategyBestCalmarSortinoScatter}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Strategy Calmar vs Sortino (Aggregate) <ChartInfo metric="calmar" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Each dot = one strategy · X = best Calmar · Y = best Sortino · top-right = elite
				risk-adjusted performers
			</p>
			<svg viewBox="0 0 {sbcs.W} {sbcs.H}" class="mt-2 w-full" style="height:80px">
				{#each sbcs.mapped as p, _i (_i)}
					<circle cx={p.cx} cy={p.cy} r="3" fill="var(--ch-violet)" />
				{/each}
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>Calmar 0</span><span>→ best Calmar per strategy →</span><span
					>{sbcs.maxC.toFixed(1)}</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Aggregated per strategy (best run) · clusters top-right = reliably efficient strategies
				across both risk metrics
			</p>
		</section>
	{/if}

	{#if runImportDowDistribution}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Research Activity by Day of Week <ChartInfo metric="tradeCount" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Number of backtests imported per day of week — reveals when research sessions typically
				happen
			</p>
			<div class="mt-3 flex items-end gap-2" style="height:72px">
				{#each runImportDowDistribution as d, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-0.5">
						<span class="font-mono text-[9px] text-muted-foreground"
							>{d.count > 0 ? d.count : ''}</span
						>
						<div
							class="w-full rounded-sm"
							style="height:{d.barPct}%; background:rgba(99,102,241,{0.4 +
								d.barPct / 200}); min-height:{d.count > 0 ? 2 : 0}px"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-around font-mono text-[9px] text-muted-foreground">
				{#each runImportDowDistribution as d, _i (_i)}
					<span class="flex-1 text-center">{d.day}</span>
				{/each}
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Tallest bar = most active research day · weekend spikes suggest dedicated quant sessions
				outside trading hours
			</p>
		</section>
	{/if}

	{#if strategyProfitSpread}
		{@const sps = strategyProfitSpread}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Strategy Profit Spread (Min / Median / Max) <ChartInfo metric="totalProfit" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Top 10 by median profit% · each bar shows the full range [min→max] with median marker (min 3
				runs)
			</p>
			<div class="mt-3 space-y-2">
				{#each sps.rows as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right font-mono text-[10px] text-muted-foreground">{i + 1}</span>
						<span class="w-32 truncate font-mono text-[10px] text-muted-foreground">{r.name}</span>
						<div
							class="relative flex-1 overflow-hidden rounded-sm"
							style="height:14px; background:var(--ch-rule-faint)"
						>
							<div
								class="absolute h-full rounded-sm"
								style="left:{sps.toBarPct(r.min)}%; right:{100 -
									sps.toBarPct(r.max)}%; background:var(--ch-violet-light)"
							></div>
							<div
								class="absolute h-full w-0.5"
								style="left:{sps.toBarPct(r.med)}%; background:var(--ch-profit-strong)"
							></div>
						</div>
						<span class="w-20 text-right font-mono text-[9px] text-muted-foreground"
							>{r.min.toFixed(0)}→{r.max.toFixed(0)}%</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Wide bar = high variability across runs · narrow bar = consistent performer · green line =
				median profit · prefer narrow bars with positive median
			</p>
		</section>
	{/if}

	{#if strategyProfitByTimeframe}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Avg Profit% by Timeframe (All Runs) <ChartInfo metric="avgProfit" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Average total profit% grouped by timeframe across all archived runs (min 3 runs per TF) —
				which TF produces best results?
			</p>
			<div class="mt-3 flex items-end gap-2" style="height:72px">
				{#each strategyProfitByTimeframe as r, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-0.5">
						<span
							class="font-mono text-[8px]"
							style="color:{r.avg >= 0 ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
						>
							{r.avg >= 0 ? '+' : ''}{r.avg.toFixed(0)}%
						</span>
						<div
							class="w-full rounded-sm"
							style="height:{r.barPct}%; background:{r.avg >= 0
								? 'var(--ch-profit)'
								: 'var(--ch-loss-light)'}; min-height:2px"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-around font-mono text-[9px] text-muted-foreground">
				{#each strategyProfitByTimeframe as r, _i (_i)}
					<span class="flex-1 text-center">{r.tf}</span>
				{/each}
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Tallest green bar = highest average profit timeframe · n per TF shown in hover · informs
				which timeframe to prioritise in future research
			</p>
		</section>
	{/if}

	{#if runSortinoByTimeframe}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Avg Sortino by Timeframe (All Runs) <ChartInfo metric="sortino" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Average Sortino ratio per timeframe across all archived runs (min 3 per TF) — which TF
				produces the smoothest equity curve?
			</p>
			<div class="mt-3 flex items-end gap-2" style="height:72px">
				{#each runSortinoByTimeframe as r, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-0.5">
						<span
							class="font-mono text-[8px]"
							style="color:{r.avg >= 0 ? 'var(--ch-teal-strong)' : 'var(--ch-loss-solid)'}"
						>
							{r.avg.toFixed(1)}
						</span>
						<div
							class="w-full rounded-sm"
							style="height:{r.barPct}%; background:{r.avg >= 0
								? 'var(--ch-teal)'
								: 'var(--ch-loss-light)'}; min-height:2px"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-around font-mono text-[9px] text-muted-foreground">
				{#each runSortinoByTimeframe as r, _i (_i)}
					<span class="flex-1 text-center">{r.tf}</span>
				{/each}
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Higher Sortino = better downside-adjusted returns · timeframes at top suit risk-averse
				portfolios · n={runSortinoByTimeframe.reduce((s, r) => s + r.count, 0)} runs
			</p>
		</section>
	{/if}

	{#if runProfitCumulativeTimeline}
		{@const rpct = runProfitCumulativeTimeline}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Cumulative Research Profit <ChartInfo metric="totalProfit" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Running sum of total_profit% across all {rpct.total} runs by import date — overall research output
				quality
			</p>
			<svg viewBox="0 0 {rpct.W} {rpct.H}" class="mt-2 w-full" style="height:60px">
				<polyline
					points={rpct.poly}
					fill="none"
					stroke={rpct.positive ? 'var(--ch-profit-strong)' : 'var(--ch-loss-strong)'}
					stroke-width="1.5"
				/>
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{rpct.mn.toFixed(0)}%</span><span>→ runs by import date →</span><span
					>total: {rpct.mx >= 0 ? '+' : ''}{rpct.mx.toFixed(0)}%</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Steadily rising = consistently profitable research · flat or declining = recent strategies
				not adding value · steepening = research acceleration
			</p>
		</section>
	{/if}

	{#if runProfitFactorByTimeframe}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Profit Factor by Timeframe <ChartInfo metric="profitFactor" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Median profit factor per timeframe across all runs (≥3 runs) · PF &gt; 1.2 = acceptable edge
			</p>
			<div class="space-y-1">
				{#each runProfitFactorByTimeframe as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-10 text-right font-mono text-[11px] text-muted-foreground">{r.tf}</span>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:{r.good
									? 'var(--ch-profit)'
									: 'var(--ch-warn)'}"
							></div>
						</div>
						<span
							class="w-10 text-right font-mono text-[10px]"
							style="color:{r.good ? 'var(--ch-profit-solid)' : 'var(--ch-warn)'}"
							>PF {r.med.toFixed(2)}</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				PF = gross profit / gross loss · timeframes with consistently higher PF produce more
				reliable signals · PF &lt; 1 = net losing
			</p>
		</section>
	{/if}

	{#if runWinRateByTimeframe}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Median Win Rate by Timeframe <ChartInfo metric="winRate" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Median win rate% per timeframe across all runs (≥3 runs) · green = ≥50%
			</p>
			<div class="space-y-1">
				{#each runWinRateByTimeframe as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-10 text-right font-mono text-[11px] text-muted-foreground">{r.tf}</span>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:{r.good
									? 'var(--ch-profit)'
									: 'var(--ch-loss)'}"
							></div>
						</div>
						<span
							class="w-12 text-right font-mono text-[10px]"
							style="color:{r.good ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
							>WR {r.med.toFixed(1)}%</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Higher win rate at longer timeframes = cleaner signals · very high WR on short TF may
				indicate over-optimisation · WR alone doesn't indicate profitability
			</p>
		</section>
	{/if}

	{#if runTradeCountByTimeframe}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Median Trade Count by Timeframe <ChartInfo metric="tradeCount" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Median total trades per run, grouped by timeframe (≥3 runs) · shorter TF = more signals
			</p>
			<div class="space-y-1">
				{#each runTradeCountByTimeframe as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-10 text-right font-mono text-[11px] text-muted-foreground">{r.tf}</span>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:var(--ch-violet)"
							></div>
						</div>
						<span class="w-16 text-right font-mono text-[10px] text-muted-foreground"
							>{r.med.toFixed(0)} trades</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				High trade count on longer TF = overtrading · low count on short TF = overly selective ·
				median reveals typical strategy activity per timeframe
			</p>
		</section>
	{/if}

	{#if runStrategyTimeframeHeatmap}
		{@const rsh = runStrategyTimeframeHeatmap}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Strategy × Timeframe Profit Heatmap <ChartInfo metric="totalProfit" {lang} />
			</h2>
			<p class="mb-2 text-[11px] text-muted-foreground">
				Median total profit% per strategy × timeframe cell (≥2 runs) · green = profitable · red =
				losing
			</p>
			<div class="overflow-x-auto">
				<table class="w-full text-[9px]">
					<thead>
						<tr>
							<th class="pr-2 text-right font-mono text-muted-foreground">Strategy</th>
							{#each rsh.timeframes as tf, _i (_i)}
								<th class="px-1 text-center font-mono text-muted-foreground">{tf}</th>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each rsh.cells as row, _i (_i)}
							<tr class="border-t border-border/30">
								<td
									class="max-w-[8rem] truncate py-0.5 pr-2 text-right font-mono text-muted-foreground"
									>{row.strategy}</td
								>
								{#each row.tfs as cell, _i (_i)}
									<td
										class="px-1 py-0.5 text-center font-mono"
										title="{cell.tf}: {cell.med != null
											? cell.med.toFixed(1) + '% (' + cell.n + ' runs)'
											: 'no data'}"
									>
										{#if cell.med != null}
											<span
												class="inline-block rounded px-0.5"
												style="background:{cell.positive
													? `rgba(34,197,94,${0.1 + cell.intensity * 0.5})`
													: `rgba(239,68,68,${0.1 + cell.intensity * 0.5})`}; color:{cell.positive
													? 'var(--ch-profit-solid)'
													: 'var(--ch-loss-solid)'}"
												>{cell.med > 0 ? '+' : ''}{cell.med.toFixed(0)}%</span
											>
										{:else}
											<span class="text-muted-foreground/30">—</span>
										{/if}
									</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Darker green = consistently high profit · darker red = consistently losing · identify best
				strategy+timeframe combo for live deployment
			</p>
		</section>
	{/if}

	{#if runCalmarByStrategy}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Median Calmar by Strategy <ChartInfo metric="calmar" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Median Calmar ratio across all archived runs per strategy (≥3 runs) · Calmar = annual return
				/ max drawdown
			</p>
			<div class="space-y-1">
				{#each runCalmarByStrategy as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-36 truncate text-right font-mono text-[10px] text-muted-foreground"
							>{r.strategy}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:{r.positive
									? 'var(--ch-profit)'
									: 'var(--ch-loss)'}"
							></div>
						</div>
						<span
							class="w-14 text-right font-mono text-[10px]"
							style="color:{r.positive ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
							>{r.calmar.toFixed(2)}</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				High Calmar = strong return per unit of drawdown risk · use alongside Sortino and profit
				factor to rank strategies for live promotion
			</p>
		</section>
	{/if}

	{#if runSortinoByStrategy}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Median Sortino by Strategy <ChartInfo metric="sortino" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Median Sortino ratio across archived runs per strategy (≥3 runs) · Sortino penalises only
				downside volatility
			</p>
			<div class="space-y-1">
				{#each runSortinoByStrategy as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-36 truncate text-right font-mono text-[10px] text-muted-foreground"
							>{r.strategy}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:{r.positive
									? 'var(--ch-violet)'
									: 'var(--ch-loss)'}"
							></div>
						</div>
						<span
							class="w-14 text-right font-mono text-[10px]"
							style="color:{r.positive ? 'var(--ch-violet-strong)' : 'var(--ch-loss-solid)'}"
							>{r.sortino.toFixed(2)}</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				High Sortino = rewards strategies that limit losses while allowing upside · pair with Calmar
				leaderboard to identify consistently low-risk performers
			</p>
		</section>
	{/if}
	{#if runProfitFactorByStrategy}
		<section class="rounded-lg border border-border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Strategy Profit Factor Leaderboard <ChartInfo metric="profitFactor" {lang} />
			</h2>
			<div class="space-y-1">
				{#each runProfitFactorByStrategy as r, _i (_i)}
					{@const color = r.good
						? 'var(--ch-profit-strong)'
						: r.pf >= 1
							? 'var(--ch-violet)'
							: 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-36 truncate text-right font-mono text-[10px] text-muted-foreground"
							>{r.strategy}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div class="h-full rounded-sm" style="width:{r.barPct}%; background:{color}"></div>
						</div>
						<span class="w-12 text-right font-mono text-[10px]" style="color:{color}"
							>{r.pf.toFixed(2)}</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Median profit_factor (gross profit ÷ gross loss) · ≥1.5 = solid edge · &lt;1 = losing
				strategy · complement to Calmar (time-normalized) and Sortino (downside-only)
			</p>
		</section>
	{/if}
	{#if runSharpeByStrategy}
		<section class="rounded-lg border border-border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Strategy Sharpe Ratio Leaderboard <ChartInfo metric="sharpe" {lang} />
			</h2>
			<div class="space-y-1">
				{#each runSharpeByStrategy as r, _i (_i)}
					{@const color = r.positive ? 'var(--ch-violet-strong)' : 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-36 truncate text-right font-mono text-[10px] text-muted-foreground"
							>{r.strategy}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div class="h-full rounded-sm" style="width:{r.barPct}%; background:{color}"></div>
						</div>
						<span class="w-14 text-right font-mono text-[10px]" style="color:{color}"
							>{r.sharpe.toFixed(2)}</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Median Sharpe ratio per strategy · total-volatility adjusted return · fourth dimension
				alongside Calmar, Sortino, and Profit Factor leaderboards
			</p>
		</section>
	{/if}
	{#if runNetProfitByStrategy}
		<section class="rounded-xl border border-border bg-card p-4">
			<h2 class="mb-1 text-sm font-semibold">
				Net Cumulative Profit by Strategy <ChartInfo metric="totalProfit" {lang} />
			</h2>
			<p class="mb-3 text-[10px] text-muted-foreground">
				Sum of total_profit_pct across all runs per strategy — high total = many profitable runs,
				not just a single lucky outlier
			</p>
			<div class="space-y-1">
				{#each runNetProfitByStrategy as r, _i (_i)}
					{@const color = r.sum > 0 ? 'var(--ch-profit-strong)' : 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span
							class="w-36 truncate text-right font-mono text-[10px] text-muted-foreground"
							title={r.strategy}>{r.strategy}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div class="h-full rounded-sm" style="width:{r.barPct}%; background:{color}"></div>
						</div>
						<span class="w-20 text-right font-mono text-[10px]" style="color:{color}"
							>{r.sum > 0 ? '+' : ''}{r.sum.toFixed(0)}%</span
						>
						<span class="w-14 text-right font-mono text-[9px] text-muted-foreground"
							>{(r.winRate * 100).toFixed(0)}%wr·{r.count}r</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Green = strategy shows consistent positive returns · sum rewards volume of profitable runs,
				not just peak single run · complementary to best_profit leaderboard
			</p>
		</section>
	{/if}
	{#if runCalmarDistribution}
		<section class="rounded-xl border border-border bg-card p-4">
			<h2 class="mb-1 text-sm font-semibold">
				Calmar Ratio Distribution <ChartInfo metric="calmar" {lang} />
			</h2>
			<p class="mb-3 text-[10px] text-muted-foreground">
				Histogram of Calmar ratios across all filtered runs · median {runCalmarDistribution.median.toFixed(
					2
				)} · {runCalmarDistribution.positive}/{runCalmarDistribution.total} positive
			</p>
			<div class="flex h-20 items-end gap-0.5">
				{#each runCalmarDistribution.buckets as b, _i (_i)}
					{@const pct = (b.count / runCalmarDistribution.maxCount) * 100}
					{@const isPos = b.lo >= 0}
					<div class="flex flex-1 flex-col items-center gap-0.5">
						<div
							class="w-full rounded-t-sm"
							style="height:{Math.max(2, pct * 0.72)}px; background:{isPos
								? 'var(--ch-profit)'
								: 'var(--ch-loss)'}"
						></div>
						<span class="w-full truncate text-center font-mono text-[7px] text-muted-foreground"
							>{b.label}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Green = Calmar ≥ 0 · red = negative · bin width = {runCalmarDistribution.step.toFixed(2)} · Calmar
				= annual return / max drawdown · right-skewed = more high-quality runs
			</p>
		</section>
	{/if}
	{#if runProfitPerTradeByStrategy}
		<section class="rounded-xl border border-border bg-card p-4">
			<h2 class="mb-1 text-sm font-semibold">
				Avg Profit per Trade by Strategy <ChartInfo metric="avgProfit" {lang} />
			</h2>
			<p class="mb-3 text-[10px] text-muted-foreground">
				Average (total_profit_pct ÷ total_trades) per strategy — measures profit efficiency
				regardless of trade count
			</p>
			<div class="space-y-1">
				{#each runProfitPerTradeByStrategy as r, _i (_i)}
					{@const color = r.avg > 0 ? 'var(--ch-profit-strong)' : 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span
							class="w-36 truncate text-right font-mono text-[10px] text-muted-foreground"
							title={r.strategy}>{r.strategy}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div class="h-full rounded-sm" style="width:{r.barPct}%; background:{color}"></div>
						</div>
						<span class="w-16 text-right font-mono text-[10px]" style="color:{color}"
							>{r.avg > 0 ? '+' : ''}{r.avg.toFixed(3)}%</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Higher = each trade contributes more profit on average · rewards strategies that trade less
				but better · complements total profit (rewards frequency) and calmar (rewards risk control)
			</p>
		</section>
	{/if}

	{#if runSharpeVsWinRate}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Sharpe vs Win Rate</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Each dot = one backtest run · x = win rate % · y = Sharpe ratio · top-right cluster = high
				accuracy AND strong risk-adjusted return · color = timeframe
			</p>
			<svg viewBox="0 0 {runSharpeVsWinRate.W} {runSharpeVsWinRate.H}" class="w-full">
				{#if runSharpeVsWinRate.zeroY !== null}
					<line
						x1="0"
						y1={runSharpeVsWinRate.zeroY}
						x2={runSharpeVsWinRate.W}
						y2={runSharpeVsWinRate.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				{#each runSharpeVsWinRate.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="2.5" fill={d.color} opacity="0.8" />
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{runSharpeVsWinRate.total} runs · {runSharpeVsWinRate.positive} positive Sharpe · WR [{runSharpeVsWinRate.wMin}%–{runSharpeVsWinRate.wMax}%]
				· Sharpe [{runSharpeVsWinRate.sMin}–{runSharpeVsWinRate.sMax}] · color = timeframe
			</p>
		</section>
	{/if}

	{#if runProfitCvByStrategy}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Profit Consistency (CV) by Strategy</h3>
			<p class="mb-3 text-[10px] text-muted-foreground">
				Coefficient of variation = std ÷ mean of total_profit_pct across runs · lower = more
				consistent returns · sorted best first · high CV = erratic strategy
			</p>
			<div class="space-y-1.5">
				{#each runProfitCvByStrategy.rows as row, i (i)}
					{@const color =
						row.cv < 0.3
							? 'var(--ch-profit-strong)'
							: row.cv < 0.7
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					<div class="flex items-center gap-2 text-xs">
						<span class="w-4 shrink-0 text-right text-muted-foreground">{i + 1}</span>
						<span class="w-32 shrink-0 truncate font-mono text-[10px]">{row.strategy}</span>
						<div class="relative h-4 flex-1 overflow-hidden rounded bg-muted/30">
							<div
								class="h-full rounded"
								style="width:{((row.cv / runProfitCvByStrategy.maxCv) * 100).toFixed(
									1
								)}%; background:{color}"
							></div>
						</div>
						<span class="w-10 text-right font-mono text-[10px]" style="color:{color}"
							>{row.cv.toFixed(2)}</span
						>
						<span class="w-10 text-right text-[9px] text-muted-foreground">n={row.count}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				CV &lt;0.3 = very consistent · 0.3–0.7 = moderate · &gt;0.7 = erratic · consistent
				strategies are more reliable for live allocation · sorted by least variation first
			</p>
		</section>
	{/if}

	{#if runProfitVsTradeCount}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Total Profit vs Trade Count</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Each dot = one backtest run · x = total trades · y = total profit % · reveals whether
				high-frequency or low-frequency runs produce better returns · color = timeframe
			</p>
			<svg viewBox="0 0 {runProfitVsTradeCount.W} {runProfitVsTradeCount.H}" class="w-full">
				{#if runProfitVsTradeCount.zeroY !== null}
					<line
						x1="0"
						y1={runProfitVsTradeCount.zeroY}
						x2={runProfitVsTradeCount.W}
						y2={runProfitVsTradeCount.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				{#each runProfitVsTradeCount.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="2.5" fill={d.color} opacity="0.8" />
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{runProfitVsTradeCount.total} runs · {runProfitVsTradeCount.positive} profitable · trades [{runProfitVsTradeCount.tMin}–{runProfitVsTradeCount.tMax}]
				· profit [{runProfitVsTradeCount.pMin}%–{runProfitVsTradeCount.pMax}%] · cluster in
				top-center = high profit regardless of trade count
			</p>
		</section>
	{/if}

	{#if runDrawdownVsSortino}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Max Drawdown vs Sortino</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Each dot = one backtest run · x = max drawdown % · y = Sortino ratio · ideal = bottom-left
				(low DD, high Sortino) · color = timeframe
			</p>
			<svg viewBox="0 0 {runDrawdownVsSortino.W} {runDrawdownVsSortino.H}" class="w-full">
				{#if runDrawdownVsSortino.zeroY !== null}
					<line
						x1="0"
						y1={runDrawdownVsSortino.zeroY}
						x2={runDrawdownVsSortino.W}
						y2={runDrawdownVsSortino.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				{#each runDrawdownVsSortino.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="2.5" fill={d.color} opacity="0.8" />
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{runDrawdownVsSortino.total} runs · {runDrawdownVsSortino.elite} in low-DD/high-Sortino zone ·
				DD [{runDrawdownVsSortino.dMin}%–{runDrawdownVsSortino.dMax}%] · Sortino [{runDrawdownVsSortino.sMin}–{runDrawdownVsSortino.sMax}]
				· color = timeframe
			</p>
		</section>
	{/if}

	{#if runWinRateByStrategy}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Avg Win Rate by Strategy</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Average win rate % per strategy across all archived backtest runs · sorted highest to lowest
				· pairs with drawdown for full quality picture
			</p>
			<div class="space-y-1">
				{#each runWinRateByStrategy.rows as row, _i (_i)}
					{@const pct = ((row.avg / runWinRateByStrategy.maxAvg) * 100).toFixed(1)}
					{@const color =
						row.avg >= 60
							? 'var(--ch-profit)'
							: row.avg >= 45
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					<div class="flex items-center gap-2 text-[10px]">
						<span class="w-36 truncate font-mono text-[9px]">{row.strategy}</span>
						<div class="flex h-3 flex-1 overflow-hidden rounded bg-muted/30">
							<div class="h-full rounded" style="width:{pct}%; background:{color}"></div>
						</div>
						<span class="w-14 text-right font-mono" style="color:{color}"
							>{row.avg.toFixed(1)}%</span
						>
						<span class="w-10 text-right text-[9px] text-muted-foreground">n={row.count}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Green ≥60% · yellow 45–60% · red &lt;45% · best run shown separately · high WR alone ≠
				profitability without adequate R:R
			</p>
		</section>
	{/if}

	{#if runProfitSkewByTimeframe}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Profit Distribution Skew by Timeframe</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Skewness of total profit % across runs per timeframe · positive = right-tailed returns (rare
				big wins) · negative = left-tailed (occasional blow-ups)
			</p>
			<div class="space-y-1">
				{#each runProfitSkewByTimeframe.rows as row, _i (_i)}
					{@const color =
						row.skew > 0.3
							? 'var(--ch-profit)'
							: row.skew < -0.3
								? 'var(--ch-loss)'
								: 'var(--ch-warn)'}
					{@const pct = ((Math.abs(row.skew) / runProfitSkewByTimeframe.maxAbs) * 50).toFixed(1)}
					<div class="flex items-center gap-2 text-[10px]">
						<span class="w-10 font-mono text-muted-foreground">{row.tf}</span>
						<div class="relative flex h-3 flex-1 items-center">
							<div class="absolute left-1/2 h-full w-px bg-border opacity-40"></div>
							{#if row.skew >= 0}
								<div
									class="absolute h-full rounded-r"
									style="left:50%; width:{pct}%; background:{color}"
								></div>
							{:else}
								<div
									class="absolute h-full rounded-l"
									style="right:50%; width:{pct}%; background:{color}"
								></div>
							{/if}
						</div>
						<span class="w-14 text-right font-mono" style="color:{color}"
							>{row.skew.toFixed(2)}</span
						>
						<span class="w-10 text-right text-[9px] text-muted-foreground">n={row.count}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Positive skew = fat right tail · TFs with negative skew carry tail-risk · use alongside
				max_drawdown for full risk picture
			</p>
		</section>
	{/if}

	{#if runTopProfitByPairs}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit by Trading Pair
			</h3>
			<div class="space-y-1">
				{#each runTopProfitByPairs.rows as row, _i (_i)}
					{@const pct = ((Math.max(0, row.avg) / runTopProfitByPairs.maxAvg) * 100).toFixed(1)}
					{@const color = row.avg >= 0 ? 'var(--ch-profit-strong)' : 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-20 shrink-0 truncate text-[9px] text-muted-foreground">{row.pair}</span>
						<div class="relative h-3 flex-1 rounded bg-muted/30">
							<div
								class="absolute top-0 left-0 h-full rounded"
								style="width:{pct}%; background:{color}"
							></div>
						</div>
						<span class="w-14 text-right font-mono text-[9px]" style="color:{color}"
							>{row.avg.toFixed(2)}%</span
						>
						<span class="w-10 text-right text-[9px] text-muted-foreground">n={row.count}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Avg backtest profit % across all runs including the pair · pairs with high n are more
				statistically reliable
			</p>
		</section>
	{/if}

	{#if runSortinoRanking}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Sortino by Strategy
			</h3>
			<div class="space-y-1">
				{#each runSortinoRanking.rows as row, _i (_i)}
					{@const pct = ((Math.max(0, row.sortino) / runSortinoRanking.maxAbs) * 100).toFixed(1)}
					{@const color =
						row.sortino >= 2
							? 'var(--ch-profit-strong)'
							: row.sortino >= 1
								? 'var(--ch-violet)'
								: row.sortino >= 0
									? 'var(--ch-warn)'
									: 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-32 shrink-0 truncate text-[9px] text-muted-foreground"
							>{row.strategy}</span
						>
						<div class="relative h-3 flex-1 rounded bg-muted/30">
							<div
								class="absolute top-0 left-0 h-full rounded"
								style="width:{pct}%; background:{color}"
							></div>
						</div>
						<span class="w-14 text-right font-mono text-[9px]" style="color:{color}"
							>{row.sortino.toFixed(2)}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Best Sortino ratio per strategy · ≥2 = excellent · 1–2 = good · &lt;0 = net negative ·
				Sortino penalizes only downside volatility
			</p>
		</section>
	{/if}

	{#if runProfitVsDrawdownScatter}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Profit vs Max Drawdown — All Runs
			</h3>
			<svg
				viewBox="0 0 {runProfitVsDrawdownScatter.W} {runProfitVsDrawdownScatter.H}"
				class="w-full"
				style="height:140px"
			>
				{#if runProfitVsDrawdownScatter.zeroY !== null}
					<line
						x1="0"
						y1={runProfitVsDrawdownScatter.zeroY}
						x2={runProfitVsDrawdownScatter.W}
						y2={runProfitVsDrawdownScatter.zeroY}
						stroke="var(--ch-axis-muted)"
						stroke-width="1"
						stroke-dasharray="3,3"
					/>
				{/if}
				<line
					x1={(runProfitVsDrawdownScatter.W * 20) / 100}
					y1="0"
					x2={(runProfitVsDrawdownScatter.W * 20) / 100}
					y2={runProfitVsDrawdownScatter.H}
					stroke="var(--ch-profit-light)"
					stroke-width="1"
					stroke-dasharray="3,3"
				/>
				{#each runProfitVsDrawdownScatter.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="2" fill={d.color} opacity="0.75" />
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{runProfitVsDrawdownScatter.total} runs · {runProfitVsDrawdownScatter.ideal} in ideal zone (profit&gt;0
				&amp; DD&lt;20%) · x = drawdown [0–{runProfitVsDrawdownScatter.dMax}%] · y = profit [{runProfitVsDrawdownScatter.pMin}–{runProfitVsDrawdownScatter.pMax}%]
				· color = timeframe
			</p>
		</section>
	{/if}

	{#if runAvgTradeCountByTF}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Trade Count per Timeframe
			</h3>
			<svg
				viewBox="0 0 {runAvgTradeCountByTF.W} {runAvgTradeCountByTF.H}"
				class="w-full"
				style="height:80px"
			>
				{#each runAvgTradeCountByTF.rows as row, i (i)}
					{@const x =
						runAvgTradeCountByTF.PAD +
						i *
							((runAvgTradeCountByTF.W - runAvgTradeCountByTF.PAD * 2) /
								runAvgTradeCountByTF.rows.length)}
					{@const barH = Math.max(
						2,
						(row.avgTrades / runAvgTradeCountByTF.maxTrades) *
							(runAvgTradeCountByTF.H - runAvgTradeCountByTF.PAD * 2 - 12)
					)}
					{@const color = row.avgProfit >= 0 ? 'var(--ch-violet)' : 'var(--ch-loss)'}
					<rect
						{x}
						y={runAvgTradeCountByTF.H - 12 - barH}
						width={runAvgTradeCountByTF.barW}
						height={barH}
						rx="2"
						fill={color}
					/>
					<text
						x={x + runAvgTradeCountByTF.barW / 2}
						y={runAvgTradeCountByTF.H - 2}
						text-anchor="middle"
						font-size="8"
						fill="var(--ch-axis-strong)">{row.tf}</text
					>
					<text
						x={x + runAvgTradeCountByTF.barW / 2}
						y={runAvgTradeCountByTF.H - 14 - barH}
						text-anchor="middle"
						font-size="7"
						fill={color}>{row.avgTrades.toFixed(0)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg total_trades per run per timeframe · indigo = positive avg profit · red = negative ·
				shorter TF = more trades · useful for slippage estimation
			</p>
		</section>
	{/if}

	{#if runHoldingTimeVsProfit}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Holding Time vs Profit Scatter ({runHoldingTimeVsProfit.count} runs)
			</h3>
			<svg
				viewBox="0 0 {runHoldingTimeVsProfit.W} {runHoldingTimeVsProfit.H}"
				class="w-full"
				style="height:100px"
			>
				{#if runHoldingTimeVsProfit.zeroY !== null}
					<line
						x1="0"
						y1={runHoldingTimeVsProfit.zeroY}
						x2={runHoldingTimeVsProfit.W}
						y2={runHoldingTimeVsProfit.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="3,3"
					/>
				{/if}
				{#each runHoldingTimeVsProfit.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="2.5" fill={d.color} stroke="none" />
				{/each}
			</svg>
			<div class="mt-1 flex justify-between text-[9px] text-muted-foreground">
				<span>← short hold</span>
				<span>x=avg holding hrs · y=total profit % · color=timeframe · dashed=zero profit</span>
				<span>long hold →</span>
			</div>
		</section>
	{/if}

	{#if runProfitFactorLeaderboard}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Profit Factor Leaderboard
			</h3>
			<div class="space-y-1.5">
				{#each runProfitFactorLeaderboard.rows as row, i (i)}
					{@const pct = ((row.pf / runProfitFactorLeaderboard.maxPF) * 100).toFixed(1)}
					{@const color =
						row.pf >= 2
							? 'var(--ch-profit)'
							: row.pf >= 1.5
								? 'var(--ch-violet)'
								: 'var(--ch-warn)'}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right text-[9px] text-muted-foreground">{i + 1}.</span>
						<span class="w-36 truncate text-[9px] text-muted-foreground">{row.strategy}</span>
						<div class="h-3 flex-1 overflow-hidden rounded bg-muted/20">
							<div class="h-full rounded" style="width:{pct}%; background:{color}"></div>
						</div>
						<span class="w-12 text-right font-mono text-[10px]" style="color:{color}"
							>{row.pf.toFixed(2)}</span
						>
						<span class="w-8 text-right text-[9px] text-muted-foreground">{row.tf}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Best profit factor per strategy across all runs · green ≥ 2 · indigo ≥ 1.5 · yellow &lt; 1.5
				· PF = gross profit / gross loss
			</p>
		</section>
	{/if}

	{#if runSortinoLeaderboard}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Sortino Ratio Leaderboard
			</h3>
			<div class="space-y-1.5">
				{#each runSortinoLeaderboard.rows as row, i (i)}
					{@const pct = ((row.sortino / runSortinoLeaderboard.maxSortino) * 100).toFixed(1)}
					{@const color =
						row.sortino >= 3
							? 'var(--ch-profit)'
							: row.sortino >= 1.5
								? 'var(--ch-violet)'
								: 'var(--ch-warn)'}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right text-[9px] text-muted-foreground">{i + 1}.</span>
						<span class="w-36 truncate text-[9px] text-muted-foreground">{row.strategy}</span>
						<div class="h-3 flex-1 overflow-hidden rounded bg-muted/20">
							<div class="h-full rounded" style="width:{pct}%; background:{color}"></div>
						</div>
						<span class="w-12 text-right font-mono text-[10px]" style="color:{color}"
							>{row.sortino.toFixed(2)}</span
						>
						<span class="w-8 text-right text-[9px] text-muted-foreground">{row.tf}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Best Sortino ratio per strategy · green ≥ 3 · indigo ≥ 1.5 · yellow &lt; 1.5 · Sortino
				penalises only downside volatility unlike Sharpe
			</p>
		</section>
	{/if}

	{#if runWinRateHistogram}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win Rate Distribution Across Runs
			</h3>
			<svg
				viewBox="0 0 {runWinRateHistogram.W} {runWinRateHistogram.H}"
				class="w-full"
				style="height:75px"
			>
				{#each runWinRateHistogram.counts as b, i (i)}
					{@const x = runWinRateHistogram.PAD + i * (runWinRateHistogram.barW + 1)}
					{@const barH = Math.max(
						1,
						(b.count / runWinRateHistogram.maxCount) *
							(runWinRateHistogram.H - runWinRateHistogram.PAD * 2 - 10)
					)}
					{@const color =
						b.lo >= 55 ? 'var(--ch-profit)' : b.lo >= 45 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<rect
						{x}
						y={runWinRateHistogram.H - 10 - barH}
						width={runWinRateHistogram.barW}
						height={barH}
						rx="1"
						fill={color}
					/>
				{/each}
				<text
					x={runWinRateHistogram.PAD}
					y={runWinRateHistogram.H - 1}
					font-size="7"
					fill="var(--ch-axis)">{runWinRateHistogram.mn}%</text
				>
				<text
					x={runWinRateHistogram.W - runWinRateHistogram.PAD}
					y={runWinRateHistogram.H - 1}
					text-anchor="end"
					font-size="7"
					fill="var(--ch-axis)">{runWinRateHistogram.mx}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{runWinRateHistogram.total} runs · avg win rate {runWinRateHistogram.avg}% · green ≥55% ·
				yellow 45–55% · red &lt;45% · shape reveals optimizer bias
			</p>
		</section>
	{/if}

	{#if runProfitDistribution}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Total Profit % Distribution Across Runs
			</h3>
			<svg
				viewBox="0 0 {runProfitDistribution.W} {runProfitDistribution.H}"
				class="w-full"
				style="height:75px"
			>
				{#each runProfitDistribution.counts as b, i (i)}
					{@const x = runProfitDistribution.PAD + i * (runProfitDistribution.barW + 1)}
					{@const barH = Math.max(
						1,
						(b.count / runProfitDistribution.maxCount) *
							(runProfitDistribution.H - runProfitDistribution.PAD * 2 - 10)
					)}
					{@const color = b.lo >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					<rect
						{x}
						y={runProfitDistribution.H - 10 - barH}
						width={runProfitDistribution.barW}
						height={barH}
						rx="1"
						fill={color}
					/>
				{/each}
				<text
					x={runProfitDistribution.PAD}
					y={runProfitDistribution.H - 1}
					font-size="7"
					fill="var(--ch-axis)">{runProfitDistribution.mn}%</text
				>
				<text
					x={runProfitDistribution.W - runProfitDistribution.PAD}
					y={runProfitDistribution.H - 1}
					text-anchor="end"
					font-size="7"
					fill="var(--ch-axis)">{runProfitDistribution.mx}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{runProfitDistribution.total} runs · avg {runProfitDistribution.avg}% · green = profitable
				bins · red = losing bins · reveals overall shape of strategy profitability
			</p>
		</section>
	{/if}

	{#if runMaxDrawdownByStrategy}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Max Drawdown by Strategy (lower = better)
			</h3>
			<svg
				viewBox="0 0 {runMaxDrawdownByStrategy.W} {runMaxDrawdownByStrategy.H}"
				class="w-full"
				style="height:{runMaxDrawdownByStrategy.H}px"
			>
				{#each runMaxDrawdownByStrategy.rows as row, i (i)}
					{@const cy = runMaxDrawdownByStrategy.PAD + i * 16 + 8}
					{@const bw =
						(row.avg / runMaxDrawdownByStrategy.maxDD) * runMaxDrawdownByStrategy.barMaxW}
					{@const color =
						row.avg <= 10
							? 'var(--ch-profit)'
							: row.avg <= 25
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					<rect
						x={runMaxDrawdownByStrategy.PAD + 82}
						y={cy - 5}
						width={bw}
						height={10}
						rx="1"
						fill={color}
					/>
					<text
						x={runMaxDrawdownByStrategy.PAD + 80}
						y={cy + 3.5}
						text-anchor="end"
						font-size="7"
						fill="var(--ch-axis-strong)">{row.strategy}</text
					>
					<text x={runMaxDrawdownByStrategy.PAD + 84 + bw} y={cy + 3.5} font-size="7" fill={color}
						>{row.avg.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg max drawdown across all runs per strategy · green ≤10% · yellow 10–25% · red &gt;25% ·
				sorted best-to-worst · identifies which strategies protect capital most
			</p>
		</section>
	{/if}

	{#if runTimeframePassRate}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Profitable Run Rate by Timeframe
			</h3>
			<svg
				viewBox="0 0 {runTimeframePassRate.W} {runTimeframePassRate.H}"
				class="w-full"
				style="height:75px"
			>
				{#each runTimeframePassRate.rows as row, i (i)}
					{@const x = runTimeframePassRate.PAD + i * (runTimeframePassRate.barW + 3)}
					{@const barH = Math.max(
						2,
						(row.rate / 100) * (runTimeframePassRate.H - runTimeframePassRate.PAD * 2 - 12)
					)}
					{@const color =
						row.rate >= 60
							? 'var(--ch-profit)'
							: row.rate >= 40
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					<rect
						{x}
						y={runTimeframePassRate.H - 12 - barH}
						width={runTimeframePassRate.barW}
						height={barH}
						rx="2"
						fill={color}
					/>
					<text
						x={x + runTimeframePassRate.barW / 2}
						y={runTimeframePassRate.H - 1}
						text-anchor="middle"
						font-size="7.5"
						fill="var(--ch-axis)">{row.tf}</text
					>
					<text
						x={x + runTimeframePassRate.barW / 2}
						y={runTimeframePassRate.H - 14 - barH}
						text-anchor="middle"
						font-size="6.5"
						fill={color}>{row.rate.toFixed(0)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				% of runs with positive total profit per timeframe · green ≥60% · yellow 40–60% · red
				&lt;40% · reveals which timeframes consistently produce profitable results
			</p>
		</section>
	{/if}

	{#if runCalmarLeaderboard}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Top Strategies by Median Calmar Ratio
			</h3>
			<div class="space-y-1.5">
				{#each runCalmarLeaderboard.rows as row, i (i)}
					{@const pct = ((row.calmar / runCalmarLeaderboard.maxCalmar) * 100).toFixed(1)}
					{@const color =
						row.calmar >= 2
							? 'var(--ch-profit-strong)'
							: row.calmar >= 1
								? 'var(--ch-violet)'
								: row.calmar >= 0
									? 'var(--ch-warn)'
									: 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right text-[9px] text-muted-foreground">{i + 1}.</span>
						<span class="w-36 truncate text-[9px] text-muted-foreground">{row.strategy}</span>
						<div class="h-3 flex-1 overflow-hidden rounded bg-muted/20">
							<div class="h-full rounded" style="width:{pct}%; background:{color}"></div>
						</div>
						<span class="w-10 text-right font-mono text-[10px]" style="color:{color}"
							>{row.calmar.toFixed(2)}</span
						>
						<span class="w-8 text-right text-[9px] text-muted-foreground">{row.count}r</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Median Calmar = annualized return ÷ max drawdown · green ≥2 · indigo ≥1 · yellow 0–1 ·
				identifies strategies with best risk-adjusted returns
			</p>
		</section>
	{/if}

	{#if runStrategyWinLossProfile}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Strategy Win/Loss Run Profile
			</h3>
			<div class="space-y-1.5">
				{#each runStrategyWinLossProfile.rows as row, _i (_i)}
					{@const winW = ((row.wins / row.total) * 100).toFixed(1)}
					{@const lossW = ((row.losses / row.total) * 100).toFixed(1)}
					{@const profitColor = row.avgProfit >= 0 ? 'var(--ch-profit-strong)' : 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-36 truncate text-[9px] text-muted-foreground">{row.strategy}</span>
						<div class="flex h-3 flex-1 overflow-hidden rounded bg-muted/10">
							<div class="h-full" style="width:{winW}%; background:var(--ch-profit)"></div>
							<div class="h-full" style="width:{lossW}%; background:var(--ch-loss-light)"></div>
						</div>
						<span class="w-10 text-right font-mono text-[10px]" style="color:{profitColor}"
							>{row.wr.toFixed(0)}%WR</span
						>
						<span class="w-8 text-right text-[9px] text-muted-foreground">{row.total}r</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Green=profitable runs · red=losing runs · sorted by win rate · strategies with mostly green
				bars are consistently generating positive backtest results
			</p>
		</section>
	{/if}
	{#if runSortinoVsCalmarScatter}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Sortino vs Calmar Scatter ({runSortinoVsCalmarScatter.count} runs)
			</h3>
			<svg
				viewBox="0 0 {runSortinoVsCalmarScatter.W} {runSortinoVsCalmarScatter.H}"
				class="w-full"
				style="height:95px"
			>
				{#each runSortinoVsCalmarScatter.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="2.5" fill={d.color} />
				{/each}
				<text
					x={runSortinoVsCalmarScatter.PAD}
					y={runSortinoVsCalmarScatter.H - 2}
					font-size="6.5"
					fill="var(--ch-axis-muted)">Sortino {runSortinoVsCalmarScatter.sMin}</text
				>
				<text
					x={runSortinoVsCalmarScatter.W - runSortinoVsCalmarScatter.PAD}
					y={runSortinoVsCalmarScatter.H - 2}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-axis-muted)">{runSortinoVsCalmarScatter.sMax}</text
				>
				<text
					x={runSortinoVsCalmarScatter.PAD - 2}
					y={runSortinoVsCalmarScatter.PAD + 4}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{runSortinoVsCalmarScatter.cMax}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				x=Sortino · y=Calmar · green=profitable run · red=losing · top-right = best
				downside-adjusted and drawdown-adjusted quality simultaneously
			</p>
		</section>
	{/if}
	{#if runProfitMonthlyHeatmap}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Strategy Profit Heatmap by Month (top {runProfitMonthlyHeatmap.topStrats.length})
			</h3>
			<svg
				viewBox="0 0 {runProfitMonthlyHeatmap.W} {runProfitMonthlyHeatmap.H}"
				class="w-full"
				style="height:{runProfitMonthlyHeatmap.H}px"
			>
				{#each runProfitMonthlyHeatmap.topStrats as strat, si (si)}
					<text
						x={runProfitMonthlyHeatmap.PAD - 2}
						y={runProfitMonthlyHeatmap.PAD +
							si * (runProfitMonthlyHeatmap.cH + 2) +
							runProfitMonthlyHeatmap.cH -
							4}
						text-anchor="end"
						font-size="7"
						fill="var(--ch-axis)">{strat}</text
					>
				{/each}
				{#each runProfitMonthlyHeatmap.months as mo, mi (mi)}
					<text
						x={runProfitMonthlyHeatmap.PAD +
							mi * (runProfitMonthlyHeatmap.cW + 2) +
							runProfitMonthlyHeatmap.cW / 2}
						y={runProfitMonthlyHeatmap.PAD - 3}
						text-anchor="middle"
						font-size="7"
						fill="var(--ch-axis)">{mo}</text
					>
				{/each}
				{#each runProfitMonthlyHeatmap.cells as c, _i (_i)}
					{@const x = runProfitMonthlyHeatmap.PAD + c.mi * (runProfitMonthlyHeatmap.cW + 2)}
					{@const y = runProfitMonthlyHeatmap.PAD + c.si * (runProfitMonthlyHeatmap.cH + 2)}
					{@const alpha =
						c.avg !== null
							? Math.min(0.85, (Math.abs(c.avg) / runProfitMonthlyHeatmap.mx) * 0.85 + 0.1)
							: 0.04}
					{@const fill =
						c.avg === null
							? 'var(--ch-axis-faint)'
							: c.avg >= 0
								? `rgba(34,197,94,${alpha})`
								: `rgba(239,68,68,${alpha})`}
					<rect
						{x}
						{y}
						width={runProfitMonthlyHeatmap.cW}
						height={runProfitMonthlyHeatmap.cH}
						rx="2"
						{fill}
					/>
					{#if c.avg !== null}
						<text
							x={x + runProfitMonthlyHeatmap.cW / 2}
							y={y + runProfitMonthlyHeatmap.cH - 4}
							text-anchor="middle"
							font-size="7"
							fill="var(--ch-axis-strong)">{c.avg >= 0 ? '+' : ''}{c.avg.toFixed(0)}%</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Avg run profit % per strategy × month · green=positive · red=negative · darker=stronger
				signal · reveals seasonal patterns per strategy
			</p>
		</section>
	{/if}
	{#if runDurationVsProfit}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Trade Duration vs Total Profit ({runDurationVsProfit.count} runs)
			</h3>
			<svg
				viewBox="0 0 {runDurationVsProfit.W} {runDurationVsProfit.H}"
				class="w-full"
				style="height:95px"
			>
				<line
					x1={runDurationVsProfit.PAD}
					y1={runDurationVsProfit.zeroY}
					x2={runDurationVsProfit.W - runDurationVsProfit.PAD}
					y2={runDurationVsProfit.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each runDurationVsProfit.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="2.5" fill={d.color} />
				{/each}
				<text
					x={runDurationVsProfit.PAD}
					y={runDurationVsProfit.H - 2}
					font-size="6.5"
					fill="var(--ch-axis-muted)">{runDurationVsProfit.dMin}h</text
				>
				<text
					x={runDurationVsProfit.W - runDurationVsProfit.PAD}
					y={runDurationVsProfit.H - 2}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-axis-muted)">{runDurationVsProfit.dMax}h</text
				>
				<text
					x={runDurationVsProfit.PAD}
					y={runDurationVsProfit.PAD + 4}
					font-size="6"
					fill="var(--ch-axis-muted)">profit {runDurationVsProfit.pMax}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				x=avg trade duration (hours) · y=total profit % · green≥10% · yellow≥0% · red=losing ·
				reveals whether shorter or longer-duration trades correlate with better performance
			</p>
		</section>
	{/if}
	{#if runSharpeLeaderboard}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Sharpe Ratio by Strategy (top 8)
			</h3>
			<svg
				viewBox="0 0 {runSharpeLeaderboard.W} {runSharpeLeaderboard.H}"
				class="w-full"
				style="height:{runSharpeLeaderboard.H}px"
			>
				{#each runSharpeLeaderboard.rows as row, i (i)}
					{@const y = i * 16 + 2}
					{@const bw = Math.max(
						2,
						(Math.abs(row.avg) / runSharpeLeaderboard.maxAbs) * runSharpeLeaderboard.barMaxW
					)}
					{@const color =
						row.avg >= 1 ? 'var(--ch-profit)' : row.avg >= 0 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<text x="0" y={y + 9} font-size="7" fill="var(--ch-axis-strong)">{row.strat}</text>
					<rect x="125" {y} width={bw} height="11" rx="2" fill={color} />
					<text x={125 + bw + 3} y={y + 9} font-size="7" fill={color}
						>{row.avg >= 0 ? '+' : ''}{row.avg.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Average Sharpe ratio per strategy (≥2 runs) · green≥1 · yellow≥0 · red=negative · higher
				Sharpe = better risk-adjusted return consistency
			</p>
		</section>
	{/if}
	{#if runWinRateIQRByTimeframe}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win Rate Distribution by Timeframe (p25–p75 IQR)
			</h3>
			<svg
				viewBox="0 0 {runWinRateIQRByTimeframe.W} {runWinRateIQRByTimeframe.H}"
				class="w-full"
				style="height:{runWinRateIQRByTimeframe.H}px"
			>
				<line
					x1={runWinRateIQRByTimeframe.PAD + runWinRateIQRByTimeframe.barMaxW * 0.5}
					y1="0"
					x2={runWinRateIQRByTimeframe.PAD + runWinRateIQRByTimeframe.barMaxW * 0.5}
					y2={runWinRateIQRByTimeframe.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="2,2"
				/>
				{#each runWinRateIQRByTimeframe.rows as row, i (i)}
					{@const y = i * 18 + 2}
					{@const xMed =
						runWinRateIQRByTimeframe.PAD + (row.med / 100) * runWinRateIQRByTimeframe.barMaxW}
					{@const xP25 =
						runWinRateIQRByTimeframe.PAD + (row.p25 / 100) * runWinRateIQRByTimeframe.barMaxW}
					{@const xP75 =
						runWinRateIQRByTimeframe.PAD + (row.p75 / 100) * runWinRateIQRByTimeframe.barMaxW}
					{@const color =
						row.med >= 55
							? 'var(--ch-profit)'
							: row.med >= 45
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					<text x="0" y={y + 11} font-size="7" fill="var(--ch-axis-strong)">{row.tf}</text>
					<rect
						x={xP25}
						{y}
						width={Math.max(2, xP75 - xP25)}
						height="12"
						rx="2"
						fill={color}
						opacity="0.35"
					/>
					<line x1={xMed} y1={y} x2={xMed} y2={y + 12} stroke={color} stroke-width="2" />
					<text x={xMed + 2} y={y + 9} font-size="6" fill={color}>{row.med.toFixed(0)}%</text>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Median win rate (vertical bar) ± IQR box per timeframe · green≥55% · yellow≥45% · red&lt;45%
				· wider box = more variable win rate outcomes
			</p>
		</section>
	{/if}
	{#if runProfitByTradeCountBucket}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit by Trade Count Range
			</h3>
			<svg
				viewBox="0 0 {runProfitByTradeCountBucket.W} {runProfitByTradeCountBucket.H}"
				class="w-full"
				style="height:72px"
			>
				<line
					x1={runProfitByTradeCountBucket.PAD}
					y1={runProfitByTradeCountBucket.midY}
					x2={runProfitByTradeCountBucket.W - runProfitByTradeCountBucket.PAD}
					y2={runProfitByTradeCountBucket.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each runProfitByTradeCountBucket.rows as row, i (i)}
					{@const x = runProfitByTradeCountBucket.PAD + i * (runProfitByTradeCountBucket.barW + 3)}
					{@const bh = Math.max(
						2,
						(Math.abs(row.avg) / runProfitByTradeCountBucket.maxAbs) *
							(runProfitByTradeCountBucket.midY - runProfitByTradeCountBucket.PAD)
					)}
					{@const color = row.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					<rect
						{x}
						y={row.avg >= 0
							? runProfitByTradeCountBucket.midY - bh
							: runProfitByTradeCountBucket.midY}
						width={runProfitByTradeCountBucket.barW}
						height={bh}
						rx="1"
						fill={color}
					/>
					<text
						x={x + runProfitByTradeCountBucket.barW / 2}
						y={runProfitByTradeCountBucket.H - 1}
						text-anchor="middle"
						font-size="6"
						fill="var(--ch-axis-muted)">{row.label}</text
					>
					<text
						x={x + runProfitByTradeCountBucket.barW / 2}
						y={row.avg >= 0
							? runProfitByTradeCountBucket.midY - bh - 2
							: runProfitByTradeCountBucket.midY + bh + 8}
						text-anchor="middle"
						font-size="5.5"
						fill={color}>{row.avg >= 0 ? '+' : ''}{row.avg.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg total profit % grouped by number of trades · reveals whether higher-frequency or
				lower-frequency strategies perform better · x-labels = trade count range
			</p>
		</section>
	{/if}

	{#if runSharpeVsSortinoArchiveScatter}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Sharpe vs Sortino — Archive Runs ({runSharpeVsSortinoArchiveScatter.count} runs)
			</h3>
			<svg
				viewBox="0 0 {runSharpeVsSortinoArchiveScatter.W} {runSharpeVsSortinoArchiveScatter.H}"
				class="w-full"
				style="height:92px"
			>
				<line
					x1={runSharpeVsSortinoArchiveScatter.zeroX}
					y1={runSharpeVsSortinoArchiveScatter.PAD}
					x2={runSharpeVsSortinoArchiveScatter.zeroX}
					y2={runSharpeVsSortinoArchiveScatter.H - runSharpeVsSortinoArchiveScatter.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				<line
					x1={runSharpeVsSortinoArchiveScatter.PAD}
					y1={runSharpeVsSortinoArchiveScatter.zeroY}
					x2={runSharpeVsSortinoArchiveScatter.W - runSharpeVsSortinoArchiveScatter.PAD}
					y2={runSharpeVsSortinoArchiveScatter.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each runSharpeVsSortinoArchiveScatter.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="2.5" fill={d.color} />
				{/each}
				<text
					x={runSharpeVsSortinoArchiveScatter.PAD}
					y={runSharpeVsSortinoArchiveScatter.H - 2}
					font-size="6.5"
					fill="var(--ch-axis-muted)">Sharpe {runSharpeVsSortinoArchiveScatter.sMin}</text
				>
				<text
					x={runSharpeVsSortinoArchiveScatter.W - runSharpeVsSortinoArchiveScatter.PAD}
					y={runSharpeVsSortinoArchiveScatter.H - 2}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-axis-muted)">{runSharpeVsSortinoArchiveScatter.sMax}</text
				>
				<text
					x={runSharpeVsSortinoArchiveScatter.PAD}
					y={runSharpeVsSortinoArchiveScatter.PAD + 5}
					font-size="6"
					fill="var(--ch-axis-muted)">Sortino {runSharpeVsSortinoArchiveScatter.soMax}</text
				>
				<text
					x={runSharpeVsSortinoArchiveScatter.PAD}
					y={runSharpeVsSortinoArchiveScatter.H - runSharpeVsSortinoArchiveScatter.PAD + 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{runSharpeVsSortinoArchiveScatter.soMin}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				x=Sharpe · y=Sortino · green=profit≥10% · yellow≥0% · red=loss · crosshairs at zero ·
				top-right = best risk-adjusted outcomes on both axes
			</p>
		</section>
	{/if}

	{#if runMonthlyRunCount}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Backtest Runs per Month ({runMonthlyRunCount.total} total)
			</h3>
			<svg
				viewBox="0 0 {runMonthlyRunCount.W} {runMonthlyRunCount.H}"
				class="w-full"
				style="height:72px"
			>
				{#each runMonthlyRunCount.bars as bar, i (i)}
					{@const y = runMonthlyRunCount.H - runMonthlyRunCount.PAD - 8 - bar.h}
					<rect
						x={bar.x}
						{y}
						width={runMonthlyRunCount.bw}
						height={bar.h}
						rx="2"
						fill={bar.color}
					/>
					{#if bar.count > 0}
						<text
							x={bar.x + runMonthlyRunCount.bw / 2}
							y={y - 2}
							text-anchor="middle"
							font-size="5.5"
							fill="var(--ch-axis)">{bar.count}</text
						>
					{/if}
					{#if i % Math.max(1, Math.floor(runMonthlyRunCount.bars.length / 6)) === 0}
						<text
							x={bar.x + runMonthlyRunCount.bw / 2}
							y={runMonthlyRunCount.H - 1}
							text-anchor="middle"
							font-size="5.5"
							fill="var(--ch-axis-muted)">{bar.mo}</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Number of backtest runs archived per month · darker = more active month · reveals research
				cadence over time
			</p>
		</section>
	{/if}

	{#if runAvgProfitByTimeframe}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit % by Timeframe
			</h3>
			<svg
				viewBox="0 0 {runAvgProfitByTimeframe.W} {runAvgProfitByTimeframe.H}"
				class="w-full"
				style="height:{runAvgProfitByTimeframe.H}px"
			>
				<line
					x1={runAvgProfitByTimeframe.zeroX}
					y1="0"
					x2={runAvgProfitByTimeframe.zeroX}
					y2={runAvgProfitByTimeframe.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each runAvgProfitByTimeframe.rows as row, i (i)}
					{@const y = i * 18 + 4}
					{@const bw = Math.max(
						2,
						(Math.abs(row.avg) / runAvgProfitByTimeframe.maxAbs) *
							(runAvgProfitByTimeframe.barMaxW / 2)
					)}
					{@const x =
						row.avg >= 0 ? runAvgProfitByTimeframe.zeroX : runAvgProfitByTimeframe.zeroX - bw}
					{@const color =
						row.avg >= 5 ? 'var(--ch-profit)' : row.avg >= 0 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<text
						x={runAvgProfitByTimeframe.PAD}
						y={y + 11}
						font-size="8"
						fill="var(--ch-axis-strong)">{row.tf}</text
					>
					<rect {x} y={y + 2} width={bw} height="12" rx="2" fill={color} />
					<text
						x={row.avg >= 0
							? runAvgProfitByTimeframe.zeroX + bw + 3
							: runAvgProfitByTimeframe.zeroX - bw - 3}
						y={y + 11}
						text-anchor={row.avg >= 0 ? 'start' : 'end'}
						font-size="7"
						fill={color}>{row.avg >= 0 ? '+' : ''}{row.avg.toFixed(1)}%</text
					>
					<text
						x={runAvgProfitByTimeframe.W - 2}
						y={y + 11}
						text-anchor="end"
						font-size="6"
						fill="var(--ch-axis-muted)">{row.count}r</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Average total profit % per timeframe · diverging bars from zero · green=positive avg ·
				red=negative avg · count = number of runs
			</p>
		</section>
	{/if}
	{#if runTopStrategiesByAvgProfit}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Top Strategies by Avg Profit
			</h3>
			<svg
				viewBox="0 0 {runTopStrategiesByAvgProfit.W} {runTopStrategiesByAvgProfit.H}"
				class="w-full"
				style="height:{runTopStrategiesByAvgProfit.H}px"
			>
				<line
					x1={runTopStrategiesByAvgProfit.zeroX}
					y1="0"
					x2={runTopStrategiesByAvgProfit.zeroX}
					y2={runTopStrategiesByAvgProfit.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each runTopStrategiesByAvgProfit.rows as row, i (i)}
					{@const y = i * 16 + 2}
					{@const bw = Math.max(
						2,
						(Math.abs(row.avg) / runTopStrategiesByAvgProfit.maxAbs) *
							(runTopStrategiesByAvgProfit.barMaxW / 2)
					)}
					{@const x =
						row.avg >= 0
							? runTopStrategiesByAvgProfit.zeroX
							: runTopStrategiesByAvgProfit.zeroX - bw}
					{@const color =
						row.avg >= 5 ? 'var(--ch-profit)' : row.avg >= 0 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<text
						x={runTopStrategiesByAvgProfit.PAD}
						y={y + 10}
						font-size="7"
						fill="var(--ch-axis-strong)">{row.strat}</text
					>
					<rect {x} {y} width={bw} height="12" rx="2" fill={color} />
					<text
						x={row.avg >= 0
							? runTopStrategiesByAvgProfit.zeroX + bw + 3
							: runTopStrategiesByAvgProfit.zeroX - bw - 3}
						y={y + 10}
						text-anchor={row.avg >= 0 ? 'start' : 'end'}
						font-size="7"
						fill={color}>{row.avg >= 0 ? '+' : ''}{row.avg.toFixed(1)}%</text
					>
					<text
						x={runTopStrategiesByAvgProfit.W - 2}
						y={y + 10}
						text-anchor="end"
						font-size="6"
						fill="var(--ch-axis-muted)">{row.count}r</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Strategies ranked by avg total profit % across archived backtest runs · diverging from zero
				· green≥5% · yellow≥0% · count=archived runs · reveals most consistently profitable
				strategies
			</p>
		</section>
	{/if}
	{#if runSharpeVsDrawdownScatter}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Sharpe vs Max Drawdown
			</h3>
			<svg
				viewBox="0 0 {runSharpeVsDrawdownScatter.W} {runSharpeVsDrawdownScatter.H}"
				class="w-full"
				style="height:{runSharpeVsDrawdownScatter.H}px"
			>
				<line
					x1={runSharpeVsDrawdownScatter.zeroX}
					y1={runSharpeVsDrawdownScatter.PAD}
					x2={runSharpeVsDrawdownScatter.zeroX}
					y2={runSharpeVsDrawdownScatter.H - runSharpeVsDrawdownScatter.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.8"
					stroke-dasharray="3,2"
				/>
				{#each runSharpeVsDrawdownScatter.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="1.8" fill={d.color} />
				{/each}
				<text
					x={runSharpeVsDrawdownScatter.PAD}
					y={runSharpeVsDrawdownScatter.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">Sharpe {runSharpeVsDrawdownScatter.sMin}</text
				>
				<text
					x={runSharpeVsDrawdownScatter.W - runSharpeVsDrawdownScatter.PAD}
					y={runSharpeVsDrawdownScatter.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{runSharpeVsDrawdownScatter.sMax}</text
				>
				<text
					x={runSharpeVsDrawdownScatter.PAD}
					y={runSharpeVsDrawdownScatter.PAD + 4}
					font-size="6"
					fill="var(--ch-axis-muted)">DD {runSharpeVsDrawdownScatter.ddMax}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				x=Sharpe ratio · y=max drawdown % · green≥1 · yellow≥0 · red&lt;0 · ideal = high Sharpe
				(right) + low drawdown (bottom) · reveals risk-adjusted quality of archived runs
			</p>
		</section>
	{/if}
	{#if runProfitFactorHistogram}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-2 text-xs font-semibold text-foreground">Profit Factor Distribution</h3>
			<svg
				viewBox="0 0 {runProfitFactorHistogram.W} {runProfitFactorHistogram.H}"
				class="w-full"
				style="height:{runProfitFactorHistogram.H}px"
			>
				{#each runProfitFactorHistogram.bars as bar, _i (_i)}
					<rect
						x={bar.x}
						y={runProfitFactorHistogram.H - runProfitFactorHistogram.PAD - bar.h - 12}
						width={runProfitFactorHistogram.bw}
						height={bar.h}
						fill={bar.color}
						rx="1"
					/>
				{/each}
				<line
					x1={runProfitFactorHistogram.x1}
					y1={runProfitFactorHistogram.PAD}
					x2={runProfitFactorHistogram.x1}
					y2={runProfitFactorHistogram.H - runProfitFactorHistogram.PAD - 12}
					stroke="var(--ch-axis-strong)"
					stroke-width="1"
					stroke-dasharray="3,2"
				/>
				<text
					x={runProfitFactorHistogram.PAD}
					y={runProfitFactorHistogram.H - 3}
					font-size="6"
					fill="var(--ch-axis-muted)">0</text
				>
				<text
					x={runProfitFactorHistogram.x1 + 2}
					y={runProfitFactorHistogram.PAD + 8}
					font-size="6"
					fill="var(--ch-axis-strong)">PF=1</text
				>
				<text
					x={runProfitFactorHistogram.W - runProfitFactorHistogram.PAD}
					y={runProfitFactorHistogram.H - 3}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{runProfitFactorHistogram.mx}</text
				>
				<text
					x={runProfitFactorHistogram.W - 2}
					y={runProfitFactorHistogram.PAD + 8}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">n={runProfitFactorHistogram.total}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Profit factor histogram · green≥1 (profitable) · red&lt;1 (unprofitable) · vertical line at
				PF=1 · reveals distribution of run quality across archived backtests
			</p>
		</section>
	{/if}
	{#if runCalmarTimeline}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-2 text-xs font-semibold text-foreground">Avg Calmar Ratio Over Time</h3>
			<svg
				viewBox="0 0 {runCalmarTimeline.W} {runCalmarTimeline.H}"
				class="w-full"
				style="height:{runCalmarTimeline.H}px"
			>
				<polygon points={runCalmarTimeline.area} fill={runCalmarTimeline.fillColor} />
				<line
					x1={runCalmarTimeline.PAD}
					y1={runCalmarTimeline.zeroY}
					x2={runCalmarTimeline.W - runCalmarTimeline.PAD}
					y2={runCalmarTimeline.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				<polyline
					points={runCalmarTimeline.polyline}
					fill="none"
					stroke={runCalmarTimeline.color}
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={runCalmarTimeline.PAD}
					y={runCalmarTimeline.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{runCalmarTimeline.firstMo}</text
				>
				<text
					x={runCalmarTimeline.W - runCalmarTimeline.PAD}
					y={runCalmarTimeline.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{runCalmarTimeline.lastMo}</text
				>
				<text
					x={runCalmarTimeline.W - runCalmarTimeline.PAD}
					y={runCalmarTimeline.PAD + 6}
					text-anchor="end"
					font-size="7"
					fill={runCalmarTimeline.color}>{runCalmarTimeline.lastAvg}</text
				>
				<text
					x={runCalmarTimeline.PAD}
					y={runCalmarTimeline.PAD + 6}
					font-size="6"
					fill="var(--ch-axis-muted)">Calmar</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Monthly avg Calmar ratio of archived backtest runs · green≥1 · yellow≥0 · red&lt;0 · zero
				baseline · reveals trend in capital-efficiency of runs over time
			</p>
		</section>
	{/if}
	{#if runWinRateTFBars}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-2 text-xs font-semibold text-foreground">Avg Win Rate by Timeframe</h3>
			<svg
				viewBox="0 0 {runWinRateTFBars.W} {runWinRateTFBars.H}"
				class="w-full"
				style="height:{runWinRateTFBars.H}px"
			>
				{#each runWinRateTFBars.bars as bar, _i (_i)}
					<rect
						x={bar.x}
						y={runWinRateTFBars.H - runWinRateTFBars.PAD - bar.h - 16}
						width={runWinRateTFBars.bw}
						height={bar.h}
						fill={bar.color}
						rx="1"
					/>
					<text
						x={bar.x + runWinRateTFBars.bw / 2}
						y={runWinRateTFBars.H - runWinRateTFBars.PAD - bar.h - 18}
						text-anchor="middle"
						font-size="6.5"
						fill={bar.color}>{bar.avg.toFixed(1)}%</text
					>
					<text
						x={bar.x + runWinRateTFBars.bw / 2}
						y={runWinRateTFBars.H - 3}
						text-anchor="middle"
						font-size="7"
						fill="var(--ch-axis)">{bar.tf}</text
					>
					<text
						x={bar.x + runWinRateTFBars.bw / 2}
						y={runWinRateTFBars.H - runWinRateTFBars.PAD - 2}
						text-anchor="middle"
						font-size="5.5"
						fill="var(--ch-axis-muted)">{bar.count}r</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg win rate % per timeframe · green≥60% · yellow≥50% · red&lt;50% · count=runs · reveals
				which timeframes tend to produce more winning trades in archived backtests
			</p>
		</section>
	{/if}
	{#if runAvgTradeCountByMonth}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Trade Count per Month
			</h3>
			<svg
				viewBox="0 0 {runAvgTradeCountByMonth.W} {runAvgTradeCountByMonth.H}"
				class="w-full"
				style="height:{runAvgTradeCountByMonth.H}px"
			>
				<polygon points={runAvgTradeCountByMonth.area} fill="var(--ch-violet-light)" />
				<polyline
					points={runAvgTradeCountByMonth.polyline}
					fill="none"
					stroke="var(--ch-violet)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={runAvgTradeCountByMonth.PAD}
					y={runAvgTradeCountByMonth.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{runAvgTradeCountByMonth.firstMo}</text
				>
				<text
					x={runAvgTradeCountByMonth.W - runAvgTradeCountByMonth.PAD}
					y={runAvgTradeCountByMonth.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{runAvgTradeCountByMonth.lastMo}</text
				>
				<text
					x={runAvgTradeCountByMonth.PAD}
					y={runAvgTradeCountByMonth.PAD + 6}
					font-size="7"
					fill="var(--ch-violet-strong)">{runAvgTradeCountByMonth.maxV}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Monthly avg trade count per backtest run · indigo area · reveals whether strategies are
				configured to trade more or fewer times over the archive history
			</p>
		</section>
	{/if}
	{#if runDrawdownHistogram}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Max Drawdown % Distribution
			</h3>
			<svg
				viewBox="0 0 {runDrawdownHistogram.W} {runDrawdownHistogram.H}"
				class="w-full"
				style="height:{runDrawdownHistogram.H}px"
			>
				{#each runDrawdownHistogram.buckets as b, i (i)}
					{@const x = runDrawdownHistogram.PAD + i * (runDrawdownHistogram.bw + 1)}
					{@const bh = Math.max(
						2,
						(b.count / runDrawdownHistogram.maxC) *
							(runDrawdownHistogram.H - runDrawdownHistogram.PAD * 2 - 10)
					)}
					{@const y = runDrawdownHistogram.H - runDrawdownHistogram.PAD - 10 - bh}
					{@const col =
						b.lo < 10 ? 'var(--ch-profit)' : b.lo < 25 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<rect {x} {y} width={runDrawdownHistogram.bw} height={bh} rx="1" fill={col} />
				{/each}
				<text
					x={runDrawdownHistogram.PAD}
					y={runDrawdownHistogram.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">0%</text
				>
				<text
					x={runDrawdownHistogram.W - runDrawdownHistogram.PAD}
					y={runDrawdownHistogram.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{runDrawdownHistogram.maxV}%</text
				>
				<text
					x={runDrawdownHistogram.W / 2}
					y={runDrawdownHistogram.H - 2}
					text-anchor="middle"
					font-size="6"
					fill="var(--ch-axis-muted)">n={runDrawdownHistogram.total}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Distribution of max drawdown % across archived runs · green&lt;10% · yellow&lt;25% · red≥25%
				· reveals overall risk profile of the strategy archive
			</p>
		</section>
	{/if}
	{#if runAvgProfitByTF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit % by Timeframe
			</h3>
			<svg
				viewBox="0 0 {runAvgProfitByTF.W} {runAvgProfitByTF.H}"
				class="w-full"
				style="height:{runAvgProfitByTF.H}px"
			>
				<line
					x1={runAvgProfitByTF.PAD}
					y1={runAvgProfitByTF.midY}
					x2={runAvgProfitByTF.W - runAvgProfitByTF.PAD}
					y2={runAvgProfitByTF.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each runAvgProfitByTF.rows as row, i (i)}
					{@const x = runAvgProfitByTF.toX(i)}
					{@const bh = runAvgProfitByTF.toH(row.avg)}
					{@const color = row.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					{@const y = row.avg >= 0 ? runAvgProfitByTF.midY - bh : runAvgProfitByTF.midY}
					<rect {x} {y} width={runAvgProfitByTF.bw} height={Math.max(1, bh)} rx="1" fill={color} />
					<text
						x={x + runAvgProfitByTF.bw / 2}
						y={runAvgProfitByTF.H - 3}
						text-anchor="middle"
						font-size="7"
						fill="var(--ch-axis)">{row.tf}</text
					>
					<text
						x={x + runAvgProfitByTF.bw / 2}
						y={row.avg >= 0 ? runAvgProfitByTF.midY - bh - 2 : runAvgProfitByTF.midY + bh + 9}
						text-anchor="middle"
						font-size="6"
						fill={color}>{row.avg.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg total profit % per timeframe across archived runs · green=positive · red=negative ·
				diverging from zero · shows which timeframes tend to produce profitable results
			</p>
		</section>
	{/if}
	{#if runWinRateVsDrawdown}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win Rate vs Max Drawdown Scatter
			</h3>
			<svg
				viewBox="0 0 {runWinRateVsDrawdown.W} {runWinRateVsDrawdown.H}"
				class="w-full"
				style="height:{runWinRateVsDrawdown.H}px"
			>
				<line
					x1={runWinRateVsDrawdown.PAD}
					y1={runWinRateVsDrawdown.PAD}
					x2={runWinRateVsDrawdown.PAD}
					y2={runWinRateVsDrawdown.H - runWinRateVsDrawdown.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				<line
					x1={runWinRateVsDrawdown.PAD}
					y1={runWinRateVsDrawdown.H - runWinRateVsDrawdown.PAD}
					x2={runWinRateVsDrawdown.W - runWinRateVsDrawdown.PAD}
					y2={runWinRateVsDrawdown.H - runWinRateVsDrawdown.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each runWinRateVsDrawdown.pts as p, _i (_i)}
					{@const cx = runWinRateVsDrawdown.toX(p.wr)}
					{@const cy = runWinRateVsDrawdown.toY(p.dd)}
					{@const col = p.wr >= 50 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)'}
					<circle {cx} {cy} r="2" fill={col} />
				{/each}
				<text
					x={runWinRateVsDrawdown.PAD}
					y={runWinRateVsDrawdown.PAD + 7}
					font-size="6"
					fill="var(--ch-axis-muted)">dd {runWinRateVsDrawdown.ddMax}%</text
				>
				<text
					x={runWinRateVsDrawdown.W - runWinRateVsDrawdown.PAD}
					y={runWinRateVsDrawdown.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">wr {runWinRateVsDrawdown.wrMax}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Scatter of win rate % (X) vs max drawdown % (Y) per archived run · green=WR≥50% ·
				red=WR&lt;50% · ideal cluster is right-bottom: high win rate with low drawdown
			</p>
		</section>
	{/if}
	{#if runCalmarByPairCount}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Calmar Ratio by Pair Count (buckets of 5)
			</h3>
			<svg
				viewBox="0 0 {runCalmarByPairCount.W} {runCalmarByPairCount.H}"
				class="w-full"
				style="height:{runCalmarByPairCount.H}px"
			>
				<line
					x1={runCalmarByPairCount.PAD}
					y1={runCalmarByPairCount.midY}
					x2={runCalmarByPairCount.W - runCalmarByPairCount.PAD}
					y2={runCalmarByPairCount.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each runCalmarByPairCount.rows as row, i (i)}
					{@const x = runCalmarByPairCount.PAD + i * runCalmarByPairCount.barW}
					{@const bh = Math.max(
						2,
						(Math.abs(row.avg) / runCalmarByPairCount.maxAbs) *
							(runCalmarByPairCount.midY - runCalmarByPairCount.PAD)
					)}
					{@const y = row.avg >= 0 ? runCalmarByPairCount.midY - bh : runCalmarByPairCount.midY}
					{@const color = row.avg >= 0 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
					<rect {x} {y} width={runCalmarByPairCount.barW - 1} height={bh} fill={color} />
					<text
						x={x + runCalmarByPairCount.barW / 2}
						y={runCalmarByPairCount.H - 2}
						text-anchor="middle"
						font-size="5.5"
						fill="var(--ch-axis-muted)">{row.b}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg Calmar ratio per backtest run grouped by pair count in buckets of 5 · teal=positive ·
				red=negative · reveals optimal pair count for risk-adjusted returns
			</p>
		</section>
	{/if}
	{#if runSortinoTimeline}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Monthly Avg Sortino Ratio Timeline
			</h3>
			<svg
				viewBox="0 0 {runSortinoTimeline.W} {runSortinoTimeline.H}"
				class="w-full"
				style="height:{runSortinoTimeline.H}px"
			>
				<line
					x1={runSortinoTimeline.PAD}
					y1={runSortinoTimeline.zeroY}
					x2={runSortinoTimeline.W - runSortinoTimeline.PAD}
					y2={runSortinoTimeline.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				<polygon points={runSortinoTimeline.area} fill={runSortinoTimeline.fillColor} />
				<polyline
					points={runSortinoTimeline.polyline}
					fill="none"
					stroke={runSortinoTimeline.color}
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={runSortinoTimeline.PAD}
					y={runSortinoTimeline.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{runSortinoTimeline.firstMo}</text
				>
				<text
					x={runSortinoTimeline.W - runSortinoTimeline.PAD}
					y={runSortinoTimeline.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{runSortinoTimeline.lastMo}</text
				>
				<text
					x={runSortinoTimeline.W - runSortinoTimeline.PAD}
					y={runSortinoTimeline.PAD + 6}
					text-anchor="end"
					font-size="7"
					fill={runSortinoTimeline.color}>{runSortinoTimeline.last}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Monthly avg Sortino ratio across archived runs · green≥1 · yellow≥0 · red&lt;0 · area fills
				above/below zero baseline · reveals trend in downside-risk-adjusted returns
			</p>
		</section>
	{/if}
	{#if runTradeCountScatter}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Profit% vs Trade Count Scatter
			</h3>
			<svg
				viewBox="0 0 {runTradeCountScatter.W} {runTradeCountScatter.H}"
				class="w-full"
				style="height:{runTradeCountScatter.H}px"
			>
				<line
					x1={runTradeCountScatter.PAD}
					y1={runTradeCountScatter.zeroY}
					x2={runTradeCountScatter.W - runTradeCountScatter.PAD}
					y2={runTradeCountScatter.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each runTradeCountScatter.pts as p, _i (_i)}
					{@const cx = runTradeCountScatter.toX(p.tc)}
					{@const cy = runTradeCountScatter.toY(p.profit)}
					{@const col = p.profit >= 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)'}
					<circle {cx} {cy} r="2" fill={col} />
				{/each}
				<text
					x={runTradeCountScatter.PAD}
					y={runTradeCountScatter.PAD + 7}
					font-size="6"
					fill="var(--ch-axis-muted)">+{runTradeCountScatter.profMax}%</text
				>
				<text
					x={runTradeCountScatter.W - runTradeCountScatter.PAD}
					y={runTradeCountScatter.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{runTradeCountScatter.tcMax} trades</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Scatter of total profit% (Y) vs trade count (X) per archived run · green=profitable ·
				red=loss · reveals whether high-frequency backtests consistently outperform low-frequency
				ones
			</p>
		</section>
	{/if}
	{#if runProfitByPairGroup}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit% by Trade Count Group
			</h3>
			<svg
				viewBox="0 0 {runProfitByPairGroup.W} {runProfitByPairGroup.H}"
				class="w-full"
				style="height:{runProfitByPairGroup.H}px"
			>
				<line
					x1={runProfitByPairGroup.PAD}
					y1={runProfitByPairGroup.midY}
					x2={runProfitByPairGroup.W - runProfitByPairGroup.PAD}
					y2={runProfitByPairGroup.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="1"
				/>
				{#each runProfitByPairGroup.rows as row, i (i)}
					{@const x = runProfitByPairGroup.PAD + i * (runProfitByPairGroup.bw + 2)}
					{@const bh = Math.max(
						1,
						(Math.abs(row.avg) / runProfitByPairGroup.maxAbs) *
							(runProfitByPairGroup.H / 2 - runProfitByPairGroup.PAD)
					)}
					{@const y = row.avg >= 0 ? runProfitByPairGroup.midY - bh : runProfitByPairGroup.midY}
					{@const color = row.avg >= 0 ? 'var(--ch-violet)' : 'var(--ch-loss)'}
					<rect {x} {y} width={runProfitByPairGroup.bw} height={bh} rx="2" fill={color} />
					<text
						x={x + runProfitByPairGroup.bw / 2}
						y={runProfitByPairGroup.H - 1}
						text-anchor="middle"
						font-size="6.5"
						fill="var(--ch-axis)">{row.k}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg total profit% grouped by trade count range (1-5/6-15/16-30/30+) · indigo/red diverging ·
				shows whether runs with more trades perform better in archive
			</p>
		</section>
	{/if}
	{#if runAvgSortinoByTF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Sortino by Timeframe
			</h3>
			<svg
				viewBox="0 0 {runAvgSortinoByTF.W} {runAvgSortinoByTF.H}"
				class="w-full"
				style="height:{runAvgSortinoByTF.H}px"
			>
				<line
					x1={runAvgSortinoByTF.zeroX}
					y1="0"
					x2={runAvgSortinoByTF.zeroX}
					y2={runAvgSortinoByTF.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="1"
				/>
				{#each runAvgSortinoByTF.rows as row, i (i)}
					{@const y = runAvgSortinoByTF.PAD + i * 20}
					{@const bw = Math.max(
						2,
						(Math.abs(row.avg) / runAvgSortinoByTF.maxAbs) * (runAvgSortinoByTF.barMaxW / 2)
					)}
					{@const x = row.avg >= 0 ? runAvgSortinoByTF.zeroX : runAvgSortinoByTF.zeroX - bw}
					{@const color = row.avg >= 0 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
					<rect {x} {y} width={bw} height="13" rx="2" fill={color} />
					<text x={runAvgSortinoByTF.PAD} y={y + 10} font-size="7.5" fill="var(--ch-axis-strong)"
						>{row.tf}</text
					>
					<text
						x={row.avg >= 0 ? runAvgSortinoByTF.zeroX + bw + 2 : runAvgSortinoByTF.zeroX - bw - 2}
						y={y + 10}
						text-anchor={row.avg >= 0 ? 'start' : 'end'}
						font-size="6.5"
						fill={color}>{row.avg.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg Sortino ratio per timeframe across all archived runs · teal/red diverging · identifies
				which timeframes historically deliver better risk-adjusted returns
			</p>
		</section>
	{/if}
	{#if runSharpeCDF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Sharpe Ratio CDF (Archive)
			</h3>
			<svg
				viewBox="0 0 {runSharpeCDF.W} {runSharpeCDF.H}"
				class="w-full"
				style="height:{runSharpeCDF.H}px"
			>
				<line
					x1={runSharpeCDF.zeroX}
					y1={runSharpeCDF.PAD}
					x2={runSharpeCDF.zeroX}
					y2={runSharpeCDF.H - runSharpeCDF.PAD}
					stroke="var(--ch-axis-muted)"
					stroke-width="1"
					stroke-dasharray="3,2"
				/>
				<polyline
					points={runSharpeCDF.polyline}
					fill="none"
					stroke="var(--ch-violet-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text x={runSharpeCDF.PAD} y={runSharpeCDF.H - 2} font-size="6" fill="var(--ch-axis-muted)"
					>{runSharpeCDF.minV}</text
				>
				<text
					x={runSharpeCDF.W - runSharpeCDF.PAD}
					y={runSharpeCDF.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{runSharpeCDF.maxV}</text
				>
				<text
					x={runSharpeCDF.W / 2}
					y={runSharpeCDF.PAD + 8}
					text-anchor="middle"
					font-size="7"
					fill="var(--ch-violet-strong)">median {runSharpeCDF.median} · p80 {runSharpeCDF.p80}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Cumulative distribution of Sharpe ratios across all archived runs · indigo S-curve · dashed
				zero line · right-skewed = more runs with positive Sharpe · p80 reveals top-end performance
			</p>
		</section>
	{/if}
	{#if runMonthlyStrategyCount}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Distinct Strategies Tested per Month
			</h3>
			<svg
				viewBox="0 0 {runMonthlyStrategyCount.W} {runMonthlyStrategyCount.H}"
				class="w-full"
				style="height:{runMonthlyStrategyCount.H}px"
			>
				{#each runMonthlyStrategyCount.pts as p, i (i)}
					{@const x = runMonthlyStrategyCount.PAD + i * (runMonthlyStrategyCount.bw + 1)}
					{@const bh = Math.max(
						1,
						(p.count / runMonthlyStrategyCount.maxCount) *
							(runMonthlyStrategyCount.H - runMonthlyStrategyCount.PAD * 2)
					)}
					{@const y = runMonthlyStrategyCount.H - runMonthlyStrategyCount.PAD - bh}
					<rect
						{x}
						{y}
						width={runMonthlyStrategyCount.bw}
						height={bh}
						rx="1"
						fill="var(--ch-warn)"
					/>
					{#if i % 3 === 0}
						<text
							x={x + runMonthlyStrategyCount.bw / 2}
							y={runMonthlyStrategyCount.H - 1}
							text-anchor="middle"
							font-size="5.5"
							fill="var(--ch-axis-muted)">{p.m}</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Number of distinct strategies tested per month in archived runs · orange bars · increasing
				count indicates broader strategy exploration; plateau suggests focused optimization
			</p>
		</section>
	{/if}
	{#if runDrawdownCDF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Max Drawdown% CDF (Archive)
			</h3>
			<svg
				viewBox="0 0 {runDrawdownCDF.W} {runDrawdownCDF.H}"
				class="w-full"
				style="height:{runDrawdownCDF.H}px"
			>
				<polyline
					points={runDrawdownCDF.polyline}
					fill="none"
					stroke="var(--ch-loss-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={runDrawdownCDF.PAD}
					y={runDrawdownCDF.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{runDrawdownCDF.minV}%</text
				>
				<text
					x={runDrawdownCDF.W - runDrawdownCDF.PAD}
					y={runDrawdownCDF.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{runDrawdownCDF.maxV}%</text
				>
				<text
					x={runDrawdownCDF.W / 2}
					y={runDrawdownCDF.PAD + 8}
					text-anchor="middle"
					font-size="7"
					fill="var(--ch-loss-strong)"
					>median {runDrawdownCDF.median}% · p20 {runDrawdownCDF.p20}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Cumulative distribution of max drawdown% across archived runs · red S-curve · left-skewed =
				most runs have low drawdown · p20 = 80% of runs exceed this drawdown threshold
			</p>
		</section>
	{/if}
	{#if runProfitByStrategyMonth}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit% Heatmap (Strategy × Month)
			</h3>
			<svg
				viewBox="0 0 {runProfitByStrategyMonth.W} {runProfitByStrategyMonth.H}"
				class="w-full"
				style="height:{runProfitByStrategyMonth.H}px"
			>
				{#each runProfitByStrategyMonth.strats as s, si (si)}
					<text
						x={runProfitByStrategyMonth.PAD}
						y={runProfitByStrategyMonth.PAD + (si + 1) * runProfitByStrategyMonth.cellH + 12}
						font-size="5.5"
						fill="var(--ch-axis)">{s}</text
					>
				{/each}
				{#each runProfitByStrategyMonth.months as mo, mi (mi)}
					<text
						x={runProfitByStrategyMonth.PAD +
							(mi + 1) * runProfitByStrategyMonth.cellW +
							runProfitByStrategyMonth.cellW / 2}
						y={runProfitByStrategyMonth.PAD + 8}
						text-anchor="middle"
						font-size="5.5"
						fill="var(--ch-axis)">{mo.slice(5)}</text
					>
				{/each}
				{#each runProfitByStrategyMonth.cells as cell, _i (_i)}
					{@const intensity = Math.min(1, Math.abs(cell.avg) / runProfitByStrategyMonth.maxAbs)}
					{@const alpha = (intensity * 0.6 + 0.08).toFixed(2)}
					{@const fill = cell.avg >= 0 ? `rgba(34,197,94,${alpha})` : `rgba(239,68,68,${alpha})`}
					<rect
						x={cell.x}
						y={cell.y}
						width={runProfitByStrategyMonth.cellW - 2}
						height={runProfitByStrategyMonth.cellH - 2}
						rx="2"
						{fill}
					/>
					<text
						x={cell.x + runProfitByStrategyMonth.cellW / 2 - 1}
						y={cell.y + 11}
						text-anchor="middle"
						font-size="5.5"
						fill="var(--ch-axis-strong)">{cell.avg.toFixed(1)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg profit% heatmap by strategy (rows) and month (cols, last 5) · green=positive ·
				red=negative · intensity=magnitude · reveals which strategies perform consistently
				month-over-month
			</p>
		</section>
	{/if}
	{#if runBestCalmarByStrategy}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Calmar Ratio by Strategy
			</h3>
			<svg
				viewBox="0 0 {runBestCalmarByStrategy.W} {runBestCalmarByStrategy.H}"
				class="w-full"
				style="height:{runBestCalmarByStrategy.H}px"
			>
				<line
					x1={runBestCalmarByStrategy.zeroX}
					y1="0"
					x2={runBestCalmarByStrategy.zeroX}
					y2={runBestCalmarByStrategy.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.8"
				/>
				{#each runBestCalmarByStrategy.rows as row, i (i)}
					{@const y = runBestCalmarByStrategy.PAD + i * 18}
					{@const bw = Math.max(
						2,
						(Math.abs(row.best) / runBestCalmarByStrategy.maxAbs) *
							(runBestCalmarByStrategy.barMaxW / 2)
					)}
					{@const x =
						row.best >= 0 ? runBestCalmarByStrategy.zeroX : runBestCalmarByStrategy.zeroX - bw}
					{@const color =
						row.best >= 1
							? 'var(--ch-profit)'
							: row.best >= 0
								? 'var(--ch-teal)'
								: 'var(--ch-loss)'}
					<text
						x={runBestCalmarByStrategy.PAD}
						y={y + 12}
						font-size="7"
						fill="var(--ch-axis-strong)">{row.name}</text
					>
					<rect {x} {y} width={bw} height="13" rx="2" fill={color} />
					<text
						x={row.best >= 0
							? runBestCalmarByStrategy.zeroX + bw + 2
							: runBestCalmarByStrategy.zeroX - bw - 2}
						y={y + 12}
						text-anchor={row.best >= 0 ? 'start' : 'end'}
						font-size="6"
						fill={color}>{row.best.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Best Calmar ratio achieved per strategy across all archive runs · green≥1 · teal≥0 ·
				red&lt;0 · best-ever Calmar = peak capital efficiency — shows strategy ceiling
			</p>
		</section>
	{/if}
	{#if runSharpeByPairCount}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Sharpe by Pair Count Bucket
			</h3>
			<svg
				viewBox="0 0 {runSharpeByPairCount.W} {runSharpeByPairCount.H}"
				class="w-full"
				style="height:{runSharpeByPairCount.H}px"
			>
				<line
					x1={runSharpeByPairCount.zeroX}
					y1="0"
					x2={runSharpeByPairCount.zeroX}
					y2={runSharpeByPairCount.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.8"
				/>
				{#each runSharpeByPairCount.rows as row, i (i)}
					{@const y = runSharpeByPairCount.PAD + i * 22}
					{@const bw = Math.max(
						2,
						(Math.abs(row.avg) / runSharpeByPairCount.maxAbs) * (runSharpeByPairCount.barMaxW / 2)
					)}
					{@const x = row.avg >= 0 ? runSharpeByPairCount.zeroX : runSharpeByPairCount.zeroX - bw}
					{@const color =
						row.avg >= 1 ? 'var(--ch-profit)' : row.avg >= 0 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
					<text x={runSharpeByPairCount.PAD} y={y + 14} font-size="8" fill="var(--ch-axis-strong)"
						>{row.k} pairs</text
					>
					<rect {x} {y} width={bw} height="15" rx="2" fill={color} />
					<text
						x={row.avg >= 0
							? runSharpeByPairCount.zeroX + bw + 2
							: runSharpeByPairCount.zeroX - bw - 2}
						y={y + 12}
						text-anchor={row.avg >= 0 ? 'start' : 'end'}
						font-size="6.5"
						fill={color}>{row.avg.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg Sharpe ratio by pair count group · green≥1 · teal≥0 · red&lt;0 · reveals if broad
				diversification (more pairs) improves or hurts risk-adjusted returns
			</p>
		</section>
	{/if}
	{#if runProfitByDow}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Run Profit% by Day of Week
			</h3>
			<svg
				viewBox="0 0 {runProfitByDow.W} {runProfitByDow.H}"
				class="w-full"
				style="height:{runProfitByDow.H}px"
			>
				<line
					x1={runProfitByDow.PAD}
					y1={runProfitByDow.midY}
					x2={runProfitByDow.W - runProfitByDow.PAD}
					y2={runProfitByDow.midY}
					stroke="var(--ch-axis-muted)"
					stroke-width="0.5"
				/>
				{#each runProfitByDow.rows as row, i (i)}
					{@const x = runProfitByDow.PAD + i * (runProfitByDow.bw + 1)}
					{@const barH = Math.max(
						2,
						(Math.abs(row.avg) / runProfitByDow.maxAbs) * (runProfitByDow.midY - 4)
					)}
					{@const y = row.avg >= 0 ? runProfitByDow.midY - barH : runProfitByDow.midY}
					{@const color = row.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					<rect {x} {y} width={runProfitByDow.bw} height={barH} rx="1" fill={color} />
					<text
						x={x + runProfitByDow.bw / 2}
						y={runProfitByDow.H - 1}
						text-anchor="middle"
						font-size="6.5"
						fill="var(--ch-axis-strong)">{row.d}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg profit% by run start day of week · green = positive avg · red = negative avg · reveals
				weekday seasonality in backtesting outcomes
			</p>
		</section>
	{/if}
	{#if runMonthlyTradeCount}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Monthly Avg Trade Count
			</h3>
			<svg
				viewBox="0 0 {runMonthlyTradeCount.W} {runMonthlyTradeCount.H}"
				class="w-full"
				style="height:{runMonthlyTradeCount.H}px"
			>
				{#each runMonthlyTradeCount.pts as pt, i (i)}
					{@const x = runMonthlyTradeCount.PAD + i * (runMonthlyTradeCount.bw + 0.5)}
					{@const barH = Math.max(
						2,
						(pt.avg / runMonthlyTradeCount.maxAvg) * (runMonthlyTradeCount.H - 14)
					)}
					{@const y = runMonthlyTradeCount.H - barH - 6}
					{@const color =
						pt.avg >= runMonthlyTradeCount.maxAvg * 0.7
							? 'var(--ch-teal-strong)'
							: pt.avg >= runMonthlyTradeCount.maxAvg * 0.4
								? 'var(--ch-violet)'
								: 'var(--ch-axis)'}
					<rect {x} {y} width={runMonthlyTradeCount.bw} height={barH} rx="1" fill={color} />
					<text
						x={x + runMonthlyTradeCount.bw / 2}
						y={runMonthlyTradeCount.H - 1}
						text-anchor="middle"
						font-size="5.5"
						fill="var(--ch-axis)">{pt.mo}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg trade count per run by month · teal = high activity months · identifies seasonal trading
				frequency patterns
			</p>
		</section>
	{/if}
	{#if runAvgHoldTimeByTF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Hold Time by Timeframe
			</h3>
			<svg
				viewBox="0 0 {runAvgHoldTimeByTF.W} {runAvgHoldTimeByTF.H}"
				class="w-full"
				style="height:{runAvgHoldTimeByTF.H}px"
			>
				{#each runAvgHoldTimeByTF.rows as row, i (i)}
					{@const y = runAvgHoldTimeByTF.PAD + i * 20}
					{@const bw = Math.max(
						2,
						(row.avg / runAvgHoldTimeByTF.maxAvg) * runAvgHoldTimeByTF.barMaxW
					)}
					{@const color =
						row.avg <= runAvgHoldTimeByTF.maxAvg * 0.3
							? 'var(--ch-profit)'
							: row.avg <= runAvgHoldTimeByTF.maxAvg * 0.6
								? 'var(--ch-teal)'
								: 'var(--ch-warn)'}
					<text x={runAvgHoldTimeByTF.PAD} y={y + 13} font-size="8" fill="var(--ch-axis-strong)"
						>{row.tf}</text
					>
					<rect x={runAvgHoldTimeByTF.PAD + 40} {y} width={bw} height="14" rx="2" fill={color} />
					<text x={runAvgHoldTimeByTF.PAD + 40 + bw + 3} y={y + 12} font-size="6.5" fill={color}
						>{row.avg.toFixed(0)}m</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg trade hold time (minutes) by timeframe · green=short hold · yellow=long hold · longer
				timeframes naturally produce longer hold durations
			</p>
		</section>
	{/if}
	{#if runCalmarBySortinoQuartile}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Calmar by Sortino Quartile
			</h3>
			<svg
				viewBox="0 0 {runCalmarBySortinoQuartile.W} {runCalmarBySortinoQuartile.H}"
				class="w-full"
				style="height:{runCalmarBySortinoQuartile.H}px"
			>
				<line
					x1={runCalmarBySortinoQuartile.PAD}
					y1={runCalmarBySortinoQuartile.midY}
					x2={runCalmarBySortinoQuartile.W - runCalmarBySortinoQuartile.PAD}
					y2={runCalmarBySortinoQuartile.midY}
					stroke="var(--ch-axis-muted)"
					stroke-width="0.5"
				/>
				{#each runCalmarBySortinoQuartile.rows as row, i (i)}
					{@const x = runCalmarBySortinoQuartile.PAD + i * (runCalmarBySortinoQuartile.bw + 2)}
					{@const barH = Math.max(
						2,
						(Math.abs(row.avg) / runCalmarBySortinoQuartile.maxAbs) *
							(runCalmarBySortinoQuartile.midY - 8)
					)}
					{@const y =
						row.avg >= 0 ? runCalmarBySortinoQuartile.midY - barH : runCalmarBySortinoQuartile.midY}
					{@const color =
						row.avg >= 1 ? 'var(--ch-profit)' : row.avg >= 0 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
					<rect {x} {y} width={runCalmarBySortinoQuartile.bw} height={barH} rx="2" fill={color} />
					<text
						x={x + runCalmarBySortinoQuartile.bw / 2}
						y={runCalmarBySortinoQuartile.H - 1}
						text-anchor="middle"
						font-size="7"
						fill="var(--ch-axis-strong)">{row.label}</text
					>
					<text
						x={x + runCalmarBySortinoQuartile.bw / 2}
						y={row.avg >= 0 ? y - 2 : y + barH + 8}
						text-anchor="middle"
						font-size="6"
						fill={color}>{row.avg.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg Calmar ratio by Sortino quartile · green≥1 · teal≥0 · red&lt;0 · Q4 Sortino runs (best
				downside-adjusted return) should also show high Calmar — confirms metrics are aligned
			</p>
		</section>
	{/if}
	{#if runAvgWinRateByStrategy}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Win Rate% by Strategy
			</h3>
			<svg
				viewBox="0 0 {runAvgWinRateByStrategy.W} {runAvgWinRateByStrategy.H}"
				class="w-full"
				style="height:{runAvgWinRateByStrategy.H}px"
			>
				{#each runAvgWinRateByStrategy.rows as row, i (i)}
					{@const y = runAvgWinRateByStrategy.PAD + i * 20}
					{@const bw = Math.max(2, (row.avg / 100) * runAvgWinRateByStrategy.barMaxW)}
					{@const color =
						row.avg >= 55
							? 'var(--ch-profit)'
							: row.avg >= 45
								? 'var(--ch-teal)'
								: 'var(--ch-loss)'}
					<text
						x={runAvgWinRateByStrategy.PAD}
						y={y + 13}
						font-size="7"
						fill="var(--ch-axis-strong)">{row.name}</text
					>
					<rect
						x={runAvgWinRateByStrategy.PAD + 90}
						{y}
						width={bw}
						height="14"
						rx="2"
						fill={color}
					/>
					<text
						x={runAvgWinRateByStrategy.PAD + 90 + bw + 3}
						y={y + 12}
						font-size="6.5"
						fill={color}>{row.avg.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg win rate% per strategy across all archive runs · green≥55% · teal≥45% · red&lt;45% ·
				strategies above 50% have positive expectancy on trade frequency
			</p>
		</section>
	{/if}
	{#if runProfitVsCalmarScatter}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Profit% vs Calmar Scatter
			</h3>
			<svg
				viewBox="0 0 {runProfitVsCalmarScatter.W} {runProfitVsCalmarScatter.H}"
				class="w-full"
				style="height:{runProfitVsCalmarScatter.H}px"
			>
				<line
					x1={runProfitVsCalmarScatter.midX}
					y1={0}
					x2={runProfitVsCalmarScatter.midX}
					y2={runProfitVsCalmarScatter.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				<line
					x1={0}
					y1={runProfitVsCalmarScatter.midY}
					x2={runProfitVsCalmarScatter.W}
					y2={runProfitVsCalmarScatter.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				{#each runProfitVsCalmarScatter.pts as p, _i (_i)}
					{@const cx =
						runProfitVsCalmarScatter.midX +
						(p.x / runProfitVsCalmarScatter.maxX) *
							(runProfitVsCalmarScatter.W / 2 - runProfitVsCalmarScatter.PAD)}
					{@const cy =
						runProfitVsCalmarScatter.midY -
						(p.y / runProfitVsCalmarScatter.maxY) *
							(runProfitVsCalmarScatter.H / 2 - runProfitVsCalmarScatter.PAD)}
					{@const color =
						p.wr >= 55
							? 'var(--ch-profit-light)'
							: p.wr >= 45
								? 'var(--ch-teal-light)'
								: 'var(--ch-loss-light)'}
					<circle {cx} {cy} r="2" fill={color} />
				{/each}
				<text
					x={runProfitVsCalmarScatter.W - 2}
					y={runProfitVsCalmarScatter.midY - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">Profit%→</text
				>
				<text
					x={runProfitVsCalmarScatter.PAD}
					y={runProfitVsCalmarScatter.PAD + 6}
					font-size="6"
					fill="var(--ch-axis-muted)">Calmar↑</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Scatter: total profit% (X) vs Calmar (Y) · green=WR≥55% · teal=WR≥45% · top-right quadrant =
				runs that combined high profit AND high Calmar ratio
			</p>
		</section>
	{/if}
	{#if runProfitByTimeRange}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">Avg Profit% by Backtest Year</h3>
			<svg
				viewBox={`0 0 ${runProfitByTimeRange.W} ${runProfitByTimeRange.H}`}
				width="100%"
				style="height:70px"
			>
				<line
					x1={runProfitByTimeRange.PAD}
					y1={runProfitByTimeRange.midY}
					x2={runProfitByTimeRange.W - runProfitByTimeRange.PAD}
					y2={runProfitByTimeRange.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
					stroke-dasharray="2,2"
				/>
				{#each runProfitByTimeRange.bars as b, i (i)}
					{@const bh =
						(Math.abs(b.avg) / runProfitByTimeRange.maxAbs) *
						(runProfitByTimeRange.midY - runProfitByTimeRange.PAD)}
					{@const x = runProfitByTimeRange.PAD + i * (runProfitByTimeRange.bw + 2)}
					{@const y = b.avg >= 0 ? runProfitByTimeRange.midY - bh : runProfitByTimeRange.midY}
					{@const color = b.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					<rect {x} {y} width={runProfitByTimeRange.bw} height={bh} fill={color} rx="1" />
					<text
						x={x + runProfitByTimeRange.bw / 2}
						y={runProfitByTimeRange.H}
						text-anchor="middle"
						font-size="6"
						fill="var(--ch-axis)">{b.yr}</text
					>
					<text
						x={x + runProfitByTimeRange.bw / 2}
						y={b.avg >= 0 ? y - 2 : y + bh + 7}
						text-anchor="middle"
						font-size="5"
						fill={color}>{b.avg.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg profit% by backtest timerange year · green=positive · red=negative · reveals which
				market years were most profitable for archived strategies
			</p>
		</section>
	{/if}
	{#if runAvgDrawdownCDF}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">Max Drawdown% CDF</h3>
			<svg
				viewBox={`0 0 ${runAvgDrawdownCDF.W} ${runAvgDrawdownCDF.H}`}
				width="100%"
				style="height:70px"
			>
				<line
					x1={runAvgDrawdownCDF.PAD}
					y1={runAvgDrawdownCDF.H - runAvgDrawdownCDF.PAD}
					x2={runAvgDrawdownCDF.W - runAvgDrawdownCDF.PAD}
					y2={runAvgDrawdownCDF.H - runAvgDrawdownCDF.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				<polyline
					points={runAvgDrawdownCDF.polyline}
					fill="none"
					stroke="var(--ch-loss-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={runAvgDrawdownCDF.PAD}
					y={runAvgDrawdownCDF.H - 2}
					font-size="5.5"
					fill="var(--ch-axis-muted)">{runAvgDrawdownCDF.minV}%</text
				>
				<text
					x={runAvgDrawdownCDF.W - runAvgDrawdownCDF.PAD}
					y={runAvgDrawdownCDF.H - 2}
					text-anchor="end"
					font-size="5.5"
					fill="var(--ch-axis-muted)">{runAvgDrawdownCDF.maxV}%</text
				>
				<text
					x={runAvgDrawdownCDF.W / 2}
					y={runAvgDrawdownCDF.PAD + 8}
					text-anchor="middle"
					font-size="7"
					fill="var(--ch-loss-strong)">median {runAvgDrawdownCDF.median}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				CDF of max drawdown% across archived runs · red curve · steep left = most runs have low DD ·
				flat = wide DD spread indicating inconsistent risk control
			</p>
		</section>
	{/if}
	{#if runSortinoTrend}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">
				Rolling Sortino Ratio Trend (8-run window)
			</h3>
			<svg
				viewBox={`0 0 ${runSortinoTrend.W} ${runSortinoTrend.H}`}
				width="100%"
				style="height:65px"
			>
				<line
					x1={runSortinoTrend.PAD}
					y1={runSortinoTrend.y0}
					x2={runSortinoTrend.W - runSortinoTrend.PAD}
					y2={runSortinoTrend.y0}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
					stroke-dasharray="2,2"
				/>
				<polyline
					points={runSortinoTrend.polyline}
					fill="none"
					stroke="var(--ch-teal-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={runSortinoTrend.PAD}
					y={runSortinoTrend.H}
					font-size="5.5"
					fill="var(--ch-axis-muted)">{runSortinoTrend.minV}</text
				>
				<text
					x={runSortinoTrend.W - runSortinoTrend.PAD}
					y={runSortinoTrend.H}
					text-anchor="end"
					font-size="5.5"
					fill="var(--ch-axis-muted)">{runSortinoTrend.maxV}</text
				>
				<text
					x={runSortinoTrend.PAD}
					y={runSortinoTrend.y0 - 2}
					font-size="5"
					fill="var(--ch-axis-muted)">0</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				8-run rolling Sortino ratio across {runSortinoTrend.n} archive runs · teal line · above 0 = positive
				risk-adjusted return · rising = improving downside-risk-adjusted performance
			</p>
		</section>
	{/if}
	{#if runProfitByPairCount}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">
				Avg (PF−1)% by Pair Count Bucket
			</h3>
			<svg
				viewBox={`0 0 ${runProfitByPairCount.W} ${runProfitByPairCount.H}`}
				width="100%"
				style="height:65px"
			>
				<line
					x1={runProfitByPairCount.PAD}
					y1={runProfitByPairCount.midY}
					x2={runProfitByPairCount.W - runProfitByPairCount.PAD}
					y2={runProfitByPairCount.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				{#each runProfitByPairCount.bars as b, i (i)}
					{@const bh = Math.max(
						1,
						(Math.abs(b.avg) / runProfitByPairCount.maxAbs) *
							(runProfitByPairCount.midY - runProfitByPairCount.PAD)
					)}
					{@const x = runProfitByPairCount.PAD + i * (runProfitByPairCount.bw + 4)}
					{@const y = b.avg >= 0 ? runProfitByPairCount.midY - bh : runProfitByPairCount.midY}
					{@const color = b.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					<rect {x} {y} width={runProfitByPairCount.bw} height={bh} fill={color} rx="1" />
					<text
						x={x + runProfitByPairCount.bw / 2}
						y={runProfitByPairCount.H - 1}
						text-anchor="middle"
						font-size="6"
						fill="var(--ch-axis)">{b.label}</text
					>
					<text
						x={x + runProfitByPairCount.bw / 2}
						y={b.avg >= 0 ? y - 2 : y + bh + 7}
						text-anchor="middle"
						font-size="5.5"
						fill={color}>{b.avg.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg (PF−1)% by pair count · green=positive · red=negative · more pairs may reduce or amplify
				returns depending on diversification quality
			</p>
		</section>
	{/if}

	<!-- ── Comparison panel (sticky bottom) ────────────────────────────────── -->
	{#if selected.size >= 2}
		<div
			class="fixed right-0 bottom-0 left-0 z-40 border-t border-border bg-card/95 backdrop-blur"
			style="max-height:60vh;overflow-y:auto"
		>
			<!-- Header -->
			<div class="flex items-center justify-between border-b border-border px-5 py-2">
				<span class="text-sm font-semibold">
					{lang === 'zh' ? `对比 ${selected.size} 个回测` : `Comparing ${selected.size} runs`}
				</span>
				<button
					onclick={() => {
						selected = new Set();
					}}
					class="rounded px-3 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
				>
					{t(lang, 'archive.compare.close')} ×
				</button>
			</div>

			<!-- Radar chart -->
			{#if radarData}
				{@const rd = radarData}
				<div class="flex flex-col items-center gap-6 border-b border-border px-5 py-3 sm:flex-row">
					<svg viewBox="0 0 220 190" class="shrink-0" style="width:180px;height:155px">
						<!-- Grid rings -->
						{#each rd.grid as ring, _i (_i)}
							<polygon
								points={ring.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')}
								fill="none"
								stroke="var(--ch-rule-faint)"
								stroke-width="1"
							/>
						{/each}
						<!-- Spokes -->
						{#each rd.spokes as s, _i (_i)}
							<line
								x1={rd.CX}
								y1={rd.CY}
								x2={s.x.toFixed(1)}
								y2={s.y.toFixed(1)}
								stroke="var(--ch-rule)"
								stroke-width="1"
							/>
							<text
								x={s.lx.toFixed(1)}
								y={s.ly.toFixed(1)}
								text-anchor="middle"
								dominant-baseline="middle"
								font-size="8"
								fill="var(--ch-axis-strong)">{s.label}</text
							>
						{/each}
						<!-- Run 1 polygon -->
						<polygon
							points={rd.poly0.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')}
							fill="var(--ch-profit-light)"
							stroke="rgb(34,197,94)"
							stroke-width="1.5"
						/>
						<!-- Run 2 polygon -->
						<polygon
							points={rd.poly1.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')}
							fill="rgba(129,140,248,0.15)"
							stroke="rgb(129,140,248)"
							stroke-width="1.5"
						/>
					</svg>
					<div class="flex flex-col gap-2 text-xs">
						<div class="flex items-center gap-2">
							<span
								class="inline-block h-2.5 w-4 rounded-sm border border-green-500 bg-green-500/60"
							></span><span class="font-mono">#{compareRuns[0]?.id} {compareRuns[0]?.strategy}</span
							>
						</div>
						<div class="flex items-center gap-2">
							<span
								class="inline-block h-2.5 w-4 rounded-sm border border-indigo-400 bg-indigo-500/60"
							></span><span class="font-mono">#{compareRuns[1]?.id} {compareRuns[1]?.strategy}</span
							>
						</div>
						<p class="mt-1 text-[10px] text-muted-foreground">
							LowDD = inverted MaxDD — larger polygon wins
						</p>
					</div>
				</div>
			{/if}

			<!-- Comparison grid -->
			<div class="overflow-x-auto px-5 py-3">
				<table class="w-full border-collapse font-mono text-xs">
					<!-- Run headers -->
					<thead>
						<tr>
							<th class="w-24 py-1 pr-4 text-left text-[10px] text-muted-foreground uppercase">
								{t(lang, 'archive.compare.title')}
							</th>
							{#each compareRuns as run, _i (_i)}
								<th class="min-w-48 px-3 py-1 text-left">
									<div class="text-sm font-semibold text-foreground">
										#{run.id}
										{run.strategy}
									</div>
									<div class="text-[10px] text-muted-foreground">
										{run.timeframe ?? '-'} · {fmtTime(run.started_at)}
									</div>
								</th>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each compareMetrics as metric, _i (_i)}
							<tr class="border-t border-border/40">
								<td
									class="py-1.5 pr-4 text-[10px] whitespace-nowrap text-muted-foreground uppercase"
								>
									{metric.label}
								</td>
								{#each compareRuns as run, ri (ri)}
									{@const rawVal = getMetricValue(run, metric.key)}
									{@const better = isBetter(metric, ri)}
									{@const frac = barFraction(metric, ri)}
									<td class="px-3 py-1.5">
										<div class="flex items-center gap-2">
											<span class:text-green-400={better} class:text-muted-foreground={!better}>
												{metric.fmt(rawVal)}
											</span>
											<!-- Mini bar -->
											<div class="h-2 w-20 flex-shrink-0 overflow-hidden rounded-full bg-secondary">
												<div
													class="h-full rounded-full transition-all"
													style="width:{(frac * 100).toFixed(1)}%;background-color:{better
														? '#22c55e'
														: '#64748b'}"
												></div>
											</div>
										</div>
									</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</div>
	{/if}

	<!-- ── Analytic charts grid (uniform card heights via 2-col grid) ──────── -->
	<div class="mt-6 grid gap-4 lg:grid-cols-2">
		{#if timeframeCalmarRanking}
			<section class="flex flex-col rounded-lg border bg-card p-5">
				<h2 class="mb-3 text-sm font-semibold">
					Calmar Ranking by Timeframe
					<span class="ml-1 text-xs font-normal text-muted-foreground"
						>({timeframeCalmarRanking.reduce((s, r) => s + r.count, 0)} runs · avg Calmar, profit%, win
						rate per timeframe)</span
					>
					<ChartInfo metric="calmar" {lang} />
				</h2>
				<div class="overflow-x-auto">
					<table class="w-full text-xs">
						<thead class="text-[10px] text-muted-foreground uppercase">
							<tr>
								<th class="w-16 py-1.5 pl-1 text-left">TF</th>
								<th class="w-40 py-1.5 text-left">Avg Calmar</th>
								<th class="w-20 py-1.5 text-right">Avg Profit</th>
								<th class="w-16 py-1.5 text-right">Avg WR</th>
								<th class="w-12 py-1.5 text-right">Runs</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-border/20">
							{#each timeframeCalmarRanking as r, _i (_i)}
								<tr>
									<td class="py-1.5 pl-1 font-mono font-semibold">{r.tf}</td>
									<td class="py-1.5">
										<div class="flex items-center gap-2">
											<div class="relative h-4 w-32 overflow-hidden rounded-sm bg-muted/20">
												<div
													class="absolute inset-y-0 left-0 rounded-sm"
													style="width:{Math.abs(r.calmarBarPct).toFixed(
														1
													)}%; background:{r.avgCalmar >= 1
														? 'var(--ch-profit-light)'
														: r.avgCalmar >= 0
															? 'var(--ch-warn-light)'
															: 'var(--ch-loss-light)'}"
												></div>
												<span
													class="absolute inset-y-0 left-1.5 flex items-center font-mono text-[10px]"
													>{r.avgCalmar.toFixed(2)}</span
												>
											</div>
										</div>
									</td>
									<td
										class="py-1.5 text-right font-mono"
										class:text-green-400={r.avgProfit >= 0}
										class:text-red-400={r.avgProfit < 0}
									>
										{r.avgProfit >= 0 ? '+' : ''}{r.avgProfit.toFixed(1)}%
									</td>
									<td class="py-1.5 text-right font-mono text-muted-foreground">
										{r.avgWr != null ? r.avgWr.toFixed(1) + '%' : '—'}
									</td>
									<td class="py-1.5 text-right font-mono text-muted-foreground">{r.count}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				<p class="mt-2 text-[10px] text-muted-foreground">
					Timeframes sorted short → long · green Calmar ≥ 1 · yellow 0–1 · red negative
				</p>
			</section>
		{/if}

		{#if profitVsSortino}
			{@const pvs = profitVsSortino}
			<section class="flex flex-col rounded-lg border bg-card p-5">
				<h2 class="mb-2 text-sm font-semibold">
					Profit vs Sortino
					<span class="ml-1 text-xs font-normal text-muted-foreground"
						>({pvs.dots.length} runs · colored by timeframe)</span
					>
					<ChartInfo metric="sortino" {lang} />
				</h2>
				<svg viewBox="0 0 {pvs.W} {pvs.H}" class="w-full" style="height:{pvs.H}px">
					<line
						x1={pvs.PAD}
						y1={pvs.zeroY.toFixed(1)}
						x2={pvs.W - pvs.PAD}
						y2={pvs.zeroY.toFixed(1)}
						stroke="var(--ch-rule)"
						stroke-width="1"
						stroke-dasharray="3 2"
					/>
					<line
						x1={pvs.zeroX.toFixed(1)}
						y1={pvs.PAD}
						x2={pvs.zeroX.toFixed(1)}
						y2={pvs.H - pvs.PAD}
						stroke="var(--ch-rule)"
						stroke-width="1"
						stroke-dasharray="3 2"
					/>
					{#each pvs.dots as d, _i (_i)}
						<circle cx={d.x.toFixed(1)} cy={d.y.toFixed(1)} r="3" fill={d.color} opacity="0.8">
							<title
								>{d.tf} · Sortino {d.sortino.toFixed(2)} · Profit {d.profit >= 0
									? '+'
									: ''}{d.profit.toFixed(1)}%</title
							>
						</circle>
					{/each}
				</svg>
				<div class="mt-2 flex flex-wrap gap-3 text-[10px] text-muted-foreground">
					{#each pvs.tfs as tf, _i (_i)}
						<span class="flex items-center gap-1">
							<span class="inline-block h-2 w-2 rounded-full" style="background:{pvs.tfColor[tf]}"
							></span>{tf}
						</span>
					{/each}
				</div>
				<p class="mt-1 text-[10px] text-muted-foreground">
					x = Sortino ratio · y = total profit% · top-right quadrant = high risk-adj return and high
					profit
				</p>
			</section>
		{/if}

		{#if calmarVsSortino}
			{@const cvs = calmarVsSortino}
			<section class="flex flex-col rounded-lg border bg-card p-5">
				<h2 class="mb-2 text-sm font-semibold">
					Calmar vs Sortino Risk Map
					<span class="ml-1 text-xs font-normal text-muted-foreground"
						>({cvs.dots.length} runs · r = {cvs.corr >= 0 ? '+' : ''}{cvs.corr.toFixed(2)})</span
					>
					<ChartInfo metric="calmar" {lang} />
				</h2>
				<svg viewBox="0 0 {cvs.W} {cvs.H}" class="w-full" style="height:{cvs.H}px">
					{#each cvs.dots as d, _i (_i)}
						<circle cx={d.x.toFixed(1)} cy={d.y.toFixed(1)} r="3" fill={d.color} stroke="none">
							<title
								>{d.strategy} [{d.tf}] · Calmar {d.calmar.toFixed(2)} · Sortino {d.sortino.toFixed(
									2
								)} · profit {d.profit >= 0 ? '+' : ''}{d.profit.toFixed(1)}%</title
							>
						</circle>
					{/each}
					<text x={cvs.PAD} y={cvs.H - 3} font-size="7" fill="var(--ch-rule)"
						>{cvs.xMin.toFixed(1)} C</text
					>
					<text
						x={cvs.W - cvs.PAD}
						y={cvs.H - 3}
						font-size="7"
						fill="var(--ch-rule)"
						text-anchor="end">{cvs.xMax.toFixed(1)} C</text
					>
					<text x={cvs.PAD} y={cvs.PAD + 6} font-size="7" fill="var(--ch-rule)"
						>{cvs.yMax.toFixed(1)} S</text
					>
					<text x={cvs.PAD} y={cvs.H - 10} font-size="7" fill="var(--ch-rule)"
						>{cvs.yMin.toFixed(1)} S</text
					>
				</svg>
				<p class="mt-1 text-[10px] text-muted-foreground">
					x = Calmar ratio · y = Sortino ratio · color = profit% (green=high) · top-right = best
					risk-adj quality · r = {cvs.corr >= 0 ? '+' : ''}{cvs.corr.toFixed(2)}
				</p>
			</section>
		{/if}

		{#if strategyRunProfitRange}
			<section class="flex flex-col rounded-lg border bg-card p-5">
				<h2 class="mb-3 text-sm font-semibold">
					Strategy Profit Range
					<span class="ml-1 text-xs font-normal text-muted-foreground"
						>(best vs worst run profit% · min 3 runs per strategy)</span
					>
					<ChartInfo metric="totalProfit" {lang} />
				</h2>
				<div class="space-y-2">
					{#each strategyRunProfitRange as r, _i (_i)}
						<div class="flex items-center gap-2">
							<span class="w-40 shrink-0 truncate font-mono text-[10px]" title={r.strategy}
								>{r.strategy}</span
							>
							<div class="relative h-4 flex-1 overflow-hidden rounded-sm bg-muted/20">
								<!-- range bar from worst to best -->
								<div
									class="absolute top-0 bottom-0 rounded-sm bg-indigo-500/30"
									style="left:{r.worstPct.toFixed(1)}%; width:{(r.bestPct - r.worstPct).toFixed(
										1
									)}%"
								></div>
								<!-- median dot -->
								<div
									class="absolute top-0 bottom-0 w-0.5 bg-yellow-400/80"
									style="left:{r.medianPct.toFixed(1)}%"
								></div>
							</div>
							<span class="w-32 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
								{r.worst >= 0 ? '+' : ''}{r.worst.toFixed(0)}% → +{r.best.toFixed(0)}%
							</span>
						</div>
					{/each}
				</div>
				<div class="mt-2 flex gap-4 text-[10px] text-muted-foreground">
					<span class="flex items-center gap-1"
						><span class="inline-block h-3 w-4 rounded-sm bg-indigo-500/30"></span>Profit range
						(worst–best)</span
					>
					<span class="flex items-center gap-1"
						><span class="inline-block h-3 w-0.5 rounded bg-yellow-400/80"></span>Median run</span
					>
				</div>
				<p class="mt-1 text-[10px] text-muted-foreground">
					Wide range = inconsistent results · narrow range = stable across parameter configs
				</p>
			</section>
		{/if}

		{#if profitFactorByTimeframe}
			<section class="flex flex-col rounded-lg border bg-card p-5">
				<h2 class="mb-3 text-sm font-semibold">
					Avg Profit Factor by Timeframe
					<span class="ml-1 text-xs font-normal text-muted-foreground"
						>(gross wins ÷ gross losses · min 3 runs per timeframe)</span
					>
					<ChartInfo metric="profitFactor" {lang} />
				</h2>
				<div class="space-y-1.5">
					{#each profitFactorByTimeframe as r, _i (_i)}
						<div class="flex items-center gap-2">
							<span class="w-12 shrink-0 font-mono text-[10px] font-semibold">{r.tf}</span>
							<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
								<div
									class="absolute inset-y-0 left-0 rounded-sm transition-all"
									style="width:{r.barPct.toFixed(1)}%; background:{r.avg >= 2
										? 'var(--ch-profit)'
										: r.avg >= 1.5
											? 'var(--ch-warn-light)'
											: 'var(--ch-violet-light)'}"
								></div>
								<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]"
									>{r.avg.toFixed(2)}×</span
								>
							</div>
							<span class="w-16 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
								>{r.count} runs</span
							>
						</div>
					{/each}
				</div>
				<p class="mt-2 text-[10px] text-muted-foreground">
					Green ≥2× · yellow 1.5–2× · PF &gt;1 = system earns more than it loses · which timeframe
					has best gross P&amp;L ratio?
				</p>
			</section>
		{/if}
		{#if runSortinoStrategyRanking}
			<section class="flex flex-col rounded-xl border border-border bg-card p-4">
				<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
					Avg Sortino by Strategy
				</h3>
				<svg
					viewBox="0 0 {runSortinoStrategyRanking.W} {runSortinoStrategyRanking.H}"
					class="w-full"
					style="height:{runSortinoStrategyRanking.H}px"
				>
					<line
						x1={runSortinoStrategyRanking.zeroX}
						y1="0"
						x2={runSortinoStrategyRanking.zeroX}
						y2={runSortinoStrategyRanking.H}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
					/>
					{#each runSortinoStrategyRanking.rows as row, i (i)}
						{@const y = runSortinoStrategyRanking.PAD + i * 18}
						{@const bw = Math.max(
							2,
							(Math.abs(row.avg) / runSortinoStrategyRanking.maxAbs) *
								(runSortinoStrategyRanking.barMaxW / 2)
						)}
						{@const x =
							row.avg >= 0 ? runSortinoStrategyRanking.zeroX : runSortinoStrategyRanking.zeroX - bw}
						{@const color =
							row.avg >= 1
								? 'var(--ch-profit)'
								: row.avg >= 0
									? 'var(--ch-teal)'
									: 'var(--ch-loss)'}
						<text
							x={runSortinoStrategyRanking.PAD}
							y={y + 12}
							font-size="7"
							fill="var(--ch-axis-strong)">{row.name}</text
						>
						<rect {x} {y} width={bw} height="13" rx="2" fill={color} />
						<text
							x={row.avg >= 0
								? runSortinoStrategyRanking.zeroX + bw + 2
								: runSortinoStrategyRanking.zeroX - bw - 2}
							y={y + 12}
							text-anchor={row.avg >= 0 ? 'start' : 'end'}
							font-size="6"
							fill={color}>{row.avg.toFixed(2)}</text
						>
					{/each}
				</svg>
				<p class="mt-1 text-[9px] text-muted-foreground">
					Avg Sortino ratio per strategy · green≥1 · teal 0-1 · red&lt;0 · diverging from zero ·
					Sortino measures return per unit of downside deviation
				</p>
			</section>
		{/if}
		{#if runProfitVsSharpeScatter}
			<section class="flex flex-col rounded-xl border border-border bg-card p-4">
				<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
					Profit% vs Sharpe Scatter
				</h3>
				<svg
					viewBox="0 0 {runProfitVsSharpeScatter.W} {runProfitVsSharpeScatter.H}"
					class="w-full"
					style="height:{runProfitVsSharpeScatter.H}px"
				>
					<line
						x1={runProfitVsSharpeScatter.zeroX}
						y1={runProfitVsSharpeScatter.PAD}
						x2={runProfitVsSharpeScatter.zeroX}
						y2={runProfitVsSharpeScatter.H - runProfitVsSharpeScatter.PAD}
						stroke="var(--ch-axis-faint)"
						stroke-width="0.7"
						stroke-dasharray="3,2"
					/>
					<line
						x1={runProfitVsSharpeScatter.PAD}
						y1={runProfitVsSharpeScatter.zeroY}
						x2={runProfitVsSharpeScatter.W - runProfitVsSharpeScatter.PAD}
						y2={runProfitVsSharpeScatter.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="0.7"
						stroke-dasharray="3,2"
					/>
					{#each runProfitVsSharpeScatter.pts as p, _i (_i)}
						{@const cx = runProfitVsSharpeScatter.toX(p.p)}
						{@const cy = runProfitVsSharpeScatter.toY(p.s)}
						{@const color =
							p.p > 0 && p.s > 0
								? 'var(--ch-profit)'
								: p.p > 0
									? 'var(--ch-warn)'
									: 'var(--ch-loss-light)'}
						<circle {cx} {cy} r="2.5" fill={color} />
					{/each}
				</svg>
				<p class="mt-1 text-[9px] text-muted-foreground">
					Scatter of profit% (X) vs Sharpe ratio (Y) · green=both positive · yellow=profit only ·
					red=losing · top-right = ideal — high absolute return with strong risk-adjusted quality
				</p>
			</section>
		{/if}
		{#if runAvgTradeCountByTFBars}
			<section class="flex flex-col rounded-xl border border-border bg-card p-4">
				<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
					Avg Trade Count by Timeframe
				</h3>
				<svg
					viewBox="0 0 {runAvgTradeCountByTFBars.W} {runAvgTradeCountByTFBars.H}"
					class="w-full"
					style="height:{runAvgTradeCountByTFBars.H}px"
				>
					{#each runAvgTradeCountByTFBars.rows as row, i (i)}
						{@const y = runAvgTradeCountByTFBars.PAD + i * 20}
						{@const bw = Math.max(
							2,
							(row.avg / runAvgTradeCountByTFBars.maxAvg) * runAvgTradeCountByTFBars.barMaxW
						)}
						<text
							x={runAvgTradeCountByTFBars.PAD}
							y={y + 13}
							font-size="8"
							fill="var(--ch-axis-strong)">{row.tf}</text
						>
						<rect
							x={runAvgTradeCountByTFBars.PAD + 38}
							{y}
							width={bw}
							height="14"
							rx="2"
							fill="var(--ch-teal)"
						/>
						<text
							x={runAvgTradeCountByTFBars.PAD + 38 + bw + 3}
							y={y + 12}
							font-size="7"
							fill="var(--ch-teal-strong)">{row.avg.toFixed(0)}</text
						>
					{/each}
				</svg>
				<p class="mt-1 text-[9px] text-muted-foreground">
					Avg trade count per run by timeframe · teal bars · shorter timeframes (5m/15m) typically
					generate more trades · higher count = more statistical significance
				</p>
			</section>
		{/if}
		{#if runWinRateCDF}
			<section class="flex flex-col rounded-xl border border-border bg-card p-4">
				<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
					Win Rate% CDF (All Archive Runs)
				</h3>
				<svg
					viewBox="0 0 {runWinRateCDF.W} {runWinRateCDF.H}"
					class="w-full"
					style="height:{runWinRateCDF.H}px"
				>
					<line
						x1={runWinRateCDF.p50X}
						y1={runWinRateCDF.PAD}
						x2={runWinRateCDF.p50X}
						y2={runWinRateCDF.H - runWinRateCDF.PAD}
						stroke="var(--ch-axis-faint)"
						stroke-width="0.7"
						stroke-dasharray="3,2"
					/>
					<polyline
						points={runWinRateCDF.polyline}
						fill="none"
						stroke="var(--ch-profit-strong)"
						stroke-width="1.5"
						stroke-linejoin="round"
					/>
					<text
						x={runWinRateCDF.PAD}
						y={runWinRateCDF.H - 2}
						font-size="6"
						fill="var(--ch-axis-muted)">{runWinRateCDF.minV}%</text
					>
					<text
						x={runWinRateCDF.W - runWinRateCDF.PAD}
						y={runWinRateCDF.H - 2}
						text-anchor="end"
						font-size="6"
						fill="var(--ch-axis-muted)">{runWinRateCDF.maxV}%</text
					>
					<text
						x={runWinRateCDF.W / 2}
						y={runWinRateCDF.PAD + 8}
						text-anchor="middle"
						font-size="7"
						fill="var(--ch-profit-strong)">median {runWinRateCDF.median}%</text
					>
				</svg>
				<p class="mt-1 text-[9px] text-muted-foreground">
					CDF of win rate% across all archive backtest runs · green S-curve · dashed median line ·
					right-skewed = most strategies exceed 50% win rate
				</p>
			</section>
		{/if}
	</div>
</main>
