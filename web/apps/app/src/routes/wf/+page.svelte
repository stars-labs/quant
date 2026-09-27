<script lang="ts">
	import type { PageData } from './$types';
	import type { WfResult } from '$lib/types';
	import { t, type Lang } from '$lib/i18n';
	import ChartInfo from '$lib/components/chart-info.svelte';

	let { data }: { data: PageData } = $props();
	const lang = $derived<Lang>(data.lang ?? 'zh');
	const windows = $derived(data.results as WfRow[]);
	const results = $derived(data.results);

	// Metrics referenced by some optional charts that are NOT part of the
	// api.wf_results row (legacy payloads only). Typed as optional so the
	// charts degrade to "no data" instead of failing the type-check.
	type WfRow = WfResult & {
		sharpe_ratio?: number | null;
		sortino_ratio?: number | null;
		sortino?: number | null;
		calmar_ratio?: number | null;
		profit_factor?: number | null;
		max_drawdown?: number | null;
		max_drawdown_pct?: number | null;
		winning_trades?: number | null;
	};
	const wfRows = $derived(data.results as WfRow[]);

	type WfSort = 'name' | 'sum' | 'stability';
	let wfSort = $state<WfSort>('sum');
	let wfSortAsc = $state(false);

	// Group by strategy → latest run_date per strategy → rows by window
	const byStrategy = $derived.by(() => {
		const map = new Map<string, WfResult[]>();
		for (const r of data.results) {
			if (!map.has(r.strategy)) map.set(r.strategy, []);
			map.get(r.strategy)!.push(r);
		}
		const out: Array<{ strategy: string; windows: Record<string, WfResult> }> = [];
		for (const [strategy, rows] of map) {
			const latestRun = rows.map((r) => r.run_date).reduce((a, b) => (a > b ? a : b));
			const windows: Record<string, WfResult> = {};
			for (const r of rows) if (r.run_date === latestRun) windows[r.window_label] = r;
			out.push({ strategy, windows });
		}
		return out;
	});

	const sortedByStrategy = $derived.by(() => {
		const arr = [...byStrategy];
		const dir = wfSortAsc ? 1 : -1;
		if (wfSort === 'name') return arr.sort((a, b) => dir * a.strategy.localeCompare(b.strategy));
		if (wfSort === 'sum')
			return arr.sort((a, b) => {
				const sa = allWindows.reduce((s, w) => s + (a.windows[w]?.tot_profit_pct ?? 0), 0);
				const sb = allWindows.reduce((s, w) => s + (b.windows[w]?.tot_profit_pct ?? 0), 0);
				return dir * (sa - sb);
			});
		if (wfSort === 'stability')
			return arr.sort((a, b) => dir * (stabilityScore(a.windows) - stabilityScore(b.windows)));
		return arr;
	});

	// All window labels (union, sorted)
	const allWindows = $derived.by(() => {
		const s = new Set<string>();
		for (const { windows } of byStrategy) for (const w in windows) s.add(w);
		return [...s].sort();
	});

	// Stability score: % of OK windows with positive profit
	function stabilityScore(windows: Record<string, WfResult>): number {
		const ok = Object.values(windows).filter((r) => r.status === 'ok');
		if (ok.length === 0) return 0;
		const pos = ok.filter((r) => (r.tot_profit_pct ?? 0) > 0).length;
		return Math.round((pos / ok.length) * 100);
	}

	// Plain bilingual names for the 8 walk-forward regime windows (raw keys stay in tooltips)
	const REGIME_LABELS: Record<string, { zh: string; en: string }> = {
		'2018_CRASH': { zh: '2018 崩盘年', en: '2018 crash year' },
		'2019_ACCUMULATION': { zh: '2019 积累期', en: '2019 accumulation' },
		'2020_COVID': { zh: '2020 疫情震荡', en: '2020 COVID shock' },
		'2021_BULL_TOP': { zh: '2021 牛市顶', en: '2021 bull top' },
		'2022_LUNA_FTX': { zh: '2022 爆雷年（LUNA/FTX）', en: '2022 blow-up year (LUNA/FTX)' },
		'2023_RECOVERY': { zh: '2023 复苏', en: '2023 recovery' },
		'2024_ETF_BULL': { zh: '2024 ETF 牛市', en: '2024 ETF bull' },
		'2025_PRESENT': { zh: '2025 至今', en: '2025 – now' }
	};
	function regimeLabel(w: string): string {
		const key = w.replace(/^W\d+_/, '');
		const m = REGIME_LABELS[key];
		return m ? (lang === 'en' ? m.en : m.zh) : key;
	}

	// One-line takeaway: the strategy that stayed profitable in the most regimes
	const headline = $derived.by(() => {
		const rows = byStrategy
			.map(({ strategy, windows }) => {
				const ok = Object.values(windows).filter((r) => r.status === 'ok');
				return { strategy, windows, score: stabilityScore(windows), okCount: ok.length };
			})
			.filter((r) => r.okCount >= 2)
			.sort((a, b) => b.score - a.score || b.okCount - a.okCount);
		if (rows.length === 0) return null;
		const top = rows[0];
		const w2022 = allWindows.find((w) => w.replace(/^W\d+_/, '').startsWith('2022'));
		const r2022 = w2022 ? top.windows[w2022] : undefined;
		const survived2022 = r2022?.status === 'ok' && (r2022.tot_profit_pct ?? 0) > 0;
		return { strategy: top.strategy, score: top.score, okCount: top.okCount, survived2022 };
	});

	// Cell background color based on profit magnitude
	function cellBg(v: number | null | undefined): string {
		if (v == null) return '';
		if (v > 15) return 'bg-green-500/25';
		if (v > 5) return 'bg-green-500/15';
		if (v > 0) return 'bg-green-500/8';
		if (v > -5) return 'bg-red-500/10';
		if (v > -15) return 'bg-red-500/20';
		return 'bg-red-500/30';
	}

	// Strategy stability leaderboard
	const stabilityLeaderboard = $derived.by(() => {
		if (byStrategy.length < 2) return null;
		const rows = byStrategy
			.map(({ strategy, windows }) => {
				const score = stabilityScore(windows);
				const ok = Object.values(windows).filter((r) => r.status === 'ok');
				const sum = ok.reduce((s, r) => s + (r.tot_profit_pct ?? 0), 0);
				return { strategy, score, sum, okCount: ok.length };
			})
			.sort((a, b) => b.score - a.score);
		const maxScore = Math.max(1, ...rows.map((r) => r.score));
		return rows.map((r) => ({ ...r, barPct: (r.score / maxScore) * 100 }));
	});

	// Per-window aggregate stats
	const windowAgg = $derived.by(() => {
		const agg: Record<string, { vals: number[]; okCount: number }> = {};
		for (const w of allWindows) agg[w] = { vals: [], okCount: 0 };
		for (const { windows } of byStrategy) {
			for (const w of allWindows) {
				const r = windows[w];
				if (r?.status === 'ok' && r.tot_profit_pct != null) {
					agg[w].vals.push(r.tot_profit_pct);
					if (r.tot_profit_pct > 0) agg[w].okCount++;
				}
			}
		}
		return Object.fromEntries(
			Object.entries(agg).map(([w, { vals, okCount }]) => [
				w,
				{
					avg: vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null,
					wr: vals.length ? okCount / vals.length : null,
					n: vals.length
				}
			])
		);
	});

	const avgSum = $derived(allWindows.reduce((acc, w) => acc + (windowAgg[w]?.avg ?? 0), 0));

	// Per-strategy window waterfall (top stability strategy, sequential profits)
	const windowWaterfall = $derived.by(() => {
		if (byStrategy.length === 0 || allWindows.length < 2) return null;
		const top = [...byStrategy].sort(
			(a, b) => stabilityScore(b.windows) - stabilityScore(a.windows)
		)[0];
		const bars = allWindows.map((w) => {
			const r = top.windows[w];
			return { window: w, profit: r?.status === 'ok' ? (r.tot_profit_pct ?? null) : null };
		});
		const vals = bars.map((b) => b.profit ?? 0);
		let running = 0;
		const cumulative = vals.map((v) => {
			running += v;
			return running;
		});
		const maxAbs = Math.max(1, ...vals.map(Math.abs));
		return { strategy: top.strategy, bars, cumulative, maxAbs };
	});

	// Per-window champion: strategy with highest ok profit
	const championByWindow = $derived.by(() => {
		const champ: Record<string, { strategy: string; profit: number }> = {};
		for (const w of allWindows) {
			let best: { strategy: string; profit: number } | null = null;
			for (const { strategy, windows } of byStrategy) {
				const r = windows[w];
				if (r?.status === 'ok' && r.tot_profit_pct != null) {
					if (!best || r.tot_profit_pct > best.profit)
						best = { strategy, profit: r.tot_profit_pct };
				}
			}
			if (best) champ[w] = best;
		}
		return champ;
	});

	// Window win frequency: how many windows each strategy has positive profit in
	// Average profit per window across all strategies — shows market regime trend
	const windowAvgTrend = $derived.by(() => {
		const windows = allWindows.filter((w) => windowAgg[w]?.avg != null);
		if (windows.length < 3) return null;
		const vals = windows.map((w) => windowAgg[w].avg!);
		const W = 520,
			H = 80,
			PAD = 8;
		const vMin = Math.min(...vals, 0),
			vMax = Math.max(...vals, 0.001);
		const toX = (i: number) => PAD + (i / Math.max(1, windows.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - vMin) / (vMax - vMin || 0.001)) * (H - PAD * 2);
		const zeroY = toY(0);
		const polyline = vals.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
		const dots = vals.map((v, i) => ({
			x: toX(i),
			y: toY(v),
			v,
			label: windows[i].replace(/^W\d+_/, '')
		}));
		return { polyline, dots, W, H, PAD, zeroY, windows, vals };
	});

	// Strategy profit sum ranking: cumulative window profit per strategy
	const stratProfitSumRanking = $derived.by(() => {
		const rows = byStrategy
			.map(({ strategy, windows }) => {
				const ok = Object.values(windows).filter(
					(r) => r.status === 'ok' && r.tot_profit_pct != null
				);
				const sum = ok.reduce((s, r) => s + r.tot_profit_pct!, 0);
				return { strategy, sum, okCount: ok.length };
			})
			.filter((r) => r.okCount >= 1)
			.sort((a, b) => b.sum - a.sum);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.sum)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.sum) / maxAbs) * 100 }));
	});

	// Window best-vs-worst: for each window, the spread between best and worst strategy profit
	const windowBestWorstContrast = $derived.by(() => {
		const windows = allWindows.filter((w) => {
			const vals = byStrategy
				.map(({ windows: ws }) => ws[w]?.tot_profit_pct)
				.filter((v): v is number => v != null);
			return vals.length >= 2;
		});
		if (windows.length < 2) return null;
		const rows = windows
			.map((w) => {
				const vals = byStrategy
					.map(({ strategy, windows: ws }) => ({ strategy, v: ws[w]?.tot_profit_pct }))
					.filter((e): e is { strategy: string; v: number } => e.v != null);
				vals.sort((a, b) => b.v - a.v);
				const best = vals[0];
				const worst = vals[vals.length - 1];
				const spread = best.v - worst.v;
				return { window: w.replace(/^W\d+_/, ''), spread, best, worst, count: vals.length };
			})
			.sort((a, b) => b.spread - a.spread)
			.slice(0, 12);
		const maxSpread = Math.max(0.01, ...rows.map((r) => r.spread));
		return rows.map((r) => ({ ...r, spreadBarPct: (r.spread / maxSpread) * 100 }));
	});

	// Window participation rate: how many strategies have ok results per window
	const windowParticipationRate = $derived.by(() => {
		if (allWindows.length < 2 || byStrategy.length < 2) return null;
		const total = byStrategy.length;
		const rows = allWindows
			.map((w) => {
				const ok = byStrategy.filter(
					({ windows }) => windows[w]?.status === 'ok' && windows[w]?.tot_profit_pct != null
				).length;
				const avgProfit = windowAgg[w]?.avg ?? null;
				return { window: w.replace(/^W\d+_/, ''), ok, total, pct: ok / total, avgProfit };
			})
			.sort((a, b) => b.ok - a.ok);
		return rows;
	});

	// Strategy × window heatmap: profit color per cell
	const strategyWindowHeatmap = $derived.by(() => {
		if (byStrategy.length < 2 || allWindows.length < 2) return null;
		const strats = byStrategy.slice(0, 12);
		const windows = allWindows.slice(0, 10);
		const allVals = strats.flatMap(({ windows: ws }) =>
			windows.map((w) => ws[w]?.tot_profit_pct).filter((v): v is number => v != null)
		);
		if (allVals.length < 4) return null;
		const maxAbs = Math.max(0.01, ...allVals.map(Math.abs));
		const grid = strats.map(({ strategy, windows: ws }) => ({
			strategy,
			cells: windows.map((w) => {
				const r = ws[w];
				if (!r || r.status !== 'ok' || r.tot_profit_pct == null) return null;
				return { v: r.tot_profit_pct, intensity: Math.abs(r.tot_profit_pct) / maxAbs };
			})
		}));
		return { grid, windows: windows.map((w) => w.replace(/^W\d+_/, '')), maxAbs };
	});

	// Avg trades per window across all strategies
	const avgTradesPerWindow = $derived.by(() => {
		if (allWindows.length < 2 || byStrategy.length < 2) return null;
		const bars = allWindows
			.map((w) => {
				const tradeCounts = byStrategy
					.map(({ windows }) => windows[w])
					.filter((r) => r?.status === 'ok' && r.trades != null)
					.map((r) => r!.trades!);
				const avg = tradeCounts.length
					? tradeCounts.reduce((a, b) => a + b, 0) / tradeCounts.length
					: null;
				return { window: w.replace(/^W\d+_/, ''), avg, n: tradeCounts.length };
			})
			.filter((b) => b.avg != null);
		if (bars.length < 2) return null;
		const maxAvg = Math.max(1, ...bars.map((b) => b.avg!));
		return bars.map((b) => ({ ...b, barPct: (b.avg! / maxAvg) * 100 }));
	});

	// Longest profitable window streak per strategy
	const strategyWinStreak = $derived.by(() => {
		if (allWindows.length < 2 || byStrategy.length < 2) return null;
		const rows = byStrategy
			.map(({ strategy, windows }) => {
				const results = allWindows
					.map((w) => windows[w])
					.filter((r) => r && r.status === 'ok' && r.tot_profit_pct != null)
					.map((r) => (r!.tot_profit_pct! > 0 ? 1 : 0));
				if (results.length < 2) return null;
				let maxStreak = 0,
					cur = 0;
				for (const v of results) {
					cur = v ? cur + 1 : 0;
					if (cur > maxStreak) maxStreak = cur;
				}
				const total = results.length;
				const wins = results.filter((v) => v).length;
				return { strategy, streak: maxStreak, total, wr: wins / total };
			})
			.filter((r): r is NonNullable<typeof r> => r !== null && r.streak >= 1)
			.sort((a, b) => b.streak - a.streak || b.wr - a.wr)
			.slice(0, 10);
		if (rows.length < 2) return null;
		const maxStreak = Math.max(1, ...rows.map((r) => r.streak));
		return rows.map((r) => ({ ...r, barPct: (r.streak / maxStreak) * 100 }));
	});

	// Avg profit per timeframe across all WF results
	const wfTimeframeBreakdown = $derived.by(() => {
		const ok = data.results.filter(
			(r) => r.status === 'ok' && r.tot_profit_pct != null && r.timeframe
		);
		if (ok.length < 4) return null;
		const map = new Map<string, { sum: number; count: number; wins: number }>();
		for (const r of ok) {
			if (!map.has(r.timeframe)) map.set(r.timeframe, { sum: 0, count: 0, wins: 0 });
			const v = map.get(r.timeframe)!;
			v.sum += r.tot_profit_pct!;
			v.count++;
			if (r.tot_profit_pct! > 0) v.wins++;
		}
		if (map.size < 2) return null;
		const TF_ORDER = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d'];
		const rows = [...map.entries()]
			.map(([tf, v]) => ({ tf, avg: v.sum / v.count, count: v.count, wr: v.wins / v.count }))
			.sort((a, b) => TF_ORDER.indexOf(a.tf) - TF_ORDER.indexOf(b.tf) || a.tf.localeCompare(b.tf));
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.avg)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.avg) / maxAbs) * 100 }));
	});

	// Avg profit per participated window per strategy: normalizes for strategies with fewer windows
	const stratAvgProfitPerWindow = $derived.by(() => {
		const rows = byStrategy
			.map(({ strategy, windows }) => {
				const ok = Object.values(windows).filter(
					(r) => r.status === 'ok' && r.tot_profit_pct != null
				);
				if (ok.length === 0) return null;
				const avg = ok.reduce((s, r) => s + r.tot_profit_pct!, 0) / ok.length;
				const wins = ok.filter((r) => r.tot_profit_pct! > 0).length;
				return { strategy, avg, count: ok.length, wins, wr: wins / ok.length };
			})
			.filter((r): r is NonNullable<typeof r> => r !== null && r.count >= 2)
			.sort((a, b) => b.avg - a.avg);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.avg)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.avg) / maxAbs) * 100 }));
	});

	// Each strategy's profit in the most recent WF window (current form snapshot)
	const stratLastWindowPerf = $derived.by(() => {
		if (allWindows.length === 0) return null;
		const lastWindow = allWindows[allWindows.length - 1];
		const rows = byStrategy
			.map(({ strategy, windows }) => {
				const r = windows[lastWindow];
				if (!r || r.status !== 'ok' || r.tot_profit_pct == null) return null;
				return { strategy, profit: r.tot_profit_pct, trades: r.trades ?? 0 };
			})
			.filter((r): r is NonNullable<typeof r> => r !== null)
			.sort((a, b) => b.profit - a.profit);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.profit)));
		return {
			rows: rows.map((r) => ({ ...r, barPct: (Math.abs(r.profit) / maxAbs) * 100 })),
			window: lastWindow.replace(/^W\d+_/, '')
		};
	});

	// Window profit volatility: std dev of strategy profits per window — high = strategies diverged
	const windowVolatility = $derived.by(() => {
		const rows = allWindows
			.map((w) => {
				const vals = byStrategy
					.map(({ windows }) => windows[w]?.tot_profit_pct)
					.filter((v): v is number => v != null);
				if (vals.length < 2) return null;
				const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
				const std = Math.sqrt(vals.reduce((s, v) => s + (v - mean) ** 2, 0) / vals.length);
				return { window: w, label: w.replace(/^W\d+_/, ''), std, mean, count: vals.length };
			})
			.filter((r): r is NonNullable<typeof r> => r !== null);
		if (rows.length < 2) return null;
		const maxStd = Math.max(0.01, ...rows.map((r) => r.std));
		return rows.map((r) => ({ ...r, barPct: (r.std / maxStd) * 100 }));
	});

	const stratWinFrequency = $derived.by(() => {
		const rows = byStrategy
			.map(({ strategy, windows }) => {
				const participated = allWindows.filter(
					(w) => windows[w]?.status === 'ok' && windows[w]?.tot_profit_pct != null
				);
				const wins = participated.filter((w) => (windows[w]?.tot_profit_pct ?? 0) > 0);
				return {
					strategy,
					wins: wins.length,
					total: participated.length,
					wr: participated.length > 0 ? wins.length / participated.length : 0
				};
			})
			.filter((r) => r.total >= 2)
			.sort((a, b) => b.wr - a.wr || b.wins - a.wins);
		if (rows.length < 2) return null;
		return rows;
	});

	const strategyMomentum = $derived.by(() => {
		const rows = byStrategy
			.map(({ strategy, windows }) => {
				const participated = allWindows.filter(
					(w) => windows[w]?.status === 'ok' && windows[w]?.tot_profit_pct != null
				);
				if (participated.length < 4) return null;
				const profits = participated.map((w) => windows[w]!.tot_profit_pct!);
				const allAvg = profits.reduce((a, b) => a + b, 0) / profits.length;
				const recent = profits.slice(-3);
				const recentAvg = recent.reduce((a, b) => a + b, 0) / recent.length;
				const momentum = recentAvg - allAvg;
				return { strategy, allAvg, recentAvg, momentum, count: participated.length };
			})
			.filter((r): r is NonNullable<typeof r> => r !== null)
			.sort((a, b) => b.momentum - a.momentum);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.momentum)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.momentum) / maxAbs) * 100 }));
	});

	const windowProfitRange = $derived.by(() => {
		const rows = allWindows
			.map((w) => {
				const profits = byStrategy
					.map(({ windows }) => windows[w]?.tot_profit_pct)
					.filter((v): v is number => v != null && isFinite(v));
				if (profits.length < 2) return null;
				const mn = Math.min(...profits),
					mx = Math.max(...profits);
				const avg = profits.reduce((a, b) => a + b, 0) / profits.length;
				return { w, mn, mx, avg, spread: mx - mn, count: profits.length };
			})
			.filter((r): r is NonNullable<typeof r> => r !== null);
		if (rows.length < 3) return null;
		const absMax = Math.max(0.01, ...rows.map((r) => Math.max(Math.abs(r.mn), Math.abs(r.mx))));
		const H = 80,
			MID = H / 2,
			PAD = 4;
		const toY = (v: number) => MID - (v / absMax) * (MID - PAD);
		return rows.map((r) => ({ ...r, yMn: toY(r.mn), yMx: toY(r.mx), yAvg: toY(r.avg) }));
	});

	const windowChampionFrequency = $derived.by(() => {
		const freq = new Map<string, number>();
		for (const w of allWindows) {
			let best: string | null = null,
				bestProfit = -Infinity;
			for (const { strategy, windows } of byStrategy) {
				const p = windows[w]?.tot_profit_pct;
				if (p != null && p > bestProfit) {
					bestProfit = p;
					best = strategy;
				}
			}
			if (best) freq.set(best, (freq.get(best) ?? 0) + 1);
		}
		const rows = [...freq.entries()]
			.map(([strategy, wins]) => ({ strategy, wins }))
			.sort((a, b) => b.wins - a.wins)
			.slice(0, 10);
		if (rows.length < 2) return null;
		const maxWins = rows[0].wins;
		return rows.map((r) => ({ ...r, barPct: (r.wins / maxWins) * 100 }));
	});

	// Strategy profit std dev across windows: consistency metric (distinct from windowVolatility which groups by window, not strategy)
	const strategyProfitStdDev = $derived.by(() => {
		const rows = byStrategy
			.map(({ strategy, windows }) => {
				const profits = allWindows
					.map((w) => windows[w])
					.filter((r) => r?.status === 'ok' && r.tot_profit_pct != null)
					.map((r) => r!.tot_profit_pct!);
				if (profits.length < 3) return null;
				const mean = profits.reduce((a, b) => a + b, 0) / profits.length;
				const std = Math.sqrt(profits.reduce((s, v) => s + (v - mean) ** 2, 0) / profits.length);
				return { strategy, std, mean, count: profits.length };
			})
			.filter((r): r is NonNullable<typeof r> => r !== null)
			.sort((a, b) => a.std - b.std);
		if (rows.length < 3) return null;
		const maxStd = Math.max(0.01, ...rows.map((r) => r.std));
		return rows.map((r) => ({ ...r, barPct: (r.std / maxStd) * 100 }));
	});

	const windowParticipationTrend = $derived.by(() => {
		const pts = allWindows
			.map((w) => {
				const count = byStrategy.filter(
					({ windows }) => windows[w]?.status === 'ok' && windows[w]?.tot_profit_pct != null
				).length;
				return { w, count };
			})
			.filter((p) => p.count > 0);
		if (pts.length < 4) return null;
		const W = 560,
			H = 64,
			PAD = 8;
		const maxCount = Math.max(1, ...pts.map((p) => p.count));
		const toX = (i: number) => PAD + (i / Math.max(1, pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - (v / maxCount) * (H - PAD * 2);
		const polyline = pts.map((p, i) => `${toX(i).toFixed(1)},${toY(p.count).toFixed(1)}`).join(' ');
		const recent =
			pts
				.slice(-3)
				.map((p) => p.count)
				.reduce((a, b) => a + b, 0) / 3;
		const early =
			pts
				.slice(0, 3)
				.map((p) => p.count)
				.reduce((a, b) => a + b, 0) / 3;
		return { polyline, W, H, PAD, maxCount, pts, growing: recent > early + 1 };
	});

	const windowTopStrategyProfit = $derived.by(() => {
		const wins = new Map<string, { best: number; bestStrat: string }>();
		for (const r of data.results) {
			if (r.tot_profit_pct == null || !isFinite(r.tot_profit_pct)) continue;
			const cur = wins.get(r.window_label);
			if (!cur || r.tot_profit_pct > cur.best) {
				wins.set(r.window_label, { best: r.tot_profit_pct, bestStrat: r.strategy });
			}
		}
		if (wins.size < 3) return null;
		const rows = Array.from(wins.entries())
			.map(([wl, v]) => ({ wl, best: v.best, bestStrat: v.bestStrat }))
			.sort((a, b) => a.wl.localeCompare(b.wl));
		const maxBest = Math.max(...rows.map((r) => Math.abs(r.best)), 1);
		return rows.map((r) => ({
			...r,
			barPct: (Math.abs(r.best) / maxBest) * 100,
			positive: r.best >= 0
		}));
	});

	const strategyConsistencyScore = $derived.by(() => {
		const map = new Map<string, { profitable: number; total: number }>();
		for (const r of data.results) {
			if (!map.has(r.strategy)) map.set(r.strategy, { profitable: 0, total: 0 });
			const e = map.get(r.strategy)!;
			e.total++;
			if ((r.tot_profit_pct ?? 0) > 0) e.profitable++;
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.total >= 3)
			.map(([s, v]) => ({
				strategy: s,
				score: v.profitable / v.total,
				profitable: v.profitable,
				total: v.total
			}))
			.sort((a, b) => b.score - a.score)
			.slice(0, 12);
		if (rows.length < 3) return null;
		return rows;
	});

	const strategyAvgTradesRanking = $derived.by(() => {
		const map = new Map<string, { totalTrades: number; windows: number }>();
		for (const r of data.results) {
			if (r.trades == null || !isFinite(r.trades)) continue;
			if (!map.has(r.strategy)) map.set(r.strategy, { totalTrades: 0, windows: 0 });
			const e = map.get(r.strategy)!;
			e.totalTrades += r.trades;
			e.windows++;
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.windows >= 2)
			.map(([s, v]) => ({ strategy: s, avg: v.totalTrades / v.windows, windows: v.windows }))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxAvg = Math.max(0.01, ...rows.map((r) => r.avg));
		return rows.map((r) => ({ ...r, barPct: (r.avg / maxAvg) * 100 }));
	});

	const strategyWinWindowRatio = $derived.by(() => {
		const map = new Map<string, { wins: number; total: number }>();
		for (const r of data.results) {
			if (!r.strategy) continue;
			if (!map.has(r.strategy)) map.set(r.strategy, { wins: 0, total: 0 });
			const e = map.get(r.strategy)!;
			e.total++;
			if ((r.tot_profit_pct ?? 0) > 0) e.wins++;
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.total >= 3)
			.map(([strategy, v]) => ({
				strategy,
				winRatio: v.wins / v.total,
				wins: v.wins,
				total: v.total
			}))
			.sort((a, b) => b.winRatio - a.winRatio)
			.slice(0, 12);
		if (rows.length < 3) return null;
		return rows.map((r) => ({ ...r, barPct: r.winRatio * 100 }));
	});

	const windowAvgProfitTimeline = $derived.by(() => {
		const map = new Map<string, { sum: number; count: number }>();
		for (const r of data.results) {
			if (!r.window_label || r.tot_profit_pct == null || !isFinite(r.tot_profit_pct)) continue;
			if (!map.has(r.window_label)) map.set(r.window_label, { sum: 0, count: 0 });
			const e = map.get(r.window_label)!;
			e.sum += r.tot_profit_pct;
			e.count++;
		}
		if (map.size < 3) return null;
		const rows = [...map.entries()]
			.map(([wl, v]) => ({ wl, avg: v.sum / v.count, count: v.count }))
			.sort((a, b) => a.wl.localeCompare(b.wl));
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.avg)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.avg) / maxAbs) * 100 }));
	});

	const strategyBestSingleWindow = $derived.by(() => {
		const map = new Map<string, { best: number; windows: number }>();
		for (const r of data.results) {
			if (!r.strategy || r.tot_profit_pct == null || !isFinite(r.tot_profit_pct)) continue;
			const e = map.get(r.strategy);
			if (!e) map.set(r.strategy, { best: r.tot_profit_pct, windows: 1 });
			else {
				e.best = Math.max(e.best, r.tot_profit_pct);
				e.windows++;
			}
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.windows >= 2)
			.map(([strategy, v]) => ({ strategy, best: v.best, windows: v.windows }))
			.sort((a, b) => b.best - a.best)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxBest = Math.max(0.01, ...rows.map((r) => Math.abs(r.best)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.best) / maxBest) * 100 }));
	});

	const windowLoserCount = $derived.by(() => {
		const map = new Map<string, { losers: number; total: number }>();
		for (const r of data.results) {
			if (!map.has(r.window_label)) map.set(r.window_label, { losers: 0, total: 0 });
			const e = map.get(r.window_label)!;
			e.total++;
			if ((r.tot_profit_pct ?? 0) < 0) e.losers++;
		}
		if (map.size < 3) return null;
		const rows = [...map.entries()]
			.map(([wl, v]) => ({ wl, losers: v.losers, total: v.total, loserPct: v.losers / v.total }))
			.sort((a, b) => a.wl.localeCompare(b.wl));
		const maxLosers = Math.max(1, ...rows.map((r) => r.losers));
		return rows.map((r) => ({ ...r, barPct: (r.losers / maxLosers) * 100 }));
	});

	const strategyAvgProfitPerTrade = $derived.by(() => {
		const map = new Map<string, { sumProfit: number; sumTrades: number; windows: number }>();
		for (const r of data.results) {
			if (
				r.tot_profit_pct == null ||
				!isFinite(r.tot_profit_pct) ||
				r.trades == null ||
				r.trades < 1
			)
				continue;
			if (!map.has(r.strategy)) map.set(r.strategy, { sumProfit: 0, sumTrades: 0, windows: 0 });
			const e = map.get(r.strategy)!;
			e.sumProfit += r.tot_profit_pct;
			e.sumTrades += r.trades;
			e.windows++;
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.sumTrades >= 5 && v.windows >= 2)
			.map(([strat, v]) => ({
				strat,
				avgPpt: v.sumProfit / v.sumTrades,
				trades: v.sumTrades,
				windows: v.windows
			}))
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

	const windowTotalProfitDistribution = $derived.by(() => {
		const vals = data.results
			.filter((r) => r.tot_profit_pct != null && isFinite(r.tot_profit_pct))
			.map((r) => r.tot_profit_pct!);
		if (vals.length < 10) return null;
		const mn = Math.min(...vals),
			mx = Math.max(...vals);
		const range = mx - mn || 1;
		const BINS = 8,
			step = range / BINS;
		const buckets = Array.from({ length: BINS }, (_, i) => ({
			lo: mn + i * step,
			hi: mn + (i + 1) * step,
			label: `${(mn + i * step).toFixed(0)}%`,
			count: 0
		}));
		for (const v of vals) {
			const idx = Math.min(BINS - 1, Math.floor((v - mn) / step));
			buckets[idx].count++;
		}
		const maxCount = Math.max(1, ...buckets.map((b) => b.count));
		const sorted = [...vals].sort((a, b) => a - b);
		const median = sorted[Math.floor(sorted.length / 2)];
		const positive = vals.filter((v) => v > 0).length;
		return {
			buckets: buckets.map((b) => ({ ...b, barPct: (b.count / maxCount) * 100, pos: b.lo >= 0 })),
			median,
			total: vals.length,
			positive
		};
	});

	const windowStrategyCount = $derived.by(() => {
		const map = new Map<string, Set<string>>();
		for (const r of data.results) {
			if (!map.has(r.window_label)) map.set(r.window_label, new Set());
			map.get(r.window_label)!.add(r.strategy);
		}
		if (map.size < 3) return null;
		const rows = [...map.entries()]
			.map(([wl, strats]) => ({ wl, count: strats.size }))
			.sort((a, b) => a.wl.localeCompare(b.wl));
		const maxCount = Math.max(1, ...rows.map((r) => r.count));
		return rows.map((r) => ({ ...r, barPct: (r.count / maxCount) * 100 }));
	});

	const strategyTimeframeWinWindowPct = $derived.by(() => {
		const map = new Map<string, Map<string, { wins: number; total: number }>>();
		for (const r of data.results) {
			if (!r.strategy || !r.timeframe || r.tot_profit_pct == null || !isFinite(r.tot_profit_pct))
				continue;
			if (!map.has(r.strategy)) map.set(r.strategy, new Map());
			const tm = map.get(r.strategy)!;
			if (!tm.has(r.timeframe)) tm.set(r.timeframe, { wins: 0, total: 0 });
			const e = tm.get(r.timeframe)!;
			e.total++;
			if (r.tot_profit_pct > 0) e.wins++;
		}
		const TF_ORDER = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d'];
		const timeframes = [
			...new Set(data.results.map((r) => r.timeframe).filter(Boolean))
		] as string[];
		const sortedTf = timeframes.sort((a, b) => {
			const ai = TF_ORDER.indexOf(a),
				bi = TF_ORDER.indexOf(b);
			return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
		});
		const strategies = [...map.entries()]
			.filter(([, tm]) => [...tm.values()].some((v) => v.total >= 3))
			.map(([s]) => s)
			.slice(0, 10);
		if (strategies.length < 2 || sortedTf.length < 2) return null;
		const cells = strategies.map((s) => ({
			strategy: s,
			tfs: sortedTf.map((tf) => {
				const e = map.get(s)?.get(tf);
				if (!e || e.total < 3) return { tf, wr: null, total: 0 };
				return { tf, wr: e.wins / e.total, total: e.total };
			})
		}));
		return { cells, timeframes: sortedTf };
	});

	const windowProfitByTimeframe = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const r of data.results) {
			if (!r.timeframe || r.tot_profit_pct == null || !isFinite(r.tot_profit_pct)) continue;
			if (!map.has(r.timeframe)) map.set(r.timeframe, []);
			map.get(r.timeframe)!.push(r.tot_profit_pct);
		}
		const TF_ORDER = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d'];
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 5)
			.map(([tf, vals]) => {
				const avg = vals.reduce((s, v) => s + v, 0) / vals.length;
				const positive = vals.filter((v) => v > 0).length;
				return { tf, avg, count: vals.length, winPct: positive / vals.length };
			})
			.sort((a, b) => {
				const ai = TF_ORDER.indexOf(a.tf),
					bi = TF_ORDER.indexOf(b.tf);
				return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
			});
		if (rows.length < 2) return null;
		const absMax = Math.max(0.01, ...rows.map((r) => Math.abs(r.avg)));
		return rows.map((r) => ({
			...r,
			barPct: (Math.abs(r.avg) / absMax) * 100,
			positive: r.avg > 0
		}));
	});

	const windowStrategyProfitRanking = $derived.by(() => {
		const map = new Map<string, { sum: number; wins: number; total: number }>();
		for (const r of data.results) {
			if (!r.strategy || r.tot_profit_pct == null || !isFinite(r.tot_profit_pct)) continue;
			if (!map.has(r.strategy)) map.set(r.strategy, { sum: 0, wins: 0, total: 0 });
			const e = map.get(r.strategy)!;
			e.sum += r.tot_profit_pct;
			e.total++;
			if (r.tot_profit_pct > 0) e.wins++;
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.total >= 3)
			.map(([strategy, v]) => ({
				strategy,
				total: v.sum,
				avg: v.sum / v.total,
				wr: v.wins / v.total,
				count: v.total
			}))
			.sort((a, b) => b.total - a.total)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const absMax = Math.max(0.01, ...rows.map((r) => Math.abs(r.total)));
		return rows.map((r) => ({
			...r,
			barPct: (Math.abs(r.total) / absMax) * 100,
			positive: r.total >= 0
		}));
	});

	// Avg profit across all strategies per window label (walk-forward time progression)
	const windowLabelProfitTimeline = $derived.by(() => {
		const map = new Map<string, { sum: number; count: number; wins: number }>();
		for (const r of data.results) {
			if (!r.window_label || r.tot_profit_pct == null || !isFinite(r.tot_profit_pct)) continue;
			if (!map.has(r.window_label)) map.set(r.window_label, { sum: 0, count: 0, wins: 0 });
			const e = map.get(r.window_label)!;
			e.sum += r.tot_profit_pct;
			e.count++;
			if (r.tot_profit_pct > 0) e.wins++;
		}
		const labels = [...map.keys()].sort().slice(-20);
		if (labels.length < 4) return null;
		const rows = labels.map((lbl) => {
			const e = map.get(lbl)!;
			return { lbl, avg: e.sum / e.count, wr: e.wins / e.count, count: e.count };
		});
		const vals = rows.map((r) => r.avg);
		const vMin = Math.min(...vals),
			vMax = Math.max(...vals);
		const W = 520,
			H = 80,
			PAD = 8;
		const toX = (i: number) => PAD + (i / Math.max(1, rows.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - vMin) / (vMax - vMin || 0.001)) * (H - PAD * 2);
		const poly = rows.map((r, i) => `${toX(i).toFixed(1)},${toY(r.avg).toFixed(1)}`).join(' ');
		const zeroY = toY(0);
		return { rows, poly, W, H, PAD, zeroY, first: labels[0], last: labels[labels.length - 1] };
	});

	// Worst single WF window per strategy — maximum downside risk profile
	const strategyWorstWindowLoss = $derived.by(() => {
		const map = new Map<string, { worst: number; worstLabel: string; count: number }>();
		for (const r of data.results) {
			if (!r.strategy || r.tot_profit_pct == null || !isFinite(r.tot_profit_pct)) continue;
			if (!map.has(r.strategy)) map.set(r.strategy, { worst: 0, worstLabel: '', count: 0 });
			const e = map.get(r.strategy)!;
			e.count++;
			if (r.tot_profit_pct < e.worst) {
				e.worst = r.tot_profit_pct;
				e.worstLabel = r.window_label ?? '';
			}
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.count >= 2 && v.worst < 0)
			.map(([strategy, v]) => ({
				strategy,
				worst: v.worst,
				worstLabel: v.worstLabel,
				count: v.count
			}))
			.sort((a, b) => b.worst - a.worst)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxLoss = Math.max(0.01, ...rows.map((r) => Math.abs(r.worst)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.worst) / maxLoss) * 100 }));
	});

	const strategyConsecutiveLossWindows = $derived.by(() => {
		const strats = [...new Set(data.results.map((r) => r.strategy).filter(Boolean))];
		if (strats.length < 2) return null;
		const rows = strats
			.map((strategy) => {
				const windows = data.results
					.filter(
						(r) =>
							r.strategy === strategy &&
							r.window_label &&
							r.tot_profit_pct != null &&
							isFinite(r.tot_profit_pct)
					)
					.sort((a, b) => (a.window_label ?? '').localeCompare(b.window_label ?? ''));
				if (windows.length < 3) return null;
				let maxStreak = 0,
					streak = 0;
				for (const w of windows) {
					if (w.tot_profit_pct! < 0) {
						streak++;
						if (streak > maxStreak) maxStreak = streak;
					} else streak = 0;
				}
				return { strategy, maxStreak, total: windows.length };
			})
			.filter((r): r is NonNullable<typeof r> => r !== null && r.maxStreak > 0)
			.sort((a, b) => b.maxStreak - a.maxStreak)
			.slice(0, 12);
		if (rows.length < 2) return null;
		const maxS = Math.max(1, ...rows.map((r) => r.maxStreak));
		return rows.map((r) => ({ ...r, barPct: (r.maxStreak / maxS) * 100 }));
	});

	const windowCumulativeProfitByStrategy = $derived.by(() => {
		const strats = [...new Set(data.results.map((r) => r.strategy).filter(Boolean))];
		if (strats.length < 2) return null;
		const allLabels = [
			...new Set(data.results.map((r) => r.window_label).filter(Boolean))
		].sort() as string[];
		if (allLabels.length < 3) return null;
		const COLORS = [
			'var(--ch-profit-strong)',
			'var(--ch-violet-strong)',
			'var(--ch-warn)',
			'var(--ch-loss)',
			'var(--ch-teal-strong)'
		];
		const W = 200,
			H = 50,
			PAD = 4;
		const lines = strats
			.slice(0, 5)
			.map((strategy, si) => {
				const byLabel = new Map(
					data.results
						.filter((r) => r.strategy === strategy && r.window_label && r.tot_profit_pct != null)
						.map((r) => [r.window_label!, r.tot_profit_pct!])
				);
				let cum = 0;
				const pts = allLabels.map((l) => {
					cum += byLabel.get(l) ?? 0;
					return cum;
				});
				return { strategy, pts, color: COLORS[si % COLORS.length], final: pts[pts.length - 1] };
			})
			.sort((a, b) => b.final - a.final);
		const allPts = lines.flatMap((l) => l.pts);
		const mn = Math.min(0, ...allPts),
			mx = Math.max(0.01, ...allPts);
		const range = mx - mn || 1;
		const toX = (i: number) => PAD + (i / Math.max(1, allLabels.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / range) * (H - PAD * 2);
		const zeroY = toY(0);
		const polylines = lines.map((l) => ({
			...l,
			poly: l.pts.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ')
		}));
		return { W, H, polylines, zeroY };
	});

	const windowProfitConcentration = $derived.by(() => {
		const labels = [
			...new Set(wfRows.map((r) => r.window_label).filter(Boolean))
		].sort() as string[];
		if (labels.length < 3) return null;
		const rows = labels
			.map((label) => {
				const wins = wfRows.filter(
					(r) => r.window_label === label && r.tot_profit_pct != null && isFinite(r.tot_profit_pct)
				);
				if (wins.length < 2) return null;
				const total = wins.reduce((s, r) => s + r.tot_profit_pct!, 0);
				const positives = wins.filter((r) => r.tot_profit_pct! > 0);
				if (positives.length === 0)
					return { label, topShare: 0, topStrategy: '—', total, count: wins.length };
				const best = positives.reduce((a, b) => (b.tot_profit_pct! > a.tot_profit_pct! ? b : a));
				const posTotal = positives.reduce((s, r) => s + r.tot_profit_pct!, 0);
				const topShare = posTotal > 0 ? (best.tot_profit_pct! / posTotal) * 100 : 0;
				return { label, topShare, topStrategy: best.strategy, total, count: wins.length };
			})
			.filter((r): r is NonNullable<typeof r> => r !== null);
		if (rows.length < 3) return null;
		const maxShare = Math.max(0.01, ...rows.map((r) => r.topShare));
		return rows.map((r) => ({ ...r, barPct: (r.topShare / maxShare) * 100 }));
	});

	const strategyAvgProfitTrend = $derived.by(() => {
		const stratMap: Record<string, { idx: number; profit: number }[]> = {};
		const windowLabels = [...new Set(wfRows.map((w) => w.window_label))].sort();
		for (const w of wfRows) {
			if (w.avg_profit_pct == null || !isFinite(w.avg_profit_pct)) continue;
			const idx = windowLabels.indexOf(w.window_label);
			if (!stratMap[w.strategy]) stratMap[w.strategy] = [];
			stratMap[w.strategy].push({ idx, profit: w.avg_profit_pct });
		}
		const rows = Object.entries(stratMap)
			.filter(([, pts]) => pts.length >= 3)
			.map(([strategy, pts]) => {
				const sorted = pts.sort((a, b) => a.idx - b.idx);
				const n = sorted.length;
				const sumX = sorted.reduce((s, p) => s + p.idx, 0);
				const sumY = sorted.reduce((s, p) => s + p.profit, 0);
				const sumXY = sorted.reduce((s, p) => s + p.idx * p.profit, 0);
				const sumXX = sorted.reduce((s, p) => s + p.idx * p.idx, 0);
				const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX || 1);
				const avgProfit = sumY / n;
				return { strategy, slope, avgProfit, count: n };
			})
			.sort((a, b) => b.slope - a.slope)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxSlope = Math.max(0.001, ...rows.map((r) => Math.abs(r.slope)));
		return { rows, maxSlope };
	});

	const windowMedianTradeTimeline = $derived.by(() => {
		const windowLabels = [...new Set(wfRows.map((w) => w.window_label))].sort();
		if (windowLabels.length < 3) return null;
		const pts = windowLabels
			.map((label) => {
				const wins = wfRows.filter(
					(w) => w.window_label === label && w.trades != null && isFinite(w.trades)
				);
				if (wins.length === 0) return null;
				const sorted = wins.map((w) => w.trades!).sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const median = sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
				return { label, median, count: wins.length };
			})
			.filter((p): p is NonNullable<typeof p> => p !== null);
		if (pts.length < 3) return null;
		const vals = pts.map((p) => p.median);
		const mn = Math.min(...vals),
			mx = Math.max(...vals, mn + 0.01);
		const W = 560,
			H = 72,
			PAD = 8;
		const toX = (i: number) => PAD + (i / Math.max(1, pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / (mx - mn)) * (H - PAD * 2);
		const polyline = pts
			.map((p, i) => `${toX(i).toFixed(1)},${toY(p.median).toFixed(1)}`)
			.join(' ');
		const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
		const avgY = toY(avg);
		const trend = vals[vals.length - 1] - vals[0];
		return { W, H, polyline, avg, avgY, trend, latest: vals[vals.length - 1], count: pts.length };
	});

	const windowNetProfitVsParticipation = $derived.by(() => {
		const windowLabels = [...new Set(wfRows.map((w) => w.window_label))];
		const pts = windowLabels
			.map((label) => {
				const wins = wfRows.filter((w) => w.window_label === label);
				const participation = wins.length;
				const netProfit = wins.reduce((s, w) => s + (w.tot_profit_pct ?? 0), 0);
				return { label, participation, netProfit };
			})
			.filter((p) => p.participation > 0);
		if (pts.length < 4) return null;
		const xMin = Math.min(...pts.map((p) => p.participation)),
			xMax = Math.max(...pts.map((p) => p.participation), xMin + 1);
		const yMin = Math.min(...pts.map((p) => p.netProfit)),
			yMax = Math.max(...pts.map((p) => p.netProfit), yMin + 0.01);
		const W = 560,
			H = 130,
			PAD = 10;
		const toX = (x: number) => PAD + ((x - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (y: number) => H - PAD - ((y - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const zeroY = yMin < 0 && yMax > 0 ? toY(0) : null;
		const dots = pts.map((p) => ({
			cx: toX(p.participation),
			cy: toY(p.netProfit),
			positive: p.netProfit >= 0
		}));
		return {
			W,
			H,
			dots,
			zeroY,
			xMin,
			xMax,
			yMin: yMin.toFixed(1),
			yMax: yMax.toFixed(1),
			total: pts.length
		};
	});

	const windowAvgProfitByStrategy = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const w of wfRows) {
			if (!w.strategy || w.tot_profit_pct == null || !isFinite(w.tot_profit_pct)) continue;
			if (!map[w.strategy]) map[w.strategy] = [];
			map[w.strategy].push(w.tot_profit_pct);
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.length >= 2)
			.map(([strategy, vals]) => {
				const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
				return { strategy, avg, count: vals.length };
			})
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		return { rows, maxAbs };
	});

	const windowTradeCountByStrategy = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const w of wfRows) {
			if (!w.strategy || w.trades == null || w.trades <= 0) continue;
			if (!map[w.strategy]) map[w.strategy] = [];
			map[w.strategy].push(w.trades);
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.length >= 2)
			.map(([strategy, vals]) => ({
				strategy,
				avg: vals.reduce((a, b) => a + b, 0) / vals.length,
				total: vals.reduce((a, b) => a + b, 0),
				count: vals.length
			}))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxAvg = Math.max(...rows.map((r) => r.avg), 1);
		return { rows, maxAvg };
	});

	const windowStatusBreakdown = $derived.by(() => {
		const map: Record<string, { win: number; loss: number; flat: number }> = {};
		for (const w of wfRows) {
			if (!w.strategy || w.tot_profit_pct == null) continue;
			if (!map[w.strategy]) map[w.strategy] = { win: 0, loss: 0, flat: 0 };
			if (w.tot_profit_pct > 0.1) map[w.strategy].win++;
			else if (w.tot_profit_pct < -0.1) map[w.strategy].loss++;
			else map[w.strategy].flat++;
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.win + v.loss + v.flat >= 3)
			.map(([strategy, v]) => {
				const total = v.win + v.loss + v.flat;
				return {
					strategy,
					win: v.win,
					loss: v.loss,
					flat: v.flat,
					total,
					winPct: (v.win / total) * 100
				};
			})
			.sort((a, b) => b.winPct - a.winPct)
			.slice(0, 12);
		if (rows.length < 3) return null;
		return { rows };
	});

	const windowProfitVolatilityByStrategy = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const w of wfRows) {
			if (!w.strategy || w.tot_profit_pct == null || !isFinite(w.tot_profit_pct)) continue;
			if (!map[w.strategy]) map[w.strategy] = [];
			map[w.strategy].push(w.tot_profit_pct);
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.length >= 4)
			.map(([strategy, vals]) => {
				const n = vals.length;
				const mean = vals.reduce((a, b) => a + b, 0) / n;
				const variance = vals.reduce((s, v) => s + (v - mean) ** 2, 0) / n;
				const std = Math.sqrt(variance);
				return { strategy, mean, std, count: n, cv: mean !== 0 ? std / Math.abs(mean) : Infinity };
			})
			.filter((r) => isFinite(r.std) && isFinite(r.cv))
			.sort((a, b) => a.cv - b.cv)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxStd = Math.max(...rows.map((r) => r.std), 0.01);
		const maxMeanAbs = Math.max(...rows.map((r) => Math.abs(r.mean)), 0.01);
		return { rows, maxStd, maxMeanAbs };
	});

	const windowTimeframeWinRate = $derived.by(() => {
		const TF_ORDER = ['5m', '15m', '1h', '4h', '1d'];
		const map: Record<string, { wins: number; total: number }> = {};
		for (const w of wfRows) {
			if (!w.timeframe || w.tot_profit_pct == null) continue;
			if (!map[w.timeframe]) map[w.timeframe] = { wins: 0, total: 0 };
			map[w.timeframe].total++;
			if (w.tot_profit_pct > 0.1) map[w.timeframe].wins++;
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.total >= 3)
			.map(([tf, v]) => ({ tf, winRate: (v.wins / v.total) * 100, wins: v.wins, total: v.total }))
			.sort((a, b) => {
				const ai = TF_ORDER.indexOf(a.tf),
					bi = TF_ORDER.indexOf(b.tf);
				return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
			});
		if (rows.length < 2) return null;
		const W = 400,
			H = 80,
			PAD = 10,
			BAR_W = Math.min(50, Math.floor((W - PAD * 2) / rows.length) - 4);
		return { rows, W, H, PAD, BAR_W };
	});

	const windowBestWorstByStrategy = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const w of wfRows) {
			if (!w.strategy || w.tot_profit_pct == null || !isFinite(w.tot_profit_pct)) continue;
			if (!map[w.strategy]) map[w.strategy] = [];
			map[w.strategy].push(w.tot_profit_pct);
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.length >= 3)
			.map(([strategy, vals]) => ({
				strategy,
				best: Math.max(...vals),
				worst: Math.min(...vals),
				count: vals.length
			}))
			.sort((a, b) => b.best - a.best)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(...rows.flatMap((r) => [Math.abs(r.best), Math.abs(r.worst)]), 0.01);
		return { rows, maxAbs };
	});

	const windowStatusBreakdownByStrategy = $derived.by(() => {
		const map: Record<string, { pass: number; fail: number; total: number }> = {};
		for (const w of wfRows) {
			if (!w.strategy) continue;
			if (!map[w.strategy]) map[w.strategy] = { pass: 0, fail: 0, total: 0 };
			map[w.strategy].total++;
			if (w.status === 'pass') map[w.strategy].pass++;
			else map[w.strategy].fail++;
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.total >= 2)
			.map(([strategy, v]) => ({
				strategy: strategy.slice(0, 20),
				passRate: (v.pass / v.total) * 100,
				pass: v.pass,
				fail: v.fail,
				total: v.total
			}))
			.sort((a, b) => b.passRate - a.passRate)
			.slice(0, 12);
		if (rows.length < 2) return null;
		return { rows };
	});

	const windowAvgProfitByTimeframe = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const w of wfRows) {
			if (!w.timeframe || w.avg_profit_pct == null || !isFinite(w.avg_profit_pct)) continue;
			if (!map[w.timeframe]) map[w.timeframe] = [];
			map[w.timeframe].push(w.avg_profit_pct);
		}
		const TF_ORDER = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d'];
		const rows = Object.entries(map)
			.filter(([, v]) => v.length >= 2)
			.map(([tf, vals]) => {
				const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
				const pos = vals.filter((v) => v >= 0).length;
				return { tf, avg, passRate: (pos / vals.length) * 100, count: vals.length };
			})
			.sort(
				(a, b) =>
					(TF_ORDER.indexOf(a.tf) === -1 ? 99 : TF_ORDER.indexOf(a.tf)) -
					(TF_ORDER.indexOf(b.tf) === -1 ? 99 : TF_ORDER.indexOf(b.tf))
			);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 440,
			H = 80,
			PAD = 8,
			barW = Math.min(60, Math.floor((W - PAD * 2) / rows.length) - 3);
		return { rows, maxAbs, W, H, PAD, barW };
	});

	const windowTotalTradesByStrategy = $derived.by(() => {
		const map: Record<string, number> = {};
		for (const w of wfRows) {
			if (!w.strategy || w.trades == null) continue;
			map[w.strategy] = (map[w.strategy] ?? 0) + w.trades;
		}
		const rows = Object.entries(map)
			.map(([strategy, trades]) => ({ strategy: strategy.slice(0, 22), trades }))
			.sort((a, b) => b.trades - a.trades)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxTrades = Math.max(...rows.map((r) => r.trades), 1);
		return { rows, maxTrades };
	});

	const windowProfitSpreadByStrategy = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const w of results) {
			if (!w.strategy || w.avg_profit_pct == null) continue;
			if (!map[w.strategy]) map[w.strategy] = [];
			map[w.strategy].push(w.avg_profit_pct);
		}
		const rows = Object.entries(map)
			.filter(([, vals]) => vals.length >= 2)
			.map(([strategy, vals]) => {
				const mn = Math.min(...vals),
					mx = Math.max(...vals),
					med = vals.sort((a, b) => a - b)[Math.floor(vals.length / 2)];
				return { strategy: strategy.slice(0, 20), mn, mx, med, spread: mx - mn };
			})
			.sort((a, b) => b.spread - a.spread)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const globalMin = Math.min(...rows.map((r) => r.mn));
		const globalMax = Math.max(...rows.map((r) => r.mx));
		const range = globalMax - globalMin || 1;
		const W = 400,
			H = rows.length * 16 + 20,
			PAD = 8,
			trackW = W - PAD * 2 - 90;
		const xs = (v: number) => PAD + 90 + ((v - globalMin) / range) * trackW;
		return { rows, W, H, PAD, xs, globalMin, globalMax };
	});

	const windowPassRateByTimeframe = $derived.by(() => {
		const map: Record<string, { pass: number; total: number }> = {};
		for (const w of results) {
			if (!w.timeframe) continue;
			if (!map[w.timeframe]) map[w.timeframe] = { pass: 0, total: 0 };
			map[w.timeframe].total++;
			if (w.status === 'pass') map[w.timeframe].pass++;
		}
		const TF_ORD = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '8h', '1d'];
		const rows = Object.entries(map)
			.map(([tf, v]) => ({
				tf,
				rate: v.total > 0 ? (v.pass / v.total) * 100 : 0,
				pass: v.pass,
				total: v.total
			}))
			.sort(
				(a, b) =>
					(TF_ORD.indexOf(a.tf) === -1 ? 99 : TF_ORD.indexOf(a.tf)) -
					(TF_ORD.indexOf(b.tf) === -1 ? 99 : TF_ORD.indexOf(b.tf))
			);
		if (rows.length < 2) return null;
		const W = 400,
			H = 80,
			PAD = 8,
			barW = Math.min(55, Math.floor((W - PAD * 2) / rows.length) - 3);
		return { rows, W, H, PAD, barW };
	});

	const windowAvgProfitHistogram = $derived.by(() => {
		const vals = results
			.filter((w) => w.avg_profit_pct != null && isFinite(w.avg_profit_pct))
			.map((w) => w.avg_profit_pct!);
		if (vals.length < 5) return null;
		const mn = Math.min(...vals),
			mx = Math.max(...vals);
		const bins = 12,
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
		const W = 380,
			H = 72,
			PAD = 8,
			barW = Math.floor((W - PAD * 2) / bins) - 1;
		const avg = (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2);
		return {
			counts,
			maxCount,
			W,
			H,
			PAD,
			barW,
			mn: mn.toFixed(2),
			mx: mx.toFixed(2),
			avg,
			total: vals.length
		};
	});

	const windowProfitByWindowLabel = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const w of wfRows) {
			if (!w.window_label || w.tot_profit_pct == null || !isFinite(w.tot_profit_pct)) continue;
			if (!map[w.window_label]) map[w.window_label] = [];
			map[w.window_label].push(w.tot_profit_pct);
		}
		const rows = Object.entries(map)
			.map(([label, vals]) => ({
				label: label.replace(/^W\d+_/, '').slice(0, 10),
				avg: vals.reduce((a, b) => a + b, 0) / vals.length,
				count: vals.length
			}))
			.sort((a, b) => a.label.localeCompare(b.label));
		if (rows.length < 3) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 400,
			H = 80,
			PAD = 10,
			barW = Math.max(8, Math.floor((W - PAD * 2) / rows.length) - 2);
		const midY = H / 2;
		const toH = (v: number) => (Math.abs(v) / maxAbs) * (H / 2 - PAD);
		return { rows, maxAbs, W, H, PAD, barW, midY, toH };
	});

	const windowTradesByWindowLabel = $derived.by(() => {
		const map: Record<string, number> = {};
		for (const w of wfRows) {
			if (!w.window_label || w.trades == null) continue;
			map[w.window_label] = (map[w.window_label] ?? 0) + w.trades;
		}
		const rows = Object.entries(map)
			.map(([label, trades]) => ({ label: label.replace(/^W\d+_/, '').slice(0, 10), trades }))
			.sort((a, b) => a.label.localeCompare(b.label));
		if (rows.length < 3) return null;
		const maxTrades = Math.max(...rows.map((r) => r.trades), 1);
		const W = 400,
			H = 72,
			PAD = 8,
			barW = Math.max(8, Math.floor((W - PAD * 2) / rows.length) - 2);
		return { rows, maxTrades, W, H, PAD, barW };
	});

	const windowStrategyPassRate = $derived.by(() => {
		const map = new Map<string, { pass: number; total: number }>();
		for (const w of wfRows) {
			if (!w.strategy) continue;
			if (!map.has(w.strategy)) map.set(w.strategy, { pass: 0, total: 0 });
			const e = map.get(w.strategy)!;
			e.total++;
			if (w.tot_profit_pct != null && w.tot_profit_pct > 0) e.pass++;
		}
		const rows = [...map.entries()]
			.filter(([, e]) => e.total >= 3)
			.map(([strategy, e]) => ({
				strategy: strategy.slice(0, 20),
				rate: (e.pass / e.total) * 100,
				pass: e.pass,
				total: e.total
			}))
			.sort((a, b) => b.rate - a.rate)
			.slice(0, 12);
		if (rows.length < 2) return null;
		return { rows };
	});

	const windowProfitVsTradeCount = $derived.by(() => {
		const pts = wfRows
			.filter(
				(w) =>
					w.tot_profit_pct != null && isFinite(w.tot_profit_pct) && w.trades != null && w.trades > 0
			)
			.map((w) => ({
				profit: w.tot_profit_pct!,
				trades: w.trades!,
				strategy: (w.strategy ?? '').slice(0, 10)
			}));
		if (pts.length < 5) return null;
		const pMin = Math.min(...pts.map((p) => p.profit)),
			pMax = Math.max(...pts.map((p) => p.profit), pMin + 0.01);
		const tMax = Math.max(...pts.map((p) => p.trades), 1);
		const W = 380,
			H = 100,
			PAD = 12;
		const toX = (v: number) => PAD + (v / tMax) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - pMin) / (pMax - pMin)) * (H - PAD * 2);
		const zeroY = Math.max(PAD, Math.min(H - PAD, toY(0)));
		const dots = pts.map((p) => ({
			cx: toX(p.trades),
			cy: toY(p.profit),
			color: p.profit >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss-light)'
		}));
		return {
			dots,
			W,
			H,
			PAD,
			zeroY,
			tMax,
			pMin: pMin.toFixed(1),
			pMax: pMax.toFixed(1),
			count: pts.length
		};
	});

	const windowProfitCumulativeByStrategy = $derived.by(() => {
		const map = new Map<string, { label: string; profit: number }[]>();
		for (const w of wfRows) {
			if (!w.strategy || !w.window_label || w.tot_profit_pct == null || !isFinite(w.tot_profit_pct))
				continue;
			if (!map.has(w.strategy)) map.set(w.strategy, []);
			map.get(w.strategy)!.push({ label: w.window_label, profit: w.tot_profit_pct });
		}
		const strats = [...map.entries()].filter(([, pts]) => pts.length >= 3).slice(0, 5);
		if (strats.length < 2) return null;
		const colors = [
			'var(--ch-profit-strong)',
			'var(--ch-violet-strong)',
			'var(--ch-warn)',
			'var(--ch-warn)',
			'var(--ch-loss-strong)'
		];
		const lines = strats.map(([strat, pts], bi) => {
			const sorted = [...pts].sort((a, b) => a.label.localeCompare(b.label));
			let cum = 0;
			const cumPts = sorted.map((p, i) => {
				cum += p.profit;
				return { i, cum };
			});
			return { strat: strat.slice(0, 14), color: colors[bi], pts: cumPts, windows: sorted.length };
		});
		const allCum = lines.flatMap((l) => l.pts.map((p) => p.cum));
		const mnC = Math.min(...allCum, 0),
			mxC = Math.max(...allCum, 0.01);
		const W = 400,
			H = 90,
			PAD = 12;
		const toX = (i: number, n: number) => PAD + (i / Math.max(n - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - mnC) / (mxC - mnC)) * (H - PAD * 2);
		const zeroY = Math.max(PAD, Math.min(H - PAD, toY(0)));
		const polylines = lines.map((l) => ({
			...l,
			poly: l.pts.map((p) => `${toX(p.i, l.windows).toFixed(1)},${toY(p.cum).toFixed(1)}`).join(' ')
		}));
		return { polylines, W, H, PAD, zeroY };
	});

	const windowDrawdownByStrategy = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const w of wfRows) {
			if (!w.strategy || w.max_drawdown == null || !isFinite(w.max_drawdown)) continue;
			if (!map.has(w.strategy)) map.set(w.strategy, []);
			map.get(w.strategy)!.push(Math.abs(w.max_drawdown));
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 2)
			.map(([strat, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const med = sorted[Math.floor(sorted.length / 2)];
				const max = sorted[sorted.length - 1];
				return { strat: strat.slice(0, 20), med, max, count: vals.length };
			})
			.sort((a, b) => a.med - b.med)
			.slice(0, 10);
		if (rows.length < 2) return null;
		const maxVal = Math.max(...rows.map((r) => r.max), 0.01);
		return { rows, maxVal };
	});

	const windowRollingMeanByStrategy = $derived.by(() => {
		const map = new Map<string, { label: string; profit: number }[]>();
		for (const w of wfRows) {
			if (!w.strategy || !w.window_label || w.tot_profit_pct == null || !isFinite(w.tot_profit_pct))
				continue;
			if (!map.has(w.strategy)) map.set(w.strategy, []);
			map.get(w.strategy)!.push({ label: w.window_label, profit: w.tot_profit_pct });
		}
		const strats = [...map.entries()]
			.filter(([, pts]) => pts.length >= 4)
			.sort((a, b) => b[1].length - a[1].length)
			.slice(0, 4);
		if (strats.length < 2) return null;
		const WIN = 3;
		const colors = [
			'var(--ch-profit-strong)',
			'var(--ch-violet-strong)',
			'var(--ch-warn)',
			'var(--ch-warn)'
		];
		const lines = strats.map(([strat, pts], bi) => {
			const sorted = [...pts].sort((a, b) => a.label.localeCompare(b.label));
			const rollingMeans = sorted.slice(WIN - 1).map((_, i) => {
				const window = sorted.slice(i, i + WIN);
				return { i: i + WIN - 1, mean: window.reduce((s, p) => s + p.profit, 0) / WIN };
			});
			return {
				strat: strat.slice(0, 14),
				color: colors[bi],
				pts: rollingMeans,
				total: sorted.length
			};
		});
		const allMeans = lines.flatMap((l) => l.pts.map((p) => p.mean));
		const mnM = Math.min(...allMeans, 0),
			mxM = Math.max(...allMeans, 0.01);
		const maxN = Math.max(...lines.map((l) => l.total), 1);
		const W = 400,
			H = 85,
			PAD = 12;
		const toX = (i: number) => PAD + (i / Math.max(maxN - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - mnM) / (mxM - mnM)) * (H - PAD * 2);
		const zeroY = Math.max(PAD, Math.min(H - PAD, toY(0)));
		const polylines = lines.map((l) => ({
			...l,
			poly: l.pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.mean).toFixed(1)}`).join(' ')
		}));
		return { polylines, W, H, PAD, zeroY };
	});

	const windowProfitStdByStrategy = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const w of wfRows) {
			if (!w.strategy || w.tot_profit_pct == null || !isFinite(w.tot_profit_pct)) continue;
			if (!map.has(w.strategy)) map.set(w.strategy, []);
			map.get(w.strategy)!.push(w.tot_profit_pct);
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 3)
			.map(([strat, vals]) => {
				const mean = vals.reduce((a, v) => a + v, 0) / vals.length;
				const std = Math.sqrt(vals.reduce((a, v) => a + (v - mean) ** 2, 0) / vals.length);
				return { strat: strat.slice(0, 18), std, mean, count: vals.length };
			})
			.sort((a, b) => a.std - b.std)
			.slice(0, 8);
		if (rows.length < 2) return null;
		const maxStd = Math.max(...rows.map((r) => r.std), 0.01);
		const W = 340,
			H = rows.length * 16 + 4,
			barMaxW = W - 140;
		return { rows, maxStd, W, H, barMaxW };
	});

	const windowBestWindowByStrategy = $derived.by(() => {
		const map = new Map<string, { label: string; profit: number }[]>();
		for (const w of wfRows) {
			if (!w.strategy || !w.window_label || w.tot_profit_pct == null || !isFinite(w.tot_profit_pct))
				continue;
			if (!map.has(w.strategy)) map.set(w.strategy, []);
			map.get(w.strategy)!.push({ label: w.window_label, profit: w.tot_profit_pct });
		}
		const rows = [...map.entries()]
			.filter(([, pts]) => pts.length >= 3)
			.map(([strat, pts]) => {
				const best = pts.reduce((a, b) => (b.profit > a.profit ? b : a));
				const avg = pts.reduce((a, p) => a + p.profit, 0) / pts.length;
				return {
					strat: strat.slice(0, 18),
					bestProfit: best.profit,
					bestLabel: best.label,
					avg,
					count: pts.length
				};
			})
			.sort((a, b) => b.bestProfit - a.bestProfit)
			.slice(0, 8);
		if (rows.length < 2) return null;
		const maxProfit = Math.max(...rows.map((r) => r.bestProfit), 0.01);
		const W = 340,
			H = rows.length * 16 + 4,
			barMaxW = W - 145;
		return { rows, maxProfit, W, H, barMaxW };
	});

	const windowPassRateTrend = $derived.by(() => {
		const monthMap = new Map<string, { pass: number; total: number }>();
		for (const w of wfRows) {
			if (!w.window_label) continue;
			const mo = w.window_label.slice(0, 7);
			if (!monthMap.has(mo)) monthMap.set(mo, { pass: 0, total: 0 });
			const e = monthMap.get(mo)!;
			e.total++;
			if ((w.tot_profit_pct ?? 0) > 0) e.pass++;
		}
		const months = [...monthMap.keys()].sort();
		if (months.length < 3) return null;
		const pts = months.map((mo, i) => {
			const e = monthMap.get(mo)!;
			return { i, mo: mo.slice(5), rate: e.total ? (e.pass / e.total) * 100 : 0, total: e.total };
		});
		const W = 360,
			H = 68,
			PAD = 10;
		const toX = (i: number) => PAD + (i / Math.max(pts.length - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - v / 100) * (H - PAD * 2);
		const y50 = toY(50);
		const poly = pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.rate).toFixed(1)}`).join(' ');
		const area =
			poly + ` ${toX(pts.length - 1).toFixed(1)},${H - PAD} ${toX(0).toFixed(1)},${H - PAD}`;
		return { pts, poly, area, W, H, PAD, y50 };
	});

	const windowMedianProfitByTimeframe = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const w of wfRows) {
			if (!w.timeframe || w.tot_profit_pct == null || !isFinite(w.tot_profit_pct)) continue;
			const arr = map.get(w.timeframe) ?? [];
			arr.push(w.tot_profit_pct);
			map.set(w.timeframe, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([tf, profits]) => {
				const sorted = [...profits].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
				return { tf, median, count: profits.length };
			})
			.sort((a, b) => b.median - a.median);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.median)), 0.01);
		const W = 300,
			H = rows.length * 18 + 8,
			PAD = 8,
			barMaxW = W - 80,
			midX = PAD + barMaxW / 2;
		return { rows, maxAbs, W, H, PAD, barMaxW, midX };
	});

	const windowStrategyAvgProfitRanking = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const w of wfRows) {
			if (!w.strategy || w.tot_profit_pct == null || !isFinite(w.tot_profit_pct)) continue;
			const arr = map.get(w.strategy) ?? [];
			arr.push(w.tot_profit_pct);
			map.set(w.strategy, arr);
		}
		if (map.size < 3) return null;
		const rows = [...map.entries()]
			.map(([strat, profits]) => ({
				strat: strat.slice(0, 18),
				avg: profits.reduce((a, v) => a + v, 0) / profits.length,
				count: profits.length
			}))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 10);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 340,
			H = rows.length * 16 + 6,
			PAD = 8,
			barMaxW = W - 100;
		return { rows, maxAbs, W, H, PAD, barMaxW };
	});

	const windowPassRateByStrategy = $derived.by(() => {
		const map = new Map<string, { pass: number; total: number }>();
		for (const w of wfRows) {
			if (!w.strategy || w.tot_profit_pct == null || !isFinite(w.tot_profit_pct)) continue;
			const cur = map.get(w.strategy) ?? { pass: 0, total: 0 };
			cur.total++;
			if (w.tot_profit_pct > 0) cur.pass++;
			map.set(w.strategy, cur);
		}
		if (map.size < 3) return null;
		const rows = [...map.entries()]
			.filter(([, d]) => d.total >= 3)
			.map(([strat, d]) => ({
				strat: strat.slice(0, 18),
				rate: (d.pass / d.total) * 100,
				count: d.total
			}))
			.sort((a, b) => b.rate - a.rate)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const W = 340,
			H = rows.length * 16 + 6,
			PAD = 8,
			barMaxW = W - 100;
		return { rows, W, H, PAD, barMaxW };
	});

	const windowProfitDistribution = $derived.by(() => {
		const vals = wfRows
			.filter((w) => w.tot_profit_pct != null && isFinite(w.tot_profit_pct))
			.map((w) => w.tot_profit_pct!);
		if (vals.length < 10) return null;
		const mn = Math.min(...vals),
			mx = Math.max(...vals);
		const bins = 14;
		const binSize = (mx - mn) / bins || 1;
		const buckets = Array.from({ length: bins }, (_, i) => ({ lo: mn + i * binSize, count: 0 }));
		for (const v of vals) {
			const bi = Math.min(bins - 1, Math.floor((v - mn) / binSize));
			buckets[bi].count++;
		}
		const maxC = Math.max(...buckets.map((b) => b.count), 1);
		const W = 360,
			H = 72,
			PAD = 10;
		const bw = (W - PAD * 2) / bins - 1;
		const zeroX =
			PAD +
			Math.max(0, Math.min(bins - 1, Math.floor((0 - mn) / binSize))) * ((W - PAD * 2) / bins);
		const bars = buckets.map((b, i) => ({
			x: PAD + i * ((W - PAD * 2) / bins),
			h: Math.max(2, (b.count / maxC) * (H - PAD - 14)),
			count: b.count,
			color: b.lo >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'
		}));
		return { bars, bw, W, H, PAD, zeroX, mn: mn.toFixed(1), mx: mx.toFixed(1), total: vals.length };
	});

	const windowAvgTradeCountByTF = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const w of wfRows) {
			if (!w.timeframe || w.trades == null || !isFinite(w.trades) || w.trades < 0) continue;
			const arr = map.get(w.timeframe) ?? [];
			arr.push(w.trades);
			map.set(w.timeframe, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([tf, counts]) => ({
				tf,
				avg: counts.reduce((a, v) => a + v, 0) / counts.length,
				count: counts.length
			}))
			.sort((a, b) => b.avg - a.avg);
		const maxVal = Math.max(...rows.map((r) => r.avg), 0.01);
		const W = 320,
			H = 72,
			PAD = 10;
		const bw = Math.max(4, Math.floor((W - PAD * 2) / rows.length) - 4);
		const bars = rows.map((r, i) => ({
			x: PAD + i * ((W - PAD * 2) / rows.length) + 2,
			h: Math.max(3, (r.avg / maxVal) * (H - PAD * 2 - 14)),
			avg: r.avg,
			tf: r.tf,
			count: r.count
		}));
		return { bars, bw, W, H, PAD };
	});

	const windowAvgProfitByTFDiverging = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const w of wfRows) {
			if (!w.timeframe || w.tot_profit_pct == null || !isFinite(w.tot_profit_pct)) continue;
			const arr = map.get(w.timeframe) ?? [];
			arr.push(w.tot_profit_pct);
			map.set(w.timeframe, arr);
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
		const W = 320,
			H = rows.length * 18 + 8,
			PAD = 8,
			barMaxW = W - 70;
		const toX = (v: number) => PAD + ((v + maxAbs) / (2 * maxAbs)) * barMaxW;
		const zeroX = toX(0);
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const windowSharpeByStrategy = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const w of wfRows) {
			if (
				!w.strategy ||
				w.sharpe_ratio == null ||
				!isFinite(w.sharpe_ratio) ||
				Math.abs(w.sharpe_ratio) > 50
			)
				continue;
			const arr = map.get(w.strategy) ?? [];
			arr.push(w.sharpe_ratio);
			map.set(w.strategy, arr);
		}
		if (map.size < 3) return null;
		const rows = [...map.entries()]
			.map(([name, vals]) => ({
				name: name.slice(0, 20),
				avg: vals.reduce((a, v) => a + v, 0) / vals.length,
				count: vals.length
			}))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 10);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 340,
			H = rows.length * 16 + 6,
			PAD = 8,
			barMaxW = W - 110;
		const zeroX = PAD + (maxAbs / (2 * maxAbs)) * barMaxW;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const windowProfitByStrategy = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const w of wfRows) {
			if (!w.strategy || w.tot_profit_pct == null || !isFinite(w.tot_profit_pct)) continue;
			const arr = map.get(w.strategy) ?? [];
			arr.push(w.tot_profit_pct);
			map.set(w.strategy, arr);
		}
		if (map.size < 3) return null;
		const rows = [...map.entries()]
			.map(([name, vals]) => ({
				name: name.slice(0, 20),
				avg: vals.reduce((a, v) => a + v, 0) / vals.length,
				count: vals.length
			}))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 10);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 340,
			H = rows.length * 16 + 6,
			PAD = 8,
			barMaxW = W - 110;
		const zeroX = PAD + (maxAbs / (2 * maxAbs)) * barMaxW;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const windowTradeCountByTF = $derived.by(() => {
		if (!windows || windows.length < 4) return null;
		const map = new Map<string, number[]>();
		for (const w of windows) {
			if (!w.timeframe || w.trades == null) continue;
			const arr = map.get(w.timeframe) ?? [];
			arr.push(w.trades as number);
			map.set(w.timeframe, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([tf, vals]) => ({
				tf,
				avg: vals.reduce((a, v) => a + v, 0) / vals.length,
				count: vals.length
			}))
			.sort((a, b) => b.avg - a.avg);
		const maxAvg = Math.max(...rows.map((r) => r.avg), 1);
		const W = 340,
			H = 80,
			PAD = 10;
		const bw = Math.max(6, (W - PAD * 2) / rows.length - 4);
		const toX = (i: number) => PAD + i * ((W - PAD * 2) / rows.length) + 2;
		const toH = (v: number) => Math.max(2, (v / maxAvg) * (H - PAD * 2 - 16));
		return { rows, W, H, PAD, bw, toX, toH, maxAvg: Math.round(maxAvg) };
	});

	const windowSharpeTimeline = $derived.by(() => {
		if (!windows || windows.length < 5) return null;
		const sorted = [...windows]
			.filter((w) => w.window_start && w.sharpe_ratio != null)
			.sort(
				(a, b) =>
					new Date(a.window_start as string).getTime() -
					new Date(b.window_start as string).getTime()
			);
		if (sorted.length < 4) return null;
		const vals = sorted.map((w) => w.sharpe_ratio as number);
		const minV = Math.min(...vals, 0);
		const maxV = Math.max(...vals, 0.01);
		const range = maxV - minV || 0.01;
		const W = 380,
			H = 72,
			PAD = 10;
		const toX = (i: number) => PAD + (i / (vals.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - minV) / range) * (H - PAD * 2);
		const zeroY = toY(0);
		const polyline = vals.map((v, i) => `${toX(i)},${toY(v)}`).join(' ');
		const area = `${toX(0)},${zeroY} ${polyline} ${toX(vals.length - 1)},${zeroY}`;
		const last = vals[vals.length - 1];
		const color =
			last >= 1
				? 'var(--ch-profit-strong)'
				: last >= 0
					? 'var(--ch-warn)'
					: 'var(--ch-loss-strong)';
		return {
			vals,
			polyline,
			area,
			W,
			H,
			PAD,
			toX,
			zeroY,
			color,
			fillColor: last >= 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)',
			last: last.toFixed(2)
		};
	});

	const windowProfitFactorMonthly = $derived.by(() => {
		if (!windows || windows.length < 5) return null;
		const map = new Map<string, number[]>();
		for (const w of windows) {
			if (!w.window_start || w.profit_factor == null) continue;
			const mo = (w.window_start as string).slice(0, 7);
			const arr = map.get(mo) ?? [];
			arr.push(w.profit_factor as number);
			map.set(mo, arr);
		}
		if (map.size < 3) return null;
		const months = [...map.keys()].sort();
		const pts = months.map((m) => {
			const arr = map.get(m)!;
			return { m: m.slice(5), avg: arr.reduce((a, v) => a + v, 0) / arr.length };
		});
		const maxV = Math.max(...pts.map((p) => p.avg), 1);
		const minV = Math.min(...pts.map((p) => p.avg), 0);
		const range = maxV - minV || 0.01;
		const W = 380,
			H = 68,
			PAD = 10;
		const toX = (i: number) => PAD + (i / (pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + ((maxV - v) / range) * (H - PAD * 2);
		const oneY = Math.max(PAD, Math.min(H - PAD, toY(1)));
		const polyline = pts.map((p, i) => `${toX(i)},${toY(p.avg)}`).join(' ');
		const last = pts[pts.length - 1].avg;
		const color =
			last >= 1.5
				? 'var(--ch-profit-strong)'
				: last >= 1
					? 'var(--ch-warn)'
					: 'var(--ch-loss-strong)';
		return {
			pts,
			polyline,
			W,
			H,
			PAD,
			toX,
			oneY,
			color,
			last: last.toFixed(2),
			firstMo: pts[0].m,
			lastMo: pts[pts.length - 1].m
		};
	});

	const windowCalmarByStrategy = $derived.by(() => {
		if (!windows || windows.length < 4) return null;
		const map = new Map<string, number[]>();
		for (const w of windows) {
			if (!w.strategy || w.calmar_ratio == null) continue;
			const arr = map.get(w.strategy as string) ?? [];
			arr.push(w.calmar_ratio as number);
			map.set(w.strategy as string, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([strat, arr]) => ({
				strat: strat.slice(0, 16),
				avg: arr.reduce((a, v) => a + v, 0) / arr.length
			}))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 10);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 340,
			H = rows.length * 16 + 6,
			PAD = 8,
			barMaxW = W - 110;
		const zeroX = PAD + barMaxW / 2;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const windowDrawdownTrend = $derived.by(() => {
		if (!windows || windows.length < 4) return null;
		const sorted = [...windows]
			.filter((w) => w.window_start && w.max_drawdown_pct != null)
			.sort((a, b) => (a.window_start as string).localeCompare(b.window_start as string));
		if (sorted.length < 4) return null;
		const pts = sorted.map((w) => ({
			m: (w.window_start as string).slice(0, 7),
			dd: w.max_drawdown_pct as number
		}));
		const maxDD = Math.max(...pts.map((p) => p.dd), 0.01);
		const W = 340,
			H = 72,
			PAD = 10;
		const toX = (i: number) => PAD + (i / (pts.length - 1)) * (W - PAD * 2);
		const toY = (dd: number) => H - PAD - (dd / maxDD) * (H - PAD * 2);
		const polyline = pts.map((p, i) => `${toX(i)},${toY(p.dd)}`).join(' ');
		const area = `${toX(0)},${H - PAD} ${polyline} ${toX(pts.length - 1)},${H - PAD}`;
		return {
			pts,
			polyline,
			area,
			W,
			H,
			PAD,
			toX,
			toY,
			maxDD: maxDD.toFixed(1),
			firstM: pts[0].m,
			lastM: pts[pts.length - 1].m
		};
	});

	const windowWinRateByStrategy = $derived.by(() => {
		if (!windows || windows.length < 4) return null;
		const map = new Map<string, number[]>();
		for (const w of windows) {
			if (!w.strategy || w.winning_trades == null || w.trades == null || (w.trades as number) === 0)
				continue;
			const wr = ((w.winning_trades as number) / (w.trades as number)) * 100;
			const arr = map.get(w.strategy as string) ?? [];
			arr.push(wr);
			map.set(w.strategy as string, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([strat, arr]) => ({
				strat: strat.slice(0, 16),
				avg: arr.reduce((a, v) => a + v, 0) / arr.length,
				count: arr.length
			}))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 10);
		const maxAvg = Math.max(...rows.map((r) => r.avg), 100);
		const W = 340,
			H = rows.length * 16 + 6,
			PAD = 8,
			barMaxW = W - 110;
		return { rows, maxAvg, W, H, PAD, barMaxW };
	});

	const windowMonthlyProfitBars = $derived.by(() => {
		if (!windows || windows.length < 4) return null;
		const map = new Map<string, number[]>();
		for (const w of windows) {
			if (!w.window_start || w.tot_profit_pct == null) continue;
			const mo = (w.window_start as string).slice(0, 7);
			const arr = map.get(mo) ?? [];
			arr.push(w.tot_profit_pct as number);
			map.set(mo, arr);
		}
		if (map.size < 3) return null;
		const months = [...map.keys()].sort();
		const pts = months.map((m) => {
			const arr = map.get(m)!;
			return { m: m.slice(5), avg: arr.reduce((a, v) => a + v, 0) / arr.length };
		});
		const maxAbs = Math.max(...pts.map((p) => Math.abs(p.avg)), 0.01);
		const W = 340,
			H = 72,
			PAD = 8;
		const bw = (W - PAD * 2) / pts.length - 1;
		const midY = H / 2;
		return { pts, maxAbs, W, H, PAD, bw, midY };
	});

	const windowSortinoByPairCount = $derived.by(() => {
		if (!windows || windows.length < 6) return null;
		const map = new Map<string, number[]>();
		for (const w of windows) {
			if (w.trades == null || w.sortino == null) continue;
			const bucket = `${Math.floor((w.trades as number) / 10) * 10}+`;
			const arr = map.get(bucket) ?? [];
			arr.push(w.sortino as number);
			map.set(bucket, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([bucket, vals]) => ({ bucket, avg: vals.reduce((a, v) => a + v, 0) / vals.length }))
			.sort((a, b) => parseInt(a.bucket) - parseInt(b.bucket));
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 320,
			H = rows.length * 20 + 6,
			PAD = 8,
			barMaxW = W - 50;
		const zeroX = PAD + barMaxW / 2;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const windowProfitByDow = $derived.by(() => {
		if (!windows || windows.length < 8) return null;
		const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
		const buckets: number[][] = Array.from({ length: 7 }, () => []);
		for (const w of windows) {
			if (!w.window_start || w.tot_profit_pct == null) continue;
			const dow = new Date(w.window_start as string).getDay();
			buckets[dow].push(w.tot_profit_pct as number);
		}
		const pts = DAYS.map((d, i) => ({
			d,
			avg: buckets[i].length ? buckets[i].reduce((a, v) => a + v, 0) / buckets[i].length : 0
		}));
		const maxAbs = Math.max(...pts.map((p) => Math.abs(p.avg)), 0.01);
		const W = 320,
			H = 64,
			PAD = 8;
		const bw = (W - PAD * 2) / 7 - 2;
		const midY = H / 2;
		return { pts, maxAbs, W, H, PAD, bw, midY };
	});

	const windowCalmarCDF = $derived.by(() => {
		if (!windows || windows.length < 15) return null;
		const vals = windows
			.filter((w) => w.calmar_ratio != null)
			.map((w) => w.calmar_ratio as number)
			.sort((a, b) => a - b);
		if (vals.length < 15) return null;
		const minV = vals[0],
			maxV = vals[vals.length - 1];
		const range = maxV - minV || 0.01;
		const W = 320,
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

	const windowPassRateHeatmap = $derived.by(() => {
		if (!windows || windows.length < 6) return null;
		const map = new Map<string, { pass: number; total: number }>();
		for (const w of windows) {
			if (!w.strategy || !w.window_start) continue;
			const strat = (w.strategy as string).slice(0, 12);
			const mo = (w.window_start as string).slice(0, 7);
			const key = `${strat}|${mo}`;
			const entry = map.get(key) ?? { pass: 0, total: 0 };
			entry.total++;
			if (((w.tot_profit_pct as number) ?? 0) > 0) entry.pass++;
			map.set(key, entry);
		}
		const strats = [...new Set([...map.keys()].map((k) => k.split('|')[0]))].slice(0, 6);
		const months = [...new Set([...map.keys()].map((k) => k.split('|')[1]))].sort().slice(-5);
		if (strats.length < 2 || months.length < 2) return null;
		const cellW = 40,
			cellH = 18,
			PAD = 4;
		const W = PAD + (months.length + 1) * cellW + PAD;
		const H = PAD + (strats.length + 1) * cellH + PAD;
		const cells = strats.flatMap((s, si) =>
			months.map((mo, mi) => {
				const entry = map.get(`${s}|${mo}`);
				const rate = entry ? entry.pass / entry.total : -1;
				return { x: PAD + (mi + 1) * cellW, y: PAD + (si + 1) * cellH, rate, s, mo };
			})
		);
		return { cells, strats, months, cellW, cellH, PAD, W, H };
	});

	const windowSharpeVsCalmar = $derived.by(() => {
		if (!windows || windows.length < 10) return null;
		const pts = windows
			.filter((w) => w.sharpe_ratio != null && w.calmar_ratio != null)
			.map((w) => ({
				sharpe: w.sharpe_ratio as number,
				calmar: w.calmar_ratio as number,
				profit: (w.tot_profit_pct as number) ?? 0
			}));
		if (pts.length < 8) return null;
		const shMin = Math.min(...pts.map((p) => p.sharpe));
		const shMax = Math.max(...pts.map((p) => p.sharpe), 0.01);
		const caMin = Math.min(...pts.map((p) => p.calmar));
		const caMax = Math.max(...pts.map((p) => p.calmar), 0.01);
		const shRange = shMax - shMin || 0.01;
		const caRange = caMax - caMin || 0.01;
		const W = 320,
			H = 80,
			PAD = 10;
		const toX = (s: number) => PAD + ((s - shMin) / shRange) * (W - PAD * 2);
		const toY = (c: number) => H - PAD - ((c - caMin) / caRange) * (H - PAD * 2);
		const zeroX = toX(0),
			zeroY = toY(0);
		return { pts, W, H, PAD, toX, toY, zeroX, zeroY };
	});

	const windowMonthlyTradeCount = $derived.by(() => {
		if (!windows || windows.length < 4) return null;
		const map = new Map<string, number[]>();
		for (const w of windows) {
			if (!w.window_start || w.trades == null) continue;
			const mo = (w.window_start as string).slice(0, 7);
			const arr = map.get(mo) ?? [];
			arr.push(w.trades as number);
			map.set(mo, arr);
		}
		if (map.size < 3) return null;
		const months = [...map.keys()].sort();
		const pts = months.map((m) => {
			const arr = map.get(m)!;
			return { m: m.slice(5), avg: arr.reduce((a, v) => a + v, 0) / arr.length };
		});
		const maxAvg = Math.max(...pts.map((p) => p.avg), 1);
		const W = 320,
			H = 60,
			PAD = 8;
		const bw = (W - PAD * 2) / pts.length - 1;
		return { pts, maxAvg, W, H, PAD, bw };
	});

	const windowProfitCDF = $derived.by(() => {
		if (!windows || windows.length < 8) return null;
		const vals = windows
			.filter((w) => w.tot_profit_pct != null)
			.map((w) => (w.tot_profit_pct as number) * 100)
			.sort((a, b) => a - b);
		if (vals.length < 6) return null;
		const minV = vals[0],
			maxV = vals[vals.length - 1];
		if (maxV === minV) return null;
		const W = 320,
			H = 70,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - minV) / (maxV - minV)) * (W - PAD * 2);
		const toY = (i: number) => H - PAD - (i / (vals.length - 1)) * (H - PAD * 2);
		const polyline = vals.map((v, i) => `${toX(v).toFixed(1)},${toY(i).toFixed(1)}`).join(' ');
		const zeroX = toX(0);
		const median = vals[Math.floor(vals.length / 2)].toFixed(1);
		return { polyline, zeroX, W, H, PAD, minV: minV.toFixed(1), maxV: maxV.toFixed(1), median };
	});

	const windowDrawdownStrategyRanking = $derived.by(() => {
		if (!windows || windows.length < 4) return null;
		const map = new Map<string, number[]>();
		for (const w of windows) {
			if (!w.strategy || w.max_drawdown_pct == null) continue;
			const arr = map.get(w.strategy as string) ?? [];
			arr.push(w.max_drawdown_pct as number);
			map.set(w.strategy as string, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([name, vals]) => ({
				name: name.slice(0, 18),
				avg: vals.reduce((s, v) => s + v, 0) / vals.length
			}))
			.sort((a, b) => a.avg - b.avg)
			.slice(0, 8);
		const maxAvg = Math.max(...rows.map((r) => r.avg), 1);
		const W = 320,
			H = rows.length * 18 + 10,
			PAD = 8,
			barMaxW = W - PAD * 2 - 80;
		return { rows, maxAvg, W, H, PAD, barMaxW };
	});

	const windowWinRateByStrategyRanking = $derived.by(() => {
		if (!windows || windows.length < 4) return null;
		const map = new Map<string, { wins: number; total: number }>();
		for (const w of windows) {
			if (!w.strategy || w.tot_profit_pct == null) continue;
			const name = w.strategy as string;
			const s = map.get(name) ?? { wins: 0, total: 0 };
			s.total++;
			if ((w.tot_profit_pct as number) > 0) s.wins++;
			map.set(name, s);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.filter(([, s]) => s.total >= 2)
			.map(([name, s]) => ({
				name: name.slice(0, 18),
				wr: (s.wins / s.total) * 100,
				total: s.total
			}))
			.sort((a, b) => b.wr - a.wr)
			.slice(0, 8);
		if (rows.length < 2) return null;
		const W = 320,
			H = rows.length * 18 + 10,
			PAD = 8,
			barMaxW = W - PAD * 2 - 80;
		return { rows, W, H, PAD, barMaxW };
	});

	const windowSortinoCDF = $derived.by(() => {
		if (!windows || windows.length < 8) return null;
		const vals = windows
			.filter((w) => w.sortino_ratio != null)
			.map((w) => w.sortino_ratio as number)
			.sort((a, b) => a - b);
		if (vals.length < 6) return null;
		const minV = vals[0],
			maxV = vals[vals.length - 1];
		if (maxV === minV) return null;
		const W = 320,
			H = 70,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - minV) / (maxV - minV)) * (W - PAD * 2);
		const toY = (i: number) => H - PAD - (i / (vals.length - 1)) * (H - PAD * 2);
		const polyline = vals.map((v, i) => `${toX(v).toFixed(1)},${toY(i).toFixed(1)}`).join(' ');
		const zeroX = toX(0);
		const median = vals[Math.floor(vals.length / 2)].toFixed(2);
		return { polyline, zeroX, W, H, PAD, minV: minV.toFixed(2), maxV: maxV.toFixed(2), median };
	});

	const windowProfitByStrategyQuartile = $derived.by(() => {
		if (!windows || windows.length < 12) return null;
		const byStrat = new Map<string, number[]>();
		for (const w of windows) {
			if (!w.strategy || w.tot_profit_pct == null) continue;
			const arr = byStrat.get(w.strategy as string) ?? [];
			arr.push(w.tot_profit_pct as number);
			byStrat.set(w.strategy as string, arr);
		}
		if (byStrat.size < 2) return null;
		const rows = [...byStrat.entries()]
			.filter(([, arr]) => arr.length >= 4)
			.map(([name, arr]) => {
				const s = [...arr].sort((a, b) => a - b);
				const q1 = s[Math.floor(s.length * 0.25)];
				const median = s[Math.floor(s.length * 0.5)];
				const q3 = s[Math.floor(s.length * 0.75)];
				return { name: name.slice(0, 16), q1, median, q3 };
			})
			.sort((a, b) => b.median - a.median)
			.slice(0, 6);
		if (rows.length < 2) return null;
		const allVals = rows.flatMap((r) => [r.q1, r.q3]);
		const minV = Math.min(...allVals),
			maxV = Math.max(...allVals, minV + 0.01);
		const W = 320,
			H = rows.length * 20 + 10,
			PAD = 8,
			scaleW = W - PAD * 2 - 80;
		const toX = (v: number) => PAD + 80 + ((v - minV) / (maxV - minV)) * scaleW;
		const zeroX = toX(0);
		return { rows, toX, zeroX, W, H, PAD, minV: minV.toFixed(1), maxV: maxV.toFixed(1) };
	});

	const windowTradeCountCDF = $derived.by(() => {
		if (!windows || windows.length < 8) return null;
		const vals = windows
			.filter((w) => w.trades != null)
			.map((w) => w.trades as number)
			.sort((a, b) => a - b);
		if (vals.length < 6) return null;
		const minV = vals[0],
			maxV = vals[vals.length - 1];
		if (maxV === minV) return null;
		const W = 320,
			H = 70,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - minV) / (maxV - minV)) * (W - PAD * 2);
		const toY = (i: number) => H - PAD - (i / (vals.length - 1)) * (H - PAD * 2);
		const polyline = vals.map((v, i) => `${toX(v).toFixed(1)},${toY(i).toFixed(1)}`).join(' ');
		const median = vals[Math.floor(vals.length / 2)].toFixed(0);
		return { polyline, W, H, PAD, minV: minV.toFixed(0), maxV: maxV.toFixed(0), median };
	});

	const windowCalmarByTF = $derived.by(() => {
		if (!windows || windows.length < 5) return null;
		const map = new Map<string, number[]>();
		for (const w of windows) {
			if (!w.timeframe || w.calmar_ratio == null) continue;
			const arr = map.get(w.timeframe as string) ?? [];
			arr.push(w.calmar_ratio as number);
			map.set(w.timeframe as string, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([tf, vals]) => ({ tf, avg: vals.reduce((s, v) => s + v, 0) / vals.length }))
			.sort((a, b) => b.avg - a.avg);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 280,
			H = rows.length * 22 + 8,
			PAD = 8,
			barMaxW = W - 50;
		const zeroX = PAD + 30 + barMaxW / 2;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const windowProfitByDowBars = $derived.by(() => {
		if (!windows || windows.length < 7) return null;
		const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
		const map = new Map<string, number[]>();
		for (const w of windows) {
			if (!w.window_start || w.tot_profit_pct == null) continue;
			const dow = DAYS[new Date(w.window_start as string).getDay()];
			const arr = map.get(dow) ?? [];
			arr.push(w.tot_profit_pct as number);
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

	const windowAvgSharpeByStrategy = $derived.by(() => {
		if (!windows || windows.length < 5) return null;
		const map = new Map<string, number[]>();
		for (const w of windows) {
			if (!w.strategy || w.sharpe_ratio == null) continue;
			const arr = map.get(w.strategy as string) ?? [];
			arr.push(w.sharpe_ratio as number);
			map.set(w.strategy as string, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([name, vals]) => ({
				name: (name as string).slice(0, 16),
				avg: vals.reduce((s, v) => s + v, 0) / vals.length
			}))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 8);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 280,
			H = rows.length * 20 + 8,
			PAD = 8,
			barMaxW = W - PAD * 2 - 70;
		const zeroX = PAD + 70 + barMaxW / 2;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const windowAvgTradeCountByStrategy = $derived.by(() => {
		if (!windows || windows.length < 5) return null;
		const map = new Map<string, number[]>();
		for (const w of windows) {
			if (!w.strategy || w.trades == null) continue;
			const arr = map.get(w.strategy as string) ?? [];
			arr.push(w.trades as number);
			map.set(w.strategy as string, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([name, vals]) => ({
				name: (name as string).slice(0, 16),
				avg: vals.reduce((s, v) => s + v, 0) / vals.length
			}))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 8);
		const maxAvg = Math.max(...rows.map((r) => r.avg), 1);
		const W = 280,
			H = rows.length * 20 + 8,
			PAD = 8,
			barMaxW = W - PAD * 2 - 70;
		return { rows, maxAvg, W, H, PAD, barMaxW };
	});

	const windowProfitCDFByTF = $derived.by(() => {
		if (!windows || windows.length < 10) return null;
		const byTF = new Map<string, number[]>();
		for (const w of windows) {
			if (!w.timeframe || w.tot_profit_pct == null) continue;
			const arr = byTF.get(w.timeframe as string) ?? [];
			arr.push(w.tot_profit_pct as number);
			byTF.set(w.timeframe as string, arr);
		}
		if (byTF.size < 2) return null;
		const rows = [...byTF.entries()]
			.filter(([, arr]) => arr.length >= 5)
			.map(([tf, arr]) => {
				const sorted = arr.slice().sort((a, b) => a - b);
				const median = sorted[Math.floor(sorted.length / 2)];
				const avg = arr.reduce((s, v) => s + v, 0) / arr.length;
				return { tf, median, avg, n: arr.length };
			})
			.sort((a, b) => b.avg - a.avg);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 280,
			H = rows.length * 22 + 8,
			PAD = 8,
			barMaxW = W - PAD * 2 - 40;
		const zeroX = PAD + 30 + barMaxW / 2;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const windowMonthlyCount = $derived.by(() => {
		if (!windows || windows.length < 5) return null;
		const byMonth = new Map<string, number>();
		for (const w of windows) {
			if (!w.window_start) continue;
			const mo = (w.window_start as string).slice(0, 7);
			byMonth.set(mo, (byMonth.get(mo) ?? 0) + 1);
		}
		if (byMonth.size < 3) return null;
		const pts = [...byMonth.entries()]
			.sort(([a], [b]) => a.localeCompare(b))
			.map(([mo, count]) => ({ mo: mo.slice(5), count }));
		const maxCount = Math.max(...pts.map((p) => p.count), 1);
		const W = 280,
			H = 60,
			PAD = 8;
		const bw = Math.max(1, (W - PAD * 2) / pts.length - 0.5);
		return { pts, maxCount, bw, W, H, PAD };
	});

	const windowMeanProfitByStrategy = $derived.by(() => {
		if (!windows || windows.length < 5) return null;
		const byStrat = new Map<string, number[]>();
		for (const w of windows) {
			if (w.strategy == null || w.tot_profit_pct == null) continue;
			const s = (w.strategy as string).slice(0, 14);
			const arr = byStrat.get(s) ?? [];
			arr.push(w.tot_profit_pct as number);
			byStrat.set(s, arr);
		}
		if (byStrat.size < 2) return null;
		const bars = [...byStrat.entries()]
			.map(([s, arr]) => ({ s, avg: arr.reduce((a, v) => a + v, 0) / arr.length, n: arr.length }))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 10);
		const maxAbs = Math.max(...bars.map((b) => Math.abs(b.avg)), 0.01);
		const W = 280,
			H = bars.length * 18 + 10,
			PAD = 8,
			midX = W / 2;
		const bh = 12;
		return { bars, maxAbs, W, H, PAD, midX, bh };
	});

	const windowProfitTrend = $derived.by(() => {
		if (!windows || windows.length < 15) return null;
		const sorted = [...windows]
			.filter((w) => w.window_start && w.profit_factor != null)
			.sort((a, b) => new Date(a.window_start).getTime() - new Date(b.window_start).getTime());
		if (sorted.length < 15) return null;
		const win = 8;
		const smoothed = sorted.slice(win - 1).map((_, i) => {
			const slice = sorted.slice(i, i + win);
			return slice.reduce((s, w) => s + ((w.profit_factor as number) - 1) * 100, 0) / slice.length;
		});
		const minV = Math.min(...smoothed),
			maxV = Math.max(...smoothed, minV + 0.01);
		const W = 280,
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
			minV: minV.toFixed(1),
			maxV: maxV.toFixed(1),
			n: smoothed.length
		};
	});

	const windowSortinoByDow = $derived.by(() => {
		if (!windows || windows.length < 10) return null;
		const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
		const byDow = new Map<number, number[]>();
		for (const w of windows) {
			if (!w.window_start || w.sortino_ratio == null) continue;
			const d = new Date(w.window_start as string).getUTCDay();
			const arr = byDow.get(d) ?? [];
			arr.push(w.sortino_ratio as number);
			byDow.set(d, arr);
		}
		const bars = [0, 1, 2, 3, 4, 5, 6]
			.filter((d) => byDow.has(d) && (byDow.get(d)?.length ?? 0) >= 2)
			.map((d) => ({
				label: DOW[d],
				avg: (byDow.get(d) ?? []).reduce((s, v) => s + v, 0) / (byDow.get(d)?.length ?? 1)
			}));
		if (bars.length < 3) return null;
		const maxAbs = Math.max(...bars.map((b) => Math.abs(b.avg)), 0.01);
		const W = 280,
			H = 65,
			PAD = 8,
			midY = H / 2;
		const bw = Math.max(8, (W - PAD * 2) / bars.length - 2);
		return { bars, maxAbs, W, H, PAD, midY, bw };
	});

	const windowDrawdownByDow = $derived.by(() => {
		if (!windows || windows.length < 10) return null;
		const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
		const byDow = new Map<number, number[]>();
		for (const w of windows) {
			if (!w.window_start || w.max_drawdown == null) continue;
			const d = new Date(w.window_start as string).getUTCDay();
			const arr = byDow.get(d) ?? [];
			arr.push((w.max_drawdown as number) * 100);
			byDow.set(d, arr);
		}
		const bars = [0, 1, 2, 3, 4, 5, 6]
			.filter((d) => byDow.has(d) && (byDow.get(d)?.length ?? 0) >= 2)
			.map((d) => ({
				label: DOW[d],
				avg: (byDow.get(d) ?? []).reduce((s, v) => s + v, 0) / (byDow.get(d)?.length ?? 1)
			}));
		if (bars.length < 3) return null;
		const maxAvg = Math.max(...bars.map((b) => b.avg), 1);
		const W = 280,
			H = 65,
			PAD = 8;
		const bw = Math.max(8, (W - PAD * 2) / bars.length - 2);
		return { bars, maxAvg, W, H, PAD, bw };
	});
</script>

<svelte:head><title>{t(lang, 'wf.title')} · Crypto Quant</title></svelte:head>

<main class="mx-auto w-full max-w-[1600px] px-4 py-8 sm:px-6">
	<h1 class="text-2xl font-semibold tracking-tight">
		{lang === 'en' ? 'Does it survive different markets?' : '换个市场环境，还能赚钱吗？'}
	</h1>
	<p class="mt-1 max-w-3xl text-sm text-muted-foreground">
		{lang === 'en'
			? 'We cut 2018–2026 into 8 completely different market phases and test every strategy in each phase separately — so nothing can hide behind one lucky bull run. Green = made money in that phase, red = lost money. No strategy is all green — distrust any backtest that is.'
			: '我们把 2018–2026 切成 8 个完全不同的市场阶段，每个策略在每个阶段单独测一遍 —— 策略没法靠一轮幸运牛市藏拙。绿色=那个阶段赚钱，红色=亏钱。没有策略全绿 —— 全绿的回测都该怀疑。'}
	</p>
	<p class="mt-1 text-[11px] text-muted-foreground/70">(Walk-Forward 8-Regime)</p>

	{#if headline}
		<div class="mt-4 max-w-3xl rounded-lg border border-primary/30 bg-primary/5 p-4 text-sm">
			<span class="font-semibold">{lang === 'en' ? 'One-line takeaway:' : '一句话结论：'}</span>
			{#if lang === 'en'}
				{headline.strategy} stayed profitable in {headline.score}% of {headline.okCount} market phases{headline.survived2022
					? ' — including the 2022 blow-up year (LUNA/FTX)'
					: ''}. That — not total return — is the best test of "was it just luck?".
			{:else}
				{headline.strategy} 在 {headline.okCount} 个市场阶段中 {headline.score}% 盈利{headline.survived2022
					? ' —— 包括 2022 爆雷年（LUNA/FTX）'
					: ''}。这是判断「会不会只是运气好」的最重要指标。
			{/if}
		</div>
	{/if}

	{#if byStrategy.length === 0}
		<div
			class="mt-8 rounded-lg border border-dashed bg-card p-10 text-center text-sm text-muted-foreground"
		>
			{lang === 'en' ? 'No data yet. Run' : '暂无数据。本地运行'}
			<code class="font-mono">python scripts/sync_local_state_to_timescale.py</code>
			{lang === 'en'
				? 'locally to push walk_forward_history/*.json.'
				: '推送 walk_forward_history/*.json。'}
		</div>
	{:else}
		<p class="mt-6 text-xs text-muted-foreground">
			{lang === 'en'
				? 'How to read: one row per strategy, one column per market phase. Green cell = made money in that phase, red = lost.'
				: '怎么读：一行一个策略，一列一个市场阶段。格子绿=那个阶段赚钱，红=亏钱。'}
		</p>
		<div class="mt-2 overflow-x-auto rounded-lg border bg-card">
			<table class="w-full text-xs">
				<thead class="bg-secondary text-[11px] text-muted-foreground uppercase">
					<tr>
						<th class="sticky left-0 bg-secondary px-4 py-2.5 text-left">
							<button
								type="button"
								onclick={() => {
									if (wfSort === 'name') wfSortAsc = !wfSortAsc;
									else {
										wfSort = 'name';
										wfSortAsc = true;
									}
								}}
								class="transition-colors hover:text-foreground"
							>
								{lang === 'en' ? 'Strategy' : '策略'}
								{wfSort === 'name' ? (wfSortAsc ? '↑' : '↓') : ''}
							</button>
						</th>
						{#each allWindows as w, _i (_i)}
							<th class="px-2 py-2.5 text-center text-[10px]" title={w}>{regimeLabel(w)}</th>
						{/each}
						<th class="px-3 py-2.5 text-center">
							<button
								type="button"
								onclick={() => {
									if (wfSort === 'sum') wfSortAsc = !wfSortAsc;
									else {
										wfSort = 'sum';
										wfSortAsc = false;
									}
								}}
								class="transition-colors hover:text-foreground"
							>
								{lang === 'en' ? 'Sum' : '总和'}
								{wfSort === 'sum' ? (wfSortAsc ? '↑' : '↓') : ''}
							</button>
						</th>
						<th class="px-3 py-2.5 text-center">
							<button
								type="button"
								onclick={() => {
									if (wfSort === 'stability') wfSortAsc = !wfSortAsc;
									else {
										wfSort = 'stability';
										wfSortAsc = false;
									}
								}}
								class="transition-colors hover:text-foreground"
							>
								{lang === 'en' ? 'Stability' : '稳定度'}
								{wfSort === 'stability' ? (wfSortAsc ? '↑' : '↓') : ''}
							</button>
						</th>
						<th class="px-3 py-2.5 text-center text-muted-foreground"
							>{lang === 'en' ? 'Trend' : '走势'}</th
						>
					</tr>
				</thead>
				<tbody class="font-mono">
					{#each sortedByStrategy as { strategy, windows }, _i (_i)}
						{@const sum = allWindows.reduce((acc, w) => acc + (windows[w]?.tot_profit_pct ?? 0), 0)}
						{@const score = stabilityScore(windows)}
						{@const sparkVals = allWindows.map((w) =>
							windows[w]?.status === 'ok' ? (windows[w]?.tot_profit_pct ?? null) : null
						)}
						{@const sparkMax = Math.max(1, ...sparkVals.map((v) => Math.abs(v ?? 0)))}
						{@const SW = 64}
						{@const SH = 20}
						{@const bw = Math.max(2, SW / allWindows.length - 1)}
						<tr class="border-t border-border hover:bg-accent/30">
							<td class="sticky left-0 bg-card px-4 py-2 text-sm font-semibold">
								<a href="/strategies/{strategy}" class="transition-colors hover:text-primary"
									>{strategy}</a
								>
							</td>
							{#each allWindows as w, _i (_i)}
								{@const r = windows[w]}
								{@const v = r?.tot_profit_pct}
								{@const bg = r?.status === 'ok' ? cellBg(v) : ''}
								<td
									class="px-2 py-2 text-center {bg}"
									class:text-green-400={r?.status === 'ok' && (v ?? 0) > 0}
									class:text-red-400={r?.status === 'ok' && (v ?? 0) < 0}
									class:text-muted-foreground={r?.status !== 'ok'}
									title="{strategy} {w}: {r?.status !== 'ok'
										? 'failed'
										: v?.toFixed(2) + '% · ' + (r?.trades ?? 0) + ' trades'}"
								>
									{r?.status !== 'ok'
										? '—'
										: v == null
											? '—'
											: (v >= 0 ? '+' : '') + v.toFixed(1) + '%'}
								</td>
							{/each}
							<td
								class="px-3 py-2 text-center font-semibold"
								class:text-green-400={sum > 0}
								class:text-red-400={sum < 0}
							>
								{sum >= 0 ? '+' : ''}{sum.toFixed(1)}%
							</td>
							<td class="px-3 py-2 text-center">
								<span class="inline-flex items-center gap-1">
									<span
										class="font-bold"
										class:text-green-400={score >= 70}
										class:text-yellow-400={score >= 50 && score < 70}
										class:text-red-400={score < 50}>{score}%</span
									>
									<span class="text-[9px] text-muted-foreground"
										>{lang === 'en' ? 'win' : '盈利'}</span
									>
								</span>
							</td>
							<td class="px-3 py-2 text-center">
								<svg
									viewBox="0 0 {SW} {SH}"
									width={SW}
									height={SH}
									style="display:inline-block;vertical-align:middle"
								>
									{#each sparkVals as v, i (i)}
										{@const barH =
											v == null ? 1 : Math.max(1, (Math.abs(v) / sparkMax) * (SH / 2 - 1))}
										{@const barY = v == null ? SH / 2 - 0.5 : v >= 0 ? SH / 2 - barH : SH / 2}
										{@const fill =
											v == null
												? 'var(--ch-rule)'
												: v >= 0
													? 'var(--ch-profit)'
													: 'var(--ch-loss-light)'}
										<rect x={i * (bw + 1)} y={barY} width={bw} height={barH} {fill} rx="0.5" />
									{/each}
									<line
										x1="0"
										y1={SH / 2}
										x2={SW}
										y2={SH / 2}
										stroke="var(--ch-rule-strong)"
										stroke-width="0.5"
									/>
								</svg>
							</td>
						</tr>
					{/each}
				</tbody>
				<tfoot class="border-t-2 border-border bg-secondary/60 font-mono text-[10px]">
					<tr>
						<td
							class="sticky left-0 bg-secondary/80 px-4 py-2 text-xs font-semibold text-muted-foreground"
							>{lang === 'en' ? 'Avg all' : '全部平均'}</td
						>
						{#each allWindows as w, _i (_i)}
							{@const a = windowAgg[w]}
							{@const avg = a?.avg}
							<td
								class="px-2 py-2 text-center"
								class:text-green-400={avg != null && avg > 0}
								class:text-red-400={avg != null && avg < 0}
								class:text-muted-foreground={avg == null}
								title="Window {w}: avg {avg?.toFixed(2) ?? '—'}% across {a?.n ?? 0} strategies"
							>
								{avg == null ? '—' : (avg >= 0 ? '+' : '') + avg.toFixed(1) + '%'}
							</td>
						{/each}
						<td
							class="px-3 py-2 text-center font-semibold"
							class:text-green-400={avgSum > 0}
							class:text-red-400={avgSum < 0}>{avgSum >= 0 ? '+' : ''}{avgSum.toFixed(1)}%</td
						>
						<td class="px-3 py-2 text-center text-[9px] text-muted-foreground">avg</td>
						<td class="px-3 py-2 text-center text-[9px] text-muted-foreground">—</td>
					</tr>
					<tr class="border-t border-border/50">
						<td class="sticky left-0 bg-secondary/80 px-4 py-2 text-xs font-semibold text-amber-400"
							>{lang === 'en' ? 'Champion' : '每阶段冠军'}</td
						>
						{#each allWindows as w, _i (_i)}
							{@const c = championByWindow[w]}
							<td
								class="px-2 py-1.5 text-center"
								title={c ? c.strategy + ': +' + c.profit.toFixed(2) + '%' : '—'}
							>
								{#if c}
									<a
										href="/strategies/{c.strategy}"
										class="mx-auto block max-w-[4rem] truncate text-[9px] font-semibold text-amber-400 transition-colors hover:text-amber-300"
										style="max-width:5rem">{c.strategy}</a
									>
								{:else}
									<span class="text-muted-foreground">—</span>
								{/if}
							</td>
						{/each}
						<td class="px-3 py-2 text-center text-[9px] text-muted-foreground">best</td>
						<td class="px-3 py-2 text-center text-[9px] text-muted-foreground">—</td>
						<td class="px-3 py-2 text-center text-[9px] text-muted-foreground">—</td>
					</tr>
				</tfoot>
			</table>
		</div>

		{#if stabilityLeaderboard}
			<section class="mt-8 rounded-lg border bg-card p-5">
				<h2 class="mb-4 text-sm font-semibold">
					{lang === 'en'
						? 'Who survives the most market environments?'
						: '谁在最多市场环境下都能活下来？'}
					<span class="ml-1 text-xs font-normal text-muted-foreground"
						>({lang === 'en'
							? '% of profitable windows — matters more than total return'
							: '盈利窗口占比 —— 比总收益更重要'})</span
					>
					<ChartInfo metric="leaderboard" {lang} />
				</h2>
				<div class="space-y-2">
					{#each stabilityLeaderboard as row, i (i)}
						<div class="flex items-center gap-2 text-xs">
							<span class="w-4 shrink-0 text-right font-mono text-muted-foreground">{i + 1}</span>
							<span class="w-36 shrink-0 truncate font-medium" title={row.strategy}
								>{row.strategy}</span
							>
							<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
								<div
									class="absolute inset-y-0 left-0 rounded-sm transition-all"
									style="width:{row.barPct.toFixed(1)}%; background:{row.score >= 75
										? 'var(--ch-profit-light)'
										: row.score >= 50
											? 'var(--ch-warn-light)'
											: 'var(--ch-loss-light)'}"
								></div>
								<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]"
									>{row.score}% stable</span
								>
							</div>
							<span
								class="w-16 shrink-0 text-right font-mono text-[10px]"
								class:text-green-400={row.sum > 0}
								class:text-red-400={row.sum < 0}
								>{row.sum >= 0 ? '+' : ''}{row.sum.toFixed(1)}%</span
							>
							<span class="w-8 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
								>{row.okCount}w</span
							>
						</div>
					{/each}
				</div>
				<p class="mt-2 text-[10px] text-muted-foreground">
					{lang === 'en'
						? '% = out-of-sample windows with positive return · sum = cumulative profit across all windows · w = window count'
						: '% = 盈利窗口占比（样本外）· 右侧 = 全部窗口累计收益 · w = 窗口数'}
				</p>
			</section>
		{/if}

		<section class="mt-8 grid gap-3 md:grid-cols-4">
			<div class="rounded-lg border bg-card p-4">
				<div class="text-[11px] text-muted-foreground uppercase" title="2018_CRASH">
					{lang === 'en' ? '2018 crash year' : '2018 崩盘年'}
				</div>
				<div class="mt-2 text-xs">
					{lang === 'en'
						? 'BTC −76%. The hardest window for trend-following.'
						: 'BTC −76%。趋势跟随最难的窗口。'}
				</div>
			</div>
			<div class="rounded-lg border bg-card p-4">
				<div class="text-[11px] text-muted-foreground uppercase" title="2020_COVID">
					{lang === 'en' ? '2020 COVID shock' : '2020 疫情震荡'}
				</div>
				<div class="mt-2 text-xs">
					{lang === 'en'
						? 'March 50% flash crash + sharp V-recovery.'
						: '3 月闪崩 50% + V 型大反弹。'}
				</div>
			</div>
			<div class="rounded-lg border bg-card p-4">
				<div class="text-[11px] text-muted-foreground uppercase" title="2022_LUNA_FTX">
					{lang === 'en' ? '2022 blow-up year (LUNA/FTX)' : '2022 爆雷年（LUNA/FTX）'}
				</div>
				<div class="mt-2 text-xs">
					{#if lang === 'en'}Double-crash window. <b>Spot-long hell; futures L+S shines here.</b
						>{:else}双崩盘窗口。<b>spot long 地狱，futures L+S 在这发威</b>。{/if}
				</div>
			</div>
			<div class="rounded-lg border bg-card p-4">
				<div class="text-[11px] text-muted-foreground uppercase" title="2025_PRESENT">
					{lang === 'en' ? '2025 – now' : '2025 至今'}
				</div>
				<div class="mt-2 text-xs">
					{lang === 'en' ? 'Live out-of-sample window.' : '实盘 out-of-sample 窗口。'}
				</div>
			</div>
		</section>
	{/if}

	<details class="mt-8 rounded-xl border border-border bg-card">
		<summary class="cursor-pointer p-4 text-sm font-semibold text-muted-foreground"
			>📊 高级分析（给量化爱好者）/ Advanced analytics</summary
		>
		<div class="space-y-8 p-4 pt-0">
			{#if windowWaterfall}
				{@const ww = windowWaterfall}
				<section class="mt-8 rounded-lg border bg-card p-5">
					<h2 class="mb-4 text-sm font-semibold">
						Window Waterfall — {ww.strategy}
						<span class="ml-1 text-xs font-normal text-muted-foreground"
							>(top stability strategy · sequential out-of-sample windows)</span
						>
						<ChartInfo metric="leaderboard" {lang} />
					</h2>
					<div class="flex items-end gap-1">
						{#each ww.bars as bar, i (i)}
							{@const h =
								bar.profit != null ? Math.round((Math.abs(bar.profit) / ww.maxAbs) * 72) : 0}
							<div class="flex flex-1 flex-col items-center gap-1">
								<div
									class="w-full rounded-sm transition-colors"
									style="height:{Math.max(2, h)}px; background:{bar.profit == null
										? 'var(--ch-axis-faint)'
										: bar.profit >= 0
											? 'var(--ch-profit)'
											: 'var(--ch-loss)'}"
									title="{bar.window}: {bar.profit != null
										? (bar.profit >= 0 ? '+' : '') + bar.profit.toFixed(1) + '%'
										: 'failed'}"
								></div>
								<span
									class="w-full truncate text-center text-[8px] text-muted-foreground"
									title={bar.window}>{regimeLabel(bar.window)}</span
								>
							</div>
						{/each}
					</div>
					<div class="mt-2 flex items-center gap-4 text-[10px] text-muted-foreground">
						<span class="flex items-center gap-1"
							><span class="inline-block h-2 w-2 rounded-sm bg-green-500/60"></span>Positive</span
						>
						<span class="flex items-center gap-1"
							><span class="inline-block h-2 w-2 rounded-sm bg-red-500/60"></span>Negative</span
						>
						<span class="flex items-center gap-1"
							><span class="inline-block h-2 w-2 rounded-sm bg-muted/20"></span>Failed</span
						>
						<span class="ml-auto font-mono"
							>cumulative: {ww.cumulative[ww.cumulative.length - 1] >= 0 ? '+' : ''}{ww.cumulative[
								ww.cumulative.length - 1
							]?.toFixed(1)}%</span
						>
					</div>
				</section>
			{/if}

			{#if allWindows.length >= 2 && byStrategy.length >= 2}
				<section class="mt-8 rounded-lg border bg-card p-5">
					<h2 class="mb-4 text-sm font-semibold">
						Window Profitability Rate <span class="ml-1 text-xs font-normal text-muted-foreground"
							>(% of strategies profitable per window · {byStrategy.length} strategies)</span
						>
						<ChartInfo metric="wfConsistency" {lang} />
					</h2>
					<div class="flex items-end gap-1">
						{#each allWindows as w, _i (_i)}
							{@const agg = windowAgg[w]}
							{@const wr = agg?.wr ?? 0}
							{@const n = agg?.n ?? 0}
							<div
								class="flex flex-1 flex-col items-center gap-0.5"
								title="{w}: {n > 0 ? (wr * 100).toFixed(0) : 0}% profitable · avg {agg?.avg != null
									? agg.avg.toFixed(1)
									: '?'}%"
							>
								<div
									class="w-full rounded-t-sm"
									style="height:{Math.max(2, Math.round(wr * 72))}px; background:{wr >= 0.6
										? 'var(--ch-profit)'
										: wr >= 0.4
											? 'var(--ch-warn-light)'
											: 'var(--ch-loss-light)'}"
								></div>
								<span class="text-center text-[8px] leading-tight text-muted-foreground" title={w}
									>{regimeLabel(w)}</span
								>
							</div>
						{/each}
					</div>
					<div class="mt-3 flex gap-4 text-[10px] text-muted-foreground">
						<span class="flex items-center gap-1"
							><span class="inline-block h-2 w-3 rounded-sm bg-green-500/60"></span>≥60% profitable</span
						>
						<span class="flex items-center gap-1"
							><span class="inline-block h-2 w-3 rounded-sm bg-yellow-400/55"></span>40-60%</span
						>
						<span class="flex items-center gap-1"
							><span class="inline-block h-2 w-3 rounded-sm bg-red-500/50"></span>&lt;40%</span
						>
						<span class="ml-auto">Hover for avg profit%</span>
					</div>
				</section>
			{/if}

			{#if allWindows.length >= 2 && byStrategy.length >= 2}
				{@const maxN = Math.max(1, ...allWindows.map((w) => windowAgg[w]?.n ?? 0))}
				<section class="mt-8 rounded-lg border bg-card p-5">
					<h2 class="mb-4 text-sm font-semibold">
						Strategy Coverage per Window <span
							class="ml-1 text-xs font-normal text-muted-foreground"
							>(how many strategies tested each window)</span
						>
						<ChartInfo metric="wfConsistency" {lang} />
					</h2>
					<div class="flex items-end gap-1">
						{#each allWindows as w, _i (_i)}
							{@const n = windowAgg[w]?.n ?? 0}
							<div class="flex flex-1 flex-col items-center gap-0.5" title="{w}: {n} strategies">
								<span class="font-mono text-[8px] text-muted-foreground">{n}</span>
								<div
									class="w-full rounded-t-sm"
									style="height:{Math.max(2, Math.round((n / maxN) * 56))}px; background:{n === maxN
										? 'var(--ch-violet)'
										: n >= maxN * 0.7
											? 'var(--ch-violet-light)'
											: 'var(--ch-violet-light)'}"
								></div>
								<span class="text-center text-[7px] leading-tight text-muted-foreground" title={w}
									>{regimeLabel(w)}</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Bar height = strategy count with valid results for that window · darker = full coverage
						· lighter = fewer strategies tested
					</p>
				</section>
			{/if}

			{#if stratProfitSumRanking}
				<section class="mt-6 rounded-lg border bg-card p-4">
					<h2 class="mb-3 text-sm font-semibold">
						Strategy Profit Sum Ranking <span class="ml-1 text-xs font-normal text-muted-foreground"
							>(cumulative profit% across all walk-forward windows)</span
						>
						<ChartInfo metric="walkForward" {lang} />
					</h2>
					<div class="space-y-1.5">
						{#each stratProfitSumRanking as r, i (i)}
							<div class="flex items-center gap-2 text-xs">
								<span
									class="w-44 shrink-0 truncate font-mono text-[11px] text-muted-foreground"
									title={r.strategy}>{r.strategy}</span
								>
								<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
									<div
										class="absolute inset-y-0 left-0 rounded-sm transition-all"
										style="width:{r.barPct.toFixed(1)}%; background:{r.sum >= 0
											? 'var(--ch-profit)'
											: 'var(--ch-loss-light)'}"
									></div>
									<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
										{r.sum >= 0 ? '+' : ''}{r.sum.toFixed(1)}%
									</span>
								</div>
								<span class="w-14 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
									>{r.okCount}w</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Sum of profit% across all walk-forward windows · w = window count · green = net positive
						across all periods
					</p>
				</section>
			{/if}

			{#if windowAvgTrend}
				{@const wat = windowAvgTrend}
				<section class="mt-6 rounded-lg border bg-card p-4">
					<h2 class="mb-3 text-sm font-semibold">
						Avg Profit Per Window <span class="ml-1 text-xs font-normal text-muted-foreground"
							>(cross-strategy average · market regime signal)</span
						>
						<ChartInfo metric="walkForward" {lang} />
					</h2>
					<svg viewBox="0 0 {wat.W} {wat.H}" class="w-full" style="height:{wat.H}px">
						{#if wat.zeroY > wat.PAD && wat.zeroY < wat.H - wat.PAD}
							<line
								x1={wat.PAD}
								y1={wat.zeroY}
								x2={wat.W - wat.PAD}
								y2={wat.zeroY}
								stroke="var(--ch-rule)"
								stroke-width="0.5"
								stroke-dasharray="2 2"
							/>
						{/if}
						<polyline
							points={wat.polyline}
							fill="none"
							stroke="rgba(129,140,248,0.8)"
							stroke-width="1.5"
							stroke-linejoin="round"
						/>
						{#each wat.dots as d, _i (_i)}
							<circle
								cx={d.x.toFixed(1)}
								cy={d.y.toFixed(1)}
								r="3"
								fill={d.v >= 0 ? 'var(--ch-profit-strong)' : 'var(--ch-loss-strong)'}
							>
								<title>{d.label}: {d.v >= 0 ? '+' : ''}{d.v.toFixed(2)}% avg</title>
							</circle>
						{/each}
						{#each wat.dots as d, i (i)}
							{#if i === 0 || i === wat.dots.length - 1}
								<text
									x={d.x.toFixed(1)}
									y={wat.H - 1}
									font-size="7"
									fill="var(--ch-rule-strong)"
									text-anchor={i === 0 ? 'start' : 'end'}>{d.label}</text
								>
							{/if}
						{/each}
					</svg>
					<p class="mt-1 text-[10px] text-muted-foreground">
						Average profit% across all strategies per window · green dot = net positive window ·
						indigo line connects windows chronologically
					</p>
				</section>
			{/if}

			{#if stratWinFrequency && stratWinFrequency.length >= 2}
				<section class="mt-6 rounded-lg border bg-card p-4">
					<h2 class="mb-3 text-sm font-semibold">
						Window Win Frequency <span class="ml-1 text-xs font-normal text-muted-foreground"
							>(positive windows / total windows per strategy)</span
						>
						<ChartInfo metric="wfConsistency" {lang} />
					</h2>
					<div class="space-y-1.5">
						{#each stratWinFrequency as r, i (i)}
							<div class="flex items-center gap-2 text-xs">
								<span
									class="w-44 shrink-0 truncate font-mono text-[11px] text-muted-foreground"
									title={r.strategy}>{r.strategy}</span
								>
								<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
									<div
										class="absolute inset-y-0 left-0 rounded-sm transition-all"
										style="width:{(r.wr * 100).toFixed(1)}%; background:{r.wr >= 0.6
											? 'var(--ch-profit)'
											: r.wr >= 0.4
												? 'var(--ch-warn-light)'
												: 'var(--ch-loss-light)'}"
									></div>
									<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]"
										>{r.wins}/{r.total} windows</span
									>
								</div>
								<span
									class="w-12 shrink-0 text-right font-mono text-[10px]"
									class:text-green-400={r.wr >= 0.6}
									class:text-yellow-400={r.wr >= 0.4 && r.wr < 0.6}
									class:text-red-400={r.wr < 0.4}>{(r.wr * 100).toFixed(0)}%</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Green ≥ 60% · amber 40-60% · red &lt; 40% · only strategies with ≥ 2 windows shown
					</p>
				</section>
			{/if}

			{#if windowBestWorstContrast}
				<section class="mt-6 rounded-lg border bg-card p-5">
					<h2 class="mb-3 text-sm font-semibold">
						Window Strategy Spread
						<span class="ml-1 text-xs font-normal text-muted-foreground"
							>(best minus worst strategy profit per window · high spread = high dispersion)</span
						>
						<ChartInfo metric="leaderboard" {lang} />
					</h2>
					<div class="space-y-2">
						{#each windowBestWorstContrast as r, _i (_i)}
							<div class="flex items-center gap-2">
								<span class="w-20 shrink-0 truncate font-mono text-[10px] text-muted-foreground"
									>{r.window}</span
								>
								<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
									<div
										class="absolute inset-y-0 left-0 rounded-sm bg-violet-500/40"
										style="width:{r.spreadBarPct.toFixed(1)}%"
									></div>
									<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
										Δ{r.spread.toFixed(1)}pp
									</span>
								</div>
								<span
									class="w-28 shrink-0 truncate text-right font-mono text-[10px] text-green-400"
									title={r.best.strategy}
									>↑{r.best.v.toFixed(1)}% {r.best.strategy.slice(0, 10)}</span
								>
								<span
									class="w-28 shrink-0 truncate text-right font-mono text-[10px] text-red-400"
									title={r.worst.strategy}
									>↓{r.worst.v.toFixed(1)}% {r.worst.strategy.slice(0, 10)}</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Δpp = percentage-point spread between best and worst strategy · large spread = strategy
						selection matters most in that window
					</p>
				</section>
			{/if}

			{#if windowParticipationRate}
				<section class="mt-6 rounded-lg border bg-card p-5">
					<h2 class="mb-3 text-sm font-semibold">
						Window Participation Rate
						<span class="ml-1 text-xs font-normal text-muted-foreground"
							>(how many strategies have results per window)</span
						>
						<ChartInfo metric="wfConsistency" {lang} />
					</h2>
					<div class="space-y-1.5">
						{#each windowParticipationRate as r, _i (_i)}
							<div class="flex items-center gap-2">
								<span class="w-20 shrink-0 truncate font-mono text-[10px] text-muted-foreground"
									>{r.window}</span
								>
								<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
									<div
										class="absolute inset-y-0 left-0 rounded-sm"
										style="width:{(r.pct * 100).toFixed(1)}%; background:{r.pct >= 0.8
											? 'var(--ch-profit-light)'
											: r.pct >= 0.5
												? 'var(--ch-warn-light)'
												: 'var(--ch-loss-light)'}"
									></div>
									<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
										{r.ok}/{r.total} strategies
									</span>
								</div>
								{#if r.avgProfit != null}
									<span
										class="w-16 shrink-0 text-right font-mono text-[10px]"
										class:text-green-400={r.avgProfit >= 0}
										class:text-red-400={r.avgProfit < 0}
									>
										avg {r.avgProfit >= 0 ? '+' : ''}{r.avgProfit.toFixed(1)}%
									</span>
								{/if}
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Green ≥80% coverage · yellow 50–80% · red &lt;50% · shows which windows have the most
						data
					</p>
				</section>
			{/if}

			{#if avgTradesPerWindow}
				<section class="mt-6 rounded-lg border bg-card p-5">
					<h2 class="mb-3 text-sm font-semibold">
						Avg Trades per Window
						<span class="ml-1 text-xs font-normal text-muted-foreground"
							>(across all strategies with ok results)</span
						>
						<ChartInfo metric="wfConsistency" {lang} />
					</h2>
					<div class="flex items-end gap-1" style="height:72px">
						{#each avgTradesPerWindow as b, _i (_i)}
							<div
								class="flex flex-1 flex-col items-center justify-end gap-0.5"
								title="{b.window}: avg {b.avg?.toFixed(1)} trades · {b.n} strategies"
							>
								<div
									class="w-full rounded-t-sm bg-violet-500/50"
									style="height:{Math.max(2, b.barPct * 0.6)}px"
								></div>
							</div>
						{/each}
					</div>
					<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
						{#if avgTradesPerWindow.length > 0}
							<span>{avgTradesPerWindow[0].window}</span>
							<span>{avgTradesPerWindow[avgTradesPerWindow.length - 1].window}</span>
						{/if}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Bar height = avg trade count per window · taller = more active period · hover for exact
						values
					</p>
				</section>
			{/if}

			{#if strategyWinStreak}
				<section class="mt-6 rounded-lg border bg-card p-5">
					<h2 class="mb-3 text-sm font-semibold">
						Longest Profitable Window Streak
						<span class="ml-1 text-xs font-normal text-muted-foreground"
							>(consecutive profitable windows · top 10 strategies)</span
						>
						<ChartInfo metric="streak" {lang} />
					</h2>
					<div class="space-y-1.5">
						{#each strategyWinStreak as r, i (i)}
							<div class="flex items-center gap-2">
								<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
									>{i + 1}</span
								>
								<span class="w-36 shrink-0 truncate font-mono text-[10px]" title={r.strategy}
									>{r.strategy}</span
								>
								<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
									<div
										class="absolute inset-y-0 left-0 rounded-sm bg-emerald-500/55"
										style="width:{r.barPct.toFixed(1)}%"
									></div>
									<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
										{r.streak}× streak
									</span>
								</div>
								<span class="w-20 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
									WR {(r.wr * 100).toFixed(0)}% / {r.total}w
								</span>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Bar = longest consecutive profitable windows · right = overall win rate across all
						windows
					</p>
				</section>
			{/if}

			{#if strategyWindowHeatmap}
				{@const swh = strategyWindowHeatmap}
				<section class="mt-6 rounded-lg border bg-card p-5">
					<h2 class="mb-3 text-sm font-semibold">
						Strategy × Window Heatmap
						<span class="ml-1 text-xs font-normal text-muted-foreground"
							>(profit% per cell · green = profit · red = loss)</span
						>
						<ChartInfo metric="distribution" {lang} />
					</h2>
					<div class="overflow-x-auto">
						<table class="w-full text-[10px]">
							<thead>
								<tr>
									<th class="w-36 pr-3 text-left font-normal text-muted-foreground">Strategy</th>
									{#each swh.windows as w, _i (_i)}
										<th class="px-1 text-center text-[9px] font-normal text-muted-foreground"
											>{w}</th
										>
									{/each}
								</tr>
							</thead>
							<tbody>
								{#each swh.grid as row, _i (_i)}
									<tr class="border-t border-border/20">
										<td
											class="max-w-[9rem] truncate py-1 pr-3 font-mono text-[10px] text-foreground"
											title={row.strategy}>{row.strategy}</td
										>
										{#each row.cells as cell, _i (_i)}
											<td class="px-0.5 py-1 text-center">
												{#if cell}
													<span
														class="inline-flex h-6 w-10 items-center justify-center rounded font-mono text-[9px] font-semibold"
														style="background:{cell.v >= 0
															? `rgba(34,197,94,${(cell.intensity * 0.75 + 0.1).toFixed(2)})`
															: `rgba(239,68,68,${(cell.intensity * 0.75 + 0.1).toFixed(2)})`}; color:white"
													>
														{cell.v >= 0 ? '+' : ''}{cell.v.toFixed(0)}
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
						Each cell = tot_profit% for that strategy in that walk-forward window · intensity ∝
						magnitude
					</p>
				</section>
			{/if}

			{#if stratAvgProfitPerWindow}
				<section class="mt-6 rounded-lg border bg-card p-5">
					<h2 class="mb-3 text-sm font-semibold">
						Avg Profit per Window by Strategy
						<span class="ml-1 text-xs font-normal text-muted-foreground"
							>(avg tot_profit% per participated window · min 2 windows)</span
						>
						<ChartInfo metric="avgProfit" {lang} />
					</h2>
					<div class="space-y-1.5">
						{#each stratAvgProfitPerWindow as r, i (i)}
							<div class="flex items-center gap-2">
								<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
									>{i + 1}</span
								>
								<span class="w-36 shrink-0 truncate font-mono text-[10px]" title={r.strategy}
									>{r.strategy}</span
								>
								<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
									<div
										class="absolute inset-y-0 left-0 rounded-sm transition-all"
										style="width:{r.barPct.toFixed(1)}%; background:{r.avg >= 0
											? 'var(--ch-profit-light)'
											: 'var(--ch-loss-light)'}"
									></div>
									<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
										{r.avg >= 0 ? '+' : ''}{r.avg.toFixed(1)}%
									</span>
								</div>
								<span class="w-20 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
									WR {(r.wr * 100).toFixed(0)}% · {r.count}w
								</span>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Bar = avg tot_profit% per window · right = window win rate and count · normalizes for
						strategies with fewer windows
					</p>
				</section>
			{/if}

			{#if stratLastWindowPerf}
				{@const slwp = stratLastWindowPerf}
				<section class="mt-6 rounded-lg border bg-card p-5">
					<h2 class="mb-3 text-sm font-semibold">
						Last Window Performance
						<span class="ml-1 text-xs font-normal text-muted-foreground"
							>(window: {slwp.window} · current form snapshot)</span
						>
						<ChartInfo metric="wfConsistency" {lang} />
					</h2>
					<div class="space-y-1.5">
						{#each slwp.rows as r, i (i)}
							<div class="flex items-center gap-2">
								<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
									>{i + 1}</span
								>
								<span class="w-36 shrink-0 truncate font-mono text-[10px]" title={r.strategy}
									>{r.strategy}</span
								>
								<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
									<div
										class="absolute inset-y-0 left-0 rounded-sm transition-all"
										style="width:{r.barPct.toFixed(1)}%; background:{r.profit >= 0
											? 'var(--ch-profit-light)'
											: 'var(--ch-loss-light)'}"
									></div>
									<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
										{r.profit >= 0 ? '+' : ''}{r.profit.toFixed(1)}%
									</span>
								</div>
								<span class="w-14 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
									>{r.trades}tr</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Profit% in the most recent walk-forward window · green = profitable · right = trade
						count · snapshot of which strategies are working now
					</p>
				</section>
			{/if}

			{#if wfTimeframeBreakdown}
				<section class="mt-6 rounded-lg border bg-card p-5">
					<h2 class="mb-3 text-sm font-semibold">
						Avg Profit by Timeframe (WF)
						<span class="ml-1 text-xs font-normal text-muted-foreground"
							>({data.results.filter((r) => r.status === 'ok').length} ok results across all windows)</span
						>
						<ChartInfo metric="avgProfit" {lang} />
					</h2>
					<div class="space-y-1.5">
						{#each wfTimeframeBreakdown as r, _i (_i)}
							<div class="flex items-center gap-2">
								<span class="w-12 shrink-0 font-mono text-[10px] font-semibold">{r.tf}</span>
								<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
									<div
										class="absolute inset-y-0 left-0 rounded-sm"
										style="width:{r.barPct.toFixed(1)}%; background:{r.avg >= 0
											? 'var(--ch-profit-light)'
											: 'var(--ch-loss-light)'}"
									></div>
									<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
										{r.avg >= 0 ? '+' : ''}{r.avg.toFixed(1)}% avg
									</span>
								</div>
								<span class="w-24 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
									WR {(r.wr * 100).toFixed(0)}% · {r.count}r
								</span>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Avg tot_profit% across all WF windows for each timeframe · green = positive · right =
						window win rate
					</p>
				</section>
			{/if}

			{#if windowVolatility}
				<section class="mt-6 rounded-lg border bg-card p-4">
					<h2 class="mb-3 text-sm font-semibold">
						Strategy Profit Spread per Window
						<span class="ml-1 text-xs font-normal text-muted-foreground"
							>(std dev of strategy profits — taller = more divergence between strategies that
							window)</span
						>
						<ChartInfo metric="totalProfit" {lang} />
					</h2>
					<div class="flex items-end gap-0.5" style="height:64px">
						{#each windowVolatility as w, _i (_i)}
							<div
								class="flex flex-1 flex-col items-center justify-end"
								title="{w.label}: σ={w.std.toFixed(2)}% · avg={w.mean.toFixed(
									2
								)}% · {w.count} strategies"
							>
								<div
									class="w-full rounded-t-sm"
									style="height:{Math.max(2, w.barPct * 0.6)}px; background:{w.std > 3
										? 'var(--ch-loss)'
										: w.std > 1.5
											? 'var(--ch-warn)'
											: 'var(--ch-violet-light)'}"
								></div>
							</div>
						{/each}
					</div>
					<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
						{#each windowVolatility as w, i (i)}
							{#if i === 0 || i === Math.floor(windowVolatility.length / 2) || i === windowVolatility.length - 1}
								<span>{w.label}</span>
							{/if}
						{/each}
					</div>
					<p class="mt-1 text-[10px] text-muted-foreground">
						Red σ&gt;3% · yellow 1.5–3% · blue &lt;1.5% · high spread = some strategies greatly
						outperformed others
					</p>
				</section>
			{/if}
			{#if strategyMomentum}
				<section class="mt-8 rounded-lg border border-border bg-card p-5">
					<h2 class="text-sm font-semibold">
						Strategy Momentum
						<span class="ml-1 text-xs font-normal text-muted-foreground"
							>(last-3-window avg vs all-window avg profit — improving or declining?)</span
						>
						<ChartInfo metric="avgProfit" {lang} />
					</h2>
					<div class="mt-3 space-y-1.5">
						{#each strategyMomentum as r, _i (_i)}
							<div class="flex items-center gap-2">
								<span class="w-40 truncate font-mono text-[10px]" title={r.strategy}
									>{r.strategy}</span
								>
								<div class="relative flex-1" style="height:14px">
									<div
										class="absolute rounded"
										style="height:100%; width:{r.barPct}%; background:{r.momentum > 0
											? 'var(--ch-profit-light)'
											: 'var(--ch-loss-light)'}"
									></div>
								</div>
								<span
									class="w-16 text-right font-mono text-[10px]"
									style="color:{r.momentum > 0
										? 'var(--ch-profit-strong)'
										: 'var(--ch-loss-strong)'}"
								>
									{r.momentum > 0 ? '+' : ''}{r.momentum.toFixed(1)}%
								</span>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Green = recent windows better than historical avg · red = recent underperformance
					</p>
				</section>
			{/if}
			{#if windowParticipationTrend}
				{@const wpt = windowParticipationTrend}
				<section class="mt-8 rounded-lg border border-border bg-card p-5">
					<h2 class="text-sm font-semibold">
						Strategy Participation Over Time
						<span class="ml-1 text-xs font-normal text-muted-foreground"
							>(how many strategies ran each walk-forward window · {wpt.growing
								? 'growing ↑'
								: 'stable →'})</span
						>
						<ChartInfo metric="walkForward" {lang} />
					</h2>
					<svg viewBox="0 0 {wpt.W} {wpt.H}" class="w-full" style="height:64px">
						<polyline
							points={wpt.polyline}
							fill="none"
							stroke="var(--ch-violet)"
							stroke-width="1.5"
						/>
						{#each wpt.pts as p, i (i)}
							<circle
								cx={(
									wpt.PAD +
									(i / Math.max(1, wpt.pts.length - 1)) * (wpt.W - wpt.PAD * 2)
								).toFixed(1)}
								cy={(wpt.H - wpt.PAD - (p.count / wpt.maxCount) * (wpt.H - wpt.PAD * 2)).toFixed(1)}
								r="2.5"
								fill="var(--ch-violet-strong)"><title>{p.w}: {p.count} strategies</title></circle
							>
						{/each}
					</svg>
					<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
						<span>{wpt.pts[0]?.w}</span><span>→ window →</span><span
							>{wpt.pts[wpt.pts.length - 1]?.w}</span
						>
					</div>
					<p class="mt-1 text-[10px] text-muted-foreground">
						Each point = number of strategies with valid results in that window · upward trend =
						more strategies actively tested
					</p>
				</section>
			{/if}
			{#if windowProfitRange}
				<section class="mt-8 rounded-lg border border-border bg-card p-5">
					<h2 class="text-sm font-semibold">
						Window Profit Spread
						<span class="ml-1 text-xs font-normal text-muted-foreground"
							>(min/avg/max profit% per window — how wide is the strategy spread?)</span
						>
						<ChartInfo metric="totalProfit" {lang} />
					</h2>
					<svg viewBox="0 0 {windowProfitRange.length * 18} 80" class="w-full" style="height:80px">
						<line
							x1="0"
							x2={windowProfitRange.length * 18}
							y1="40"
							y2="40"
							stroke="var(--ch-rule)"
							stroke-width="1"
						/>
						{#each windowProfitRange as r, i (i)}
							{@const x = i * 18 + 9}
							<line
								x1={x}
								x2={x}
								y1={r.yMx}
								y2={r.yMn}
								stroke={r.avg >= 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)'}
								stroke-width="6"
								stroke-linecap="round"
							/>
							<circle
								cx={x}
								cy={r.yAvg}
								r="2"
								fill={r.avg >= 0 ? 'var(--ch-profit-strong)' : 'var(--ch-loss-strong)'}
								><title
									>{r.w}: min {r.mn.toFixed(1)}% avg {r.avg.toFixed(1)}% max {r.mx.toFixed(
										1
									)}%</title
								></circle
							>
						{/each}
					</svg>
					<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
						<span>{windowProfitRange[0]?.w}</span><span>→ window →</span><span
							>{windowProfitRange[windowProfitRange.length - 1]?.w}</span
						>
					</div>
					<p class="mt-1 text-[10px] text-muted-foreground">
						Bar = min–max range · dot = avg · green = positive avg · tall bars = high strategy
						divergence in that window
					</p>
				</section>
			{/if}
			{#if windowChampionFrequency}
				<section class="mt-8 rounded-lg border border-border bg-card p-5">
					<h2 class="text-sm font-semibold">
						Window Champion Leaderboard
						<span class="ml-1 text-xs font-normal text-muted-foreground"
							>(how many walk-forward windows each strategy won)</span
						>
						<ChartInfo metric="walkForward" {lang} />
					</h2>
					<div class="mt-3 space-y-1.5">
						{#each windowChampionFrequency as r, i (i)}
							<div class="flex items-center gap-2">
								<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
									>{i + 1}</span
								>
								<a
									href="/strategies/{r.strategy}"
									class="w-40 shrink-0 truncate text-xs text-foreground hover:text-primary hover:underline"
									>{r.strategy}</a
								>
								<div class="relative h-4 flex-1 overflow-hidden rounded bg-muted">
									<div
										class="absolute inset-y-0 left-0 rounded"
										style="width:{r.barPct.toFixed(1)}%; background:{i === 0
											? 'var(--ch-warn)'
											: i <= 2
												? 'var(--ch-profit-light)'
												: 'var(--ch-violet-light)'}"
									></div>
									<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]"
										>{r.wins} win{r.wins !== 1 ? 's' : ''}</span
									>
								</div>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Gold = overall champion · strategy with most window wins is most consistently dominant
					</p>
				</section>
			{/if}
			{#if strategyProfitStdDev}
				<section class="mt-8 rounded-lg border border-border bg-card p-5">
					<h2 class="text-sm font-semibold">
						Strategy Profit Consistency
						<span class="ml-1 text-xs font-normal text-muted-foreground"
							>(std dev of profit% across windows · lower = more consistent)</span
						>
						<ChartInfo metric="totalProfit" {lang} />
					</h2>
					<div class="mt-3 space-y-1.5">
						{#each strategyProfitStdDev as r, _i (_i)}
							<div class="flex items-center gap-2">
								<a
									href="/strategies/{r.strategy}"
									class="w-40 shrink-0 truncate text-xs hover:text-primary hover:underline"
									>{r.strategy}</a
								>
								<div class="relative flex-1" style="height:14px">
									<div
										class="absolute rounded"
										style="height:100%; width:{r.barPct.toFixed(1)}%; background:{r.std < 5
											? 'var(--ch-profit-light)'
											: r.std < 15
												? 'var(--ch-warn-light)'
												: 'var(--ch-loss-light)'}"
									></div>
								</div>
								<span class="w-16 text-right font-mono text-[10px] text-muted-foreground"
									>σ {r.std.toFixed(1)}%</span
								>
								<span class="w-14 text-right font-mono text-[9px] text-muted-foreground"
									>μ {r.mean >= 0 ? '+' : ''}{r.mean.toFixed(1)}%</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Low σ (green) = consistent profit across windows · high σ (red) = erratic · sorted
						lowest to highest volatility
					</p>
				</section>
			{/if}

			{#if windowTopStrategyProfit}
				<section class="mt-8 rounded-xl border border-border bg-card p-5">
					<h2 class="text-base font-semibold">
						Window Peak Profit <ChartInfo metric="totalProfit" {lang} />
					</h2>
					<p class="mt-0.5 text-xs text-muted-foreground">
						Best single-strategy profit% achieved per walk-forward window
					</p>
					<div class="mt-3 space-y-1">
						{#each windowTopStrategyProfit as r, _i (_i)}
							<div class="flex items-center gap-2">
								<span class="w-28 truncate font-mono text-[10px] text-muted-foreground">{r.wl}</span
								>
								<div
									class="flex-1 overflow-hidden rounded-sm"
									style="height:14px; background:var(--ch-rule-faint)"
								>
									<div
										class="h-full rounded-sm transition-all"
										style="width:{r.barPct}%; background:{r.positive
											? 'var(--ch-profit)'
											: 'var(--ch-loss)'}"
									></div>
								</div>
								<span class="w-20 truncate text-right font-mono text-[10px] text-muted-foreground"
									>{r.bestStrat.slice(0, 10)}</span
								>
								<span
									class="w-12 text-right font-mono text-[10px]"
									style="color:{r.positive ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
									>{r.best >= 0 ? '+' : ''}{r.best.toFixed(1)}%</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Green = profitable window best · red = even best strategy lost · strategy name shows who
						topped each window
					</p>
				</section>
			{/if}

			{#if strategyConsistencyScore}
				<section class="mt-8 rounded-xl border border-border bg-card p-5">
					<h2 class="text-base font-semibold">
						Strategy Consistency Score <ChartInfo metric="wfConsistency" {lang} />
					</h2>
					<p class="mt-0.5 text-xs text-muted-foreground">
						Fraction of walk-forward windows where each strategy was profitable (min 3 windows)
					</p>
					<div class="mt-3 space-y-1.5">
						{#each strategyConsistencyScore as r, _i (_i)}
							<div class="flex items-center gap-2">
								<span class="w-32 truncate font-mono text-[10px] text-muted-foreground"
									>{r.strategy}</span
								>
								<div
									class="flex-1 overflow-hidden rounded-sm"
									style="height:14px; background:var(--ch-rule-faint)"
								>
									<div
										class="h-full rounded-sm"
										style="width:{(r.score * 100).toFixed(1)}%; background:{r.score >= 0.7
											? 'var(--ch-profit)'
											: r.score >= 0.5
												? 'var(--ch-warn)'
												: 'var(--ch-loss)'}"
									></div>
								</div>
								<span
									class="w-10 text-right font-mono text-[10px]"
									style="color:{r.score >= 0.7
										? 'var(--ch-profit-solid)'
										: r.score >= 0.5
											? 'var(--ch-warn)'
											: 'var(--ch-loss-solid)'}">{(r.score * 100).toFixed(0)}%</span
								>
								<span class="w-14 text-right font-mono text-[9px] text-muted-foreground"
									>{r.profitable}/{r.total} win</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Green ≥70% · yellow 50–70% · red &lt;50% · high consistency = strategy works across
						varied market regimes
					</p>
				</section>
			{/if}

			{#if strategyAvgTradesRanking}
				<section class="mt-8 rounded-xl border border-border bg-card p-5">
					<h2 class="text-base font-semibold">
						Avg Trades per Window by Strategy <ChartInfo metric="wfConsistency" {lang} />
					</h2>
					<p class="mt-0.5 text-xs text-muted-foreground">
						Average number of trades per walk-forward window per strategy (min 2 windows)
					</p>
					<div class="mt-3 space-y-1.5">
						{#each strategyAvgTradesRanking as r, _i (_i)}
							<div class="flex items-center gap-2">
								<span class="w-32 truncate font-mono text-[10px] text-muted-foreground"
									>{r.strategy}</span
								>
								<div
									class="flex-1 overflow-hidden rounded-sm"
									style="height:14px; background:var(--ch-rule-faint)"
								>
									<div
										class="h-full rounded-sm"
										style="width:{r.barPct}%; background:var(--ch-teal)"
									></div>
								</div>
								<span
									class="w-12 text-right font-mono text-[10px]"
									style="color:var(--ch-teal-strong)">{r.avg.toFixed(1)}</span
								>
								<span class="w-14 text-right font-mono text-[9px] text-muted-foreground"
									>{r.windows}w</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						High avg trades = active strategy with many signals · low = selective strategy · compare
						with profit to assess trade quality vs quantity
					</p>
				</section>
			{/if}

			{#if strategyWinWindowRatio}
				<section class="mt-8 rounded-xl border border-border bg-card p-5">
					<h2 class="text-base font-semibold">
						Strategy Window Win Rate <ChartInfo metric="winRate" {lang} />
					</h2>
					<p class="mt-0.5 text-xs text-muted-foreground">
						% of walk-forward windows each strategy finished profitable (min 3 windows) — robustness
						across regimes
					</p>
					<div class="mt-3 space-y-1.5">
						{#each strategyWinWindowRatio as r, i (i)}
							<div class="flex items-center gap-2">
								<span class="w-5 text-right font-mono text-[10px] text-muted-foreground"
									>{i + 1}</span
								>
								<span class="w-32 truncate font-mono text-[10px] text-muted-foreground"
									>{r.strategy}</span
								>
								<div
									class="flex-1 overflow-hidden rounded-sm"
									style="height:14px; background:var(--ch-rule-faint)"
								>
									<div
										class="h-full rounded-sm"
										style="width:{r.barPct}%; background:{r.winRatio >= 0.6
											? 'var(--ch-profit)'
											: r.winRatio >= 0.4
												? 'var(--ch-warn)'
												: 'var(--ch-loss-light)'}"
									></div>
								</div>
								<span
									class="w-14 text-right font-mono text-[10px]"
									style="color:{r.winRatio >= 0.6
										? 'var(--ch-profit-solid)'
										: r.winRatio >= 0.4
											? 'var(--ch-warn)'
											: 'var(--ch-loss-solid)'}">{(r.winRatio * 100).toFixed(0)}%</span
								>
								<span class="w-14 text-right font-mono text-[9px] text-muted-foreground"
									>{r.wins}/{r.total}w</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Green ≥60% = consistently profitable across regimes · yellow = mixed · red = struggled
						across most windows · favour green strategies in live deployment
					</p>
				</section>
			{/if}

			{#if windowAvgProfitTimeline}
				<section class="mt-8 rounded-xl border border-border bg-card p-5">
					<h2 class="text-base font-semibold">
						Window Average Profit Timeline <ChartInfo metric="totalProfit" {lang} />
					</h2>
					<p class="mt-0.5 text-xs text-muted-foreground">
						Average profit% per walk-forward window across all strategies — identifies which periods
						were collectively profitable
					</p>
					<div class="mt-3 flex items-end gap-1" style="height:72px">
						{#each windowAvgProfitTimeline as r, _i (_i)}
							<div class="flex flex-1 flex-col items-center gap-0.5">
								<span
									class="font-mono text-[7px]"
									style="color:{r.avg >= 0 ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
								>
									{r.avg >= 0 ? '+' : ''}{r.avg.toFixed(0)}
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
					<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
						<span>{windowAvgProfitTimeline[0].wl.slice(0, 10)}</span><span>→ window →</span><span
							>{windowAvgProfitTimeline[windowAvgProfitTimeline.length - 1].wl.slice(0, 10)}</span
						>
					</div>
					<p class="mt-1 text-[10px] text-muted-foreground">
						Green = profitable window on average · red = regime where most strategies lost ·
						sequence of reds = difficult market period for all strategies
					</p>
				</section>
			{/if}

			{#if strategyBestSingleWindow}
				<section class="mt-8 rounded-xl border border-border bg-card p-5">
					<h2 class="text-base font-semibold">
						Strategy Best Single Window Profit <ChartInfo metric="leaderboard" {lang} />
					</h2>
					<p class="mt-0.5 text-xs text-muted-foreground">
						Top 10 strategies by their single highest profit% in any walk-forward window — peak
						performance potential
					</p>
					<div class="mt-3 space-y-1.5">
						{#each strategyBestSingleWindow as r, i (i)}
							<div class="flex items-center gap-2">
								<span class="w-5 text-right font-mono text-[10px] text-muted-foreground"
									>{i + 1}</span
								>
								<span class="w-32 truncate font-mono text-[10px] text-muted-foreground"
									>{r.strategy}</span
								>
								<div
									class="flex-1 overflow-hidden rounded-sm"
									style="height:14px; background:var(--ch-rule-faint)"
								>
									<div
										class="h-full rounded-sm"
										style="width:{r.barPct}%; background:{r.best >= 0
											? 'var(--ch-profit)'
											: 'var(--ch-loss-light)'}"
									></div>
								</div>
								<span
									class="w-16 text-right font-mono text-[10px]"
									style="color:{r.best >= 0 ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
									>{r.best >= 0 ? '+' : ''}{r.best.toFixed(1)}%</span
								>
								<span class="w-10 text-right font-mono text-[9px] text-muted-foreground"
									>{r.windows}w</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Best window profit shows peak opportunity · combine with strategyWinWindowRatio to
						distinguish consistently good vs occasionally great strategies
					</p>
				</section>
			{/if}

			{#if windowLoserCount}
				<section class="mt-8 rounded-xl border border-border bg-card p-5">
					<h2 class="text-base font-semibold">
						Window Loser Count <ChartInfo metric="wfConsistency" {lang} />
					</h2>
					<p class="mt-0.5 text-xs text-muted-foreground">
						Strategies that lost money per walk-forward window — high count = harsh market regime
					</p>
					<div class="mt-3 space-y-1">
						{#each windowLoserCount as r, _i (_i)}
							<div class="flex items-center gap-2">
								<span class="w-28 truncate font-mono text-[10px] text-muted-foreground">{r.wl}</span
								>
								<div
									class="flex-1 overflow-hidden rounded-sm"
									style="height:12px; background:var(--ch-rule-faint)"
								>
									<div
										class="h-full rounded-sm"
										style="width:{r.barPct}%; background:rgba(239,68,68,{0.4 + r.loserPct * 0.4})"
									></div>
								</div>
								<span
									class="w-10 text-right font-mono text-[10px]"
									style="color:var(--ch-loss-solid)">{r.losers}</span
								>
								<span class="w-12 text-right font-mono text-[9px] text-muted-foreground"
									>{(r.loserPct * 100).toFixed(0)}% lose</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Tall red bar = window where most strategies failed · useful for identifying bearish or
						choppy regime windows
					</p>
				</section>
			{/if}

			{#if strategyAvgProfitPerTrade}
				<section class="rounded-xl border border-border bg-card p-5">
					<h2 class="text-sm font-semibold">
						Strategy Avg Profit per Trade (WF) <ChartInfo metric="avgProfit" {lang} />
					</h2>
					<p class="mb-3 text-[11px] text-muted-foreground">
						Average profit% per individual trade across all walk-forward windows (≥5 trades, ≥2
						windows)
					</p>
					<div class="space-y-1">
						{#each strategyAvgProfitPerTrade as r, _i (_i)}
							<div class="flex items-center gap-2">
								<span class="w-32 truncate text-right font-mono text-[10px] text-muted-foreground"
									>{r.strat}</span
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
									>n={r.trades}</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Profit-per-trade across WF windows shows efficiency net of signal frequency · high value
						= each trade carrying more weight
					</p>
				</section>
			{/if}

			{#if windowTotalProfitDistribution}
				{@const wtpd = windowTotalProfitDistribution}
				<section class="rounded-xl border border-border bg-card p-5">
					<h2 class="text-sm font-semibold">
						Window Profit Distribution <ChartInfo metric="distribution" {lang} />
					</h2>
					<p class="mb-3 text-[11px] text-muted-foreground">
						Histogram of total profit% across all WF windows · median {wtpd.median.toFixed(1)}% · {wtpd.positive}/{wtpd.total}
						profitable
					</p>
					<div class="flex items-end gap-1" style="height:64px">
						{#each wtpd.buckets as b, _i (_i)}
							<div class="flex flex-1 flex-col items-center gap-0.5">
								<span class="font-mono text-[7px] text-muted-foreground"
									>{b.count > 0 ? b.count : ''}</span
								>
								<div
									class="w-full rounded-sm"
									style="height:{b.barPct}%; background:{b.pos
										? 'var(--ch-profit)'
										: 'var(--ch-loss)'}; min-height:{b.count > 0 ? 2 : 0}px"
								></div>
							</div>
						{/each}
					</div>
					<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
						<span>{wtpd.buckets[0].label}</span><span>← window profit →</span><span
							>{wtpd.buckets[wtpd.buckets.length - 1].label}</span
						>
					</div>
					<p class="mt-1 text-[10px] text-muted-foreground">
						Right-skewed = most windows profitable · symmetric = mixed regime performance · left
						tail = occasional bad windows dragging returns
					</p>
				</section>
			{/if}

			{#if windowStrategyCount}
				<section class="rounded-xl border border-border bg-card p-5">
					<h2 class="text-sm font-semibold">
						Strategies per WF Window <ChartInfo metric="walkForward" {lang} />
					</h2>
					<p class="mb-3 text-[11px] text-muted-foreground">
						Number of distinct strategies participating in each walk-forward window · declining =
						strategies being retired
					</p>
					<div class="flex items-end gap-1" style="height:64px">
						{#each windowStrategyCount as r, _i (_i)}
							<div
								class="flex flex-1 flex-col items-center gap-0.5"
								title="{r.wl}: {r.count} strategies"
							>
								<span class="font-mono text-[7px] text-muted-foreground">{r.count}</span>
								<div
									class="w-full rounded-sm"
									style="height:{r.barPct}%; background:var(--ch-violet); min-height:2px"
								></div>
							</div>
						{/each}
					</div>
					<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
						<span>{windowStrategyCount[0].wl}</span><span>← window →</span><span
							>{windowStrategyCount[windowStrategyCount.length - 1].wl}</span
						>
					</div>
					<p class="mt-1 text-[10px] text-muted-foreground">
						Consistent bar height = stable strategy pool · drops = strategies excluded from later
						windows · rising = new strategies being added
					</p>
				</section>
			{/if}

			{#if strategyTimeframeWinWindowPct}
				{@const stww = strategyTimeframeWinWindowPct}
				<section class="rounded-xl border border-border bg-card p-5">
					<h2 class="text-sm font-semibold">
						Strategy × Timeframe Win Window % <ChartInfo metric="timeframe" {lang} />
					</h2>
					<p class="mb-2 text-[11px] text-muted-foreground">
						% of walk-forward windows with positive profit per strategy × timeframe (≥3 windows) ·
						green ≥60% · yellow 40–60% · red &lt;40%
					</p>
					<div class="overflow-x-auto">
						<table class="w-full text-[9px]">
							<thead>
								<tr>
									<th class="pr-2 text-right font-mono text-muted-foreground">Strategy</th>
									{#each stww.timeframes as tf, _i (_i)}
										<th class="px-1 text-center font-mono text-muted-foreground">{tf}</th>
									{/each}
								</tr>
							</thead>
							<tbody>
								{#each stww.cells as row, _i (_i)}
									<tr class="border-t border-border/30">
										<td
											class="max-w-[8rem] truncate py-0.5 pr-2 text-right font-mono text-muted-foreground"
											>{row.strategy}</td
										>
										{#each row.tfs as cell, _i (_i)}
											<td
												class="px-1 py-0.5 text-center font-mono"
												title="{cell.tf}: {cell.wr != null
													? (cell.wr * 100).toFixed(0) + '% (' + cell.total + ' windows)'
													: 'no data'}"
											>
												{#if cell.wr != null}
													<span
														class="inline-block rounded px-0.5"
														style="background:{cell.wr >= 0.6
															? 'var(--ch-profit-light)'
															: cell.wr >= 0.4
																? 'var(--ch-warn-light)'
																: 'var(--ch-loss-light)'}; color:{cell.wr >= 0.6
															? 'var(--ch-profit-solid)'
															: cell.wr >= 0.4
																? 'var(--ch-warn)'
																: 'var(--ch-loss-solid)'}">{(cell.wr * 100).toFixed(0)}%</span
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
						High % across multiple timeframes = robust strategy · high only on one TF =
						timeframe-specific edge · use for live timeframe selection
					</p>
				</section>
			{/if}

			{#if windowProfitByTimeframe}
				<section class="rounded-xl border border-border bg-card p-5">
					<h2 class="text-sm font-semibold">
						Avg Window Profit by Timeframe <ChartInfo metric="totalProfit" {lang} />
					</h2>
					<p class="mb-3 text-[11px] text-muted-foreground">
						Average tot_profit% per walk-forward window, grouped by timeframe (≥5 windows) · reveals
						which TFs produce more profitable windows
					</p>
					<div class="space-y-1">
						{#each windowProfitByTimeframe as r, _i (_i)}
							<div class="flex items-center gap-2">
								<span class="w-10 text-right font-mono text-[11px] text-muted-foreground"
									>{r.tf}</span
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
									class="w-16 text-right font-mono text-[10px]"
									style="color:{r.positive ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
									>{r.avg > 0 ? '+' : ''}{r.avg.toFixed(2)}%</span
								>
								<span class="w-12 text-right font-mono text-[9px] text-muted-foreground"
									>{(r.winPct * 100).toFixed(0)}% win</span
								>
								<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
									>n={r.count}</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						High avg profit + high win % = most reliable timeframe for walk-forward testing · use to
						choose primary TF for live deployment
					</p>
				</section>
			{/if}

			{#if windowStrategyProfitRanking}
				<section class="rounded-xl border border-border bg-card p-5">
					<h2 class="text-sm font-semibold">
						Total WF Profit by Strategy <ChartInfo metric="totalProfit" {lang} />
					</h2>
					<p class="mb-3 text-[11px] text-muted-foreground">
						Sum of tot_profit% across all walk-forward windows per strategy (≥3 windows) · shows
						cumulative WF performance
					</p>
					<div class="space-y-1">
						{#each windowStrategyProfitRanking as r, _i (_i)}
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
									class="w-16 text-right font-mono text-[10px]"
									style="color:{r.positive ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
									>{r.total > 0 ? '+' : ''}{r.total.toFixed(1)}%</span
								>
								<span class="w-10 text-right font-mono text-[9px] text-muted-foreground"
									>{(r.wr * 100).toFixed(0)}% WR</span
								>
								<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
									>n={r.count}</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Total WF profit = sum across all time windows · high WR + high total = most consistent
						walk-forward performer · prioritise for live trading
					</p>
				</section>
			{/if}
			{#if windowLabelProfitTimeline}
				{@const wlpt = windowLabelProfitTimeline}
				<section class="rounded-lg border border-border bg-card p-4">
					<h2 class="mb-1 text-sm font-semibold">
						Walk-Forward Window Profit Timeline <ChartInfo metric="walkForward" {lang} />
					</h2>
					<p class="mb-3 text-[11px] text-muted-foreground">
						Avg profit across all strategies per WF window · shows market regime difficulty over
						time
					</p>
					<svg viewBox="0 0 {wlpt.W} {wlpt.H}" class="w-full" style="height:82px">
						<line
							x1={wlpt.PAD}
							y1={wlpt.zeroY}
							x2={wlpt.W - wlpt.PAD}
							y2={wlpt.zeroY}
							stroke="var(--ch-axis-muted)"
							stroke-width="1"
							stroke-dasharray="3,3"
						/>
						{#each wlpt.rows as r, i (i)}
							{@const x =
								wlpt.PAD + (i / Math.max(1, wlpt.rows.length - 1)) * (wlpt.W - wlpt.PAD * 2)}
							{@const y =
								wlpt.H -
								wlpt.PAD -
								((r.avg - Math.min(...wlpt.rows.map((rr) => rr.avg))) /
									(Math.max(...wlpt.rows.map((rr) => rr.avg)) -
										Math.min(...wlpt.rows.map((rr) => rr.avg)) || 0.001)) *
									(wlpt.H - wlpt.PAD * 2)}
							<circle
								cx={x}
								cy={y}
								r="2.5"
								fill={r.avg >= 0 ? 'var(--ch-profit-strong)' : 'var(--ch-loss)'}
							/>
						{/each}
						<polyline points={wlpt.poly} fill="none" stroke="var(--ch-violet)" stroke-width="1.5" />
					</svg>
					<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
						<span>{wlpt.first}</span><span>← walk-forward windows →</span><span>{wlpt.last}</span>
					</div>
					<p class="mt-1 text-[10px] text-muted-foreground">
						Green dots = profitable windows · red = losing market regime · rising trend = strategy
						suite adapting well · falling = regime change hurting all strategies
					</p>
				</section>
			{/if}
			{#if strategyWorstWindowLoss}
				<section class="rounded-lg border border-border bg-card p-4">
					<h2 class="mb-3 text-sm font-semibold">
						Strategy Worst Single Window Loss <ChartInfo metric="totalProfit" {lang} />
					</h2>
					<div class="space-y-1">
						{#each strategyWorstWindowLoss as r, _i (_i)}
							<div class="flex items-center gap-2">
								<span class="w-36 truncate text-right font-mono text-[10px] text-muted-foreground"
									>{r.strategy}</span
								>
								<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
									<div
										class="h-full rounded-sm"
										style="width:{r.barPct}%; background:var(--ch-loss)"
									></div>
								</div>
								<span class="w-16 text-right font-mono text-[10px] text-red-400"
									>{r.worst.toFixed(1)}%</span
								>
								<span class="w-20 truncate text-right font-mono text-[9px] text-muted-foreground"
									>{r.worstLabel}</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Worst single walk-forward window loss per strategy · sorted least-bad first · high loss
						= regime sensitivity · use to set position sizing and risk limits
					</p>
				</section>
			{/if}
			{#if strategyConsecutiveLossWindows}
				<section class="rounded-xl border border-border bg-card p-4">
					<h2 class="mb-1 text-sm font-semibold">
						Max Consecutive Losing Windows <ChartInfo metric="wfConsistency" {lang} />
					</h2>
					<p class="mb-3 text-[10px] text-muted-foreground">
						Longest unbroken streak of walk-forward windows with negative profit per strategy —
						measures drawdown duration risk
					</p>
					<div class="space-y-2">
						{#each strategyConsecutiveLossWindows as r, _i (_i)}
							{@const ratio = r.maxStreak / r.total}
							{@const color =
								ratio < 0.25
									? 'var(--ch-profit-strong)'
									: ratio < 0.5
										? 'var(--ch-warn)'
										: 'var(--ch-loss-strong)'}
							<div class="flex items-center gap-2">
								<span
									class="w-36 truncate text-right font-mono text-[10px] text-muted-foreground"
									title={r.strategy}>{r.strategy}</span
								>
								<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
									<div
										class="h-full rounded-sm"
										style="width:{r.barPct}%; background:{color}"
									></div>
								</div>
								<span class="w-12 text-right font-mono text-[10px]" style="color:{color}"
									>{r.maxStreak}× loss</span
								>
								<span class="w-14 text-right font-mono text-[9px] text-muted-foreground"
									>of {r.total} wins</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Green ≤25% of windows losing consecutively · yellow ≤50% · red majority consecutive
						losses = strategy struggles in extended regimes
					</p>
				</section>
			{/if}
			{#if windowCumulativeProfitByStrategy}
				<section class="rounded-xl border border-border bg-card p-4">
					<h2 class="mb-1 text-sm font-semibold">
						Cumulative WF Profit by Strategy <ChartInfo metric="totalProfit" {lang} />
					</h2>
					<p class="mb-3 text-[10px] text-muted-foreground">
						Running cumulative total profit % across walk-forward windows (chronological) — top 5
						strategies by final cumulative score
					</p>
					<svg
						viewBox="0 0 {windowCumulativeProfitByStrategy.W} {windowCumulativeProfitByStrategy.H}"
						class="w-full"
					>
						<line
							x1="0"
							y1={windowCumulativeProfitByStrategy.zeroY}
							x2={windowCumulativeProfitByStrategy.W}
							y2={windowCumulativeProfitByStrategy.zeroY}
							stroke="var(--ch-axis-faint)"
							stroke-width="1"
							stroke-dasharray="3,2"
						/>
						{#each windowCumulativeProfitByStrategy.polylines as l, _i (_i)}
							<polyline points={l.poly} fill="none" stroke={l.color} stroke-width="1.5" />
						{/each}
					</svg>
					<div class="mt-2 flex flex-wrap gap-3">
						{#each windowCumulativeProfitByStrategy.polylines as l, _i (_i)}
							<span class="flex items-center gap-1 font-mono text-[9px] text-muted-foreground">
								<span class="inline-block h-1.5 w-4 rounded-sm" style="background:{l.color}"></span>
								{l.strategy} ({l.final > 0 ? '+' : ''}{l.final.toFixed(1)}%)
							</span>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Monotone rising = consistent across all windows · flat or falling = struggling in recent
						periods · divergence = different regime sensitivity
					</p>
				</section>
			{/if}
			{#if windowProfitConcentration}
				<section class="rounded-xl border border-border bg-card p-4">
					<h2 class="mb-1 text-sm font-semibold">
						Top-Strategy Profit Share per Window <ChartInfo metric="leaderboard" {lang} />
					</h2>
					<p class="mb-3 text-[10px] text-muted-foreground">
						% of each window's total positive profit captured by the single best strategy — high =
						one strategy dominates, low = profits spread across strategies
					</p>
					<div class="space-y-1">
						{#each windowProfitConcentration as r, _i (_i)}
							{@const color =
								r.topShare > 80
									? 'var(--ch-loss)'
									: r.topShare > 50
										? 'var(--ch-warn)'
										: 'var(--ch-profit-strong)'}
							<div class="flex items-center gap-2">
								<span class="w-20 truncate font-mono text-[10px] text-muted-foreground"
									>{r.label}</span
								>
								<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
									<div
										class="h-full rounded-sm"
										style="width:{r.barPct}%; background:{color}"
									></div>
								</div>
								<span class="w-12 text-right font-mono text-[10px]" style="color:{color}"
									>{r.topShare.toFixed(0)}%</span
								>
								<span
									class="w-28 truncate text-right font-mono text-[9px] text-muted-foreground"
									title={r.topStrategy}>{r.topStrategy}</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Green ≤50% = diverse profits · yellow = moderate concentration · red ≥80% = single
						strategy dominates · consistent leader across windows = reliable alpha source
					</p>
				</section>
			{/if}

			{#if strategyAvgProfitTrend}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-1 text-sm font-semibold">Strategy Avg Profit Trend (Slope)</h3>
					<p class="mb-3 text-[10px] text-muted-foreground">
						Linear regression slope of avg_profit_pct over walk-forward windows · positive =
						improving over time · negative = degrading · sorted by steepest improvement
					</p>
					<div class="space-y-1.5">
						{#each strategyAvgProfitTrend.rows as row, _i (_i)}
							{@const color = row.slope > 0 ? 'var(--ch-profit-strong)' : 'var(--ch-loss)'}
							<div class="flex items-center gap-2 text-xs">
								<span class="w-36 shrink-0 truncate font-mono text-[10px]">{row.strategy}</span>
								<div class="relative h-4 flex-1 overflow-hidden rounded bg-muted/30">
									<div
										class="h-full rounded"
										style="width:{(
											(Math.abs(row.slope) / strategyAvgProfitTrend.maxSlope) *
											100
										).toFixed(1)}%; background:{color}"
									></div>
								</div>
								<span class="w-14 text-right font-mono text-[10px]" style="color:{color}"
									>{row.slope > 0 ? '+' : ''}{row.slope.toFixed(3)}</span
								>
								<span class="w-8 text-right text-[9px] text-muted-foreground">n={row.count}</span>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[9px] text-muted-foreground">
						Slope = change in avg profit % per window step · green = improving · red = degrading ·
						strategies with positive slope are adapting well to new market conditions
					</p>
				</section>
			{/if}

			{#if windowMedianTradeTimeline}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-1 text-sm font-semibold">Median Trade Count per Window (Timeline)</h3>
					<p class="mb-2 text-[10px] text-muted-foreground">
						Median trades across all strategies per walk-forward window over time · rising = more
						active signals · falling = market going quiet or strategy filtering more aggressively
					</p>
					<svg
						viewBox="0 0 {windowMedianTradeTimeline.W} {windowMedianTradeTimeline.H}"
						class="w-full"
					>
						<line
							x1="0"
							y1={windowMedianTradeTimeline.avgY}
							x2={windowMedianTradeTimeline.W}
							y2={windowMedianTradeTimeline.avgY}
							stroke="var(--ch-warn-light)"
							stroke-width="1"
							stroke-dasharray="4,3"
						/>
						<polyline
							points={windowMedianTradeTimeline.polyline}
							fill="none"
							stroke="var(--ch-violet-strong)"
							stroke-width="2"
						/>
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						{windowMedianTradeTimeline.count} windows · latest median = {windowMedianTradeTimeline.latest.toFixed(
							0
						)} trades · avg = {windowMedianTradeTimeline.avg.toFixed(0)} · trend {windowMedianTradeTimeline.trend >
						2
							? '↑ increasing activity'
							: windowMedianTradeTimeline.trend < -2
								? '↓ declining activity'
								: '→ stable'}
					</p>
				</section>
			{/if}

			{#if windowNetProfitVsParticipation}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-1 text-sm font-semibold">Window Net Profit vs Strategy Participation</h3>
					<p class="mb-2 text-[10px] text-muted-foreground">
						Each dot = one walk-forward window · x = number of strategies active · y = sum of
						tot_profit_pct · windows with many strategies AND high profit = broad market opportunity
					</p>
					<svg
						viewBox="0 0 {windowNetProfitVsParticipation.W} {windowNetProfitVsParticipation.H}"
						class="w-full"
					>
						{#if windowNetProfitVsParticipation.zeroY !== null}
							<line
								x1="0"
								y1={windowNetProfitVsParticipation.zeroY}
								x2={windowNetProfitVsParticipation.W}
								y2={windowNetProfitVsParticipation.zeroY}
								stroke="var(--ch-axis-faint)"
								stroke-width="1"
								stroke-dasharray="4,3"
							/>
						{/if}
						{#each windowNetProfitVsParticipation.dots as d, _i (_i)}
							<circle
								cx={d.cx}
								cy={d.cy}
								r="3"
								fill={d.positive ? 'var(--ch-profit)' : 'var(--ch-loss)'}
							/>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						{windowNetProfitVsParticipation.total} windows · x=strategies [{windowNetProfitVsParticipation.xMin}–{windowNetProfitVsParticipation.xMax}]
						· y=net profit [{windowNetProfitVsParticipation.yMin}%–{windowNetProfitVsParticipation.yMax}%]
						· green = profitable · red = losing windows
					</p>
				</section>
			{/if}

			{#if windowAvgProfitByStrategy}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-1 text-sm font-semibold">Strategy Avg Window Profit</h3>
					<p class="mb-2 text-[10px] text-muted-foreground">
						Average tot_profit_pct across all walk-forward windows per strategy · measures how
						consistently each strategy extracts profit across time slices
					</p>
					<div class="space-y-1">
						{#each windowAvgProfitByStrategy.rows as row, _i (_i)}
							{@const color = row.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
							{@const pct = ((Math.abs(row.avg) / windowAvgProfitByStrategy.maxAbs) * 100).toFixed(
								1
							)}
							<div class="flex items-center gap-2 text-[10px]">
								<span class="w-36 truncate font-mono text-[9px]">{row.strategy}</span>
								<div class="flex h-3 flex-1 overflow-hidden rounded bg-muted/30">
									<div class="h-full rounded" style="width:{pct}%; background:{color}"></div>
								</div>
								<span class="w-14 text-right font-mono" style="color:{color}"
									>{row.avg.toFixed(2)}%</span
								>
								<span class="w-10 text-right text-muted-foreground">n={row.count}</span>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[9px] text-muted-foreground">
						Strategies sorted by avg window profit · green = positive average · red = net losing
						across windows · n = number of WF windows participated in
					</p>
				</section>
			{/if}

			{#if windowTradeCountByStrategy}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-1 text-sm font-semibold">Avg Trades per WF Window by Strategy</h3>
					<p class="mb-2 text-[10px] text-muted-foreground">
						Average number of trades per walk-forward window per strategy · high = active signal
						generation · low = selective or slow-moving strategy
					</p>
					<div class="space-y-1">
						{#each windowTradeCountByStrategy.rows as row, _i (_i)}
							{@const pct = ((row.avg / windowTradeCountByStrategy.maxAvg) * 100).toFixed(1)}
							{@const color = `rgba(99,102,241,${(0.4 + (row.avg / windowTradeCountByStrategy.maxAvg) * 0.45).toFixed(2)})`}
							<div class="flex items-center gap-2 text-[10px]">
								<span class="w-36 truncate font-mono text-[9px]">{row.strategy}</span>
								<div class="flex h-3 flex-1 overflow-hidden rounded bg-muted/30">
									<div class="h-full rounded" style="width:{pct}%; background:{color}"></div>
								</div>
								<span class="w-14 text-right font-mono text-muted-foreground"
									>{row.avg.toFixed(0)}</span
								>
								<span class="w-10 text-right text-[9px] text-muted-foreground">n={row.count}</span>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[9px] text-muted-foreground">
						Avg trades per window · total trades = avg × windows · very low avg (&lt;5/window) may
						lack statistical significance in any single WF period
					</p>
				</section>
			{/if}

			{#if windowStatusBreakdown}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-1 text-sm font-semibold">Window Win/Loss Breakdown by Strategy</h3>
					<p class="mb-2 text-[10px] text-muted-foreground">
						For each strategy: how many WF windows were profitable vs losing · sorted by win % ·
						reveals consistency across time periods
					</p>
					<div class="space-y-1">
						{#each windowStatusBreakdown.rows as row, _i (_i)}
							<div class="flex items-center gap-2 text-[10px]">
								<span class="w-36 truncate font-mono text-[9px]">{row.strategy}</span>
								<div class="flex h-3 flex-1 overflow-hidden rounded">
									<div
										class="h-full"
										style="width:{row.winPct.toFixed(1)}%; background:var(--ch-profit)"
									></div>
									<div
										class="h-full"
										style="width:{((row.flat / row.total) * 100).toFixed(
											1
										)}%; background:var(--ch-axis-muted)"
									></div>
									<div
										class="h-full"
										style="width:{((row.loss / row.total) * 100).toFixed(
											1
										)}%; background:var(--ch-loss)"
									></div>
								</div>
								<span class="w-20 text-right text-[9px] text-muted-foreground"
									>{row.win}W/{row.loss}L/{row.flat}F</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[9px] text-muted-foreground">
						Green = profitable windows · gray = flat (±0.1%) · red = losing windows · high green % =
						consistent performer across time slices
					</p>
				</section>
			{/if}

			{#if windowProfitVolatilityByStrategy}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Window Profit Consistency (Low CV = Stable)
					</h3>
					<div class="space-y-1">
						{#each windowProfitVolatilityByStrategy.rows as row, _i (_i)}
							{@const stdPct = ((row.std / windowProfitVolatilityByStrategy.maxStd) * 100).toFixed(
								1
							)}
							{@const meanPct = (
								(Math.abs(row.mean) / windowProfitVolatilityByStrategy.maxMeanAbs) *
								100
							).toFixed(1)}
							{@const isPos = row.mean >= 0}
							<div class="flex items-center gap-2">
								<span class="w-24 shrink-0 truncate text-[9px] text-muted-foreground"
									>{row.strategy}</span
								>
								<div class="relative h-3 flex-1 rounded bg-muted/20">
									<div
										class="absolute top-0 left-0 h-full rounded"
										style="width:{meanPct}%; background:{isPos
											? 'var(--ch-profit)'
											: 'var(--ch-loss)'}"
									></div>
									<div
										class="absolute top-0 left-0 h-full rounded"
										style="width:{stdPct}%; background:var(--ch-warn-light); mix-blend-mode:screen"
									></div>
								</div>
								<span
									class="w-12 text-right font-mono text-[9px]"
									style="color:{isPos ? 'var(--ch-profit-strong)' : 'var(--ch-loss-strong)'}"
									>{row.mean.toFixed(2)}%</span
								>
								<span class="w-12 text-right font-mono text-[9px] text-muted-foreground"
									>±{row.std.toFixed(2)}</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[9px] text-muted-foreground">
						Green = mean window profit · yellow overlay = std dev (wider = less consistent) · sorted
						by CV ascending · low CV strategies are most predictable
					</p>
				</section>
			{/if}

			{#if windowTimeframeWinRate}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Walk-Forward Win Rate by Timeframe
					</h3>
					<svg
						viewBox="0 0 {windowTimeframeWinRate.W} {windowTimeframeWinRate.H}"
						class="w-full"
						style="height:80px"
					>
						<line
							x1={windowTimeframeWinRate.PAD}
							y1={windowTimeframeWinRate.H / 2}
							x2={windowTimeframeWinRate.W - windowTimeframeWinRate.PAD}
							y2={windowTimeframeWinRate.H / 2}
							stroke="var(--ch-axis-muted)"
							stroke-width="1"
							stroke-dasharray="3,3"
						/>
						{#each windowTimeframeWinRate.rows as row, i (i)}
							{@const x =
								windowTimeframeWinRate.PAD +
								i *
									((windowTimeframeWinRate.W - windowTimeframeWinRate.PAD * 2) /
										windowTimeframeWinRate.rows.length)}
							{@const barH = Math.max(
								2,
								(row.winRate / 100) *
									(windowTimeframeWinRate.H - windowTimeframeWinRate.PAD * 2 - 12)
							)}
							{@const color =
								row.winRate >= 60
									? 'var(--ch-profit)'
									: row.winRate >= 50
										? 'var(--ch-violet)'
										: row.winRate >= 40
											? 'var(--ch-warn)'
											: 'var(--ch-loss)'}
							<rect
								{x}
								y={windowTimeframeWinRate.H - 12 - barH}
								width={windowTimeframeWinRate.BAR_W}
								height={barH}
								rx="2"
								fill={color}
							/>
							<text
								x={x + windowTimeframeWinRate.BAR_W / 2}
								y={windowTimeframeWinRate.H - 2}
								text-anchor="middle"
								font-size="8"
								fill="var(--ch-axis-strong)">{row.tf}</text
							>
							<text
								x={x + windowTimeframeWinRate.BAR_W / 2}
								y={windowTimeframeWinRate.H - 14 - barH}
								text-anchor="middle"
								font-size="8"
								fill={color}>{row.winRate.toFixed(0)}%</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						% of walk-forward windows with profit &gt;0.1% per timeframe · dashed = 50% line · green
						≥60% · red &lt;40%
					</p>
				</section>
			{/if}

			{#if windowBestWorstByStrategy}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Best &amp; Worst Window by Strategy
					</h3>
					<div class="space-y-1">
						{#each windowBestWorstByStrategy.rows as row, _i (_i)}
							{@const bestPct = ((row.best / windowBestWorstByStrategy.maxAbs) * 50).toFixed(1)}
							{@const worstPct = (
								(Math.abs(row.worst) / windowBestWorstByStrategy.maxAbs) *
								50
							).toFixed(1)}
							<div class="flex items-center gap-2">
								<span class="w-28 shrink-0 truncate text-[9px] text-muted-foreground"
									>{row.strategy}</span
								>
								<div class="relative flex h-3 flex-1 rounded bg-muted/20">
									<div
										class="absolute top-0 right-1/2 h-full rounded-l"
										style="width:{worstPct}%; background:var(--ch-loss)"
									></div>
									<div
										class="absolute top-0 left-1/2 h-full rounded-r"
										style="width:{bestPct}%; background:var(--ch-profit)"
									></div>
								</div>
								<span
									class="w-14 text-right font-mono text-[9px]"
									style="color:var(--ch-profit-strong)">+{row.best.toFixed(2)}%</span
								>
								<span
									class="w-14 text-right font-mono text-[9px]"
									style="color:var(--ch-loss-strong)">{row.worst.toFixed(2)}%</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[9px] text-muted-foreground">
						Green = best window profit · red = worst window loss · center = 0 · wide spread = high
						variance across time periods
					</p>
				</section>
			{/if}

			{#if windowStatusBreakdownByStrategy}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Walk-Forward Pass Rate by Strategy
					</h3>
					<div class="space-y-1.5">
						{#each windowStatusBreakdownByStrategy.rows as row, _i (_i)}
							<div class="flex items-center gap-2">
								<span class="w-36 shrink-0 truncate text-[9px] text-muted-foreground"
									>{row.strategy}</span
								>
								<div class="h-3 flex-1 overflow-hidden rounded bg-muted/20">
									<div
										class="h-full rounded"
										style="width:{row.passRate.toFixed(1)}%; background:var(--ch-profit)"
									></div>
								</div>
								<span
									class="w-10 text-right font-mono text-[10px]"
									style="color:var(--ch-profit-strong)">{row.passRate.toFixed(0)}%</span
								>
								<span class="w-14 text-right text-[9px] text-muted-foreground"
									>{row.pass}p / {row.fail}f</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[9px] text-muted-foreground">
						% of walk-forward windows that passed · sorted by pass rate · p=pass f=fail · higher =
						more robust out-of-sample performance
					</p>
				</section>
			{/if}

			{#if windowAvgProfitByTimeframe}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Avg Window Profit by Timeframe
					</h3>
					<svg
						viewBox="0 0 {windowAvgProfitByTimeframe.W} {windowAvgProfitByTimeframe.H}"
						class="w-full"
						style="height:80px"
					>
						<line
							x1="0"
							y1={windowAvgProfitByTimeframe.H / 2}
							x2={windowAvgProfitByTimeframe.W}
							y2={windowAvgProfitByTimeframe.H / 2}
							stroke="var(--ch-axis-faint)"
							stroke-width="1"
						/>
						{#each windowAvgProfitByTimeframe.rows as row, i (i)}
							{@const x =
								windowAvgProfitByTimeframe.PAD +
								i *
									((windowAvgProfitByTimeframe.W - windowAvgProfitByTimeframe.PAD * 2) /
										windowAvgProfitByTimeframe.rows.length)}
							{@const midY = windowAvgProfitByTimeframe.H / 2}
							{@const barH = Math.max(
								1,
								(Math.abs(row.avg) / windowAvgProfitByTimeframe.maxAbs) *
									(midY - windowAvgProfitByTimeframe.PAD - 8)
							)}
							{@const color = row.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
							{#if row.avg >= 0}
								<rect
									{x}
									y={midY - barH}
									width={windowAvgProfitByTimeframe.barW}
									height={barH}
									rx="2"
									fill={color}
								/>
							{:else}
								<rect
									{x}
									y={midY}
									width={windowAvgProfitByTimeframe.barW}
									height={barH}
									rx="2"
									fill={color}
								/>
							{/if}
							<text
								x={x + windowAvgProfitByTimeframe.barW / 2}
								y={windowAvgProfitByTimeframe.H - 2}
								text-anchor="middle"
								font-size="8"
								fill="var(--ch-axis)">{row.tf}</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg out-of-sample window profit per timeframe · green = profitable TFs · red = losing
						TFs · bars above/below center
					</p>
				</section>
			{/if}

			{#if windowTotalTradesByStrategy}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Total WF Trades by Strategy
					</h3>
					<div class="space-y-1.5">
						{#each windowTotalTradesByStrategy.rows as row, _i (_i)}
							{@const pct = ((row.trades / windowTotalTradesByStrategy.maxTrades) * 100).toFixed(1)}
							<div class="flex items-center gap-2">
								<span class="w-36 shrink-0 truncate text-[9px] text-muted-foreground"
									>{row.strategy}</span
								>
								<div class="h-3 flex-1 overflow-hidden rounded bg-muted/20">
									<div
										class="h-full rounded"
										style="width:{pct}%; background:var(--ch-violet)"
									></div>
								</div>
								<span class="w-14 text-right font-mono text-[10px] text-muted-foreground"
									>{row.trades}</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[9px] text-muted-foreground">
						Sum of trades across all WF windows per strategy · more trades = better statistical
						confidence in walk-forward results
					</p>
				</section>
			{/if}

			{#if windowProfitSpreadByStrategy}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Window Profit Spread by Strategy
					</h3>
					<svg
						viewBox="0 0 {windowProfitSpreadByStrategy.W} {windowProfitSpreadByStrategy.H}"
						class="w-full"
						style="height:{windowProfitSpreadByStrategy.H}px"
					>
						<line
							x1={windowProfitSpreadByStrategy.xs(0)}
							y1={windowProfitSpreadByStrategy.PAD}
							x2={windowProfitSpreadByStrategy.xs(0)}
							y2={windowProfitSpreadByStrategy.H - windowProfitSpreadByStrategy.PAD}
							stroke="var(--ch-axis-muted)"
							stroke-width="0.8"
							stroke-dasharray="3,2"
						/>
						{#each windowProfitSpreadByStrategy.rows as row, i (i)}
							{@const cy = windowProfitSpreadByStrategy.PAD + i * 16 + 8}
							{@const x1 = windowProfitSpreadByStrategy.xs(row.mn)}
							{@const x2 = windowProfitSpreadByStrategy.xs(row.mx)}
							{@const xm = windowProfitSpreadByStrategy.xs(row.med)}
							{@const color = row.med >= 0 ? 'var(--ch-violet)' : 'var(--ch-loss)'}
							<line
								{x1}
								y1={cy}
								{x2}
								y2={cy}
								stroke="var(--ch-axis-muted)"
								stroke-width="4"
								stroke-linecap="round"
							/>
							<rect
								x={x1}
								y={cy - 3}
								width={x2 - x1}
								height={6}
								rx="2"
								fill={color}
								opacity="0.5"
							/>
							<circle cx={xm} {cy} r="3" fill={color} />
							<text
								x={windowProfitSpreadByStrategy.PAD + 88}
								y={cy + 3.5}
								text-anchor="end"
								font-size="7"
								fill="var(--ch-axis-strong)">{row.strategy}</text
							>
						{/each}
						<text
							x={windowProfitSpreadByStrategy.xs(windowProfitSpreadByStrategy.globalMin)}
							y={windowProfitSpreadByStrategy.H}
							font-size="6.5"
							fill="var(--ch-axis-muted)"
							text-anchor="middle">{windowProfitSpreadByStrategy.globalMin.toFixed(1)}%</text
						>
						<text
							x={windowProfitSpreadByStrategy.xs(windowProfitSpreadByStrategy.globalMax)}
							y={windowProfitSpreadByStrategy.H}
							font-size="6.5"
							fill="var(--ch-axis-muted)"
							text-anchor="middle">{windowProfitSpreadByStrategy.globalMax.toFixed(1)}%</text
						>
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Min–max window profit range per strategy · bar width = consistency spread · dot = median
						· narrower bar = more consistent WF results
					</p>
				</section>
			{/if}

			{#if windowPassRateByTimeframe}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Pass Rate by Timeframe
					</h3>
					<svg
						viewBox="0 0 {windowPassRateByTimeframe.W} {windowPassRateByTimeframe.H}"
						class="w-full"
						style="height:80px"
					>
						{#each windowPassRateByTimeframe.rows as row, i (i)}
							{@const x =
								windowPassRateByTimeframe.PAD +
								i *
									((windowPassRateByTimeframe.W - windowPassRateByTimeframe.PAD * 2) /
										windowPassRateByTimeframe.rows.length)}
							{@const barH = Math.max(
								2,
								(row.rate / 100) *
									(windowPassRateByTimeframe.H - windowPassRateByTimeframe.PAD * 2 - 12)
							)}
							{@const color =
								row.rate >= 60
									? 'var(--ch-profit)'
									: row.rate >= 40
										? 'var(--ch-warn)'
										: 'var(--ch-loss)'}
							<rect
								{x}
								y={windowPassRateByTimeframe.H - 12 - barH}
								width={windowPassRateByTimeframe.barW}
								height={barH}
								rx="2"
								fill={color}
							/>
							<text
								x={x + windowPassRateByTimeframe.barW / 2}
								y={windowPassRateByTimeframe.H - 1}
								text-anchor="middle"
								font-size="8"
								fill="var(--ch-axis)">{row.tf}</text
							>
							<text
								x={x + windowPassRateByTimeframe.barW / 2}
								y={windowPassRateByTimeframe.H - 14 - barH}
								text-anchor="middle"
								font-size="7"
								fill={color}>{row.rate.toFixed(0)}%</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						% of WF windows passing per timeframe · green ≥60% · yellow 40–60% · red &lt;40% ·
						reveals which timeframes produce consistently out-of-sample profitable windows
					</p>
				</section>
			{/if}

			{#if windowAvgProfitHistogram}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Window Avg Profit Distribution
					</h3>
					<svg
						viewBox="0 0 {windowAvgProfitHistogram.W} {windowAvgProfitHistogram.H}"
						class="w-full"
						style="height:72px"
					>
						{#each windowAvgProfitHistogram.counts as b, i (i)}
							{@const x = windowAvgProfitHistogram.PAD + i * (windowAvgProfitHistogram.barW + 1)}
							{@const barH = Math.max(
								1,
								(b.count / windowAvgProfitHistogram.maxCount) *
									(windowAvgProfitHistogram.H - windowAvgProfitHistogram.PAD * 2 - 10)
							)}
							{@const color = b.lo >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
							<rect
								{x}
								y={windowAvgProfitHistogram.H - 10 - barH}
								width={windowAvgProfitHistogram.barW}
								height={barH}
								rx="1"
								fill={color}
							/>
						{/each}
						<text
							x={windowAvgProfitHistogram.PAD}
							y={windowAvgProfitHistogram.H - 1}
							font-size="7"
							fill="var(--ch-axis)">{windowAvgProfitHistogram.mn}%</text
						>
						<text
							x={windowAvgProfitHistogram.W - windowAvgProfitHistogram.PAD}
							y={windowAvgProfitHistogram.H - 1}
							text-anchor="end"
							font-size="7"
							fill="var(--ch-axis)">{windowAvgProfitHistogram.mx}%</text
						>
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						{windowAvgProfitHistogram.total} windows · avg {windowAvgProfitHistogram.avg}% · green =
						profitable windows · red = losing · right-skewed = more passing windows than losing
					</p>
				</section>
			{/if}

			{#if windowProfitByWindowLabel}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Avg Total Profit by Window Period
					</h3>
					<svg
						viewBox="0 0 {windowProfitByWindowLabel.W} {windowProfitByWindowLabel.H}"
						class="w-full"
						style="height:80px"
					>
						<line
							x1={windowProfitByWindowLabel.PAD}
							y1={windowProfitByWindowLabel.midY}
							x2={windowProfitByWindowLabel.W - windowProfitByWindowLabel.PAD}
							y2={windowProfitByWindowLabel.midY}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.8"
						/>
						{#each windowProfitByWindowLabel.rows as row, i (i)}
							{@const x = windowProfitByWindowLabel.PAD + i * (windowProfitByWindowLabel.barW + 2)}
							{@const bh = windowProfitByWindowLabel.toH(row.avg)}
							{@const positive = row.avg >= 0}
							{@const color = positive ? 'var(--ch-profit)' : 'var(--ch-loss)'}
							<rect
								{x}
								y={positive ? windowProfitByWindowLabel.midY - bh : windowProfitByWindowLabel.midY}
								width={windowProfitByWindowLabel.barW}
								height={bh}
								rx="1"
								fill={color}
							/>
							<text
								x={x + windowProfitByWindowLabel.barW / 2}
								y={windowProfitByWindowLabel.H - 1}
								text-anchor="middle"
								font-size="6"
								fill="var(--ch-axis)">{row.label}</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg total profit % per window period across all strategies · reveals whether
						profitability improves or degrades over time · green = profitable · red = losing
					</p>
				</section>
			{/if}

			{#if windowTradesByWindowLabel}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Total Trades per Window Period (all strategies)
					</h3>
					<svg
						viewBox="0 0 {windowTradesByWindowLabel.W} {windowTradesByWindowLabel.H}"
						class="w-full"
						style="height:72px"
					>
						{#each windowTradesByWindowLabel.rows as row, i (i)}
							{@const x = windowTradesByWindowLabel.PAD + i * (windowTradesByWindowLabel.barW + 2)}
							{@const barH = Math.max(
								2,
								(row.trades / windowTradesByWindowLabel.maxTrades) *
									(windowTradesByWindowLabel.H - windowTradesByWindowLabel.PAD * 2 - 12)
							)}
							{@const color =
								row.trades === windowTradesByWindowLabel.maxTrades
									? 'var(--ch-warn)'
									: 'var(--ch-violet)'}
							<rect
								{x}
								y={windowTradesByWindowLabel.H - 12 - barH}
								width={windowTradesByWindowLabel.barW}
								height={barH}
								rx="1"
								fill={color}
							/>
							<text
								x={x + windowTradesByWindowLabel.barW / 2}
								y={windowTradesByWindowLabel.H - 1}
								text-anchor="middle"
								font-size="6"
								fill="var(--ch-axis)">{row.label}</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Sum of all strategy trades per window period · yellow = busiest window · shows which
						out-of-sample periods had most market activity across tested strategies
					</p>
				</section>
			{/if}

			{#if windowStrategyPassRate}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Window Pass Rate by Strategy
					</h3>
					<div class="space-y-1.5">
						{#each windowStrategyPassRate.rows as row, i (i)}
							{@const color =
								row.rate >= 60
									? 'var(--ch-profit)'
									: row.rate >= 40
										? 'var(--ch-warn)'
										: 'var(--ch-loss)'}
							<div class="flex items-center gap-2">
								<span class="w-5 text-right text-[9px] text-muted-foreground">{i + 1}.</span>
								<span class="w-36 truncate text-[9px] text-muted-foreground">{row.strategy}</span>
								<div class="h-3 flex-1 overflow-hidden rounded bg-muted/20">
									<div
										class="h-full rounded"
										style="width:{row.rate.toFixed(1)}%; background:{color}"
									></div>
								</div>
								<span class="w-10 text-right font-mono text-[10px]" style="color:{color}"
									>{row.rate.toFixed(0)}%</span
								>
								<span class="w-12 text-right text-[9px] text-muted-foreground"
									>{row.pass}/{row.total}w</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[9px] text-muted-foreground">
						% of profitable out-of-sample windows per strategy · green ≥60% · yellow 40–60% · red
						&lt;40% · strategies with high pass rate are more robustly walk-forward optimized
					</p>
				</section>
			{/if}

			{#if windowProfitVsTradeCount}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Window Profit vs Trade Count Scatter ({windowProfitVsTradeCount.count} windows)
					</h3>
					<svg
						viewBox="0 0 {windowProfitVsTradeCount.W} {windowProfitVsTradeCount.H}"
						class="w-full"
						style="height:100px"
					>
						<line
							x1={windowProfitVsTradeCount.PAD}
							y1={windowProfitVsTradeCount.zeroY}
							x2={windowProfitVsTradeCount.W - windowProfitVsTradeCount.PAD}
							y2={windowProfitVsTradeCount.zeroY}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.8"
							stroke-dasharray="3,2"
						/>
						{#each windowProfitVsTradeCount.dots as d, _i (_i)}
							<circle cx={d.cx} cy={d.cy} r="2.5" fill={d.color} />
						{/each}
						<text
							x={windowProfitVsTradeCount.PAD}
							y={windowProfitVsTradeCount.H - 2}
							font-size="6.5"
							fill="var(--ch-axis-muted)">0 trades</text
						>
						<text
							x={windowProfitVsTradeCount.W - windowProfitVsTradeCount.PAD}
							y={windowProfitVsTradeCount.H - 2}
							text-anchor="end"
							font-size="6.5"
							fill="var(--ch-axis-muted)">{windowProfitVsTradeCount.tMax} trades</text
						>
						<text
							x={windowProfitVsTradeCount.PAD - 2}
							y={windowProfitVsTradeCount.PAD + 4}
							text-anchor="end"
							font-size="6"
							fill="var(--ch-axis-muted)">{windowProfitVsTradeCount.pMax}%</text
						>
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						x=trades in window · y=profit % · green=profitable · red=losing · windows with many
						trades and positive profit are ideal — high-frequency profitable windows
					</p>
				</section>
			{/if}
			{#if windowProfitCumulativeByStrategy}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Cumulative WF Profit by Strategy
					</h3>
					<svg
						viewBox="0 0 {windowProfitCumulativeByStrategy.W} {windowProfitCumulativeByStrategy.H}"
						class="w-full"
						style="height:90px"
					>
						<line
							x1={windowProfitCumulativeByStrategy.PAD}
							y1={windowProfitCumulativeByStrategy.zeroY}
							x2={windowProfitCumulativeByStrategy.W - windowProfitCumulativeByStrategy.PAD}
							y2={windowProfitCumulativeByStrategy.zeroY}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.8"
							stroke-dasharray="3,2"
						/>
						{#each windowProfitCumulativeByStrategy.polylines as line, _i (_i)}
							<polyline
								points={line.poly}
								fill="none"
								stroke={line.color}
								stroke-width="1.5"
								stroke-linejoin="round"
							/>
						{/each}
					</svg>
					<div class="mt-1 flex flex-wrap gap-2">
						{#each windowProfitCumulativeByStrategy.polylines as line, _i (_i)}
							<span class="text-[9px]" style="color:{line.color}">■ {line.strat}</span>
						{/each}
						<span class="text-[9px] text-muted-foreground"
							>· cumulative out-of-sample profit % across windows · rising = consistently profitable
							walk-forward</span
						>
					</div>
				</section>
			{/if}
			{#if windowDrawdownByStrategy}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Median Drawdown by Strategy
					</h3>
					<div class="space-y-1.5">
						{#each windowDrawdownByStrategy.rows as row, _i (_i)}
							{@const medW = (row.med / windowDrawdownByStrategy.maxVal) * 100}
							{@const maxW = (row.max / windowDrawdownByStrategy.maxVal) * 100}
							{@const color =
								row.med <= 5
									? 'var(--ch-profit)'
									: row.med <= 15
										? 'var(--ch-warn)'
										: 'var(--ch-loss)'}
							<div class="flex items-center gap-2">
								<span class="w-36 truncate text-right text-[10px] text-muted-foreground"
									>{row.strat}</span
								>
								<div class="relative h-3 flex-1 rounded bg-secondary/40">
									<div
										class="absolute top-0 left-0 h-3 rounded"
										style="width:{maxW}%;background:var(--ch-axis-faint)"
									></div>
									<div
										class="absolute top-0 left-0 h-3 rounded"
										style="width:{medW}%;background:{color}"
									></div>
								</div>
								<span class="w-12 text-right font-mono text-[10px]" style="color:{color}"
									>{row.med.toFixed(1)}%</span
								>
								<span class="w-5 text-right text-[9px] text-muted-foreground">{row.count}w</span>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[9px] text-muted-foreground">
						Median WF window drawdown per strategy (solid) + max (ghost) · green≤5% · yellow≤15% ·
						red&gt;15% · sorted best to worst
					</p>
				</section>
			{/if}
			{#if windowRollingMeanByStrategy}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Rolling 3-Window Mean Profit by Strategy
					</h3>
					<svg
						viewBox="0 0 {windowRollingMeanByStrategy.W} {windowRollingMeanByStrategy.H}"
						class="w-full"
						style="height:85px"
					>
						<line
							x1={windowRollingMeanByStrategy.PAD}
							y1={windowRollingMeanByStrategy.zeroY}
							x2={windowRollingMeanByStrategy.W - windowRollingMeanByStrategy.PAD}
							y2={windowRollingMeanByStrategy.zeroY}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.8"
							stroke-dasharray="3,2"
						/>
						{#each windowRollingMeanByStrategy.polylines as line, _i (_i)}
							<polyline
								points={line.poly}
								fill="none"
								stroke={line.color}
								stroke-width="1.5"
								stroke-linejoin="round"
							/>
						{/each}
					</svg>
					<div class="mt-1 flex flex-wrap gap-2">
						{#each windowRollingMeanByStrategy.polylines as line, _i (_i)}
							<span class="text-[9px]" style="color:{line.color}">■ {line.strat}</span>
						{/each}
						<span class="text-[9px] text-muted-foreground"
							>· smoothed WF profit trend (3-window rolling mean) · rising = strategy improving
							out-of-sample · stable above zero = robust walk-forward</span
						>
					</div>
				</section>
			{/if}
			{#if windowProfitStdByStrategy}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Profit Volatility by Strategy (std dev, sorted asc)
					</h3>
					<svg
						viewBox="0 0 {windowProfitStdByStrategy.W} {windowProfitStdByStrategy.H}"
						class="w-full"
						style="height:{windowProfitStdByStrategy.H}px"
					>
						{#each windowProfitStdByStrategy.rows as row, i (i)}
							{@const y = i * 16 + 2}
							{@const bw = Math.max(
								2,
								(row.std / windowProfitStdByStrategy.maxStd) * windowProfitStdByStrategy.barMaxW
							)}
							{@const color =
								row.std < 5
									? 'var(--ch-profit)'
									: row.std < 15
										? 'var(--ch-warn)'
										: 'var(--ch-loss)'}
							<text x="0" y={y + 9} font-size="7" fill="var(--ch-axis-strong)">{row.strat}</text>
							<rect x="135" {y} width={bw} height="11" rx="2" fill={color} />
							<text x={135 + bw + 3} y={y + 9} font-size="7" fill={color}
								>σ{row.std.toFixed(1)}%</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Standard deviation of WF window profit % per strategy (≥3 windows, sorted lowest first)
						· green&lt;5% · yellow&lt;15% · red≥15% · lower σ = more consistent walk-forward
						performance
					</p>
				</section>
			{/if}
			{#if windowBestWindowByStrategy}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Best Single Window Profit by Strategy
					</h3>
					<svg
						viewBox="0 0 {windowBestWindowByStrategy.W} {windowBestWindowByStrategy.H}"
						class="w-full"
						style="height:{windowBestWindowByStrategy.H}px"
					>
						{#each windowBestWindowByStrategy.rows as row, i (i)}
							{@const y = i * 16 + 2}
							{@const bw = Math.max(
								2,
								(row.bestProfit / windowBestWindowByStrategy.maxProfit) *
									windowBestWindowByStrategy.barMaxW
							)}
							{@const color =
								row.bestProfit >= 10
									? 'var(--ch-profit)'
									: row.bestProfit >= 0
										? 'var(--ch-warn)'
										: 'var(--ch-loss)'}
							<text x="0" y={y + 9} font-size="7" fill="var(--ch-axis-strong)">{row.strat}</text>
							<rect x="140" {y} width={bw} height="11" rx="2" fill={color} />
							<text x={140 + bw + 3} y={y + 9} font-size="6.5" fill={color}
								>{row.bestProfit >= 0 ? '+' : ''}{row.bestProfit.toFixed(1)}%</text
							>
							<text x={140 + bw + 38} y={y + 9} font-size="5.5" fill="var(--ch-axis-muted)"
								>{row.bestLabel}</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Best single out-of-sample window profit per strategy (sorted desc) · label shows which
						window · green≥10% · yellow≥0% · reveals peak out-of-sample performance
					</p>
				</section>
			{/if}
			{#if windowPassRateTrend}
				<section class="mt-6 rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Pass Rate Trend by Month
					</h3>
					<svg
						viewBox="0 0 {windowPassRateTrend.W} {windowPassRateTrend.H}"
						class="w-full"
						style="height:68px"
					>
						<line
							x1={windowPassRateTrend.PAD}
							y1={windowPassRateTrend.y50}
							x2={windowPassRateTrend.W - windowPassRateTrend.PAD}
							y2={windowPassRateTrend.y50}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.7"
							stroke-dasharray="3,2"
						/>
						<polygon points={windowPassRateTrend.area} fill="var(--ch-profit-light)" />
						<polyline
							points={windowPassRateTrend.poly}
							fill="none"
							stroke="var(--ch-profit)"
							stroke-width="1.5"
							stroke-linejoin="round"
						/>
						{#each windowPassRateTrend.pts as p, i (i)}
							{#if i % Math.max(1, Math.floor(windowPassRateTrend.pts.length / 6)) === 0}
								{@const x =
									windowPassRateTrend.PAD +
									(i / Math.max(windowPassRateTrend.pts.length - 1, 1)) *
										(windowPassRateTrend.W - windowPassRateTrend.PAD * 2)}
								<text
									{x}
									y={windowPassRateTrend.H - 1}
									text-anchor="middle"
									font-size="6"
									fill="var(--ch-axis-muted)">{p.mo}</text
								>
							{/if}
						{/each}
						<text
							x={windowPassRateTrend.PAD}
							y={windowPassRateTrend.y50 - 2}
							font-size="5.5"
							fill="var(--ch-axis-muted)">50%</text
						>
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						% of WF windows with positive profit each month · above dashed = majority of windows
						profitable · rising = strategy robustness improving over time
					</p>
				</section>
			{/if}

			{#if windowMedianProfitByTimeframe}
				<section class="mb-6 rounded-xl border border-border bg-card p-5">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Median WF Window Profit by Timeframe
					</h3>
					<svg
						viewBox="0 0 {windowMedianProfitByTimeframe.W} {windowMedianProfitByTimeframe.H}"
						class="w-full"
						style="height:{windowMedianProfitByTimeframe.H}px"
					>
						<line
							x1={windowMedianProfitByTimeframe.midX}
							y1="0"
							x2={windowMedianProfitByTimeframe.midX}
							y2={windowMedianProfitByTimeframe.H}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.7"
						/>
						{#each windowMedianProfitByTimeframe.rows as row, i (i)}
							{@const y = i * 18 + 4}
							{@const bw = Math.max(
								2,
								(Math.abs(row.median) / windowMedianProfitByTimeframe.maxAbs) *
									(windowMedianProfitByTimeframe.barMaxW / 2)
							)}
							{@const x =
								row.median >= 0
									? windowMedianProfitByTimeframe.midX
									: windowMedianProfitByTimeframe.midX - bw}
							{@const color =
								row.median >= 2
									? 'var(--ch-profit)'
									: row.median >= 0
										? 'var(--ch-warn)'
										: 'var(--ch-loss)'}
							<text
								x={windowMedianProfitByTimeframe.PAD}
								y={y + 10}
								font-size="8"
								fill="var(--ch-axis-strong)">{row.tf}</text
							>
							<rect {x} y={y + 2} width={bw} height="10" rx="2" fill={color} />
							<text
								x={row.median >= 0
									? windowMedianProfitByTimeframe.midX + bw + 3
									: windowMedianProfitByTimeframe.midX - bw - 3}
								y={y + 10}
								text-anchor={row.median >= 0 ? 'start' : 'end'}
								font-size="7"
								fill={color}>{row.median >= 0 ? '+' : ''}{row.median.toFixed(2)}%</text
							>
							<text
								x={windowMedianProfitByTimeframe.W - 2}
								y={y + 10}
								text-anchor="end"
								font-size="6"
								fill="var(--ch-axis-muted)">{row.count}w</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Median window profit % per timeframe · diverging bars from center · green=positive ·
						red=negative · count shows number of WF windows per timeframe
					</p>
				</section>
			{/if}

			{#if windowStrategyAvgProfitRanking}
				<section class="mb-6 rounded-xl border border-border bg-card p-5">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Top Strategies by Avg WF Window Profit (top 10)
					</h3>
					<svg
						viewBox="0 0 {windowStrategyAvgProfitRanking.W} {windowStrategyAvgProfitRanking.H}"
						class="w-full"
						style="height:{windowStrategyAvgProfitRanking.H}px"
					>
						{#each windowStrategyAvgProfitRanking.rows as row, i (i)}
							{@const y = i * 16 + 2}
							{@const bw = Math.max(
								2,
								(Math.abs(row.avg) / windowStrategyAvgProfitRanking.maxAbs) *
									windowStrategyAvgProfitRanking.barMaxW
							)}
							{@const color =
								row.avg >= 2
									? 'var(--ch-profit)'
									: row.avg >= 0
										? 'var(--ch-warn)'
										: 'var(--ch-loss)'}
							<text
								x={windowStrategyAvgProfitRanking.PAD}
								y={y + 10}
								font-size="7"
								fill="var(--ch-axis-strong)">{row.strat}</text
							>
							<rect
								x={windowStrategyAvgProfitRanking.PAD + 115}
								{y}
								width={bw}
								height="12"
								rx="2"
								fill={color}
							/>
							<text
								x={windowStrategyAvgProfitRanking.PAD + 115 + bw + 3}
								y={y + 10}
								font-size="7"
								fill={color}>{row.avg >= 0 ? '+' : ''}{row.avg.toFixed(2)}%</text
							>
							<text
								x={windowStrategyAvgProfitRanking.W - 2}
								y={y + 10}
								text-anchor="end"
								font-size="6"
								fill="var(--ch-axis-muted)">{row.count}w</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Strategies ranked by avg WF window profit % · bar length = magnitude · count = number of
						WF windows · green=positive avg · reveals most walk-forward-consistent strategies
					</p>
				</section>
			{/if}
			{#if windowProfitDistribution}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Window Profit Distribution
					</h3>
					<svg
						viewBox="0 0 {windowProfitDistribution.W} {windowProfitDistribution.H}"
						class="w-full"
						style="height:{windowProfitDistribution.H}px"
					>
						<line
							x1={windowProfitDistribution.zeroX}
							y1="0"
							x2={windowProfitDistribution.zeroX}
							y2={windowProfitDistribution.H - 14}
							stroke="var(--ch-axis-muted)"
							stroke-width="0.8"
						/>
						{#each windowProfitDistribution.bars as bar, _i (_i)}
							<rect
								x={bar.x}
								y={windowProfitDistribution.H - 14 - bar.h}
								width={windowProfitDistribution.bw}
								height={bar.h}
								rx="1"
								fill={bar.color}
							/>
						{/each}
						<text
							x={windowProfitDistribution.PAD}
							y={windowProfitDistribution.H - 2}
							font-size="7"
							fill="var(--ch-axis)">{windowProfitDistribution.mn}%</text
						>
						<text
							x={windowProfitDistribution.W - windowProfitDistribution.PAD}
							y={windowProfitDistribution.H - 2}
							text-anchor="end"
							font-size="7"
							fill="var(--ch-axis)">{windowProfitDistribution.mx}%</text
						>
						<text
							x={windowProfitDistribution.W / 2}
							y={windowProfitDistribution.H - 2}
							text-anchor="middle"
							font-size="7"
							fill="var(--ch-axis-muted)">n={windowProfitDistribution.total}</text
						>
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Distribution of all WF window profit % values · green=profit≥0 · red=loss · zero line
						shows profit/loss boundary · reveals overall WF performance spread
					</p>
				</section>
			{/if}
			{#if windowPassRateByStrategy}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Pass Rate by Strategy
					</h3>
					<svg
						viewBox="0 0 {windowPassRateByStrategy.W} {windowPassRateByStrategy.H}"
						class="w-full"
						style="height:{windowPassRateByStrategy.H}px"
					>
						<line
							x1={windowPassRateByStrategy.PAD + windowPassRateByStrategy.barMaxW / 2}
							y1="0"
							x2={windowPassRateByStrategy.PAD + windowPassRateByStrategy.barMaxW / 2}
							y2={windowPassRateByStrategy.H}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.7"
							stroke-dasharray="3,2"
						/>
						{#each windowPassRateByStrategy.rows as row, i (i)}
							{@const y = i * 16 + 2}
							{@const bw = Math.max(2, (row.rate / 100) * windowPassRateByStrategy.barMaxW)}
							{@const color =
								row.rate >= 60
									? 'var(--ch-profit)'
									: row.rate >= 50
										? 'var(--ch-warn)'
										: 'var(--ch-loss)'}
							<text
								x={windowPassRateByStrategy.PAD}
								y={y + 10}
								font-size="7"
								fill="var(--ch-axis-strong)">{row.strat}</text
							>
							<rect
								x={windowPassRateByStrategy.PAD + 118}
								{y}
								width={bw}
								height="12"
								rx="2"
								fill={color}
							/>
							<text
								x={windowPassRateByStrategy.PAD + 118 + bw + 3}
								y={y + 10}
								font-size="7"
								fill={color}>{row.rate.toFixed(1)}%</text
							>
							<text
								x={windowPassRateByStrategy.W - 2}
								y={y + 10}
								text-anchor="end"
								font-size="6"
								fill="var(--ch-axis-muted)">{row.count}w</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						% of WF windows with profit>0 per strategy (min 3 windows) · green≥60% · yellow≥50% ·
						count=total WF windows · reveals most walk-forward-consistent strategies
					</p>
				</section>
			{/if}
			{#if windowAvgProfitByTFDiverging}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Avg WF Profit by Timeframe (Diverging)
					</h3>
					<svg
						viewBox="0 0 {windowAvgProfitByTFDiverging.W} {windowAvgProfitByTFDiverging.H}"
						class="w-full"
						style="height:{windowAvgProfitByTFDiverging.H}px"
					>
						<line
							x1={windowAvgProfitByTFDiverging.zeroX}
							y1="0"
							x2={windowAvgProfitByTFDiverging.zeroX}
							y2={windowAvgProfitByTFDiverging.H}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.7"
						/>
						{#each windowAvgProfitByTFDiverging.rows as row, i (i)}
							{@const y = i * 18 + 2}
							{@const bw = Math.max(
								2,
								(Math.abs(row.avg) / windowAvgProfitByTFDiverging.maxAbs) *
									(windowAvgProfitByTFDiverging.barMaxW / 2)
							)}
							{@const x =
								row.avg >= 0
									? windowAvgProfitByTFDiverging.zeroX
									: windowAvgProfitByTFDiverging.zeroX - bw}
							{@const color =
								row.avg >= 2
									? 'var(--ch-profit)'
									: row.avg >= 0
										? 'var(--ch-warn)'
										: 'var(--ch-loss)'}
							<text
								x={windowAvgProfitByTFDiverging.PAD}
								y={y + 12}
								font-size="8"
								fill="var(--ch-axis-strong)">{row.tf}</text
							>
							<rect {x} {y} width={bw} height="14" rx="2" fill={color} />
							<text
								x={row.avg >= 0
									? windowAvgProfitByTFDiverging.zeroX + bw + 3
									: windowAvgProfitByTFDiverging.zeroX - bw - 3}
								y={y + 12}
								text-anchor={row.avg >= 0 ? 'start' : 'end'}
								font-size="7"
								fill={color}>{row.avg >= 0 ? '+' : ''}{row.avg.toFixed(2)}%</text
							>
							<text
								x={windowAvgProfitByTFDiverging.W - 2}
								y={y + 12}
								text-anchor="end"
								font-size="6"
								fill="var(--ch-axis-muted)">{row.count}w</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg WF window profit % per timeframe · diverging from zero · green≥2% · yellow≥0% ·
						count=WF windows · reveals which timeframes produce the most profitable walk-forward
						windows
					</p>
				</section>
			{/if}
			{#if windowAvgTradeCountByTF}
				<section class="rounded-lg border border-border bg-card p-3">
					<h3 class="mb-2 text-xs font-semibold text-foreground">Avg Trade Count by Timeframe</h3>
					<svg
						viewBox="0 0 {windowAvgTradeCountByTF.W} {windowAvgTradeCountByTF.H}"
						class="w-full"
						style="height:{windowAvgTradeCountByTF.H}px"
					>
						{#each windowAvgTradeCountByTF.bars as bar, i (i)}
							{@const barH = bar.h}
							<rect
								x={bar.x}
								y={windowAvgTradeCountByTF.H - windowAvgTradeCountByTF.PAD - barH - 14}
								width={windowAvgTradeCountByTF.bw}
								height={barH}
								fill="var(--ch-violet)"
								rx="1"
							/>
							<text
								x={bar.x + windowAvgTradeCountByTF.bw / 2}
								y={windowAvgTradeCountByTF.H - windowAvgTradeCountByTF.PAD - barH - 16}
								text-anchor="middle"
								font-size="6"
								fill="var(--ch-axis-strong)">{bar.avg.toFixed(0)}</text
							>
							<text
								x={bar.x + windowAvgTradeCountByTF.bw / 2}
								y={windowAvgTradeCountByTF.H - 3}
								text-anchor="middle"
								font-size="6"
								fill="var(--ch-axis)">{bar.tf}</text
							>
							<text
								x={bar.x + windowAvgTradeCountByTF.bw / 2}
								y={windowAvgTradeCountByTF.H - windowAvgTradeCountByTF.PAD - 2}
								text-anchor="middle"
								font-size="5"
								fill="var(--ch-axis-muted)">{bar.count}w</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg trade count per WF window by timeframe · indigo bars · label=avg trades · count=WF
						windows · reveals activity level across timeframes in walk-forward analysis
					</p>
				</section>
			{/if}
			{#if windowSharpeByStrategy}
				<section class="rounded-lg border border-border bg-card p-3">
					<h3 class="mb-2 text-xs font-semibold text-foreground">Avg WF Sharpe by Strategy</h3>
					<svg
						viewBox="0 0 {windowSharpeByStrategy.W} {windowSharpeByStrategy.H}"
						class="w-full"
						style="height:{windowSharpeByStrategy.H}px"
					>
						<line
							x1={windowSharpeByStrategy.zeroX}
							y1="0"
							x2={windowSharpeByStrategy.zeroX}
							y2={windowSharpeByStrategy.H}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.7"
							stroke-dasharray="3,2"
						/>
						{#each windowSharpeByStrategy.rows as row, i (i)}
							{@const y = i * 16 + 2}
							{@const bw = Math.max(
								2,
								(Math.abs(row.avg) / windowSharpeByStrategy.maxAbs) *
									(windowSharpeByStrategy.barMaxW / 2)
							)}
							{@const x =
								row.avg >= 0 ? windowSharpeByStrategy.zeroX : windowSharpeByStrategy.zeroX - bw}
							{@const color =
								row.avg >= 1
									? 'var(--ch-profit)'
									: row.avg >= 0
										? 'var(--ch-warn)'
										: 'var(--ch-loss)'}
							<text
								x={windowSharpeByStrategy.PAD}
								y={y + 10}
								font-size="7"
								fill="var(--ch-axis-strong)">{row.name}</text
							>
							<rect {x} {y} width={bw} height="12" rx="2" fill={color} />
							<text
								x={row.avg >= 0
									? windowSharpeByStrategy.zeroX + bw + 3
									: windowSharpeByStrategy.zeroX - bw - 3}
								y={y + 10}
								text-anchor={row.avg >= 0 ? 'start' : 'end'}
								font-size="7"
								fill={color}>{row.avg.toFixed(2)}</text
							>
							<text
								x={windowSharpeByStrategy.W - 2}
								y={y + 10}
								text-anchor="end"
								font-size="6"
								fill="var(--ch-axis-muted)">{row.count}w</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Strategies ranked by avg Sharpe ratio across WF windows · green≥1 · yellow≥0 · red&lt;0
						· count=windows · reveals which strategies produce most consistent risk-adjusted returns
						in walk-forward
					</p>
				</section>
			{/if}
			{#if windowProfitByStrategy}
				<section class="rounded-lg border border-border bg-card p-3">
					<h3 class="mb-2 text-xs font-semibold text-foreground">Avg WF Profit % by Strategy</h3>
					<svg
						viewBox="0 0 {windowProfitByStrategy.W} {windowProfitByStrategy.H}"
						class="w-full"
						style="height:{windowProfitByStrategy.H}px"
					>
						<line
							x1={windowProfitByStrategy.zeroX}
							y1="0"
							x2={windowProfitByStrategy.zeroX}
							y2={windowProfitByStrategy.H}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.7"
							stroke-dasharray="3,2"
						/>
						{#each windowProfitByStrategy.rows as row, i (i)}
							{@const y = i * 16 + 2}
							{@const bw = Math.max(
								2,
								(Math.abs(row.avg) / windowProfitByStrategy.maxAbs) *
									(windowProfitByStrategy.barMaxW / 2)
							)}
							{@const x =
								row.avg >= 0 ? windowProfitByStrategy.zeroX : windowProfitByStrategy.zeroX - bw}
							{@const color =
								row.avg >= 2
									? 'var(--ch-profit)'
									: row.avg >= 0
										? 'var(--ch-warn)'
										: 'var(--ch-loss)'}
							<text
								x={windowProfitByStrategy.PAD}
								y={y + 10}
								font-size="7"
								fill="var(--ch-axis-strong)">{row.name}</text
							>
							<rect {x} {y} width={bw} height="12" rx="2" fill={color} />
							<text
								x={row.avg >= 0
									? windowProfitByStrategy.zeroX + bw + 3
									: windowProfitByStrategy.zeroX - bw - 3}
								y={y + 10}
								text-anchor={row.avg >= 0 ? 'start' : 'end'}
								font-size="7"
								fill={color}>{row.avg >= 0 ? '+' : ''}{row.avg.toFixed(2)}%</text
							>
							<text
								x={windowProfitByStrategy.W - 2}
								y={y + 10}
								text-anchor="end"
								font-size="6"
								fill="var(--ch-axis-muted)">{row.count}w</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Strategies ranked by avg profit % across WF windows · green≥2% · yellow≥0% · red&lt;0% ·
						count=windows · reveals which strategies generate the most profit in walk-forward
						testing
					</p>
				</section>
			{/if}
			{#if windowTradeCountByTF}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Avg Trade Count per Timeframe (WF)
					</h3>
					<svg
						viewBox="0 0 {windowTradeCountByTF.W} {windowTradeCountByTF.H}"
						class="w-full"
						style="height:{windowTradeCountByTF.H}px"
					>
						{#each windowTradeCountByTF.rows as row, i (i)}
							{@const x = windowTradeCountByTF.toX(i)}
							{@const bh = windowTradeCountByTF.toH(row.avg)}
							{@const y = windowTradeCountByTF.H - windowTradeCountByTF.PAD - bh - 16}
							<rect
								{x}
								{y}
								width={windowTradeCountByTF.bw}
								height={bh}
								rx="1"
								fill="var(--ch-teal)"
							/>
							<text
								x={x + windowTradeCountByTF.bw / 2}
								y={y - 2}
								text-anchor="middle"
								font-size="6.5"
								fill="var(--ch-teal-strong)">{Math.round(row.avg)}</text
							>
							<text
								x={x + windowTradeCountByTF.bw / 2}
								y={windowTradeCountByTF.H - 3}
								text-anchor="middle"
								font-size="7"
								fill="var(--ch-axis)">{row.tf}</text
							>
							<text
								x={x + windowTradeCountByTF.bw / 2}
								y={windowTradeCountByTF.H - windowTradeCountByTF.PAD - 2}
								text-anchor="middle"
								font-size="5.5"
								fill="var(--ch-axis-muted)">{row.count}w</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg number of trades per WF window by timeframe · teal bars · higher trade count
						timeframes provide more statistical significance to WF results
					</p>
				</section>
			{/if}
			{#if windowSharpeTimeline}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Sharpe Timeline
					</h3>
					<svg
						viewBox="0 0 {windowSharpeTimeline.W} {windowSharpeTimeline.H}"
						class="w-full"
						style="height:{windowSharpeTimeline.H}px"
					>
						<polygon points={windowSharpeTimeline.area} fill={windowSharpeTimeline.fillColor} />
						<line
							x1={windowSharpeTimeline.PAD}
							y1={windowSharpeTimeline.zeroY}
							x2={windowSharpeTimeline.W - windowSharpeTimeline.PAD}
							y2={windowSharpeTimeline.zeroY}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.7"
							stroke-dasharray="3,2"
						/>
						<polyline
							points={windowSharpeTimeline.polyline}
							fill="none"
							stroke={windowSharpeTimeline.color}
							stroke-width="1.5"
							stroke-linejoin="round"
						/>
						<text
							x={windowSharpeTimeline.W - windowSharpeTimeline.PAD}
							y={windowSharpeTimeline.PAD + 6}
							text-anchor="end"
							font-size="7"
							fill={windowSharpeTimeline.color}>{windowSharpeTimeline.last}</text
						>
						<text
							x={windowSharpeTimeline.PAD}
							y={windowSharpeTimeline.PAD + 6}
							font-size="6"
							fill="var(--ch-axis-muted)">Sharpe</text
						>
						<text
							x={windowSharpeTimeline.PAD}
							y={windowSharpeTimeline.H - 2}
							font-size="6"
							fill="var(--ch-axis-muted)">earliest →</text
						>
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						WF window Sharpe ratio sorted by start date · green≥1 · yellow≥0 · red&lt;0 · zero
						baseline · reveals whether WF performance is improving over successive time windows
					</p>
				</section>
			{/if}
			{#if windowProfitFactorMonthly}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Profit Factor Monthly Trend
					</h3>
					<svg
						viewBox="0 0 {windowProfitFactorMonthly.W} {windowProfitFactorMonthly.H}"
						class="w-full"
						style="height:{windowProfitFactorMonthly.H}px"
					>
						<line
							x1={windowProfitFactorMonthly.PAD}
							y1={windowProfitFactorMonthly.oneY}
							x2={windowProfitFactorMonthly.W - windowProfitFactorMonthly.PAD}
							y2={windowProfitFactorMonthly.oneY}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.7"
							stroke-dasharray="3,2"
						/>
						<polyline
							points={windowProfitFactorMonthly.polyline}
							fill="none"
							stroke={windowProfitFactorMonthly.color}
							stroke-width="1.5"
							stroke-linejoin="round"
						/>
						{#each windowProfitFactorMonthly.pts as p, i (i)}
							{#if i === 0 || i === windowProfitFactorMonthly.pts.length - 1}
								<text
									x={windowProfitFactorMonthly.toX(i)}
									y={windowProfitFactorMonthly.H - 2}
									text-anchor={i === 0 ? 'start' : 'end'}
									font-size="6"
									fill="var(--ch-axis-muted)">{p.m}</text
								>
							{/if}
						{/each}
						<text
							x={windowProfitFactorMonthly.W - windowProfitFactorMonthly.PAD}
							y={windowProfitFactorMonthly.PAD + 6}
							text-anchor="end"
							font-size="7"
							fill={windowProfitFactorMonthly.color}>{windowProfitFactorMonthly.last}</text
						>
						<text
							x={windowProfitFactorMonthly.PAD}
							y={windowProfitFactorMonthly.PAD + 6}
							font-size="6"
							fill="var(--ch-axis-muted)">PF</text
						>
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Monthly avg profit factor across WF windows · green≥1.5 · yellow≥1 · red&lt;1 · dashed
						line at PF=1 · reveals whether WF strategy has improving edge over time
					</p>
				</section>
			{/if}
			{#if windowCalmarByStrategy}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Avg Calmar Ratio by Strategy
					</h3>
					<svg
						viewBox="0 0 {windowCalmarByStrategy.W} {windowCalmarByStrategy.H}"
						class="w-full"
						style="height:{windowCalmarByStrategy.H}px"
					>
						<line
							x1={windowCalmarByStrategy.zeroX}
							y1="0"
							x2={windowCalmarByStrategy.zeroX}
							y2={windowCalmarByStrategy.H}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.7"
							stroke-dasharray="3,2"
						/>
						{#each windowCalmarByStrategy.rows as row, i (i)}
							{@const y = windowCalmarByStrategy.PAD + i * 16}
							{@const bw = Math.max(
								2,
								(Math.abs(row.avg) / windowCalmarByStrategy.maxAbs) *
									(windowCalmarByStrategy.barMaxW / 2)
							)}
							{@const x =
								row.avg >= 0 ? windowCalmarByStrategy.zeroX : windowCalmarByStrategy.zeroX - bw}
							{@const color = row.avg >= 0 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
							<rect {x} {y} width={bw} height="12" rx="1" fill={color} />
							<text
								x={windowCalmarByStrategy.PAD}
								y={y + 10}
								font-size="6.5"
								fill="var(--ch-axis-strong)">{row.strat}</text
							>
							<text
								x={row.avg >= 0
									? windowCalmarByStrategy.zeroX + bw + 2
									: windowCalmarByStrategy.zeroX - bw - 2}
								y={y + 10}
								text-anchor={row.avg >= 0 ? 'start' : 'end'}
								font-size="6.5"
								fill={color}>{row.avg.toFixed(2)}</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg Calmar ratio per strategy across all WF windows · teal=positive · red=negative ·
						diverging from zero · Calmar = annual return / max drawdown · higher is better
					</p>
				</section>
			{/if}
			{#if windowDrawdownTrend}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Max Drawdown Trend Over WF Windows
					</h3>
					<svg
						viewBox="0 0 {windowDrawdownTrend.W} {windowDrawdownTrend.H}"
						class="w-full"
						style="height:{windowDrawdownTrend.H}px"
					>
						<polygon points={windowDrawdownTrend.area} fill="var(--ch-loss-light)" />
						<polyline
							points={windowDrawdownTrend.polyline}
							fill="none"
							stroke="var(--ch-loss)"
							stroke-width="1.5"
							stroke-linejoin="round"
						/>
						<text
							x={windowDrawdownTrend.PAD}
							y={windowDrawdownTrend.H - 2}
							font-size="6"
							fill="var(--ch-axis-muted)">{windowDrawdownTrend.firstM}</text
						>
						<text
							x={windowDrawdownTrend.W - windowDrawdownTrend.PAD}
							y={windowDrawdownTrend.H - 2}
							text-anchor="end"
							font-size="6"
							fill="var(--ch-axis-muted)">{windowDrawdownTrend.lastM}</text
						>
						<text
							x={windowDrawdownTrend.PAD}
							y={windowDrawdownTrend.PAD + 7}
							font-size="7"
							fill="var(--ch-loss-strong)">{windowDrawdownTrend.maxDD}%</text
						>
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Max drawdown % trend across WF windows sorted by start date · red area · decreasing
						trend indicates improving risk control over successive walk-forward periods
					</p>
				</section>
			{/if}
			{#if windowWinRateByStrategy}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Avg Win Rate by Strategy (WF Windows)
					</h3>
					<svg
						viewBox="0 0 {windowWinRateByStrategy.W} {windowWinRateByStrategy.H}"
						class="w-full"
						style="height:{windowWinRateByStrategy.H}px"
					>
						{#each windowWinRateByStrategy.rows as row, i (i)}
							{@const y = windowWinRateByStrategy.PAD + i * 16}
							{@const bw = Math.max(
								2,
								(row.avg / windowWinRateByStrategy.maxAvg) * windowWinRateByStrategy.barMaxW
							)}
							{@const color =
								row.avg >= 60
									? 'var(--ch-profit)'
									: row.avg >= 50
										? 'var(--ch-warn)'
										: 'var(--ch-loss)'}
							<text
								x={windowWinRateByStrategy.PAD}
								y={y + 11}
								font-size="6.5"
								fill="var(--ch-axis-strong)">{row.strat}</text
							>
							<rect
								x={windowWinRateByStrategy.PAD + 108}
								{y}
								width={bw}
								height="12"
								rx="1"
								fill={color}
							/>
							<text
								x={windowWinRateByStrategy.PAD + 108 + bw + 3}
								y={y + 11}
								font-size="6.5"
								fill={color}>{row.avg.toFixed(1)}%</text
							>
							<text
								x={windowWinRateByStrategy.W - 2}
								y={y + 11}
								text-anchor="end"
								font-size="5.5"
								fill="var(--ch-axis-muted)">{row.count}w</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg win rate % per strategy across all WF windows · green≥60% · yellow≥50% · red&lt;50%
						· identifies which strategies maintain high accuracy in out-of-sample periods
					</p>
				</section>
			{/if}
			{#if windowMonthlyProfitBars}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Monthly Avg WF Profit% Timeline
					</h3>
					<svg
						viewBox="0 0 {windowMonthlyProfitBars.W} {windowMonthlyProfitBars.H}"
						class="w-full"
						style="height:{windowMonthlyProfitBars.H}px"
					>
						<line
							x1={windowMonthlyProfitBars.PAD}
							y1={windowMonthlyProfitBars.midY}
							x2={windowMonthlyProfitBars.W - windowMonthlyProfitBars.PAD}
							y2={windowMonthlyProfitBars.midY}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.7"
							stroke-dasharray="3,2"
						/>
						{#each windowMonthlyProfitBars.pts as p, i (i)}
							{@const x = windowMonthlyProfitBars.PAD + i * (windowMonthlyProfitBars.bw + 1)}
							{@const bh = Math.max(
								2,
								(Math.abs(p.avg) / windowMonthlyProfitBars.maxAbs) *
									(windowMonthlyProfitBars.midY - windowMonthlyProfitBars.PAD)
							)}
							{@const y =
								p.avg >= 0 ? windowMonthlyProfitBars.midY - bh : windowMonthlyProfitBars.midY}
							{@const color = p.avg >= 0 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
							<rect {x} {y} width={windowMonthlyProfitBars.bw} height={bh} fill={color} />
							{#if i % 3 === 0}
								<text
									x={x + windowMonthlyProfitBars.bw / 2}
									y={windowMonthlyProfitBars.H - 1}
									text-anchor="middle"
									font-size="5.5"
									fill="var(--ch-axis-muted)">{p.m}</text
								>
							{/if}
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Monthly avg total profit% across WF windows grouped by window start date · teal=positive
						· red=negative · reveals seasonal performance patterns in out-of-sample testing
					</p>
				</section>
			{/if}
			{#if windowSortinoByPairCount}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Avg Sortino by Trade Count Bucket (WF)
					</h3>
					<svg
						viewBox="0 0 {windowSortinoByPairCount.W} {windowSortinoByPairCount.H}"
						class="w-full"
						style="height:{windowSortinoByPairCount.H}px"
					>
						<line
							x1={windowSortinoByPairCount.zeroX}
							y1="0"
							x2={windowSortinoByPairCount.zeroX}
							y2={windowSortinoByPairCount.H}
							stroke="var(--ch-axis-faint)"
							stroke-width="1"
						/>
						{#each windowSortinoByPairCount.rows as row, i (i)}
							{@const y = windowSortinoByPairCount.PAD + i * 20}
							{@const bw = Math.max(
								2,
								(Math.abs(row.avg) / windowSortinoByPairCount.maxAbs) *
									(windowSortinoByPairCount.barMaxW / 2)
							)}
							{@const x =
								row.avg >= 0 ? windowSortinoByPairCount.zeroX : windowSortinoByPairCount.zeroX - bw}
							{@const color = row.avg >= 0 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
							<rect {x} {y} width={bw} height="13" rx="2" fill={color} />
							<text
								x={windowSortinoByPairCount.PAD}
								y={y + 10}
								font-size="7"
								fill="var(--ch-axis-strong)">{row.bucket} trades</text
							>
							<text
								x={row.avg >= 0
									? windowSortinoByPairCount.zeroX + bw + 2
									: windowSortinoByPairCount.zeroX - bw - 2}
								y={y + 10}
								text-anchor={row.avg >= 0 ? 'start' : 'end'}
								font-size="6.5"
								fill={color}>{row.avg.toFixed(2)}</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg Sortino ratio grouped by trade count bucket (10s) across WF windows · teal/red ·
						identifies whether higher-frequency WF windows deliver better risk-adjusted returns
					</p>
				</section>
			{/if}
			{#if windowProfitByDow}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Avg Profit% by Day of Week (Window Start)
					</h3>
					<svg
						viewBox="0 0 {windowProfitByDow.W} {windowProfitByDow.H}"
						class="w-full"
						style="height:{windowProfitByDow.H}px"
					>
						<line
							x1={windowProfitByDow.PAD}
							y1={windowProfitByDow.midY}
							x2={windowProfitByDow.W - windowProfitByDow.PAD}
							y2={windowProfitByDow.midY}
							stroke="var(--ch-axis-faint)"
							stroke-width="1"
						/>
						{#each windowProfitByDow.pts as p, i (i)}
							{@const x = windowProfitByDow.PAD + i * (windowProfitByDow.bw + 2)}
							{@const bh = Math.max(
								1,
								(Math.abs(p.avg) / windowProfitByDow.maxAbs) *
									(windowProfitByDow.H / 2 - windowProfitByDow.PAD)
							)}
							{@const y = p.avg >= 0 ? windowProfitByDow.midY - bh : windowProfitByDow.midY}
							{@const color = p.avg >= 0 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
							<rect {x} {y} width={windowProfitByDow.bw} height={bh} rx="1" fill={color} />
							<text
								x={x + windowProfitByDow.bw / 2}
								y={windowProfitByDow.H - 1}
								text-anchor="middle"
								font-size="6"
								fill="var(--ch-axis)">{p.d}</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg WF profit% by day of week (window start date) · teal=positive · red=negative ·
						reveals whether windows starting on certain days perform systematically better
					</p>
				</section>
			{/if}
			{#if windowCalmarCDF}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Calmar Ratio CDF (WF Windows)
					</h3>
					<svg
						viewBox="0 0 {windowCalmarCDF.W} {windowCalmarCDF.H}"
						class="w-full"
						style="height:{windowCalmarCDF.H}px"
					>
						<line
							x1={windowCalmarCDF.zeroX}
							y1={windowCalmarCDF.PAD}
							x2={windowCalmarCDF.zeroX}
							y2={windowCalmarCDF.H - windowCalmarCDF.PAD}
							stroke="var(--ch-axis-muted)"
							stroke-width="1"
							stroke-dasharray="3,2"
						/>
						<polyline
							points={windowCalmarCDF.polyline}
							fill="none"
							stroke="var(--ch-teal-strong)"
							stroke-width="1.5"
							stroke-linejoin="round"
						/>
						<text
							x={windowCalmarCDF.PAD}
							y={windowCalmarCDF.H - 2}
							font-size="6"
							fill="var(--ch-axis-muted)">{windowCalmarCDF.minV}</text
						>
						<text
							x={windowCalmarCDF.W - windowCalmarCDF.PAD}
							y={windowCalmarCDF.H - 2}
							text-anchor="end"
							font-size="6"
							fill="var(--ch-axis-muted)">{windowCalmarCDF.maxV}</text
						>
						<text
							x={windowCalmarCDF.W / 2}
							y={windowCalmarCDF.PAD + 8}
							text-anchor="middle"
							font-size="7"
							fill="var(--ch-teal-strong)">median {windowCalmarCDF.median}</text
						>
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Cumulative distribution of Calmar ratios across WF windows · teal S-curve · dashed zero
						line · right-skew = most windows achieve positive Calmar · reveals out-of-sample quality
					</p>
				</section>
			{/if}
			{#if windowPassRateHeatmap}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Pass Rate Heatmap (Strategy × Month)
					</h3>
					<svg
						viewBox="0 0 {windowPassRateHeatmap.W} {windowPassRateHeatmap.H}"
						class="w-full"
						style="height:{windowPassRateHeatmap.H}px"
					>
						{#each windowPassRateHeatmap.strats as s, si (si)}
							<text
								x={windowPassRateHeatmap.PAD}
								y={windowPassRateHeatmap.PAD + (si + 1) * windowPassRateHeatmap.cellH + 12}
								font-size="5.5"
								fill="var(--ch-axis)">{s}</text
							>
						{/each}
						{#each windowPassRateHeatmap.months as mo, mi (mi)}
							<text
								x={windowPassRateHeatmap.PAD +
									(mi + 1) * windowPassRateHeatmap.cellW +
									windowPassRateHeatmap.cellW / 2}
								y={windowPassRateHeatmap.PAD + 8}
								text-anchor="middle"
								font-size="5.5"
								fill="var(--ch-axis)">{mo.slice(5)}</text
							>
						{/each}
						{#each windowPassRateHeatmap.cells as cell, _i (_i)}
							{@const alpha = cell.rate < 0 ? '0.08' : (cell.rate * 0.65 + 0.1).toFixed(2)}
							{@const fill =
								cell.rate < 0
									? 'var(--ch-axis-faint)'
									: cell.rate >= 0.5
										? `rgba(34,197,94,${alpha})`
										: `rgba(239,68,68,${alpha})`}
							<rect
								x={cell.x}
								y={cell.y}
								width={windowPassRateHeatmap.cellW - 2}
								height={windowPassRateHeatmap.cellH - 2}
								rx="2"
								{fill}
							/>
							{#if cell.rate >= 0}
								<text
									x={cell.x + windowPassRateHeatmap.cellW / 2 - 1}
									y={cell.y + 11}
									text-anchor="middle"
									font-size="5.5"
									fill="var(--ch-axis-strong)">{(cell.rate * 100).toFixed(0)}%</text
								>
							{/if}
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Pass rate (% windows with positive profit) heatmap by strategy and month · green=high
						pass · red=low pass · grey=no data · reveals strategy consistency across time
					</p>
				</section>
			{/if}
			{#if windowSharpeVsCalmar}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Sharpe vs Calmar Scatter (WF Windows)
					</h3>
					<svg
						viewBox="0 0 {windowSharpeVsCalmar.W} {windowSharpeVsCalmar.H}"
						class="w-full"
						style="height:{windowSharpeVsCalmar.H}px"
					>
						<line
							x1={windowSharpeVsCalmar.zeroX}
							y1={windowSharpeVsCalmar.PAD}
							x2={windowSharpeVsCalmar.zeroX}
							y2={windowSharpeVsCalmar.H - windowSharpeVsCalmar.PAD}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.7"
							stroke-dasharray="3,2"
						/>
						<line
							x1={windowSharpeVsCalmar.PAD}
							y1={windowSharpeVsCalmar.zeroY}
							x2={windowSharpeVsCalmar.W - windowSharpeVsCalmar.PAD}
							y2={windowSharpeVsCalmar.zeroY}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.7"
							stroke-dasharray="3,2"
						/>
						{#each windowSharpeVsCalmar.pts as p, _i (_i)}
							{@const cx = windowSharpeVsCalmar.toX(p.sharpe)}
							{@const cy = windowSharpeVsCalmar.toY(p.calmar)}
							{@const color =
								p.sharpe > 0 && p.calmar > 0
									? 'var(--ch-teal)'
									: p.sharpe > 0
										? 'var(--ch-warn-light)'
										: 'var(--ch-loss-light)'}
							<circle {cx} {cy} r="2.5" fill={color} />
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Scatter of Sharpe (X) vs Calmar (Y) per WF window · teal=both positive · yellow=Sharpe
						only · red=both negative · top-right quadrant = ideal out-of-sample windows
					</p>
				</section>
			{/if}
			{#if windowMonthlyTradeCount}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Avg Trade Count per Month (WF)
					</h3>
					<svg
						viewBox="0 0 {windowMonthlyTradeCount.W} {windowMonthlyTradeCount.H}"
						class="w-full"
						style="height:{windowMonthlyTradeCount.H}px"
					>
						{#each windowMonthlyTradeCount.pts as p, i (i)}
							{@const x = windowMonthlyTradeCount.PAD + i * (windowMonthlyTradeCount.bw + 1)}
							{@const bh = Math.max(
								1,
								(p.avg / windowMonthlyTradeCount.maxAvg) *
									(windowMonthlyTradeCount.H - windowMonthlyTradeCount.PAD * 2)
							)}
							{@const y = windowMonthlyTradeCount.H - windowMonthlyTradeCount.PAD - bh}
							<rect
								{x}
								{y}
								width={windowMonthlyTradeCount.bw}
								height={bh}
								rx="1"
								fill="var(--ch-teal)"
							/>
							{#if i % 3 === 0}
								<text
									x={x + windowMonthlyTradeCount.bw / 2}
									y={windowMonthlyTradeCount.H - 1}
									text-anchor="middle"
									font-size="5.5"
									fill="var(--ch-axis-muted)">{p.m}</text
								>
							{/if}
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg trade count per WF window by window start month · teal bars · rising trade count may
						indicate more liquid market conditions or broader pair coverage in recent windows
					</p>
				</section>
			{/if}
			{#if windowProfitCDF}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Window Profit% CDF
					</h3>
					<svg
						viewBox="0 0 {windowProfitCDF.W} {windowProfitCDF.H}"
						class="w-full"
						style="height:{windowProfitCDF.H}px"
					>
						<line
							x1={windowProfitCDF.zeroX}
							y1={windowProfitCDF.PAD}
							x2={windowProfitCDF.zeroX}
							y2={windowProfitCDF.H - windowProfitCDF.PAD}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.7"
							stroke-dasharray="3,2"
						/>
						<polyline
							points={windowProfitCDF.polyline}
							fill="none"
							stroke="var(--ch-teal-strong)"
							stroke-width="1.5"
							stroke-linejoin="round"
						/>
						<text
							x={windowProfitCDF.PAD}
							y={windowProfitCDF.H - 2}
							font-size="6"
							fill="var(--ch-axis-muted)">{windowProfitCDF.minV}%</text
						>
						<text
							x={windowProfitCDF.W - windowProfitCDF.PAD}
							y={windowProfitCDF.H - 2}
							text-anchor="end"
							font-size="6"
							fill="var(--ch-axis-muted)">{windowProfitCDF.maxV}%</text
						>
						<text
							x={windowProfitCDF.W / 2}
							y={windowProfitCDF.PAD + 8}
							text-anchor="middle"
							font-size="7"
							fill="var(--ch-teal-strong)">median {windowProfitCDF.median}%</text
						>
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						CDF of out-of-sample profit% across all WF windows · teal S-curve · dashed zero line ·
						right of zero = majority of windows are profitable in the test period
					</p>
				</section>
			{/if}
			{#if windowDrawdownStrategyRanking}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Avg Max Drawdown% by Strategy (WF)
					</h3>
					<svg
						viewBox="0 0 {windowDrawdownStrategyRanking.W} {windowDrawdownStrategyRanking.H}"
						class="w-full"
						style="height:{windowDrawdownStrategyRanking.H}px"
					>
						{#each windowDrawdownStrategyRanking.rows as row, i (i)}
							{@const y = windowDrawdownStrategyRanking.PAD + i * 18}
							{@const bw = Math.max(
								2,
								(row.avg / windowDrawdownStrategyRanking.maxAvg) *
									windowDrawdownStrategyRanking.barMaxW
							)}
							{@const color =
								row.avg <= 8
									? 'var(--ch-profit)'
									: row.avg <= 15
										? 'var(--ch-warn)'
										: 'var(--ch-loss)'}
							<text
								x={windowDrawdownStrategyRanking.PAD}
								y={y + 12}
								font-size="7"
								fill="var(--ch-axis-strong)">{row.name}</text
							>
							<rect
								x={windowDrawdownStrategyRanking.PAD + 80}
								{y}
								width={bw}
								height="13"
								rx="2"
								fill={color}
							/>
							<text
								x={windowDrawdownStrategyRanking.PAD + 80 + bw + 3}
								y={y + 12}
								font-size="6.5"
								fill={color}>{row.avg.toFixed(1)}%</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg max drawdown% per strategy across WF windows (best first) · green≤8% · yellow≤15% ·
						red&gt;15% · lower DD in out-of-sample = more robust strategy
					</p>
				</section>
			{/if}
			{#if windowWinRateByStrategyRanking}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Win Rate% by Strategy
					</h3>
					<svg
						viewBox="0 0 {windowWinRateByStrategyRanking.W} {windowWinRateByStrategyRanking.H}"
						class="w-full"
						style="height:{windowWinRateByStrategyRanking.H}px"
					>
						{#each windowWinRateByStrategyRanking.rows as row, i (i)}
							{@const y = windowWinRateByStrategyRanking.PAD + i * 18}
							{@const bw = Math.max(2, (row.wr / 100) * windowWinRateByStrategyRanking.barMaxW)}
							{@const color =
								row.wr >= 55
									? 'var(--ch-profit)'
									: row.wr >= 45
										? 'var(--ch-teal)'
										: 'var(--ch-loss)'}
							<text
								x={windowWinRateByStrategyRanking.PAD}
								y={y + 12}
								font-size="7"
								fill="var(--ch-axis-strong)">{row.name}</text
							>
							<rect
								x={windowWinRateByStrategyRanking.PAD + 80}
								{y}
								width={bw}
								height="13"
								rx="2"
								fill={color}
							/>
							<text
								x={windowWinRateByStrategyRanking.PAD + 80 + bw + 3}
								y={y + 12}
								font-size="6.5"
								fill={color}>{row.wr.toFixed(1)}%</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Win rate% (% WF windows with positive profit) per strategy · green≥55% · teal≥45% ·
						red&lt;45% · high win rate = strategy consistently profitable out-of-sample
					</p>
				</section>
			{/if}
			{#if windowSortinoCDF}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Sortino Ratio CDF
					</h3>
					<svg
						viewBox="0 0 {windowSortinoCDF.W} {windowSortinoCDF.H}"
						class="w-full"
						style="height:{windowSortinoCDF.H}px"
					>
						<line
							x1={windowSortinoCDF.zeroX}
							y1={windowSortinoCDF.PAD}
							x2={windowSortinoCDF.zeroX}
							y2={windowSortinoCDF.H - windowSortinoCDF.PAD}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.7"
							stroke-dasharray="3,2"
						/>
						<polyline
							points={windowSortinoCDF.polyline}
							fill="none"
							stroke="var(--ch-teal-strong)"
							stroke-width="1.5"
							stroke-linejoin="round"
						/>
						<text
							x={windowSortinoCDF.PAD}
							y={windowSortinoCDF.H - 2}
							font-size="6"
							fill="var(--ch-axis-muted)">{windowSortinoCDF.minV}</text
						>
						<text
							x={windowSortinoCDF.W - windowSortinoCDF.PAD}
							y={windowSortinoCDF.H - 2}
							text-anchor="end"
							font-size="6"
							fill="var(--ch-axis-muted)">{windowSortinoCDF.maxV}</text
						>
						<text
							x={windowSortinoCDF.W / 2}
							y={windowSortinoCDF.PAD + 8}
							text-anchor="middle"
							font-size="7"
							fill="var(--ch-teal-strong)">median {windowSortinoCDF.median}</text
						>
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						CDF of Sortino ratios across all WF windows · teal S-curve · dashed zero line · median
						annotation · right-skew = most out-of-sample windows show positive risk-adjusted return
					</p>
				</section>
			{/if}
			{#if windowProfitByStrategyQuartile}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Profit% IQR by Strategy
					</h3>
					<svg
						viewBox="0 0 {windowProfitByStrategyQuartile.W} {windowProfitByStrategyQuartile.H}"
						class="w-full"
						style="height:{windowProfitByStrategyQuartile.H}px"
					>
						<line
							x1={windowProfitByStrategyQuartile.zeroX}
							y1="0"
							x2={windowProfitByStrategyQuartile.zeroX}
							y2={windowProfitByStrategyQuartile.H}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.7"
							stroke-dasharray="3,2"
						/>
						{#each windowProfitByStrategyQuartile.rows as row, i (i)}
							{@const y = windowProfitByStrategyQuartile.PAD + i * 20}
							{@const x1 = windowProfitByStrategyQuartile.toX(row.q1)}
							{@const x2 = windowProfitByStrategyQuartile.toX(row.q3)}
							{@const mx = windowProfitByStrategyQuartile.toX(row.median)}
							{@const color = row.median >= 0 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
							<text
								x={windowProfitByStrategyQuartile.PAD}
								y={y + 13}
								font-size="6.5"
								fill="var(--ch-axis-strong)">{row.name}</text
							>
							<rect x={x1} {y} width={Math.max(2, x2 - x1)} height="14" rx="2" fill={color} />
							<line
								x1={mx}
								y1={y}
								x2={mx}
								y2={y + 14}
								stroke="var(--ch-axis-strong)"
								stroke-width="1.2"
							/>
						{/each}
						<text
							x={windowProfitByStrategyQuartile.PAD}
							y={windowProfitByStrategyQuartile.H - 2}
							font-size="5.5"
							fill="var(--ch-axis-muted)">{windowProfitByStrategyQuartile.minV}%</text
						>
						<text
							x={windowProfitByStrategyQuartile.W - windowProfitByStrategyQuartile.PAD}
							y={windowProfitByStrategyQuartile.H - 2}
							text-anchor="end"
							font-size="5.5"
							fill="var(--ch-axis-muted)">{windowProfitByStrategyQuartile.maxV}%</text
						>
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						IQR (Q1-Q3) of out-of-sample profit% per strategy · teal bar=positive median ·
						red=negative median · white line=median · narrow bar = consistent · wide = high variance
					</p>
				</section>
			{/if}
			{#if windowTradeCountCDF}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Trade Count CDF
					</h3>
					<svg
						viewBox="0 0 {windowTradeCountCDF.W} {windowTradeCountCDF.H}"
						class="w-full"
						style="height:{windowTradeCountCDF.H}px"
					>
						<polyline
							points={windowTradeCountCDF.polyline}
							fill="none"
							stroke="var(--ch-violet-strong)"
							stroke-width="1.5"
							stroke-linejoin="round"
						/>
						<text
							x={windowTradeCountCDF.PAD}
							y={windowTradeCountCDF.H - 2}
							font-size="6"
							fill="var(--ch-axis-muted)">{windowTradeCountCDF.minV}</text
						>
						<text
							x={windowTradeCountCDF.W - windowTradeCountCDF.PAD}
							y={windowTradeCountCDF.H - 2}
							text-anchor="end"
							font-size="6"
							fill="var(--ch-axis-muted)">{windowTradeCountCDF.maxV}</text
						>
						<text
							x={windowTradeCountCDF.W / 2}
							y={windowTradeCountCDF.PAD + 8}
							text-anchor="middle"
							font-size="7"
							fill="var(--ch-violet-strong)">median {windowTradeCountCDF.median}</text
						>
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						CDF of trade count per WF window · indigo S-curve · left tail = windows with few trades
						(low confidence) · high median = most windows have statistically meaningful sample size
					</p>
				</section>
			{/if}
			{#if windowCalmarByTF}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Calmar Ratio by Timeframe
					</h3>
					<svg
						viewBox="0 0 {windowCalmarByTF.W} {windowCalmarByTF.H}"
						class="w-full"
						style="height:{windowCalmarByTF.H}px"
					>
						<line
							x1={windowCalmarByTF.zeroX}
							y1={0}
							x2={windowCalmarByTF.zeroX}
							y2={windowCalmarByTF.H}
							stroke="var(--ch-axis-muted)"
							stroke-width="0.5"
						/>
						{#each windowCalmarByTF.rows as row, i (i)}
							{@const y = 4 + i * 22}
							{@const bw = Math.max(
								2,
								(Math.abs(row.avg) / windowCalmarByTF.maxAbs) * (windowCalmarByTF.barMaxW / 2)
							)}
							{@const x = row.avg >= 0 ? windowCalmarByTF.zeroX : windowCalmarByTF.zeroX - bw}
							{@const color =
								row.avg >= 1
									? 'var(--ch-profit)'
									: row.avg >= 0
										? 'var(--ch-teal)'
										: 'var(--ch-loss)'}
							<text x={windowCalmarByTF.PAD} y={y + 13} font-size="8" fill="var(--ch-axis-strong)"
								>{row.tf}</text
							>
							<rect {x} {y} width={bw} height="16" rx="2" fill={color} />
							<text
								x={row.avg >= 0 ? windowCalmarByTF.zeroX + bw + 2 : windowCalmarByTF.zeroX - bw - 2}
								y={y + 12}
								text-anchor={row.avg >= 0 ? 'start' : 'end'}
								font-size="6.5"
								fill={color}>{row.avg.toFixed(2)}</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg Calmar ratio by timeframe · green≥1 · teal≥0 · red&lt;0 · Calmar = annualised return
						/ max drawdown — higher = better risk-adjusted performance
					</p>
				</section>
			{/if}
			{#if windowProfitByDowBars}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Profit% by Window Start Day
					</h3>
					<svg
						viewBox="0 0 {windowProfitByDowBars.W} {windowProfitByDowBars.H}"
						class="w-full"
						style="height:{windowProfitByDowBars.H}px"
					>
						<line
							x1={windowProfitByDowBars.PAD}
							y1={windowProfitByDowBars.midY}
							x2={windowProfitByDowBars.W - windowProfitByDowBars.PAD}
							y2={windowProfitByDowBars.midY}
							stroke="var(--ch-axis-muted)"
							stroke-width="0.5"
						/>
						{#each windowProfitByDowBars.rows as row, i (i)}
							{@const x = windowProfitByDowBars.PAD + i * (windowProfitByDowBars.bw + 1)}
							{@const barH = Math.max(
								2,
								(Math.abs(row.avg) / windowProfitByDowBars.maxAbs) *
									(windowProfitByDowBars.midY - 4)
							)}
							{@const y =
								row.avg >= 0 ? windowProfitByDowBars.midY - barH : windowProfitByDowBars.midY}
							{@const color = row.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
							<rect {x} {y} width={windowProfitByDowBars.bw} height={barH} rx="1" fill={color} />
							<text
								x={x + windowProfitByDowBars.bw / 2}
								y={windowProfitByDowBars.H - 1}
								text-anchor="middle"
								font-size="6.5"
								fill="var(--ch-axis-strong)">{row.d}</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg profit% by WF window start day of week · green = positive avg · red = negative ·
						reveals which days windows are launched produce better outcomes
					</p>
				</section>
			{/if}
			{#if windowAvgSharpeByStrategy}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Avg Sharpe by Strategy (WF)
					</h3>
					<svg
						viewBox="0 0 {windowAvgSharpeByStrategy.W} {windowAvgSharpeByStrategy.H}"
						class="w-full"
						style="height:{windowAvgSharpeByStrategy.H}px"
					>
						<line
							x1={windowAvgSharpeByStrategy.zeroX}
							y1={0}
							x2={windowAvgSharpeByStrategy.zeroX}
							y2={windowAvgSharpeByStrategy.H}
							stroke="var(--ch-axis-muted)"
							stroke-width="0.5"
						/>
						{#each windowAvgSharpeByStrategy.rows as row, i (i)}
							{@const y = windowAvgSharpeByStrategy.PAD + i * 20}
							{@const bw = Math.max(
								2,
								(Math.abs(row.avg) / windowAvgSharpeByStrategy.maxAbs) *
									(windowAvgSharpeByStrategy.barMaxW / 2)
							)}
							{@const x =
								row.avg >= 0
									? windowAvgSharpeByStrategy.zeroX
									: windowAvgSharpeByStrategy.zeroX - bw}
							{@const color =
								row.avg >= 1
									? 'var(--ch-profit)'
									: row.avg >= 0
										? 'var(--ch-teal)'
										: 'var(--ch-loss)'}
							<text
								x={windowAvgSharpeByStrategy.PAD}
								y={y + 13}
								font-size="7"
								fill="var(--ch-axis-strong)">{row.name}</text
							>
							<rect {x} {y} width={bw} height="14" rx="2" fill={color} />
							<text
								x={row.avg >= 0
									? windowAvgSharpeByStrategy.zeroX + bw + 2
									: windowAvgSharpeByStrategy.zeroX - bw - 2}
								y={y + 11}
								text-anchor={row.avg >= 0 ? 'start' : 'end'}
								font-size="6.5"
								fill={color}>{row.avg.toFixed(2)}</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg Sharpe ratio per strategy across WF windows · green≥1 · teal≥0 · red&lt;0 ·
						strategies consistently above zero show robust risk-adjusted edge across walk-forward
						periods
					</p>
				</section>
			{/if}
			{#if windowAvgTradeCountByStrategy}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Avg Trade Count by Strategy (WF)
					</h3>
					<svg
						viewBox="0 0 {windowAvgTradeCountByStrategy.W} {windowAvgTradeCountByStrategy.H}"
						class="w-full"
						style="height:{windowAvgTradeCountByStrategy.H}px"
					>
						{#each windowAvgTradeCountByStrategy.rows as row, i (i)}
							{@const y = windowAvgTradeCountByStrategy.PAD + i * 20}
							{@const bw = Math.max(
								2,
								(row.avg / windowAvgTradeCountByStrategy.maxAvg) *
									windowAvgTradeCountByStrategy.barMaxW
							)}
							{@const color =
								row.avg >= windowAvgTradeCountByStrategy.maxAvg * 0.7
									? 'var(--ch-teal-strong)'
									: row.avg >= windowAvgTradeCountByStrategy.maxAvg * 0.4
										? 'var(--ch-violet)'
										: 'var(--ch-axis-muted)'}
							<text
								x={windowAvgTradeCountByStrategy.PAD}
								y={y + 13}
								font-size="7"
								fill="var(--ch-axis-strong)">{row.name}</text
							>
							<rect
								x={windowAvgTradeCountByStrategy.PAD + 70}
								{y}
								width={bw}
								height="14"
								rx="2"
								fill={color}
							/>
							<text
								x={windowAvgTradeCountByStrategy.PAD + 70 + bw + 3}
								y={y + 11}
								font-size="6.5"
								fill={color}>{row.avg.toFixed(0)}</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg trade count per strategy per WF window · teal = high-frequency strategies · low
						count = selective entries · high count = broader market participation
					</p>
				</section>
			{/if}
			{#if windowProfitCDFByTF}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						Avg Profit% by Timeframe (WF)
					</h3>
					<svg
						viewBox="0 0 {windowProfitCDFByTF.W} {windowProfitCDFByTF.H}"
						class="w-full"
						style="height:{windowProfitCDFByTF.H}px"
					>
						<line
							x1={windowProfitCDFByTF.zeroX}
							y1={0}
							x2={windowProfitCDFByTF.zeroX}
							y2={windowProfitCDFByTF.H}
							stroke="var(--ch-axis-muted)"
							stroke-width="0.5"
						/>
						{#each windowProfitCDFByTF.rows as row, i (i)}
							{@const y = windowProfitCDFByTF.PAD + i * 22}
							{@const bw = Math.max(
								2,
								(Math.abs(row.avg) / windowProfitCDFByTF.maxAbs) * (windowProfitCDFByTF.barMaxW / 2)
							)}
							{@const x = row.avg >= 0 ? windowProfitCDFByTF.zeroX : windowProfitCDFByTF.zeroX - bw}
							{@const color =
								row.avg >= 5
									? 'var(--ch-profit)'
									: row.avg >= 0
										? 'var(--ch-teal)'
										: 'var(--ch-loss)'}
							<text
								x={windowProfitCDFByTF.PAD}
								y={y + 14}
								font-size="8"
								fill="var(--ch-axis-strong)">{row.tf}</text
							>
							<rect {x} {y} width={bw} height="15" rx="2" fill={color} />
							<text
								x={row.avg >= 0
									? windowProfitCDFByTF.zeroX + bw + 2
									: windowProfitCDFByTF.zeroX - bw - 2}
								y={y + 12}
								text-anchor={row.avg >= 0 ? 'start' : 'end'}
								font-size="6.5"
								fill={color}>{row.avg.toFixed(1)}% ({row.n})</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg profit% per timeframe across WF windows · green≥5% · teal≥0% · red&lt;0% · window
						count shown in parentheses — higher n = more statistically reliable timeframe estimate
					</p>
				</section>
			{/if}
			{#if windowMonthlyCount}
				<section class="rounded-xl border border-border bg-card p-4">
					<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
						WF Windows per Month
					</h3>
					<svg
						viewBox="0 0 {windowMonthlyCount.W} {windowMonthlyCount.H}"
						class="w-full"
						style="height:{windowMonthlyCount.H}px"
					>
						{#each windowMonthlyCount.pts as pt, i (i)}
							{@const x = windowMonthlyCount.PAD + i * (windowMonthlyCount.bw + 0.5)}
							{@const bh = Math.max(
								2,
								(pt.count / windowMonthlyCount.maxCount) * (windowMonthlyCount.H - 12)
							)}
							{@const y = windowMonthlyCount.H - bh - 6}
							{@const color =
								pt.count >= windowMonthlyCount.maxCount * 0.7
									? 'var(--ch-teal-strong)'
									: 'var(--ch-violet)'}
							<rect {x} {y} width={windowMonthlyCount.bw} height={bh} rx="1" fill={color} />
							<text
								x={x + windowMonthlyCount.bw / 2}
								y={windowMonthlyCount.H - 1}
								text-anchor="middle"
								font-size="5.5"
								fill="var(--ch-axis)">{pt.mo}</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Walk-forward window count per month · teal = months with most WF evaluations · gaps =
						periods without walk-forward testing · rising = increasing research cadence
					</p>
				</section>
			{/if}
			{#if windowMeanProfitByStrategy}
				<section class="rounded-lg border border-border bg-card p-3">
					<h3 class="mb-1 text-xs font-semibold text-muted-foreground">
						Avg WF Profit% by Strategy
					</h3>
					<svg
						viewBox={`0 0 ${windowMeanProfitByStrategy.W} ${windowMeanProfitByStrategy.H}`}
						width="100%"
						style="height:{windowMeanProfitByStrategy.H}px"
					>
						<line
							x1={windowMeanProfitByStrategy.midX}
							y1={windowMeanProfitByStrategy.PAD}
							x2={windowMeanProfitByStrategy.midX}
							y2={windowMeanProfitByStrategy.H - windowMeanProfitByStrategy.PAD}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.5"
						/>
						{#each windowMeanProfitByStrategy.bars as b, i (i)}
							{@const bw =
								(Math.abs(b.avg) / windowMeanProfitByStrategy.maxAbs) *
								(windowMeanProfitByStrategy.midX - windowMeanProfitByStrategy.PAD)}
							{@const y = windowMeanProfitByStrategy.PAD + i * (windowMeanProfitByStrategy.bh + 6)}
							{@const color = b.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
							{@const x =
								b.avg >= 0 ? windowMeanProfitByStrategy.midX : windowMeanProfitByStrategy.midX - bw}
							<rect {x} {y} width={bw} height={windowMeanProfitByStrategy.bh} fill={color} rx="1" />
							<text
								x={windowMeanProfitByStrategy.midX - 3}
								y={y + windowMeanProfitByStrategy.bh / 2 + 2.5}
								text-anchor="end"
								font-size="6"
								fill="var(--ch-axis-strong)">{b.s}</text
							>
							<text
								x={b.avg >= 0
									? windowMeanProfitByStrategy.midX + bw + 2
									: windowMeanProfitByStrategy.midX - bw - 2}
								y={y + windowMeanProfitByStrategy.bh / 2 + 2.5}
								text-anchor={b.avg >= 0 ? 'start' : 'end'}
								font-size="5.5"
								fill={color}>{b.avg.toFixed(2)}%</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg walk-forward profit% per strategy · green=profitable · red=losing · best strategies
						consistently deliver positive out-of-sample WF returns
					</p>
				</section>
			{/if}
			{#if windowDrawdownByDow}
				<section class="rounded-lg border border-border bg-card p-3">
					<h3 class="mb-1 text-xs font-semibold text-muted-foreground">
						Avg WF Drawdown% by Start Day
					</h3>
					<svg
						viewBox={`0 0 ${windowDrawdownByDow.W} ${windowDrawdownByDow.H}`}
						width="100%"
						style="height:65px"
					>
						{#each windowDrawdownByDow.bars as b, i (i)}
							{@const bh =
								(b.avg / windowDrawdownByDow.maxAvg) *
								(windowDrawdownByDow.H - windowDrawdownByDow.PAD * 2)}
							{@const x = windowDrawdownByDow.PAD + i * (windowDrawdownByDow.bw + 2)}
							{@const y = windowDrawdownByDow.H - windowDrawdownByDow.PAD - bh}
							{@const color =
								b.avg <= 10
									? 'var(--ch-profit)'
									: b.avg <= 25
										? 'var(--ch-warn)'
										: 'var(--ch-loss)'}
							<rect {x} {y} width={windowDrawdownByDow.bw} height={bh} fill={color} rx="1" />
							<text
								x={x + windowDrawdownByDow.bw / 2}
								y={windowDrawdownByDow.H}
								text-anchor="middle"
								font-size="6"
								fill="var(--ch-axis)">{b.label}</text
							>
							<text
								x={x + windowDrawdownByDow.bw / 2}
								y={y - 2}
								text-anchor="middle"
								font-size="5.5"
								fill={color}>{b.avg.toFixed(1)}%</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg max drawdown% by WF window start day · green≤10% · yellow≤25% · red&gt;25% · higher
						DD on certain days may signal regime-sensitive entry timing
					</p>
				</section>
			{/if}
			{#if windowProfitTrend}
				<section class="rounded-lg border border-border bg-card p-3">
					<h3 class="mb-1 text-xs font-semibold text-muted-foreground">
						Rolling WF (PF−1)% Trend (8-window)
					</h3>
					<svg
						viewBox={`0 0 ${windowProfitTrend.W} ${windowProfitTrend.H}`}
						width="100%"
						style="height:65px"
					>
						<line
							x1={windowProfitTrend.PAD}
							y1={windowProfitTrend.y0}
							x2={windowProfitTrend.W - windowProfitTrend.PAD}
							y2={windowProfitTrend.y0}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.5"
							stroke-dasharray="2,2"
						/>
						<polyline
							points={windowProfitTrend.polyline}
							fill="none"
							stroke="var(--ch-profit-strong)"
							stroke-width="1.5"
							stroke-linejoin="round"
						/>
						<text
							x={windowProfitTrend.PAD}
							y={windowProfitTrend.H}
							font-size="5.5"
							fill="var(--ch-axis-muted)">{windowProfitTrend.minV}%</text
						>
						<text
							x={windowProfitTrend.W - windowProfitTrend.PAD}
							y={windowProfitTrend.H}
							text-anchor="end"
							font-size="5.5"
							fill="var(--ch-axis-muted)">{windowProfitTrend.maxV}%</text
						>
						<text
							x={windowProfitTrend.PAD}
							y={windowProfitTrend.y0 - 2}
							font-size="5"
							fill="var(--ch-axis-muted)">0%</text
						>
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						8-window rolling WF (PF−1)% across {windowProfitTrend.n} windows · green line · above 0 =
						consistent profit · trend direction indicates walk-forward strategy momentum
					</p>
				</section>
			{/if}
			{#if windowSortinoByDow}
				<section class="rounded-lg border border-border bg-card p-3">
					<h3 class="mb-1 text-xs font-semibold text-muted-foreground">
						Avg WF Sortino by Start Day
					</h3>
					<svg
						viewBox={`0 0 ${windowSortinoByDow.W} ${windowSortinoByDow.H}`}
						width="100%"
						style="height:65px"
					>
						<line
							x1={windowSortinoByDow.PAD}
							y1={windowSortinoByDow.midY}
							x2={windowSortinoByDow.W - windowSortinoByDow.PAD}
							y2={windowSortinoByDow.midY}
							stroke="var(--ch-axis-faint)"
							stroke-width="0.5"
						/>
						{#each windowSortinoByDow.bars as b, i (i)}
							{@const bh = Math.max(
								1,
								(Math.abs(b.avg) / windowSortinoByDow.maxAbs) *
									(windowSortinoByDow.midY - windowSortinoByDow.PAD)
							)}
							{@const x = windowSortinoByDow.PAD + i * (windowSortinoByDow.bw + 2)}
							{@const y = b.avg >= 0 ? windowSortinoByDow.midY - bh : windowSortinoByDow.midY}
							{@const color =
								b.avg >= 1 ? 'var(--ch-profit)' : b.avg >= 0 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
							<rect {x} {y} width={windowSortinoByDow.bw} height={bh} fill={color} rx="1" />
							<text
								x={x + windowSortinoByDow.bw / 2}
								y={windowSortinoByDow.H}
								text-anchor="middle"
								font-size="6"
								fill="var(--ch-axis)">{b.label}</text
							>
							<text
								x={x + windowSortinoByDow.bw / 2}
								y={b.avg >= 0 ? y - 2 : y + bh + 7}
								text-anchor="middle"
								font-size="5.5"
								fill={color}>{b.avg.toFixed(2)}</text
							>
						{/each}
					</svg>
					<p class="mt-1 text-[9px] text-muted-foreground">
						Avg Sortino ratio by WF window start day · green≥1 · teal≥0 · red&lt;0 · day-of-week may
						reveal regime-sensitive entry quality in walk-forward tests
					</p>
				</section>
			{/if}
		</div>
	</details>
</main>
