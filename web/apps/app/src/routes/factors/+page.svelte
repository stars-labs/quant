<script lang="ts">
	import type { PageData } from './$types';
	import ChartInfo from '$lib/components/chart-info.svelte';
	import type { Lang } from '$lib/i18n';

	let { data }: { data: PageData } = $props();
	// ChartInfo references {lang} in every chart h2; without this declaration
	// SSR throws "lang is not defined" before any markup renders.
	const lang = $derived<Lang>(data.lang ?? 'zh');
	// Hold-time metrics referenced by one optional chart are NOT part of the
	// api.backtest_runs row (legacy payloads only) — typed optional so the
	// chart degrades to "no data" instead of failing the type-check.
	type RunRow = (typeof data.runs)[number] & { holding_avg_hours?: number | null };
	const runs = $derived(data.runs as RunRow[]);
	// `factors` is referenced bare by analytics blocks expecting a derived
	// per-factor stats array; the existing per-factor computation lives in
	// `factorStats` and the loader doesn't ship a precomputed `factors`. Stub
	// to an empty array so the bare-`factors` guards return null cleanly.
	const factors = $derived<FactorStat[]>([]);

	interface FactorStat {
		factor: string;
		count: number;
		median_profit: number;
		avg_profit: number;
		median_sharpe: number | null;
		median_calmar: number | null;
		avg_sharpe: number | null;
		avg_calmar: number | null;
		avg_sortino: number | null;
		/** Mean win rate, percent scale (0–100). */
		avg_win_rate: number | null;
		avg_profit_factor: number | null;
		avg_dd: number;
		win_rate: number;
		strategies: string[];
		stddev_profit?: number | null;
		/** Never populated — factors aggregate across timeframes (legacy fields). */
		timeframe?: string | null;
		first_seen?: string | null;
	}

	interface ComboPair {
		a: string;
		b: string;
		count: number;
		median_profit: number;
	}

	function median(arr: number[]): number {
		if (arr.length === 0) return 0;
		const s = [...arr].sort((a, b) => a - b);
		const m = Math.floor(s.length / 2);
		return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
	}

	function mean(arr: number[]): number {
		if (arr.length === 0) return 0;
		return arr.reduce((a, b) => a + b, 0) / arr.length;
	}

	type SortKey = 'profit' | 'sharpe' | 'calmar' | 'count' | 'dd';
	let sortKey = $state<SortKey>('profit');
	let filterText = $state('');

	const factorStats = $derived.by((): FactorStat[] => {
		const map = new Map<
			string,
			{
				profits: number[];
				sharpes: number[];
				calmars: number[];
				sortinos: number[];
				profitFactors: number[];
				dds: number[];
				winRates: number[];
				strategies: Set<string>;
			}
		>();

		for (const run of data.runs) {
			if (!run.factors || run.factors.length === 0) continue;
			for (const factor of run.factors) {
				if (!map.has(factor)) {
					map.set(factor, {
						profits: [],
						sharpes: [],
						calmars: [],
						sortinos: [],
						profitFactors: [],
						dds: [],
						winRates: [],
						strategies: new Set()
					});
				}
				const entry = map.get(factor)!;
				if (run.total_profit_pct != null) entry.profits.push(run.total_profit_pct);
				if (run.sharpe != null) entry.sharpes.push(run.sharpe);
				if (run.calmar != null) entry.calmars.push(run.calmar);
				if (run.sortino != null) entry.sortinos.push(run.sortino);
				if (run.profit_factor != null) entry.profitFactors.push(run.profit_factor);
				if (run.max_drawdown_pct != null) entry.dds.push(run.max_drawdown_pct);
				if (run.win_rate_pct != null) entry.winRates.push(run.win_rate_pct);
				entry.strategies.add(run.strategy);
			}
		}

		const stats: FactorStat[] = [];
		for (const [factor, entry] of map.entries()) {
			stats.push({
				factor,
				count: entry.profits.length,
				median_profit: median(entry.profits),
				avg_profit: mean(entry.profits),
				median_sharpe: entry.sharpes.length > 0 ? median(entry.sharpes) : null,
				median_calmar: entry.calmars.length > 0 ? median(entry.calmars) : null,
				avg_sharpe: entry.sharpes.length > 0 ? mean(entry.sharpes) : null,
				avg_calmar: entry.calmars.length > 0 ? mean(entry.calmars) : null,
				avg_sortino: entry.sortinos.length > 0 ? mean(entry.sortinos) : null,
				avg_win_rate: entry.winRates.length > 0 ? mean(entry.winRates) : null,
				avg_profit_factor: entry.profitFactors.length > 0 ? mean(entry.profitFactors) : null,
				avg_dd: mean(entry.dds),
				win_rate: mean(entry.winRates),
				strategies: [...entry.strategies].sort()
			});
		}

		return stats.sort((a, b) => b.median_profit - a.median_profit);
	});

	const sortedStats = $derived.by((): FactorStat[] => {
		const filtered = filterText
			? factorStats.filter((s) => s.factor.toLowerCase().includes(filterText.toLowerCase()))
			: factorStats;

		return [...filtered].sort((a, b) => {
			switch (sortKey) {
				case 'profit':
					return b.median_profit - a.median_profit;
				case 'sharpe':
					return (b.median_sharpe ?? -Infinity) - (a.median_sharpe ?? -Infinity);
				case 'calmar':
					return (b.median_calmar ?? -Infinity) - (a.median_calmar ?? -Infinity);
				case 'count':
					return b.count - a.count;
				case 'dd':
					return a.avg_dd - b.avg_dd; // lower dd is better
				default:
					return 0;
			}
		});
	});

	// Column max values for bar normalization
	const maxProfit = $derived(Math.max(...factorStats.map((s) => Math.abs(s.median_profit)), 0.001));
	const maxSharpe = $derived(Math.max(...factorStats.map((s) => s.median_sharpe ?? 0), 0.001));
	const maxCalmar = $derived(Math.max(...factorStats.map((s) => s.median_calmar ?? 0), 0.001));
	const maxDd = $derived(Math.max(...factorStats.map((s) => s.avg_dd), 0.001));
	const maxWinRate = $derived(Math.max(...factorStats.map((s) => s.win_rate), 0.001));

	// Top combos: pairs of factors that co-occur most
	const topCombos = $derived.by((): ComboPair[] => {
		const comboMap = new Map<string, { a: string; b: string; profits: number[] }>();

		for (const run of data.runs) {
			if (!run.factors || run.factors.length < 2) continue;
			const sorted = [...run.factors].sort();
			for (let i = 0; i < sorted.length; i++) {
				for (let j = i + 1; j < sorted.length; j++) {
					const key = `${sorted[i]}|${sorted[j]}`;
					if (!comboMap.has(key)) {
						comboMap.set(key, { a: sorted[i], b: sorted[j], profits: [] });
					}
					if (run.total_profit_pct != null) {
						comboMap.get(key)!.profits.push(run.total_profit_pct);
					}
				}
			}
		}

		const combos: ComboPair[] = [];
		for (const [, entry] of comboMap.entries()) {
			combos.push({
				a: entry.a,
				b: entry.b,
				count: entry.profits.length,
				median_profit: median(entry.profits)
			});
		}

		return combos.sort((a, b) => b.count - a.count).slice(0, 10);
	});

	// Factor × metric heatmap (top 15 factors by count)
	const HEATMAP_METRICS = [
		{ key: 'median_profit' as keyof FactorStat, label: 'Profit%', higher: true },
		{ key: 'median_sharpe' as keyof FactorStat, label: 'Sharpe', higher: true },
		{ key: 'median_calmar' as keyof FactorStat, label: 'Calmar', higher: true },
		{ key: 'win_rate' as keyof FactorStat, label: 'WinRate', higher: true },
		{ key: 'avg_dd' as keyof FactorStat, label: 'AvgDD', higher: false }
	];
	const heatmapRows = $derived.by(() => {
		const rows = [...factorStats].sort((a, b) => b.count - a.count).slice(0, 15);
		// Per-metric min/max for normalization
		const ranges = HEATMAP_METRICS.map((m) => {
			const vals = rows.map((r) => Number(r[m.key] ?? 0));
			return { min: Math.min(...vals), max: Math.max(...vals) };
		});
		return rows.map((r) => ({
			factor: r.factor,
			count: r.count,
			cells: HEATMAP_METRICS.map((m, i) => {
				const v = Number(r[m.key] ?? 0);
				const { min, max } = ranges[i];
				const norm = max === min ? 0.5 : (v - min) / (max - min);
				const score = m.higher ? norm : 1 - norm;
				return { v, score, raw: r[m.key] };
			})
		}));
	});

	function heatCell(score: number): string {
		if (score > 0.75) return 'bg-green-500/70';
		if (score > 0.55) return 'bg-green-700/50';
		if (score > 0.45) return 'bg-muted/20';
		if (score > 0.25) return 'bg-red-700/40';
		return 'bg-red-500/60';
	}

	// Factor WR sparklines over time (split runs into 4 quarters by imported_at)
	const factorTrend = $derived.by(() => {
		const runsWithDate = data.runs
			.filter((r) => r.factors?.length && r.imported_at && r.win_rate_pct != null)
			.sort((a, b) => a.imported_at.localeCompare(b.imported_at));
		if (runsWithDate.length < 8) return null;
		const Q = 4;
		const step = Math.ceil(runsWithDate.length / Q);
		const quarters = Array.from({ length: Q }, (_, qi) =>
			runsWithDate.slice(qi * step, (qi + 1) * step)
		);
		// Top 8 factors by count
		const topFactors = [...factorStats]
			.sort((a, b) => b.count - a.count)
			.slice(0, 8)
			.map((f) => f.factor);
		return topFactors
			.map((factor) => {
				const pts = quarters.map((q) => {
					const subset = q.filter((r) => r.factors!.includes(factor));
					if (subset.length === 0) return null;
					return subset.reduce((sum, r) => sum + (r.win_rate_pct ?? 0), 0) / subset.length;
				});
				const valid = pts.filter((v): v is number => v != null);
				if (valid.length < 2) return null;
				const trend = valid[valid.length - 1] - valid[0];
				return { factor, pts, trend, latest: valid[valid.length - 1] };
			})
			.filter(Boolean) as {
			factor: string;
			pts: (number | null)[];
			trend: number;
			latest: number;
		}[];
	});

	// Avg drawdown leaderboard (lower dd = better, min 3 runs)
	const ddLeaderboard = $derived.by(() => {
		const rows = factorStats
			.filter((f) => f.count >= 3 && f.avg_dd > 0)
			.map((f) => ({ factor: f.factor, avgDd: f.avg_dd, count: f.count }))
			.sort((a, b) => a.avgDd - b.avgDd)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxDd = Math.max(1, ...rows.map((r) => r.avgDd));
		return rows.map((r) => ({ ...r, barPct: (r.avgDd / maxDd) * 100 }));
	});

	// Factor Calmar Leaderboard: sorted by median_calmar (return/maxDD)
	const calmarLeaderboard = $derived.by(() => {
		const rows = factorStats
			.filter((f) => f.count >= 2 && f.median_calmar != null && f.median_calmar > 0)
			.map((f) => ({
				factor: f.factor,
				calmar: f.median_calmar!,
				count: f.count,
				profit: f.avg_profit
			}))
			.sort((a, b) => b.calmar - a.calmar)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxCalmar = Math.max(0.01, ...rows.map((r) => r.calmar));
		return rows.map((r) => ({ ...r, barPct: (r.calmar / maxCalmar) * 100 }));
	});

	// Win Rate vs Profit scatter: each factor as a dot, x=avg_profit, y=win_rate
	const wrProfitScatter = $derived.by(() => {
		const pts = factorStats.filter(
			(f) => f.count >= 2 && f.win_rate != null && f.avg_profit != null
		);
		if (pts.length < 4) return null;
		const xs = pts.map((f) => f.avg_profit!);
		const ys = pts.map((f) => f.win_rate!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs);
		const yMin = Math.min(0, ...ys),
			yMax = Math.max(...ys, 0.001);
		const W = 380,
			H = 140,
			PAD = 20;
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin || 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin || 0.001)) * (H - PAD * 2);
		const zeroX = toX(0);
		const fiftyY = toY(0.5);
		const dots = pts.map((f) => ({
			factor: f.factor,
			x: toX(f.avg_profit!),
			y: toY(f.win_rate!),
			count: f.count,
			profit: f.avg_profit!,
			wr: f.win_rate!,
			gold: f.avg_profit! > 0 && f.win_rate! > 0.5
		}));
		return { dots, W, H, PAD, zeroX, fiftyY, xMin, xMax, yMin, yMax };
	});

	// Factor co-occurrence: top-10 factors, count how often each pair appears together
	const factorCoOccurrence = $derived.by(() => {
		const top = [...factorStats]
			.sort((a, b) => b.count - a.count)
			.slice(0, 8)
			.map((f) => f.factor);
		if (top.length < 3) return null;
		const matrix = new Map<string, number>();
		for (const run of data.runs) {
			if (!run.factors || run.factors.length < 2) continue;
			const relevant = run.factors.filter((f) => top.includes(f));
			for (let i = 0; i < relevant.length; i++) {
				for (let j = i + 1; j < relevant.length; j++) {
					const key = [relevant[i], relevant[j]].sort().join('||');
					matrix.set(key, (matrix.get(key) ?? 0) + 1);
				}
			}
		}
		const pairs = [...matrix.entries()]
			.map(([key, count]) => {
				const [a, b] = key.split('||');
				return { a, b, count };
			})
			.sort((x, y) => y.count - x.count)
			.slice(0, 10);
		const maxCount = Math.max(1, ...pairs.map((p) => p.count));
		return { pairs, maxCount, top };
	});

	// Factor win rate leaderboard: ranked by % of profitable runs
	const factorWinRateLeaderboard = $derived.by(() => {
		const rows = factorStats
			.filter((f) => f.count >= 3 && f.win_rate != null)
			.map((f) => ({ factor: f.factor, wr: f.win_rate, count: f.count, profit: f.avg_profit }))
			.sort((a, b) => b.wr - a.wr)
			.slice(0, 14);
		if (rows.length < 3) return null;
		return rows;
	});

	// Factor strategy breadth: how many unique strategies each factor appears in
	const strategyBreadth = $derived.by(() => {
		const rows = [...factorStats]
			.filter((f) => f.strategies.length >= 1)
			.map((f) => ({
				factor: f.factor,
				stratCount: f.strategies.length,
				count: f.count,
				profit: f.avg_profit
			}))
			.sort((a, b) => b.stratCount - a.stratCount)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxStrat = Math.max(1, ...rows.map((r) => r.stratCount));
		return rows.map((r) => ({ ...r, barPct: (r.stratCount / maxStrat) * 100 }));
	});

	// Avg profit by factor count: runs with 1, 2, 3, 4+ factors
	const avgProfitByFactorCount = $derived.by(() => {
		const runs = data.runs.filter(
			(r) => r.factors && r.factors.length > 0 && r.total_profit_pct != null
		);
		if (runs.length < 5) return null;
		const buckets: Record<string, { sum: number; count: number; wins: number }> = {
			'1': { sum: 0, count: 0, wins: 0 },
			'2': { sum: 0, count: 0, wins: 0 },
			'3': { sum: 0, count: 0, wins: 0 },
			'4+': { sum: 0, count: 0, wins: 0 }
		};
		for (const r of runs) {
			const n = r.factors!.length;
			const key = n >= 4 ? '4+' : String(n);
			buckets[key].sum += r.total_profit_pct!;
			buckets[key].count++;
			if (r.total_profit_pct! > 0) buckets[key].wins++;
		}
		const rows = Object.entries(buckets)
			.filter(([, v]) => v.count > 0)
			.map(([label, v]) => ({ label, count: v.count, avg: v.sum / v.count, wr: v.wins / v.count }));
		if (rows.length < 2) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.avg)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.avg) / maxAbs) * 100 }));
	});

	// KPI summary
	// Top 5 factors monthly avg profit trend: is each factor getting better or worse over time?
	const factorMonthlyTrend = $derived.by(() => {
		const topFactors = [...factorStats]
			.sort((a, b) => b.count - a.count)
			.slice(0, 5)
			.map((f) => f.factor);
		const runs = data.runs.filter(
			(r) => r.factors?.length && r.started_at && r.total_profit_pct != null
		);
		if (runs.length < 6) return null;
		const monthSet = new Set<string>();
		for (const r of runs) monthSet.add(r.started_at!.slice(0, 7));
		const months = [...monthSet].sort().slice(-8);
		if (months.length < 2) return null;
		const series = topFactors
			.map((factor) => {
				const pts = months.map((m) => {
					const bucket = runs.filter(
						(r) => r.started_at!.startsWith(m) && r.factors!.includes(factor)
					);
					if (bucket.length === 0) return null;
					return bucket.reduce((s, r) => s + r.total_profit_pct!, 0) / bucket.length;
				});
				return { factor, pts };
			})
			.filter((s) => s.pts.some((v) => v != null));
		if (series.length < 2) return null;
		const allVals = series.flatMap((s) => s.pts).filter((v): v is number => v != null);
		const vMin = Math.min(...allVals, 0),
			vMax = Math.max(...allVals, 0.001);
		const W = 520,
			H = 100,
			PAD = 8;
		const toX = (i: number) => PAD + (i / Math.max(1, months.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - vMin) / (vMax - vMin || 0.001)) * (H - PAD * 2);
		const COLORS = [
			'var(--ch-violet-strong)',
			'var(--ch-profit-strong)',
			'var(--ch-loss-strong)',
			'var(--ch-warn)',
			'var(--ch-violet-light)'
		];
		const zeroY = toY(0);
		const lines = series.map((s, si) => {
			const validPts = s.pts.map((v, i) =>
				v != null ? `${toX(i).toFixed(1)},${toY(v).toFixed(1)}` : null
			);
			const segments: string[] = [];
			let seg: string[] = [];
			for (const pt of validPts) {
				if (pt) {
					seg.push(pt);
				} else {
					if (seg.length > 1) segments.push(seg.join(' '));
					seg = [];
				}
			}
			if (seg.length > 1) segments.push(seg.join(' '));
			return { factor: s.factor, segments, color: COLORS[si] };
		});
		return { lines, months, W, H, PAD, zeroY };
	});

	// Low drawdown leaderboard: factors with best (lowest) avg drawdown, min 5 runs
	// Factor profit-factor leaderboard: avg profit_factor per factor (min 5 runs)
	const factorProfitFactorLeaderboard = $derived.by(() => {
		const runsWithPF = data.runs.filter(
			(r) =>
				r.factors?.length && r.profit_factor != null && r.profit_factor > 0 && r.profit_factor < 100
		);
		if (runsWithPF.length < 5) return null;
		const map = new Map<string, { sum: number; count: number }>();
		for (const r of runsWithPF) {
			for (const f of r.factors!) {
				if (!map.has(f)) map.set(f, { sum: 0, count: 0 });
				const v = map.get(f)!;
				v.sum += r.profit_factor!;
				v.count++;
			}
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.count >= 5)
			.map(([factor, v]) => ({ factor, avgPF: v.sum / v.count, count: v.count }))
			.sort((a, b) => b.avgPF - a.avgPF)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxPF = Math.max(0.01, ...rows.map((r) => r.avgPF));
		return rows.map((r) => ({ ...r, barPct: (r.avgPF / maxPF) * 100 }));
	});

	// Factor Sharpe leaderboard: top factors by median Sharpe (min 5 runs)
	const factorSharpeLeaderboard = $derived.by(() => {
		const rows = factorStats
			.filter((f) => f.count >= 5 && f.median_sharpe != null && Number.isFinite(f.median_sharpe))
			.map((f) => ({
				factor: f.factor,
				sharpe: f.median_sharpe!,
				count: f.count,
				profit: f.avg_profit
			}))
			.sort((a, b) => b.sharpe - a.sharpe)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.sharpe)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.sharpe) / maxAbs) * 100 }));
	});

	// Factor Calmar leaderboard: top factors by median Calmar ratio (min 5 runs)
	const factorCalmarLeaderboard = $derived.by(() => {
		const rows = factorStats
			.filter(
				(f) =>
					f.count >= 5 && f.median_calmar != null && f.median_calmar > 0 && f.median_calmar < 200
			)
			.map((f) => ({
				factor: f.factor,
				calmar: f.median_calmar!,
				count: f.count,
				profit: f.avg_profit
			}))
			.sort((a, b) => b.calmar - a.calmar)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxCalmar = Math.max(0.01, ...rows.map((r) => r.calmar));
		return rows.map((r) => ({ ...r, barPct: (r.calmar / maxCalmar) * 100 }));
	});

	const lowDrawdownLeaderboard = $derived.by(() => {
		const rows = factorStats
			.filter((f) => f.count >= 5 && f.avg_dd != null)
			.map((f) => ({
				factor: f.factor,
				dd: f.avg_dd,
				count: f.count,
				profit: f.avg_profit,
				wr: f.win_rate
			}))
			.sort((a, b) => a.dd - b.dd)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxDd = Math.max(0.01, ...rows.map((r) => r.dd));
		return rows.map((r) => ({ ...r, barPct: (r.dd / maxDd) * 100 }));
	});

	// Factor profit volatility: std dev of profit% per factor — lower = more consistent
	const factorProfitVolatility = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const run of data.runs) {
			if (!run.factors || run.total_profit_pct == null) continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, []);
				map.get(f)!.push(run.total_profit_pct);
			}
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 5)
			.map(([factor, vals]) => {
				const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
				const std = Math.sqrt(vals.reduce((s, v) => s + (v - avg) ** 2, 0) / vals.length);
				return { factor, std, avg, count: vals.length };
			})
			.sort((a, b) => a.std - b.std)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxStd = Math.max(0.01, ...rows.map((r) => r.std));
		return rows.map((r) => ({ ...r, barPct: (r.std / maxStd) * 100 }));
	});

	// Factor Sortino leaderboard: median Sortino per factor (distinct from Sharpe and Calmar leaderboards)
	const factorSortinoLeaderboard = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const run of data.runs) {
			if (!run.factors || run.sortino == null || !isFinite(run.sortino) || run.sortino > 200)
				continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, []);
				map.get(f)!.push(run.sortino);
			}
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 5)
			.map(([factor, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const med = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
				return { factor, sortino: med, count: vals.length };
			})
			.sort((a, b) => b.sortino - a.sortino)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.sortino)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.sortino) / maxAbs) * 100 }));
	});

	// Factor win count per factor — how many distinct winning runs include this factor
	const factorWinCount = $derived.by(() => {
		const map = new Map<string, { wins: number; total: number }>();
		for (const run of data.runs) {
			if (!run.factors) continue;
			const isWin = run.total_profit_pct != null && run.total_profit_pct > 0;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, { wins: 0, total: 0 });
				const e = map.get(f)!;
				e.total++;
				if (isWin) e.wins++;
			}
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.total >= 5)
			.map(([factor, v]) => ({ factor, wins: v.wins, total: v.total, wr: v.wins / v.total }))
			.sort((a, b) => b.wr - a.wr)
			.slice(0, 12);
		if (rows.length < 3) return null;
		return rows;
	});

	// Factor avg holding time: which factors correlate with longer or shorter trades?
	const factorAvgHoldingTime = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const run of runs) {
			if (
				!run.factors ||
				run.holding_avg_hours == null ||
				!isFinite(run.holding_avg_hours) ||
				run.holding_avg_hours <= 0 ||
				run.holding_avg_hours > 10000
			)
				continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, []);
				map.get(f)!.push(run.holding_avg_hours);
			}
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 5)
			.map(([factor, vals]) => ({
				factor,
				avg: vals.reduce((a, b) => a + b, 0) / vals.length,
				count: vals.length
			}))
			.sort((a, b) => a.avg - b.avg)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxAvg = Math.max(0.01, rows[rows.length - 1].avg);
		return rows.map((r) => ({ ...r, barPct: (r.avg / maxAvg) * 100 }));
	});

	const factorDrawdownSpread = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const run of data.runs) {
			if (
				!run.factors ||
				run.max_drawdown_pct == null ||
				!isFinite(run.max_drawdown_pct) ||
				run.max_drawdown_pct < 0
			)
				continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, []);
				map.get(f)!.push(run.max_drawdown_pct);
			}
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 5)
			.map(([factor, vals]) => {
				const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
				const variance = vals.reduce((s, v) => s + (v - avg) ** 2, 0) / vals.length;
				return { factor, std: Math.sqrt(variance), avg, count: vals.length };
			})
			.sort((a, b) => a.std - b.std)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxStd = Math.max(0.01, rows[rows.length - 1].std);
		return rows.map((r) => ({ ...r, barPct: (r.std / maxStd) * 100 }));
	});

	const factorTopTimeframes = $derived.by(() => {
		const map = new Map<string, Map<string, number>>();
		for (const run of data.runs) {
			if (!run.factors || !run.timeframe) continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, new Map());
				const tfMap = map.get(f)!;
				tfMap.set(run.timeframe, (tfMap.get(run.timeframe) ?? 0) + 1);
			}
		}
		const rows = [...map.entries()]
			.filter(([, tfMap]) => [...tfMap.values()].reduce((a, b) => a + b, 0) >= 5)
			.map(([factor, tfMap]) => {
				const total = [...tfMap.values()].reduce((a, b) => a + b, 0);
				const topTfs = [...tfMap.entries()]
					.sort((a, b) => b[1] - a[1])
					.slice(0, 3)
					.map(([tf, cnt]) => ({ tf, pct: (cnt / total) * 100 }));
				return { factor, topTfs, total };
			})
			.sort((a, b) => b.total - a.total)
			.slice(0, 10);
		if (rows.length < 3) return null;
		return rows;
	});

	const factorSortinoVsCalmar = $derived.by(() => {
		const map = new Map<string, { sortinos: number[]; calmars: number[] }>();
		for (const run of data.runs) {
			if (
				!run.factors ||
				run.sortino == null ||
				!isFinite(run.sortino) ||
				run.sortino < -50 ||
				run.calmar == null ||
				!isFinite(run.calmar) ||
				run.calmar < -20 ||
				run.calmar > 50
			)
				continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, { sortinos: [], calmars: [] });
				const e = map.get(f)!;
				e.sortinos.push(run.sortino);
				e.calmars.push(run.calmar);
			}
		}
		const pts = [...map.entries()]
			.filter(([, v]) => v.sortinos.length >= 5)
			.map(([factor, v]) => ({
				factor,
				avgSortino: v.sortinos.reduce((a, b) => a + b, 0) / v.sortinos.length,
				avgCalmar: v.calmars.reduce((a, b) => a + b, 0) / v.calmars.length,
				count: v.sortinos.length
			}));
		if (pts.length < 4) return null;
		const W = 560,
			H = 110,
			PAD = 10;
		const xs = pts.map((p) => p.avgSortino),
			ys = pts.map((p) => p.avgCalmar);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 0.1);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.1);
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const maxCount = Math.max(1, ...pts.map((p) => p.count));
		const dots = pts.map((p) => ({
			cx: toX(p.avgSortino),
			cy: toY(p.avgCalmar),
			r: 2.5 + Math.min(4, (p.count / maxCount) * 4),
			color:
				p.avgSortino >= 1 && p.avgCalmar >= 1
					? 'var(--ch-profit)'
					: p.avgSortino >= 0 && p.avgCalmar >= 0
						? 'var(--ch-warn)'
						: 'var(--ch-loss-light)',
			title: `${p.factor} · sortino ${p.avgSortino.toFixed(2)} · calmar ${p.avgCalmar.toFixed(2)} · ${p.count} runs`
		}));
		return { dots, W, H, PAD, xMin, xMax, yMin, yMax };
	});

	// Distinct pair coverage per factor: how many unique pairs appear in runs using each factor (distinct from factorTopTimeframes, factorDrawdownSpread, factorWinCount)
	const factorPairCoverage = $derived.by(() => {
		const map = new Map<string, Set<string>>();
		for (const run of data.runs) {
			if (!run.factors || !run.pairs) continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, new Set());
				for (const p of run.pairs) map.get(f)!.add(p);
			}
		}
		const rows = [...map.entries()]
			.filter(([, pairSet]) => pairSet.size >= 1)
			.map(([factor, pairSet]) => ({ factor, pairCount: pairSet.size }))
			.sort((a, b) => b.pairCount - a.pairCount)
			.slice(0, 15);
		if (rows.length < 3) return null;
		const maxCount = Math.max(1, ...rows.map((r) => r.pairCount));
		return rows.map((r) => ({ ...r, barPct: (r.pairCount / maxCount) * 100 }));
	});

	// Best single run profit% per factor: peak performance for each factor's best-case scenario (distinct from factorWinCount, factorCalmarLeaderboard, factorSortinoLeaderboard, factorProfitFactorLeaderboard)
	const factorBestRunLeaderboard = $derived.by(() => {
		const map = new Map<string, { best: number; bestStrategy: string; bestTf: string | null }>();
		for (const run of data.runs) {
			if (!run.factors || run.total_profit_pct == null || !isFinite(run.total_profit_pct)) continue;
			for (const f of run.factors) {
				const cur = map.get(f);
				if (!cur || run.total_profit_pct > cur.best) {
					map.set(f, {
						best: run.total_profit_pct,
						bestStrategy: run.strategy,
						bestTf: run.timeframe
					});
				}
			}
		}
		const rows = [...map.entries()]
			.map(([factor, v]) => ({ factor, ...v }))
			.sort((a, b) => b.best - a.best)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.best)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.best) / maxAbs) * 100 }));
	});

	const factorAvgWinRateRanking = $derived.by(() => {
		const map = new Map<string, { sum: number; count: number }>();
		for (const run of data.runs) {
			if (!run.factors || run.win_rate_pct == null || !isFinite(run.win_rate_pct)) continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, { sum: 0, count: 0 });
				const e = map.get(f)!;
				e.sum += run.win_rate_pct;
				e.count++;
			}
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.count >= 3)
			.map(([factor, v]) => ({ factor, avg: v.sum / v.count, count: v.count }))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxAvg = Math.max(0.01, ...rows.map((r) => r.avg));
		return rows.map((r) => ({ ...r, barPct: (r.avg / maxAvg) * 100 }));
	});

	const factorCalmarRanking = $derived.by(() => {
		const map = new Map<string, { sum: number; count: number }>();
		for (const run of data.runs) {
			if (!run.factors || run.calmar == null || !isFinite(run.calmar) || run.calmar <= 0) continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, { sum: 0, count: 0 });
				const e = map.get(f)!;
				e.sum += run.calmar;
				e.count++;
			}
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.count >= 3)
			.map(([factor, v]) => ({ factor, avg: v.sum / v.count, count: v.count }))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxAvg = Math.max(0.01, ...rows.map((r) => r.avg));
		return rows.map((r) => ({ ...r, barPct: (r.avg / maxAvg) * 100 }));
	});

	const factorRunCountTimeline = $derived.by(() => {
		const map = new Map<string, { sum: number; count: number }>();
		for (const run of data.runs) {
			if (!run.factors || !run.imported_at) continue;
			const ym = run.imported_at.slice(0, 7);
			for (const f of run.factors) {
				const key = `${f}|${ym}`;
				map.set(key, { sum: (map.get(key)?.sum ?? 0) + 1, count: 1 });
			}
		}
		const factorMonths = new Map<string, Map<string, number>>();
		for (const [key, v] of map.entries()) {
			const [factor, ym] = key.split('|');
			if (!factorMonths.has(factor)) factorMonths.set(factor, new Map());
			factorMonths.get(factor)!.set(ym, v.sum);
		}
		const topFactors = [...factorMonths.entries()]
			.map(([f, months]) => ({ f, total: [...months.values()].reduce((a, b) => a + b, 0) }))
			.sort((a, b) => b.total - a.total)
			.slice(0, 5)
			.map((x) => x.f);
		if (topFactors.length < 2) return null;
		const allYms = [...new Set([...map.keys()].map((k) => k.split('|')[1]))].sort();
		if (allYms.length < 2) return null;
		const colors = [
			'var(--ch-profit-strong)',
			'var(--ch-violet-strong)',
			'var(--ch-warn)',
			'var(--ch-loss-strong)',
			'var(--ch-teal-strong)'
		];
		const W = 300,
			H = 60,
			PAD = 6;
		const lines = topFactors.map((f, i) => {
			const months = factorMonths.get(f)!;
			const pts = allYms.map((ym) => months.get(ym) ?? 0);
			const maxPt = Math.max(1, ...pts);
			const poly = pts
				.map((v, j) => {
					const x = PAD + (j / Math.max(1, pts.length - 1)) * (W - PAD * 2);
					const y = H - PAD - (v / maxPt) * (H - PAD * 2);
					return `${x.toFixed(1)},${y.toFixed(1)}`;
				})
				.join(' ');
			return { factor: f, poly, color: colors[i % colors.length], latest: pts[pts.length - 1] };
		});
		return { lines, W, H, PAD, firstYm: allYms[0], lastYm: allYms[allYms.length - 1] };
	});

	const factorProfitEfficiency = $derived.by(() => {
		const rows = factorStats
			.filter((s) => s.avg_dd > 0.01 && s.count >= 3 && s.median_profit != null)
			.map((s) => ({
				factor: s.factor,
				efficiency: s.median_profit / s.avg_dd,
				profit: s.median_profit,
				dd: s.avg_dd,
				count: s.count
			}))
			.sort((a, b) => b.efficiency - a.efficiency)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxEff = Math.max(0.01, ...rows.map((r) => Math.abs(r.efficiency)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.efficiency) / maxEff) * 100 }));
	});

	const factorStrategyCount = $derived.by(() => {
		const rows = factorStats
			.filter((s) => s.strategies && s.strategies.length >= 2)
			.map((s) => ({ factor: s.factor, stratCount: new Set(s.strategies).size, runs: s.count }))
			.sort((a, b) => b.stratCount - a.stratCount)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxCount = Math.max(1, ...rows.map((r) => r.stratCount));
		return rows.map((r) => ({ ...r, barPct: (r.stratCount / maxCount) * 100 }));
	});

	const factorWinRateVsProfit = $derived.by(() => {
		const pts = factorStats.filter(
			(s) =>
				s.win_rate != null &&
				s.median_profit != null &&
				s.count >= 3 &&
				isFinite(s.win_rate) &&
				isFinite(s.median_profit)
		);
		if (pts.length < 5) return null;
		const W = 360,
			H = 80,
			PAD = 8;
		const xs = pts.map((s) => s.win_rate),
			ys = pts.map((s) => s.median_profit);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 0.01);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.01);
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const dots = pts.map((s) => ({
			cx: toX(s.win_rate),
			cy: toY(s.median_profit),
			good: s.median_profit > 0 && s.win_rate > 0.5,
			label: s.factor.slice(0, 8)
		}));
		return { dots, W, H, PAD, xMin, xMax, yMin, yMax };
	});

	const factorProfitPerTrade = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const run of data.runs) {
			if (!run.factors || run.total_profit_pct == null || !isFinite(run.total_profit_pct)) continue;
			const trades = run.total_trades;
			if (trades == null || trades < 1) continue;
			const ppt = run.total_profit_pct / trades;
			if (!isFinite(ppt)) continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, []);
				map.get(f)!.push(ppt);
			}
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 4)
			.map(([factor, vals]) => {
				const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
				return { factor, avgPpt: avg, count: vals.length };
			})
			.sort((a, b) => b.avgPpt - a.avgPpt)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(0.001, ...rows.map((r) => Math.abs(r.avgPpt)));
		return rows.map((r) => ({
			...r,
			barPct: (Math.abs(r.avgPpt) / maxAbs) * 100,
			positive: r.avgPpt >= 0
		}));
	});

	const factorDrawdownVsProfit = $derived.by(() => {
		const pts = factorStats.filter(
			(s) =>
				s.avg_dd != null &&
				isFinite(s.avg_dd) &&
				s.median_profit != null &&
				isFinite(s.median_profit) &&
				s.count >= 3
		);
		if (pts.length < 5) return null;
		const W = 360,
			H = 80,
			PAD = 8;
		const xs = pts.map((s) => s.avg_dd),
			ys = pts.map((s) => s.median_profit);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 0.01);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.01);
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const zeroY = toY(0);
		const dots = pts.map((s) => ({
			cx: toX(s.avg_dd),
			cy: toY(s.median_profit),
			ideal: s.median_profit > 0 && s.avg_dd < (xMax - xMin) * 0.35 + xMin,
			label: s.factor.slice(0, 6)
		}));
		return { dots, W, H, zeroY, xMin, xMax, yMin, yMax };
	});

	const factorTimeframeDiversity = $derived.by(() => {
		const map = new Map<string, Set<string>>();
		for (const run of data.runs) {
			if (!run.factors || !run.timeframe) continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, new Set());
				map.get(f)!.add(run.timeframe);
			}
		}
		const rows = [...map.entries()]
			.filter(([, tfs]) => tfs.size >= 2)
			.map(([factor, tfs]) => ({ factor, tfCount: tfs.size, tfs: [...tfs].sort().join(', ') }))
			.sort((a, b) => b.tfCount - a.tfCount)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxCount = Math.max(1, ...rows.map((r) => r.tfCount));
		return rows.map((r) => ({ ...r, barPct: (r.tfCount / maxCount) * 100 }));
	});

	const factorProfitFactorRanking = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const run of data.runs) {
			if (
				!run.factors ||
				run.profit_factor == null ||
				!isFinite(run.profit_factor) ||
				run.profit_factor < 0 ||
				run.profit_factor > 50
			)
				continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, []);
				map.get(f)!.push(run.profit_factor);
			}
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 4)
			.map(([factor, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const med = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
				return { factor, pf: med, count: vals.length };
			})
			.sort((a, b) => b.pf - a.pf)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxPf = Math.max(1, ...rows.map((r) => r.pf));
		return rows.map((r) => ({ ...r, barPct: (r.pf / maxPf) * 100, good: r.pf >= 1.2 }));
	});

	const factorMaxDrawdownRanking = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const run of data.runs) {
			if (
				!run.factors ||
				run.max_drawdown_pct == null ||
				!isFinite(run.max_drawdown_pct) ||
				run.max_drawdown_pct < 0
			)
				continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, []);
				map.get(f)!.push(run.max_drawdown_pct);
			}
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 4)
			.map(([factor, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const med = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
				return { factor, dd: med, count: vals.length };
			})
			.sort((a, b) => a.dd - b.dd)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxDd = Math.max(0.01, ...rows.map((r) => r.dd));
		return rows.map((r) => ({ ...r, barPct: (r.dd / maxDd) * 100, safe: r.dd < 20 }));
	});

	const factorTradeCountProfile = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const run of data.runs) {
			if (
				!run.factors ||
				run.total_trades == null ||
				!isFinite(run.total_trades) ||
				run.total_trades < 1
			)
				continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, []);
				map.get(f)!.push(run.total_trades);
			}
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 4)
			.map(([factor, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const med = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
				return { factor, trades: med, count: vals.length };
			})
			.sort((a, b) => b.trades - a.trades)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxTrades = Math.max(1, ...rows.map((r) => r.trades));
		return rows.map((r) => ({ ...r, barPct: (r.trades / maxTrades) * 100 }));
	});

	// Factor win/loss ratio: avg wins÷losses per factor (distinct from win_rate = wins/total)
	const factorWinLossRatio = $derived.by(() => {
		const map = new Map<string, { totalWins: number; totalLosses: number; count: number }>();
		for (const run of data.runs) {
			if (!run.factors?.length || run.wins == null || run.losses == null || run.losses === 0)
				continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, { totalWins: 0, totalLosses: 0, count: 0 });
				const e = map.get(f)!;
				e.totalWins += run.wins;
				e.totalLosses += run.losses;
				e.count++;
			}
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.count >= 3 && v.totalLosses > 0)
			.map(([factor, v]) => ({
				factor,
				ratio: v.totalWins / v.totalLosses,
				count: v.count
			}))
			.filter((r) => r.ratio > 0 && r.ratio < 50)
			.sort((a, b) => b.ratio - a.ratio)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxRatio = Math.max(0.01, ...rows.map((r) => r.ratio));
		return rows.map((r) => ({ ...r, barPct: (r.ratio / maxRatio) * 100 }));
	});

	// High-profit hit rate: % of runs >5% profit per factor (quality threshold, distinct from win_rate >0)
	const factorHighProfitHitRate = $derived.by(() => {
		const THRESHOLD = 5;
		const map = new Map<string, { hits: number; total: number }>();
		for (const run of data.runs) {
			if (!run.factors?.length || run.total_profit_pct == null || !isFinite(run.total_profit_pct))
				continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, { hits: 0, total: 0 });
				const e = map.get(f)!;
				e.total++;
				if (run.total_profit_pct > THRESHOLD) e.hits++;
			}
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.total >= 4)
			.map(([factor, v]) => ({ factor, rate: v.hits / v.total, hits: v.hits, total: v.total }))
			.sort((a, b) => b.rate - a.rate)
			.slice(0, 14);
		if (rows.length < 3) return null;
		return rows;
	});

	// Recent vs older half profit comparison for top factors — trend direction
	const factorImprovement = $derived.by(() => {
		const topFactors = [...factorStats]
			.sort((a, b) => b.count - a.count)
			.slice(0, 8)
			.map((f) => f.factor);
		const runsWithDate = data.runs
			.filter(
				(r) =>
					r.factors?.length &&
					r.imported_at &&
					r.total_profit_pct != null &&
					isFinite(r.total_profit_pct!)
			)
			.sort((a, b) => a.imported_at.localeCompare(b.imported_at));
		if (runsWithDate.length < 10) return null;
		const half = Math.floor(runsWithDate.length / 2);
		const older = runsWithDate.slice(0, half);
		const recent = runsWithDate.slice(half);
		const rows = topFactors
			.map((factor) => {
				const oldVals = older
					.filter((r) => r.factors!.includes(factor))
					.map((r) => r.total_profit_pct!);
				const recVals = recent
					.filter((r) => r.factors!.includes(factor))
					.map((r) => r.total_profit_pct!);
				if (oldVals.length < 2 || recVals.length < 2) return null;
				const oldAvg = oldVals.reduce((s, x) => s + x, 0) / oldVals.length;
				const recAvg = recVals.reduce((s, x) => s + x, 0) / recVals.length;
				return { factor, oldAvg, recAvg, delta: recAvg - oldAvg };
			})
			.filter((r): r is NonNullable<typeof r> => r !== null);
		if (rows.length < 3) return null;
		const maxDelta = Math.max(0.01, ...rows.map((r) => Math.abs(r.delta)));
		return rows
			.sort((a, b) => b.delta - a.delta)
			.map((r) => ({ ...r, barPct: (Math.abs(r.delta) / maxDelta) * 100 }));
	});

	const factorProfitRangeSpread = $derived.by(() => {
		const topFactors = [...factorStats]
			.sort((a, b) => b.count - a.count)
			.slice(0, 12)
			.map((f) => f.factor);
		const rows = topFactors
			.map((factor) => {
				const vals = data.runs
					.filter(
						(r) =>
							r.factors?.includes(factor) &&
							r.total_profit_pct != null &&
							isFinite(r.total_profit_pct)
					)
					.map((r) => r.total_profit_pct!);
				if (vals.length < 3) return null;
				const min = Math.min(...vals),
					max = Math.max(...vals);
				const spread = max - min;
				const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
				return { factor, min, max, spread, avg, count: vals.length };
			})
			.filter((r): r is NonNullable<typeof r> => r !== null);
		if (rows.length < 3) return null;
		const maxSpread = Math.max(0.01, ...rows.map((r) => r.spread));
		return rows
			.sort((a, b) => a.spread - b.spread)
			.map((r) => ({ ...r, barPct: (r.spread / maxSpread) * 100 }));
	});

	const factorProfitQuantile90 = $derived.by(() => {
		const topFactors = [...factorStats]
			.sort((a, b) => b.count - a.count)
			.slice(0, 12)
			.map((f) => f.factor);
		const rows = topFactors
			.map((factor) => {
				const vals = data.runs
					.filter(
						(r) =>
							r.factors?.includes(factor) &&
							r.total_profit_pct != null &&
							isFinite(r.total_profit_pct)
					)
					.map((r) => r.total_profit_pct!)
					.sort((a, b) => a - b);
				if (vals.length < 5) return null;
				const q90 = vals[Math.floor(vals.length * 0.9)];
				const q50 = vals[Math.floor(vals.length * 0.5)];
				const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
				return { factor, q90, q50, avg, count: vals.length };
			})
			.filter((r): r is NonNullable<typeof r> => r !== null)
			.sort((a, b) => b.q90 - a.q90);
		if (rows.length < 3) return null;
		const maxQ90 = Math.max(0.01, ...rows.map((r) => Math.abs(r.q90)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.q90) / maxQ90) * 100 }));
	});

	const totalRuns = $derived(data.runs.filter((r) => r.factors && r.factors.length > 0).length);
	const bestFactor = $derived(factorStats.length > 0 ? factorStats[0] : null);

	function fmt(v: number | null | undefined, dp = 2): string {
		if (v == null) return '—';
		return v.toFixed(dp);
	}

	function barWidth(value: number, max: number): number {
		if (max === 0) return 0;
		return Math.min(100, Math.max(0, (Math.abs(value) / max) * 100));
	}

	const factorBestStrategyWinRate = $derived.by(() => {
		const map: Record<string, { best: number; count: number }> = {};
		for (const run of runs) {
			if (!run.factors || !run.win_rate_pct || !isFinite(run.win_rate_pct)) continue;
			for (const f of run.factors) {
				if (!map[f]) map[f] = { best: -Infinity, count: 0 };
				map[f].count++;
				if (run.win_rate_pct > map[f].best) map[f].best = run.win_rate_pct;
			}
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.count >= 2 && isFinite(v.best))
			.map(([factor, v]) => ({ factor, best: v.best, count: v.count }))
			.sort((a, b) => b.best - a.best)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxBest = Math.max(...rows.map((r) => r.best), 0.01);
		return { rows, maxBest };
	});

	const factorSortinoVsDrawdown = $derived.by(() => {
		const map: Record<string, { sortinos: number[]; dds: number[] }> = {};
		for (const run of runs) {
			if (!run.factors) continue;
			for (const f of run.factors) {
				if (!map[f]) map[f] = { sortinos: [], dds: [] };
				if (run.sortino != null && isFinite(run.sortino) && run.sortino > -100 && run.sortino < 500)
					map[f].sortinos.push(run.sortino);
				if (
					run.max_drawdown_pct != null &&
					isFinite(run.max_drawdown_pct) &&
					run.max_drawdown_pct > 0
				)
					map[f].dds.push(run.max_drawdown_pct);
			}
		}
		const pts = Object.entries(map)
			.filter(([, v]) => v.sortinos.length >= 3 && v.dds.length >= 3)
			.map(([factor, v]) => ({
				factor,
				sortino: v.sortinos.reduce((a, b) => a + b, 0) / v.sortinos.length,
				dd: v.dds.reduce((a, b) => a + b, 0) / v.dds.length
			}));
		if (pts.length < 5) return null;
		const sMin = Math.min(...pts.map((p) => p.sortino)),
			sMax = Math.max(...pts.map((p) => p.sortino), sMin + 0.01);
		const dMin = Math.min(...pts.map((p) => p.dd)),
			dMax = Math.max(...pts.map((p) => p.dd), dMin + 0.01);
		const W = 560,
			H = 130,
			PAD = 10;
		const toX = (d: number) => PAD + ((d - dMin) / (dMax - dMin)) * (W - PAD * 2);
		const toY = (s: number) => H - PAD - ((s - sMin) / (sMax - sMin)) * (H - PAD * 2);
		const zeroY = sMin < 0 && sMax > 0 ? toY(0) : null;
		const dots = pts.map((p) => ({ cx: toX(p.dd), cy: toY(p.sortino), factor: p.factor }));
		return {
			W,
			H,
			dots,
			zeroY,
			dMin: dMin.toFixed(1),
			dMax: dMax.toFixed(1),
			sMin: sMin.toFixed(1),
			sMax: sMax.toFixed(1),
			total: pts.length
		};
	});

	const factorProfitCvRanking = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const run of runs) {
			if (!run.factors || run.total_profit_pct == null || !isFinite(run.total_profit_pct)) continue;
			for (const f of run.factors) {
				if (!map[f]) map[f] = [];
				map[f].push(run.total_profit_pct);
			}
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.length >= 4)
			.map(([factor, vals]) => {
				const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
				const std = Math.sqrt(vals.reduce((s, v) => s + (v - mean) ** 2, 0) / vals.length);
				const cv = mean !== 0 ? Math.abs(std / mean) : Infinity;
				return { factor, cv, mean, count: vals.length };
			})
			.filter((r) => isFinite(r.cv))
			.sort((a, b) => a.cv - b.cv)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxCv = Math.max(...rows.map((r) => r.cv), 0.01);
		return { rows, maxCv };
	});

	const factorWinRateVsCalmar = $derived.by(() => {
		const map: Record<string, { wr: number[]; cal: number[] }> = {};
		for (const run of runs) {
			if (!run.factors || run.win_rate_pct == null || run.calmar == null) continue;
			if (!isFinite(run.win_rate_pct) || !isFinite(run.calmar)) continue;
			for (const f of run.factors) {
				if (!map[f]) map[f] = { wr: [], cal: [] };
				map[f].wr.push(run.win_rate_pct);
				map[f].cal.push(run.calmar);
			}
		}
		const dots = Object.entries(map)
			.filter(([, v]) => v.wr.length >= 3)
			.map(([factor, v]) => {
				const avgWr = v.wr.reduce((a, b) => a + b, 0) / v.wr.length;
				const avgCal = v.cal.reduce((a, b) => a + b, 0) / v.cal.length;
				return { factor, avgWr, avgCal, count: v.wr.length };
			});
		if (dots.length < 4) return null;
		const W = 560,
			H = 180,
			PAD = 28;
		const wrMin = Math.min(...dots.map((d) => d.avgWr));
		const wrMax = Math.max(...dots.map((d) => d.avgWr), wrMin + 0.01);
		const calMin = Math.min(...dots.map((d) => d.avgCal));
		const calMax = Math.max(...dots.map((d) => d.avgCal), calMin + 0.01);
		const toX = (v: number) => PAD + ((v - wrMin) / (wrMax - wrMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - calMin) / (calMax - calMin)) * (H - PAD * 2);
		const zeroY = calMin <= 0 && calMax >= 0 ? toY(0) : null;
		const colored = dots.map((d) => {
			const score =
				(d.avgWr - wrMin) / (wrMax - wrMin + 0.001) +
				(d.avgCal - calMin) / (calMax - calMin + 0.001);
			const hue = Math.round(score * 120);
			return { ...d, cx: toX(d.avgWr), cy: toY(d.avgCal), color: `hsl(${hue},70%,55%)` };
		});
		return {
			dots: colored,
			W,
			H,
			zeroY,
			total: dots.length,
			wrMin: wrMin.toFixed(1),
			wrMax: wrMax.toFixed(1),
			calMin: calMin.toFixed(2),
			calMax: calMax.toFixed(2)
		};
	});

	const factorAvgTradeCount = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const run of runs) {
			if (!run.factors || run.total_trades == null || run.total_trades <= 0) continue;
			for (const f of run.factors) {
				if (!map[f]) map[f] = [];
				map[f].push(run.total_trades);
			}
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.length >= 3)
			.map(([factor, vals]) => {
				const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
				return { factor, avg, count: vals.length };
			})
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxAvg = Math.max(...rows.map((r) => r.avg), 1);
		return { rows, maxAvg };
	});

	const factorProfitSkew = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const run of runs) {
			if (!run.factors || run.total_profit_pct == null || !isFinite(run.total_profit_pct)) continue;
			for (const f of run.factors) {
				if (!map[f]) map[f] = [];
				map[f].push(run.total_profit_pct);
			}
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.length >= 5)
			.map(([factor, vals]) => {
				const n = vals.length;
				const mean = vals.reduce((a, b) => a + b, 0) / n;
				const std = Math.sqrt(vals.reduce((s, v) => s + (v - mean) ** 2, 0) / n);
				const skew = std > 0 ? vals.reduce((s, v) => s + ((v - mean) / std) ** 3, 0) / n : 0;
				return { factor, skew, count: n };
			})
			.filter((r) => isFinite(r.skew))
			.sort((a, b) => b.skew - a.skew)
			.slice(0, 14);
		if (rows.length < 4) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.skew)), 0.01);
		return { rows, maxAbs };
	});

	const factorCalmarByTimeframe = $derived.by(() => {
		const TFS = ['5m', '15m', '1h', '4h', '1d'];
		const TF_COL: Record<string, string> = {
			'5m': 'var(--ch-violet)',
			'15m': 'var(--ch-profit)',
			'1h': 'var(--ch-warn)',
			'4h': 'var(--ch-loss)',
			'1d': 'var(--ch-teal)'
		};
		const map: Record<string, Record<string, number[]>> = {};
		for (const run of runs) {
			if (!run.factors || run.calmar == null || !isFinite(run.calmar) || Math.abs(run.calmar) > 200)
				continue;
			const tf = run.timeframe ?? 'other';
			for (const f of run.factors) {
				if (!map[f]) map[f] = {};
				if (!map[f][tf]) map[f][tf] = [];
				map[f][tf].push(run.calmar);
			}
		}
		const factors = Object.entries(map)
			.filter(([, tfMap]) => Object.values(tfMap).flat().length >= 4)
			.map(([factor, tfMap]) => {
				const tfVals = TFS.map((tf) => {
					const vals = tfMap[tf] ?? [];
					const avg = vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
					return { tf, avg, count: vals.length };
				});
				const overallAvg =
					Object.values(tfMap)
						.flat()
						.reduce((a, b) => a + b, 0) / Object.values(tfMap).flat().length;
				return { factor, tfVals, overallAvg };
			})
			.sort((a, b) => b.overallAvg - a.overallAvg)
			.slice(0, 10);
		if (factors.length < 3) return null;
		const allVals = factors.flatMap((f) =>
			f.tfVals.filter((v) => v.avg !== null).map((v) => v.avg!)
		);
		const vMin = Math.min(...allVals),
			vMax = Math.max(...allVals, vMin + 0.01);
		const W = 560,
			H = 160,
			ROW_H = 14,
			PAD_L = 80,
			PAD_R = 10;
		const toW = (v: number) =>
			Math.max(0, ((v - Math.min(vMin, 0)) / (vMax - Math.min(vMin, 0))) * (W - PAD_L - PAD_R));
		const zeroX = PAD_L + Math.max(0, -vMin / (vMax - Math.min(vMin, 0))) * (W - PAD_L - PAD_R);
		return {
			factors,
			TFS,
			TF_COL,
			W,
			H,
			ROW_H,
			PAD_L,
			PAD_R,
			toW,
			zeroX,
			vMin: vMin.toFixed(2),
			vMax: vMax.toFixed(2)
		};
	});

	const factorTopProfitFactorRanking = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const run of runs) {
			if (
				!run.factors ||
				run.profit_factor == null ||
				!isFinite(run.profit_factor) ||
				run.profit_factor <= 0 ||
				run.profit_factor > 30
			)
				continue;
			for (const f of run.factors) {
				if (!map[f]) map[f] = [];
				map[f].push(run.profit_factor);
			}
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.length >= 3)
			.map(([factor, vals]) => {
				const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
				const best = Math.max(...vals);
				return { factor, avg, best, count: vals.length };
			})
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxAvg = Math.max(...rows.map((r) => r.avg), 0.01);
		return { rows, maxAvg };
	});

	const factorMonthlyRunCount = $derived.by(() => {
		const factorTotals: Record<string, number> = {};
		for (const run of runs) {
			if (!run.factors) continue;
			for (const f of run.factors) factorTotals[f] = (factorTotals[f] ?? 0) + 1;
		}
		const topFactors = Object.entries(factorTotals)
			.sort((a, b) => b[1] - a[1])
			.slice(0, 5)
			.map(([f]) => f);
		if (topFactors.length < 2) return null;
		const map: Record<string, Record<string, number>> = {};
		for (const run of runs) {
			if (!run.factors || !run.imported_at) continue;
			const mo = run.imported_at.slice(0, 7);
			for (const f of run.factors) {
				if (!topFactors.includes(f)) continue;
				if (!map[mo]) map[mo] = {};
				map[mo][f] = (map[mo][f] ?? 0) + 1;
			}
		}
		const months = Object.keys(map).sort().slice(-12);
		if (months.length < 3) return null;
		const COLORS = [
			'var(--ch-violet)',
			'var(--ch-profit)',
			'var(--ch-warn)',
			'var(--ch-loss)',
			'var(--ch-teal)'
		];
		const series = topFactors.map((f, i) => ({
			factor: f,
			color: COLORS[i],
			counts: months.map((mo) => map[mo]?.[f] ?? 0)
		}));
		const totals = months.map((_, i) => series.reduce((s, sr) => s + sr.counts[i], 0));
		const maxTotal = Math.max(...totals, 1);
		const W = 560,
			H = 100,
			PAD = 8;
		const barW = Math.max(2, Math.floor((W - PAD * 2) / months.length) - 1);
		return { series, months, totals, maxTotal, W, H, PAD, barW };
	});

	const factorCalmarVsWinRate = $derived.by(() => {
		const pts = factorStats
			.filter(
				(f) =>
					f.median_calmar != null &&
					isFinite(f.median_calmar!) &&
					f.win_rate != null &&
					isFinite(f.win_rate) &&
					f.count >= 2
			)
			.map((f) => ({
				factor: f.factor,
				calmar: f.median_calmar!,
				wr: f.win_rate,
				count: f.count,
				profit: f.avg_profit
			}));
		if (pts.length < 4) return null;
		const W = 520,
			H = 100,
			PAD = 12;
		const mnC = Math.min(...pts.map((p) => p.calmar)),
			mxC = Math.max(...pts.map((p) => p.calmar), mnC + 0.01);
		const mnW = Math.min(...pts.map((p) => p.wr)),
			mxW = Math.max(...pts.map((p) => p.wr), mnW + 1);
		const mxN = Math.max(...pts.map((p) => p.count));
		const toX = (v: number) => PAD + ((v - mnW) / (mxW - mnW)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mnC) / (mxC - mnC)) * (H - PAD * 2);
		const toR = (c: number) => 3 + (c / mxN) * 7;
		const dots = pts.map((p) => ({
			cx: toX(p.wr),
			cy: toY(p.calmar),
			r: toR(p.count),
			color: p.profit >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'
		}));
		const zeroY = mnC <= 0 && mxC >= 0 ? toY(0) : null;
		return { W, H, dots, zeroY, count: pts.length };
	});

	const factorDrawdownRanking = $derived.by(() => {
		const rows = [...factorStats]
			.filter((f) => f.avg_dd != null && isFinite(f.avg_dd) && f.count >= 2)
			.map((f) => ({ factor: f.factor, dd: f.avg_dd, count: f.count }))
			.sort((a, b) => a.dd - b.dd)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxDD = Math.max(...rows.map((r) => r.dd), 0.01);
		return { rows, maxDD };
	});

	const factorStrategyCountRanking = $derived.by(() => {
		const rows = [...factorStats]
			.filter((f) => f.strategies != null && f.strategies.length >= 1)
			.map((f) => ({
				factor: f.factor,
				strategies: f.strategies.length,
				count: f.count,
				profit: f.avg_profit
			}))
			.sort((a, b) => b.strategies - a.strategies)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxStrats = Math.max(...rows.map((r) => r.strategies), 1);
		return { rows, maxStrats };
	});

	const factorWinRateDistribution = $derived.by(() => {
		const vals = factorStats.filter((f) => f.win_rate != null).map((f) => f.win_rate);
		if (vals.length < 4) return null;
		const mn = Math.min(...vals),
			mx = Math.max(...vals);
		const bins = 12;
		const step = (mx - mn) / bins || 1;
		const counts = Array.from({ length: bins }, (_, i) => {
			const lo = mn + i * step,
				hi = lo + step;
			return {
				lo,
				hi,
				count: vals.filter((v) => v >= lo && (i === bins - 1 ? v <= hi : v < hi)).length,
				label: `${(lo * 100).toFixed(0)}%`
			};
		});
		const maxCount = Math.max(...counts.map((c) => c.count), 1);
		const W = 380,
			H = 70,
			PAD = 8,
			barW = Math.floor((W - PAD * 2) / bins) - 1;
		return {
			counts,
			maxCount,
			W,
			H,
			PAD,
			barW,
			avg: ((vals.reduce((a, b) => a + b, 0) / vals.length) * 100).toFixed(1)
		};
	});

	const factorProfitVsDrawdownBubble = $derived.by(() => {
		const pts = factorStats
			.filter((f) => f.avg_profit != null && f.avg_dd != null && f.count >= 2)
			.map((f) => ({
				factor: f.factor,
				profit: f.avg_profit,
				dd: Math.abs(f.avg_dd),
				count: f.count,
				calmar: f.median_calmar ?? 0
			}));
		if (pts.length < 4) return null;
		const W = 400,
			H = 160,
			PAD = 28;
		const minP = Math.min(...pts.map((p) => p.profit));
		const maxP = Math.max(...pts.map((p) => p.profit));
		const maxDD = Math.max(...pts.map((p) => p.dd), 0.01);
		const maxCount = Math.max(...pts.map((p) => p.count), 1);
		const xs = (v: number) => PAD + ((v - minP) / (maxP - minP || 1)) * (W - PAD * 2);
		const ys = (v: number) => PAD + (1 - v / maxDD) * (H - PAD * 2);
		const rs = (c: number) => 3 + (c / maxCount) * 9;
		const color = (cal: number) =>
			cal >= 1.5 ? 'var(--ch-violet)' : cal >= 0.5 ? 'var(--ch-warn)' : 'var(--ch-loss)';
		return { pts, W, H, PAD, xs, ys, rs, color, minP, maxP, maxDD };
	});

	const factorProfitTierBreakdown = $derived.by(() => {
		const tiers = [
			{ label: '<0%', color: 'var(--ch-loss)', test: (v: number) => v < 0 },
			{ label: '0–5%', color: 'var(--ch-warn)', test: (v: number) => v >= 0 && v < 5 },
			{ label: '5–15%', color: 'var(--ch-profit)', test: (v: number) => v >= 5 && v < 15 },
			{ label: '>15%', color: 'var(--ch-violet-strong)', test: (v: number) => v >= 15 }
		];
		const top = factorStats.filter((f) => f.avg_profit != null).slice(0, 20);
		if (top.length < 3) return null;
		const rows = top.map((f) => {
			const counts = tiers.map((t) => ({ label: t.label, color: t.color, count: 0 }));
			return { factor: f.factor, counts, total: f.count };
		});
		const allVals = top.map((f) => ({ factor: f.factor, profit: f.avg_profit }));
		for (const v of allVals) {
			const row = rows.find((r) => r.factor === v.factor);
			if (!row) continue;
			const ti = tiers.findIndex((t) => t.test(v.profit));
			if (ti >= 0) row.counts[ti].count++;
		}
		const maxTotal = Math.max(...rows.map((r) => r.total), 1);
		return { rows: rows.slice(0, 12), maxTotal, tiers };
	});

	const factorMedianCalmarLeaderboard = $derived.by(() => {
		const rows = factorStats
			.filter(
				(f) =>
					f.median_calmar != null &&
					isFinite(f.median_calmar) &&
					f.median_calmar > 0 &&
					f.count >= 3
			)
			.map((f) => ({ factor: f.factor, calmar: f.median_calmar!, count: f.count, wr: f.win_rate }))
			.sort((a, b) => b.calmar - a.calmar)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxCalmar = Math.max(...rows.map((r) => r.calmar), 0.01);
		return { rows, maxCalmar };
	});

	const factorTopSharpeRanking = $derived.by(() => {
		const rows = factorStats
			.filter((f) => f.median_sharpe != null && isFinite(f.median_sharpe) && f.count >= 3)
			.map((f) => ({ factor: f.factor, sharpe: f.median_sharpe!, count: f.count, wr: f.win_rate }))
			.sort((a, b) => b.sharpe - a.sharpe)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.sharpe)), 0.01);
		return { rows, maxAbs };
	});

	const factorBestVsWorstRun = $derived.by(() => {
		const map = new Map<string, { best: number; worst: number; count: number }>();
		for (const run of data.runs) {
			if (!run.factors || run.total_profit_pct == null || !isFinite(run.total_profit_pct)) continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, { best: -Infinity, worst: Infinity, count: 0 });
				const e = map.get(f)!;
				if (run.total_profit_pct > e.best) e.best = run.total_profit_pct;
				if (run.total_profit_pct < e.worst) e.worst = run.total_profit_pct;
				e.count++;
			}
		}
		const rows = [...map.entries()]
			.filter(([, e]) => e.count >= 4 && isFinite(e.best) && isFinite(e.worst))
			.map(([factor, e]) => ({
				factor: factor.slice(0, 14),
				best: e.best,
				worst: e.worst,
				spread: e.best - e.worst,
				count: e.count
			}))
			.sort((a, b) => b.best - a.best)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const absMax = Math.max(
			...rows.map((r) => Math.max(Math.abs(r.best), Math.abs(r.worst))),
			0.01
		);
		return { rows, absMax };
	});

	const factorCalmarEfficiency = $derived.by(() => {
		const rows = factorStats
			.filter(
				(f) => f.median_calmar != null && isFinite(f.median_calmar) && f.avg_dd > 0 && f.count >= 3
			)
			.map((f) => ({
				factor: f.factor.slice(0, 14),
				calmar: f.median_calmar!,
				dd: f.avg_dd,
				count: f.count,
				efficiency: f.median_calmar! / f.avg_dd
			}))
			.sort((a, b) => b.efficiency - a.efficiency)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxEff = Math.max(...rows.map((r) => Math.abs(r.efficiency)), 0.01);
		return { rows, maxEff };
	});

	const factorTimeframeWinRate = $derived.by(() => {
		const map = new Map<string, Map<string, { wins: number; total: number }>>();
		for (const run of data.runs) {
			if (!run.factors || !run.timeframe || run.win_rate_pct == null || !isFinite(run.win_rate_pct))
				continue;
			for (const f of run.factors) {
				if (!map.has(f)) map.set(f, new Map());
				const inner = map.get(f)!;
				if (!inner.has(run.timeframe)) inner.set(run.timeframe, { wins: 0, total: 0 });
				const e = inner.get(run.timeframe)!;
				e.total++;
				if (run.win_rate_pct > 50) e.wins++;
			}
		}
		const TF_ORDER = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d'];
		const topFactors = factorStats
			.filter((f) => f.count >= 5)
			.sort((a, b) => b.count - a.count)
			.slice(0, 6)
			.map((f) => f.factor);
		const usedTfs = TF_ORDER.filter((tf) => topFactors.some((f) => map.get(f)?.has(tf)));
		if (topFactors.length < 2 || usedTfs.length < 2) return null;
		const cells = topFactors.flatMap((f, fi) =>
			usedTfs.map((tf, ti) => {
				const e = map.get(f)?.get(tf);
				const rate = e && e.total >= 2 ? (e.wins / e.total) * 100 : null;
				return { f: f.slice(0, 12), tf, rate, fi, ti };
			})
		);
		const cW = 32,
			cH = 16,
			PAD = 32;
		return {
			cells,
			topFactors: topFactors.map((f) => f.slice(0, 12)),
			usedTfs,
			cW,
			cH,
			PAD,
			W: PAD + usedTfs.length * (cW + 2),
			H: PAD + topFactors.length * (cH + 2)
		};
	});

	const factorSharpeVsCalmarScatter = $derived.by(() => {
		const pts = factorStats
			.filter(
				(f) =>
					f.avg_sharpe != null &&
					isFinite(f.avg_sharpe) &&
					Math.abs(f.avg_sharpe) < 50 &&
					f.avg_calmar != null &&
					isFinite(f.avg_calmar) &&
					Math.abs(f.avg_calmar) < 50 &&
					f.count >= 3
			)
			.map((f) => ({
				label: f.factor.slice(0, 14),
				sharpe: f.avg_sharpe!,
				calmar: f.avg_calmar!,
				count: f.count
			}));
		if (pts.length < 4) return null;
		const sMin = Math.min(...pts.map((p) => p.sharpe)),
			sMax = Math.max(...pts.map((p) => p.sharpe), sMin + 0.1);
		const cMin = Math.min(...pts.map((p) => p.calmar)),
			cMax = Math.max(...pts.map((p) => p.calmar), cMin + 0.1);
		const W = 360,
			H = 100,
			PAD = 12;
		const toX = (v: number) => PAD + ((v - sMin) / (sMax - sMin)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - cMin) / (cMax - cMin)) * (H - PAD * 2);
		const dots = pts.map((p) => ({
			cx: toX(p.sharpe),
			cy: toY(p.calmar),
			label: p.label,
			color:
				p.calmar >= 1 && p.sharpe >= 1
					? 'var(--ch-profit)'
					: p.calmar >= 0 && p.sharpe >= 0
						? 'var(--ch-warn)'
						: 'var(--ch-loss)'
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

	const factorTopUsageTrend = $derived.by(() => {
		const topFactors = factorStats
			.filter((f) => f.count >= 5)
			.sort((a, b) => b.count - a.count)
			.slice(0, 3)
			.map((f) => f.factor);
		if (topFactors.length < 2) return null;
		const monthMap = new Map<string, Map<string, number>>();
		for (const run of data.runs) {
			if (!run.factors || !run.imported_at) continue;
			const mo = run.imported_at.slice(0, 7);
			for (const f of run.factors) {
				if (!topFactors.includes(f)) continue;
				if (!monthMap.has(mo)) monthMap.set(mo, new Map());
				monthMap.get(mo)!.set(f, (monthMap.get(mo)!.get(f) ?? 0) + 1);
			}
		}
		const months = [...monthMap.keys()].sort().slice(-8);
		if (months.length < 3) return null;
		const colors = ['var(--ch-profit-strong)', 'var(--ch-violet-strong)', 'var(--ch-warn)'];
		const lines = topFactors.map((f, fi) => {
			const pts = months.map((mo, i) => ({ i, count: monthMap.get(mo)?.get(f) ?? 0 }));
			return { factor: f.slice(0, 14), color: colors[fi], pts };
		});
		const maxCount = Math.max(...lines.flatMap((l) => l.pts.map((p) => p.count)), 1);
		const W = 360,
			H = 80,
			PAD = 10;
		const toX = (i: number) => PAD + (i / Math.max(months.length - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - v / maxCount) * (H - PAD * 2);
		const polylines = lines.map((l) => ({
			...l,
			poly: l.pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.count).toFixed(1)}`).join(' ')
		}));
		return { polylines, months: months.map((m) => m.slice(5)), W, H, PAD, maxCount };
	});

	const factorAvgTradeCountByTF = $derived.by(() => {
		const TF_ORDER = ['15m', '30m', '1h', '2h', '4h', '8h', '1d'];
		const tfCounts = new Map<string, number>();
		for (const r of data.runs) {
			if (!r.timeframe) continue;
			tfCounts.set(r.timeframe, (tfCounts.get(r.timeframe) ?? 0) + 1);
		}
		const topTFs = TF_ORDER.filter((tf) => (tfCounts.get(tf) ?? 0) >= 3).slice(0, 4);
		if (topTFs.length < 2) return null;
		const topFactors = factorStats
			.filter((f) => f.count >= 5)
			.sort((a, b) => b.count - a.count)
			.slice(0, 5)
			.map((f) => f.factor);
		if (topFactors.length < 2) return null;
		const map = new Map<string, Map<string, number[]>>();
		for (const r of data.runs) {
			if (!r.factors || !r.timeframe || !topTFs.includes(r.timeframe) || r.total_trades == null)
				continue;
			for (const f of r.factors) {
				if (!topFactors.includes(f)) continue;
				if (!map.has(f)) map.set(f, new Map());
				if (!map.get(f)!.has(r.timeframe)) map.get(f)!.set(r.timeframe, []);
				map.get(f)!.get(r.timeframe)!.push(r.total_trades);
			}
		}
		const rows = topFactors.map((f) => ({
			factor: f.slice(0, 12),
			tfs: topTFs.map((tf) => {
				const vals = map.get(f)?.get(tf) ?? [];
				return {
					tf,
					avg: vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0,
					count: vals.length
				};
			})
		}));
		const maxAvg = Math.max(...rows.flatMap((r) => r.tfs.map((t) => t.avg)), 1);
		const colors = ['var(--ch-violet)', 'var(--ch-profit)', 'var(--ch-warn)', 'var(--ch-warn)'];
		const ROW_H = 14,
			PAD = 60,
			barMaxW = 200;
		return {
			rows,
			topTFs,
			maxAvg,
			colors,
			ROW_H,
			PAD,
			barMaxW,
			W: PAD + barMaxW + 40,
			H: PAD + rows.length * (topTFs.length * (ROW_H + 1) + 6)
		};
	});

	const factorWinRateVsCalmarScatter = $derived.by(() => {
		const pts = factorStats
			.filter(
				(f) =>
					f.count >= 3 &&
					f.median_calmar != null &&
					isFinite(f.median_calmar) &&
					Math.abs(f.median_calmar) < 50
			)
			.map((f) => ({
				factor: f.factor.slice(0, 10),
				wr: f.win_rate,
				calmar: f.median_calmar ?? 0,
				count: f.count
			}));
		if (pts.length < 4) return null;
		const wrMin = Math.min(...pts.map((p) => p.wr)),
			wrMax = Math.max(...pts.map((p) => p.wr), wrMin + 0.1);
		const cMin = Math.min(...pts.map((p) => p.calmar)),
			cMax = Math.max(...pts.map((p) => p.calmar), cMin + 0.1);
		const W = 340,
			H = 90,
			PAD = 12;
		const toX = (v: number) => PAD + ((v - wrMin) / (wrMax - wrMin)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - cMin) / (cMax - cMin)) * (H - PAD * 2);
		const zeroY = Math.max(PAD, Math.min(H - PAD, toY(0)));
		const dots = pts.map((p) => ({
			cx: toX(p.wr),
			cy: toY(p.calmar),
			label: p.factor,
			r: Math.max(2.5, Math.min(5, 2 + p.count / 10)),
			color:
				p.calmar >= 1
					? 'var(--ch-profit)'
					: p.calmar >= 0
						? 'var(--ch-warn)'
						: 'var(--ch-loss-light)'
		}));
		return {
			dots,
			W,
			H,
			PAD,
			zeroY,
			wrMin: wrMin.toFixed(0),
			wrMax: wrMax.toFixed(0),
			cMin: cMin.toFixed(1),
			cMax: cMax.toFixed(1)
		};
	});

	const factorProfitByTimeframeTrend = $derived.by(() => {
		const tfColors: Record<string, string> = {
			'15m': 'var(--ch-profit-strong)',
			'1h': 'var(--ch-violet-strong)',
			'4h': 'var(--ch-warn)',
			'1d': 'var(--ch-warn)'
		};
		const targetTFs = ['15m', '1h', '4h', '1d'];
		const tfMonths = new Map<string, Map<string, number[]>>();
		for (const r of data.runs) {
			if (
				!r.timeframe ||
				!targetTFs.includes(r.timeframe) ||
				!r.imported_at ||
				r.total_profit_pct == null ||
				!isFinite(r.total_profit_pct)
			)
				continue;
			const mo = r.imported_at.slice(0, 7);
			if (!tfMonths.has(r.timeframe)) tfMonths.set(r.timeframe, new Map());
			if (!tfMonths.get(r.timeframe)!.has(mo)) tfMonths.get(r.timeframe)!.set(mo, []);
			tfMonths.get(r.timeframe)!.get(mo)!.push(r.total_profit_pct);
		}
		const allMonths = [...new Set([...tfMonths.values()].flatMap((m) => [...m.keys()]))].sort();
		if (allMonths.length < 3 || tfMonths.size < 2) return null;
		const W = 360,
			H = 80,
			PAD = 10;
		const toX = (i: number) => PAD + (i / Math.max(allMonths.length - 1, 1)) * (W - PAD * 2);
		const lines = targetTFs
			.filter((tf) => (tfMonths.get(tf)?.size ?? 0) >= 2)
			.map((tf) => {
				const pts = allMonths
					.map((mo, i) => {
						const vals = tfMonths.get(tf)?.get(mo) ?? [];
						return vals.length ? { i, avg: vals.reduce((a, v) => a + v, 0) / vals.length } : null;
					})
					.filter(Boolean) as { i: number; avg: number }[];
				return { tf, color: tfColors[tf], pts };
			})
			.filter((l) => l.pts.length >= 2);
		if (lines.length < 2) return null;
		const allAvgs = lines.flatMap((l) => l.pts.map((p) => p.avg));
		const mn = Math.min(...allAvgs),
			mx = Math.max(...allAvgs, mn + 0.1);
		const toY = (v: number) => PAD + (1 - (v - mn) / (mx - mn)) * (H - PAD * 2);
		const zeroY = Math.max(PAD, Math.min(H - PAD, toY(0)));
		const polylines = lines.map((l) => ({
			...l,
			poly: l.pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.avg).toFixed(1)}`).join(' ')
		}));
		return { polylines, allMonths, W, H, PAD, zeroY };
	});

	const factorSharpeVsSortinoScatter = $derived.by(() => {
		const pts = factorStats
			.filter(
				(f) =>
					f.avg_sharpe != null &&
					isFinite(f.avg_sharpe) &&
					Math.abs(f.avg_sharpe) < 30 &&
					f.avg_sortino != null &&
					isFinite(f.avg_sortino) &&
					Math.abs(f.avg_sortino) < 60 &&
					f.median_calmar != null &&
					isFinite(f.median_calmar)
			)
			.map((f) => ({
				name: f.factor.slice(0, 12),
				sharpe: f.avg_sharpe!,
				sortino: f.avg_sortino!,
				calmar: f.median_calmar!
			}));
		if (pts.length < 5) return null;
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
			name: p.name,
			color:
				p.calmar > 2
					? 'var(--ch-profit)'
					: p.calmar > 0
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

	const factorWinRateByMonth = $derived.by(() => {
		const map = new Map<string, { wins: number; total: number }>();
		for (const run of data.runs) {
			if (!run.imported_at || run.win_rate_pct == null || !isFinite(run.win_rate_pct)) continue;
			const mo = run.imported_at.slice(0, 7);
			const cur = map.get(mo) ?? { wins: 0, total: 0 };
			cur.wins += run.win_rate_pct;
			cur.total++;
			map.set(mo, cur);
		}
		if (map.size < 4) return null;
		const months = [...map.keys()].sort();
		const pts = months.map((m) => {
			const d = map.get(m)!;
			return { mo: m, wr: d.wins / d.total };
		});
		const mn = Math.min(...pts.map((p) => p.wr)),
			mx = Math.max(...pts.map((p) => p.wr), mn + 0.5);
		const W = 360,
			H = 72,
			PAD = 10;
		const toX = (i: number) => PAD + (i / Math.max(pts.length - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - mn) / (mx - mn)) * (H - PAD * 2);
		const poly = pts.map((p, i) => `${toX(i).toFixed(1)},${toY(p.wr).toFixed(1)}`).join(' ');
		const area =
			poly + ` ${toX(pts.length - 1).toFixed(1)},${H - PAD} ${toX(0).toFixed(1)},${H - PAD}`;
		const y50 = Math.max(PAD, Math.min(H - PAD, toY(50)));
		return {
			pts,
			poly,
			area,
			W,
			H,
			PAD,
			mn: mn.toFixed(1),
			mx: mx.toFixed(1),
			y50,
			count: pts.length
		};
	});

	const factorProfitFactorVsWinRateScatter = $derived.by(() => {
		const pts = factorStats
			.filter(
				(f) =>
					f.avg_profit_factor != null &&
					isFinite(f.avg_profit_factor) &&
					f.avg_profit_factor > 0 &&
					f.avg_profit_factor < 20 &&
					f.win_rate != null &&
					isFinite(f.win_rate) &&
					f.count != null
			)
			.map((f) => ({
				name: f.factor.slice(0, 12),
				pf: f.avg_profit_factor!,
				wr: f.win_rate,
				count: f.count!
			}));
		if (pts.length < 5) return null;
		const pfMin = Math.min(...pts.map((p) => p.pf)),
			pfMax = Math.max(...pts.map((p) => p.pf), pfMin + 0.1);
		const wrMin = Math.min(...pts.map((p) => p.wr)),
			wrMax = Math.max(...pts.map((p) => p.wr), wrMin + 0.1);
		const countMax = Math.max(...pts.map((p) => p.count), 1);
		const W = 360,
			H = 92,
			PAD = 12;
		const toX = (v: number) => PAD + ((v - wrMin) / (wrMax - wrMin)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - pfMin) / (pfMax - pfMin)) * (H - PAD * 2);
		const x1Line = toX(50),
			zeroY = Math.max(PAD, Math.min(H - PAD, toY(1)));
		const dots = pts.map((p) => ({
			cx: toX(p.wr),
			cy: toY(p.pf),
			name: p.name,
			r: 2 + (p.count / countMax) * 3,
			color: `rgba(99,102,241,${0.3 + (p.count / countMax) * 0.55})`
		}));
		return {
			dots,
			W,
			H,
			PAD,
			x1Line,
			zeroY,
			wrMin: wrMin.toFixed(0),
			wrMax: wrMax.toFixed(0),
			pfMin: pfMin.toFixed(1),
			pfMax: pfMax.toFixed(1),
			count: pts.length
		};
	});

	const factorTopByRunCount = $derived.by(() => {
		const rows = factorStats
			.filter((f) => f.count != null && f.count > 0)
			.map((f) => ({ name: f.factor.slice(0, 20), count: f.count!, avgProfit: f.avg_profit ?? 0 }))
			.sort((a, b) => b.count - a.count)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxC = Math.max(...rows.map((r) => r.count), 1);
		const W = 340,
			H = rows.length * 16 + 6,
			PAD = 8,
			barMaxW = W - 90;
		return { rows, maxC, W, H, PAD, barMaxW };
	});

	const factorAvgProfitRanking = $derived.by(() => {
		const rows = factorStats
			.filter(
				(f) => f.avg_profit != null && isFinite(f.avg_profit) && f.count != null && f.count >= 3
			)
			.map((f) => ({ name: f.factor.slice(0, 20), avg: f.avg_profit!, count: f.count! }))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 340,
			H = rows.length * 16 + 6,
			PAD = 8,
			barMaxW = W - 90;
		const zeroX = PAD + (maxAbs / (2 * maxAbs)) * barMaxW;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const factorSharpeHistogram = $derived.by(() => {
		const vals = factorStats
			.filter((f) => f.avg_sharpe != null && isFinite(f.avg_sharpe) && Math.abs(f.avg_sharpe) < 50)
			.map((f) => f.avg_sharpe!);
		if (vals.length < 5) return null;
		const mn = Math.min(...vals),
			mx = Math.max(...vals);
		const bins = 12;
		const binSize = (mx - mn) / bins || 1;
		const buckets = Array.from({ length: bins }, (_, i) => ({ lo: mn + i * binSize, count: 0 }));
		for (const v of vals) {
			const bi = Math.min(bins - 1, Math.floor((v - mn) / binSize));
			buckets[bi].count++;
		}
		const maxC = Math.max(...buckets.map((b) => b.count), 1);
		const W = 360,
			H = 68,
			PAD = 10;
		const bw = (W - PAD * 2) / bins - 1;
		const zeroX =
			PAD +
			Math.max(0, Math.min(bins - 1, Math.floor((0 - mn) / binSize))) * ((W - PAD * 2) / bins);
		const bars = buckets.map((b, i) => ({
			x: PAD + i * ((W - PAD * 2) / bins),
			h: Math.max(2, (b.count / maxC) * (H - PAD - 16)),
			color: b.lo >= 1 ? 'var(--ch-profit)' : b.lo >= 0 ? 'var(--ch-warn)' : 'var(--ch-loss-light)'
		}));
		return { bars, bw, W, H, PAD, zeroX, mn: mn.toFixed(1), mx: mx.toFixed(1), total: vals.length };
	});

	const factorCalmarWinRateScatter2 = $derived.by(() => {
		const pts = factorStats
			.filter(
				(f) =>
					f.avg_calmar != null &&
					isFinite(f.avg_calmar) &&
					f.avg_win_rate != null &&
					isFinite(f.avg_win_rate) &&
					Math.abs(f.avg_calmar) < 30
			)
			.map((f) => ({
				calmar: f.avg_calmar!,
				wr: f.avg_win_rate!,
				name: (f.factor ?? '').slice(0, 12)
			}));
		if (pts.length < 4) return null;
		const minC = Math.min(...pts.map((p) => p.calmar)),
			maxC = Math.max(...pts.map((p) => p.calmar));
		const minW = Math.min(...pts.map((p) => p.wr)),
			maxW = Math.max(...pts.map((p) => p.wr));
		const rangeC = maxC - minC || 1,
			rangeW = maxW - minW || 1;
		const W = 360,
			H = 80,
			PAD = 12;
		const zeroX = PAD + (Math.max(0, -minC) / rangeC) * (W - PAD * 2);
		const dots = pts.map((p) => ({
			cx: PAD + ((p.calmar - minC) / rangeC) * (W - PAD * 2),
			cy: PAD + ((maxW - p.wr) / rangeW) * (H - PAD * 2),
			color:
				p.calmar >= 1 && p.wr >= 55
					? 'var(--ch-profit)'
					: p.calmar >= 0
						? 'var(--ch-warn)'
						: 'var(--ch-loss-light)'
		}));
		return {
			dots,
			W,
			H,
			PAD,
			zeroX,
			minC: minC.toFixed(1),
			maxC: maxC.toFixed(1),
			minW: minW.toFixed(0),
			maxW: maxW.toFixed(0)
		};
	});

	const factorMonthlyUsageTrend = $derived.by(() => {
		const factorMonths = new Map<string, Map<string, number>>();
		for (const r of data.runs) {
			if (!r.imported_at) continue;
			const mo = r.imported_at.slice(0, 7);
			const factors: string[] = r.factors ?? [];
			for (const f of factors) {
				if (!f) continue;
				const fm = factorMonths.get(f) ?? new Map<string, number>();
				fm.set(mo, (fm.get(mo) ?? 0) + 1);
				factorMonths.set(f, fm);
			}
		}
		if (factorMonths.size < 2) return null;
		const top3 = [...factorMonths.entries()]
			.map(([f, mm]) => ({ f, total: [...mm.values()].reduce((a, v) => a + v, 0), mm }))
			.sort((a, b) => b.total - a.total)
			.slice(0, 3);
		const allMonths = [...new Set([...factorMonths.values()].flatMap((m) => [...m.keys()]))]
			.sort()
			.slice(-8);
		if (allMonths.length < 3 || top3.length < 2) return null;
		const maxVal = Math.max(...top3.flatMap((t) => allMonths.map((m) => t.mm.get(m) ?? 0)), 1);
		const W = 360,
			H = 68,
			PAD = 10;
		const toX = (i: number) => PAD + (i / (allMonths.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - (v / maxVal) * (H - PAD * 2);
		const colors = ['var(--ch-profit-strong)', 'var(--ch-violet-strong)', 'var(--ch-warn)'];
		const lines = top3.map((t, ci) => ({
			name: t.f.slice(0, 14),
			color: colors[ci],
			points: allMonths.map((m, i) => `${toX(i)},${toY(t.mm.get(m) ?? 0)}`).join(' ')
		}));
		return { lines, allMonths: allMonths.map((m) => m.slice(5)), W, H, PAD, toX };
	});

	const factorProfitFactorVsWinRate = $derived.by(() => {
		if (!factors || factors.length < 6) return null;
		const pts = factors
			.filter((f) => f.avg_profit_factor != null && f.avg_win_rate != null)
			.map((f) => ({
				pf: f.avg_profit_factor as number,
				wr: f.avg_win_rate as number,
				name: ((f.factor as string) ?? '').slice(0, 10)
			}));
		if (pts.length < 5) return null;
		const pfMax = Math.max(...pts.map((p) => p.pf), 1);
		const W = 320,
			H = 110,
			PAD = 14;
		const toX = (wr: number) => PAD + (wr / 100) * (W - PAD * 2);
		const toY = (pf: number) => H - PAD - (pf / pfMax) * (H - PAD * 2);
		return { pts, W, H, PAD, toX, toY, pfMax: pfMax.toFixed(2) };
	});

	const factorTopBySharpe = $derived.by(() => {
		if (!factors || factors.length < 4) return null;
		const rows = factors
			.filter((f) => f.avg_sharpe != null)
			.map((f) => ({
				name: ((f.factor as string) ?? '').slice(0, 20),
				sharpe: f.avg_sharpe as number,
				count: (f.count as number) ?? 0
			}))
			.sort((a, b) => b.sharpe - a.sharpe)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.sharpe)), 0.01);
		const W = 340,
			H = rows.length * 16 + 6,
			PAD = 8,
			barMaxW = W - 100;
		const zeroX = PAD + (maxAbs / (2 * maxAbs)) * barMaxW;
		return { rows, W, H, PAD, barMaxW, zeroX, maxAbs };
	});

	const factorAvgDrawdownRanking = $derived.by(() => {
		if (!factors || factors.length < 4) return null;
		const rows = factors
			.filter((f) => f.avg_dd != null)
			.map((f) => ({
				name: ((f.factor as string) ?? '').slice(0, 20),
				dd: f.avg_dd as number,
				count: (f.count as number) ?? 0
			}))
			.sort((a, b) => a.dd - b.dd)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxDD = Math.max(...rows.map((r) => r.dd), 0.01);
		const W = 340,
			H = rows.length * 16 + 6,
			PAD = 8,
			barMaxW = W - 100;
		return { rows, maxDD, W, H, PAD, barMaxW };
	});

	const factorMonthlyTotalRuns = $derived.by(() => {
		if (!factors || factors.length < 4) return null;
		const map = new Map<string, number[]>();
		for (const f of factors) {
			if (!f.first_seen || f.count == null) continue;
			const mo = (f.first_seen as string).slice(0, 7);
			const arr = map.get(mo) ?? [];
			arr.push(f.count as number);
			map.set(mo, arr);
		}
		if (map.size < 3) return null;
		const months = [...map.keys()].sort();
		const pts = months.map((m) => {
			const arr = map.get(m)!;
			return { m: m.slice(5), total: arr.reduce((a, v) => a + v, 0) };
		});
		const maxV = Math.max(...pts.map((p) => p.total), 1);
		const W = 380,
			H = 68,
			PAD = 10;
		const toX = (i: number) => PAD + (i / (pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - (v / maxV) * (H - PAD * 2);
		const polyline = pts.map((p, i) => `${toX(i)},${toY(p.total)}`).join(' ');
		const area = `${toX(0)},${H - PAD} ${polyline} ${toX(pts.length - 1)},${H - PAD}`;
		return {
			pts,
			polyline,
			area,
			W,
			H,
			PAD,
			maxV,
			firstMo: pts[0].m,
			lastMo: pts[pts.length - 1].m
		};
	});

	const factorSharpeByRunCount = $derived.by(() => {
		if (!factorStats || factorStats.length < 5) return null;
		const pts = factorStats
			.filter((f) => f.count != null && f.avg_sharpe != null)
			.map((f) => ({
				rc: f.count as number,
				sh: f.avg_sharpe as number,
				name: ((f.factor as string) ?? '').slice(0, 10)
			}));
		if (pts.length < 4) return null;
		const rcMax = Math.max(...pts.map((p) => p.rc), 1);
		const shMin = Math.min(...pts.map((p) => p.sh), 0);
		const shMax = Math.max(...pts.map((p) => p.sh), 0.01);
		const range = shMax - shMin || 0.01;
		const W = 300,
			H = 100,
			PAD = 12;
		const toX = (rc: number) => PAD + (rc / rcMax) * (W - PAD * 2);
		const toY = (sh: number) => H - PAD - ((sh - shMin) / range) * (H - PAD * 2);
		const zeroY = toY(0);
		return { pts, W, H, PAD, toX, toY, zeroY, rcMax, shMax: shMax.toFixed(2) };
	});

	const factorProfitByRunCountBucket = $derived.by(() => {
		if (!factorStats || factorStats.length < 5) return null;
		const map = new Map<number, number[]>();
		for (const f of factorStats) {
			if (f.count == null || f.avg_profit == null) continue;
			const rc = f.count as number;
			const bucket = rc <= 5 ? 5 : rc <= 10 ? 10 : rc <= 20 ? 20 : rc <= 50 ? 50 : 100;
			const arr = map.get(bucket) ?? [];
			arr.push(f.avg_profit as number);
			map.set(bucket, arr);
		}
		if (map.size < 3) return null;
		const buckets = [...map.keys()].sort((a, b) => a - b);
		const rows = buckets.map((b) => {
			const arr = map.get(b)!;
			return { b: `≤${b}`, avg: arr.reduce((a, v) => a + v, 0) / arr.length, count: arr.length };
		});
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 300,
			H = 72,
			PAD = 8;
		const bw = (W - PAD * 2) / rows.length - 2;
		const midY = H / 2;
		return { rows, maxAbs, W, H, PAD, bw, midY };
	});

	const factorCalmarByTF = $derived.by(() => {
		if (!factorStats || factorStats.length < 4) return null;
		const map = new Map<string, number[]>();
		for (const f of factorStats) {
			if (!f.timeframe || f.avg_calmar == null) continue;
			const arr = map.get(f.timeframe as string) ?? [];
			arr.push(f.avg_calmar as number);
			map.set(f.timeframe as string, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([tf, vals]) => ({ tf, avg: vals.reduce((a, v) => a + v, 0) / vals.length }))
			.sort((a, b) => b.avg - a.avg);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 300,
			H = rows.length * 20 + 6,
			PAD = 8,
			barMaxW = W - 50;
		const zeroX = PAD + barMaxW / 2;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const factorTopSharpeTimeline = $derived.by(() => {
		if (!factorStats || factorStats.length < 5) return null;
		const sorted = [...factorStats]
			.filter((f) => f.avg_sharpe != null)
			.sort((a, b) => (b.avg_sharpe as number) - (a.avg_sharpe as number))
			.slice(0, 8);
		if (sorted.length < 4) return null;
		const maxSh = Math.max(...sorted.map((f) => f.avg_sharpe as number), 0.01);
		const W = 320,
			H = sorted.length * 20 + 6,
			PAD = 8,
			barMaxW = W - 110;
		return { sorted, maxSh, W, H, PAD, barMaxW };
	});

	const factorDrawdownVsSharpeScatter = $derived.by(() => {
		if (!factorStats || factorStats.length < 6) return null;
		const pts = factorStats
			.filter((f) => f.avg_sharpe != null && f.avg_dd != null)
			.map((f) => ({
				sharpe: f.avg_sharpe as number,
				dd: f.avg_dd as number,
				name: ((f.factor as string) ?? '').slice(0, 10)
			}));
		if (pts.length < 5) return null;
		const shMin = Math.min(...pts.map((p) => p.sharpe));
		const shMax = Math.max(...pts.map((p) => p.sharpe), 0.01);
		const ddMax = Math.max(...pts.map((p) => p.dd), 0.01);
		const shRange = shMax - shMin || 0.01;
		const W = 300,
			H = 90,
			PAD = 10;
		const toX = (sh: number) => PAD + ((sh - shMin) / shRange) * (W - PAD * 2);
		const toY = (dd: number) => H - PAD - (dd / ddMax) * (H - PAD * 2);
		const zeroX = toX(0);
		return { pts, W, H, PAD, toX, toY, zeroX };
	});

	const factorRunsByTFBars = $derived.by(() => {
		if (!factorStats || factorStats.length < 4) return null;
		const map = new Map<string, number>();
		for (const f of factorStats) {
			if (!f.timeframe) continue;
			map.set(
				f.timeframe as string,
				(map.get(f.timeframe as string) ?? 0) + ((f.count as number) ?? 0)
			);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([tf, count]) => ({ tf, count }))
			.sort((a, b) => b.count - a.count);
		const maxCount = Math.max(...rows.map((r) => r.count), 1);
		const W = 300,
			H = rows.length * 20 + 6,
			PAD = 8,
			barMaxW = W - 40;
		return { rows, maxCount, W, H, PAD, barMaxW };
	});

	const factorProfitCDF = $derived.by(() => {
		if (!factorStats || factorStats.length < 15) return null;
		const vals = factorStats
			.filter((f) => f.avg_profit != null)
			.map((f) => f.avg_profit as number)
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
		return {
			polyline,
			W,
			H,
			PAD,
			zeroX,
			minV: minV.toFixed(2),
			maxV: maxV.toFixed(2),
			median: median.toFixed(2)
		};
	});

	const factorSortinoCDF = $derived.by(() => {
		if (!factorStats || factorStats.length < 15) return null;
		const vals = factorStats
			.filter((f) => f.avg_sortino != null)
			.map((f) => f.avg_sortino as number)
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

	const factorWinRateRanking = $derived.by(() => {
		if (!factorStats || factorStats.length < 5) return null;
		const rows = factorStats
			.filter((f) => f.avg_win_rate != null)
			.map((f) => ({ name: (f.factor as string).slice(0, 22), wr: f.avg_win_rate as number }))
			.sort((a, b) => b.wr - a.wr)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxWR = Math.max(...rows.map((r) => r.wr), 1);
		const W = 300,
			H = rows.length * 18 + 10,
			PAD = 8,
			barMaxW = W - PAD * 2 - 90;
		return { rows, maxWR, W, H, PAD, barMaxW };
	});

	const factorCalmarCDF = $derived.by(() => {
		if (!factorStats || factorStats.length < 10) return null;
		const vals = factorStats
			.filter((f) => f.avg_calmar != null)
			.map((f) => f.avg_calmar as number)
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
		const zeroX = toX(0);
		const median = vals[Math.floor(vals.length / 2)].toFixed(2);
		return { polyline, zeroX, W, H, PAD, minV: minV.toFixed(2), maxV: maxV.toFixed(2), median };
	});

	const factorAvgProfitByRunBucket = $derived.by(() => {
		if (!factorStats || factorStats.length < 5) return null;
		const map = new Map<string, number[]>();
		for (const f of factorStats) {
			if (f.avg_profit == null || f.count == null) continue;
			const rc = f.count as number;
			const bucket = rc <= 5 ? '1-5' : rc <= 15 ? '6-15' : rc <= 30 ? '16-30' : '30+';
			const arr = map.get(bucket) ?? [];
			arr.push(f.avg_profit as number);
			map.set(bucket, arr);
		}
		if (map.size < 2) return null;
		const ORDER = ['1-5', '6-15', '16-30', '30+'];
		const rows = ORDER.filter((k) => map.has(k)).map((k) => {
			const arr = map.get(k)!;
			return { k, avg: arr.reduce((s, v) => s + v, 0) / arr.length };
		});
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 300,
			H = rows.length * 22 + 6,
			PAD = 8,
			barMaxW = W - 60;
		const zeroX = PAD + 40 + barMaxW / 2;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const factorSortinoVsWinRateScatter = $derived.by(() => {
		if (!factorStats || factorStats.length < 8) return null;
		const pts = factorStats
			.filter((f) => f.avg_sortino != null && f.avg_win_rate != null)
			.map((f) => ({ sortino: f.avg_sortino as number, wr: f.avg_win_rate as number }));
		if (pts.length < 6) return null;
		const minS = Math.min(...pts.map((p) => p.sortino)),
			maxS = Math.max(...pts.map((p) => p.sortino), minS + 0.1);
		const minWR = Math.min(...pts.map((p) => p.wr)),
			maxWR = Math.max(...pts.map((p) => p.wr), minWR + 1);
		const W = 300,
			H = 80,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - minS) / (maxS - minS)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - minWR) / (maxWR - minWR)) * (H - PAD * 2);
		const zeroX = toX(0);
		return { pts, toX, toY, zeroX, W, H, PAD, minS: minS.toFixed(2), maxS: maxS.toFixed(2) };
	});

	const factorProfitByTF = $derived.by(() => {
		if (!runs || runs.length < 5) return null;
		const map = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.timeframe || r.total_profit_pct == null) continue;
			const arr = map.get(r.timeframe as string) ?? [];
			arr.push(r.total_profit_pct as number);
			map.set(r.timeframe as string, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.filter(([, arr]) => arr.length >= 2)
			.map(([tf, arr]) => ({ tf, avg: arr.reduce((s, v) => s + v, 0) / arr.length }))
			.sort((a, b) => b.avg - a.avg);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 280,
			H = rows.length * 22 + 8,
			PAD = 8,
			barMaxW = W - 50;
		const zeroX = PAD + 30 + barMaxW / 2;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const factorTopCalmarByRunCount = $derived.by(() => {
		if (!factorStats || factorStats.length < 5) return null;
		const rows = factorStats
			.filter((f) => f.factor && f.avg_calmar != null && f.count != null)
			.map((f) => ({
				name: (f.factor as string).slice(0, 18),
				calmar: f.avg_calmar as number,
				n: f.count as number
			}))
			.sort((a, b) => b.calmar - a.calmar)
			.slice(0, 8);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.calmar)), 0.01);
		const W = 320,
			H = rows.length * 18 + 10,
			PAD = 8,
			barMaxW = W - PAD * 2 - 80;
		const zeroX = PAD + 80 + barMaxW / 2;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const factorProfitVsCalmar = $derived.by(() => {
		if (!factorStats || factorStats.length < 8) return null;
		const pts = factorStats
			.filter((f) => f.avg_profit != null && f.avg_calmar != null)
			.map((f) => ({ profit: f.avg_profit as number, calmar: f.avg_calmar as number }));
		if (pts.length < 6) return null;
		const minP = Math.min(...pts.map((p) => p.profit)),
			maxP = Math.max(...pts.map((p) => p.profit), minP + 0.01);
		const minC = Math.min(...pts.map((p) => p.calmar)),
			maxC = Math.max(...pts.map((p) => p.calmar), minC + 0.01);
		const W = 300,
			H = 80,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - minP) / (maxP - minP)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - minC) / (maxC - minC)) * (H - PAD * 2);
		const zeroX = toX(0),
			zeroY = toY(0);
		return { pts, toX, toY, zeroX, zeroY, W, H, PAD, minP: minP.toFixed(1), maxP: maxP.toFixed(1) };
	});

	const factorRunCountByTF = $derived.by(() => {
		if (!runs || runs.length < 5) return null;
		const map = new Map<string, number>();
		for (const r of runs) {
			if (!r.timeframe) continue;
			map.set(r.timeframe as string, (map.get(r.timeframe as string) ?? 0) + 1);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([tf, count]) => ({ tf, count }))
			.sort((a, b) => b.count - a.count);
		const maxCount = Math.max(...rows.map((r) => r.count), 1);
		const W = 260,
			H = 60,
			PAD = 8;
		const bw = (W - PAD * 2) / rows.length - 1;
		return { rows, maxCount, bw, W, H, PAD };
	});

	const factorSharpeByWinRateBucket = $derived.by(() => {
		if (!runs || runs.length < 8) return null;
		const buckets = [
			{ label: '<40%', min: 0, max: 40 },
			{ label: '40-50%', min: 40, max: 50 },
			{ label: '50-60%', min: 50, max: 60 },
			{ label: '>60%', min: 60, max: 100 }
		];
		const rows = buckets
			.map((b) => {
				const vals = runs
					.filter((r) => r.win_rate_pct != null && r.sharpe != null)
					.filter((r) => {
						const wr = r.win_rate_pct as number;
						return wr >= b.min && wr < b.max;
					})
					.map((r) => r.sharpe as number);
				const avg = vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : 0;
				return { label: b.label, avg, n: vals.length };
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

	const factorAvgDrawdownByTF = $derived.by(() => {
		if (!runs || runs.length < 5) return null;
		const map = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.timeframe || r.max_drawdown_pct == null) continue;
			const arr = map.get(r.timeframe as string) ?? [];
			arr.push(r.max_drawdown_pct as number);
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

	const factorTopProfitByFactor = $derived.by(() => {
		if (!runs || runs.length < 5) return null;
		const map = new Map<string, number[]>();
		for (const r of runs) {
			if (!r.factors?.length || r.total_profit_pct == null) continue;
			for (const f of r.factors) {
				const arr = map.get(f) ?? [];
				arr.push(r.total_profit_pct as number);
				map.set(f, arr);
			}
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([factor, vals]) => ({
				factor: (factor as string).slice(0, 18),
				best: Math.max(...vals)
			}))
			.sort((a, b) => b.best - a.best)
			.slice(0, 8);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.best)), 0.01);
		const W = 280,
			H = rows.length * 18 + 8,
			PAD = 8,
			barMaxW = W - PAD * 2 - 80;
		const zeroX = PAD + 80 + barMaxW / 2;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const factorRunsByMonth = $derived.by(() => {
		if (!runs || runs.length < 5) return null;
		const byMonth = new Map<string, number>();
		for (const r of runs) {
			if (!r.imported_at) continue;
			const mo = (r.imported_at as string).slice(0, 7);
			byMonth.set(mo, (byMonth.get(mo) ?? 0) + 1);
		}
		if (byMonth.size < 3) return null;
		const pts = [...byMonth.entries()]
			.sort(([a], [b]) => a.localeCompare(b))
			.map(([mo, count]) => ({ mo: mo.slice(5), count }));
		const maxCount = Math.max(...pts.map((p) => p.count), 1);
		const W = 280,
			H = 65,
			PAD = 8;
		const bw = Math.max(1, (W - PAD * 2) / pts.length - 0.5);
		return { pts, maxCount, bw, W, H, PAD };
	});

	const factorAvgProfitCDF = $derived.by(() => {
		if (!runs || runs.length < 10) return null;
		const byFactor = new Map<string, number[]>();
		for (const r of runs) {
			if (r.factors == null || r.factors.length === 0 || r.total_profit_pct == null) continue;
			for (const f of r.factors) {
				const arr = byFactor.get(f) ?? [];
				arr.push(r.total_profit_pct as number);
				byFactor.set(f, arr);
			}
		}
		if (byFactor.size < 4) return null;
		const avgs = [...byFactor.entries()]
			.map(([, arr]) => arr.reduce((s, v) => s + v, 0) / arr.length)
			.sort((a, b) => a - b);
		const minV = avgs[0],
			maxV = avgs[avgs.length - 1],
			rng = maxV - minV || 1;
		const W = 280,
			H = 65,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - minV) / rng) * (W - PAD * 2);
		const toY = (i: number) => H - PAD - (i / Math.max(avgs.length - 1, 1)) * (H - PAD * 2);
		const polyline = avgs.map((v, i) => `${toX(v).toFixed(1)},${toY(i).toFixed(1)}`).join(' ');
		const median = avgs[Math.floor(avgs.length / 2)];
		return {
			polyline,
			toX,
			toY,
			W,
			H,
			PAD,
			minV: minV.toFixed(2),
			maxV: maxV.toFixed(2),
			median: median.toFixed(2)
		};
	});

	const factorSharpeCalmarScatter2 = $derived.by(() => {
		if (!runs || runs.length < 10) return null;
		const pts = runs
			.filter((r) => r.sharpe != null && r.calmar != null)
			.map((r) => ({
				x: r.sharpe as number,
				y: r.calmar as number,
				wr: (r.win_rate_pct as number) ?? 50
			}));
		if (pts.length < 8) return null;
		const xs = pts.map((p) => p.x),
			ys = pts.map((p) => p.y);
		const minX = Math.min(...xs),
			maxX = Math.max(...xs),
			minY = Math.min(...ys),
			maxY = Math.max(...ys);
		const W = 280,
			H = 80,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - minX) / (maxX - minX || 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - minY) / (maxY - minY || 1)) * (H - PAD * 2);
		return {
			pts,
			W,
			H,
			PAD,
			toX,
			toY,
			minX: minX.toFixed(1),
			maxX: maxX.toFixed(1),
			minY: minY.toFixed(1),
			maxY: maxY.toFixed(1)
		};
	});

	const factorWinRateTrend = $derived.by(() => {
		if (!runs || runs.length < 15) return null;
		const sorted = [...runs]
			.filter((r) => r.started_at && r.win_rate_pct != null)
			.sort(
				(a, b) =>
					new Date(a.started_at as string).getTime() - new Date(b.started_at as string).getTime()
			);
		if (sorted.length < 15) return null;
		const win = 10;
		const smoothed = sorted.slice(win - 1).map((_, i) => {
			const slice = sorted.slice(i, i + win);
			return {
				idx: i + win - 1,
				wr: slice.reduce((s, r) => s + (r.win_rate_pct as number), 0) / slice.length
			};
		});
		const minWR = Math.min(...smoothed.map((s) => s.wr));
		const maxWR = Math.max(...smoothed.map((s) => s.wr), minWR + 0.01);
		const W = 280,
			H = 65,
			PAD = 8;
		const toX = (i: number) => PAD + (i / (smoothed.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - minWR) / (maxWR - minWR)) * (H - PAD * 2);
		const polyline = smoothed.map((s, i) => `${toX(i)},${toY(s.wr)}`).join(' ');
		const y50 = toY(50);
		return {
			polyline,
			W,
			H,
			PAD,
			toX,
			toY,
			y50,
			minWR: minWR.toFixed(1),
			maxWR: maxWR.toFixed(1),
			n: smoothed.length
		};
	});

	const factorWinRateByDow = $derived.by(() => {
		if (!runs || runs.length < 10) return null;
		const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
		const byDow = new Map<number, { wins: number; total: number }>();
		for (const r of runs) {
			if (!r.started_at || r.win_rate_pct == null) continue;
			const d = new Date(r.started_at as string).getUTCDay();
			const prev = byDow.get(d) ?? { wins: 0, total: 0 };
			prev.total++;
			if ((r.win_rate_pct as number) >= 50) prev.wins++;
			byDow.set(d, prev);
		}
		const bars = [0, 1, 2, 3, 4, 5, 6]
			.filter((d) => byDow.has(d) && (byDow.get(d)?.total ?? 0) >= 2)
			.map((d) => ({
				label: DOW[d],
				wr: ((byDow.get(d)?.wins ?? 0) / (byDow.get(d)?.total ?? 1)) * 100,
				n: byDow.get(d)?.total ?? 0
			}));
		if (bars.length < 3) return null;
		const maxWR = Math.max(...bars.map((b) => b.wr), 1);
		const W = 280,
			H = 65,
			PAD = 8;
		const bw = Math.max(8, (W - PAD * 2) / bars.length - 2);
		return { bars, maxWR, W, H, PAD, bw };
	});
</script>

<svelte:head>
	<title>Factor Attribution · Crypto Quant</title>
</svelte:head>

<main class="mx-auto w-full max-w-[1600px] px-4 py-8 sm:px-6">
	<h1 class="text-2xl font-semibold tracking-tight">Factor Attribution</h1>
	<p class="mt-1 max-w-3xl text-sm text-muted-foreground">
		Which indicator/regime tags correlate with better backtest results?
	</p>

	<!-- KPI row -->
	<div class="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3">
		<div class="rounded-xl border border-border bg-card p-4">
			<p class="text-xs tracking-wide text-muted-foreground uppercase">Unique Factors</p>
			<p class="mt-1 font-mono text-2xl font-semibold">{factorStats.length}</p>
		</div>
		<div class="rounded-xl border border-border bg-card p-4">
			<p class="text-xs tracking-wide text-muted-foreground uppercase">Runs Analyzed</p>
			<p class="mt-1 font-mono text-2xl font-semibold">{totalRuns}</p>
		</div>
		<div class="col-span-2 rounded-xl border border-border bg-card p-4 sm:col-span-1">
			<p class="text-xs tracking-wide text-muted-foreground uppercase">Best Factor</p>
			{#if bestFactor}
				<p class="mt-1 truncate font-mono text-base font-semibold text-green-400">
					{bestFactor.factor}
				</p>
				<p class="text-xs text-muted-foreground">
					median profit {fmt(bestFactor.median_profit)}%
				</p>
			{:else}
				<p class="mt-1 text-muted-foreground">—</p>
			{/if}
		</div>
	</div>

	<!-- Factor × metric heatmap -->
	{#if heatmapRows.length > 0}
		<section class="mt-6 rounded-lg border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Factor × Metric Heatmap <span class="ml-1 text-xs font-normal text-muted-foreground"
					>(top {heatmapRows.length} by run count · column-normalized)</span
				>
				<ChartInfo metric="factor" {lang} />
			</h2>
			<div class="overflow-x-auto">
				<table class="w-full text-xs">
					<thead>
						<tr>
							<th class="w-36 pr-4 pb-2 text-left text-[10px] text-muted-foreground uppercase"
								>Factor</th
							>
							<th class="w-10 px-1 pb-2 text-center text-[10px] text-muted-foreground">Runs</th>
							{#each HEATMAP_METRICS as m, _i (_i)}
								<th class="w-16 px-1 pb-2 text-center text-[10px] text-muted-foreground uppercase"
									>{m.label}</th
								>
							{/each}
						</tr>
					</thead>
					<tbody class="font-mono">
						{#each heatmapRows as row (row.factor)}
							<tr class="border-t border-border/30">
								<td
									class="max-w-36 truncate py-1 pr-4 text-[11px] text-foreground"
									title={row.factor}>{row.factor}</td
								>
								<td class="px-1 py-1 text-center text-[10px] text-muted-foreground">{row.count}</td>
								{#each row.cells as cell, ci (ci)}
									<td class="px-1 py-1 text-center">
										<div
											class="rounded px-1 py-0.5 text-[10px] {heatCell(cell.score)}"
											title="{HEATMAP_METRICS[ci].label}: {typeof cell.raw === 'number'
												? cell.raw.toFixed(2)
												: '—'}"
										>
											{typeof cell.raw === 'number' ? cell.raw.toFixed(1) : '—'}
										</div>
									</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<div class="mt-2 flex items-center gap-3 text-[10px] text-muted-foreground">
				<span class="flex items-center gap-1"
					><span class="inline-block h-3 w-5 rounded-sm bg-green-500/70"></span>best in column</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-3 w-5 rounded-sm bg-muted/20"></span>middle</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-3 w-5 rounded-sm bg-red-500/60"></span>worst in column</span
				>
			</div>
		</section>
	{/if}

	<!-- Controls: sort + filter -->
	<div class="mt-6 flex flex-wrap items-center gap-3">
		<span class="text-xs text-muted-foreground">Sort by:</span>
		{#each [['profit', 'Profit'], ['sharpe', 'Sharpe'], ['calmar', 'Calmar'], ['count', 'Count'], ['dd', 'Drawdown']] as [key, label], _i (_i)}
			<button
				type="button"
				class="rounded-full border px-3 py-1 text-xs transition-colors"
				class:border-primary={sortKey === key}
				class:bg-primary={sortKey === key}
				class:text-primary-foreground={sortKey === key}
				class:border-border={sortKey !== key}
				class:text-muted-foreground={sortKey !== key}
				class:hover:bg-accent={sortKey !== key}
				onclick={() => {
					sortKey = key as SortKey;
				}}
			>
				{label}
			</button>
		{/each}
		<input
			type="text"
			placeholder="Filter factors…"
			bind:value={filterText}
			class="ml-auto rounded-md border border-border bg-secondary px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:ring-1 focus:ring-primary focus:outline-none"
		/>
	</div>

	<!-- Factor table -->
	{#if sortedStats.length === 0}
		<div
			class="mt-8 rounded-xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground"
		>
			{filterText
				? 'No factors match your filter.'
				: 'No factor data found. Run backtests with factor tags to populate this page.'}
		</div>
	{:else}
		<div class="mt-4 overflow-x-auto rounded-xl border border-border bg-card">
			<table class="w-full text-xs">
				<thead class="bg-secondary text-[11px] text-muted-foreground uppercase">
					<tr>
						<th class="px-4 py-3 text-left whitespace-nowrap">Factor</th>
						<th class="px-4 py-3 text-right whitespace-nowrap">Runs</th>
						<th class="px-4 py-3 text-left whitespace-nowrap">Strategies</th>
						<th class="min-w-[130px] px-4 py-3 text-right whitespace-nowrap">Median Profit%</th>
						<th class="min-w-[110px] px-4 py-3 text-right whitespace-nowrap">Avg Sharpe</th>
						<th class="min-w-[110px] px-4 py-3 text-right whitespace-nowrap">Avg Calmar</th>
						<th class="min-w-[110px] px-4 py-3 text-right whitespace-nowrap">Avg DD%</th>
						<th class="min-w-[110px] px-4 py-3 text-right whitespace-nowrap">Win Rate%</th>
					</tr>
				</thead>
				<tbody>
					{#each sortedStats as stat, _i (_i)}
						<tr class="border-t border-border transition-colors hover:bg-accent/30">
							<!-- Factor chip -->
							<td class="px-4 py-2.5">
								<span class="rounded bg-secondary px-2 py-0.5 font-mono text-xs">
									{stat.factor}
								</span>
							</td>
							<!-- Run count -->
							<td class="px-4 py-2.5 text-right font-mono">{stat.count}</td>
							<!-- Strategies -->
							<td class="max-w-[180px] px-4 py-2.5">
								<div class="flex flex-wrap gap-1">
									{#each stat.strategies.slice(0, 3) as strat, _i (_i)}
										<span
											class="max-w-[80px] truncate rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px]"
											title={strat}
										>
											{strat}
										</span>
									{/each}
									{#if stat.strategies.length > 3}
										<span class="text-[10px] text-muted-foreground"
											>+{stat.strategies.length - 3}</span
										>
									{/if}
								</div>
							</td>
							<!-- Median Profit% with bar -->
							<td class="px-4 py-2.5 text-right">
								<div class="flex items-center justify-end gap-2">
									<div class="w-16 shrink-0">
										<div
											class="h-1 rounded-sm"
											style="width: {barWidth(
												stat.median_profit,
												maxProfit
											)}%; background: {stat.median_profit >= 0 ? '#4ade80' : '#f87171'}"
										></div>
									</div>
									<span
										class="w-14 text-right font-mono font-semibold"
										class:text-green-400={stat.median_profit > 0}
										class:text-red-400={stat.median_profit < 0}
									>
										{fmt(stat.median_profit)}%
									</span>
								</div>
							</td>
							<!-- Avg Sharpe with bar -->
							<td class="px-4 py-2.5 text-right">
								<div class="flex items-center justify-end gap-2">
									<div class="w-16 shrink-0">
										{#if stat.median_sharpe != null && stat.median_sharpe > 0}
											<div
												class="h-1 rounded-sm"
												style="width: {barWidth(
													stat.median_sharpe,
													maxSharpe
												)}%; background: #4a9eff"
											></div>
										{/if}
									</div>
									<span class="w-14 text-right font-mono">{fmt(stat.median_sharpe)}</span>
								</div>
							</td>
							<!-- Avg Calmar with bar -->
							<td class="px-4 py-2.5 text-right">
								<div class="flex items-center justify-end gap-2">
									<div class="w-16 shrink-0">
										{#if stat.median_calmar != null && stat.median_calmar > 0}
											<div
												class="h-1 rounded-sm"
												style="width: {barWidth(
													stat.median_calmar,
													maxCalmar
												)}%; background: #a78bfa"
											></div>
										{/if}
									</div>
									<span class="w-14 text-right font-mono">{fmt(stat.median_calmar)}</span>
								</div>
							</td>
							<!-- Avg DD% with bar (lower = better, inverted) -->
							<td class="px-4 py-2.5 text-right">
								<div class="flex items-center justify-end gap-2">
									<div class="w-16 shrink-0">
										<div
											class="h-1 rounded-sm"
											style="width: {barWidth(stat.avg_dd, maxDd)}%; background: #f87171"
										></div>
									</div>
									<span class="w-14 text-right font-mono text-red-400">{fmt(stat.avg_dd)}%</span>
								</div>
							</td>
							<!-- Win Rate% with bar -->
							<td class="px-4 py-2.5 text-right">
								<div class="flex items-center justify-end gap-2">
									<div class="w-16 shrink-0">
										<div
											class="h-1 rounded-sm"
											style="width: {barWidth(stat.win_rate, maxWinRate)}%; background: #34d399"
										></div>
									</div>
									<span class="w-14 text-right font-mono">{fmt(stat.win_rate)}%</span>
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}

	<!-- Factor co-occurrence combos -->
	{#if topCombos.length > 0}
		<section class="mt-10">
			<h2 class="text-base font-semibold tracking-tight">
				Top Factor Co-occurrences <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mt-1 text-sm text-muted-foreground">
				Factor pairs that appear together most often and their combined median profit.
			</p>
			<div class="mt-4 overflow-x-auto rounded-xl border border-border bg-card">
				<table class="w-full text-xs">
					<thead class="bg-secondary text-[11px] text-muted-foreground uppercase">
						<tr>
							<th class="px-4 py-3 text-left whitespace-nowrap">Factor A</th>
							<th class="px-4 py-3 text-left whitespace-nowrap">Factor B</th>
							<th class="px-4 py-3 text-right whitespace-nowrap">Co-occurrences</th>
							<th class="px-4 py-3 text-right whitespace-nowrap">Median Profit%</th>
						</tr>
					</thead>
					<tbody>
						{#each topCombos as combo, _i (_i)}
							<tr class="border-t border-border transition-colors hover:bg-accent/30">
								<td class="px-4 py-2.5">
									<span class="rounded bg-secondary px-2 py-0.5 font-mono">{combo.a}</span>
								</td>
								<td class="px-4 py-2.5">
									<span class="rounded bg-secondary px-2 py-0.5 font-mono">{combo.b}</span>
								</td>
								<td class="px-4 py-2.5 text-right font-mono">{combo.count}</td>
								<td
									class="px-4 py-2.5 text-right font-mono font-semibold"
									class:text-green-400={combo.median_profit > 0}
									class:text-red-400={combo.median_profit < 0}
								>
									{fmt(combo.median_profit)}%
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{/if}

	{#if factorTrend && factorTrend.length > 0}
		<section class="mt-10 rounded-lg border bg-card p-5">
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Factor Win-Rate Trend <span class="ml-1 text-xs font-normal text-muted-foreground"
						>(top factors · 4 time periods)</span
					>
					<ChartInfo metric="factor" {lang} />
				</h2>
				<span class="text-[11px] text-muted-foreground">↑ improving · ↓ degrading</span>
			</div>
			<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
				{#each factorTrend as ft, _i (_i)}
					{@const TW = 80}
					{@const TH = 32}
					{@const TPAD = 3}
					{@const valid = ft.pts.filter((v): v is number => v != null)}
					{@const mn = Math.min(...valid)}
					{@const mx = Math.max(...valid, mn + 0.1)}
					{@const pts = ft.pts.map((v, i) => {
						const x = TPAD + (i / (ft.pts.length - 1)) * (TW - TPAD * 2);
						const y = v == null ? null : TH - TPAD - ((v - mn) / (mx - mn)) * (TH - TPAD * 2);
						return { x, y, v };
					})}
					{@const polyline = pts
						.filter((p) => p.y != null)
						.map((p) => `${p.x.toFixed(1)},${p.y!.toFixed(1)}`)
						.join(' ')}
					<div class="flex items-center gap-3 rounded-lg border bg-secondary/30 p-3">
						<div>
							<svg viewBox="0 0 {TW} {TH}" width={TW} height={TH}>
								<polyline
									points={polyline}
									fill="none"
									stroke={ft.trend > 1
										? 'rgb(34,197,94)'
										: ft.trend < -1
											? 'rgb(239,68,68)'
											: 'rgb(148,163,184)'}
									stroke-width="1.5"
									stroke-linejoin="round"
								/>
								{#each pts as p, _i (_i)}
									{#if p.y != null}
										<circle
											cx={p.x}
											cy={p.y}
											r="2"
											fill={ft.trend > 1
												? 'rgb(34,197,94)'
												: ft.trend < -1
													? 'rgb(239,68,68)'
													: 'rgb(148,163,184)'}
										/>
									{/if}
								{/each}
							</svg>
						</div>
						<div class="min-w-0">
							<div class="truncate text-[11px] font-semibold">{ft.factor}</div>
							<div class="font-mono text-[10px] text-muted-foreground">
								WR {ft.latest.toFixed(1)}%
								<span
									class:text-green-400={ft.trend > 1}
									class:text-red-400={ft.trend < -1}
									class:text-muted-foreground={Math.abs(ft.trend) <= 1}
								>
									{ft.trend >= 0 ? '+' : ''}{ft.trend.toFixed(1)}pp
								</span>
							</div>
						</div>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Each dot = avg win-rate of runs with this factor in that time period. pp = percentage-point
				change from first to last period.
			</p>
		</section>
	{/if}

	{#if factorStats.length >= 3}
		{@const wrTop = [...factorStats]
			.filter((f) => f.win_rate > 0 && f.count >= 2)
			.sort((a, b) => b.win_rate - a.win_rate)
			.slice(0, 12)}
		{@const wrMax = wrTop.length ? wrTop[0].win_rate : 100}
		<section class="mb-6">
			<h2 class="mb-3 text-sm font-semibold tracking-wider text-muted-foreground uppercase">
				Win-Rate Leaderboard <ChartInfo metric="winRate" {lang} />
			</h2>
			<div class="rounded-lg border bg-card p-4">
				<div class="space-y-2">
					{#each wrTop as f, i (i)}
						{@const barW = Math.max(2, (f.win_rate / wrMax) * 100)}
						{@const tone =
							f.win_rate >= 60
								? 'bg-green-500/70'
								: f.win_rate >= 50
									? 'bg-yellow-500/70'
									: 'bg-red-500/60'}
						<div class="flex items-center gap-2 text-[11px]">
							<span class="w-4 text-right font-mono text-muted-foreground">{i + 1}</span>
							<span class="w-28 truncate font-medium" title={f.factor}>{f.factor}</span>
							<div class="h-4 flex-1 overflow-hidden rounded bg-secondary/40">
								<div class="h-full rounded {tone}" style="width:{barW}%"></div>
							</div>
							<span class="w-12 text-right font-mono">{f.win_rate.toFixed(1)}%</span>
							<span class="w-12 text-right font-mono text-muted-foreground">{f.count}r</span>
						</div>
					{/each}
				</div>
				<p class="mt-3 text-[10px] text-muted-foreground">
					Factors ranked by average win-rate across all runs (min 2 runs). r = run count.
				</p>
			</div>
		</section>
	{/if}

	{#if ddLeaderboard}
		<section class="mb-6">
			<h2 class="mb-3 text-sm font-semibold tracking-wider text-muted-foreground uppercase">
				Lowest Avg Drawdown Factors <ChartInfo metric="maxDrawdown" {lang} />
			</h2>
			<div class="rounded-lg border bg-card p-4">
				<div class="space-y-2">
					{#each ddLeaderboard as row, i (i)}
						<div class="flex items-center gap-2 text-[11px]">
							<span class="w-4 text-right font-mono text-muted-foreground">{i + 1}</span>
							<span class="w-28 truncate font-medium" title={row.factor}>{row.factor}</span>
							<div class="h-4 flex-1 overflow-hidden rounded bg-secondary/40">
								<div
									class="h-full rounded"
									style="width:{row.barPct}%; background:{row.avgDd <= 15
										? 'var(--ch-profit)'
										: row.avgDd <= 30
											? 'var(--ch-warn)'
											: 'var(--ch-loss)'}"
								></div>
							</div>
							<span class="w-14 text-right font-mono">{row.avgDd.toFixed(1)}% DD</span>
							<span class="w-10 text-right font-mono text-muted-foreground">{row.count}r</span>
						</div>
					{/each}
				</div>
				<p class="mt-3 text-[10px] text-muted-foreground">
					Factors ranked by lowest avg max-drawdown (min 3 runs). Green ≤15% · yellow ≤30% · red
					>30%
				</p>
			</div>
		</section>
	{/if}

	{#if calmarLeaderboard}
		<section class="mb-6">
			<h2 class="mb-3 text-sm font-semibold tracking-wider text-muted-foreground uppercase">
				Factor Calmar Leaderboard <ChartInfo metric="factor" {lang} />
			</h2>
			<div class="rounded-lg border bg-card p-4">
				<div class="space-y-1.5">
					{#each calmarLeaderboard as row, i (i)}
						<div class="flex items-center gap-2 text-xs">
							<span class="w-4 shrink-0 text-right font-mono text-muted-foreground">{i + 1}</span>
							<span
								class="w-32 shrink-0 truncate font-mono text-[10px] text-muted-foreground"
								title={row.factor}>{row.factor}</span
							>
							<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
								<div
									class="absolute inset-y-0 left-0 rounded-sm transition-all"
									style="width:{row.barPct.toFixed(1)}%; background:{row.calmar >= 1
										? 'var(--ch-profit-light)'
										: row.calmar >= 0.5
											? 'var(--ch-warn-light)'
											: 'var(--ch-violet-light)'}"
								></div>
								<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]"
									>{row.calmar.toFixed(2)}</span
								>
							</div>
							<span class="w-10 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
								>{row.count}r</span
							>
						</div>
					{/each}
				</div>
				<p class="mt-2 text-[10px] text-muted-foreground">
					Calmar = median profit / median maxDD · ≥1 excellent · 0.5-1 good · r = run count
				</p>
			</div>
		</section>
	{/if}

	{#if wrProfitScatter}
		{@const wps = wrProfitScatter}
		<section class="mb-6">
			<h2 class="mb-3 text-sm font-semibold tracking-wider text-muted-foreground uppercase">
				Win Rate vs Avg Profit <ChartInfo metric="winRate" {lang} />
			</h2>
			<div class="rounded-lg border bg-card p-4">
				<svg viewBox="0 0 {wps.W} {wps.H}" class="w-full" style="height:{wps.H}px;min-width:200px">
					<!-- quadrant lines -->
					{#if wps.zeroX > wps.PAD && wps.zeroX < wps.W - wps.PAD}
						<line
							x1={wps.zeroX}
							y1={wps.PAD}
							x2={wps.zeroX}
							y2={wps.H - wps.PAD}
							stroke="var(--ch-rule)"
							stroke-width="1"
							stroke-dasharray="3 2"
						/>
					{/if}
					{#if wps.fiftyY > wps.PAD && wps.fiftyY < wps.H - wps.PAD}
						<line
							x1={wps.PAD}
							y1={wps.fiftyY}
							x2={wps.W - wps.PAD}
							y2={wps.fiftyY}
							stroke="var(--ch-rule)"
							stroke-width="1"
							stroke-dasharray="3 2"
						/>
						<text x={wps.PAD + 2} y={wps.fiftyY - 2} font-size="7" fill="var(--ch-rule-strong)"
							>WR 50%</text
						>
					{/if}
					{#each wps.dots as d, _i (_i)}
						<circle
							cx={d.x.toFixed(1)}
							cy={d.y.toFixed(1)}
							r={Math.min(6, Math.max(2.5, Math.sqrt(d.count) * 1.2))}
							fill={d.gold
								? 'var(--ch-warn)'
								: d.profit > 0
									? 'var(--ch-profit-light)'
									: 'var(--ch-loss-light)'}
							stroke={d.gold ? '#fde047' : 'none'}
							stroke-width="0.5"
						>
							<title
								>{d.factor} · profit {d.profit >= 0 ? '+' : ''}{d.profit.toFixed(1)}% · WR {(
									d.wr * 100
								).toFixed(0)}% · {d.count} runs</title
							>
						</circle>
					{/each}
					<text x={wps.PAD} y={wps.H - 2} font-size="7" fill="var(--ch-rule)"
						>{wps.xMin.toFixed(0)}%</text
					>
					<text
						x={wps.W - wps.PAD}
						y={wps.H - 2}
						font-size="7"
						fill="var(--ch-rule)"
						text-anchor="end">{wps.xMax.toFixed(0)}%</text
					>
					<text
						x={wps.W - wps.PAD}
						y="10"
						font-size="7"
						fill="var(--ch-warn-light)"
						text-anchor="end">★ high WR + profit</text
					>
				</svg>
				<p class="mt-1 text-[10px] text-muted-foreground">
					x = avg profit% · y = win rate · dot size ∝ run count · yellow = profitable &amp;
					WR&gt;50%
				</p>
			</div>
		</section>
	{/if}

	{#if strategyBreadth}
		<section class="mb-6">
			<h2 class="mb-3 text-sm font-semibold tracking-wider text-muted-foreground uppercase">
				Factor Strategy Breadth <ChartInfo metric="factor" {lang} />
			</h2>
			<div class="rounded-lg border bg-card p-4">
				<div class="space-y-1.5">
					{#each strategyBreadth as row, i (i)}
						<div class="flex items-center gap-2 text-xs">
							<span
								class="w-40 shrink-0 truncate font-mono text-muted-foreground"
								title={row.factor}>{row.factor}</span
							>
							<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
								<div
									class="absolute inset-y-0 left-0 rounded-sm transition-all"
									style="width:{row.barPct.toFixed(1)}%; background:hsl({200 + i * 18},55%,40%)"
								></div>
								<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]"
									>{row.stratCount} strat{row.stratCount !== 1 ? 's' : ''}</span
								>
							</div>
							<span class="w-14 shrink-0 text-right font-mono text-[10px]">{row.count}r</span>
							<span
								class="w-16 shrink-0 text-right font-mono text-[10px]"
								class:text-green-400={row.profit > 0}
								class:text-red-400={row.profit < 0}
								>{row.profit >= 0 ? '+' : ''}{row.profit.toFixed(1)}%</span
							>
						</div>
					{/each}
				</div>
				<p class="mt-2 text-[10px] text-muted-foreground">
					Factors ranked by how many distinct strategies use them · r = run count · % = avg profit
				</p>
			</div>
		</section>
	{/if}

	{#if factorWinRateLeaderboard}
		<section class="mb-6">
			<h2 class="mb-3 text-sm font-semibold tracking-wider text-muted-foreground uppercase">
				Factor Win Rate Leaderboard <ChartInfo metric="factor" {lang} />
			</h2>
			<div class="rounded-lg border bg-card p-4">
				<div class="space-y-1.5">
					{#each factorWinRateLeaderboard as row, _i (_i)}
						<div class="flex items-center gap-2 text-xs">
							<span
								class="w-40 shrink-0 truncate font-mono text-[11px] text-muted-foreground"
								title={row.factor}>{row.factor}</span
							>
							<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
								<div
									class="absolute inset-y-0 left-0 rounded-sm transition-all"
									style="width:{(row.wr * 100).toFixed(1)}%; background:{row.wr >= 0.6
										? 'var(--ch-profit)'
										: row.wr >= 0.45
											? 'var(--ch-warn-light)'
											: 'var(--ch-loss-light)'}"
								></div>
								<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]"
									>{(row.wr * 100).toFixed(0)}% WR</span
								>
							</div>
							<span class="w-10 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
								>{row.count}r</span
							>
							<span
								class="w-16 shrink-0 text-right font-mono text-[10px]"
								class:text-green-400={row.profit > 0}
								class:text-red-400={row.profit < 0}
								>{row.profit >= 0 ? '+' : ''}{row.profit.toFixed(1)}%</span
							>
						</div>
					{/each}
				</div>
				<p class="mt-2 text-[10px] text-muted-foreground">
					Win rate = % of runs that are profitable when factor is present · green ≥60% · amber
					45-60% · r = run count
				</p>
			</div>
		</section>
	{/if}

	{#if factorCoOccurrence && factorCoOccurrence.pairs.length >= 3}
		{@const fco = factorCoOccurrence}
		<section class="mb-6">
			<h2 class="mb-3 text-sm font-semibold tracking-wider text-muted-foreground uppercase">
				Factor Co-occurrence <ChartInfo metric="factorCooccurrence" {lang} />
			</h2>
			<div class="rounded-lg border bg-card p-4">
				<div class="space-y-1.5">
					{#each fco.pairs as p, _i (_i)}
						{@const barW = Math.max(2, (p.count / fco.maxCount) * 100)}
						<div class="flex items-center gap-2 text-[11px]">
							<div class="flex min-w-0 flex-1 items-center gap-1">
								<span class="truncate font-mono text-blue-300" title={p.a}>{p.a}</span>
								<span class="shrink-0 text-muted-foreground">+</span>
								<span class="truncate font-mono text-indigo-300" title={p.b}>{p.b}</span>
							</div>
							<div class="h-3 w-24 shrink-0 overflow-hidden rounded bg-secondary/40">
								<div class="h-full rounded bg-indigo-500/60" style="width:{barW}%"></div>
							</div>
							<span class="w-10 shrink-0 text-right font-mono text-muted-foreground"
								>{p.count}r</span
							>
						</div>
					{/each}
				</div>
				<p class="mt-3 text-[10px] text-muted-foreground">
					Top factor pairs by co-occurrence count across runs. r = run count.
				</p>
			</div>
		</section>
	{/if}

	{#if avgProfitByFactorCount}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Avg Profit by Factor Count
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(does combining more factors improve returns?)</span
				>
				<ChartInfo metric="factor" {lang} />
			</h2>
			<div class="flex h-24 items-end gap-4">
				{#each avgProfitByFactorCount as r, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-1">
						<span class="font-mono text-[9px] text-muted-foreground"
							>{r.avg >= 0 ? '+' : ''}{r.avg.toFixed(1)}%</span
						>
						<div
							class="w-full rounded-t-sm transition-all"
							style="height:{Math.max(3, r.barPct * 0.72)}px; background:{r.avg >= 0
								? 'var(--ch-profit)'
								: 'var(--ch-loss-light)'}"
						></div>
						<span class="font-mono text-[10px] font-semibold">{r.label}</span>
						<span class="font-mono text-[9px] text-muted-foreground"
							>{r.count}r · WR {(r.wr * 100).toFixed(0)}%</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Each column = runs using exactly that many factors · avg = mean total profit% across those
				runs
			</p>
		</section>
	{/if}

	{#if factorMonthlyTrend}
		{@const fmt2 = factorMonthlyTrend}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-2 text-sm font-semibold">
				Top Factor Monthly Profit Trend
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(avg profit% per month for top 5 factors)</span
				>
				<ChartInfo metric="factor" {lang} />
			</h2>
			<svg viewBox="0 0 {fmt2.W} {fmt2.H}" class="w-full" style="height:{fmt2.H}px">
				<line
					x1={fmt2.PAD}
					y1={fmt2.zeroY.toFixed(1)}
					x2={fmt2.W - fmt2.PAD}
					y2={fmt2.zeroY.toFixed(1)}
					stroke="var(--ch-rule)"
					stroke-width="1"
					stroke-dasharray="3 2"
				/>
				{#each fmt2.lines as line, _i (_i)}
					{#each line.segments as seg, _i (_i)}
						<polyline
							points={seg}
							fill="none"
							stroke={line.color}
							stroke-width="1.5"
							opacity="0.85"
						/>
					{/each}
				{/each}
			</svg>
			<div class="mt-2 flex flex-wrap gap-3">
				{#each fmt2.lines as line, i (i)}
					<span class="flex items-center gap-1 font-mono text-[10px]">
						<span class="inline-block h-2 w-4 rounded-sm" style="background:{line.color}"></span>
						{line.factor}
					</span>
				{/each}
			</div>
			<div class="mt-1 flex justify-between text-[10px] text-muted-foreground">
				<span>{fmt2.months[0]}</span>
				<span>{fmt2.months[fmt2.months.length - 1]}</span>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Each line = avg total profit% of runs containing that factor · trend up = factor improving
				over time
			</p>
		</section>
	{/if}

	{#if factorProfitFactorLeaderboard}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Best Profit-Factor per Factor
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(avg profit_factor = gross wins / gross losses · min 5 runs)</span
				>
				<ChartInfo metric="factor" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each factorProfitFactorLeaderboard as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
							>{i + 1}</span
						>
						<span class="w-36 shrink-0 truncate font-mono text-[10px]" title={r.factor}
							>{r.factor}</span
						>
						<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm"
								style="width:{r.barPct.toFixed(1)}%; background:{r.avgPF >= 1.5
									? 'var(--ch-profit-light)'
									: r.avgPF >= 1.0
										? 'var(--ch-warn-light)'
										: 'var(--ch-loss-light)'}"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
								PF {r.avgPF.toFixed(2)}
							</span>
						</div>
						<span class="w-14 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
							>{r.count}r</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Green ≥ 1.5 · yellow 1.0–1.5 · red &lt; 1.0 · PF &gt; 1 = wins outweigh losses
			</p>
		</section>
	{/if}

	{#if lowDrawdownLeaderboard}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Lowest Drawdown Factors
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(safest factors by avg max drawdown · min 5 runs)</span
				>
				<ChartInfo metric="maxDrawdown" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each lowDrawdownLeaderboard as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
							>{i + 1}</span
						>
						<span class="w-36 shrink-0 truncate font-mono text-[10px]" title={r.factor}
							>{r.factor}</span
						>
						<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm bg-green-500/40"
								style="width:{r.barPct.toFixed(1)}%"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
								DD {r.dd.toFixed(1)}%
							</span>
						</div>
						<span class="w-24 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
							{r.count}r · WR {(r.wr * 100).toFixed(0)}%
						</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Shorter bar = lower drawdown = safer · sorted by lowest avg max drawdown across all runs
				containing this factor
			</p>
		</section>
	{/if}

	{#if factorSharpeLeaderboard}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Best Sharpe Factors
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(median Sharpe per factor · min 5 runs)</span
				>
				<ChartInfo metric="factor" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each factorSharpeLeaderboard as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
							>{i + 1}</span
						>
						<span class="w-36 shrink-0 truncate font-mono text-[10px]" title={r.factor}
							>{r.factor}</span
						>
						<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm"
								style="width:{r.barPct.toFixed(1)}%; background:{r.sharpe >= 1
									? 'var(--ch-profit-light)'
									: r.sharpe >= 0
										? 'var(--ch-warn-light)'
										: 'var(--ch-loss-light)'}"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
								S {r.sharpe.toFixed(2)}
							</span>
						</div>
						<span class="w-20 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
							{r.count}r · {r.profit >= 0 ? '+' : ''}{r.profit.toFixed(0)}%
						</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Green ≥ 1 · yellow 0–1 · red &lt; 0 · right = run count and avg profit%
			</p>
		</section>
	{/if}

	{#if factorProfitVolatility}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Most Consistent Factors
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(lowest profit% std dev · shorter bar = more consistent · min 5 runs)</span
				>
				<ChartInfo metric="totalProfit" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each factorProfitVolatility as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
							>{i + 1}</span
						>
						<span class="w-36 shrink-0 truncate font-mono text-[10px]" title={r.factor}
							>{r.factor}</span
						>
						<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm transition-all"
								style="width:{r.barPct.toFixed(1)}%; background:{r.barPct < 30
									? 'var(--ch-profit)'
									: r.barPct < 60
										? 'var(--ch-warn-light)'
										: 'var(--ch-loss-light)'}"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
								σ {r.std.toFixed(1)}%
							</span>
						</div>
						<span class="w-20 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
							avg {r.avg >= 0 ? '+' : ''}{r.avg.toFixed(0)}% · {r.count}r
						</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				σ = standard deviation of profit% across runs · shorter bar = more reliable results · green
				&lt;30th pct · red = high variance
			</p>
		</section>
	{/if}

	{#if factorCalmarLeaderboard}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Best Calmar Factors
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(median Calmar ratio · annual return ÷ max drawdown · min 5 runs)</span
				>
				<ChartInfo metric="calmar" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each factorCalmarLeaderboard as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
							>{i + 1}</span
						>
						<span class="w-36 shrink-0 truncate font-mono text-[10px]" title={r.factor}
							>{r.factor}</span
						>
						<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm"
								style="width:{r.barPct.toFixed(1)}%; background:{r.calmar >= 2
									? 'var(--ch-profit-light)'
									: r.calmar >= 1
										? 'var(--ch-warn-light)'
										: 'var(--ch-violet-light)'}"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
								C {r.calmar.toFixed(2)}
							</span>
						</div>
						<span class="w-20 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
							{r.count}r · {r.profit >= 0 ? '+' : ''}{r.profit.toFixed(0)}%
						</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Green ≥ 2 · yellow 1–2 · higher Calmar = better return per unit of drawdown risk
			</p>
		</section>
	{/if}

	{#if factorSortinoLeaderboard}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Best Sortino Factors
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(median Sortino ratio · return ÷ downside deviation · min 5 runs)</span
				>
				<ChartInfo metric="sortino" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each factorSortinoLeaderboard as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
							>{i + 1}</span
						>
						<span class="w-36 shrink-0 truncate font-mono text-[10px]" title={r.factor}
							>{r.factor}</span
						>
						<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm transition-all"
								style="width:{r.barPct.toFixed(1)}%; background:{r.sortino >= 3
									? 'var(--ch-profit-light)'
									: r.sortino >= 1
										? 'var(--ch-warn-light)'
										: 'var(--ch-violet-light)'}"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
								S {r.sortino.toFixed(2)}
							</span>
						</div>
						<span class="w-12 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
							>{r.count}r</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Green ≥3 · yellow 1–3 · Sortino penalizes only downside risk unlike Sharpe which penalizes
				all volatility
			</p>
		</section>
	{/if}

	{#if factorWinCount}
		<section class="mt-6 rounded-lg border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Factor Win Rate (run-level)
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(% of runs with this factor that had positive total profit · min 5 runs)</span
				>
				<ChartInfo metric="factor" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each factorWinCount as r, i (i)}
					{@const color =
						r.wr >= 0.6
							? 'var(--ch-profit)'
							: r.wr >= 0.5
								? 'var(--ch-warn-light)'
								: 'var(--ch-loss-light)'}
					<div class="flex items-center gap-2">
						<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
							>{i + 1}</span
						>
						<span class="w-32 shrink-0 truncate text-xs text-foreground">{r.factor}</span>
						<div class="relative h-4 flex-1 overflow-hidden rounded bg-muted">
							<div
								class="h-full rounded"
								style="width:{(r.wr * 100).toFixed(1)}%; background:{color}"
							></div>
						</div>
						<span class="w-20 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
							>{(r.wr * 100).toFixed(0)}% ({r.wins}/{r.total})</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Green ≥60% · yellow 50–60% · red &lt;50% · win = run had positive total profit%
			</p>
		</section>
	{/if}

	{#if factorAvgHoldingTime}
		<section class="mt-6 rounded-lg border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Avg Holding Time per Factor
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(factors sorted by shortest avg hold · shorter = quicker in-and-out style)</span
				>
				<ChartInfo metric="factor" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each factorAvgHoldingTime as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
							>{i + 1}</span
						>
						<span class="w-32 shrink-0 truncate text-xs text-foreground">{r.factor}</span>
						<div class="relative h-4 flex-1 overflow-hidden rounded bg-muted">
							<div
								class="absolute inset-y-0 left-0 rounded"
								style="width:{r.barPct.toFixed(1)}%; background:var(--ch-violet-light)"
							></div>
						</div>
						<span class="w-20 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
							>{r.avg < 24 ? r.avg.toFixed(1) + 'h' : (r.avg / 24).toFixed(1) + 'd'}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Shorter bar = factor appears in runs with quicker trades · min 5 runs · useful for matching
				factor to trading style
			</p>
		</section>
	{/if}
	{#if factorDrawdownSpread}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Drawdown Consistency by Factor
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(std dev of max drawdown — shorter bar = more predictable risk)</span
				>
				<ChartInfo metric="factor" {lang} />
			</h2>
			<div class="mt-3 space-y-1.5">
				{#each factorDrawdownSpread as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
							>{i + 1}</span
						>
						<span class="w-32 shrink-0 truncate text-xs text-foreground">{r.factor}</span>
						<div class="relative h-4 flex-1 overflow-hidden rounded bg-muted">
							<div
								class="absolute inset-y-0 left-0 rounded"
								style="width:{r.barPct.toFixed(1)}%; background:{r.std < 5
									? 'var(--ch-profit-light)'
									: r.std < 15
										? 'var(--ch-warn-light)'
										: 'var(--ch-loss-light)'}"
							></div>
						</div>
						<span class="w-20 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
							>σ {r.std.toFixed(1)}%</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Green σ&lt;5% · yellow 5–15% · red &gt;15% · low spread = factor produces reliably bounded
				drawdowns
			</p>
		</section>
	{/if}
	{#if factorTopTimeframes}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Factor Timeframe Affinity
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(which timeframes each factor most commonly runs on)</span
				>
				<ChartInfo metric="factor" {lang} />
			</h2>
			<div class="mt-3 space-y-2">
				{#each factorTopTimeframes as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-32 shrink-0 truncate text-xs text-foreground">{r.factor}</span>
						<div class="flex flex-1 gap-1">
							{#each r.topTfs as tf, _i (_i)}
								<span
									class="rounded px-1.5 py-0.5 font-mono text-[9px]"
									style="background:var(--ch-violet-light); border:1px solid var(--ch-violet-light)"
								>
									{tf.tf} <span class="text-muted-foreground">{tf.pct.toFixed(0)}%</span>
								</span>
							{/each}
						</div>
						<span class="w-14 shrink-0 text-right font-mono text-[9px] text-muted-foreground"
							>{r.total} runs</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Top 3 timeframes per factor by run count · % = share of that factor's runs on that timeframe
			</p>
		</section>
	{/if}
	{#if factorPairCoverage}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Pair Coverage by Factor
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(how many distinct trading pairs appear in runs using each factor)</span
				>
				<ChartInfo metric="factor" {lang} />
			</h2>
			<div class="mt-3 space-y-1.5">
				{#each factorPairCoverage as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-36 truncate font-mono text-[10px]" title={r.factor}>{r.factor}</span>
						<div class="relative flex-1" style="height:14px">
							<div
								class="absolute rounded"
								style="height:100%; width:{r.barPct}%; background:var(--ch-violet-light)"
							></div>
						</div>
						<span class="w-20 text-right font-mono text-[10px] text-muted-foreground"
							>{r.pairCount} pairs</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Wider coverage = factor tested across more pairs · narrow coverage may indicate
				pair-specific signal bias
			</p>
		</section>
	{/if}
	{#if factorSortinoVsCalmar}
		{@const svc = factorSortinoVsCalmar}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Factor Risk Map: Sortino vs Calmar
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(avg per-factor · ideal = top-right · dot size = run count)</span
				>
				<ChartInfo metric="factor" {lang} />
			</h2>
			<svg viewBox="0 0 {svc.W} {svc.H}" class="w-full" style="height:110px">
				{#each svc.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r={d.r} fill={d.color} opacity="0.85"
						><title>{d.title}</title></circle
					>
				{/each}
			</svg>
			<div class="flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>Sortino {svc.xMin.toFixed(1)}</span><span>→ avg Sortino →</span><span
					>{svc.xMax.toFixed(1)}</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Y-axis = avg Calmar · green = both ≥1 · yellow = both ≥0 · larger dot = more runs ·
				top-right = best risk-adjusted factors
			</p>
		</section>
	{/if}
	{#if factorBestRunLeaderboard}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Factor Best-Case Run Leaderboard
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(highest single run profit% ever achieved using each factor)</span
				>
				<ChartInfo metric="factor" {lang} />
			</h2>
			<div class="mt-3 space-y-1.5">
				{#each factorBestRunLeaderboard as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
							>{i + 1}</span
						>
						<span class="w-36 shrink-0 truncate font-mono text-[10px]" title={r.factor}
							>{r.factor}</span
						>
						<div class="relative flex-1" style="height:14px">
							<div
								class="absolute rounded"
								style="height:100%; width:{r.barPct.toFixed(1)}%; background:{r.best >= 50
									? 'var(--ch-profit)'
									: r.best >= 10
										? 'var(--ch-violet-light)'
										: r.best >= 0
											? 'var(--ch-warn-light)'
											: 'var(--ch-loss-light)'}"
							></div>
						</div>
						<span
							class="w-16 text-right font-mono text-[10px]"
							style="color:{r.best >= 0 ? 'rgb(74,222,128)' : 'rgb(248,113,113)'}"
							>{r.best >= 0 ? '+' : ''}{r.best.toFixed(1)}%</span
						>
						<span class="w-8 shrink-0 text-right font-mono text-[9px] text-muted-foreground"
							>{r.bestTf ?? '?'}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Peak profit of the best single run that includes each factor · shows each factor's ceiling
				performance potential
			</p>
		</section>
	{/if}

	{#if factorAvgWinRateRanking}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Factor Avg Win Rate <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Average win rate % across all runs that include each factor (min 3 runs)
			</p>
			<div class="mt-3 space-y-1.5">
				{#each factorAvgWinRateRanking as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-32 truncate font-mono text-[10px] text-muted-foreground">{r.factor}</span
						>
						<div
							class="flex-1 overflow-hidden rounded-sm"
							style="height:14px; background:var(--ch-rule-faint)"
						>
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:var(--ch-profit)"
							></div>
						</div>
						<span class="w-12 text-right font-mono text-[10px]" style="color:var(--ch-profit-solid)"
							>{r.avg.toFixed(1)}%</span
						>
						<span class="w-10 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Factors with consistently high win rates tend to generate cleaner entry signals · compare
				with profit to spot high-win-low-profit factors
			</p>
		</section>
	{/if}

	{#if factorCalmarRanking}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Factor Avg Calmar Ratio <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Average Calmar ratio across all runs containing each factor (min 3 runs)
			</p>
			<div class="mt-3 space-y-1.5">
				{#each factorCalmarRanking as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-32 truncate font-mono text-[10px] text-muted-foreground">{r.factor}</span
						>
						<div
							class="flex-1 overflow-hidden rounded-sm"
							style="height:14px; background:var(--ch-rule-faint)"
						>
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:var(--ch-violet)"
							></div>
						</div>
						<span
							class="w-12 text-right font-mono text-[10px]"
							style="color:var(--ch-violet-strong)">{r.avg.toFixed(2)}</span
						>
						<span class="w-10 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Higher Calmar = factor consistently used in strategies that earn more per unit of drawdown ·
				risk-adjusted factor quality
			</p>
		</section>
	{/if}

	{#if factorRunCountTimeline}
		{@const frct = factorRunCountTimeline}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Factor Research Activity Timeline <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Monthly run count for top 5 factors by total usage — shows research focus shifts over time
			</p>
			<svg viewBox="0 0 {frct.W} {frct.H}" class="mt-2 w-full" style="height:60px">
				{#each frct.lines as l, _i (_i)}
					<polyline points={l.poly} fill="none" stroke={l.color} stroke-width="1.5" />
				{/each}
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{frct.firstYm}</span><span>→ months →</span><span>{frct.lastYm}</span>
			</div>
			<div class="mt-2 flex flex-wrap gap-x-4 gap-y-1">
				{#each frct.lines as l, _i (_i)}
					<span class="flex items-center gap-1 font-mono text-[10px] text-muted-foreground">
						<span class="inline-block h-2 w-3 rounded-sm" style="background:{l.color}"></span>
						{l.factor.slice(0, 14)}
					</span>
				{/each}
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Rising line = increasing research investment in that factor · crossing lines = shifting
				research priorities
			</p>
		</section>
	{/if}

	{#if factorProfitEfficiency}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Factor Profit Efficiency (Profit / Drawdown) <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Median profit% ÷ avg drawdown% — factors with highest return per unit of risk (min 3 runs)
			</p>
			<div class="mt-3 space-y-1.5">
				{#each factorProfitEfficiency as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right font-mono text-[10px] text-muted-foreground">{i + 1}</span>
						<span class="w-28 truncate font-mono text-[10px] text-muted-foreground"
							>{r.factor.slice(0, 14)}</span
						>
						<div
							class="flex-1 overflow-hidden rounded-sm"
							style="height:14px; background:var(--ch-rule-faint)"
						>
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:{r.efficiency >= 0
									? 'var(--ch-teal)'
									: 'var(--ch-loss-light)'}"
							></div>
						</div>
						<span
							class="w-14 text-right font-mono text-[10px]"
							style="color:{r.efficiency >= 0 ? 'var(--ch-teal-strong)' : 'var(--ch-loss-solid)'}"
							>×{r.efficiency.toFixed(2)}</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Efficiency &gt;1 = profit exceeds drawdown · factors near top generate the most return for
				each percent of drawdown endured
			</p>
		</section>
	{/if}

	{#if factorWinRateVsProfit}
		{@const fwrvp = factorWinRateVsProfit}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Factor Win Rate vs Median Profit Scatter <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Each dot = one factor · X = avg win rate · Y = median profit% · top-right = ideal
				high-win-rate high-profit factors
			</p>
			<svg viewBox="0 0 {fwrvp.W} {fwrvp.H}" class="mt-2 w-full" style="height:80px">
				<line
					x1={fwrvp.PAD}
					y1={fwrvp.H -
						fwrvp.PAD -
						((0 - fwrvp.yMin) / (fwrvp.yMax - fwrvp.yMin)) * (fwrvp.H - fwrvp.PAD * 2)}
					x2={fwrvp.W - fwrvp.PAD}
					y2={fwrvp.H -
						fwrvp.PAD -
						((0 - fwrvp.yMin) / (fwrvp.yMax - fwrvp.yMin)) * (fwrvp.H - fwrvp.PAD * 2)}
					stroke="var(--ch-rule)"
					stroke-width="0.5"
				/>
				{#each fwrvp.dots as d, _i (_i)}
					<circle
						cx={d.cx}
						cy={d.cy}
						r="3"
						fill={d.good ? 'var(--ch-profit)' : 'var(--ch-loss-light)'}
					/>
				{/each}
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>WR {(fwrvp.xMin * 100).toFixed(0)}%</span><span>→ win rate →</span><span
					>{(fwrvp.xMax * 100).toFixed(0)}%</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Green = win rate &gt;50% and positive median profit · factors in top-right are both reliable
				and profitable on the whole
			</p>
		</section>
	{/if}

	{#if factorStrategyCount}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Factor Strategy Coverage <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Number of distinct strategies that have used each factor — wider adoption = more
				battle-tested factor
			</p>
			<div class="mt-3 space-y-1.5">
				{#each factorStrategyCount as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right font-mono text-[10px] text-muted-foreground">{i + 1}</span>
						<span class="w-28 truncate font-mono text-[10px] text-muted-foreground"
							>{r.factor.slice(0, 14)}</span
						>
						<div
							class="flex-1 overflow-hidden rounded-sm"
							style="height:14px; background:var(--ch-rule-faint)"
						>
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:var(--ch-warn)"
							></div>
						</div>
						<span class="w-12 text-right font-mono text-[10px]" style="color:var(--ch-warn)"
							>{r.stratCount} strats</span
						>
						<span class="w-10 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.runs}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Factors used by many strategies have been validated across diverse approaches · narrow-use
				factors may be highly strategy-specific
			</p>
		</section>
	{/if}

	{#if factorProfitPerTrade}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Factor Profit-per-Trade <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Average profit% per individual trade for runs tagged with each factor (≥4 runs)
			</p>
			<div class="space-y-1">
				{#each factorProfitPerTrade as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-28 truncate text-right font-mono text-[11px] text-muted-foreground"
							>{r.factor}</span
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
							class="w-16 text-right font-mono text-[10px]"
							style="color:{r.positive ? 'var(--ch-violet-strong)' : 'var(--ch-loss-solid)'}"
							>{r.avgPpt > 0 ? '+' : ''}{r.avgPpt.toFixed(3)}%</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Profit-per-trade normalises for run length · factors here with few large wins vs many small
				wins have very different risk profiles
			</p>
		</section>
	{/if}

	{#if factorDrawdownVsProfit}
		{@const fdp = factorDrawdownVsProfit}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Factor Drawdown vs Profit Scatter <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mb-2 text-[11px] text-muted-foreground">
				Each dot = one factor · x-axis: avg drawdown% · y-axis: median profit% · upper-left = ideal
				(low DD, high profit)
			</p>
			<svg viewBox="0 0 {fdp.W} {fdp.H}" class="w-full" style="height:90px">
				<line
					x1="8"
					y1={fdp.zeroY}
					x2={fdp.W - 8}
					y2={fdp.zeroY}
					stroke="var(--ch-rule)"
					stroke-width="0.8"
				/>
				{#each fdp.dots as d, _i (_i)}
					<circle
						cx={d.cx}
						cy={d.cy}
						r="3"
						fill={d.ideal ? 'var(--ch-profit)' : 'var(--ch-loss-light)'}
					/>
				{/each}
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>DD {fdp.xMin.toFixed(1)}%</span><span>← avg drawdown →</span><span
					>DD {fdp.xMax.toFixed(1)}%</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Green = low drawdown + positive profit · upper-left quadrant factors are the most efficient
				risk-adjusted tags to include
			</p>
		</section>
	{/if}

	{#if factorTimeframeDiversity}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Factor Timeframe Diversity <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Number of distinct timeframes each factor tag appears across · high diversity = robust
				across trading horizons
			</p>
			<div class="space-y-1">
				{#each factorTimeframeDiversity as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-28 truncate text-right font-mono text-[11px] text-muted-foreground"
							>{r.factor}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:var(--ch-violet)"
							></div>
						</div>
						<span class="w-8 text-right font-mono text-[10px] text-muted-foreground"
							>{r.tfCount} TFs</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Factors validated across many timeframes are more likely to represent genuine market regimes
				than timeframe-specific artefacts
			</p>
		</section>
	{/if}

	{#if factorProfitFactorRanking}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Factor Profit Factor Ranking <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Median profit factor per factor tag across associated runs (≥4 runs) · PF &gt; 1.2 =
				acceptable edge
			</p>
			<div class="space-y-1">
				{#each factorProfitFactorRanking as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-28 truncate text-right font-mono text-[11px] text-muted-foreground"
							>{r.factor}</span
						>
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
							>PF {r.pf.toFixed(2)}</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				PF = gross wins / gross losses · factors with high PF generate more dollar-value wins than
				losses · combine with win rate for full picture
			</p>
		</section>
	{/if}

	{#if factorMaxDrawdownRanking}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Factor Max Drawdown Ranking <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Median max drawdown% across runs using each factor (≥4 runs) · sorted lowest first
			</p>
			<div class="space-y-1">
				{#each factorMaxDrawdownRanking as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-28 truncate text-right font-mono text-[10px] text-muted-foreground"
							>{r.factor}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:{r.safe
									? 'var(--ch-profit)'
									: 'var(--ch-loss)'}"
							></div>
						</div>
						<span
							class="w-16 text-right font-mono text-[10px]"
							style="color:{r.safe ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
							>{r.dd.toFixed(1)}% DD</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Low drawdown factors = safer signal components · combine with profit factor and Calmar to
				identify best risk-adjusted factors for live use
			</p>
		</section>
	{/if}

	{#if factorTradeCountProfile}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Factor Trade Count Profile <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Median total trades per run using each factor (≥4 runs) · high count = high-frequency signal
				component
			</p>
			<div class="space-y-1">
				{#each factorTradeCountProfile as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-28 truncate text-right font-mono text-[10px] text-muted-foreground"
							>{r.factor}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:var(--ch-violet)"
							></div>
						</div>
						<span class="w-16 text-right font-mono text-[10px] text-muted-foreground"
							>{r.trades.toFixed(0)} trades</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				High trade count = active signal factor · low count = selective entry filter · combine with
				win rate to judge if frequency adds value
			</p>
		</section>
	{/if}
	{#if factorWinLossRatio}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Factor Win/Loss Ratio Leaderboard <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Cumulative wins ÷ losses across runs using each factor (≥3 runs) · distinct from win rate —
				measures magnitude of edge
			</p>
			<div class="space-y-1">
				{#each factorWinLossRatio as r, _i (_i)}
					{@const color =
						r.ratio >= 2
							? 'var(--ch-profit-strong)'
							: r.ratio >= 1
								? 'var(--ch-violet)'
								: 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-28 truncate text-right font-mono text-[10px] text-muted-foreground"
							>{r.factor}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div class="h-full rounded-sm" style="width:{r.barPct}%; background:{color}"></div>
						</div>
						<span class="w-14 text-right font-mono text-[10px]" style="color:{color}"
							>{r.ratio.toFixed(2)}×</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				W/L ratio ≥2× = strong edge · ≥1× = marginal · &lt;1× = more losses than wins · use
				alongside profit factor to distinguish high-frequency from high-return factors
			</p>
		</section>
	{/if}
	{#if factorHighProfitHitRate}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Factor High-Profit Hit Rate (&gt;5%) <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				% of backtest runs achieving &gt;5% total profit — quality threshold rate, distinct from
				basic win rate (&gt;0%)
			</p>
			<div class="space-y-1">
				{#each factorHighProfitHitRate as r, _i (_i)}
					{@const color =
						r.rate >= 0.5
							? 'var(--ch-profit-strong)'
							: r.rate >= 0.3
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-28 truncate text-right font-mono text-[10px] text-muted-foreground"
							>{r.factor}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div
								class="h-full rounded-sm"
								style="width:{(r.rate * 100).toFixed(1)}%; background:{color}"
							></div>
						</div>
						<span class="w-14 text-right font-mono text-[10px]" style="color:{color}"
							>{(r.rate * 100).toFixed(1)}%</span
						>
						<span class="w-14 text-right font-mono text-[9px] text-muted-foreground"
							>{r.hits}/{r.total}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Green ≥50% = reliable high-profit generator · yellow = occasional · red = rarely hits
				threshold · bar width = hit rate directly (not normalized)
			</p>
		</section>
	{/if}
	{#if factorImprovement}
		<section class="rounded-xl border border-border bg-card p-4">
			<h2 class="mb-1 text-sm font-semibold">
				Factor Improvement (Recent vs Older Runs) <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mb-3 text-[10px] text-muted-foreground">
				Compares avg profit % of each factor in recent half of runs vs older half — positive delta =
				improving, negative = declining
			</p>
			<div class="space-y-2">
				{#each factorImprovement as r, _i (_i)}
					{@const isPos = r.delta >= 0}
					{@const color = isPos ? 'var(--ch-profit-strong)' : 'var(--ch-loss-strong)'}
					<div class="flex items-center gap-2">
						<span class="w-28 truncate text-[10px] text-muted-foreground" title={r.factor}
							>{r.factor}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div class="h-full rounded-sm" style="width:{r.barPct}%; background:{color}"></div>
						</div>
						<span class="w-16 text-right font-mono text-[10px]" style="color:{color}"
							>{isPos ? '+' : ''}{r.delta.toFixed(2)}%</span
						>
						<span class="w-20 text-right font-mono text-[9px] text-muted-foreground"
							>{r.recAvg.toFixed(2)} vs {r.oldAvg.toFixed(2)}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Green = factor improving over time · red = factor declining · delta = recent avg − older avg
				· bar width = normalized magnitude
			</p>
		</section>
	{/if}
	{#if factorProfitRangeSpread}
		<section class="rounded-xl border border-border bg-card p-4">
			<h2 class="mb-1 text-sm font-semibold">
				Profit Range Spread by Factor <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mb-3 text-[10px] text-muted-foreground">
				Range between best and worst run profit % for each factor — narrow spread = consistent
				outcomes, wide = high variance
			</p>
			<div class="space-y-1">
				{#each factorProfitRangeSpread as r, _i (_i)}
					{@const consistency =
						r.spread < 20
							? 'var(--ch-profit-strong)'
							: r.spread < 60
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-28 truncate text-[10px] text-muted-foreground" title={r.factor}
							>{r.factor}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:{consistency}"
							></div>
						</div>
						<span class="w-14 text-right font-mono text-[10px]" style="color:{consistency}"
							>±{r.spread.toFixed(0)}%</span
						>
						<span class="w-20 text-right font-mono text-[9px] text-muted-foreground"
							>{r.min.toFixed(0)}…{r.max.toFixed(0)}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Sorted narrowest-first · green ≤20% spread = reliable · yellow ≤60% = moderate variance ·
				red = wide outcome range · prefer factors with tight spreads around positive avg
			</p>
		</section>
	{/if}
	{#if factorProfitQuantile90}
		<section class="rounded-xl border border-border bg-card p-4">
			<h2 class="mb-1 text-sm font-semibold">
				90th Percentile Profit by Factor <ChartInfo metric="factor" {lang} />
			</h2>
			<p class="mb-3 text-[10px] text-muted-foreground">
				90th-percentile total profit % per factor — shows ceiling performance, not just the single
				best outlier run
			</p>
			<div class="space-y-1">
				{#each factorProfitQuantile90 as r, _i (_i)}
					{@const color = r.q90 > 0 ? 'var(--ch-profit-strong)' : 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-28 truncate text-[10px] text-muted-foreground" title={r.factor}
							>{r.factor}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div class="h-full rounded-sm" style="width:{r.barPct}%; background:{color}"></div>
						</div>
						<span class="w-16 text-right font-mono text-[10px]" style="color:{color}"
							>{r.q90 > 0 ? '+' : ''}{r.q90.toFixed(1)}%</span
						>
						<span class="w-20 text-right font-mono text-[9px] text-muted-foreground"
							>med {r.q50.toFixed(1)}% · {r.count}r</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Bar = 90th-percentile profit · sorted descending · high p90 = strong upside potential when
				factor performs well · compare to median for skew assessment
			</p>
		</section>
	{/if}

	{#if factorBestStrategyWinRate}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Best Win Rate Achieved per Factor</h3>
			<p class="mb-3 text-[10px] text-muted-foreground">
				Single highest win_rate_pct observed across all runs using each factor · shows ceiling
				performance · not average — peak potential when factor fires optimally
			</p>
			<div class="space-y-1.5">
				{#each factorBestStrategyWinRate.rows as row, _i (_i)}
					<div class="flex items-center gap-2 text-xs">
						<span class="w-28 shrink-0 truncate font-mono text-[10px] text-muted-foreground"
							>{row.factor}</span
						>
						<div class="relative h-4 flex-1 overflow-hidden rounded bg-muted/30">
							<div
								class="h-full rounded"
								style="width:{((row.best / factorBestStrategyWinRate.maxBest) * 100).toFixed(
									1
								)}%; background:rgba(34,197,94,{Math.min(
									0.85,
									0.3 + (row.best / factorBestStrategyWinRate.maxBest) * 0.55
								)})"
							></div>
						</div>
						<span class="w-12 text-right font-mono">{row.best.toFixed(1)}%</span>
						<span class="w-10 text-right text-[9px] text-muted-foreground">n={row.count}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Top factor = {factorBestStrategyWinRate.rows[0].factor} at {factorBestStrategyWinRate.rows[0].best.toFixed(
					1
				)}% · peak win rate — use alongside avg win rate to detect factors with occasional outlier
				runs vs consistently high accuracy
			</p>
		</section>
	{/if}

	{#if factorSortinoVsDrawdown}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Factor: Avg Sortino vs Avg Drawdown</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Each dot = one factor · x = avg max drawdown % across runs · y = avg Sortino ratio ·
				top-left = low drawdown AND strong downside risk control
			</p>
			<svg viewBox="0 0 {factorSortinoVsDrawdown.W} {factorSortinoVsDrawdown.H}" class="w-full">
				{#if factorSortinoVsDrawdown.zeroY !== null}
					<line
						x1="0"
						y1={factorSortinoVsDrawdown.zeroY}
						x2={factorSortinoVsDrawdown.W}
						y2={factorSortinoVsDrawdown.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				{#each factorSortinoVsDrawdown.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="3" fill="var(--ch-teal)" />
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{factorSortinoVsDrawdown.total} factors · x=drawdown [{factorSortinoVsDrawdown.dMin}%–{factorSortinoVsDrawdown.dMax}%]
				· y=Sortino [{factorSortinoVsDrawdown.sMin}–{factorSortinoVsDrawdown.sMax}] · each point =
				avg across all runs using that factor
			</p>
		</section>
	{/if}

	{#if factorProfitCvRanking}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Factor Profit Consistency (CV Ranking)</h3>
			<p class="mb-3 text-[10px] text-muted-foreground">
				Coefficient of variation of total_profit_pct per factor · lower = more consistent profit
				signal · sorted best-first · high CV = factor produces erratic results
			</p>
			<div class="space-y-1.5">
				{#each factorProfitCvRanking.rows as row, i (i)}
					{@const color =
						row.cv < 0.3
							? 'var(--ch-profit-strong)'
							: row.cv < 0.7
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					<div class="flex items-center gap-2 text-xs">
						<span class="w-4 shrink-0 text-right text-muted-foreground">{i + 1}</span>
						<span class="w-28 shrink-0 truncate font-mono text-[10px]">{row.factor}</span>
						<div class="relative h-4 flex-1 overflow-hidden rounded bg-muted/30">
							<div
								class="h-full rounded"
								style="width:{((row.cv / factorProfitCvRanking.maxCv) * 100).toFixed(
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
				CV = std/mean of profit · green &lt;0.3 = highly consistent · yellow = moderate · red
				&gt;0.7 = unreliable · pair with avg profit ranking for full picture
			</p>
		</section>
	{/if}

	{#if factorWinRateVsCalmar}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Factor: Avg Win Rate vs Avg Calmar</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Each dot = one factor · x = avg win rate % · y = avg Calmar ratio · top-right = high win
				rate AND strong risk-adjusted return · color = combined score (green = elite)
			</p>
			<svg viewBox="0 0 {factorWinRateVsCalmar.W} {factorWinRateVsCalmar.H}" class="w-full">
				{#if factorWinRateVsCalmar.zeroY !== null}
					<line
						x1="0"
						y1={factorWinRateVsCalmar.zeroY}
						x2={factorWinRateVsCalmar.W}
						y2={factorWinRateVsCalmar.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				{#each factorWinRateVsCalmar.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="4" fill={d.color} fill-opacity="0.75" />
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{factorWinRateVsCalmar.total} factors · x=win rate [{factorWinRateVsCalmar.wrMin}%–{factorWinRateVsCalmar.wrMax}%]
				· y=Calmar [{factorWinRateVsCalmar.calMin}–{factorWinRateVsCalmar.calMax}] · each dot = avg
				across all runs tagged with that factor
			</p>
		</section>
	{/if}

	{#if factorAvgTradeCount}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Factor: Avg Trade Count</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Average total trades per backtest run for each factor · high = active/noisy factor · low =
				selective/patient signals · affects statistical significance
			</p>
			<div class="space-y-1">
				{#each factorAvgTradeCount.rows as row, i (i)}
					{@const pct = ((row.avg / factorAvgTradeCount.maxAvg) * 100).toFixed(1)}
					{@const hue = Math.round(200 - (i / factorAvgTradeCount.rows.length) * 120)}
					{@const color = `hsl(${hue},60%,55%)`}
					<div class="flex items-center gap-2 text-[10px]">
						<span class="w-28 truncate font-mono text-[9px]">{row.factor}</span>
						<div class="flex h-3 flex-1 overflow-hidden rounded bg-muted/30">
							<div class="h-full rounded" style="width:{pct}%; background:{color}"></div>
						</div>
						<span class="w-14 text-right font-mono" style="color:{color}">{row.avg.toFixed(0)}</span
						>
						<span class="w-10 text-right text-[9px] text-muted-foreground">n={row.count}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Avg trades proxy for signal frequency · pair with win rate for selectivity · factors with
				&lt;30 avg trades may lack statistical robustness
			</p>
		</section>
	{/if}

	{#if factorProfitSkew}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Factor: Profit Distribution Skew</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Skewness of profit % distribution per factor · positive = right-tailed (rare big wins) ·
				negative = left-tailed (rare big losses) · near zero = symmetric
			</p>
			<div class="space-y-1">
				{#each factorProfitSkew.rows as row, _i (_i)}
					{@const color =
						row.skew > 0.5
							? 'var(--ch-profit)'
							: row.skew < -0.5
								? 'var(--ch-loss)'
								: 'var(--ch-warn)'}
					{@const pct = ((Math.abs(row.skew) / factorProfitSkew.maxAbs) * 50).toFixed(1)}
					<div class="flex items-center gap-2 text-[10px]">
						<span class="w-28 truncate font-mono text-[9px]">{row.factor}</span>
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
				Positive skew = fat right tail (occasional large wins) · negative = fat left tail
				(occasional large losses) · ideal = positive skew + positive mean
			</p>
		</section>
	{/if}

	{#if factorCalmarByTimeframe}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Calmar by Factor &amp; Timeframe
			</h3>
			<div class="mb-2 flex flex-wrap gap-3">
				{#each factorCalmarByTimeframe.TFS as tf, _i (_i)}
					<span class="text-[9px]" style="color:{factorCalmarByTimeframe.TF_COL[tf]}">{tf}</span>
				{/each}
			</div>
			<div class="space-y-1">
				{#each factorCalmarByTimeframe.factors as f, _i (_i)}
					<div class="flex items-center gap-1">
						<span class="w-20 shrink-0 truncate text-[9px] text-muted-foreground">{f.factor}</span>
						<div class="flex flex-1 gap-0.5">
							{#each f.tfVals as tv, _i (_i)}
								{#if tv.avg !== null && tv.count > 0}
									{@const w = factorCalmarByTimeframe.toW(tv.avg)}
									<div
										class="h-3 rounded"
										style="width:{Math.max(
											2,
											(w / (560 - 80 - 10)) * 100
										)}%; background:{factorCalmarByTimeframe.TF_COL[tv.tf] ??
											'var(--ch-axis-muted)'}; opacity:0.85"
										title="{tv.tf}: {tv.avg.toFixed(2)} (n={tv.count})"
									></div>
								{:else}
									<div class="h-3 w-1 rounded bg-muted/20"></div>
								{/if}
							{/each}
						</div>
						<span
							class="w-12 text-right font-mono text-[9px]"
							style="color:{f.overallAvg >= 0
								? 'var(--ch-profit-strong)'
								: 'var(--ch-loss-strong)'}">{f.overallAvg.toFixed(2)}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Calmar = annualised return / max drawdown · each segment = one timeframe · overall avg on
				right · top {factorCalmarByTimeframe.factors.length} factors by Calmar shown
			</p>
		</section>
	{/if}

	{#if factorTopProfitFactorRanking}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit Factor by Factor Tag
			</h3>
			<div class="space-y-1">
				{#each factorTopProfitFactorRanking.rows as row, _i (_i)}
					{@const pct = ((row.avg / factorTopProfitFactorRanking.maxAvg) * 100).toFixed(1)}
					{@const color =
						row.avg >= 2
							? 'var(--ch-profit-strong)'
							: row.avg >= 1.5
								? 'var(--ch-violet)'
								: row.avg >= 1
									? 'var(--ch-warn)'
									: 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-24 shrink-0 truncate text-[9px] text-muted-foreground">{row.factor}</span
						>
						<div class="relative h-3 flex-1 rounded bg-muted/30">
							<div
								class="absolute top-0 left-0 h-full rounded"
								style="width:{pct}%; background:{color}"
							></div>
						</div>
						<span class="w-10 text-right font-mono text-[9px]" style="color:{color}"
							>{row.avg.toFixed(2)}</span
						>
						<span class="w-8 text-right text-[9px] text-muted-foreground">n={row.count}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Avg profit factor across all runs tagged with each factor · PF&gt;2 = excellent · PF&lt;1 =
				net loss · sorted by avg descending
			</p>
		</section>
	{/if}

	{#if factorMonthlyRunCount}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Monthly Run Count — Top 5 Factors
			</h3>
			<div class="mb-2 flex flex-wrap gap-3">
				{#each factorMonthlyRunCount.series as sr, _i (_i)}
					<span class="text-[9px]" style="color:{sr.color}">{sr.factor}</span>
				{/each}
			</div>
			<svg
				viewBox="0 0 {factorMonthlyRunCount.W} {factorMonthlyRunCount.H}"
				class="w-full"
				style="height:100px"
			>
				{#each factorMonthlyRunCount.months as mo, i (i)}
					{@const x =
						factorMonthlyRunCount.PAD +
						i *
							((factorMonthlyRunCount.W - factorMonthlyRunCount.PAD * 2) /
								factorMonthlyRunCount.months.length)}
					{@const totalH =
						(factorMonthlyRunCount.totals[i] / factorMonthlyRunCount.maxTotal) *
						(factorMonthlyRunCount.H - factorMonthlyRunCount.PAD * 2 - 10)}
					{#each factorMonthlyRunCount.series as sr, si (si)}
						{@const segH =
							totalH > 0 ? (sr.counts[i] / factorMonthlyRunCount.totals[i]) * totalH : 0}
						{@const prevH = factorMonthlyRunCount.series
							.slice(0, si)
							.reduce(
								(s, prev) =>
									s +
									(totalH > 0 ? (prev.counts[i] / factorMonthlyRunCount.totals[i]) * totalH : 0),
								0
							)}
						{#if segH > 0}
							<rect
								{x}
								y={factorMonthlyRunCount.H - 10 - prevH - segH}
								width={factorMonthlyRunCount.barW}
								height={segH}
								fill={sr.color}
							/>
						{/if}
					{/each}
					{#if i % 3 === 0}
						<text {x} y={factorMonthlyRunCount.H - 1} font-size="7" fill="var(--ch-axis)"
							>{mo.slice(5)}</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Stacked bars = run count per factor per month · last 12 months · color = factor tag · height
				= total runs
			</p>
		</section>
	{/if}

	{#if factorCalmarVsWinRate}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Factor Win Rate vs Calmar ({factorCalmarVsWinRate.count} factors)
			</h3>
			<svg
				viewBox="0 0 {factorCalmarVsWinRate.W} {factorCalmarVsWinRate.H}"
				class="w-full"
				style="height:100px"
			>
				{#if factorCalmarVsWinRate.zeroY !== null}
					<line
						x1="0"
						y1={factorCalmarVsWinRate.zeroY}
						x2={factorCalmarVsWinRate.W}
						y2={factorCalmarVsWinRate.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="3,3"
					/>
				{/if}
				{#each factorCalmarVsWinRate.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r={d.r} fill={d.color} stroke="none" />
				{/each}
			</svg>
			<div class="mt-1 flex justify-between text-[9px] text-muted-foreground">
				<span>← low win rate</span>
				<span>x=avg win rate % · y=median Calmar · size=run count · green=profitable avg</span>
				<span>high win rate →</span>
			</div>
		</section>
	{/if}

	{#if factorDrawdownRanking}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Factor Avg Drawdown Ranking (lowest first)
			</h3>
			<div class="space-y-1.5">
				{#each factorDrawdownRanking.rows as row, _i (_i)}
					{@const pct = ((row.dd / factorDrawdownRanking.maxDD) * 100).toFixed(1)}
					{@const color =
						row.dd < factorDrawdownRanking.maxDD * 0.33
							? 'var(--ch-profit)'
							: row.dd < factorDrawdownRanking.maxDD * 0.66
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-28 truncate text-right text-[9px] text-muted-foreground"
							>{row.factor}</span
						>
						<div class="h-3 flex-1 overflow-hidden rounded bg-muted/20">
							<div class="h-full rounded" style="width:{pct}%; background:{color}"></div>
						</div>
						<span class="w-12 text-right font-mono text-[10px]" style="color:{color}"
							>{row.dd.toFixed(1)}%</span
						>
						<span class="w-8 text-right text-[9px] text-muted-foreground">n={row.count}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Avg max drawdown per factor · sorted lowest to highest · green = low risk · red = high
				drawdown · lower is safer
			</p>
		</section>
	{/if}

	{#if factorStrategyCountRanking}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Factor Strategy Coverage (unique strategies per factor)
			</h3>
			<div class="space-y-1.5">
				{#each factorStrategyCountRanking.rows as row, _i (_i)}
					{@const pct = ((row.strategies / factorStrategyCountRanking.maxStrats) * 100).toFixed(1)}
					{@const color = row.profit >= 0 ? 'var(--ch-violet)' : 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-28 truncate text-right text-[9px] text-muted-foreground"
							>{row.factor}</span
						>
						<div class="h-3 flex-1 overflow-hidden rounded bg-muted/20">
							<div class="h-full rounded" style="width:{pct}%; background:{color}"></div>
						</div>
						<span class="w-8 text-right font-mono text-[10px] text-muted-foreground"
							>{row.strategies}</span
						>
						<span class="w-16 text-right text-[9px] text-muted-foreground">{row.count} runs</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				How many distinct strategies use each factor · wider bar = more broadly adopted · indigo =
				profitable avg · red = losing avg
			</p>
		</section>
	{/if}

	{#if factorWinRateDistribution}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Factor Win Rate Distribution
			</h3>
			<svg
				viewBox="0 0 {factorWinRateDistribution.W} {factorWinRateDistribution.H}"
				class="w-full"
				style="height:70px"
			>
				{#each factorWinRateDistribution.counts as b, i (i)}
					{@const x = factorWinRateDistribution.PAD + i * (factorWinRateDistribution.barW + 1)}
					{@const barH = Math.max(
						1,
						(b.count / factorWinRateDistribution.maxCount) *
							(factorWinRateDistribution.H - factorWinRateDistribution.PAD * 2 - 8)
					)}
					{@const color =
						b.lo >= 0.55 ? 'var(--ch-profit)' : b.lo >= 0.45 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<rect
						{x}
						y={factorWinRateDistribution.H - 8 - barH}
						width={factorWinRateDistribution.barW}
						height={barH}
						rx="1"
						fill={color}
					/>
					{#if i === 0 || i === factorWinRateDistribution.counts.length - 1}
						<text
							x={x + factorWinRateDistribution.barW / 2}
							y={factorWinRateDistribution.H - 1}
							text-anchor="middle"
							font-size="7"
							fill="var(--ch-axis)">{b.label}</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Distribution of win rates across factors · avg {factorWinRateDistribution.avg}% · green ≥55%
				· yellow 45–55% · red &lt;45%
			</p>
		</section>
	{/if}

	{#if factorProfitVsDrawdownBubble}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Factor Profit vs Drawdown Bubble Chart
			</h3>
			<svg
				viewBox="0 0 {factorProfitVsDrawdownBubble.W} {factorProfitVsDrawdownBubble.H}"
				class="w-full"
				style="height:160px"
			>
				<line
					x1={factorProfitVsDrawdownBubble.xs(0)}
					y1={factorProfitVsDrawdownBubble.PAD}
					x2={factorProfitVsDrawdownBubble.xs(0)}
					y2={factorProfitVsDrawdownBubble.H - factorProfitVsDrawdownBubble.PAD}
					stroke="var(--ch-axis-muted)"
					stroke-width="0.8"
					stroke-dasharray="3,3"
				/>
				{#each factorProfitVsDrawdownBubble.pts as p, _i (_i)}
					<circle
						cx={factorProfitVsDrawdownBubble.xs(p.profit)}
						cy={factorProfitVsDrawdownBubble.ys(p.dd)}
						r={factorProfitVsDrawdownBubble.rs(p.count)}
						fill={factorProfitVsDrawdownBubble.color(p.calmar)}
					/>
					<text
						x={factorProfitVsDrawdownBubble.xs(p.profit)}
						y={factorProfitVsDrawdownBubble.ys(p.dd) - factorProfitVsDrawdownBubble.rs(p.count) - 1}
						text-anchor="middle"
						font-size="6"
						fill="var(--ch-axis-strong)">{p.factor.slice(0, 10)}</text
					>
				{/each}
				<text
					x={factorProfitVsDrawdownBubble.PAD}
					y={factorProfitVsDrawdownBubble.H - 4}
					font-size="7"
					fill="var(--ch-axis)">{factorProfitVsDrawdownBubble.minP.toFixed(1)}%</text
				>
				<text
					x={factorProfitVsDrawdownBubble.W - factorProfitVsDrawdownBubble.PAD}
					y={factorProfitVsDrawdownBubble.H - 4}
					text-anchor="end"
					font-size="7"
					fill="var(--ch-axis)">{factorProfitVsDrawdownBubble.maxP.toFixed(1)}%</text
				>
				<text
					x={factorProfitVsDrawdownBubble.PAD - 2}
					y={factorProfitVsDrawdownBubble.PAD + 4}
					text-anchor="end"
					font-size="7"
					fill="var(--ch-axis)">{factorProfitVsDrawdownBubble.maxDD.toFixed(1)}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				x = avg profit · y = avg drawdown (higher = lower DD) · bubble size = run count · indigo
				≥1.5 Calmar · yellow ≥0.5 · red &lt;0.5
			</p>
		</section>
	{/if}

	{#if factorProfitTierBreakdown}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Factor Profit Tier Breakdown (top 12 factors)
			</h3>
			<div class="space-y-1">
				{#each factorProfitTierBreakdown.rows as row, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-24 truncate text-right text-[9px] text-muted-foreground"
							>{row.factor}</span
						>
						<div class="flex h-3 flex-1 gap-px overflow-hidden rounded">
							{#each row.counts as c, _i (_i)}
								{@const w = ((c.count / Math.max(row.total, 1)) * 100).toFixed(1)}
								{#if c.count > 0}
									<div class="h-full" style="width:{w}%; background:{c.color}; flex-shrink:0"></div>
								{/if}
							{/each}
						</div>
						<span class="w-10 text-right text-[9px] text-muted-foreground">{row.total} runs</span>
					</div>
				{/each}
			</div>
			<div class="mt-2 flex gap-3 text-[9px] text-muted-foreground">
				{#each factorProfitTierBreakdown.tiers as t, _i (_i)}
					<span style="color:{t.color}">■ {t.label}</span>
				{/each}
			</div>
		</section>
	{/if}

	{#if factorMedianCalmarLeaderboard}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Top Factors by Median Calmar Ratio
			</h3>
			<div class="space-y-1.5">
				{#each factorMedianCalmarLeaderboard.rows as row, i (i)}
					{@const pct = ((row.calmar / factorMedianCalmarLeaderboard.maxCalmar) * 100).toFixed(1)}
					{@const color =
						row.calmar >= 1.5
							? 'var(--ch-violet-strong)'
							: row.calmar >= 0.8
								? 'var(--ch-profit)'
								: 'var(--ch-warn)'}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right text-[9px] text-muted-foreground">{i + 1}.</span>
						<span class="w-28 truncate text-[9px] text-muted-foreground">{row.factor}</span>
						<div class="h-3 flex-1 overflow-hidden rounded bg-muted/20">
							<div class="h-full rounded" style="width:{pct}%; background:{color}"></div>
						</div>
						<span class="w-10 text-right font-mono text-[10px]" style="color:{color}"
							>{row.calmar.toFixed(2)}</span
						>
						<span class="w-14 text-right text-[9px] text-muted-foreground"
							>{(row.wr * 100).toFixed(0)}% WR</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Median Calmar per factor · indigo ≥1.5 · green ≥0.8 · yellow &lt;0.8 · median is robust to
				outlier runs · shows typical risk-adjusted quality
			</p>
		</section>
	{/if}

	{#if factorTopSharpeRanking}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Top Factors by Median Sharpe Ratio
			</h3>
			<div class="space-y-1.5">
				{#each factorTopSharpeRanking.rows as row, i (i)}
					{@const pct = ((Math.abs(row.sharpe) / factorTopSharpeRanking.maxAbs) * 100).toFixed(1)}
					{@const color =
						row.sharpe >= 2
							? 'var(--ch-profit-strong)'
							: row.sharpe >= 1
								? 'var(--ch-violet)'
								: row.sharpe >= 0
									? 'var(--ch-warn)'
									: 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right text-[9px] text-muted-foreground">{i + 1}.</span>
						<span class="w-28 truncate text-[9px] text-muted-foreground">{row.factor}</span>
						<div class="h-3 flex-1 overflow-hidden rounded bg-muted/20">
							<div class="h-full rounded" style="width:{pct}%; background:{color}"></div>
						</div>
						<span class="w-10 text-right font-mono text-[10px]" style="color:{color}"
							>{row.sharpe.toFixed(2)}</span
						>
						<span class="w-14 text-right text-[9px] text-muted-foreground">{row.count} runs</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Median Sharpe per factor · green ≥2 · indigo ≥1 · yellow 0–1 · red &lt;0 · Sharpe measures
				return per unit of total volatility
			</p>
		</section>
	{/if}

	{#if factorBestVsWorstRun}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Factor Best vs Worst Run Range
			</h3>
			<div class="space-y-1.5">
				{#each factorBestVsWorstRun.rows as row, i (i)}
					{@const bestPct = ((Math.abs(row.best) / factorBestVsWorstRun.absMax) * 50).toFixed(1)}
					{@const worstPct = ((Math.abs(row.worst) / factorBestVsWorstRun.absMax) * 50).toFixed(1)}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right text-[9px] text-muted-foreground">{i + 1}.</span>
						<span class="w-28 truncate text-[9px] text-muted-foreground">{row.factor}</span>
						<div class="flex h-3 flex-1 overflow-hidden rounded bg-muted/20">
							<div class="h-full" style="width:{worstPct}%; background:var(--ch-loss)"></div>
							<div class="h-full" style="width:{bestPct}%; background:var(--ch-profit)"></div>
						</div>
						<span class="w-12 text-right font-mono text-[9px] text-muted-foreground"
							>{row.worst.toFixed(0)}/+{row.best.toFixed(0)}%</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Red=worst run profit% · green=best run profit% · wide range = high variance factor · sorted
				by best run (top factors had highest upside)
			</p>
		</section>
	{/if}

	{#if factorCalmarEfficiency}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Factor Calmar Efficiency (Calmar ÷ Avg Drawdown)
			</h3>
			<div class="space-y-1.5">
				{#each factorCalmarEfficiency.rows as row, i (i)}
					{@const pct = ((Math.abs(row.efficiency) / factorCalmarEfficiency.maxEff) * 100).toFixed(
						1
					)}
					{@const color =
						row.efficiency >= 0.5
							? 'var(--ch-profit)'
							: row.efficiency >= 0.2
								? 'var(--ch-violet)'
								: row.efficiency >= 0
									? 'var(--ch-warn)'
									: 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right text-[9px] text-muted-foreground">{i + 1}.</span>
						<span class="w-28 truncate text-[9px] text-muted-foreground">{row.factor}</span>
						<div class="h-3 flex-1 overflow-hidden rounded bg-muted/20">
							<div class="h-full rounded" style="width:{pct}%; background:{color}"></div>
						</div>
						<span class="w-12 text-right font-mono text-[10px]" style="color:{color}"
							>{row.efficiency.toFixed(3)}</span
						>
						<span class="w-10 text-right text-[9px] text-muted-foreground">{row.count}r</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Calmar ÷ avg drawdown · higher = factor generates more return per unit of drawdown risk ·
				green ≥0.5 · indigo ≥0.2 · identifies factors with best risk-adjusted alpha
			</p>
		</section>
	{/if}

	{#if factorTimeframeWinRate}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Top Factor × Timeframe Win Rate Heatmap
			</h3>
			<svg
				viewBox="0 0 {factorTimeframeWinRate.W} {factorTimeframeWinRate.H}"
				class="w-full"
				style="height:{factorTimeframeWinRate.H}px"
			>
				{#each factorTimeframeWinRate.usedTfs as tf, ti (ti)}
					<text
						x={factorTimeframeWinRate.PAD +
							ti * (factorTimeframeWinRate.cW + 2) +
							factorTimeframeWinRate.cW / 2}
						y={10}
						text-anchor="middle"
						font-size="6.5"
						fill="var(--ch-axis)">{tf}</text
					>
				{/each}
				{#each factorTimeframeWinRate.topFactors as f, fi (fi)}
					<text
						x={factorTimeframeWinRate.PAD - 2}
						y={factorTimeframeWinRate.PAD +
							fi * (factorTimeframeWinRate.cH + 2) +
							factorTimeframeWinRate.cH -
							2}
						text-anchor="end"
						font-size="6"
						fill="var(--ch-axis)">{f}</text
					>
				{/each}
				{#each factorTimeframeWinRate.cells as c, _i (_i)}
					{@const x = factorTimeframeWinRate.PAD + c.ti * (factorTimeframeWinRate.cW + 2)}
					{@const y = factorTimeframeWinRate.PAD + c.fi * (factorTimeframeWinRate.cH + 2)}
					{@const alpha = c.rate === null ? 0.04 : c.rate >= 60 ? 0.75 : c.rate >= 40 ? 0.4 : 0.15}
					{@const baseColor = c.rate !== null && c.rate >= 50 ? '34,197,94' : '239,68,68'}
					<rect
						{x}
						{y}
						width={factorTimeframeWinRate.cW}
						height={factorTimeframeWinRate.cH}
						rx="2"
						fill={c.rate === null ? 'var(--ch-axis-faint)' : `rgba(${baseColor},${alpha})`}
					/>
					{#if c.rate !== null}
						<text
							x={x + factorTimeframeWinRate.cW / 2}
							y={y + factorTimeframeWinRate.cH - 3}
							text-anchor="middle"
							font-size="7"
							fill="var(--ch-axis-strong)">{c.rate.toFixed(0)}%</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-2 text-[9px] text-muted-foreground">
				% of runs with win rate &gt;50% per factor × timeframe · green=above 50% · red=below · dark
				green=consistently high win rate in that timeframe
			</p>
		</section>
	{/if}
	{#if factorSharpeVsCalmarScatter}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Factor Avg Sharpe vs Calmar ({factorSharpeVsCalmarScatter.count} factors)
			</h3>
			<svg
				viewBox="0 0 {factorSharpeVsCalmarScatter.W} {factorSharpeVsCalmarScatter.H}"
				class="w-full"
				style="height:100px"
			>
				{#each factorSharpeVsCalmarScatter.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="3" fill={d.color} />
					<text x={d.cx + 4} y={d.cy + 3} font-size="6" fill="var(--ch-axis)">{d.label}</text>
				{/each}
				<text
					x={factorSharpeVsCalmarScatter.PAD}
					y={factorSharpeVsCalmarScatter.H - 2}
					font-size="6.5"
					fill="var(--ch-axis-muted)">Sharpe {factorSharpeVsCalmarScatter.sMin}</text
				>
				<text
					x={factorSharpeVsCalmarScatter.W - factorSharpeVsCalmarScatter.PAD}
					y={factorSharpeVsCalmarScatter.H - 2}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-axis-muted)">{factorSharpeVsCalmarScatter.sMax}</text
				>
				<text
					x={factorSharpeVsCalmarScatter.PAD}
					y={factorSharpeVsCalmarScatter.PAD + 4}
					font-size="6"
					fill="var(--ch-axis-muted)">Calmar {factorSharpeVsCalmarScatter.cMax}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				x=avg Sharpe · y=avg Calmar · green=both≥1 · yellow=both≥0 · red=either negative · top-right
				factors excel at both volatility and drawdown adjustment
			</p>
		</section>
	{/if}
	{#if factorTopUsageTrend}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Factor Usage Trend (top {factorTopUsageTrend.polylines.length} by month)
			</h3>
			<svg
				viewBox="0 0 {factorTopUsageTrend.W} {factorTopUsageTrend.H}"
				class="w-full"
				style="height:80px"
			>
				{#each factorTopUsageTrend.polylines as line, _i (_i)}
					<polyline
						points={line.poly}
						fill="none"
						stroke={line.color}
						stroke-width="1.5"
						stroke-linejoin="round"
					/>
				{/each}
				{#each factorTopUsageTrend.months as mo, i (i)}
					{@const x =
						factorTopUsageTrend.PAD +
						(i / Math.max(factorTopUsageTrend.months.length - 1, 1)) *
							(factorTopUsageTrend.W - factorTopUsageTrend.PAD * 2)}
					<text
						{x}
						y={factorTopUsageTrend.H - 1}
						text-anchor="middle"
						font-size="6.5"
						fill="var(--ch-axis-muted)">{mo}</text
					>
				{/each}
			</svg>
			<div class="mt-1 flex flex-wrap gap-2">
				{#each factorTopUsageTrend.polylines as line, _i (_i)}
					<span class="text-[9px]" style="color:{line.color}">■ {line.factor}</span>
				{/each}
				<span class="text-[9px] text-muted-foreground"
					>· run count per month · rising = factor gaining adoption · reveals trend shifts in
					strategy research focus</span
				>
			</div>
		</section>
	{/if}
	{#if factorAvgTradeCountByTF}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Trade Count per Factor × Timeframe
			</h3>
			<div class="space-y-3">
				{#each factorAvgTradeCountByTF.rows as row, _i (_i)}
					<div>
						<p class="mb-0.5 text-[9px] font-medium text-muted-foreground">{row.factor}</p>
						{#each row.tfs as tf, ti (ti)}
							{#if tf.count >= 2}
								{@const barW =
									(tf.avg / factorAvgTradeCountByTF.maxAvg) * factorAvgTradeCountByTF.barMaxW}
								<div class="mb-0.5 flex items-center gap-1.5">
									<span class="w-8 text-right text-[9px] text-muted-foreground">{tf.tf}</span>
									<div
										class="h-2.5 rounded"
										style="width:{barW}px;background:{factorAvgTradeCountByTF.colors[ti]}"
									></div>
									<span class="text-[9px] text-muted-foreground">{tf.avg.toFixed(0)}t</span>
								</div>
							{/if}
						{/each}
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Avg trades per backtest run · grouped by factor and timeframe · reveals which
				factor+timeframe combinations generate more trading signals
			</p>
		</section>
	{/if}
	{#if factorWinRateVsCalmarScatter}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Factor Win Rate vs Avg Calmar
			</h3>
			<svg
				viewBox="0 0 {factorWinRateVsCalmarScatter.W} {factorWinRateVsCalmarScatter.H}"
				class="w-full"
				style="height:90px"
			>
				<line
					x1={factorWinRateVsCalmarScatter.PAD}
					y1={factorWinRateVsCalmarScatter.zeroY}
					x2={factorWinRateVsCalmarScatter.W - factorWinRateVsCalmarScatter.PAD}
					y2={factorWinRateVsCalmarScatter.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each factorWinRateVsCalmarScatter.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r={d.r} fill={d.color} />
					<text
						x={d.cx}
						y={d.cy - d.r - 1}
						text-anchor="middle"
						font-size="5.5"
						fill="var(--ch-axis)">{d.label}</text
					>
				{/each}
				<text
					x={factorWinRateVsCalmarScatter.PAD}
					y={factorWinRateVsCalmarScatter.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">WR {factorWinRateVsCalmarScatter.wrMin}%</text
				>
				<text
					x={factorWinRateVsCalmarScatter.W - factorWinRateVsCalmarScatter.PAD}
					y={factorWinRateVsCalmarScatter.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{factorWinRateVsCalmarScatter.wrMax}%</text
				>
				<text
					x={factorWinRateVsCalmarScatter.PAD}
					y={factorWinRateVsCalmarScatter.PAD + 5}
					font-size="6"
					fill="var(--ch-axis-muted)">Calmar {factorWinRateVsCalmarScatter.cMax}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				x=avg win rate % · y=avg Calmar · bubble size=run count · green≥1 · yellow≥0 · red&lt;0 ·
				top-right = factors with both high win rate and strong drawdown-adjusted returns
			</p>
		</section>
	{/if}
	{#if factorProfitByTimeframeTrend}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit Trend by Timeframe
			</h3>
			<svg
				viewBox="0 0 {factorProfitByTimeframeTrend.W} {factorProfitByTimeframeTrend.H}"
				class="w-full"
				style="height:80px"
			>
				<line
					x1={factorProfitByTimeframeTrend.PAD}
					y1={factorProfitByTimeframeTrend.zeroY}
					x2={factorProfitByTimeframeTrend.W - factorProfitByTimeframeTrend.PAD}
					y2={factorProfitByTimeframeTrend.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each factorProfitByTimeframeTrend.polylines as line, _i (_i)}
					<polyline
						points={line.poly}
						fill="none"
						stroke={line.color}
						stroke-width="1.5"
						stroke-linejoin="round"
					/>
				{/each}
				{#each factorProfitByTimeframeTrend.allMonths as mo, i (i)}
					{#if i % Math.max(1, Math.floor(factorProfitByTimeframeTrend.allMonths.length / 5)) === 0}
						{@const x =
							factorProfitByTimeframeTrend.PAD +
							(i / Math.max(factorProfitByTimeframeTrend.allMonths.length - 1, 1)) *
								(factorProfitByTimeframeTrend.W - factorProfitByTimeframeTrend.PAD * 2)}
						<text
							{x}
							y={factorProfitByTimeframeTrend.H - 1}
							text-anchor="middle"
							font-size="6"
							fill="var(--ch-axis-muted)">{mo.slice(5)}</text
						>
					{/if}
				{/each}
			</svg>
			<div class="mt-1 flex flex-wrap gap-2 text-[9px]">
				{#each factorProfitByTimeframeTrend.polylines as line, _i (_i)}
					<span style="color:{line.color}">■ {line.tf}</span>
				{/each}
				<span class="text-muted-foreground"
					>· monthly avg profit % across all runs for each timeframe</span
				>
			</div>
		</section>
	{/if}

	{#if factorSharpeVsSortinoScatter}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Factor Sharpe vs Sortino ({factorSharpeVsSortinoScatter.count} factors)
			</h3>
			<svg
				viewBox="0 0 {factorSharpeVsSortinoScatter.W} {factorSharpeVsSortinoScatter.H}"
				class="w-full"
				style="height:92px"
			>
				<line
					x1={factorSharpeVsSortinoScatter.zeroX}
					y1={factorSharpeVsSortinoScatter.PAD}
					x2={factorSharpeVsSortinoScatter.zeroX}
					y2={factorSharpeVsSortinoScatter.H - factorSharpeVsSortinoScatter.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				<line
					x1={factorSharpeVsSortinoScatter.PAD}
					y1={factorSharpeVsSortinoScatter.zeroY}
					x2={factorSharpeVsSortinoScatter.W - factorSharpeVsSortinoScatter.PAD}
					y2={factorSharpeVsSortinoScatter.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each factorSharpeVsSortinoScatter.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="3" fill={d.color} />
					<text x={d.cx + 4} y={d.cy + 3} font-size="5.5" fill="var(--ch-axis)">{d.name}</text>
				{/each}
				<text
					x={factorSharpeVsSortinoScatter.PAD}
					y={factorSharpeVsSortinoScatter.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">Sharpe {factorSharpeVsSortinoScatter.sMin}</text
				>
				<text
					x={factorSharpeVsSortinoScatter.W - factorSharpeVsSortinoScatter.PAD}
					y={factorSharpeVsSortinoScatter.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{factorSharpeVsSortinoScatter.sMax}</text
				>
				<text
					x={factorSharpeVsSortinoScatter.PAD}
					y={factorSharpeVsSortinoScatter.PAD + 5}
					font-size="6"
					fill="var(--ch-axis-muted)">Sortino {factorSharpeVsSortinoScatter.soMax}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				x=avg Sharpe · y=avg Sortino · color: green=Calmar&gt;2 · yellow=Calmar&gt;0 · red=Calmar≤0
				· top-right = best risk-adjusted factors on both metrics
			</p>
		</section>
	{/if}

	{#if factorWinRateByMonth}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Win Rate by Month ({factorWinRateByMonth.count} months)
			</h3>
			<svg
				viewBox="0 0 {factorWinRateByMonth.W} {factorWinRateByMonth.H}"
				class="w-full"
				style="height:72px"
			>
				<polygon points={factorWinRateByMonth.area} fill="var(--ch-violet-light)" />
				<polyline
					points={factorWinRateByMonth.poly}
					fill="none"
					stroke="var(--ch-violet-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				{#if factorWinRateByMonth.y50 >= factorWinRateByMonth.PAD && factorWinRateByMonth.y50 <= factorWinRateByMonth.H - factorWinRateByMonth.PAD}
					<line
						x1={factorWinRateByMonth.PAD}
						y1={factorWinRateByMonth.y50}
						x2={factorWinRateByMonth.W - factorWinRateByMonth.PAD}
						y2={factorWinRateByMonth.y50}
						stroke="var(--ch-axis-faint)"
						stroke-width="0.7"
						stroke-dasharray="3,2"
					/>
					<text
						x={factorWinRateByMonth.W - factorWinRateByMonth.PAD + 1}
						y={factorWinRateByMonth.y50 + 3}
						font-size="5.5"
						fill="var(--ch-axis-muted)">50%</text
					>
				{/if}
				{#each factorWinRateByMonth.pts as p, i (i)}
					{#if i % Math.max(1, Math.floor(factorWinRateByMonth.pts.length / 6)) === 0}
						{@const x =
							factorWinRateByMonth.PAD +
							(i / Math.max(factorWinRateByMonth.pts.length - 1, 1)) *
								(factorWinRateByMonth.W - factorWinRateByMonth.PAD * 2)}
						<text
							{x}
							y={factorWinRateByMonth.H - 1}
							text-anchor="middle"
							font-size="5.5"
							fill="var(--ch-axis-muted)">{p.mo.slice(5)}</text
						>
					{/if}
				{/each}
				<text
					x={factorWinRateByMonth.PAD}
					y={factorWinRateByMonth.PAD + 5}
					font-size="6"
					fill="var(--ch-axis-muted)">{factorWinRateByMonth.mx}%</text
				>
				<text
					x={factorWinRateByMonth.PAD}
					y={factorWinRateByMonth.H - factorWinRateByMonth.PAD}
					font-size="6"
					fill="var(--ch-axis-muted)">{factorWinRateByMonth.mn}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Average win rate % across all backtest runs per month · indigo area · dashed line at 50% ·
				rising trend = improving strategy selection over time
			</p>
		</section>
	{/if}

	{#if factorProfitFactorVsWinRateScatter}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Profit Factor vs Win Rate per Factor ({factorProfitFactorVsWinRateScatter.count} factors)
			</h3>
			<svg
				viewBox="0 0 {factorProfitFactorVsWinRateScatter.W} {factorProfitFactorVsWinRateScatter.H}"
				class="w-full"
				style="height:92px"
			>
				<line
					x1={factorProfitFactorVsWinRateScatter.x1Line}
					y1={factorProfitFactorVsWinRateScatter.PAD}
					x2={factorProfitFactorVsWinRateScatter.x1Line}
					y2={factorProfitFactorVsWinRateScatter.H - factorProfitFactorVsWinRateScatter.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				<line
					x1={factorProfitFactorVsWinRateScatter.PAD}
					y1={factorProfitFactorVsWinRateScatter.zeroY}
					x2={factorProfitFactorVsWinRateScatter.W - factorProfitFactorVsWinRateScatter.PAD}
					y2={factorProfitFactorVsWinRateScatter.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each factorProfitFactorVsWinRateScatter.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r={d.r} fill={d.color} />
					<text x={d.cx + d.r + 2} y={d.cy + 3} font-size="5.5" fill="var(--ch-axis)">{d.name}</text
					>
				{/each}
				<text
					x={factorProfitFactorVsWinRateScatter.PAD}
					y={factorProfitFactorVsWinRateScatter.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">WR {factorProfitFactorVsWinRateScatter.wrMin}%</text
				>
				<text
					x={factorProfitFactorVsWinRateScatter.W - factorProfitFactorVsWinRateScatter.PAD}
					y={factorProfitFactorVsWinRateScatter.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{factorProfitFactorVsWinRateScatter.wrMax}%</text
				>
				<text
					x={factorProfitFactorVsWinRateScatter.PAD}
					y={factorProfitFactorVsWinRateScatter.PAD + 5}
					font-size="6"
					fill="var(--ch-axis-muted)">PF {factorProfitFactorVsWinRateScatter.pfMax}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				x=avg win rate % · y=avg profit factor · dot size = usage count · dashed lines at 50% WR and
				PF=1 · top-right = high win rate AND high profit factor
			</p>
		</section>
	{/if}
	{#if factorTopByRunCount}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Top Factors by Run Count
			</h3>
			<svg
				viewBox="0 0 {factorTopByRunCount.W} {factorTopByRunCount.H}"
				class="w-full"
				style="height:{factorTopByRunCount.H}px"
			>
				{#each factorTopByRunCount.rows as row, i (i)}
					{@const y = i * 16 + 2}
					{@const bw = Math.max(
						2,
						(row.count / factorTopByRunCount.maxC) * factorTopByRunCount.barMaxW
					)}
					{@const color =
						row.avgProfit >= 5
							? 'var(--ch-profit)'
							: row.avgProfit >= 0
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					<text x={factorTopByRunCount.PAD} y={y + 10} font-size="7" fill="var(--ch-axis-strong)"
						>{row.name}</text
					>
					<rect
						x={factorTopByRunCount.PAD + 125}
						{y}
						width={bw}
						height="12"
						rx="2"
						fill="var(--ch-violet-light)"
					/>
					<text
						x={factorTopByRunCount.PAD + 125 + bw + 3}
						y={y + 10}
						font-size="7"
						fill="var(--ch-axis-strong)">{row.count}</text
					>
					<text
						x={factorTopByRunCount.W - 2}
						y={y + 10}
						text-anchor="end"
						font-size="6"
						fill={color}>{row.avgProfit >= 0 ? '+' : ''}{row.avgProfit.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Factors ranked by total backtest run count · bar length = usage frequency · right label =
				avg profit · reveals most commonly tested factors
			</p>
		</section>
	{/if}
	{#if factorSharpeHistogram}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Factor Avg Sharpe Distribution
			</h3>
			<svg
				viewBox="0 0 {factorSharpeHistogram.W} {factorSharpeHistogram.H}"
				class="w-full"
				style="height:{factorSharpeHistogram.H}px"
			>
				<line
					x1={factorSharpeHistogram.zeroX}
					y1="0"
					x2={factorSharpeHistogram.zeroX}
					y2={factorSharpeHistogram.H - 16}
					stroke="var(--ch-axis-muted)"
					stroke-width="0.8"
				/>
				{#each factorSharpeHistogram.bars as bar, _i (_i)}
					<rect
						x={bar.x}
						y={factorSharpeHistogram.H - 16 - bar.h}
						width={factorSharpeHistogram.bw}
						height={bar.h}
						rx="1"
						fill={bar.color}
					/>
				{/each}
				<text
					x={factorSharpeHistogram.PAD}
					y={factorSharpeHistogram.H - 3}
					font-size="7"
					fill="var(--ch-axis)">{factorSharpeHistogram.mn}</text
				>
				<text
					x={factorSharpeHistogram.W - factorSharpeHistogram.PAD}
					y={factorSharpeHistogram.H - 3}
					text-anchor="end"
					font-size="7"
					fill="var(--ch-axis)">{factorSharpeHistogram.mx}</text
				>
				<text
					x={factorSharpeHistogram.W / 2}
					y={factorSharpeHistogram.H - 3}
					text-anchor="middle"
					font-size="7"
					fill="var(--ch-axis-muted)">n={factorSharpeHistogram.total} factors</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Distribution of avg Sharpe ratio across all factors · green≥1 · yellow≥0 · red&lt;0 · zero
				line at center · reveals overall risk-adjusted quality of factor universe
			</p>
		</section>
	{/if}
	{#if factorAvgProfitRanking}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Top Factors by Avg Profit %
			</h3>
			<svg
				viewBox="0 0 {factorAvgProfitRanking.W} {factorAvgProfitRanking.H}"
				class="w-full"
				style="height:{factorAvgProfitRanking.H}px"
			>
				<line
					x1={factorAvgProfitRanking.zeroX}
					y1="0"
					x2={factorAvgProfitRanking.zeroX}
					y2={factorAvgProfitRanking.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each factorAvgProfitRanking.rows as row, i (i)}
					{@const y = i * 16 + 2}
					{@const bw = Math.max(
						2,
						(Math.abs(row.avg) / factorAvgProfitRanking.maxAbs) *
							(factorAvgProfitRanking.barMaxW / 2)
					)}
					{@const x =
						row.avg >= 0 ? factorAvgProfitRanking.zeroX : factorAvgProfitRanking.zeroX - bw}
					{@const color =
						row.avg >= 5 ? 'var(--ch-profit)' : row.avg >= 0 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<text x={factorAvgProfitRanking.PAD} y={y + 10} font-size="7" fill="var(--ch-axis-strong)"
						>{row.name}</text
					>
					<rect {x} {y} width={bw} height="12" rx="2" fill={color} />
					<text
						x={row.avg >= 0
							? factorAvgProfitRanking.zeroX + bw + 3
							: factorAvgProfitRanking.zeroX - bw - 3}
						y={y + 10}
						text-anchor={row.avg >= 0 ? 'start' : 'end'}
						font-size="7"
						fill={color}>{row.avg >= 0 ? '+' : ''}{row.avg.toFixed(1)}%</text
					>
					<text
						x={factorAvgProfitRanking.W - 2}
						y={y + 10}
						text-anchor="end"
						font-size="6"
						fill="var(--ch-axis-muted)">{row.count}r</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Factors ranked by avg backtest profit % (min 3 runs) · diverging from zero · green≥5% ·
				yellow≥0% · count=runs · reveals which factors most reliably drive profitable strategies
			</p>
		</section>
	{/if}
	{#if factorCalmarWinRateScatter2}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Calmar Ratio vs Win Rate by Factor
			</h3>
			<svg
				viewBox="0 0 {factorCalmarWinRateScatter2.W} {factorCalmarWinRateScatter2.H}"
				class="w-full"
				style="height:{factorCalmarWinRateScatter2.H}px"
			>
				<line
					x1={factorCalmarWinRateScatter2.zeroX}
					y1={factorCalmarWinRateScatter2.PAD}
					x2={factorCalmarWinRateScatter2.zeroX}
					y2={factorCalmarWinRateScatter2.H - factorCalmarWinRateScatter2.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.8"
					stroke-dasharray="3,2"
				/>
				{#each factorCalmarWinRateScatter2.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="2.2" fill={d.color} />
				{/each}
				<text
					x={factorCalmarWinRateScatter2.PAD}
					y={factorCalmarWinRateScatter2.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">Calmar {factorCalmarWinRateScatter2.minC}</text
				>
				<text
					x={factorCalmarWinRateScatter2.W - factorCalmarWinRateScatter2.PAD}
					y={factorCalmarWinRateScatter2.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{factorCalmarWinRateScatter2.maxC}</text
				>
				<text
					x={factorCalmarWinRateScatter2.PAD}
					y={factorCalmarWinRateScatter2.PAD + 5}
					font-size="6"
					fill="var(--ch-axis-muted)">WR {factorCalmarWinRateScatter2.maxW}%</text
				>
				<text
					x={factorCalmarWinRateScatter2.PAD}
					y={factorCalmarWinRateScatter2.H - factorCalmarWinRateScatter2.PAD + 3}
					font-size="6"
					fill="var(--ch-axis-muted)">{factorCalmarWinRateScatter2.minW}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				x=avg Calmar ratio · y=avg win rate % · green=Calmar≥1+WR≥55% · yellow=Calmar≥0 ·
				red=negative Calmar · ideal = top-right (high Calmar + high win rate)
			</p>
		</section>
	{/if}
	{#if factorMonthlyUsageTrend}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Top Factor Monthly Usage Trend
			</h3>
			<svg
				viewBox="0 0 {factorMonthlyUsageTrend.W} {factorMonthlyUsageTrend.H}"
				class="w-full"
				style="height:{factorMonthlyUsageTrend.H}px"
			>
				{#each factorMonthlyUsageTrend.lines as line, li (li)}
					<polyline
						points={line.points}
						fill="none"
						stroke={line.color}
						stroke-width="1.5"
						stroke-linejoin="round"
					/>
					<text
						x={factorMonthlyUsageTrend.W - factorMonthlyUsageTrend.PAD + 2}
						y={factorMonthlyUsageTrend.PAD + li * 10 + 6}
						font-size="6"
						fill={line.color}>{line.name}</text
					>
				{/each}
				{#each factorMonthlyUsageTrend.allMonths as mo, i (i)}
					{#if i % 2 === 0}
						<text
							x={factorMonthlyUsageTrend.toX(i)}
							y={factorMonthlyUsageTrend.H - 2}
							text-anchor="middle"
							font-size="6"
							fill="var(--ch-axis-muted)">{mo}</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Monthly backtest run count for top 3 most-used factors · each line = one factor · reveals
				which factors researchers are currently focusing on and how usage shifts over time
			</p>
		</section>
	{/if}
	{#if factorProfitFactorVsWinRate}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Profit Factor vs Win Rate (per Factor)
			</h3>
			<svg
				viewBox="0 0 {factorProfitFactorVsWinRate.W} {factorProfitFactorVsWinRate.H}"
				class="w-full"
				style="height:{factorProfitFactorVsWinRate.H}px"
			>
				<line
					x1={factorProfitFactorVsWinRate.PAD}
					y1={factorProfitFactorVsWinRate.H - factorProfitFactorVsWinRate.PAD}
					x2={factorProfitFactorVsWinRate.W - factorProfitFactorVsWinRate.PAD}
					y2={factorProfitFactorVsWinRate.H - factorProfitFactorVsWinRate.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				<line
					x1={factorProfitFactorVsWinRate.PAD}
					y1={factorProfitFactorVsWinRate.PAD}
					x2={factorProfitFactorVsWinRate.PAD}
					y2={factorProfitFactorVsWinRate.H - factorProfitFactorVsWinRate.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each factorProfitFactorVsWinRate.pts as p, _i (_i)}
					{@const cx = factorProfitFactorVsWinRate.toX(p.wr)}
					{@const cy = factorProfitFactorVsWinRate.toY(p.pf)}
					{@const col = p.pf >= 1 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					<circle {cx} {cy} r="2.5" fill={col} />
				{/each}
				<text
					x={factorProfitFactorVsWinRate.PAD}
					y={factorProfitFactorVsWinRate.PAD + 6}
					font-size="6"
					fill="var(--ch-axis-muted)">pf {factorProfitFactorVsWinRate.pfMax}</text
				>
				<text
					x={factorProfitFactorVsWinRate.W - factorProfitFactorVsWinRate.PAD}
					y={factorProfitFactorVsWinRate.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">wr 100%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Scatter of avg win rate % (X) vs avg profit factor (Y) per factor · green=pf≥1 · red=pf&lt;1
				· upper-right corner is ideal; reveals factor quality distribution
			</p>
		</section>
	{/if}
	{#if factorTopBySharpe}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Top Factors by Avg Sharpe
			</h3>
			<svg
				viewBox="0 0 {factorTopBySharpe.W} {factorTopBySharpe.H}"
				class="w-full"
				style="height:{factorTopBySharpe.H}px"
			>
				<line
					x1={factorTopBySharpe.zeroX}
					y1="0"
					x2={factorTopBySharpe.zeroX}
					y2={factorTopBySharpe.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each factorTopBySharpe.rows as row, i (i)}
					{@const y = factorTopBySharpe.PAD + i * 16}
					{@const bw = Math.max(
						2,
						(Math.abs(row.sharpe) / factorTopBySharpe.maxAbs) * (factorTopBySharpe.barMaxW / 2)
					)}
					{@const x = row.sharpe >= 0 ? factorTopBySharpe.zeroX : factorTopBySharpe.zeroX - bw}
					{@const color =
						row.sharpe >= 1
							? 'var(--ch-profit)'
							: row.sharpe >= 0
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					<text x={factorTopBySharpe.PAD} y={y + 10} font-size="6.5" fill="var(--ch-axis-strong)"
						>{row.name}</text
					>
					<rect {x} {y} width={bw} height="12" rx="1" fill={color} />
					<text
						x={row.sharpe >= 0
							? factorTopBySharpe.zeroX + bw + 2
							: factorTopBySharpe.zeroX - bw - 2}
						y={y + 10}
						text-anchor={row.sharpe >= 0 ? 'start' : 'end'}
						font-size="6.5"
						fill={color}>{row.sharpe.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Factors ranked by avg Sharpe ratio · green≥1 · yellow≥0 · red&lt;0 · diverging from zero ·
				reveals which factors most reliably improve risk-adjusted returns
			</p>
		</section>
	{/if}
	{#if factorAvgDrawdownRanking}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Factors by Lowest Avg Drawdown
			</h3>
			<svg
				viewBox="0 0 {factorAvgDrawdownRanking.W} {factorAvgDrawdownRanking.H}"
				class="w-full"
				style="height:{factorAvgDrawdownRanking.H}px"
			>
				{#each factorAvgDrawdownRanking.rows as row, i (i)}
					{@const y = factorAvgDrawdownRanking.PAD + i * 16}
					{@const bw = Math.max(
						2,
						(row.dd / factorAvgDrawdownRanking.maxDD) * factorAvgDrawdownRanking.barMaxW
					)}
					{@const color =
						row.dd < 10 ? 'var(--ch-profit)' : row.dd < 20 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<text
						x={factorAvgDrawdownRanking.PAD}
						y={y + 11}
						font-size="6.5"
						fill="var(--ch-axis-strong)">{row.name}</text
					>
					<rect
						x={factorAvgDrawdownRanking.PAD + 100}
						{y}
						width={bw}
						height="12"
						rx="1"
						fill={color}
					/>
					<text
						x={factorAvgDrawdownRanking.PAD + 100 + bw + 3}
						y={y + 11}
						font-size="6.5"
						fill={color}>{row.dd.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Factors ranked by lowest avg max drawdown % · green&lt;10% · yellow&lt;20% · red≥20% · lower
				drawdown factors are safer to combine into a strategy
			</p>
		</section>
	{/if}
	{#if factorMonthlyTotalRuns}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Factor Discovery Timeline (Total Runs)
			</h3>
			<svg
				viewBox="0 0 {factorMonthlyTotalRuns.W} {factorMonthlyTotalRuns.H}"
				class="w-full"
				style="height:{factorMonthlyTotalRuns.H}px"
			>
				<polygon points={factorMonthlyTotalRuns.area} fill="rgba(20,184,166,0.1)" />
				<polyline
					points={factorMonthlyTotalRuns.polyline}
					fill="none"
					stroke="var(--ch-teal)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={factorMonthlyTotalRuns.PAD}
					y={factorMonthlyTotalRuns.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{factorMonthlyTotalRuns.firstMo}</text
				>
				<text
					x={factorMonthlyTotalRuns.W - factorMonthlyTotalRuns.PAD}
					y={factorMonthlyTotalRuns.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{factorMonthlyTotalRuns.lastMo}</text
				>
				<text
					x={factorMonthlyTotalRuns.PAD}
					y={factorMonthlyTotalRuns.PAD + 6}
					font-size="7"
					fill="var(--ch-teal-strong)">{factorMonthlyTotalRuns.maxV}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Total backtest runs per month grouped by factor first-seen date · teal area · reveals when
				factors were discovered and how heavily each cohort was tested
			</p>
		</section>
	{/if}
	{#if factorSharpeByRunCount}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Factor Run Count vs Avg Sharpe Scatter
			</h3>
			<svg
				viewBox="0 0 {factorSharpeByRunCount.W} {factorSharpeByRunCount.H}"
				class="w-full"
				style="height:{factorSharpeByRunCount.H}px"
			>
				<line
					x1={factorSharpeByRunCount.PAD}
					y1={factorSharpeByRunCount.zeroY}
					x2={factorSharpeByRunCount.W - factorSharpeByRunCount.PAD}
					y2={factorSharpeByRunCount.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each factorSharpeByRunCount.pts as p, _i (_i)}
					{@const cx = factorSharpeByRunCount.toX(p.rc)}
					{@const cy = factorSharpeByRunCount.toY(p.sh)}
					{@const col =
						p.sh >= 1
							? 'var(--ch-profit)'
							: p.sh >= 0
								? 'var(--ch-warn-light)'
								: 'var(--ch-loss-light)'}
					<circle {cx} {cy} r="3" fill={col} />
				{/each}
				<text
					x={factorSharpeByRunCount.PAD}
					y={factorSharpeByRunCount.PAD + 7}
					font-size="6"
					fill="var(--ch-axis-muted)">sh {factorSharpeByRunCount.shMax}</text
				>
				<text
					x={factorSharpeByRunCount.W - factorSharpeByRunCount.PAD}
					y={factorSharpeByRunCount.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{factorSharpeByRunCount.rcMax} runs</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Scatter of factor run count (X) vs avg Sharpe ratio (Y) · green≥1 · yellow≥0 · red&lt;0 ·
				more-tested factors in upper-right indicate robust high-quality signals
			</p>
		</section>
	{/if}
	{#if factorProfitByRunCountBucket}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit% by Factor Run Count Bucket
			</h3>
			<svg
				viewBox="0 0 {factorProfitByRunCountBucket.W} {factorProfitByRunCountBucket.H}"
				class="w-full"
				style="height:{factorProfitByRunCountBucket.H}px"
			>
				<line
					x1={factorProfitByRunCountBucket.PAD}
					y1={factorProfitByRunCountBucket.midY}
					x2={factorProfitByRunCountBucket.W - factorProfitByRunCountBucket.PAD}
					y2={factorProfitByRunCountBucket.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each factorProfitByRunCountBucket.rows as row, i (i)}
					{@const x = factorProfitByRunCountBucket.PAD + i * (factorProfitByRunCountBucket.bw + 2)}
					{@const bh = Math.max(
						2,
						(Math.abs(row.avg) / factorProfitByRunCountBucket.maxAbs) *
							(factorProfitByRunCountBucket.midY - factorProfitByRunCountBucket.PAD)
					)}
					{@const y =
						row.avg >= 0
							? factorProfitByRunCountBucket.midY - bh
							: factorProfitByRunCountBucket.midY}
					{@const color = row.avg >= 0 ? 'var(--ch-violet)' : 'var(--ch-loss)'}
					<rect {x} {y} width={factorProfitByRunCountBucket.bw} height={bh} fill={color} />
					<text
						x={x + factorProfitByRunCountBucket.bw / 2}
						y={factorProfitByRunCountBucket.H - 2}
						text-anchor="middle"
						font-size="6"
						fill="var(--ch-axis-muted)">{row.b}</text
					>
					<text
						x={x + factorProfitByRunCountBucket.bw / 2}
						y={row.avg >= 0
							? factorProfitByRunCountBucket.midY - bh - 2
							: factorProfitByRunCountBucket.midY + bh + 9}
						text-anchor="middle"
						font-size="5.5"
						fill={color}>{row.avg.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg profit% grouped by factor run count bucket · indigo=positive · red=negative · reveals if
				frequently-tested factors produce better returns than rarely-tested ones
			</p>
		</section>
	{/if}
	{#if factorCalmarByTF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Calmar Ratio by Timeframe
			</h3>
			<svg
				viewBox="0 0 {factorCalmarByTF.W} {factorCalmarByTF.H}"
				class="w-full"
				style="height:{factorCalmarByTF.H}px"
			>
				<line
					x1={factorCalmarByTF.zeroX}
					y1="0"
					x2={factorCalmarByTF.zeroX}
					y2={factorCalmarByTF.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each factorCalmarByTF.rows as row, i (i)}
					{@const y = factorCalmarByTF.PAD + i * 20}
					{@const bw = Math.max(
						2,
						(Math.abs(row.avg) / factorCalmarByTF.maxAbs) * (factorCalmarByTF.barMaxW / 2)
					)}
					{@const x = row.avg >= 0 ? factorCalmarByTF.zeroX : factorCalmarByTF.zeroX - bw}
					{@const color =
						row.avg >= 1 ? 'var(--ch-teal)' : row.avg >= 0 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<rect {x} {y} width={bw} height="14" rx="2" fill={color} />
					<text x={factorCalmarByTF.PAD} y={y + 11} font-size="7" fill="var(--ch-axis-strong)"
						>{row.tf}</text
					>
					<text
						x={row.avg >= 0 ? factorCalmarByTF.zeroX + bw + 2 : factorCalmarByTF.zeroX - bw - 2}
						y={y + 11}
						text-anchor={row.avg >= 0 ? 'start' : 'end'}
						font-size="7"
						fill={color}>{row.avg.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg Calmar ratio per timeframe across all factors · teal≥1 · yellow≥0 · red&lt;0 · Calmar =
				return / max drawdown · reveals which timeframes produce best risk-adjusted factor
				performance
			</p>
		</section>
	{/if}
	{#if factorTopSharpeTimeline}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Top Factors by Avg Sharpe
			</h3>
			<svg
				viewBox="0 0 {factorTopSharpeTimeline.W} {factorTopSharpeTimeline.H}"
				class="w-full"
				style="height:{factorTopSharpeTimeline.H}px"
			>
				{#each factorTopSharpeTimeline.sorted as f, i (i)}
					{@const y = factorTopSharpeTimeline.PAD + i * 20}
					{@const bw = Math.max(
						2,
						((f.avg_sharpe as number) / factorTopSharpeTimeline.maxSh) *
							factorTopSharpeTimeline.barMaxW
					)}
					{@const intensity = (f.avg_sharpe as number) / factorTopSharpeTimeline.maxSh}
					<rect
						x={factorTopSharpeTimeline.PAD + 108}
						{y}
						width={bw}
						height="14"
						rx="2"
						fill={`rgba(99,102,241,${(intensity * 0.55 + 0.2).toFixed(2)})`}
					/>
					<text
						x={factorTopSharpeTimeline.PAD}
						y={y + 11}
						font-size="6.5"
						fill="var(--ch-axis-strong)">{((f.factor as string) ?? '').slice(0, 16)}</text
					>
					<text
						x={factorTopSharpeTimeline.PAD + 108 + bw + 3}
						y={y + 11}
						font-size="6.5"
						fill="var(--ch-violet-strong)">{(f.avg_sharpe as number).toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Top 8 factors ranked by avg Sharpe ratio · indigo intensity scales with relative Sharpe ·
				identifies the highest risk-adjusted signal factors in the dataset
			</p>
		</section>
	{/if}
	{#if factorDrawdownVsSharpeScatter}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Drawdown vs Avg Sharpe (Factor Scatter)
			</h3>
			<svg
				viewBox="0 0 {factorDrawdownVsSharpeScatter.W} {factorDrawdownVsSharpeScatter.H}"
				class="w-full"
				style="height:{factorDrawdownVsSharpeScatter.H}px"
			>
				<line
					x1={factorDrawdownVsSharpeScatter.zeroX}
					y1={factorDrawdownVsSharpeScatter.PAD}
					x2={factorDrawdownVsSharpeScatter.zeroX}
					y2={factorDrawdownVsSharpeScatter.H - factorDrawdownVsSharpeScatter.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each factorDrawdownVsSharpeScatter.pts as p, _i (_i)}
					{@const cx = factorDrawdownVsSharpeScatter.toX(p.sharpe)}
					{@const cy = factorDrawdownVsSharpeScatter.toY(p.dd)}
					{@const color =
						p.sharpe > 1
							? 'var(--ch-profit)'
							: p.sharpe > 0
								? 'var(--ch-violet)'
								: 'var(--ch-loss-light)'}
					<circle {cx} {cy} r="3" fill={color} />
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Scatter of avg Sharpe (X) vs avg max drawdown% (Y) per factor · green=Sharpe>1 ·
				indigo=Sharpe>0 · red=negative · lower-right = high Sharpe with low drawdown = ideal factors
			</p>
		</section>
	{/if}
	{#if factorRunsByTFBars}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Total Runs by Timeframe (Factors)
			</h3>
			<svg
				viewBox="0 0 {factorRunsByTFBars.W} {factorRunsByTFBars.H}"
				class="w-full"
				style="height:{factorRunsByTFBars.H}px"
			>
				{#each factorRunsByTFBars.rows as row, i (i)}
					{@const y = factorRunsByTFBars.PAD + i * 20}
					{@const bw = Math.max(
						2,
						(row.count / factorRunsByTFBars.maxCount) * factorRunsByTFBars.barMaxW
					)}
					<text x={factorRunsByTFBars.PAD} y={y + 13} font-size="7.5" fill="var(--ch-axis-strong)"
						>{row.tf}</text
					>
					<rect
						x={factorRunsByTFBars.PAD + 38}
						{y}
						width={bw}
						height="14"
						rx="2"
						fill="var(--ch-teal)"
					/>
					<text
						x={factorRunsByTFBars.PAD + 38 + bw + 3}
						y={y + 13}
						font-size="6.5"
						fill="var(--ch-teal-strong)">{row.count}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Total number of backtest runs grouped by timeframe across all factors · teal bars · reveals
				which timeframes are most tested and may be over-represented in factor analysis
			</p>
		</section>
	{/if}
	{#if factorProfitCDF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit% CDF (Factors)
			</h3>
			<svg
				viewBox="0 0 {factorProfitCDF.W} {factorProfitCDF.H}"
				class="w-full"
				style="height:{factorProfitCDF.H}px"
			>
				<line
					x1={factorProfitCDF.zeroX}
					y1={factorProfitCDF.PAD}
					x2={factorProfitCDF.zeroX}
					y2={factorProfitCDF.H - factorProfitCDF.PAD}
					stroke="var(--ch-axis-muted)"
					stroke-width="1"
					stroke-dasharray="3,2"
				/>
				<polyline
					points={factorProfitCDF.polyline}
					fill="none"
					stroke="var(--ch-violet-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={factorProfitCDF.PAD}
					y={factorProfitCDF.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{factorProfitCDF.minV}%</text
				>
				<text
					x={factorProfitCDF.W - factorProfitCDF.PAD}
					y={factorProfitCDF.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{factorProfitCDF.maxV}%</text
				>
				<text
					x={factorProfitCDF.W / 2}
					y={factorProfitCDF.PAD + 8}
					text-anchor="middle"
					font-size="7"
					fill="var(--ch-violet-strong)">median {factorProfitCDF.median}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Cumulative distribution of avg profit% across all factors · indigo S-curve · right of zero =
				majority positive · dashed zero line · reveals distribution of factor effectiveness
			</p>
		</section>
	{/if}
	{#if factorSortinoCDF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Sortino CDF (Factors)
			</h3>
			<svg
				viewBox="0 0 {factorSortinoCDF.W} {factorSortinoCDF.H}"
				class="w-full"
				style="height:{factorSortinoCDF.H}px"
			>
				<line
					x1={factorSortinoCDF.zeroX}
					y1={factorSortinoCDF.PAD}
					x2={factorSortinoCDF.zeroX}
					y2={factorSortinoCDF.H - factorSortinoCDF.PAD}
					stroke="var(--ch-axis-muted)"
					stroke-width="1"
					stroke-dasharray="3,2"
				/>
				<polyline
					points={factorSortinoCDF.polyline}
					fill="none"
					stroke="var(--ch-teal-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={factorSortinoCDF.PAD}
					y={factorSortinoCDF.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{factorSortinoCDF.minV}</text
				>
				<text
					x={factorSortinoCDF.W - factorSortinoCDF.PAD}
					y={factorSortinoCDF.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{factorSortinoCDF.maxV}</text
				>
				<text
					x={factorSortinoCDF.W / 2}
					y={factorSortinoCDF.PAD + 8}
					text-anchor="middle"
					font-size="7"
					fill="var(--ch-teal-strong)"
					>median {factorSortinoCDF.median} · p80 {factorSortinoCDF.p80}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Cumulative distribution of avg Sortino ratio per factor · teal S-curve · dashed zero ·
				right-skewed = most factors deliver positive risk-adjusted returns · p80 shows quality
				threshold
			</p>
		</section>
	{/if}
	{#if factorWinRateRanking}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Top Factors by Avg Win Rate
			</h3>
			<svg
				viewBox="0 0 {factorWinRateRanking.W} {factorWinRateRanking.H}"
				class="w-full"
				style="height:{factorWinRateRanking.H}px"
			>
				{#each factorWinRateRanking.rows as row, i (i)}
					{@const y = factorWinRateRanking.PAD + i * 18}
					{@const bw = Math.max(
						2,
						(row.wr / factorWinRateRanking.maxWR) * factorWinRateRanking.barMaxW
					)}
					{@const color =
						row.wr >= 60 ? 'var(--ch-profit)' : row.wr >= 50 ? 'var(--ch-teal)' : 'var(--ch-warn)'}
					<text x={factorWinRateRanking.PAD} y={y + 12} font-size="7" fill="var(--ch-axis-strong)"
						>{row.name}</text
					>
					<rect
						x={factorWinRateRanking.PAD + 90}
						{y}
						width={bw}
						height="13"
						rx="2"
						style="fill:{color}"
					/>
					<text x={factorWinRateRanking.PAD + 90 + bw + 3} y={y + 12} font-size="6.5" fill={color}
						>{row.wr.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Top 10 factors by avg win rate · green≥60% · teal 50-60% · yellow&lt;50% · high win rate
				factors generate more consistent entries regardless of profit size
			</p>
		</section>
	{/if}
	{#if factorCalmarCDF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Calmar CDF (Factors)
			</h3>
			<svg
				viewBox="0 0 {factorCalmarCDF.W} {factorCalmarCDF.H}"
				class="w-full"
				style="height:{factorCalmarCDF.H}px"
			>
				<line
					x1={factorCalmarCDF.zeroX}
					y1={factorCalmarCDF.PAD}
					x2={factorCalmarCDF.zeroX}
					y2={factorCalmarCDF.H - factorCalmarCDF.PAD}
					stroke="var(--ch-axis-muted)"
					stroke-width="0.8"
					stroke-dasharray="3,2"
				/>
				<polyline
					points={factorCalmarCDF.polyline}
					fill="none"
					stroke="var(--ch-warn)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={factorCalmarCDF.PAD}
					y={factorCalmarCDF.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{factorCalmarCDF.minV}</text
				>
				<text
					x={factorCalmarCDF.W - factorCalmarCDF.PAD}
					y={factorCalmarCDF.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{factorCalmarCDF.maxV}</text
				>
				<text
					x={factorCalmarCDF.W / 2}
					y={factorCalmarCDF.PAD + 8}
					text-anchor="middle"
					font-size="7"
					fill="var(--ch-warn)">median {factorCalmarCDF.median}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				CDF of avg Calmar ratio per factor · orange S-curve · dashed zero line · right-skewed = most
				factors produce return/drawdown ratio above zero · identifies robust factor tiers
			</p>
		</section>
	{/if}
	{#if factorAvgProfitByRunBucket}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit% by Factor Run Count Bucket
			</h3>
			<svg
				viewBox="0 0 {factorAvgProfitByRunBucket.W} {factorAvgProfitByRunBucket.H}"
				class="w-full"
				style="height:{factorAvgProfitByRunBucket.H}px"
			>
				<line
					x1={factorAvgProfitByRunBucket.zeroX}
					y1="0"
					x2={factorAvgProfitByRunBucket.zeroX}
					y2={factorAvgProfitByRunBucket.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="1"
				/>
				{#each factorAvgProfitByRunBucket.rows as row, i (i)}
					{@const y = factorAvgProfitByRunBucket.PAD + i * 22}
					{@const bw = Math.max(
						2,
						(Math.abs(row.avg) / factorAvgProfitByRunBucket.maxAbs) *
							(factorAvgProfitByRunBucket.barMaxW / 2)
					)}
					{@const x =
						row.avg >= 0 ? factorAvgProfitByRunBucket.zeroX : factorAvgProfitByRunBucket.zeroX - bw}
					{@const color = row.avg >= 0 ? 'var(--ch-violet)' : 'var(--ch-loss)'}
					<text
						x={factorAvgProfitByRunBucket.PAD}
						y={y + 14}
						font-size="8"
						fill="var(--ch-axis-strong)">{row.k} runs</text
					>
					<rect {x} {y} width={bw} height="15" rx="2" fill={color} />
					<text
						x={row.avg >= 0
							? factorAvgProfitByRunBucket.zeroX + bw + 2
							: factorAvgProfitByRunBucket.zeroX - bw - 2}
						y={y + 12}
						text-anchor={row.avg >= 0 ? 'start' : 'end'}
						font-size="6.5"
						fill={color}>{row.avg.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg profit% grouped by how many runs each factor has · indigo=positive · red=negative ·
				well-tested factors (30+) show more reliable avg profit estimates
			</p>
		</section>
	{/if}
	{#if factorSortinoVsWinRateScatter}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Sortino vs Win Rate Scatter (Factors)
			</h3>
			<svg
				viewBox="0 0 {factorSortinoVsWinRateScatter.W} {factorSortinoVsWinRateScatter.H}"
				class="w-full"
				style="height:{factorSortinoVsWinRateScatter.H}px"
			>
				<line
					x1={factorSortinoVsWinRateScatter.zeroX}
					y1={factorSortinoVsWinRateScatter.PAD}
					x2={factorSortinoVsWinRateScatter.zeroX}
					y2={factorSortinoVsWinRateScatter.H - factorSortinoVsWinRateScatter.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each factorSortinoVsWinRateScatter.pts as p, _i (_i)}
					{@const cx = factorSortinoVsWinRateScatter.toX(p.sortino)}
					{@const cy = factorSortinoVsWinRateScatter.toY(p.wr)}
					{@const color =
						p.sortino > 0 && p.wr >= 50
							? 'var(--ch-teal)'
							: p.sortino > 0
								? 'var(--ch-warn-light)'
								: 'var(--ch-loss-light)'}
					<circle {cx} {cy} r="2.5" fill={color} />
				{/each}
				<text
					x={factorSortinoVsWinRateScatter.PAD}
					y={factorSortinoVsWinRateScatter.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{factorSortinoVsWinRateScatter.minS}</text
				>
				<text
					x={factorSortinoVsWinRateScatter.W - factorSortinoVsWinRateScatter.PAD}
					y={factorSortinoVsWinRateScatter.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{factorSortinoVsWinRateScatter.maxS}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Scatter of avg Sortino (X) vs avg win rate% (Y) per factor · teal=positive Sortino+≥50%WR ·
				yellow=positive Sortino only · red=negative Sortino · top-right = ideal factors
			</p>
		</section>
	{/if}
	{#if factorProfitByTF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit% by Timeframe (Factor Runs)
			</h3>
			<svg
				viewBox="0 0 {factorProfitByTF.W} {factorProfitByTF.H}"
				class="w-full"
				style="height:{factorProfitByTF.H}px"
			>
				<line
					x1={factorProfitByTF.zeroX}
					y1="0"
					x2={factorProfitByTF.zeroX}
					y2={factorProfitByTF.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.8"
				/>
				{#each factorProfitByTF.rows as row, i (i)}
					{@const y = factorProfitByTF.PAD + i * 22}
					{@const bw = Math.max(
						2,
						(Math.abs(row.avg) / factorProfitByTF.maxAbs) * (factorProfitByTF.barMaxW / 2)
					)}
					{@const x = row.avg >= 0 ? factorProfitByTF.zeroX : factorProfitByTF.zeroX - bw}
					{@const color = row.avg >= 0 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
					<text x={factorProfitByTF.PAD} y={y + 14} font-size="8" fill="var(--ch-axis-strong)"
						>{row.tf}</text
					>
					<rect {x} {y} width={bw} height="15" rx="2" fill={color} />
					<text
						x={row.avg >= 0 ? factorProfitByTF.zeroX + bw + 2 : factorProfitByTF.zeroX - bw - 2}
						y={y + 12}
						text-anchor={row.avg >= 0 ? 'start' : 'end'}
						font-size="6.5"
						fill={color}>{row.avg.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg total profit% by timeframe across factor runs · teal=positive · red=negative · reveals
				which timeframes are most profitable for factor-based strategies
			</p>
		</section>
	{/if}
	{#if factorTopCalmarByRunCount}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Top Factors by Avg Calmar
			</h3>
			<svg
				viewBox="0 0 {factorTopCalmarByRunCount.W} {factorTopCalmarByRunCount.H}"
				class="w-full"
				style="height:{factorTopCalmarByRunCount.H}px"
			>
				<line
					x1={factorTopCalmarByRunCount.zeroX}
					y1="0"
					x2={factorTopCalmarByRunCount.zeroX}
					y2={factorTopCalmarByRunCount.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.8"
				/>
				{#each factorTopCalmarByRunCount.rows as row, i (i)}
					{@const y = factorTopCalmarByRunCount.PAD + i * 18}
					{@const bw = Math.max(
						2,
						(Math.abs(row.calmar) / factorTopCalmarByRunCount.maxAbs) *
							(factorTopCalmarByRunCount.barMaxW / 2)
					)}
					{@const x =
						row.calmar >= 0
							? factorTopCalmarByRunCount.zeroX
							: factorTopCalmarByRunCount.zeroX - bw}
					{@const color =
						row.calmar >= 1
							? 'var(--ch-profit)'
							: row.calmar >= 0
								? 'var(--ch-teal)'
								: 'var(--ch-loss)'}
					<text
						x={factorTopCalmarByRunCount.PAD}
						y={y + 12}
						font-size="7"
						fill="var(--ch-axis-strong)">{row.name}</text
					>
					<rect {x} {y} width={bw} height="13" rx="2" fill={color} />
					<text
						x={row.calmar >= 0
							? factorTopCalmarByRunCount.zeroX + bw + 2
							: factorTopCalmarByRunCount.zeroX - bw - 2}
						y={y + 12}
						text-anchor={row.calmar >= 0 ? 'start' : 'end'}
						font-size="6"
						fill={color}>{row.calmar.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Top 8 factors by avg Calmar ratio · green≥1 · teal≥0 · red&lt;0 · Calmar = return/drawdown ·
				high Calmar factor = efficient capital use relative to risk taken
			</p>
		</section>
	{/if}
	{#if factorProfitVsCalmar}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit% vs Calmar Scatter (Factors)
			</h3>
			<svg
				viewBox="0 0 {factorProfitVsCalmar.W} {factorProfitVsCalmar.H}"
				class="w-full"
				style="height:{factorProfitVsCalmar.H}px"
			>
				<line
					x1={factorProfitVsCalmar.zeroX}
					y1={factorProfitVsCalmar.PAD}
					x2={factorProfitVsCalmar.zeroX}
					y2={factorProfitVsCalmar.H - factorProfitVsCalmar.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				<line
					x1={factorProfitVsCalmar.PAD}
					y1={factorProfitVsCalmar.zeroY}
					x2={factorProfitVsCalmar.W - factorProfitVsCalmar.PAD}
					y2={factorProfitVsCalmar.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each factorProfitVsCalmar.pts as p, _i (_i)}
					{@const cx = factorProfitVsCalmar.toX(p.profit)}
					{@const cy = factorProfitVsCalmar.toY(p.calmar)}
					{@const color =
						p.profit > 0 && p.calmar > 0
							? 'var(--ch-profit)'
							: p.profit > 0
								? 'var(--ch-warn-light)'
								: 'var(--ch-loss-light)'}
					<circle {cx} {cy} r="2.5" fill={color} />
				{/each}
				<text
					x={factorProfitVsCalmar.PAD}
					y={factorProfitVsCalmar.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{factorProfitVsCalmar.minP}%</text
				>
				<text
					x={factorProfitVsCalmar.W - factorProfitVsCalmar.PAD}
					y={factorProfitVsCalmar.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{factorProfitVsCalmar.maxP}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Scatter of avg profit% (X) vs avg Calmar (Y) per factor · green=both positive ·
				yellow=profit only · red=negative profit · top-right = best factors: profitable AND capital
				efficient
			</p>
		</section>
	{/if}
	{#if factorRunCountByTF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Run Count by Timeframe (Factors)
			</h3>
			<svg
				viewBox="0 0 {factorRunCountByTF.W} {factorRunCountByTF.H}"
				class="w-full"
				style="height:{factorRunCountByTF.H}px"
			>
				{#each factorRunCountByTF.rows as row, i (i)}
					{@const x = factorRunCountByTF.PAD + i * (factorRunCountByTF.bw + 1)}
					{@const bh = Math.max(
						2,
						(row.count / factorRunCountByTF.maxCount) *
							(factorRunCountByTF.H - factorRunCountByTF.PAD * 2 - 10)
					)}
					{@const y = factorRunCountByTF.H - factorRunCountByTF.PAD - 10 - bh}
					<rect {x} {y} width={factorRunCountByTF.bw} height={bh} rx="1" fill="var(--ch-warn)" />
					<text
						x={x + factorRunCountByTF.bw / 2}
						y={factorRunCountByTF.H - 1}
						text-anchor="middle"
						font-size="6.5"
						fill="var(--ch-axis)">{row.tf}</text
					>
					<text
						x={x + factorRunCountByTF.bw / 2}
						y={y - 2}
						text-anchor="middle"
						font-size="6"
						fill="var(--ch-warn)">{row.count}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Total backtest run count by timeframe across factor runs · orange bars · timeframe with most
				runs = most-tested configuration · reveals where research effort is concentrated
			</p>
		</section>
	{/if}
	{#if factorSharpeByWinRateBucket}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Sharpe by Win Rate Bucket
			</h3>
			<svg
				viewBox="0 0 {factorSharpeByWinRateBucket.W} {factorSharpeByWinRateBucket.H}"
				class="w-full"
				style="height:{factorSharpeByWinRateBucket.H}px"
			>
				<line
					x1={factorSharpeByWinRateBucket.PAD}
					y1={factorSharpeByWinRateBucket.midY}
					x2={factorSharpeByWinRateBucket.W - factorSharpeByWinRateBucket.PAD}
					y2={factorSharpeByWinRateBucket.midY}
					stroke="var(--ch-axis-muted)"
					stroke-width="0.5"
				/>
				{#each factorSharpeByWinRateBucket.rows as row, i (i)}
					{@const x = factorSharpeByWinRateBucket.PAD + i * (factorSharpeByWinRateBucket.bw + 2)}
					{@const barH = Math.max(
						2,
						(Math.abs(row.avg) / factorSharpeByWinRateBucket.maxAbs) *
							(factorSharpeByWinRateBucket.midY - 8)
					)}
					{@const y =
						row.avg >= 0
							? factorSharpeByWinRateBucket.midY - barH
							: factorSharpeByWinRateBucket.midY}
					{@const color =
						row.avg >= 1 ? 'var(--ch-profit)' : row.avg >= 0 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
					<rect {x} {y} width={factorSharpeByWinRateBucket.bw} height={barH} rx="2" fill={color} />
					<text
						x={x + factorSharpeByWinRateBucket.bw / 2}
						y={factorSharpeByWinRateBucket.H - 1}
						text-anchor="middle"
						font-size="6.5"
						fill="var(--ch-axis-strong)">{row.label}</text
					>
					<text
						x={x + factorSharpeByWinRateBucket.bw / 2}
						y={row.avg >= 0 ? y - 2 : y + barH + 8}
						text-anchor="middle"
						font-size="6"
						fill={color}>{row.avg.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg Sharpe ratio by win rate bucket · green≥1 · teal≥0 · red&lt;0 · diverging bars from
				midline · validates whether higher win rate reliably produces better risk-adjusted returns
			</p>
		</section>
	{/if}
	{#if factorAvgDrawdownByTF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Max Drawdown% by Timeframe
			</h3>
			<svg
				viewBox="0 0 {factorAvgDrawdownByTF.W} {factorAvgDrawdownByTF.H}"
				class="w-full"
				style="height:{factorAvgDrawdownByTF.H}px"
			>
				{#each factorAvgDrawdownByTF.rows as row, i (i)}
					{@const y = factorAvgDrawdownByTF.PAD + i * 20}
					{@const bw = Math.max(
						2,
						(row.avg / factorAvgDrawdownByTF.maxAvg) * factorAvgDrawdownByTF.barMaxW
					)}
					{@const color =
						row.avg <= 10
							? 'var(--ch-profit)'
							: row.avg <= 25
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					<text x={factorAvgDrawdownByTF.PAD} y={y + 13} font-size="8" fill="var(--ch-axis-strong)"
						>{row.tf}</text
					>
					<rect x={factorAvgDrawdownByTF.PAD + 40} {y} width={bw} height="14" rx="2" fill={color} />
					<text x={factorAvgDrawdownByTF.PAD + 40 + bw + 3} y={y + 12} font-size="6.5" fill={color}
						>{row.avg.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg max drawdown% by timeframe · green≤10% · yellow≤25% · red&gt;25% · longer timeframes
				often show higher drawdowns but wider profit windows
			</p>
		</section>
	{/if}
	{#if factorTopProfitByFactor}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Profit% by Factor
			</h3>
			<svg
				viewBox="0 0 {factorTopProfitByFactor.W} {factorTopProfitByFactor.H}"
				class="w-full"
				style="height:{factorTopProfitByFactor.H}px"
			>
				<line
					x1={factorTopProfitByFactor.zeroX}
					y1={0}
					x2={factorTopProfitByFactor.zeroX}
					y2={factorTopProfitByFactor.H}
					stroke="var(--ch-axis-muted)"
					stroke-width="0.5"
				/>
				{#each factorTopProfitByFactor.rows as row, i (i)}
					{@const y = factorTopProfitByFactor.PAD + i * 18}
					{@const bw = Math.max(
						2,
						(Math.abs(row.best) / factorTopProfitByFactor.maxAbs) *
							(factorTopProfitByFactor.barMaxW / 2)
					)}
					{@const x =
						row.best >= 0 ? factorTopProfitByFactor.zeroX : factorTopProfitByFactor.zeroX - bw}
					{@const color =
						row.best >= 20
							? 'var(--ch-profit)'
							: row.best >= 0
								? 'var(--ch-teal)'
								: 'var(--ch-loss)'}
					<text
						x={factorTopProfitByFactor.PAD}
						y={y + 12}
						font-size="7"
						fill="var(--ch-axis-strong)">{row.factor}</text
					>
					<rect {x} {y} width={bw} height="13" rx="2" fill={color} />
					<text
						x={row.best >= 0
							? factorTopProfitByFactor.zeroX + bw + 2
							: factorTopProfitByFactor.zeroX - bw - 2}
						y={y + 11}
						text-anchor={row.best >= 0 ? 'start' : 'end'}
						font-size="6.5"
						fill={color}>{row.best.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Best profit% ever achieved per factor · green≥20% · teal≥0% · shows peak potential of each
				factor configuration — peak differs from avg which is shown in other panels
			</p>
		</section>
	{/if}
	{#if factorRunsByMonth}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Monthly Factor Run Count
			</h3>
			<svg
				viewBox="0 0 {factorRunsByMonth.W} {factorRunsByMonth.H}"
				class="w-full"
				style="height:{factorRunsByMonth.H}px"
			>
				{#each factorRunsByMonth.pts as pt, i (i)}
					{@const x = factorRunsByMonth.PAD + i * (factorRunsByMonth.bw + 0.5)}
					{@const bh = Math.max(
						2,
						(pt.count / factorRunsByMonth.maxCount) * (factorRunsByMonth.H - 14)
					)}
					{@const y = factorRunsByMonth.H - bh - 8}
					{@const color =
						pt.count >= factorRunsByMonth.maxCount * 0.7
							? 'var(--ch-warn)'
							: pt.count >= factorRunsByMonth.maxCount * 0.4
								? 'var(--ch-warn)'
								: 'var(--ch-axis-muted)'}
					<rect {x} {y} width={factorRunsByMonth.bw} height={bh} rx="1" fill={color} />
					<text
						x={x + factorRunsByMonth.bw / 2}
						y={factorRunsByMonth.H - 1}
						text-anchor="middle"
						font-size="5.5"
						fill="var(--ch-axis)">{pt.mo}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Factor backtest run count by month · orange = peak research months · reveals when factor
				exploration was most intensive and whether cadence has been maintained
			</p>
		</section>
	{/if}
	{#if factorAvgProfitCDF}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">Per-Factor Avg Profit CDF</h3>
			<svg
				viewBox={`0 0 ${factorAvgProfitCDF.W} ${factorAvgProfitCDF.H}`}
				width="100%"
				style="height:65px"
			>
				<line
					x1={factorAvgProfitCDF.PAD}
					y1={factorAvgProfitCDF.H - factorAvgProfitCDF.PAD}
					x2={factorAvgProfitCDF.W - factorAvgProfitCDF.PAD}
					y2={factorAvgProfitCDF.H - factorAvgProfitCDF.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				<line
					x1={factorAvgProfitCDF.toX(0)}
					y1={factorAvgProfitCDF.PAD}
					x2={factorAvgProfitCDF.toX(0)}
					y2={factorAvgProfitCDF.H - factorAvgProfitCDF.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
					stroke-dasharray="2,2"
				/>
				<polyline
					points={factorAvgProfitCDF.polyline}
					fill="none"
					stroke="var(--ch-profit-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={factorAvgProfitCDF.PAD}
					y={factorAvgProfitCDF.H - 2}
					font-size="5.5"
					fill="var(--ch-axis-muted)">{factorAvgProfitCDF.minV}%</text
				>
				<text
					x={factorAvgProfitCDF.W - factorAvgProfitCDF.PAD}
					y={factorAvgProfitCDF.H - 2}
					text-anchor="end"
					font-size="5.5"
					fill="var(--ch-axis-muted)">{factorAvgProfitCDF.maxV}%</text
				>
				<text
					x={factorAvgProfitCDF.W / 2}
					y={factorAvgProfitCDF.PAD + 8}
					text-anchor="middle"
					font-size="7"
					fill="var(--ch-profit-strong)">median {factorAvgProfitCDF.median}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				CDF of per-factor avg profit% · green S-curve · dashed at 0% breakeven · factors to the
				right are profitable · steep curve = most factors cluster near median
			</p>
		</section>
	{/if}
	{#if factorWinRateByDow}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">
				Win Rate% by Backtest Start Day
			</h3>
			<svg
				viewBox={`0 0 ${factorWinRateByDow.W} ${factorWinRateByDow.H}`}
				width="100%"
				style="height:65px"
			>
				<line
					x1={factorWinRateByDow.PAD}
					y1={factorWinRateByDow.H -
						factorWinRateByDow.PAD -
						(50 / factorWinRateByDow.maxWR) * (factorWinRateByDow.H - factorWinRateByDow.PAD * 2)}
					x2={factorWinRateByDow.W - factorWinRateByDow.PAD}
					y2={factorWinRateByDow.H -
						factorWinRateByDow.PAD -
						(50 / factorWinRateByDow.maxWR) * (factorWinRateByDow.H - factorWinRateByDow.PAD * 2)}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
					stroke-dasharray="2,2"
				/>
				{#each factorWinRateByDow.bars as b, i (i)}
					{@const bh =
						(b.wr / factorWinRateByDow.maxWR) * (factorWinRateByDow.H - factorWinRateByDow.PAD * 2)}
					{@const x = factorWinRateByDow.PAD + i * (factorWinRateByDow.bw + 2)}
					{@const y = factorWinRateByDow.H - factorWinRateByDow.PAD - bh}
					{@const color =
						b.wr >= 55
							? 'var(--ch-profit)'
							: b.wr >= 45
								? 'var(--ch-teal)'
								: 'var(--ch-loss-light)'}
					<rect {x} {y} width={factorWinRateByDow.bw} height={bh} fill={color} rx="1" />
					<text
						x={x + factorWinRateByDow.bw / 2}
						y={factorWinRateByDow.H}
						text-anchor="middle"
						font-size="6"
						fill="var(--ch-axis)">{b.label}</text
					>
					<text
						x={x + factorWinRateByDow.bw / 2}
						y={y - 2}
						text-anchor="middle"
						font-size="5.5"
						fill={color}>{b.wr.toFixed(0)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Win rate% by factor run start day of week · green≥55% · teal≥45% · red&lt;45% · dashed at
				50% · day-of-week bias may indicate regime sensitivity
			</p>
		</section>
	{/if}
	{#if factorSharpeCalmarScatter2}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">
				Sharpe vs Calmar Scatter (per run)
			</h3>
			<svg
				viewBox={`0 0 ${factorSharpeCalmarScatter2.W} ${factorSharpeCalmarScatter2.H}`}
				width="100%"
				style="height:80px"
			>
				<line
					x1={factorSharpeCalmarScatter2.PAD}
					y1={factorSharpeCalmarScatter2.toY(0)}
					x2={factorSharpeCalmarScatter2.W - factorSharpeCalmarScatter2.PAD}
					y2={factorSharpeCalmarScatter2.toY(0)}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
					stroke-dasharray="2,2"
				/>
				{#each factorSharpeCalmarScatter2.pts as p, _i (_i)}
					<circle
						cx={factorSharpeCalmarScatter2.toX(p.x)}
						cy={factorSharpeCalmarScatter2.toY(p.y)}
						r="2.5"
						fill={p.wr >= 0.55
							? 'var(--ch-profit-light)'
							: p.wr >= 0.45
								? 'var(--ch-teal-light)'
								: 'var(--ch-loss-light)'}
					/>
				{/each}
				<text
					x={factorSharpeCalmarScatter2.PAD}
					y={factorSharpeCalmarScatter2.H - 1}
					font-size="5.5"
					fill="var(--ch-axis-muted)">Sharpe {factorSharpeCalmarScatter2.minX}</text
				>
				<text
					x={factorSharpeCalmarScatter2.W - factorSharpeCalmarScatter2.PAD}
					y={factorSharpeCalmarScatter2.H - 1}
					text-anchor="end"
					font-size="5.5"
					fill="var(--ch-axis-muted)">{factorSharpeCalmarScatter2.maxX}</text
				>
				<text
					x={factorSharpeCalmarScatter2.PAD - 2}
					y={factorSharpeCalmarScatter2.toY(+factorSharpeCalmarScatter2.maxY)}
					font-size="5"
					fill="var(--ch-axis-muted)">Cal {factorSharpeCalmarScatter2.maxY}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Sharpe vs Calmar ratio per run · green=WR≥55% · teal=WR≥45% · red=WR&lt;45% · upper-right =
				best risk-adjusted runs · cluster shape reveals factor quality
			</p>
		</section>
	{/if}
	{#if factorWinRateTrend}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">
				Rolling Win Rate Trend (10-run window)
			</h3>
			<svg
				viewBox={`0 0 ${factorWinRateTrend.W} ${factorWinRateTrend.H}`}
				width="100%"
				style="height:65px"
			>
				<line
					x1={factorWinRateTrend.PAD}
					y1={factorWinRateTrend.y50}
					x2={factorWinRateTrend.W - factorWinRateTrend.PAD}
					y2={factorWinRateTrend.y50}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
					stroke-dasharray="2,2"
				/>
				<polyline
					points={factorWinRateTrend.polyline}
					fill="none"
					stroke="var(--ch-profit-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={factorWinRateTrend.PAD}
					y={factorWinRateTrend.H}
					font-size="5.5"
					fill="var(--ch-axis-muted)">{factorWinRateTrend.minWR}%</text
				>
				<text
					x={factorWinRateTrend.W - factorWinRateTrend.PAD}
					y={factorWinRateTrend.H}
					text-anchor="end"
					font-size="5.5"
					fill="var(--ch-axis-muted)">{factorWinRateTrend.maxWR}%</text
				>
				<text
					x={factorWinRateTrend.PAD}
					y={factorWinRateTrend.y50 - 2}
					font-size="5"
					fill="var(--ch-axis-muted)">50%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				10-run rolling win rate% across {factorWinRateTrend.n} factor backtests · green line · dashed
				at 50% · rising trend signals improving factor regime · drops indicate deterioration
			</p>
		</section>
	{/if}
</main>
