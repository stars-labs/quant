<script lang="ts">
	import type { PageData } from './$types';
	import FactorBadges from '$lib/components/factor-badges.svelte';
	import InfoTip from '$lib/components/info-tip.svelte';
	import FormulaCard from '$lib/components/formula-card.svelte';
	import Callout from '$lib/components/callout.svelte';
	import { fmtPct, fmtTime } from '$lib/utils';
	import { t, type Lang } from '$lib/i18n';
	import { vps } from '$lib/api';
	import { onMount } from 'svelte';
	import type { BacktestTrade } from '$lib/types';
	import { STRATEGIES } from '$lib/strategies';
	import ChartInfo from '$lib/components/chart-info.svelte';
	import StrategyInfo from '$lib/components/strategy-info.svelte';

	const STRATEGY_FORMULAS: Record<string, { label: string; formula: string; note: string }> = {
		HonestTrend15mDry: {
			label: '入场信号公式',
			formula: 'entry = EMA(fast) 上穿 EMA(slow)\n        且 RSI > 50 且 ATR 确认波动',
			note: 'fast/slow EMA 长度由 Hyperopt 优化（94/139）。持仓最短 12 小时防短线噪音。DCA 加仓最多 2 次，各用 80% 仓位。'
		},
		HonestTrend1mMtf: {
			label: '多时间框架信号',
			formula:
				'entry = 1m EMA cross\n        + 15m trend filter (同向)\n        + 1h regime filter (多头环境)',
			note: '三层时间框架过滤：1m 触发 → 15m 趋势确认 → 1h 大周期环境。减少逆势假突破。'
		}
	};

	let { data }: { data: PageData } = $props();
	const { meta, strategyName, runs, wfLatest, wfDate, currentFactors } = data;
	const lang = $derived<Lang>(data.lang ?? 'zh');

	const statusTone: Record<string, string> = {
		live: 'bg-green-950 text-green-400 border-green-800',
		dryrun: 'bg-yellow-950 text-yellow-400 border-yellow-800',
		research: 'bg-blue-950 text-blue-400 border-blue-800',
		retired: 'bg-muted text-muted-foreground border-border'
	};

	const wfMax = Math.max(1, ...wfLatest.map((w) => Math.abs(w.tot_profit_pct ?? 0)));

	function signClass(v: number | null | undefined): string {
		if (v == null) return 'text-muted-foreground';
		return v > 0 ? 'text-green-500' : v < 0 ? 'text-red-500' : 'text-muted-foreground';
	}

	function fmt(key: string, vars: Record<string, string | number>) {
		let s = t(lang, key);
		for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
		return s;
	}

	// Daily P&L calendar — loaded lazily from best run
	let calendarTrades = $state<BacktestTrade[]>([]);
	let calendarLoading = $state(false);
	let calendarLoaded = $state(false);

	// Top-level aliases so analytics blocks can reference `trades` and
	// `selectedTrades` directly (some blocks were authored against bare
	// symbols — these derived aliases avoid ReferenceErrors at SSR time).
	const trades = $derived(calendarTrades);
	const selectedTrades = $derived(calendarTrades);

	const bestRunId = $derived(runs[0]?.id ?? null);

	// CAGR: annualized return from best run's profit% and timerange
	const cagrData = $derived.by(() => {
		const run = runs[0];
		if (!run?.total_profit_pct || !run.timerange) return null;
		const match = run.timerange.match(/(\d{8})-(\d{8})/);
		if (!match) return null;
		const parse = (s: string) => new Date(`${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`);
		const start = parse(match[1]),
			end = parse(match[2]);
		const years = (end.getTime() - start.getTime()) / (365.25 * 24 * 3600 * 1000);
		if (years < 0.1) return null;
		const totalReturn = run.total_profit_pct / 100;
		const cagr = (Math.pow(1 + totalReturn, 1 / years) - 1) * 100;
		return {
			cagr,
			years: years.toFixed(1),
			profit: run.total_profit_pct,
			timerange: run.timerange
		};
	});

	const calendarData = $derived.by(() => {
		if (calendarTrades.length === 0) return { weeks: [], maxAbs: 0, minDate: '', maxDate: '' };
		// Group by close_date day
		const byDay = new Map<string, number>();
		for (const t of calendarTrades) {
			if (!t.close_date || t.profit_abs == null) continue;
			const day = t.close_date.slice(0, 10);
			byDay.set(day, (byDay.get(day) ?? 0) + t.profit_abs);
		}
		if (byDay.size === 0) return { weeks: [], maxAbs: 0, minDate: '', maxDate: '' };

		const days = [...byDay.keys()].sort();
		const minDate = days[0];
		const maxDate = days[days.length - 1];
		const maxAbs = Math.max(...[...byDay.values()].map(Math.abs), 1);

		// Build week grid: Sunday-anchored
		const start = new Date(minDate);
		start.setDate(start.getDate() - start.getDay()); // go back to Sunday
		const end = new Date(maxDate);
		end.setDate(end.getDate() + (6 - end.getDay())); // forward to Saturday

		const weeks: { date: string; profit: number | null }[][] = [];
		let week: { date: string; profit: number | null }[] = [];
		const cur = new Date(start);
		while (cur <= end) {
			const key = cur.toISOString().slice(0, 10);
			week.push({ date: key, profit: byDay.has(key) ? (byDay.get(key) ?? 0) : null });
			if (cur.getDay() === 6) {
				weeks.push(week);
				week = [];
			}
			cur.setDate(cur.getDate() + 1);
		}
		if (week.length) weeks.push(week);
		return { weeks, maxAbs, minDate, maxDate };
	});

	function cellColor(profit: number | null, maxAbs: number): string {
		if (profit === null) return 'bg-muted/20';
		if (Math.abs(profit) < 0.01) return 'bg-muted/40';
		const intensity = Math.min(Math.abs(profit) / maxAbs, 1);
		if (profit > 0) {
			if (intensity > 0.7) return 'bg-green-500';
			if (intensity > 0.35) return 'bg-green-600/70';
			return 'bg-green-800/50';
		} else {
			if (intensity > 0.7) return 'bg-red-500';
			if (intensity > 0.35) return 'bg-red-600/70';
			return 'bg-red-900/50';
		}
	}

	async function loadCalendar() {
		if (calendarLoaded || calendarLoading || !bestRunId) return;
		calendarLoading = true;
		try {
			calendarTrades = await vps.backtestTrades(fetch, bestRunId, { limit: 50000 });
			calendarLoaded = true;
		} finally {
			calendarLoading = false;
		}
	}

	onMount(() => {
		if (bestRunId) loadCalendar();
	});

	// Time-of-day × day-of-week heatmap
	const DOW_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
	const timeHeatmap = $derived.by(() => {
		if (calendarTrades.length === 0) return null;
		const grid: Record<string, { sum: number; count: number }> = {};
		for (const t of calendarTrades) {
			if (!t.close_date || t.profit_pct == null) continue;
			const d = new Date(t.close_date);
			const dow = d.getUTCDay();
			const h = d.getUTCHours();
			const key = `${dow}-${h}`;
			if (!grid[key]) grid[key] = { sum: 0, count: 0 };
			grid[key].sum += t.profit_pct;
			grid[key].count++;
		}
		let maxAbs = 0.1;
		for (const v of Object.values(grid)) {
			const avg = v.sum / v.count;
			if (Math.abs(avg) > maxAbs) maxAbs = Math.abs(avg);
		}
		return { grid, maxAbs };
	});

	function heatColor(sum: number | undefined, count: number | undefined, maxAbs: number): string {
		if (!count || sum == null) return 'bg-muted/15';
		const avg = sum / count;
		const intensity = Math.min(Math.abs(avg) / maxAbs, 1);
		if (avg > 0) {
			if (intensity > 0.6) return 'bg-green-500';
			if (intensity > 0.3) return 'bg-green-700/60';
			return 'bg-green-900/40';
		} else {
			if (intensity > 0.6) return 'bg-red-500';
			if (intensity > 0.3) return 'bg-red-700/60';
			return 'bg-red-900/40';
		}
	}

	// Entry time heatmap (open_date → count per dow×hour)
	const entryHeatmap = $derived.by(() => {
		if (calendarTrades.length === 0) return null;
		const grid: Record<string, number> = {};
		for (const t of calendarTrades) {
			if (!t.open_date) continue;
			const d = new Date(t.open_date);
			const dow = d.getUTCDay();
			const h = d.getUTCHours();
			const key = `${dow}-${h}`;
			grid[key] = (grid[key] ?? 0) + 1;
		}
		const maxCount = Math.max(1, ...Object.values(grid));
		return { grid, maxCount };
	});

	// Exit reason breakdown
	const exitReasons = $derived.by(() => {
		if (calendarTrades.length === 0) return null;
		const map = new Map<string, { count: number; wins: number; totalProfit: number }>();
		for (const t of calendarTrades) {
			const reason = t.exit_reason ?? 'unknown';
			if (!map.has(reason)) map.set(reason, { count: 0, wins: 0, totalProfit: 0 });
			const r = map.get(reason)!;
			r.count++;
			if ((t.profit_pct ?? 0) > 0) r.wins++;
			r.totalProfit += t.profit_abs ?? 0;
		}
		const entries = [...map.entries()]
			.map(([reason, v]) => ({ reason, ...v, wr: v.wins / v.count }))
			.sort((a, b) => b.count - a.count);
		const maxCount = Math.max(1, ...entries.map((e) => e.count));
		return entries.map((e) => ({ ...e, barPct: (e.count / maxCount) * 100 }));
	});

	// Avg profit per exit reason (distinct from exitReasons which is count-sorted)
	const exitReasonAvgProfit = $derived.by(() => {
		const valid = calendarTrades.filter((t) => t.exit_reason && t.profit_pct != null);
		if (valid.length < 8) return null;
		const map = new Map<string, { profitSum: number; count: number; wins: number }>();
		for (const t of valid) {
			const r = t.exit_reason!;
			if (!map.has(r)) map.set(r, { profitSum: 0, count: 0, wins: 0 });
			const v = map.get(r)!;
			v.profitSum += t.profit_pct!;
			v.count++;
			if (t.profit_pct! > 0) v.wins++;
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.count >= 2)
			.map(([reason, v]) => ({
				reason,
				avgProfit: v.profitSum / v.count,
				count: v.count,
				wr: v.wins / v.count
			}))
			.sort((a, b) => b.avgProfit - a.avgProfit);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(0.001, ...rows.map((r) => Math.abs(r.avgProfit)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.avgProfit) / maxAbs) * 100 }));
	});

	// Pair contribution table
	const pairStats = $derived.by(() => {
		if (calendarTrades.length === 0) return null;
		const map = new Map<string, { count: number; wins: number; profit: number }>();
		for (const t of calendarTrades) {
			if (!map.has(t.pair)) map.set(t.pair, { count: 0, wins: 0, profit: 0 });
			const r = map.get(t.pair)!;
			r.count++;
			if ((t.profit_pct ?? 0) > 0) r.wins++;
			r.profit += t.profit_abs ?? 0;
		}
		return [...map.entries()]
			.map(([pair, v]) => ({ pair, ...v, wr: v.wins / v.count }))
			.sort((a, b) => b.profit - a.profit);
	});

	// Similar strategies (static catalog, asset+mode Jaccard)
	const similarStrategies = $derived.by(() => {
		if (!meta) return [];
		const myAssets = new Set(meta.assets);
		return STRATEGIES.filter((s) => s.name !== strategyName)
			.map((s) => {
				const allAssets = new Set([...myAssets, ...s.assets]);
				const sharedAssets = s.assets.filter((a) => myAssets.has(a)).length;
				const assetJ = sharedAssets / (allAssets.size || 1);
				const sameMode = s.mode === meta.mode ? 0.4 : 0;
				const score = assetJ * 0.6 + sameMode;
				return { name: s.name, mode: s.mode, status: s.status, score };
			})
			.filter((s) => s.score > 0.2)
			.sort((a, b) => b.score - a.score)
			.slice(0, 4);
	});

	// Drawdown episodes
	const drawdownEpisodes = $derived.by(() => {
		const closed = calendarTrades
			.filter((t) => t.close_date && t.profit_abs != null)
			.sort((a, b) => a.close_date!.localeCompare(b.close_date!));
		if (closed.length < 5) return null;
		// Build equity curve
		let equity = 0;
		const curve = closed.map((t) => {
			equity += t.profit_abs!;
			return { date: t.close_date!, equity };
		});
		// Find drawdown episodes
		type Episode = {
			peakDate: string;
			peakEq: number;
			troughDate: string;
			troughEq: number;
			depth: number;
			recoveryDate: string | null;
		};
		const episodes: Episode[] = [];
		let peakI = 0;
		for (let i = 1; i < curve.length; i++) {
			if (curve[i].equity > curve[peakI].equity) {
				// If we were in a drawdown, close it
				if (i > peakI + 1) {
					const troughI =
						curve
							.slice(peakI, i)
							.reduce((mi, v, j) => (v.equity < curve[peakI + mi].equity ? j : mi), 0) + peakI;
					const depth = curve[peakI].equity - curve[troughI].equity;
					if (depth > 0)
						episodes.push({
							peakDate: curve[peakI].date,
							peakEq: curve[peakI].equity,
							troughDate: curve[troughI].date,
							troughEq: curve[troughI].equity,
							depth,
							recoveryDate: curve[i].date
						});
				}
				peakI = i;
			}
		}
		// Check for ongoing drawdown at end
		const lastPeakI = curve.reduce((mi, v, i) => (v.equity > curve[mi].equity ? i : mi), 0);
		if (lastPeakI < curve.length - 1) {
			const troughI =
				curve
					.slice(lastPeakI)
					.reduce((mi, v, j) => (v.equity < curve[lastPeakI + mi].equity ? j : mi), 0) + lastPeakI;
			const depth = curve[lastPeakI].equity - curve[troughI].equity;
			if (depth > 0)
				episodes.push({
					peakDate: curve[lastPeakI].date,
					peakEq: curve[lastPeakI].equity,
					troughDate: curve[troughI].date,
					troughEq: curve[troughI].equity,
					depth,
					recoveryDate: null
				});
		}
		return episodes.sort((a, b) => b.depth - a.depth).slice(0, 5);
	});

	// Profit distribution histogram
	const profitHistogram = $derived.by(() => {
		const vals = calendarTrades.map((t) => t.profit_pct).filter((v): v is number => v != null);
		if (vals.length < 10) return null;
		const mn = Math.min(...vals),
			mx = Math.max(...vals);
		const BINS = 20;
		const step = (mx - mn) / BINS || 0.01;
		const bins = Array.from({ length: BINS }, (_, i) => ({
			lo: mn + i * step,
			hi: mn + (i + 1) * step,
			count: 0,
			wins: 0
		}));
		for (const v of vals) {
			const i = Math.min(BINS - 1, Math.floor((v - mn) / step));
			bins[i].count++;
			if (v > 0) bins[i].wins++;
		}
		const maxCount = Math.max(1, ...bins.map((b) => b.count));
		const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
		const sorted = [...vals].sort((a, b) => a - b);
		const median = sorted[Math.floor(sorted.length / 2)];
		return { bins, maxCount, mean, median, mn, mx };
	});

	// Trade P&L strip: last 60 trades as sized color blocks
	const tradeStrip = $derived.by(() => {
		const sorted = calendarTrades
			.filter((t) => t.close_date && t.profit_pct != null)
			.sort((a, b) => a.close_date!.localeCompare(b.close_date!))
			.slice(-60);
		if (sorted.length < 10) return null;
		const maxAbs = Math.max(0.01, ...sorted.map((t) => Math.abs(t.profit_pct!)));
		return sorted.map((t) => ({
			pct: t.profit_pct!,
			pair: t.pair,
			close: t.close_date!.slice(0, 10),
			size: Math.max(0.05, Math.abs(t.profit_pct!) / maxAbs)
		}));
	});

	// Rolling 20-trade win-rate sparkline
	const rollingWR = $derived.by(() => {
		const sorted = calendarTrades
			.filter((t) => t.close_date && t.profit_pct != null)
			.sort((a, b) => a.close_date!.localeCompare(b.close_date!));
		const WINDOW = 20;
		if (sorted.length < WINDOW + 5) return null;
		const points: { date: string; wr: number }[] = [];
		for (let i = WINDOW - 1; i < sorted.length; i++) {
			const slice = sorted.slice(i - WINDOW + 1, i + 1);
			const wins = slice.filter((t) => (t.profit_pct ?? 0) > 0).length;
			points.push({ date: sorted[i].close_date!, wr: wins / WINDOW });
		}
		const W = 560,
			H = 60,
			PAD = 4;
		const wrs = points.map((p) => p.wr);
		const mn = Math.min(...wrs),
			mx = Math.max(...wrs);
		const range = mx - mn || 0.01;
		const toX = (i: number) => PAD + (i / (points.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / range) * (H - PAD * 2);
		const poly = points.map((p, i) => `${toX(i)},${toY(p.wr)}`).join(' ');
		const avgWr = wrs.reduce((a, b) => a + b, 0) / wrs.length;
		const avgY = toY(avgWr);
		const fiftyY = toY(0.5);
		const latestWr = wrs[wrs.length - 1];
		return {
			poly,
			W,
			H,
			PAD,
			avgWr,
			avgY,
			fiftyY,
			latestWr,
			firstDate: points[0].date.slice(0, 10),
			lastDate: points[points.length - 1].date.slice(0, 10),
			mn,
			mx
		};
	});

	// Raw equity curve (sequential closed trades)
	const equityCurve = $derived.by(() => {
		const sorted = calendarTrades
			.filter((t) => t.close_date && t.profit_abs != null)
			.sort((a, b) => a.close_date!.localeCompare(b.close_date!));
		if (sorted.length < 10) return null;
		let equity = 0;
		const pts = sorted.map((t) => {
			equity += t.profit_abs!;
			return equity;
		});
		const W = 560,
			H = 100,
			PAD = 4;
		const mn = Math.min(0, ...pts);
		const mx = Math.max(...pts, 0.01);
		const range = mx - mn || 0.01;
		const toX = (i: number) => PAD + (i / (pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / range) * (H - PAD * 2);
		const zeroY = toY(0);
		const linePts = pts.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
		const areaPts = `${PAD},${zeroY.toFixed(1)} ${linePts} ${W - PAD},${zeroY.toFixed(1)}`;
		const final = pts[pts.length - 1];
		const peak = Math.max(...pts);
		return {
			linePts,
			areaPts,
			W,
			H,
			PAD,
			zeroY,
			final,
			peak,
			mn,
			mx,
			firstDate: sorted[0].close_date!.slice(0, 10),
			lastDate: sorted[sorted.length - 1].close_date!.slice(0, 10)
		};
	});

	// Underwater drawdown chart — running drawdown depth (equity/peak - 1)
	const underwaterChart = $derived.by(() => {
		const sorted = calendarTrades
			.filter((t) => t.close_date && t.profit_abs != null)
			.sort((a, b) => a.close_date!.localeCompare(b.close_date!));
		if (sorted.length < 10) return null;
		let equity = 0;
		let peak = 0;
		const dd: number[] = [];
		for (const t of sorted) {
			equity += t.profit_abs!;
			if (equity > peak) peak = equity;
			dd.push(peak > 0 ? ((equity - peak) / peak) * 100 : 0);
		}
		const minDD = Math.min(...dd, -0.01);
		const W = 560,
			H = 60,
			PAD = 4;
		const toX = (i: number) => PAD + (i / (dd.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (v / minDD) * (H - PAD * 2);
		const linePts = dd.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
		const areaPts = `${PAD},${PAD} ${linePts} ${W - PAD},${PAD}`;
		const maxDD = minDD;
		const avgDD = dd.reduce((a, b) => a + b, 0) / dd.length;
		return { linePts, areaPts, W, H, PAD, maxDD, avgDD };
	});

	// Expectancy breakdown
	const expectancy = $derived.by(() => {
		const trades = calendarTrades.filter((t) => t.profit_pct != null);
		if (trades.length < 10) return null;
		const wins = trades.filter((t) => t.profit_pct! > 0);
		const losses = trades.filter((t) => t.profit_pct! <= 0);
		const wr = wins.length / trades.length;
		const avgWin = wins.length ? wins.reduce((s, t) => s + t.profit_pct!, 0) / wins.length : 0;
		const avgLoss = losses.length
			? Math.abs(losses.reduce((s, t) => s + t.profit_pct!, 0) / losses.length)
			: 0;
		const expectancyVal = wr * avgWin - (1 - wr) * avgLoss;
		const payoffRatio = avgLoss > 0 ? avgWin / avgLoss : null;
		return {
			wr,
			avgWin,
			avgLoss,
			expectancyVal,
			payoffRatio,
			n: trades.length,
			wins: wins.length,
			losses: losses.length
		};
	});

	// Monthly P&L heatmap: year × month grid
	const monthlyPnl = $derived.by(() => {
		const trades = calendarTrades.filter((t) => t.close_date && t.profit_abs != null);
		if (trades.length < 10) return null;
		const byYM = new Map<string, number>();
		for (const t of trades) {
			const key = t.close_date!.slice(0, 7); // YYYY-MM
			byYM.set(key, (byYM.get(key) ?? 0) + t.profit_abs!);
		}
		const keys = [...byYM.keys()].sort();
		const years = [...new Set(keys.map((k) => k.slice(0, 4)))].sort();
		if (years.length === 0) return null;
		const vals = [...byYM.values()];
		const maxAbs = Math.max(1, ...vals.map(Math.abs));
		const MONTHS = [
			'Jan',
			'Feb',
			'Mar',
			'Apr',
			'May',
			'Jun',
			'Jul',
			'Aug',
			'Sep',
			'Oct',
			'Nov',
			'Dec'
		];
		const grid = years.map((yr) =>
			MONTHS.map((_, mi) => {
				const key = `${yr}-${String(mi + 1).padStart(2, '0')}`;
				const v = byYM.get(key) ?? null;
				return { key, v, pct: v == null ? 0 : v / maxAbs };
			})
		);
		const total = vals.reduce((a, b) => a + b, 0);
		const winMonths = [...byYM.values()].filter((v) => v > 0).length;
		return { grid, years, MONTHS, total, winMonths, total_months: byYM.size };
	});

	// Consecutive win/loss streak analysis
	const streakStats = $derived.by(() => {
		const trades = calendarTrades
			.filter((t) => t.close_date && t.profit_pct != null)
			.sort((a, b) => a.close_date!.localeCompare(b.close_date!));
		if (trades.length < 5) return null;
		let maxWin = 0,
			maxLoss = 0,
			curWin = 0,
			curLoss = 0;
		for (const t of trades) {
			const win = t.profit_pct! > 0;
			if (win) {
				curWin++;
				curLoss = 0;
				maxWin = Math.max(maxWin, curWin);
			} else {
				curLoss++;
				curWin = 0;
				maxLoss = Math.max(maxLoss, curLoss);
			}
		}
		// Current streak (from end)
		const last = trades[trades.length - 1];
		const isWinStreak = last.profit_pct! > 0;
		let currentStreak = 0;
		for (let i = trades.length - 1; i >= 0; i--) {
			const w = trades[i].profit_pct! > 0;
			if (w === isWinStreak) currentStreak++;
			else break;
		}
		return { maxWin, maxLoss, currentStreak, isWinStreak, total: trades.length };
	});

	// Best and worst individual trades by profit_abs
	const extremeTrades = $derived.by(() => {
		const trades = calendarTrades.filter((t) => t.profit_abs != null && t.pair && t.close_date);
		if (trades.length < 6) return null;
		const sorted = [...trades].sort((a, b) => b.profit_abs! - a.profit_abs!);
		const best = sorted.slice(0, 3);
		const worst = sorted.slice(-3).reverse();
		return { best, worst };
	});

	// Enter tag performance
	const enterTagStats = $derived.by(() => {
		if (calendarTrades.length === 0) return null;
		const map = new Map<
			string,
			{ count: number; wins: number; profit: number; profitPcts: number[] }
		>();
		for (const t of calendarTrades) {
			const tag = t.enter_tag ?? 'default';
			if (!map.has(tag)) map.set(tag, { count: 0, wins: 0, profit: 0, profitPcts: [] });
			const r = map.get(tag)!;
			r.count++;
			if ((t.profit_pct ?? 0) > 0) r.wins++;
			r.profit += t.profit_abs ?? 0;
			if (t.profit_pct != null) r.profitPcts.push(t.profit_pct);
		}
		return [...map.entries()]
			.map(([tag, v]) => ({
				tag,
				count: v.count,
				wr: v.wins / v.count,
				profit: v.profit,
				avgPct: v.profitPcts.length
					? v.profitPcts.reduce((a, b) => a + b, 0) / v.profitPcts.length
					: 0
			}))
			.sort((a, b) => b.count - a.count)
			.slice(0, 12);
	});

	// Enter-tag profit contribution (share of total profit)
	const enterTagProfitShare = $derived.by(() => {
		const trades = calendarTrades.filter((t) => t.profit_abs != null);
		if (trades.length < 5) return null;
		const map = new Map<string, { profit: number; count: number; wins: number }>();
		for (const t of trades) {
			const tag = t.enter_tag ?? 'default';
			if (!map.has(tag)) map.set(tag, { profit: 0, count: 0, wins: 0 });
			const e = map.get(tag)!;
			e.profit += t.profit_abs!;
			e.count++;
			if ((t.profit_pct ?? 0) > 0) e.wins++;
		}
		const rows = [...map.entries()]
			.map(([tag, v]) => ({ tag, ...v, wr: v.wins / v.count }))
			.sort((a, b) => b.profit - a.profit);
		if (rows.length < 2) return null;
		const totalAbs = rows.reduce((s, r) => s + Math.abs(r.profit), 0) || 1;
		const totalProfit = rows.reduce((s, r) => s + r.profit, 0);
		return { rows: rows.slice(0, 10), totalAbs, totalProfit };
	});

	// Rolling profit factor (20-trade window): gross win / |gross loss|
	const rollingPF = $derived.by(() => {
		const trades = [...calendarTrades]
			.filter((t) => t.profit_abs != null)
			.sort((a, b) => {
				const da = a.close_date ?? a.open_date,
					db = b.close_date ?? b.open_date;
				return da < db ? -1 : da > db ? 1 : 0;
			});
		const W = 20;
		if (trades.length < W + 2) return null;
		const pts: { idx: number; pf: number }[] = [];
		for (let i = W - 1; i < trades.length; i++) {
			const window = trades.slice(i - W + 1, i + 1);
			const wins = window
				.filter((t) => (t.profit_abs ?? 0) > 0)
				.reduce((s, t) => s + t.profit_abs!, 0);
			const losses = Math.abs(
				window.filter((t) => (t.profit_abs ?? 0) < 0).reduce((s, t) => s + t.profit_abs!, 0)
			);
			const pf = losses === 0 ? (wins > 0 ? 4 : 1) : Math.min(4, wins / losses);
			pts.push({ idx: i, pf });
		}
		if (pts.length < 3) return null;
		const pfVals = pts.map((p) => p.pf);
		const pfMax = Math.max(2, ...pfVals);
		const W_SVG = 560,
			H_SVG = 70,
			PAD = 6;
		const toX = (i: number) =>
			PAD + ((i - (W - 1)) / Math.max(1, trades.length - W)) * (W_SVG - PAD * 2);
		const toY = (v: number) => H_SVG - PAD - (v / pfMax) * (H_SVG - PAD * 2);
		const oneY = toY(1);
		const polyline = pts.map((p) => `${toX(p.idx).toFixed(1)},${toY(p.pf).toFixed(1)}`).join(' ');
		const avg = pfVals.reduce((a, b) => a + b, 0) / pfVals.length;
		return { polyline, W: W_SVG, H: H_SVG, PAD, pfMax, oneY, avg, total: pts.length };
	});

	// Trade entry hour distribution: which UTC hours see the most entries and best WR
	const entryHourChart = $derived.by(() => {
		const trades = calendarTrades.filter((t) => t.open_date && t.profit_pct != null);
		if (trades.length < 8) return null;
		const hours = Array.from({ length: 24 }, (_, h) => ({ h, count: 0, wins: 0, profit: 0 }));
		for (const t of trades) {
			const h = new Date(t.open_date).getUTCHours();
			hours[h].count++;
			if ((t.profit_pct ?? 0) > 0) hours[h].wins++;
			hours[h].profit += t.profit_abs ?? 0;
		}
		const active = hours.filter((h) => h.count > 0);
		if (active.length < 3) return null;
		const maxCount = Math.max(1, ...hours.map((h) => h.count));
		return hours.map((h) => ({
			...h,
			barPct: (h.count / maxCount) * 100,
			wr: h.count > 0 ? h.wins / h.count : 0
		}));
	});

	// Profit by hold-duration tier
	const profitByDuration = $derived.by(() => {
		const trades = calendarTrades.filter(
			(t) => t.trade_duration_min != null && t.profit_pct != null && t.profit_abs != null
		);
		if (trades.length < 10) return null;
		type Trade = (typeof trades)[number];
		const tiers: { label: string; max: number; trades: Trade[] }[] = [
			{ label: 'Short\n<4h', max: 240, trades: [] },
			{ label: 'Medium\n4-24h', max: 1440, trades: [] },
			{ label: 'Long\n1-7d', max: 10080, trades: [] },
			{ label: 'Very Long\n7d+', max: Infinity, trades: [] }
		];
		for (const t of trades) {
			const tier = tiers.find((tier) => t.trade_duration_min! < tier.max);
			if (tier) tier.trades.push(t);
		}
		const maxAbsProfit = Math.max(
			1,
			...tiers.map((t) => Math.abs(t.trades.reduce((s, tr) => s + tr.profit_abs!, 0)))
		);
		return tiers
			.filter((t) => t.trades.length > 0)
			.map((t) => {
				const wins = t.trades.filter((tr) => tr.profit_pct! > 0);
				const totalProfit = t.trades.reduce((s, tr) => s + tr.profit_abs!, 0);
				const avgPct = t.trades.reduce((s, tr) => s + tr.profit_pct!, 0) / t.trades.length;
				return {
					label: t.label,
					count: t.trades.length,
					wr: wins.length / t.trades.length,
					totalProfit,
					avgPct,
					barPct: (Math.abs(totalProfit) / maxAbsProfit) * 100,
					positive: totalProfit >= 0
				};
			});
	});

	// Trade scatter: duration (log) vs profit_pct
	const tradeScatter = $derived.by(() => {
		const trades = calendarTrades.filter(
			(t) => t.trade_duration_min != null && t.profit_pct != null
		);
		if (trades.length < 10) return null;
		const W = 560,
			H = 140,
			PAD = 4;
		const durations = trades.map((t) => Math.log10(Math.max(1, t.trade_duration_min!)));
		const profits = trades.map((t) => t.profit_pct!);
		const dMin = Math.min(...durations),
			dMax = Math.max(...durations);
		const pMin = Math.min(...profits) * 1.1,
			pMax = Math.max(...profits) * 1.1;
		const zeroY = ((0 - pMin) / (pMax - pMin || 1)) * (H - PAD * 2);
		const dots = trades.map((t, i) => ({
			x: PAD + ((durations[i] - dMin) / (dMax - dMin || 1)) * (W - PAD * 2),
			y: H - PAD - ((profits[i] - pMin) / (pMax - pMin || 1)) * (H - PAD * 2),
			win: profits[i] > 0,
			tip: `${t.pair} ${t.trade_duration_min}min ${profits[i] >= 0 ? '+' : ''}${profits[i].toFixed(2)}%`
		}));
		const gridDurations = [1, 60, 1440, 10080]
			.map((v) => ({
				x: PAD + ((Math.log10(v) - dMin) / (dMax - dMin || 1)) * (W - PAD * 2),
				label: v < 60 ? `${v}m` : v < 1440 ? `${v / 60}h` : v < 10080 ? `${v / 1440}d` : '7d'
			}))
			.filter((v) => v.x >= PAD && v.x <= W - PAD);
		return { dots, W, H, PAD, zeroY: H - PAD - zeroY, gridDurations };
	});

	// Trade duration histogram
	const DURATION_BUCKETS = [
		{ label: '<1h', min: 0, max: 60 },
		{ label: '1-4h', min: 60, max: 240 },
		{ label: '4-12h', min: 240, max: 720 },
		{ label: '12-24h', min: 720, max: 1440 },
		{ label: '1-3d', min: 1440, max: 4320 },
		{ label: '3-7d', min: 4320, max: 10080 },
		{ label: '7d+', min: 10080, max: Infinity }
	];
	const durationHistogram = $derived.by(() => {
		if (calendarTrades.length === 0) return null;
		const buckets = DURATION_BUCKETS.map((b) => ({ ...b, count: 0, wins: 0 }));
		for (const t of calendarTrades) {
			if (t.trade_duration_min == null) continue;
			const d = t.trade_duration_min;
			const b = buckets.find((b) => d >= b.min && d < b.max);
			if (!b) continue;
			b.count++;
			if ((t.profit_pct ?? 0) > 0) b.wins++;
		}
		const maxCount = Math.max(1, ...buckets.map((b) => b.count));
		return buckets.map((b) => ({
			...b,
			pct: b.count / maxCount,
			wr: b.count > 0 ? b.wins / b.count : 0
		}));
	});

	// Day-of-week avg profit bars
	const DOW_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
	const dowPnl = $derived.by(() => {
		const trades = calendarTrades.filter((t) => t.close_date && t.profit_abs != null);
		if (trades.length < 14) return null;
		const byDow = Array.from({ length: 7 }, () => ({ sum: 0, count: 0, wins: 0 }));
		for (const t of trades) {
			const dow = new Date(t.close_date!).getUTCDay();
			byDow[dow].sum += t.profit_abs!;
			byDow[dow].count++;
			if ((t.profit_pct ?? 0) > 0) byDow[dow].wins++;
		}
		const maxAbs = Math.max(1, ...byDow.map((d) => Math.abs(d.sum)));
		return byDow.map((d, i) => ({
			label: DOW_NAMES[i],
			sum: d.sum,
			count: d.count,
			wr: d.count > 0 ? d.wins / d.count : 0,
			barPct: d.count > 0 ? (Math.abs(d.sum) / maxAbs) * 100 : 0,
			positive: d.sum >= 0
		}));
	});

	// Optimization trend: is the strategy improving over time?
	const optimizationTrend = $derived.by(() => {
		const sorted = [...runs]
			.filter((r) => r.imported_at && r.total_profit_pct != null && r.sharpe != null)
			.sort((a, b) => a.imported_at.localeCompare(b.imported_at));
		if (sorted.length < 4) return null;
		const n = Math.max(2, Math.floor(sorted.length / 3));
		const early = sorted.slice(0, n);
		const recent = sorted.slice(-n);
		const avgProfit = (arr: typeof sorted) =>
			arr.reduce((s, r) => s + r.total_profit_pct!, 0) / arr.length;
		const avgSharpe = (arr: typeof sorted) => arr.reduce((s, r) => s + r.sharpe!, 0) / arr.length;
		const profitDelta = avgProfit(recent) - avgProfit(early);
		const sharpeDelta = avgSharpe(recent) - avgSharpe(early);
		const improving = profitDelta > 2 && sharpeDelta > 0.1;
		const declining = profitDelta < -2 && sharpeDelta < -0.1;
		return {
			label: improving ? 'Improving' : declining ? 'Declining' : 'Stable',
			icon: improving ? '↑' : declining ? '↓' : '→',
			color: improving
				? 'text-green-400 bg-green-950/40 border-green-700/50'
				: declining
					? 'text-red-400 bg-red-950/30 border-red-700/40'
					: 'text-muted-foreground bg-secondary/40 border-border',
			profitDelta,
			sharpeDelta,
			n
		};
	});

	// Percentile rank of best run among all runs
	const bestRunPercentiles = $derived.by(() => {
		if (runs.length < 3 || !runs[0]) return null;
		const best = runs[0];
		function pctRank(
			vals: (number | null | undefined)[],
			v: number | null | undefined
		): number | null {
			if (v == null) return null;
			const valid = vals.filter((x): x is number => x != null);
			if (valid.length < 2) return null;
			const below = valid.filter((x) => x < v).length;
			return Math.round((below / (valid.length - 1)) * 100);
		}
		const profits = runs.map((r) => r.total_profit_pct);
		const sharpes = runs.map((r) => r.sharpe);
		const dds = runs.map((r) => r.max_drawdown_pct);
		return {
			profit: pctRank(profits, best.total_profit_pct),
			sharpe: pctRank(sharpes, best.sharpe),
			dd:
				dds.filter((x): x is number => x != null).length >= 2
					? Math.round(
							(runs.filter((r) => (r.max_drawdown_pct ?? 0) > (best.max_drawdown_pct ?? 0)).length /
								(runs.length - 1)) *
								100
						)
					: null
		};
	});

	// Runs-over-time sparkline (sort by imported_at)
	const runsTimeSeries = $derived.by(() => {
		if (runs.length < 3) return null;
		const sorted = [...runs]
			.filter((r) => r.imported_at && r.total_profit_pct != null)
			.sort((a, b) => a.imported_at.localeCompare(b.imported_at));
		if (sorted.length < 3) return null;

		const profits = sorted.map((r) => r.total_profit_pct!);
		const sharpes = sorted.map((r) => r.sharpe ?? 0);
		const dds = sorted.map((r) => r.max_drawdown_pct ?? 0);

		const W = 560,
			H = 80;
		function spark(vals: number[], color: string) {
			const mn = Math.min(...vals),
				mx = Math.max(...vals, mn + 0.001);
			const pts = vals
				.map((v, i) => {
					const x = (i / (vals.length - 1)) * W;
					const y = H - ((v - mn) / (mx - mn)) * H;
					return `${x.toFixed(1)},${y.toFixed(1)}`;
				})
				.join(' ');
			return { pts, color, last: vals[vals.length - 1], mn, mx };
		}
		return {
			profit: spark(profits, 'rgb(34,197,94)'),
			sharpe: spark(sharpes, 'rgb(129,140,248)'),
			dd: spark(dds, 'rgb(239,68,68)'),
			dates: sorted.map((r) => r.imported_at.slice(0, 10)),
			W,
			H
		};
	});

	// Weekly P&L bar chart from calendarTrades
	const weeklyPnlBars = $derived.by(() => {
		const closed = calendarTrades.filter((t) => t.close_date && t.profit_abs != null);
		if (closed.length < 8) return null;
		const byWeek = new Map<string, { sum: number; count: number; wins: number }>();
		for (const t of closed) {
			const d = new Date(t.close_date!);
			const jan4 = new Date(d.getFullYear(), 0, 4);
			const startOfWeek = new Date(jan4);
			startOfWeek.setDate(jan4.getDate() - ((jan4.getDay() + 6) % 7));
			const weekNum = Math.ceil(((d.getTime() - startOfWeek.getTime()) / 86400000 + 1) / 7);
			const key = `${d.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
			if (!byWeek.has(key)) byWeek.set(key, { sum: 0, count: 0, wins: 0 });
			const w = byWeek.get(key)!;
			w.sum += t.profit_abs!;
			w.count++;
			if (t.profit_abs! > 0) w.wins++;
		}
		const weeks = [...byWeek.entries()].sort((a, b) => a[0].localeCompare(b[0])).slice(-40);
		if (weeks.length < 3) return null;
		const vals = weeks.map((w) => w[1].sum);
		const maxAbs = Math.max(0.01, ...vals.map(Math.abs));
		const W = 560,
			H = 80;
		const barW = Math.max(2, W / weeks.length - 1);
		const bars = weeks.map(([week, v], i) => ({
			x: i * (W / weeks.length),
			h: (Math.abs(v.sum) / maxAbs) * (H / 2 - 2),
			positive: v.sum >= 0,
			week,
			sum: v.sum,
			count: v.count
		}));
		const winWeeks = vals.filter((v) => v > 0).length;
		const total = vals.reduce((a, b) => a + b, 0);
		return { bars, W, H, barW, maxAbs, winWeeks, total, weeks: weeks.length };
	});

	// Sharpe vs Calmar run scatter (per-strategy)
	const runRiskScatter = $derived.by(() => {
		const valid = runs.filter(
			(r) => r.sharpe != null && r.calmar != null && r.total_profit_pct != null
		);
		if (valid.length < 4) return null;
		const W = 320,
			H = 160,
			PL = 28,
			PB = 20,
			PT = 8,
			PR = 8;
		const sharpes = valid.map((r) => r.sharpe!);
		const calmars = valid.map((r) => r.calmar!);
		const profits = valid.map((r) => r.total_profit_pct!);
		const xMin = Math.min(...sharpes),
			xMax = Math.max(...sharpes, xMin + 0.01);
		const yMin = Math.min(...calmars),
			yMax = Math.max(...calmars, yMin + 0.01);
		const pMin = Math.min(...profits),
			pMax = Math.max(...profits, pMin + 0.01);
		const toX = (v: number) => PL + ((v - xMin) / (xMax - xMin)) * (W - PL - PR);
		const toY = (v: number) => PT + (1 - (v - yMin) / (yMax - yMin)) * (H - PT - PB);
		const colorFor = (p: number) => {
			const t = (p - pMin) / (pMax - pMin);
			if (t > 0.66) return '#34d399';
			if (t > 0.33) return '#fbbf24';
			return '#f87171';
		};
		const dots = valid.map((r) => ({
			cx: toX(r.sharpe!),
			cy: toY(r.calmar!),
			color: colorFor(r.total_profit_pct!),
			tip: `Run #${r.id} · Sharpe ${r.sharpe!.toFixed(2)} · Calmar ${r.calmar!.toFixed(2)} · ${r.total_profit_pct! >= 0 ? '+' : ''}${r.total_profit_pct!.toFixed(1)}%`,
			isBest: r.id === runs[0]?.id
		}));
		return { dots, W, H, PL, PB, PT, PR, xMin, xMax, yMin, yMax };
	});

	// Monthly return heatmap: cumulative profit% per calendar month
	const monthlyReturnHeatmap = $derived.by(() => {
		const trades = calendarTrades.filter((t) => t.close_date && t.profit_pct != null);
		if (trades.length < 6) return null;
		const map = new Map<string, { sum: number; count: number; wins: number }>();
		for (const t of trades) {
			const key = t.close_date!.slice(0, 7); // YYYY-MM
			if (!map.has(key)) map.set(key, { sum: 0, count: 0, wins: 0 });
			const e = map.get(key)!;
			e.sum += t.profit_pct!;
			e.count++;
			if (t.profit_pct! > 0) e.wins++;
		}
		const months = [...map.keys()].sort();
		if (months.length < 2) return null;
		const years = [...new Set(months.map((m) => m.slice(0, 4)))].sort();
		const MONTH_LABELS = [
			'Jan',
			'Feb',
			'Mar',
			'Apr',
			'May',
			'Jun',
			'Jul',
			'Aug',
			'Sep',
			'Oct',
			'Nov',
			'Dec'
		];
		const maxAbs = Math.max(0.001, ...months.map((m) => Math.abs(map.get(m)!.sum)));
		const grid = years.map((year) => ({
			year,
			cells: Array.from({ length: 12 }, (_, mi) => {
				const key = `${year}-${String(mi + 1).padStart(2, '0')}`;
				const v = map.get(key);
				return v
					? {
							sum: v.sum,
							count: v.count,
							wr: v.wins / v.count,
							intensity: Math.abs(v.sum) / maxAbs
						}
					: null;
			})
		}));
		return { grid, years, MONTH_LABELS, maxAbs };
	});

	// Monte Carlo simulation — bootstrapped equity curve bands
	const N_SIMS = 300;
	// Pair profit ranking: top pairs by cumulative profit_pct from calendarTrades
	const pairProfitRanking = $derived.by(() => {
		const trades = calendarTrades.filter((t) => t.pair && t.profit_pct != null);
		if (trades.length < 8) return null;
		const map = new Map<string, { sum: number; count: number; wins: number }>();
		for (const t of trades) {
			if (!map.has(t.pair)) map.set(t.pair, { sum: 0, count: 0, wins: 0 });
			const e = map.get(t.pair)!;
			e.sum += t.profit_pct!;
			e.count++;
			if (t.profit_pct! > 0) e.wins++;
		}
		const rows = [...map.entries()]
			.map(([pair, v]) => ({ pair, sum: v.sum, count: v.count, wr: v.wins / v.count }))
			.sort((a, b) => b.sum - a.sum)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.sum)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.sum) / maxAbs) * 100 }));
	});

	// Trade duration vs profit scatter: do longer holds yield better returns?
	const tradeDurationVsProfit = $derived.by(() => {
		const pts = calendarTrades.filter(
			(t) => t.trade_duration_min != null && t.trade_duration_min > 0 && t.profit_pct != null
		);
		if (pts.length < 8) return null;
		const xs = pts.map((t) => t.trade_duration_min!);
		const ys = pts.map((t) => t.profit_pct!);
		const xMax = Math.min(Math.max(...xs), 10000);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, 0.001);
		const W = 520,
			H = 110,
			PAD = 20;
		const toX = (v: number) => PAD + (Math.min(v, xMax) / xMax) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin || 0.001)) * (H - PAD * 2);
		const zeroY = toY(0);
		const n = xs.length;
		const cxs = xs.map((x) => Math.min(x, xMax));
		const mx = cxs.reduce((a, b) => a + b, 0) / n,
			my = ys.reduce((a, b) => a + b, 0) / n;
		const num = cxs.reduce((s, x, i) => s + (x - mx) * (ys[i] - my), 0);
		const den = Math.sqrt(
			cxs.reduce((s, x) => s + (x - mx) ** 2, 0) * ys.reduce((s, y) => s + (y - my) ** 2, 0)
		);
		const corr = den === 0 ? 0 : num / den;
		const dots = pts.map((t) => ({
			x: toX(t.trade_duration_min!),
			y: toY(t.profit_pct!),
			min: t.trade_duration_min!,
			profit: t.profit_pct!
		}));
		return { dots, W, H, PAD, zeroY, xMax, corr };
	});

	// Run import timeline: backtest activity over last 12 weeks for this strategy
	const runImportTimeline = $derived.by(() => {
		if (runs.length < 2) return null;
		const now = Date.now();
		const MS_WEEK = 7 * 24 * 3600 * 1000;
		const weeks = Array.from({ length: 12 }, (_, i) => {
			const wEnd = now - i * MS_WEEK;
			const wStart = wEnd - MS_WEEK;
			const label = new Date(wStart).toLocaleDateString('en', { month: 'short', day: 'numeric' });
			return { label, start: wStart, end: wEnd, count: 0 };
		}).reverse();
		for (const r of runs) {
			const ts = new Date(r.imported_at).getTime();
			const w = weeks.find((w) => ts >= w.start && ts < w.end);
			if (w) w.count++;
		}
		if (weeks.every((w) => w.count === 0)) return null;
		const maxCount = Math.max(1, ...weeks.map((w) => w.count));
		return { weeks, maxCount, total: runs.length };
	});

	// Monthly avg trade profit%: 12-month bar chart (distinct from weeklyPnlBars cumulative and monthlyReturnHeatmap grid)
	// Per-pair win rate: distinct from pairProfitRanking (cumulative profit sum)
	// Win rate per entry tag: distinct from enterTagStats (count) and enterTagProfitShare (profit%)
	const enterTagWinRate = $derived.by(() => {
		const trades = calendarTrades.filter((t) => t.enter_tag && t.profit_pct != null);
		if (trades.length < 10) return null;
		const map = new Map<string, { wins: number; total: number }>();
		for (const t of trades) {
			const tag = t.enter_tag!;
			if (!map.has(tag)) map.set(tag, { wins: 0, total: 0 });
			const e = map.get(tag)!;
			e.total++;
			if (t.profit_pct! > 0) e.wins++;
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.total >= 3)
			.map(([tag, v]) => ({ tag, wr: v.wins / v.total, count: v.total, wins: v.wins }))
			.sort((a, b) => b.wr - a.wr)
			.slice(0, 12);
		if (rows.length < 2) return null;
		return rows;
	});

	const pairWinRate = $derived.by(() => {
		const trades = calendarTrades.filter((t) => t.pair && t.profit_pct != null);
		if (trades.length < 10) return null;
		const map = new Map<string, { wins: number; total: number }>();
		for (const t of trades) {
			if (!map.has(t.pair)) map.set(t.pair, { wins: 0, total: 0 });
			const e = map.get(t.pair)!;
			e.total++;
			if (t.profit_pct! > 0) e.wins++;
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.total >= 3)
			.map(([pair, v]) => ({ pair, wr: v.wins / v.total, count: v.total, wins: v.wins }))
			.sort((a, b) => b.wr - a.wr)
			.slice(0, 14);
		if (rows.length < 3) return null;
		return rows;
	});

	const avgProfitByMonth = $derived.by(() => {
		const closed = calendarTrades.filter((t) => t.close_date && t.profit_pct != null);
		if (closed.length < 10) return null;
		const now = new Date();
		const months = Array.from({ length: 12 }, (_, i) => {
			const d = new Date(now.getFullYear(), now.getMonth() - 11 + i, 1);
			const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
			return {
				key,
				label: d.toLocaleDateString('en', { month: 'short', year: '2-digit' }),
				trades: [] as number[]
			};
		});
		for (const t of closed) {
			const key = t.close_date!.slice(0, 7);
			const m = months.find((x) => x.key === key);
			if (m) m.trades.push(t.profit_pct!);
		}
		const rows = months.map((m) => ({
			label: m.label,
			key: m.key,
			count: m.trades.length,
			avg: m.trades.length ? m.trades.reduce((a, b) => a + b, 0) / m.trades.length : null
		}));
		if (rows.filter((r) => r.count > 0).length < 2) return null;
		const maxAbs = Math.max(0.001, ...rows.map((r) => Math.abs(r.avg ?? 0)));
		return rows.map((r) => ({
			...r,
			barPct: r.avg != null ? (Math.abs(r.avg) / maxAbs) * 100 : 0
		}));
	});

	const monteCarloData = $derived.by(() => {
		if (calendarTrades.length < 10) return null;
		const returns = calendarTrades
			.filter((t) => t.profit_pct != null)
			.map((t) => 1 + t.profit_pct! / 100);
		if (returns.length < 5) return null;

		const sims: number[][] = [];
		for (let i = 0; i < N_SIMS; i++) {
			const shuffled = [...returns].sort(() => Math.random() - 0.5);
			const curve: number[] = [1];
			let eq = 1;
			for (const r of shuffled) {
				eq *= r;
				curve.push(eq);
			}
			sims.push(curve);
		}

		const steps = returns.length + 1;
		const p5: number[] = [],
			p50: number[] = [],
			p95: number[] = [];
		for (let t = 0; t < steps; t++) {
			const vals = sims.map((s) => s[t] ?? s[s.length - 1]).sort((a, b) => a - b);
			const n = vals.length;
			p5.push(vals[Math.floor(n * 0.05)]);
			p50.push(vals[Math.floor(n * 0.5)]);
			p95.push(vals[Math.floor(n * 0.95)]);
		}

		const observed: number[] = [1];
		let eq2 = 1;
		for (const r of returns) {
			eq2 *= r;
			observed.push(eq2);
		}

		const allVals = [...p5, ...p95, ...observed];
		const yMin = Math.min(...allVals) * 0.95;
		const yMax = Math.max(...allVals) * 1.05;

		const W = 560,
			H = 160;
		function toX(i: number) {
			return (i / (steps - 1)) * W;
		}
		function toY(v: number) {
			return H - ((v - yMin) / (yMax - yMin)) * H;
		}

		function polyline(arr: number[]) {
			return arr.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
		}
		function band(lo: number[], hi: number[]) {
			const top = hi.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
			const bot = [...lo]
				.reverse()
				.map((v, i) => `${toX(lo.length - 1 - i).toFixed(1)},${toY(v).toFixed(1)}`)
				.join(' ');
			return `${top} ${bot}`;
		}

		const finalObs = observed[observed.length - 1];
		const finalP50 = p50[p50.length - 1];
		return {
			bandPath: band(p5, p95),
			p50line: polyline(p50),
			obsline: polyline(observed),
			zeroY: toY(1).toFixed(1),
			W,
			H,
			steps,
			finalObs,
			finalP50,
			p5final: p5[p5.length - 1],
			p95final: p95[p95.length - 1]
		};
	});

	// Exit hour analysis: avg profit% per UTC close hour — which hours produce best exits?
	const exitHourAnalysis = $derived.by(() => {
		const trades = calendarTrades.filter((t) => t.close_date && t.profit_pct != null);
		if (trades.length < 20) return null;
		const hours = Array.from({ length: 24 }, (_, h) => ({ h, sum: 0, count: 0, wins: 0 }));
		for (const t of trades) {
			const h = new Date(t.close_date!).getUTCHours();
			hours[h].sum += t.profit_pct!;
			hours[h].count++;
			if (t.profit_pct! > 0) hours[h].wins++;
		}
		const active = hours.filter((h) => h.count > 0);
		if (active.length < 4) return null;
		const rows = hours.map((h) => ({
			h: h.h,
			label: String(h.h).padStart(2, '0'),
			count: h.count,
			avg: h.count > 0 ? h.sum / h.count : null,
			wr: h.count > 0 ? h.wins / h.count : null
		}));
		const maxAbs = Math.max(0.001, ...rows.map((r) => Math.abs(r.avg ?? 0)));
		return rows.map((r) => ({
			...r,
			barPct: r.avg != null ? (Math.abs(r.avg) / maxAbs) * 100 : 0
		}));
	});

	const runCalmarTimeline = $derived.by(() => {
		const sorted = runs
			.filter(
				(r) =>
					r.imported_at && r.calmar != null && isFinite(r.calmar) && r.calmar > -20 && r.calmar < 50
			)
			.sort((a, b) => a.imported_at.localeCompare(b.imported_at))
			.slice(-40);
		if (sorted.length < 5) return null;
		const vals = sorted.map((r) => r.calmar!);
		const W = 560,
			H = 72,
			PAD = 8;
		const mn = Math.min(...vals),
			mx = Math.max(...vals, mn + 0.1);
		const toX = (i: number) => PAD + (i / (sorted.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / (mx - mn)) * (H - PAD * 2);
		const zeroY = mn < 0 ? toY(0) : H - PAD;
		const polyline = sorted
			.map((r, i) => `${toX(i).toFixed(1)},${toY(r.calmar!).toFixed(1)}`)
			.join(' ');
		const trend = vals[vals.length - 1] - vals[0];
		return { polyline, W, H, PAD, zeroY, mn, mx, trend, count: sorted.length };
	});

	const tradeMonthlyVolume = $derived.by(() => {
		const trades = calendarTrades.filter((t) => t.close_date);
		if (trades.length < 10) return null;
		const map = new Map<string, number>();
		for (const t of trades) {
			const ym = t.close_date!.slice(0, 7);
			map.set(ym, (map.get(ym) ?? 0) + 1);
		}
		const rows = [...map.entries()]
			.sort((a, b) => a[0].localeCompare(b[0]))
			.map(([ym, count]) => ({ ym, label: ym.slice(2), count }));
		if (rows.length < 2) return null;
		const maxCount = Math.max(1, ...rows.map((r) => r.count));
		return rows.map((r) => ({ ...r, barPct: (r.count / maxCount) * 100 }));
	});

	// Pair holding time ranking: avg, min, max hold duration per pair (distinct from pairProfitRanking, pairWinRate, pairWorstTrade)
	const pairHoldingTimeRanking = $derived.by(() => {
		const trades = calendarTrades.filter(
			(t) => t.pair && t.trade_duration_min != null && t.trade_duration_min > 0
		);
		if (trades.length < 10) return null;
		const map = new Map<string, number[]>();
		for (const t of trades) {
			if (!map.has(t.pair)) map.set(t.pair, []);
			map.get(t.pair)!.push(t.trade_duration_min!);
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 3)
			.map(([pair, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
				return { pair, avg, min: sorted[0], max: sorted[sorted.length - 1], count: vals.length };
			})
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxAvg = Math.max(1, ...rows.map((r) => r.avg));
		const fmtH = (m: number) => (m >= 60 ? `${(m / 60).toFixed(1)}h` : `${Math.round(m)}m`);
		return rows.map((r) => ({
			...r,
			barPct: (r.avg / maxAvg) * 100,
			avgLabel: fmtH(r.avg),
			maxLabel: fmtH(r.max)
		}));
	});

	// Exit reason profit profile: avg profit% and win rate per exit reason (distinct from enterTagStats by tag, exitHourAnalysis by hour)
	const exitReasonProfitProfile = $derived.by(() => {
		const trades = calendarTrades.filter((t) => t.exit_reason && t.profit_pct != null);
		if (trades.length < 10) return null;
		const map = new Map<string, { sum: number; count: number; wins: number }>();
		for (const t of trades) {
			const r = t.exit_reason!;
			if (!map.has(r)) map.set(r, { sum: 0, count: 0, wins: 0 });
			const e = map.get(r)!;
			e.sum += t.profit_pct!;
			e.count++;
			if (t.profit_pct! > 0) e.wins++;
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.count >= 2)
			.map(([reason, v]) => ({
				reason,
				avg: v.sum / v.count,
				count: v.count,
				wr: v.wins / v.count
			}))
			.sort((a, b) => b.avg - a.avg);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.avg)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.avg) / maxAbs) * 100 }));
	});

	const pairWorstTrade = $derived.by(() => {
		const trades = calendarTrades.filter((t) => t.pair && t.profit_pct != null);
		if (trades.length < 10) return null;
		const map = new Map<string, { worst: number; count: number; wins: number }>();
		for (const t of trades) {
			if (!map.has(t.pair!)) map.set(t.pair!, { worst: 0, count: 0, wins: 0 });
			const e = map.get(t.pair!)!;
			e.count++;
			if (t.profit_pct! < e.worst) e.worst = t.profit_pct!;
			if (t.profit_pct! > 0) e.wins++;
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.count >= 3)
			.map(([pair, v]) => ({ pair, worst: v.worst, count: v.count, wr: v.wins / v.count }))
			.sort((a, b) => a.worst - b.worst)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.worst)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.worst) / maxAbs) * 100 }));
	});

	const stakeAmountProfile = $derived.by(() => {
		const trades = calendarTrades.filter(
			(t) => t.stake_amount != null && t.profit_pct != null && isFinite(t.profit_pct)
		);
		if (trades.length < 15) return null;
		const stakes = trades.map((t) => t.stake_amount!);
		const minS = Math.min(...stakes),
			maxS = Math.max(...stakes);
		if (maxS - minS < 0.01) return null;
		const step = (maxS - minS) / 6;
		const buckets = Array.from({ length: 6 }, (_, i) => ({
			label: `${(minS + i * step).toFixed(0)}–${(minS + (i + 1) * step).toFixed(0)}`,
			sum: 0,
			count: 0,
			wins: 0
		}));
		for (const t of trades) {
			const idx = Math.min(5, Math.floor((t.stake_amount! - minS) / step));
			buckets[idx].sum += t.profit_pct!;
			buckets[idx].count++;
			if (t.profit_pct! > 0) buckets[idx].wins++;
		}
		const rows = buckets
			.filter((b) => b.count > 0)
			.map((b) => ({ ...b, avg: b.sum / b.count, wr: b.wins / b.count }));
		if (rows.length < 2) return null;
		const maxAbsAvg = Math.max(0.01, ...rows.map((r) => Math.abs(r.avg)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.avg) / maxAbsAvg) * 100 }));
	});

	const enterTagProfitProfile = $derived.by(() => {
		const trades = calendarTrades.filter(
			(t) => t.enter_tag && t.profit_pct != null && isFinite(t.profit_pct)
		);
		if (trades.length < 10) return null;
		const map = new Map<string, { sum: number; count: number; wins: number }>();
		for (const t of trades) {
			const tag = t.enter_tag!;
			if (!map.has(tag)) map.set(tag, { sum: 0, count: 0, wins: 0 });
			const e = map.get(tag)!;
			e.sum += t.profit_pct!;
			e.count++;
			if (t.profit_pct! > 0) e.wins++;
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.count >= 3)
			.map(([tag, v]) => ({ tag, avg: v.sum / v.count, wr: v.wins / v.count, count: v.count }))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 10);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.avg)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.avg) / maxAbs) * 100 }));
	});

	const pairProfitTrend = $derived.by(() => {
		const sorted = [...calendarTrades]
			.filter((t) => t.pair && t.profit_pct != null && t.close_date)
			.sort((a, b) => new Date(a.close_date!).getTime() - new Date(b.close_date!).getTime());
		if (sorted.length < 20) return null;
		const map = new Map<string, number[]>();
		for (const t of sorted) {
			if (!map.has(t.pair!)) map.set(t.pair!, []);
			map.get(t.pair!)!.push(t.profit_pct!);
		}
		const rows = [...map.entries()]
			.filter(([, pts]) => pts.length >= 6)
			.map(([pair, pts]) => {
				const mid = Math.floor(pts.length / 2);
				const early = pts.slice(0, mid).reduce((a, b) => a + b, 0) / mid;
				const late = pts.slice(mid).reduce((a, b) => a + b, 0) / (pts.length - mid);
				return { pair, early, late, delta: late - early, count: pts.length };
			})
			.sort((a, b) => b.delta - a.delta)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.delta)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.delta) / maxAbs) * 100 }));
	});

	const pairTradeCountVsProfit = $derived.by(() => {
		const map = new Map<string, { sum: number; count: number }>();
		for (const t of calendarTrades) {
			if (!t.pair || t.profit_pct == null || !isFinite(t.profit_pct)) continue;
			if (!map.has(t.pair)) map.set(t.pair, { sum: 0, count: 0 });
			const e = map.get(t.pair)!;
			e.sum += t.profit_pct;
			e.count++;
		}
		const pts = [...map.entries()]
			.filter(([, v]) => v.count >= 2)
			.map(([pair, v]) => ({ pair, avg: v.sum / v.count, count: v.count }));
		if (pts.length < 5) return null;
		const W = 360,
			H = 80,
			PAD = 8;
		const xs = pts.map((p) => p.count),
			ys = pts.map((p) => p.avg);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 1);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.01);
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const dots = pts.map((p) => ({
			cx: toX(p.count),
			cy: toY(p.avg),
			pos: p.avg > 0,
			pair: p.pair
		}));
		return { dots, W, H, PAD, xMin, xMax, yMin, yMax };
	});

	const tradeProfitByHour = $derived.by(() => {
		const buckets = Array.from({ length: 24 }, (_, h) => ({ h, sum: 0, count: 0 }));
		for (const t of calendarTrades) {
			if (!t.close_date || t.profit_pct == null || !isFinite(t.profit_pct)) continue;
			const h = new Date(t.close_date).getUTCHours();
			buckets[h].sum += t.profit_pct;
			buckets[h].count++;
		}
		const filled = buckets.filter((b) => b.count >= 2);
		if (filled.length < 4) return null;
		const rows = buckets.map((b) => ({ ...b, avg: b.count >= 2 ? b.sum / b.count : null }));
		const maxAbs = Math.max(
			0.01,
			...rows.filter((r) => r.avg != null).map((r) => Math.abs(r.avg!))
		);
		return rows.map((r) => ({
			...r,
			barPct: r.avg != null ? (Math.abs(r.avg) / maxAbs) * 100 : 0
		}));
	});

	const tradeProfitByDayOfWeek = $derived.by(() => {
		const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
		const buckets = DAYS.map((day) => ({ day, sum: 0, count: 0 }));
		for (const t of calendarTrades) {
			if (!t.close_date || t.profit_pct == null || !isFinite(t.profit_pct)) continue;
			const dow = new Date(t.close_date).getDay();
			buckets[dow].sum += t.profit_pct;
			buckets[dow].count++;
		}
		const filled = buckets.filter((b) => b.count >= 2);
		if (filled.length < 3) return null;
		const rows = buckets.map((b) => ({ ...b, avg: b.count > 0 ? b.sum / b.count : null }));
		const maxAbs = Math.max(
			0.01,
			...rows.filter((r) => r.avg != null).map((r) => Math.abs(r.avg!))
		);
		return rows.map((r) => ({
			...r,
			barPct: r.avg != null ? (Math.abs(r.avg) / maxAbs) * 100 : 0
		}));
	});

	const tradeStreakAnalysis = $derived.by(() => {
		const sorted = [...calendarTrades]
			.filter((t) => t.profit_pct != null && t.close_date)
			.sort((a, b) => new Date(a.close_date!).getTime() - new Date(b.close_date!).getTime());
		if (sorted.length < 10) return null;
		let maxWin = 0,
			maxLoss = 0,
			curWin = 0,
			curLoss = 0;
		for (const t of sorted) {
			if (t.profit_pct! > 0) {
				curWin++;
				curLoss = 0;
				maxWin = Math.max(maxWin, curWin);
			} else {
				curLoss++;
				curWin = 0;
				maxLoss = Math.max(maxLoss, curLoss);
			}
		}
		const last = sorted[sorted.length - 1];
		const currentIsWin = (last.profit_pct ?? 0) > 0;
		const currentStreak = currentIsWin ? curWin : -curLoss;
		return { maxWin, maxLoss, currentStreak, currentIsWin, total: sorted.length };
	});

	const tradeMonthlyWinRate = $derived.by(() => {
		const map = new Map<string, { wins: number; total: number }>();
		for (const t of calendarTrades) {
			if (!t.close_date || t.profit_pct == null || !isFinite(t.profit_pct)) continue;
			const ym = new Date(t.close_date).toISOString().slice(0, 7);
			if (!map.has(ym)) map.set(ym, { wins: 0, total: 0 });
			const e = map.get(ym)!;
			e.total++;
			if (t.profit_pct > 0) e.wins++;
		}
		if (map.size < 3) return null;
		const rows = [...map.entries()]
			.map(([ym, v]) => ({ ym, wr: v.wins / v.total, total: v.total }))
			.sort((a, b) => a.ym.localeCompare(b.ym));
		const W = 400,
			H = 60,
			PAD = 6;
		const toX = (i: number) => PAD + (i / Math.max(1, rows.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - (v / 1) * (H - PAD * 2);
		const poly = rows.map((r, i) => `${toX(i).toFixed(1)},${toY(r.wr).toFixed(1)}`).join(' ');
		const zeroY = toY(0.5);
		const avgWr = rows.reduce((s, r) => s + r.wr, 0) / rows.length;
		return { rows, poly, W, H, PAD, zeroY, avgWr };
	});

	const tradePairWinRate = $derived.by(() => {
		const map = new Map<string, { wins: number; total: number; sumProfit: number }>();
		for (const t of calendarTrades) {
			if (!t.pair || t.profit_pct == null || !isFinite(t.profit_pct)) continue;
			if (!map.has(t.pair)) map.set(t.pair, { wins: 0, total: 0, sumProfit: 0 });
			const e = map.get(t.pair)!;
			e.total++;
			e.sumProfit += t.profit_pct;
			if (t.profit_pct > 0) e.wins++;
		}
		const rows = [...map.entries()]
			.filter(([, v]) => v.total >= 3)
			.map(([pair, v]) => ({
				pair,
				wr: v.wins / v.total,
				total: v.total,
				avgProfit: v.sumProfit / v.total
			}))
			.sort((a, b) => b.wr - a.wr)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxWr = Math.max(1, ...rows.map((r) => r.wr));
		return rows.map((r) => ({ ...r, barPct: (r.wr / maxWr) * 100 }));
	});

	const tradeProfitCumulativeTimeline = $derived.by(() => {
		const sorted = [...calendarTrades]
			.filter((t) => t.close_date && t.profit_pct != null && isFinite(t.profit_pct))
			.sort((a, b) => new Date(a.close_date!).getTime() - new Date(b.close_date!).getTime());
		if (sorted.length < 5) return null;
		let cum = 0;
		const pts = sorted.map((t) => {
			cum += t.profit_pct!;
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
		const zeroY = toY(0);
		const final = pts[pts.length - 1];
		const first = sorted[0].close_date!.slice(0, 7),
			last = sorted[sorted.length - 1].close_date!.slice(0, 7);
		return {
			poly,
			W,
			H,
			PAD,
			zeroY,
			mn,
			final,
			positive: final > 0,
			first,
			last,
			total: sorted.length
		};
	});

	const tradeHoldingBucketWinRate = $derived.by(() => {
		const trades = calendarTrades.filter(
			(t) => t.trade_duration_min != null && t.profit_pct != null && isFinite(t.profit_pct)
		);
		if (trades.length < 15) return null;
		const durations = trades.map((t) => t.trade_duration_min!);
		const minD = Math.min(...durations),
			maxD = Math.max(...durations);
		if (maxD - minD < 1) return null;
		const BINS = 6;
		const step = (maxD - minD) / BINS;
		const buckets = Array.from({ length: BINS }, (_, i) => {
			const lo = minD + i * step,
				hi = minD + (i + 1) * step;
			const label =
				lo < 60
					? `${lo.toFixed(0)}–${hi.toFixed(0)}m`
					: `${(lo / 60).toFixed(0)}–${(hi / 60).toFixed(0)}h`;
			return { label, wins: 0, total: 0, sumProfit: 0 };
		});
		for (const t of trades) {
			const idx = Math.min(BINS - 1, Math.floor((t.trade_duration_min! - minD) / step));
			buckets[idx].total++;
			buckets[idx].sumProfit += t.profit_pct!;
			if (t.profit_pct! > 0) buckets[idx].wins++;
		}
		const rows = buckets
			.filter((b) => b.total >= 3)
			.map((b) => ({ ...b, wr: b.wins / b.total, avg: b.sumProfit / b.total }));
		if (rows.length < 2) return null;
		return rows;
	});

	const tradeEnterTagHourHeatmap = $derived.by(() => {
		const tags = [...new Set(calendarTrades.map((t) => t.enter_tag).filter(Boolean))] as string[];
		if (tags.length < 2) return null;
		const map = new Map<string, { wins: number; total: number }[]>();
		for (const tag of tags)
			map.set(
				tag,
				Array.from({ length: 24 }, () => ({ wins: 0, total: 0 }))
			);
		for (const t of calendarTrades) {
			if (!t.enter_tag || !t.open_date || t.profit_pct == null || !isFinite(t.profit_pct)) continue;
			const hour = new Date(t.open_date).getHours();
			const e = map.get(t.enter_tag)?.[hour];
			if (!e) continue;
			e.total++;
			if (t.profit_pct > 0) e.wins++;
		}
		const validTags = tags
			.filter((tag) => map.get(tag)!.reduce((s, e) => s + e.total, 0) >= 8)
			.slice(0, 6);
		if (validTags.length < 2) return null;
		const HOURS = Array.from({ length: 24 }, (_, i) => i);
		const cells = validTags.map((tag) => ({
			tag,
			hours: HOURS.map((h) => {
				const e = map.get(tag)![h];
				return { h, wr: e.total >= 2 ? e.wins / e.total : null, total: e.total };
			})
		}));
		return { cells, hours: HOURS };
	});

	const runTimeframeComparisonTable = $derived.by(() => {
		const map = new Map<
			string,
			{ profits: number[]; wins: number; total: number; calmars: number[] }
		>();
		for (const r of runs) {
			if (!r.timeframe) continue;
			if (!map.has(r.timeframe))
				map.set(r.timeframe, { profits: [], wins: 0, total: 0, calmars: [] });
			const e = map.get(r.timeframe)!;
			if (r.total_profit_pct != null && isFinite(r.total_profit_pct)) {
				e.profits.push(r.total_profit_pct);
				e.total++;
				if (r.total_profit_pct > 0) e.wins++;
			}
			if (r.calmar != null && isFinite(r.calmar) && r.calmar > -10 && r.calmar < 100)
				e.calmars.push(r.calmar);
		}
		const TF_ORDER = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d'];
		const rows = [...map.entries()]
			.filter(([, v]) => v.total >= 2)
			.map(([tf, v]) => ({
				tf,
				avg: v.profits.length ? v.profits.reduce((s, x) => s + x, 0) / v.profits.length : null,
				wr: v.total > 0 ? v.wins / v.total : null,
				calmar: v.calmars.length ? v.calmars.reduce((s, x) => s + x, 0) / v.calmars.length : null,
				count: v.total
			}))
			.sort((a, b) => {
				const ai = TF_ORDER.indexOf(a.tf),
					bi = TF_ORDER.indexOf(b.tf);
				return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
			});
		if (rows.length < 2) return null;
		return rows;
	});

	// Profit_factor timeline across runs ordered by import date
	const runProfitFactorTimeline = $derived.by(() => {
		const pts = runs
			.filter(
				(r) =>
					r.profit_factor != null &&
					isFinite(r.profit_factor) &&
					r.profit_factor > 0 &&
					r.profit_factor < 50 &&
					r.imported_at
			)
			.sort((a, b) => a.imported_at.localeCompare(b.imported_at))
			.map((r) => ({ pf: r.profit_factor!, date: r.imported_at.slice(0, 10) }));
		if (pts.length < 5) return null;
		const vals = pts.map((p) => p.pf);
		const vMin = Math.min(...vals),
			vMax = Math.max(...vals);
		const W = 440,
			H = 70,
			PAD = 8;
		const toX = (i: number) => PAD + (i / Math.max(1, pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - vMin) / (vMax - vMin || 0.001)) * (H - PAD * 2);
		const poly = pts.map((p, i) => `${toX(i).toFixed(1)},${toY(p.pf).toFixed(1)}`).join(' ');
		const y1 = toY(1);
		const avg = vals.reduce((s, x) => s + x, 0) / vals.length;
		return {
			pts,
			poly,
			W,
			H,
			PAD,
			y1,
			avg,
			vMin,
			vMax,
			first: pts[0].date,
			last: pts[pts.length - 1].date
		};
	});

	// Monthly exit reason breakdown across closed trades
	const tradeExitReasonTimeline = $derived.by(() => {
		const evts = trades.filter((t) => t.exit_reason && t.close_date);
		if (evts.length < 10) return null;
		const monthSet = new Set<string>();
		for (const t of evts) monthSet.add(t.close_date!.slice(0, 7));
		const months = [...monthSet].sort().slice(-12);
		if (months.length < 3) return null;
		const reasons = [...new Set(evts.map((t) => t.exit_reason!))].slice(0, 5);
		const COLORS = [
			'var(--ch-violet-strong)',
			'var(--ch-profit-strong)',
			'var(--ch-warn)',
			'var(--ch-loss)',
			'var(--ch-violet-light)'
		];
		const grid = new Map<string, Map<string, number>>();
		for (const m of months) grid.set(m, new Map(reasons.map((r) => [r, 0])));
		for (const t of evts) {
			const m = t.close_date!.slice(0, 7);
			if (!grid.has(m) || !t.exit_reason || !grid.get(m)!.has(t.exit_reason)) continue;
			grid.get(m)!.set(t.exit_reason, (grid.get(m)!.get(t.exit_reason) ?? 0) + 1);
		}
		const monthTotals = months.map((m) => [...grid.get(m)!.values()].reduce((s, x) => s + x, 0));
		const maxTotal = Math.max(1, ...monthTotals);
		return { months, reasons, COLORS, grid, maxTotal };
	});

	const runDrawdownTimeline = $derived.by(() => {
		const valid = data.runs
			.filter(
				(r) =>
					r.max_drawdown_pct != null &&
					isFinite(r.max_drawdown_pct) &&
					r.max_drawdown_pct >= 0 &&
					r.imported_at
			)
			.sort((a, b) => a.imported_at.localeCompare(b.imported_at));
		if (valid.length < 4) return null;
		const vals = valid.map((r) => r.max_drawdown_pct!);
		const maxDd = Math.max(0.01, ...vals);
		const W = 560,
			H = 72,
			PAD = 8;
		const toX = (i: number) => PAD + (i / Math.max(1, vals.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (v / maxDd) * (H - PAD * 2);
		const polyline = valid
			.map((r, i) => `${toX(i).toFixed(1)},${toY(r.max_drawdown_pct!).toFixed(1)}`)
			.join(' ');
		const dots = valid.map((r, i) => ({
			cx: toX(i),
			cy: toY(r.max_drawdown_pct!),
			date: r.imported_at.slice(0, 10),
			dd: r.max_drawdown_pct!,
			tf: r.timeframe
		}));
		const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
		const avgY = toY(avg);
		const trend = vals[vals.length - 1] - vals[0];
		return { W, H, polyline, dots, avg, avgY, trend, maxDd };
	});

	const runSharpeTimeline = $derived.by(() => {
		const valid = data.runs
			.filter((r) => r.sharpe != null && isFinite(r.sharpe) && r.imported_at)
			.sort((a, b) => a.imported_at.localeCompare(b.imported_at));
		if (valid.length < 4) return null;
		const vals = valid.map((r) => r.sharpe!);
		const mn = Math.min(...vals),
			mx = Math.max(...vals, mn + 0.01);
		const W = 560,
			H = 72,
			PAD = 8;
		const toX = (i: number) => PAD + (i / Math.max(1, vals.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / (mx - mn)) * (H - PAD * 2);
		const zeroY = mn < 0 && mx > 0 ? toY(0) : mn >= 0 ? H - PAD : PAD;
		const polyline = valid
			.map((r, i) => `${toX(i).toFixed(1)},${toY(r.sharpe!).toFixed(1)}`)
			.join(' ');
		const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
		const avgY = toY(avg);
		const trend = vals[vals.length - 1] - vals[0];
		const latest = vals[vals.length - 1];
		return { W, H, polyline, zeroY, avg, avgY, trend, latest, count: vals.length };
	});

	const runProfitFactorByTimeframe = $derived.by(() => {
		const grouped: Record<string, number[]> = {};
		for (const r of data.runs) {
			if (
				r.profit_factor != null &&
				isFinite(r.profit_factor) &&
				r.profit_factor > 0 &&
				r.profit_factor < 50 &&
				r.timeframe
			) {
				if (!grouped[r.timeframe]) grouped[r.timeframe] = [];
				grouped[r.timeframe].push(r.profit_factor);
			}
		}
		const entries = Object.entries(grouped).filter(([, v]) => v.length >= 2);
		if (entries.length < 2) return null;
		const rows = entries
			.map(([tf, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const median = sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
				const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
				return { tf, median, avg, count: vals.length };
			})
			.sort((a, b) => b.median - a.median);
		const maxVal = Math.max(...rows.map((r) => r.median), 1);
		return { rows, maxVal };
	});

	const runWinRateByTimeframe = $derived.by(() => {
		const grouped: Record<string, number[]> = {};
		for (const r of data.runs) {
			if (r.win_rate_pct == null || !isFinite(r.win_rate_pct) || !r.timeframe) continue;
			if (!grouped[r.timeframe]) grouped[r.timeframe] = [];
			grouped[r.timeframe].push(r.win_rate_pct);
		}
		const entries = Object.entries(grouped).filter(([, v]) => v.length >= 2);
		if (entries.length < 2) return null;
		const rows = entries
			.map(([tf, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const median = sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
				return { tf, median, count: vals.length, min: sorted[0], max: sorted[sorted.length - 1] };
			})
			.sort((a, b) => b.median - a.median);
		const maxVal = Math.max(...rows.map((r) => r.median), 1);
		return { rows, maxVal };
	});

	const runCalmarByTimeframe = $derived.by(() => {
		const grouped: Record<string, number[]> = {};
		for (const r of data.runs) {
			if (
				r.calmar == null ||
				!isFinite(r.calmar) ||
				r.calmar < -50 ||
				r.calmar > 200 ||
				!r.timeframe
			)
				continue;
			if (!grouped[r.timeframe]) grouped[r.timeframe] = [];
			grouped[r.timeframe].push(r.calmar);
		}
		const entries = Object.entries(grouped).filter(([, v]) => v.length >= 2);
		if (entries.length < 2) return null;
		const rows = entries
			.map(([tf, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const median = sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
				return { tf, median, count: vals.length };
			})
			.sort((a, b) => b.median - a.median);
		const absMax = Math.max(0.01, ...rows.map((r) => Math.abs(r.median)));
		return { rows, absMax };
	});

	const tradePairProfitDistribution = $derived.by(() => {
		const pairMap: Record<string, number[]> = {};
		for (const t of trades) {
			if (!t.pair || t.profit_pct == null || !isFinite(t.profit_pct)) continue;
			if (!pairMap[t.pair]) pairMap[t.pair] = [];
			pairMap[t.pair].push(t.profit_pct);
		}
		const topPairs = Object.entries(pairMap)
			.filter(([, v]) => v.length >= 5)
			.sort((a, b) => b[1].length - a[1].length)
			.slice(0, 5)
			.map(([pair, vals]) => {
				const mn = Math.min(...vals),
					mx = Math.max(...vals, mn + 0.01);
				const bucketCount = 12;
				const step = (mx - mn) / bucketCount;
				const buckets = Array.from({ length: bucketCount }, (_, i) => ({
					lo: mn + i * step,
					count: 0
				}));
				for (const v of vals) {
					const idx = Math.min(bucketCount - 1, Math.floor((v - mn) / step));
					buckets[idx].count++;
				}
				const maxCount = Math.max(...buckets.map((b) => b.count), 1);
				return { pair, buckets, maxCount, mn, mx, n: vals.length };
			});
		if (topPairs.length < 2) return null;
		return { pairs: topPairs };
	});

	const tradeAvgHoldingByMonth = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const t of trades) {
			if (!t.close_date || t.trade_duration_min == null || !isFinite(t.trade_duration_min))
				continue;
			const mo = t.close_date.slice(0, 7);
			if (!map[mo]) map[mo] = [];
			map[mo].push(t.trade_duration_min);
		}
		const rows = Object.entries(map)
			.map(([month, v]) => ({
				month,
				avg: v.reduce((a, b) => a + b, 0) / v.length,
				count: v.length
			}))
			.sort((a, b) => a.month.localeCompare(b.month));
		if (rows.length < 3) return null;
		const maxAvg = Math.max(...rows.map((r) => r.avg), 0.01);
		const W = 560,
			H = 80,
			PAD = 8;
		const barW = Math.max(2, (W - PAD * 2) / rows.length - 1);
		const globalAvg = rows.reduce((s, r) => s + r.avg, 0) / rows.length;
		const bars = rows.map((r, i) => {
			const x = PAD + i * ((W - PAD * 2) / rows.length);
			const h = Math.max(2, (r.avg / maxAvg) * (H - PAD * 2));
			const frac = r.avg / maxAvg;
			const color = `rgba(${Math.round(99 + frac * 140)},${Math.round(102 + frac * 60)},${Math.round(241 - frac * 150)},0.75)`;
			return { ...r, x, y: H - PAD - h, h, color };
		});
		const avgY = H - PAD - (globalAvg / maxAvg) * (H - PAD * 2);
		return { bars, barW, W, H, globalAvg, avgY, total: rows.length };
	});

	const tradeProfitByExitReason = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const t of trades) {
			if (!t.exit_reason || t.profit_pct == null || !isFinite(t.profit_pct)) continue;
			if (!map[t.exit_reason]) map[t.exit_reason] = [];
			map[t.exit_reason].push(t.profit_pct);
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.length >= 2)
			.map(([reason, vals]) => {
				const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
				return { reason, avg, count: vals.length };
			})
			.sort((a, b) => b.avg - a.avg);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		return { rows, maxAbs };
	});

	const tradeRunningPnlTimeline = $derived.by(() => {
		const sorted = [...trades]
			.filter((t) => t.close_date && t.profit_abs != null && isFinite(t.profit_abs))
			.sort((a, b) => a.close_date!.localeCompare(b.close_date!));
		if (sorted.length < 5) return null;
		let running = 0;
		const pts = sorted.map((t) => {
			running += t.profit_abs!;
			return running;
		});
		const mn = Math.min(...pts),
			mx = Math.max(...pts, mn + 0.01);
		const W = 560,
			H = 90,
			PAD = 8;
		const toX = (i: number) => PAD + (i / Math.max(1, pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / (mx - mn)) * (H - PAD * 2);
		const polyline = pts.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
		const zeroY = mn < 0 && mx > 0 ? toY(0) : null;
		const final = pts[pts.length - 1];
		const color = final >= 0 ? 'var(--ch-profit-strong)' : 'var(--ch-loss-strong)';
		return {
			W,
			H,
			polyline,
			zeroY,
			mn: mn.toFixed(2),
			mx: mx.toFixed(2),
			final: final.toFixed(2),
			count: pts.length,
			color
		};
	});

	const tradePairHoldingProfile = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const t of trades) {
			if (
				!t.pair ||
				t.trade_duration_min == null ||
				!isFinite(t.trade_duration_min) ||
				t.trade_duration_min <= 0
			)
				continue;
			if (!map[t.pair]) map[t.pair] = [];
			map[t.pair].push(t.trade_duration_min);
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.length >= 2)
			.map(([pair, vals]) => {
				const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
				const med = [...vals].sort((a, b) => a - b)[Math.floor(vals.length / 2)];
				return { pair, avg, med, count: vals.length };
			})
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxAvg = Math.max(...rows.map((r) => r.avg), 1);
		const toHrs = (m: number) =>
			m >= 1440
				? `${(m / 1440).toFixed(1)}d`
				: m >= 60
					? `${(m / 60).toFixed(1)}h`
					: `${m.toFixed(0)}m`;
		return { rows, maxAvg, toHrs };
	});

	const tradeExitReasonProfitProfile = $derived.by(() => {
		const map: Record<string, { profits: number[]; count: number }> = {};
		for (const t of trades) {
			if (!t.exit_reason || t.profit_pct == null || !isFinite(t.profit_pct)) continue;
			if (!map[t.exit_reason]) map[t.exit_reason] = { profits: [], count: 0 };
			map[t.exit_reason].profits.push(t.profit_pct);
			map[t.exit_reason].count++;
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.profits.length >= 1)
			.map(([reason, v]) => {
				const avg = v.profits.reduce((a, b) => a + b, 0) / v.profits.length;
				const wins = v.profits.filter((p) => p >= 0).length;
				const wr = (wins / v.profits.length) * 100;
				return { reason, avg, wr, count: v.profits.length };
			})
			.sort((a, b) => b.count - a.count)
			.slice(0, 12);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		return { rows, maxAbs };
	});

	const tradeEntryTagProfitSummary = $derived.by(() => {
		const map: Record<string, { profits: number[]; durations: number[] }> = {};
		for (const t of trades) {
			if (!t.enter_tag || t.profit_pct == null || !isFinite(t.profit_pct)) continue;
			if (!map[t.enter_tag]) map[t.enter_tag] = { profits: [], durations: [] };
			map[t.enter_tag].profits.push(t.profit_pct);
			if (t.trade_duration_min != null && isFinite(t.trade_duration_min))
				map[t.enter_tag].durations.push(t.trade_duration_min);
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.profits.length >= 2)
			.map(([tag, v]) => {
				const avg = v.profits.reduce((a, b) => a + b, 0) / v.profits.length;
				const winRate = (v.profits.filter((p) => p >= 0).length / v.profits.length) * 100;
				const avgDur =
					v.durations.length > 0
						? v.durations.reduce((a, b) => a + b, 0) / v.durations.length
						: null;
				return { tag, avg, winRate, count: v.profits.length, avgDur };
			})
			.sort((a, b) => b.avg - a.avg);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const toHrs = (m: number) =>
			m >= 1440
				? `${(m / 1440).toFixed(1)}d`
				: m >= 60
					? `${(m / 60).toFixed(1)}h`
					: `${m.toFixed(0)}m`;
		return { rows, maxAbs, toHrs };
	});

	const tradeProfitByMonth = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const t of trades) {
			if (t.close_date == null || t.profit_pct == null || !isFinite(t.profit_pct)) continue;
			const mo = t.close_date.slice(0, 7);
			if (!map[mo]) map[mo] = [];
			map[mo].push(t.profit_pct);
		}
		const months = Object.keys(map).sort().slice(-12);
		if (months.length < 3) return null;
		const rows = months.map((mo) => {
			const vals = map[mo];
			const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
			const wr = (vals.filter((p) => p >= 0).length / vals.length) * 100;
			return { mo: mo.slice(5), avg, wr, count: vals.length };
		});
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 480,
			H = 80,
			PAD = 8,
			barW = Math.max(4, Math.floor((W - PAD * 2) / rows.length) - 2);
		return { rows, maxAbs, W, H, PAD, barW };
	});

	const tradeStakeSizeDistribution = $derived.by(() => {
		const vals = trades
			.filter((t) => t.stake_amount != null && isFinite(t.stake_amount) && t.stake_amount > 0)
			.map((t) => t.stake_amount!);
		if (vals.length < 5) return null;
		const mn = Math.min(...vals),
			mx = Math.max(...vals);
		if (mx <= mn) return null;
		const BUCKETS = 10;
		const step = (mx - mn) / BUCKETS;
		const counts = Array.from({ length: BUCKETS }, (_, i) => {
			const lo = mn + i * step,
				hi = lo + step;
			return {
				lo,
				hi,
				count: vals.filter((v) => v >= lo && (i === BUCKETS - 1 ? v <= hi : v < hi)),
				label: (lo + step / 2).toFixed(0)
			};
		}).map((b) => ({ ...b, count: b.count.length }));
		const maxCount = Math.max(...counts.map((b) => b.count), 1);
		const W = 440,
			H = 70,
			PAD = 8,
			barW = Math.floor((W - PAD * 2) / BUCKETS) - 1;
		return { counts, maxCount, W, H, PAD, barW, mn: mn.toFixed(0), mx: mx.toFixed(0) };
	});

	const tradeWinLossStreakTimeline = $derived.by(() => {
		const sorted = [...trades]
			.filter((t) => t.close_date != null && t.profit_pct != null && isFinite(t.profit_pct))
			.sort((a, b) => new Date(a.close_date!).getTime() - new Date(b.close_date!).getTime())
			.slice(-60);
		if (sorted.length < 10) return null;
		let streak = 0;
		const pts = sorted.map((t) => {
			const win = t.profit_pct! >= 0;
			streak = win ? Math.max(1, streak + 1) : Math.min(-1, streak - 1);
			return { streak, win };
		});
		const maxStreak = Math.max(...pts.map((p) => Math.abs(p.streak)), 1);
		const W = 520,
			H = 60,
			PAD = 6;
		const barW = Math.max(3, Math.floor((W - PAD * 2) / pts.length) - 1);
		return { pts, maxStreak, W, H, PAD, barW };
	});

	const tradeHoldingTimeHistogram = $derived.by(() => {
		const vals = trades
			.filter((t) => t.trade_duration_min != null && t.trade_duration_min > 0)
			.map((t) => t.trade_duration_min! / 60);
		if (vals.length < 5) return null;
		const mn = 0,
			mx = Math.min(Math.max(...vals), 200);
		const bins = 12,
			step = (mx - mn) / bins || 1;
		const counts = Array.from({ length: bins }, (_, i) => {
			const lo = mn + i * step,
				hi = lo + step;
			return {
				lo,
				count: vals.filter((v) => v >= lo && (i === bins - 1 ? v <= hi + 9999 : v < hi)).length
			};
		});
		const maxCount = Math.max(...counts.map((c) => c.count), 1);
		const W = 380,
			H = 70,
			PAD = 8,
			barW = Math.floor((W - PAD * 2) / bins) - 1;
		const avgH = (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1);
		return { counts, maxCount, W, H, PAD, barW, mx: mx.toFixed(0), avgH, total: vals.length };
	});

	const tradeProfitByPair = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const t of trades) {
			if (!t.pair || t.profit_pct == null) continue;
			if (!map[t.pair]) map[t.pair] = [];
			map[t.pair].push(t.profit_pct);
		}
		const rows = Object.entries(map)
			.map(([pair, vals]) => ({
				pair,
				avg: vals.reduce((a, b) => a + b, 0) / vals.length,
				count: vals.length
			}))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 16);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 400,
			H = rows.length * 14 + 20,
			PAD = 8,
			midX = W / 2,
			barMaxW = (W - PAD * 2) / 2 - 50;
		return { rows, maxAbs, W, H, PAD, midX, barMaxW };
	});

	const tradeMonthlyProfitHeatmap = $derived.by(() => {
		const map: Record<string, { sum: number; count: number }> = {};
		for (const t of trades) {
			if (!t.close_date || t.profit_pct == null) continue;
			const d = new Date(t.close_date);
			const key = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
			if (!map[key]) map[key] = { sum: 0, count: 0 };
			map[key].sum += t.profit_pct;
			map[key].count++;
		}
		const months = Object.keys(map).sort().slice(-12);
		if (months.length < 3) return null;
		const rows = months.map((m) => ({
			label: m.slice(5),
			avg: map[m].sum / map[m].count,
			count: map[m].count
		}));
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 420,
			H = 60,
			PAD = 8,
			barW = Math.min(28, Math.floor((W - PAD * 2) / rows.length) - 2),
			midY = H / 2;
		return { rows, maxAbs, W, H, PAD, barW, midY };
	});

	const tradeEntryHourDistribution = $derived.by(() => {
		const counts = Array.from({ length: 24 }, (_, h) => ({ hour: h, count: 0, profitSum: 0 }));
		for (const t of trades) {
			if (!t.open_date) continue;
			const h = new Date(t.open_date).getUTCHours();
			counts[h].count++;
			if (t.profit_pct != null) counts[h].profitSum += t.profit_pct;
		}
		const active = counts.filter((c) => c.count > 0);
		if (active.length < 4) return null;
		const maxCount = Math.max(...counts.map((c) => c.count), 1);
		const W = 420,
			H = 65,
			PAD = 8,
			barW = Math.floor((W - PAD * 2) / 24) - 1;
		return { counts, maxCount, W, H, PAD, barW };
	});

	const tradeProfitQuantiles = $derived.by(() => {
		const vals = [...trades.filter((t) => t.profit_pct != null).map((t) => t.profit_pct!)].sort(
			(a, b) => a - b
		);
		if (vals.length < 10) return null;
		const q = (p: number) => {
			const i = p * (vals.length - 1);
			const lo = Math.floor(i);
			return vals[lo] + (i - lo) * ((vals[lo + 1] ?? vals[lo]) - vals[lo]);
		};
		const p5 = q(0.05),
			p25 = q(0.25),
			p50 = q(0.5),
			p75 = q(0.75),
			p95 = q(0.95);
		const mn = vals[0],
			mx = vals[vals.length - 1];
		const range = mx - mn || 1;
		const W = 360,
			H = 60,
			PAD = 20;
		const toX = (v: number) => PAD + ((v - mn) / range) * (W - PAD * 2);
		const midY = H / 2;
		return { p5, p25, p50, p75, p95, mn, mx, W, H, PAD, toX, midY, count: vals.length };
	});

	const tradePairWinLossBalance = $derived.by(() => {
		const map = new Map<string, { wins: number; losses: number }>();
		for (const t of trades) {
			if (!t.pair || t.profit_pct == null) continue;
			if (!map.has(t.pair)) map.set(t.pair, { wins: 0, losses: 0 });
			const e = map.get(t.pair)!;
			if (t.profit_pct >= 0) e.wins++;
			else e.losses++;
		}
		const rows = [...map.entries()]
			.filter(([, e]) => e.wins + e.losses >= 3)
			.map(([pair, e]) => {
				const total = e.wins + e.losses;
				return {
					pair: pair.split('/')[0].slice(0, 8),
					wins: e.wins,
					losses: e.losses,
					total,
					wr: (e.wins / total) * 100
				};
			})
			.sort((a, b) => b.wr - a.wr)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const W = 380,
			H = 90,
			PAD = 10;
		const barH = Math.max(6, Math.floor((H - PAD * 2) / rows.length) - 2);
		return { rows, W, H, PAD, barH };
	});

	const tradeExitReasonHoldingTime = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const t of trades) {
			if (!t.exit_reason || !t.open_date || !t.close_date) continue;
			const hrs = (new Date(t.close_date).getTime() - new Date(t.open_date).getTime()) / 3600000;
			if (!isFinite(hrs) || hrs <= 0) continue;
			const tag = t.exit_reason.slice(0, 18);
			if (!map.has(tag)) map.set(tag, []);
			map.get(tag)!.push(hrs);
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 2)
			.map(([tag, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const med = sorted[Math.floor(sorted.length / 2)];
				return { tag, med, count: vals.length };
			})
			.sort((a, b) => b.med - a.med)
			.slice(0, 10);
		if (rows.length < 2) return null;
		const maxMed = Math.max(...rows.map((r) => r.med), 0.01);
		return { rows, maxMed };
	});

	const tradeDowAvgProfitBars = $derived.by(() => {
		const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
		const buckets: number[][] = Array.from({ length: 7 }, () => []);
		for (const t of trades) {
			if (!t.open_date || t.profit_pct == null || !isFinite(t.profit_pct)) continue;
			const dow = new Date(t.open_date).getUTCDay();
			buckets[dow].push(t.profit_pct);
		}
		const rows = days.map((label, i) => {
			const vals = buckets[i];
			const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
			return { label, avg, count: vals.length };
		});
		if (rows.every((r) => r.count === 0)) return null;
		const mx = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 320,
			H = 70,
			PAD = 8,
			barW = Math.floor((W - PAD * 2) / 7) - 2;
		const midY = H / 2;
		const toH = (v: number) => Math.max(2, (Math.abs(v) / mx) * (H / 2 - PAD));
		return { rows, mx: mx.toFixed(2), W, H, PAD, barW, midY, toH };
	});

	const tradeCumProfitByExitReason = $derived.by(() => {
		const sorted = [...trades]
			.filter(
				(t) => t.close_date && t.exit_reason && t.profit_pct != null && isFinite(t.profit_pct)
			)
			.sort((a, b) => new Date(a.close_date!).getTime() - new Date(b.close_date!).getTime());
		if (sorted.length < 10) return null;
		const reasonCounts = new Map<string, number>();
		for (const t of sorted) {
			const r = t.exit_reason!;
			reasonCounts.set(r, (reasonCounts.get(r) ?? 0) + 1);
		}
		const topReasons = [...reasonCounts.entries()]
			.sort((a, b) => b[1] - a[1])
			.slice(0, 4)
			.map(([r]) => r);
		const colors = [
			'var(--ch-profit-strong)',
			'var(--ch-violet-strong)',
			'var(--ch-warn)',
			'var(--ch-loss-strong)'
		];
		const lines = topReasons
			.map((reason, ri) => {
				const pts = sorted.filter((t) => t.exit_reason === reason);
				let cum = 0;
				const cumPts = pts.map((t, i) => {
					cum += t.profit_pct!;
					return { i, cum };
				});
				return { reason: reason.slice(0, 16), color: colors[ri], pts: cumPts };
			})
			.filter((l) => l.pts.length >= 3);
		if (lines.length < 2) return null;
		const allCum = lines.flatMap((l) => l.pts.map((p) => p.cum));
		const mnC = Math.min(...allCum, 0),
			mxC = Math.max(...allCum, 0.01);
		const W = 380,
			H = 85,
			PAD = 10;
		const toX = (i: number, n: number) => PAD + (i / Math.max(n - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - mnC) / (mxC - mnC)) * (H - PAD * 2);
		const zeroY = Math.max(PAD, Math.min(H - PAD, toY(0)));
		const polylines = lines.map((l) => ({
			...l,
			poly: l.pts
				.map((p) => `${toX(p.i, l.pts.length).toFixed(1)},${toY(p.cum).toFixed(1)}`)
				.join(' ')
		}));
		return { polylines, W, H, PAD, zeroY };
	});

	const tradeMonthlyWinRateTrend = $derived.by(() => {
		const map = new Map<string, { wins: number; total: number }>();
		for (const t of trades) {
			if (!t.close_date || t.profit_pct == null || !isFinite(t.profit_pct)) continue;
			const mo = t.close_date.slice(0, 7);
			if (!map.has(mo)) map.set(mo, { wins: 0, total: 0 });
			const e = map.get(mo)!;
			e.total++;
			if (t.profit_pct >= 0) e.wins++;
		}
		const months = [...map.keys()].sort();
		if (months.length < 3) return null;
		const pts = months.map((mo, i) => {
			const e = map.get(mo)!;
			return { i, mo: mo.slice(5), wr: e.total ? (e.wins / e.total) * 100 : 0, total: e.total };
		});
		const W = 380,
			H = 70,
			PAD = 8;
		const toX = (i: number) => PAD + (i / Math.max(pts.length - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - v / 100) * (H - PAD * 2);
		const poly = pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.wr).toFixed(1)}`).join(' ');
		const areaBase = `${toX(pts.length - 1).toFixed(1)},${H - PAD} ${toX(0).toFixed(1)},${H - PAD}`;
		const area = poly + ' ' + areaBase;
		const y50 = toY(50);
		return { pts, poly, area, W, H, PAD, y50 };
	});

	const tradePairProfitHeatmap = $derived.by(() => {
		const pairs = [...new Set(trades.filter((t) => t.pair).map((t) => t.pair!))];
		const months = [
			...new Set(trades.filter((t) => t.close_date).map((t) => t.close_date!.slice(0, 7)))
		].sort();
		if (pairs.length < 2 || months.length < 2) return null;
		const topPairs = pairs.slice(0, Math.min(6, pairs.length));
		const recentMonths = months.slice(-6);
		const grid = topPairs.map((pair) =>
			recentMonths.map((mo) => {
				const ts = trades.filter(
					(t) =>
						t.pair === pair &&
						t.close_date?.startsWith(mo) &&
						t.profit_pct != null &&
						isFinite(t.profit_pct)
				);
				return ts.length ? ts.reduce((a, t) => a + t.profit_pct!, 0) / ts.length : null;
			})
		);
		const vals = grid.flat().filter((v) => v != null) as number[];
		if (vals.length < 4) return null;
		const maxAbs = Math.max(...vals.map(Math.abs), 0.01);
		const CW = 42,
			CH = 14,
			PAD = 4;
		const W = PAD + recentMonths.length * CW + 80,
			H = PAD + topPairs.length * CH + 14;
		return { topPairs, recentMonths, grid, maxAbs, CW, CH, PAD, W, H };
	});

	const tradeExitReasonWinRate = $derived.by(() => {
		const map = new Map<string, { wins: number; total: number }>();
		for (const t of trades) {
			const reason = t.exit_reason ?? 'unknown';
			if (!map.has(reason)) map.set(reason, { wins: 0, total: 0 });
			const e = map.get(reason)!;
			e.total++;
			if ((t.profit_pct ?? 0) >= 0) e.wins++;
		}
		const rows = [...map.entries()]
			.filter(([, e]) => e.total >= 3)
			.map(([reason, e]) => ({
				reason: reason.slice(0, 18),
				wr: (e.wins / e.total) * 100,
				total: e.total
			}))
			.sort((a, b) => b.total - a.total)
			.slice(0, 8);
		if (rows.length < 2) return null;
		const W = 340,
			H = rows.length * 16 + 4,
			barMaxW = W - 140;
		return { rows, W, H, barMaxW };
	});

	const tradeProfitBySizeQuartile = $derived.by(() => {
		const valid = trades.filter(
			(t) =>
				t.stake_amount != null &&
				isFinite(t.stake_amount) &&
				t.profit_pct != null &&
				isFinite(t.profit_pct)
		);
		if (valid.length < 12) return null;
		const sorted = [...valid].sort((a, b) => a.stake_amount! - b.stake_amount!);
		const Q = Math.floor(sorted.length / 4);
		const quartiles = [
			{ label: 'Q1 (small)', trades: sorted.slice(0, Q) },
			{ label: 'Q2', trades: sorted.slice(Q, Q * 2) },
			{ label: 'Q3', trades: sorted.slice(Q * 2, Q * 3) },
			{ label: 'Q4 (large)', trades: sorted.slice(Q * 3) }
		];
		const rows = quartiles.map((q) => {
			const profits = q.trades.map((t) => t.profit_pct!);
			const avg = profits.reduce((a, v) => a + v, 0) / profits.length;
			const wins = profits.filter((p) => p >= 0).length;
			return { label: q.label, avg, wr: (wins / profits.length) * 100, count: profits.length };
		});
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 320,
			H = 72,
			PAD = 10,
			barW = Math.floor((W - PAD * 2) / 4) - 4,
			midY = H / 2;
		return { rows, maxAbs, W, H, PAD, barW, midY };
	});

	const tradeDowHourHeatmap = $derived.by(() => {
		const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
		const HOURS = [0, 4, 8, 12, 16, 20];
		const grid: number[][] = Array.from({ length: 7 }, () => new Array(6).fill(0));
		for (const t of selectedTrades) {
			if (!t.close_date) continue;
			const d = new Date(t.close_date);
			const dow = (d.getUTCDay() + 6) % 7;
			const h = d.getUTCHours();
			const hBin = Math.min(5, Math.floor(h / 4));
			grid[dow][hBin]++;
		}
		const maxVal = Math.max(...grid.flat(), 1);
		const W = 300,
			H = 90,
			cellW = Math.floor((W - 30) / 6),
			cellH = Math.floor((H - 10) / 7);
		return { grid, maxVal, DAYS, HOURS, W, H, cellW, cellH, count: selectedTrades.length };
	});

	const tradeAvgProfitByPair = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const t of selectedTrades) {
			if (!t.pair || t.profit_pct == null || !isFinite(t.profit_pct)) continue;
			const arr = map.get(t.pair) ?? [];
			arr.push(t.profit_pct);
			map.set(t.pair, arr);
		}
		if (map.size < 3) return null;
		const rows = [...map.entries()]
			.filter(([, ps]) => ps.length >= 2)
			.map(([pair, ps]) => ({
				pair: pair.slice(0, 14),
				avg: ps.reduce((a, v) => a + v, 0) / ps.length,
				count: ps.length
			}))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 340,
			H = rows.length * 16 + 6,
			PAD = 8,
			barMaxW = W - 90,
			midX = PAD + barMaxW / 2;
		const toX = (v: number) => PAD + ((v + maxAbs) / (2 * maxAbs)) * barMaxW;
		const zeroX = toX(0);
		return { rows, maxAbs, W, H, PAD, barMaxW, midX, zeroX, toX };
	});

	const tradeCumProfitTimeline = $derived.by(() => {
		const sorted = selectedTrades
			.filter((t) => t.close_date && t.profit_pct != null && isFinite(t.profit_pct))
			.sort((a, b) => a.close_date!.localeCompare(b.close_date!));
		if (sorted.length < 5) return null;
		let cum = 0;
		const pts = sorted.map((t, i) => {
			cum += t.profit_pct!;
			return { i, cum, date: t.close_date!.slice(0, 10) };
		});
		const minY = Math.min(...pts.map((p) => p.cum)),
			maxY = Math.max(...pts.map((p) => p.cum));
		const W = 380,
			H = 72,
			PAD = 10;
		const toX = (i: number) => PAD + (i / Math.max(pts.length - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - minY) / Math.max(maxY - minY, 0.01)) * (H - PAD * 2);
		const polyline = pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.cum).toFixed(1)}`).join(' ');
		const area =
			`${toX(0).toFixed(1)},${H - PAD} ` +
			polyline +
			` ${toX(pts.length - 1).toFixed(1)},${H - PAD}`;
		const zeroY = Math.max(PAD, Math.min(H - PAD, toY(0)));
		const finalCum = pts[pts.length - 1].cum;
		const color = finalCum >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)';
		const fillColor = finalCum >= 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)';
		return {
			pts,
			polyline,
			area,
			zeroY,
			W,
			H,
			PAD,
			finalCum,
			color,
			fillColor,
			toX,
			firstDate: pts[0].date,
			lastDate: pts[pts.length - 1].date
		};
	});

	const tradeMonthlyProfitBars = $derived.by(() => {
		const map = new Map<string, { profits: number[] }>();
		for (const t of selectedTrades) {
			if (!t.close_date || t.profit_pct == null || !isFinite(t.profit_pct)) continue;
			const mo = t.close_date.slice(0, 7);
			const cur = map.get(mo) ?? { profits: [] };
			cur.profits.push(t.profit_pct);
			map.set(mo, cur);
		}
		if (map.size < 3) return null;
		const months = [...map.keys()].sort();
		const rows = months.map((m) => {
			const { profits } = map.get(m)!;
			const avg = profits.reduce((a, v) => a + v, 0) / profits.length;
			const wins = profits.filter((p) => p >= 0).length;
			return { mo: m.slice(5), avg, wr: (wins / profits.length) * 100, count: profits.length };
		});
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 360,
			H = 72,
			PAD = 10;
		const bw = Math.max(3, (W - PAD * 2) / rows.length - 2);
		const midY = H / 2;
		const bars = rows.map((r, i) => ({
			x: PAD + i * ((W - PAD * 2) / rows.length),
			h: Math.max(2, (Math.abs(r.avg) / maxAbs) * (midY - PAD - 4)),
			avg: r.avg,
			mo: r.mo,
			wr: r.wr,
			count: r.count,
			color: r.avg >= 0.5 ? 'var(--ch-profit)' : r.avg >= 0 ? 'var(--ch-warn)' : 'var(--ch-loss)'
		}));
		return { bars, bw, W, H, PAD, midY, count: rows.length };
	});

	const tradeHoldTimeVsProfit = $derived.by(() => {
		const raw: { holdH: number; profit: number }[] = [];
		for (const t of selectedTrades) {
			if (!t.open_date || !t.close_date || t.profit_pct == null || !isFinite(t.profit_pct))
				continue;
			const holdH = (new Date(t.close_date).getTime() - new Date(t.open_date).getTime()) / 3600000;
			if (holdH <= 0 || !isFinite(holdH)) continue;
			raw.push({ holdH, profit: t.profit_pct });
		}
		if (raw.length < 10) return null;
		const maxH = Math.min(Math.max(...raw.map((p) => p.holdH)), 240);
		const minP = Math.min(...raw.map((p) => p.profit));
		const maxP = Math.max(...raw.map((p) => p.profit));
		const range = maxP - minP || 1;
		const W = 360,
			H = 80,
			PAD = 12;
		const zeroY = Math.max(PAD, Math.min(H - PAD, PAD + (maxP / range) * (H - PAD * 2)));
		const dots = raw.map((p) => ({
			cx: PAD + Math.min(1, p.holdH / maxH) * (W - PAD * 2),
			cy: PAD + ((maxP - p.profit) / range) * (H - PAD * 2),
			color: p.profit >= 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)'
		}));
		return {
			dots,
			W,
			H,
			PAD,
			zeroY,
			maxH: maxH.toFixed(0),
			minP: minP.toFixed(1),
			maxP: maxP.toFixed(1)
		};
	});

	const tradeWinRateByExitReason = $derived.by(() => {
		const map = new Map<string, { wins: number; total: number }>();
		for (const t of selectedTrades) {
			if (!t.exit_reason || t.profit_pct == null || !isFinite(t.profit_pct)) continue;
			const cur = map.get(t.exit_reason) ?? { wins: 0, total: 0 };
			cur.total++;
			if (t.profit_pct > 0) cur.wins++;
			map.set(t.exit_reason, cur);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.filter(([, d]) => d.total >= 2)
			.map(([reason, d]) => ({
				reason: reason.slice(0, 18),
				wr: (d.wins / d.total) * 100,
				count: d.total
			}))
			.sort((a, b) => b.wr - a.wr);
		if (rows.length < 2) return null;
		const W = 340,
			H = rows.length * 16 + 6,
			PAD = 8,
			barMaxW = W - 90;
		return { rows, W, H, PAD, barMaxW };
	});

	const tradeProfitByEntryHour = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const map = new Map<number, { sum: number; count: number }>();
		for (const t of trades) {
			if (!t.open_date) continue;
			const h = new Date(t.open_date).getUTCHours();
			const e = map.get(h) ?? { sum: 0, count: 0 };
			e.sum += t.profit_pct ?? 0;
			e.count++;
			map.set(h, e);
		}
		if (map.size < 4) return null;
		const rows = Array.from({ length: 24 }, (_, h) => {
			const e = map.get(h);
			return { h, avg: e ? e.sum / e.count : 0, count: e?.count ?? 0 };
		});
		const vals = rows.map((r) => r.avg);
		const maxAbs = Math.max(Math.abs(Math.min(...vals)), Math.abs(Math.max(...vals)), 0.01);
		const W = 380,
			H = 80,
			PAD = 10;
		const bw = (W - PAD * 2) / 24 - 1;
		const midY = H / 2;
		const toH = (v: number) => (Math.abs(v) / maxAbs) * (midY - PAD);
		return { rows, W, H, PAD, bw, midY, toH, maxAbs };
	});

	const tradeDurationHistogram = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const durations = trades
			.filter((t) => t.open_date && t.close_date)
			.map(
				(t) =>
					(new Date(t.close_date as string).getTime() - new Date(t.open_date as string).getTime()) /
					3600000
			);
		if (durations.length < 8) return null;
		const maxH = Math.max(...durations);
		const bins = 16;
		const step = maxH / bins;
		const buckets = Array.from({ length: bins }, (_, i) => ({ lo: i * step, count: 0 }));
		for (const d of durations) {
			const bi = Math.min(bins - 1, Math.floor(d / step));
			buckets[bi].count++;
		}
		const maxC = Math.max(...buckets.map((b) => b.count), 1);
		const W = 340,
			H = 72,
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
			maxH: maxH.toFixed(0),
			total: durations.length
		};
	});

	const tradeMonthlyWinLoss = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const map = new Map<string, { wins: number; losses: number }>();
		for (const t of trades) {
			if (!t.close_date) continue;
			const mo = (t.close_date as string).slice(0, 7);
			const e = map.get(mo) ?? { wins: 0, losses: 0 };
			if ((t.profit_pct ?? 0) >= 0) e.wins++;
			else e.losses++;
			map.set(mo, e);
		}
		if (map.size < 3) return null;
		const months = [...map.keys()].sort();
		const data = months.map((m) => ({ m: m.slice(5), ...map.get(m)! }));
		const maxTotal = Math.max(...data.map((d) => d.wins + d.losses), 1);
		const W = 380,
			H = 72,
			PAD = 10;
		const bw = Math.max(2, (W - PAD * 2) / months.length - 2);
		const toX = (i: number) => PAD + i * ((W - PAD * 2) / months.length);
		const toH = (v: number) => (v / maxTotal) * (H - PAD * 2 - 10);
		return { data, W, H, PAD, bw, toX, toH, maxTotal };
	});

	const tradePairProfitRanking = $derived.by(() => {
		if (!trades || trades.length < 8) return null;
		const map = new Map<string, { sum: number; count: number }>();
		for (const t of trades) {
			if (!t.pair || t.profit_pct == null) continue;
			const e = map.get(t.pair) ?? { sum: 0, count: 0 };
			e.sum += t.profit_pct as number;
			e.count++;
			map.set(t.pair, e);
		}
		const rows = [...map.entries()]
			.filter(([, e]) => e.count >= 2)
			.map(([pair, e]) => ({ pair: pair.slice(0, 12), avg: e.sum / e.count, count: e.count }))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 340,
			H = rows.length * 16 + 6,
			PAD = 8,
			barMaxW = W - 90;
		const zeroX = PAD + (maxAbs / (2 * maxAbs)) * barMaxW;
		return { rows, W, H, PAD, barMaxW, zeroX, maxAbs };
	});

	const tradeExitHourDistribution = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const counts = new Array(24).fill(0);
		for (const t of trades) {
			if (!t.close_date) continue;
			const h = new Date(t.close_date as string).getUTCHours();
			counts[h]++;
		}
		const maxCount = Math.max(...counts, 1);
		const W = 340,
			H = 50,
			PAD = 6;
		const barW = (W - PAD * 2) / 24;
		return { counts, maxCount, W, H, PAD, barW };
	});

	const tradeAvgProfitByStake = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const stakes = trades
			.filter((t) => t.stake_amount != null && t.profit_pct != null)
			.map((t) => ({ stake: t.stake_amount as number, profit: t.profit_pct as number }));
		if (stakes.length < 8) return null;
		const maxStake = Math.max(...stakes.map((s) => s.stake), 0.01);
		const bucketCount = 8;
		const bucketSize = maxStake / bucketCount;
		const buckets: number[][] = Array.from({ length: bucketCount }, () => []);
		for (const s of stakes) {
			const b = Math.min(Math.floor(s.stake / bucketSize), bucketCount - 1);
			buckets[b].push(s.profit);
		}
		const rows = buckets
			.map((arr, i) => ({
				label: `${(i * bucketSize).toFixed(0)}`,
				avg: arr.length ? arr.reduce((a, v) => a + v, 0) / arr.length : 0,
				count: arr.length
			}))
			.filter((r) => r.count > 0);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 320,
			H = 72,
			PAD = 8;
		const bw = (W - PAD * 2) / rows.length - 2;
		const midY = H / 2;
		return { rows, maxAbs, W, H, PAD, bw, midY };
	});

	const tradeProfitByDow = $derived.by(() => {
		if (!trades || trades.length < 14) return null;
		const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
		const map = new Map<number, number[]>();
		for (const t of trades) {
			if (!t.open_date || t.profit_pct == null) continue;
			const dow = new Date(t.open_date as string).getUTCDay();
			const arr = map.get(dow) ?? [];
			arr.push(t.profit_pct as number);
			map.set(dow, arr);
		}
		const rows = DOW.map((label, i) => {
			const arr = map.get(i) ?? [];
			return {
				label,
				avg: arr.length ? arr.reduce((a, v) => a + v, 0) / arr.length : 0,
				count: arr.length
			};
		});
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 300,
			H = 60,
			PAD = 8;
		const bw = (W - PAD * 2) / 7 - 2;
		const midY = H / 2;
		return { rows, maxAbs, W, H, PAD, bw, midY };
	});

	const tradeRollingWinRate = $derived.by(() => {
		if (!trades || trades.length < 20) return null;
		const sorted = [...trades]
			.filter((t) => t.open_date && t.profit_pct != null)
			.sort((a, b) => (a.open_date as string).localeCompare(b.open_date as string));
		if (sorted.length < 20) return null;
		const window = 20;
		const pts: { i: number; wr: number }[] = [];
		for (let i = window - 1; i < sorted.length; i++) {
			const slice = sorted.slice(i - window + 1, i + 1);
			const wins = slice.filter((t) => (t.profit_pct as number) > 0).length;
			pts.push({ i, wr: (wins / window) * 100 });
		}
		const W = 340,
			H = 68,
			PAD = 10;
		const toX = (i: number) =>
			PAD + ((i - (window - 1)) / (sorted.length - window)) * (W - PAD * 2);
		const toY = (wr: number) => H - PAD - (wr / 100) * (H - PAD * 2);
		const polyline = pts.map((p) => `${toX(p.i)},${toY(p.wr)}`).join(' ');
		const fiftyY = toY(50);
		const last = pts[pts.length - 1].wr;
		const color =
			last >= 55
				? 'var(--ch-profit-strong)'
				: last >= 45
					? 'var(--ch-warn)'
					: 'var(--ch-loss-strong)';
		return { pts, polyline, W, H, PAD, toX, toY, fiftyY, color, last: last.toFixed(0) };
	});

	const tradeProfitCDF = $derived.by(() => {
		if (!trades || trades.length < 15) return null;
		const profits = trades
			.filter((t) => t.profit_pct != null)
			.map((t) => t.profit_pct as number)
			.sort((a, b) => a - b);
		if (profits.length < 15) return null;
		const minP = profits[0],
			maxP = profits[profits.length - 1];
		const range = maxP - minP || 0.01;
		const W = 340,
			H = 80,
			PAD = 10;
		const toX = (p: number) => PAD + ((p - minP) / range) * (W - PAD * 2);
		const toY = (i: number) => H - PAD - (i / (profits.length - 1)) * (H - PAD * 2);
		const polyline = profits.map((p, i) => `${toX(p)},${toY(i)}`).join(' ');
		const zeroX = toX(0);
		const p25 = profits[Math.floor(profits.length * 0.25)];
		const p75 = profits[Math.floor(profits.length * 0.75)];
		const median = profits[Math.floor(profits.length * 0.5)];
		return {
			polyline,
			W,
			H,
			PAD,
			zeroX,
			minP: minP.toFixed(2),
			maxP: maxP.toFixed(2),
			median: median.toFixed(2),
			p25: p25.toFixed(2),
			p75: p75.toFixed(2)
		};
	});

	const tradeHoldTimeByMonth = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const map = new Map<string, number[]>();
		for (const t of trades) {
			if (!t.open_date || t.trade_duration_min == null) continue;
			const mo = (t.open_date as string).slice(0, 7);
			const arr = map.get(mo) ?? [];
			arr.push((t.trade_duration_min as number) / 60);
			map.set(mo, arr);
		}
		if (map.size < 3) return null;
		const months = [...map.keys()].sort();
		const pts = months.map((m) => {
			const arr = map.get(m)!;
			return { m: m.slice(5), avg: arr.reduce((a, v) => a + v, 0) / arr.length };
		});
		const maxAvg = Math.max(...pts.map((p) => p.avg), 0.01);
		const W = 340,
			H = 68,
			PAD = 8;
		const bw = (W - PAD * 2) / pts.length - 1;
		return { pts, maxAvg, W, H, PAD, bw };
	});

	const tradePairHoldTimeRanking = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const map = new Map<string, number[]>();
		for (const t of trades) {
			if (!t.pair || t.trade_duration_min == null) continue;
			const arr = map.get(t.pair as string) ?? [];
			arr.push((t.trade_duration_min as number) / 3600);
			map.set(t.pair as string, arr);
		}
		if (map.size < 3) return null;
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 2)
			.map(([pair, vals]) => ({
				pair: (pair as string).split('/')[0],
				avg: vals.reduce((a, v) => a + v, 0) / vals.length
			}))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxAvg = Math.max(...rows.map((r) => r.avg), 0.01);
		const W = 300,
			H = rows.length * 18 + 6,
			PAD = 8,
			barMaxW = W - 50;
		return { rows, maxAvg, W, H, PAD, barMaxW };
	});

	const tradeExitReasonByMonth = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const map = new Map<string, Map<string, number>>();
		for (const t of trades) {
			if (!t.close_date || !t.exit_reason) continue;
			const mo = (t.close_date as string).slice(0, 7);
			const reason = (t.exit_reason as string).slice(0, 10);
			const inner = map.get(mo) ?? new Map();
			inner.set(reason, (inner.get(reason) ?? 0) + 1);
			map.set(mo, inner);
		}
		if (map.size < 3) return null;
		const months = [...map.keys()].sort().slice(-8);
		const allReasons = [...new Set(months.flatMap((m) => [...(map.get(m)?.keys() ?? [])]))].slice(
			0,
			4
		);
		if (allReasons.length < 2) return null;
		const COLORS = ['var(--ch-violet)', 'var(--ch-profit)', 'var(--ch-warn)', 'var(--ch-loss)'];
		const cellW = 28,
			cellH = 16,
			PAD = 4;
		const W = PAD + (months.length + 1) * cellW,
			H = PAD + (allReasons.length + 1) * cellH;
		const maxCount = Math.max(
			...months.flatMap((m) => allReasons.map((r) => map.get(m)?.get(r) ?? 0)),
			1
		);
		return { months, allReasons, map, COLORS, cellW, cellH, PAD, W, H, maxCount };
	});

	const tradeEntryTagWinRate = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const map = new Map<string, { wins: number; total: number }>();
		for (const t of trades) {
			const tag = ((t.enter_tag as string) || 'default').slice(0, 14);
			const s = map.get(tag) ?? { wins: 0, total: 0 };
			s.total += 1;
			if ((t.profit_pct as number) > 0) s.wins += 1;
			map.set(tag, s);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([tag, s]) => ({ tag, wr: s.total > 0 ? s.wins / s.total : 0, total: s.total }))
			.sort((a, b) => b.wr - a.wr)
			.slice(0, 10);
		const W = 300,
			H = rows.length * 18 + 10,
			PAD = 8,
			barMaxW = W - PAD * 2 - 60;
		return { rows, W, H, PAD, barMaxW };
	});

	const tradeSizeTrend = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const map = new Map<string, number[]>();
		for (const t of trades) {
			if (!t.open_date) continue;
			const mo = (t.open_date as string).slice(0, 7);
			const stake = t.stake_amount as number;
			if (stake == null || isNaN(stake)) continue;
			const arr = map.get(mo) ?? [];
			arr.push(stake);
			map.set(mo, arr);
		}
		if (map.size < 3) return null;
		const months = [...map.keys()].sort().slice(-12);
		const avgs = months.map((m) => {
			const a = map.get(m)!;
			return a.reduce((s, v) => s + v, 0) / a.length;
		});
		const minV = Math.min(...avgs),
			maxV = Math.max(...avgs, minV + 1);
		const W = 300,
			H = 56,
			PAD = 8;
		const toX = (i: number) => PAD + (i / Math.max(months.length - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - minV) / (maxV - minV)) * (H - PAD * 2);
		const pts = months.map((_, i) => `${toX(i).toFixed(1)},${toY(avgs[i]).toFixed(1)}`).join(' ');
		return { months, avgs, pts, minV: minV.toFixed(0), maxV: maxV.toFixed(0), W, H, PAD };
	});

	const tradeMonthlyWinLossCount = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const map = new Map<string, { wins: number; losses: number }>();
		for (const t of trades) {
			if (!t.close_date || t.profit_pct == null) continue;
			const mo = (t.close_date as string).slice(0, 7);
			const s = map.get(mo) ?? { wins: 0, losses: 0 };
			if ((t.profit_pct as number) > 0) s.wins++;
			else s.losses++;
			map.set(mo, s);
		}
		if (map.size < 3) return null;
		const months = [...map.keys()].sort().slice(-12);
		const pts = months.map((m) => map.get(m) ?? { wins: 0, losses: 0 });
		const maxCount = Math.max(...pts.map((p) => p.wins + p.losses), 1);
		const W = 300,
			H = 60,
			PAD = 8,
			bw = (W - PAD * 2) / months.length - 1;
		return { months, pts, maxCount, W, H, PAD, bw };
	});

	const tradeProfitByPairCountBucket = $derived.by(() => {
		if (!runs || runs.length < 5) return null;
		const map = new Map<string, number[]>();
		for (const r of runs) {
			const pc = Array.isArray(r.pairs) ? r.pairs.length : undefined;
			if (pc == null || r.total_profit_pct == null) continue;
			const bucket = pc <= 5 ? '1-5' : pc <= 15 ? '6-15' : pc <= 30 ? '16-30' : '30+';
			const arr = map.get(bucket) ?? [];
			arr.push(r.total_profit_pct as number);
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

	const tradeStakeHistogram = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const vals = trades.filter((t) => t.stake_amount != null).map((t) => t.stake_amount as number);
		if (vals.length < 8) return null;
		const minV = Math.min(...vals),
			maxV = Math.max(...vals);
		if (maxV === minV) return null;
		const BINS = 10;
		const binW = (maxV - minV) / BINS;
		const counts = Array(BINS).fill(0);
		for (const v of vals) {
			const bi = Math.min(BINS - 1, Math.floor((v - minV) / binW));
			counts[bi]++;
		}
		const maxCount = Math.max(...counts, 1);
		const W = 300,
			H = 60,
			PAD = 8;
		const bw = (W - PAD * 2) / BINS - 1;
		const bins = counts.map((c, i) => ({
			x: PAD + i * ((W - PAD * 2) / BINS),
			h: Math.max(1, (c / maxCount) * (H - PAD * 2 - 10)),
			c,
			label: (minV + i * binW).toFixed(0)
		}));
		return { bins, maxCount, bw, W, H, PAD, minV: minV.toFixed(0), maxV: maxV.toFixed(0) };
	});

	const tradeExitWinRateTrend = $derived.by(() => {
		if (!trades || trades.length < 8) return null;
		const byReason = new Map<string, { wins: number; total: number }>();
		for (const t of trades) {
			const reason = (t.exit_reason as string | undefined) ?? 'unknown';
			const s = byReason.get(reason) ?? { wins: 0, total: 0 };
			s.total++;
			if (((t.profit_pct as number | undefined) ?? 0) > 0) s.wins++;
			byReason.set(reason, s);
		}
		const rows = [...byReason.entries()]
			.filter(([, s]) => s.total >= 3)
			.map(([reason, s]) => ({
				reason: reason.slice(0, 20),
				wr: (s.wins / s.total) * 100,
				n: s.total
			}))
			.sort((a, b) => b.wr - a.wr)
			.slice(0, 8);
		if (rows.length < 2) return null;
		const W = 320,
			H = rows.length * 18 + 10,
			PAD = 8,
			barMaxW = W - PAD * 2 - 90;
		return { rows, W, H, PAD, barMaxW };
	});

	const tradeWeeklyWinRate = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
		const map = new Map<string, { wins: number; total: number }>();
		for (const t of trades) {
			if (!t.open_date || t.profit_pct == null) continue;
			const dow = DAYS[new Date(t.open_date as string).getDay()];
			const s = map.get(dow) ?? { wins: 0, total: 0 };
			s.total++;
			if ((t.profit_pct as number) > 0) s.wins++;
			map.set(dow, s);
		}
		const rows = DAYS.filter((d) => map.has(d)).map((d) => {
			const s = map.get(d)!;
			return { d, wr: (s.wins / s.total) * 100, n: s.total };
		});
		if (rows.length < 3) return null;
		const W = 280,
			H = 60,
			PAD = 8;
		const bw = (W - PAD * 2) / rows.length - 1;
		return { rows, bw, W, H, PAD };
	});

	const tradeWeeklyProfitTrend = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const byWeek = new Map<string, number[]>();
		for (const t of trades) {
			if (!t.close_date || t.profit_pct == null) continue;
			const d = new Date(t.close_date as string);
			const week = `${d.getFullYear()}-W${String(Math.ceil((d.getDate() - d.getDay() + 6) / 7)).padStart(2, '0')}`;
			const arr = byWeek.get(week) ?? [];
			arr.push(t.profit_pct as number);
			byWeek.set(week, arr);
		}
		if (byWeek.size < 4) return null;
		const pts = [...byWeek.entries()]
			.sort(([a], [b]) => a.localeCompare(b))
			.map(([w, arr]) => ({ w, avg: arr.reduce((s, v) => s + v, 0) / arr.length }));
		const maxAbs = Math.max(...pts.map((p) => Math.abs(p.avg)), 0.01);
		const W = 320,
			H = 60,
			PAD = 8,
			midY = H / 2;
		const bw = Math.max(1, (W - PAD * 2) / pts.length - 0.5);
		return { pts, maxAbs, bw, W, H, PAD, midY };
	});

	const tradeStakeProfitScatter = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const pts = trades
			.filter((t) => t.stake_amount != null && t.profit_pct != null)
			.map((t) => ({ stake: t.stake_amount as number, profit: t.profit_pct as number }));
		if (pts.length < 10) return null;
		const maxStake = Math.max(...pts.map((p) => p.stake), 0.01);
		const maxP = Math.max(...pts.map((p) => Math.abs(p.profit)), 0.01);
		const W = 300,
			H = 100,
			PAD = 12,
			midY = H / 2;
		return { pts, maxStake, maxP, W, H, PAD, midY };
	});

	const tradeEntryTagCount = $derived.by(() => {
		if (!trades || trades.length < 5) return null;
		const map = new Map<string, number>();
		for (const t of trades) {
			const tag = (t.enter_tag as string | null) ?? 'unknown';
			map.set(tag, (map.get(tag) ?? 0) + 1);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.sort((a, b) => b[1] - a[1])
			.slice(0, 10)
			.map(([tag, count]) => ({ tag: tag.slice(0, 14), count }));
		const maxCount = Math.max(...rows.map((r) => r.count), 1);
		const W = 300,
			H = rows.length * 18 + 10,
			PAD = 8,
			barMaxW = W - PAD * 2 - 90;
		return { rows, maxCount, W, H, PAD, barMaxW };
	});

	const tradeExitTagWinRate = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const map = new Map<string, { wins: number; total: number }>();
		for (const t of trades) {
			const tag = (t.exit_reason as string | null) ?? 'unknown';
			const rec = map.get(tag) ?? { wins: 0, total: 0 };
			rec.total++;
			if (((t.profit_pct as number) ?? 0) > 0) rec.wins++;
			map.set(tag, rec);
		}
		const rows = [...map.entries()]
			.filter(([, r]) => r.total >= 3)
			.map(([tag, r]) => ({ tag: tag.slice(0, 16), wr: (r.wins / r.total) * 100, n: r.total }))
			.sort((a, b) => b.wr - a.wr)
			.slice(0, 8);
		if (rows.length < 2) return null;
		const W = 300,
			H = rows.length * 20 + 8,
			PAD = 8,
			barMaxW = W - PAD * 2 - 90;
		return { rows, W, H, PAD, barMaxW };
	});

	const tradeMonthlyAvgHoldTime = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const byMonth = new Map<string, number[]>();
		for (const t of trades) {
			if (!t.open_date || !t.close_date) continue;
			const mo = (t.open_date as string).slice(0, 7);
			const hrs =
				(new Date(t.close_date as string).getTime() - new Date(t.open_date as string).getTime()) /
				3600000;
			if (hrs <= 0 || hrs > 720) continue;
			const arr = byMonth.get(mo) ?? [];
			arr.push(hrs);
			byMonth.set(mo, arr);
		}
		if (byMonth.size < 3) return null;
		const pts = [...byMonth.entries()]
			.sort(([a], [b]) => a.localeCompare(b))
			.map(([mo, arr]) => ({ mo: mo.slice(5), avg: arr.reduce((s, v) => s + v, 0) / arr.length }));
		const maxAvg = Math.max(...pts.map((p) => p.avg), 1);
		const W = 300,
			H = 65,
			PAD = 10;
		const toX = (i: number) => PAD + (i / Math.max(pts.length - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - (v / maxAvg) * (H - PAD * 2);
		const polyline = pts.map((p, i) => `${toX(i).toFixed(1)},${toY(p.avg).toFixed(1)}`).join(' ');
		return { pts, polyline, toX, maxAvg, W, H, PAD };
	});

	const tradePairProfitCDF = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const byPair = new Map<string, number[]>();
		for (const t of trades) {
			if (t.pair == null || t.profit_pct == null) continue;
			const arr = byPair.get(t.pair as string) ?? [];
			arr.push(t.profit_pct as number);
			byPair.set(t.pair as string, arr);
		}
		if (byPair.size < 4) return null;
		const avgByPair = [...byPair.entries()].map(([pair, arr]) => ({
			pair,
			avg: arr.reduce((s, v) => s + v, 0) / arr.length
		}));
		const sorted = [...avgByPair].sort((a, b) => a.avg - b.avg);
		const W = 300,
			H = 65,
			PAD = 10;
		const minV = sorted[0].avg,
			maxV = sorted[sorted.length - 1].avg,
			rng = maxV - minV || 1;
		const toX = (v: number) => PAD + ((v - minV) / rng) * (W - PAD * 2);
		const toY = (i: number) => H - PAD - (i / Math.max(sorted.length - 1, 1)) * (H - PAD * 2);
		const polyline = sorted
			.map((p, i) => `${toX(p.avg).toFixed(1)},${toY(i).toFixed(1)}`)
			.join(' ');
		return { sorted, polyline, toX, toY, W, H, PAD, minV, maxV };
	});

	const tradeExitHourWinRate = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const byHour = new Map<number, { wins: number; total: number }>();
		for (const t of trades) {
			if (!t.close_date) continue;
			const hr = new Date(t.close_date as string).getUTCHours();
			const prev = byHour.get(hr) ?? { wins: 0, total: 0 };
			prev.total++;
			if (((t.profit_pct as number) ?? 0) > 0) prev.wins++;
			byHour.set(hr, prev);
		}
		const bars = [...byHour.entries()]
			.filter(([, v]) => v.total >= 3)
			.sort(([a], [b]) => a - b)
			.map(([hr, v]) => ({ hr, wr: (v.wins / v.total) * 100, n: v.total }));
		if (bars.length < 4) return null;
		const maxWR = Math.max(...bars.map((b) => b.wr), 1);
		const W = 300,
			H = 65,
			PAD = 8;
		const bw = Math.max(2, (W - PAD * 2) / bars.length - 1);
		return { bars, maxWR, W, H, PAD, bw };
	});

	const tradeOpenHourHeatmap = $derived.by(() => {
		if (!trades || trades.length < 20) return null;
		const matrix = Array.from({ length: 7 }, () => Array(24).fill(0));
		const counts = Array.from({ length: 7 }, () => Array(24).fill(0));
		for (const t of trades) {
			if (!t.open_date || t.profit_pct == null) continue;
			const dt = new Date(t.open_date as string);
			const dow = dt.getUTCDay();
			const hr = dt.getUTCHours();
			matrix[dow][hr] += t.profit_pct as number;
			counts[dow][hr]++;
		}
		const cells: { dow: number; hr: number; avg: number }[] = [];
		let maxAbs = 0.01;
		for (let d = 0; d < 7; d++) {
			for (let h = 0; h < 24; h++) {
				if (counts[d][h] < 2) continue;
				const avg = matrix[d][h] / counts[d][h];
				if (Math.abs(avg) > maxAbs) maxAbs = Math.abs(avg);
				cells.push({ dow: d, hr: h, avg });
			}
		}
		if (cells.length < 10) return null;
		const DOW = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
		const W = 300,
			H = 80,
			PAD = 6;
		const cw = (W - PAD * 2) / 24,
			ch = (H - PAD * 2) / 7;
		return { cells, maxAbs, DOW, W, H, PAD, cw, ch };
	});

	const tradeProfitBySide = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const sides = new Map<string, { wins: number; total: number; sumProfit: number }>();
		for (const t of trades) {
			const side = t.is_short ? 'short' : 'long';
			const prev = sides.get(side) ?? { wins: 0, total: 0, sumProfit: 0 };
			prev.total++;
			prev.sumProfit += (t.profit_pct as number) ?? 0;
			if (((t.profit_pct as number) ?? 0) > 0) prev.wins++;
			sides.set(side, prev);
		}
		if (sides.size < 1) return null;
		const bars = [...sides.entries()].map(([side, v]) => ({
			side,
			avgProfit: v.sumProfit / v.total,
			wr: (v.wins / v.total) * 100,
			n: v.total
		}));
		const maxAbsProfit = Math.max(...bars.map((b) => Math.abs(b.avgProfit)), 0.01);
		const W = 300,
			H = 65,
			PAD = 8,
			midY = H / 2;
		const bw = Math.max(20, (W - PAD * 2) / bars.length - 10);
		return { bars, maxAbsProfit, W, H, PAD, midY, bw };
	});

	const tradeSmoothedWinRate = $derived.by(() => {
		if (!trades || trades.length < 20) return null;
		const sorted = [...trades].sort(
			(a, b) =>
				new Date(a.open_date as string).getTime() - new Date(b.open_date as string).getTime()
		);
		const windowSize = Math.max(5, Math.floor(sorted.length / 15));
		const pts = sorted.map((_, i) => {
			const slice = sorted.slice(Math.max(0, i - windowSize), i + 1);
			const wins = slice.filter((t) => ((t.profit_pct as number) ?? 0) > 0).length;
			return { i, wr: (wins / slice.length) * 100 };
		});
		const W = 300,
			H = 65,
			PAD = 10;
		const toX = (i: number) => PAD + (i / Math.max(pts.length - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - 0) / 100) * (H - PAD * 2);
		const polyline = pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.wr).toFixed(1)}`).join(' ');
		return { pts, polyline, toX, toY, W, H, PAD };
	});

	const tradeDurationByExitReason = $derived.by(() => {
		if (!trades || trades.length < 10) return null;
		const byReason = new Map<string, number[]>();
		for (const t of trades) {
			if (!t.exit_reason || !t.open_date || !t.close_date) continue;
			const reason = (t.exit_reason as string).slice(0, 14);
			const hrs =
				(new Date(t.close_date as string).getTime() - new Date(t.open_date as string).getTime()) /
				3600000;
			if (hrs <= 0 || hrs > 720) continue;
			const arr = byReason.get(reason) ?? [];
			arr.push(hrs);
			byReason.set(reason, arr);
		}
		if (byReason.size < 2) return null;
		const bars = [...byReason.entries()]
			.map(([reason, arr]) => ({
				reason,
				avg: arr.reduce((s, v) => s + v, 0) / arr.length,
				n: arr.length
			}))
			.filter((b) => b.n >= 2)
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 8);
		if (bars.length < 2) return null;
		const maxAvg = Math.max(...bars.map((b) => b.avg), 1);
		const W = 300,
			H = bars.length * 18 + 10,
			PAD = 8,
			barMaxW = W - PAD * 2 - 70;
		return { bars, maxAvg, W, H, PAD, barMaxW };
	});
</script>

<svelte:head><title>{strategyName} · Crypto Quant</title></svelte:head>

<main class="mx-auto w-full max-w-[1600px] px-4 py-8 sm:px-6">
	<nav class="mb-4 text-xs text-muted-foreground">
		<a href="/strategies" class="hover:text-foreground">{t(lang, 'detail.breadcrumb')}</a>
		<span class="mx-2">/</span>
		<span class="font-mono">{strategyName}</span>
	</nav>

	<header class="mb-8">
		<div class="flex flex-wrap items-center gap-3">
			<h1 class="text-3xl font-semibold tracking-tight">{strategyName}</h1>
			<StrategyInfo strategy={strategyName} {lang} kelly={data.kelly ?? null} />
			{#if meta}
				<span
					class="rounded border px-2 py-0.5 font-mono text-[10px] uppercase {statusTone[
						meta.status
					]}"
				>
					{t(lang, `strategies.status.${meta.status}`)}
				</span>
			{/if}
			<a
				href="/strategies/{strategyName}/share"
				class="ml-auto flex items-center gap-1.5 rounded-md border border-border bg-secondary px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					class="h-3.5 w-3.5"
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
					stroke-width="2"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z"
					/>
				</svg>
				Share
			</a>
		</div>
		{#if meta}
			<p class="mt-2 max-w-3xl text-sm text-muted-foreground">{meta.tagline}</p>
		{/if}
	</header>

	<section class="mb-6 grid gap-4 md:grid-cols-3">
		<div class="rounded-lg border bg-card p-4">
			<div class="text-xs text-muted-foreground">{t(lang, 'detail.mode')}</div>
			<div class="mt-1 font-mono text-sm">{meta?.mode ?? '—'}</div>
		</div>
		<div class="rounded-lg border bg-card p-4">
			<div class="text-xs text-muted-foreground">{t(lang, 'detail.tf')}</div>
			<div class="mt-1 font-mono text-sm">{meta?.timeframe ?? runs[0]?.timeframe ?? '—'}</div>
		</div>
		<div class="rounded-lg border bg-card p-4">
			<div class="text-xs text-muted-foreground">{t(lang, 'detail.pairs')}</div>
			<div class="mt-1 font-mono text-xs">
				{(meta?.assets ?? runs[0]?.pairs ?? []).slice(0, 4).join(' · ') || '—'}
			</div>
		</div>
	</section>

	{#if currentFactors && currentFactors.length}
		<section class="mb-6 rounded-lg border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">{t(lang, 'detail.factors')}</h2>
			<FactorBadges factors={currentFactors} />
			<p class="mt-3 text-xs text-muted-foreground">{t(lang, 'detail.factorsDesc')}</p>
		</section>
	{/if}

	{#if meta}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<h2 class="mb-2 text-sm font-semibold">{t(lang, 'detail.mechanics')}</h2>
			<p class="mb-3 text-sm text-foreground">{meta.summary}</p>
			<ul class="space-y-1 text-sm text-muted-foreground">
				{#each meta.mechanics as m, _i (_i)}
					<li class="flex gap-2"><span class="text-primary">▸</span><span>{m}</span></li>
				{/each}
			</ul>
			{#if STRATEGY_FORMULAS[strategyName]}
				{@const f = STRATEGY_FORMULAS[strategyName]}
				<FormulaCard label={f.label} formula={f.formula} note={f.note} />
			{/if}
		</section>
	{/if}

	{#if runsTimeSeries}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Metric History <span class="ml-1 text-xs font-normal text-muted-foreground"
						>({runs.length} runs over time)</span
					>
					<ChartInfo metric="leaderboard" {lang} />
				</h2>
				<div class="flex gap-4 text-[10px]">
					<span class="flex items-center gap-1"
						><span class="inline-block h-0.5 w-4 rounded bg-green-400"></span>Profit%</span
					>
					<span class="flex items-center gap-1"
						><span class="inline-block h-0.5 w-4 rounded bg-indigo-400"></span>Sharpe</span
					>
					<span class="flex items-center gap-1"
						><span class="inline-block h-0.5 w-4 rounded bg-red-400"></span>MaxDD%</span
					>
				</div>
			</div>
			<div class="space-y-2">
				{#each [runsTimeSeries.profit, runsTimeSeries.sharpe, runsTimeSeries.dd] as s, _i (_i)}
					<div class="relative">
						<div class="absolute top-0 right-0 font-mono text-[10px]" style="color:{s.color}">
							{s.last.toFixed(2)}
							<span class="text-muted-foreground">({s.mn.toFixed(1)}–{s.mx.toFixed(1)})</span>
						</div>
						<svg
							viewBox="0 0 {runsTimeSeries.W} {runsTimeSeries.H}"
							class="w-full"
							style="height:50px"
						>
							<polyline
								points={s.pts}
								fill="none"
								stroke={s.color}
								stroke-width="1.5"
								opacity="0.8"
							/>
						</svg>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{runsTimeSeries.dates[0]}</span>
				<span>{runsTimeSeries.dates[runsTimeSeries.dates.length - 1]}</span>
			</div>
		</section>
	{/if}

	{#if runs.length > 0}
		<section class="mb-6">
			<div class="mb-3">
				<Callout type="warning">
					回测不等于实盘 · 以下指标基于历史数据优化，实盘滑点/资金量/市场结构变化均会影响实际表现。
				</Callout>
			</div>
			{#if bestRunPercentiles}
				<div class="mb-3 flex flex-wrap items-center gap-2">
					<span class="text-[11px] text-muted-foreground"
						>Best run ranks among {runs.length} runs:</span
					>
					{#if bestRunPercentiles.profit != null}
						{@const p = bestRunPercentiles.profit}
						<span
							class="rounded-full border px-2.5 py-0.5 font-mono text-[11px]
							{p >= 80
								? 'border-green-700/50 bg-green-950/40 text-green-400'
								: p >= 50
									? 'border-yellow-700/50 bg-yellow-950/30 text-yellow-400'
									: 'border-red-700/50 bg-red-950/30 text-red-400'}"
							title="Profit percentile rank among all {runs.length} runs"
						>
							Profit p{p}
						</span>
					{/if}
					{#if bestRunPercentiles.sharpe != null}
						{@const p = bestRunPercentiles.sharpe}
						<span
							class="rounded-full border px-2.5 py-0.5 font-mono text-[11px]
							{p >= 80
								? 'border-green-700/50 bg-green-950/40 text-green-400'
								: p >= 50
									? 'border-yellow-700/50 bg-yellow-950/30 text-yellow-400'
									: 'border-red-700/50 bg-red-950/30 text-red-400'}"
							title="Sharpe percentile rank among all {runs.length} runs"
						>
							Sharpe p{p}
						</span>
					{/if}
					{#if bestRunPercentiles.dd != null}
						{@const p = bestRunPercentiles.dd}
						<span
							class="rounded-full border px-2.5 py-0.5 font-mono text-[11px]
							{p >= 80
								? 'border-green-700/50 bg-green-950/40 text-green-400'
								: p >= 50
									? 'border-yellow-700/50 bg-yellow-950/30 text-yellow-400'
									: 'border-red-700/50 bg-red-950/30 text-red-400'}"
							title="DD lower than {p}% of runs (lower DD = better)"
						>
							DD p{p}
						</span>
					{/if}
					{#if optimizationTrend}
						<span
							class="rounded-full border px-2.5 py-0.5 font-mono text-[11px] {optimizationTrend.color}"
							title="Comparing last {optimizationTrend.n} vs first {optimizationTrend.n} runs · profit delta {optimizationTrend.profitDelta >=
							0
								? '+'
								: ''}{optimizationTrend.profitDelta.toFixed(
								1
							)}pp · Sharpe delta {optimizationTrend.sharpeDelta >= 0
								? '+'
								: ''}{optimizationTrend.sharpeDelta.toFixed(2)}"
						>
							{optimizationTrend.icon}
							{optimizationTrend.label}
						</span>
					{/if}
					{#if cagrData}
						{@const tone =
							cagrData.cagr >= 50
								? 'border-green-700/50 bg-green-950/40 text-green-400'
								: cagrData.cagr >= 0
									? 'border-yellow-700/50 bg-yellow-950/30 text-yellow-400'
									: 'border-red-700/50 bg-red-950/30 text-red-400'}
						<span
							class="rounded-full border px-2.5 py-0.5 font-mono text-[11px] {tone}"
							title="CAGR from best run · {cagrData.profit.toFixed(
								1
							)}% over {cagrData.years}y · timerange {cagrData.timerange}"
						>
							CAGR {cagrData.cagr >= 0 ? '+' : ''}{cagrData.cagr.toFixed(1)}%/yr
						</span>
					{/if}
				</div>
			{/if}
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					{fmt('detail.backtestTable', { n: Math.min(runs.length, 25) })}
				</h2>
				<span class="text-xs text-muted-foreground"
					>{fmt('detail.backtestCount', { n: runs.length })}</span
				>
			</div>
			<div class="overflow-x-auto rounded-lg border bg-card">
				<table class="w-full text-xs">
					<thead class="bg-secondary text-left text-[10px] text-muted-foreground uppercase">
						<tr>
							<th class="px-3 py-2">{t(lang, 'detail.table.imported')}</th>
							<th class="px-3">{t(lang, 'detail.table.timerange')}</th>
							<th class="px-3 text-right"
								><span class="inline-flex items-center"
									>{t(lang, 'detail.table.trades')}<InfoTip
										text={t(lang, 'metric.tip.trades')}
									/></span
								></th
							>
							<th class="px-3 text-right"
								><span class="inline-flex items-center"
									>{t(lang, 'detail.table.winRate')}<InfoTip
										text={t(lang, 'metric.tip.wr')}
									/></span
								></th
							>
							<th class="px-3 text-right"
								><span class="inline-flex items-center"
									>{t(lang, 'detail.table.profit')}<InfoTip
										text={t(lang, 'metric.tip.profit')}
									/></span
								></th
							>
							<th class="px-3 text-right"
								><span class="inline-flex items-center"
									>{t(lang, 'detail.table.maxDd')}<InfoTip
										text={t(lang, 'metric.tip.maxDd')}
									/></span
								></th
							>
							<th class="px-3 text-right"
								><span class="inline-flex items-center"
									>{t(lang, 'detail.table.calmar')}<InfoTip
										text={t(lang, 'metric.tip.calmar')}
									/></span
								></th
							>
							<th class="px-3 text-right"
								><span class="inline-flex items-center"
									>{t(lang, 'detail.table.sharpe')}<InfoTip
										text={t(lang, 'metric.tip.sharpe')}
									/></span
								></th
							>
							<th class="px-3 text-right"
								><span class="inline-flex items-center"
									>{t(lang, 'detail.table.sortino')}<InfoTip
										text={t(lang, 'metric.tip.sortino')}
										placement="top"
									/></span
								></th
							>
							<th class="px-3 text-right"
								><span class="inline-flex items-center"
									>{t(lang, 'detail.table.pf')}<InfoTip
										text={t(lang, 'metric.tip.pf')}
										placement="top"
									/></span
								></th
							>
						</tr>
					</thead>
					<tbody class="font-mono">
						{#each runs.slice(0, 25) as r (r.id)}
							<tr class="border-t border-border hover:bg-accent/40">
								<td class="px-3 py-1.5 text-muted-foreground">{fmtTime(r.imported_at)}</td>
								<td class="px-3 text-muted-foreground">{r.timerange ?? '—'}</td>
								<td class="px-3 text-right">{r.total_trades ?? 0}</td>
								<td class="px-3 text-right"
									>{r.win_rate_pct == null ? '—' : r.win_rate_pct.toFixed(1)}</td
								>
								<td class="px-3 text-right {signClass(r.total_profit_pct)}"
									>{fmtPct(r.total_profit_pct)}</td
								>
								<td class="px-3 text-right" class:text-red-500={(r.max_drawdown_pct ?? 0) > 20}>
									{r.max_drawdown_pct == null ? '—' : r.max_drawdown_pct.toFixed(1)}
								</td>
								<td class="px-3 text-right">{r.calmar == null ? '—' : r.calmar.toFixed(2)}</td>
								<td class="px-3 text-right">{r.sharpe == null ? '—' : r.sharpe.toFixed(2)}</td>
								<td class="px-3 text-right">{r.sortino == null ? '—' : r.sortino.toFixed(2)}</td>
								<td class="px-3 text-right"
									>{r.profit_factor == null ? '—' : r.profit_factor.toFixed(2)}</td
								>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{:else}
		<section
			class="mb-6 rounded-lg border border-dashed bg-card p-6 text-center text-sm text-muted-foreground"
		>
			{t(lang, 'detail.empty')}
		</section>
	{/if}

	{#if bestRunId && (calendarLoading || calendarLoaded)}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Daily P&L Calendar <span class="ml-1 text-xs font-normal text-muted-foreground"
						>(best run)</span
					>
					<ChartInfo metric="calendar" {lang} />
				</h2>
				{#if calendarLoading}
					<span class="text-xs text-muted-foreground">Loading…</span>
				{:else}
					<span class="text-xs text-muted-foreground"
						>{calendarData.minDate} → {calendarData.maxDate}</span
					>
				{/if}
			</div>
			{#if calendarLoading}
				<div class="h-20 animate-pulse rounded bg-muted/20"></div>
			{:else if calendarData.weeks.length > 0}
				<div class="overflow-x-auto">
					<div class="flex min-w-max gap-0.5">
						{#each calendarData.weeks as week, _i (_i)}
							<div class="flex flex-col gap-0.5">
								{#each week as day, _i (_i)}
									<div
										class="h-3 w-3 rounded-sm {cellColor(day.profit, calendarData.maxAbs)}"
										title="{day.date}: {day.profit == null
											? 'no trades'
											: (day.profit >= 0 ? '+' : '') + day.profit.toFixed(2) + ' USDT'}"
									></div>
								{/each}
							</div>
						{/each}
					</div>
				</div>
				<div class="mt-2 flex items-center gap-1.5 text-[10px] text-muted-foreground">
					<span>Less</span>
					<div class="h-2.5 w-2.5 rounded-sm bg-muted/20"></div>
					<div class="h-2.5 w-2.5 rounded-sm bg-green-800/50"></div>
					<div class="h-2.5 w-2.5 rounded-sm bg-green-600/70"></div>
					<div class="h-2.5 w-2.5 rounded-sm bg-green-500"></div>
					<span>More profit</span>
					<span class="mx-2">|</span>
					<div class="h-2.5 w-2.5 rounded-sm bg-red-900/50"></div>
					<div class="h-2.5 w-2.5 rounded-sm bg-red-600/70"></div>
					<div class="h-2.5 w-2.5 rounded-sm bg-red-500"></div>
					<span>Loss</span>
				</div>
			{/if}
		</section>
	{/if}

	{#if drawdownEpisodes && drawdownEpisodes.length > 0}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Top Drawdown Episodes <span class="ml-1 text-xs font-normal text-muted-foreground"
					>(best run · worst {drawdownEpisodes.length})</span
				>
				<ChartInfo metric="maxDrawdown" {lang} />
			</h2>
			<div class="space-y-2">
				{#each drawdownEpisodes as ep, i (i)}
					{@const depthPct = ep.peakEq > 0 ? (ep.depth / ep.peakEq) * 100 : 0}
					{@const daysDown = Math.round(
						(new Date(ep.troughDate).getTime() - new Date(ep.peakDate).getTime()) / 86400000
					)}
					<div
						class="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-border bg-muted/10 px-3 py-2 text-xs"
					>
						<span class="w-4 font-mono text-muted-foreground">#{i + 1}</span>
						<span class="w-16 font-mono font-semibold text-red-400">−{depthPct.toFixed(1)}%</span>
						<span class="text-muted-foreground"
							>{ep.peakDate.slice(0, 10)} → {ep.troughDate.slice(0, 10)}</span
						>
						<span class="text-muted-foreground">{daysDown}d down</span>
						<span class="text-muted-foreground">−{ep.depth.toFixed(0)} USDT</span>
						{#if ep.recoveryDate}
							{@const daysRecover = Math.round(
								(new Date(ep.recoveryDate).getTime() - new Date(ep.troughDate).getTime()) / 86400000
							)}
							<span class="ml-auto text-green-400/70">recovered in {daysRecover}d</span>
						{:else}
							<span class="ml-auto text-amber-400/80">ongoing ↓</span>
						{/if}
					</div>
				{/each}
			</div>
		</section>
	{/if}

	{#if profitHistogram}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Profit Distribution <span class="ml-1 text-xs font-normal text-muted-foreground"
						>(per-trade profit%)</span
					>
					<ChartInfo metric="distribution" {lang} />
				</h2>
				<div class="flex gap-4 font-mono text-[10px] text-muted-foreground">
					<span
						>mean <span
							class:text-green-400={profitHistogram.mean > 0}
							class:text-red-400={profitHistogram.mean < 0}
							>{profitHistogram.mean >= 0 ? '+' : ''}{profitHistogram.mean.toFixed(2)}%</span
						></span
					>
					<span
						>median <span
							class:text-green-400={profitHistogram.median > 0}
							class:text-red-400={profitHistogram.median < 0}
							>{profitHistogram.median >= 0 ? '+' : ''}{profitHistogram.median.toFixed(2)}%</span
						></span
					>
				</div>
			</div>
			<div class="flex h-20 items-end gap-0.5">
				{#each profitHistogram.bins as b, _i (_i)}
					{@const heightPct = (b.count / profitHistogram.maxCount) * 100}
					{@const isProfit = b.lo + (b.hi - b.lo) / 2 > 0}
					<div
						class="flex-1 rounded-t-sm transition-all {isProfit
							? 'bg-green-500/60 hover:bg-green-500/80'
							: 'bg-red-500/60 hover:bg-red-500/80'}"
						style="height:{heightPct}%"
						title="{b.lo.toFixed(1)}% to {b.hi.toFixed(1)}%: {b.count} trades"
					></div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{profitHistogram.mn.toFixed(1)}%</span>
				<span>0%</span>
				<span>{profitHistogram.mx.toFixed(1)}%</span>
			</div>
		</section>
	{/if}

	{#if tradeStrip}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Trade P&amp;L Strip <span class="ml-1 text-xs font-normal text-muted-foreground"
					>(last {tradeStrip.length} trades · block size ∝ |profit%|)</span
				>
				<ChartInfo metric="tradeCount" {lang} />
			</h2>
			<div class="flex h-10 w-full items-end gap-px overflow-hidden rounded-sm">
				{#each tradeStrip as t, _i (_i)}
					<div
						class="rounded-t-[1px]"
						style="flex:{t.size}; height:{Math.max(
							20,
							Math.round(t.size * 36)
						)}px; background:{t.pct >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}"
						title="{t.pair} · {t.close} · {t.pct >= 0 ? '+' : ''}{t.pct.toFixed(2)}%"
					></div>
				{/each}
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Chronological left→right · green = win, red = loss · wider/taller = larger magnitude · hover
				for detail
			</p>
		</section>
	{/if}

	{#if rollingWR}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Rolling Win-Rate <span class="ml-1 text-xs font-normal text-muted-foreground"
						>(20-trade window · {rollingWR.firstDate} → {rollingWR.lastDate})</span
					>
					<ChartInfo metric="rollingWinRate" {lang} />
				</h2>
				<div class="flex items-center gap-3 text-[11px]">
					<span class="text-muted-foreground"
						>latest <span
							class:text-green-400={rollingWR.latestWr >= 0.5}
							class:text-red-400={rollingWR.latestWr < 0.5}
							class="font-mono font-semibold">{(rollingWR.latestWr * 100).toFixed(0)}%</span
						></span
					>
					<span class="text-muted-foreground"
						>avg <span class="font-mono text-foreground">{(rollingWR.avgWr * 100).toFixed(0)}%</span
						></span
					>
				</div>
			</div>
			<svg viewBox="0 0 {rollingWR.W} {rollingWR.H}" class="w-full" style="height:60px">
				<!-- 50% reference line -->
				{#if rollingWR.fiftyY >= rollingWR.PAD && rollingWR.fiftyY <= rollingWR.H - rollingWR.PAD}
					<line
						x1={rollingWR.PAD}
						y1={rollingWR.fiftyY}
						x2={rollingWR.W - rollingWR.PAD}
						y2={rollingWR.fiftyY}
						stroke="var(--ch-rule-strong)"
						stroke-width="1"
						stroke-dasharray="4 3"
					/>
					<text
						x={rollingWR.W - rollingWR.PAD - 2}
						y={rollingWR.fiftyY - 2}
						text-anchor="end"
						font-size="8"
						fill="var(--ch-rule-strong)">50%</text
					>
				{/if}
				<!-- avg line -->
				<line
					x1={rollingWR.PAD}
					y1={rollingWR.avgY}
					x2={rollingWR.W - rollingWR.PAD}
					y2={rollingWR.avgY}
					stroke="var(--ch-warn-light)"
					stroke-width="1"
					stroke-dasharray="3 3"
				/>
				<!-- Gradient fill area under line -->
				<defs>
					<linearGradient id="wrGrad" x1="0" y1="0" x2="0" y2="1">
						<stop offset="0%" stop-color="var(--ch-profit-light)" />
						<stop offset="100%" stop-color="var(--ch-profit-light)" />
					</linearGradient>
				</defs>
				<polygon
					points="{rollingWR.PAD},{rollingWR.H - rollingWR.PAD} {rollingWR.poly} {rollingWR.W -
						rollingWR.PAD},{rollingWR.H - rollingWR.PAD}"
					fill="url(#wrGrad)"
				/>
				<polyline
					points={rollingWR.poly}
					fill="none"
					stroke="var(--ch-profit-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground">
				<span>{(rollingWR.mn * 100).toFixed(0)}% min</span>
				<span>{(rollingWR.mx * 100).toFixed(0)}% max</span>
			</div>
		</section>
	{/if}

	{#if rollingPF}
		{@const rpf = rollingPF}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Rolling Profit Factor <span class="ml-1 text-xs font-normal text-muted-foreground"
					>(20-trade window · {rpf.total} points · avg {rpf.avg.toFixed(2)})</span
				>
				<ChartInfo metric="profitFactor" {lang} />
			</h2>
			<svg viewBox="0 0 {rpf.W} {rpf.H}" class="w-full" style="height:{rpf.H}px;min-width:240px">
				<!-- break-even line at PF=1 -->
				{#if rpf.oneY >= rpf.PAD && rpf.oneY <= rpf.H - rpf.PAD}
					<line
						x1={rpf.PAD}
						y1={rpf.oneY}
						x2={rpf.W - rpf.PAD}
						y2={rpf.oneY}
						stroke="var(--ch-rule-strong)"
						stroke-width="1"
						stroke-dasharray="4 3"
					/>
					<text x={rpf.PAD + 2} y={rpf.oneY - 3} font-size="7" fill="var(--ch-rule-strong)"
						>PF=1</text
					>
				{/if}
				<!-- fill above/below 1 -->
				<polygon
					points="{rpf.PAD},{rpf.oneY} {rpf.polyline} {rpf.W - rpf.PAD},{rpf.oneY}"
					fill={rpf.avg >= 1 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)'}
				/>
				<polyline
					points={rpf.polyline}
					fill="none"
					stroke={rpf.avg >= 1.5 ? '#34d399' : rpf.avg >= 1 ? '#facc15' : '#f87171'}
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={rpf.W - rpf.PAD}
					y="10"
					font-size="7"
					fill="var(--ch-rule-strong)"
					text-anchor="end">max {rpf.pfMax.toFixed(1)}</text
				>
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				PF = gross wins / gross losses (20-trade window) · above 1 = edge positive · green ≥1.5 ·
				amber 1-1.5 · red &lt;1
			</p>
		</section>
	{/if}

	{#if streakStats}
		{@const ss = streakStats}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Streak Analysis <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({ss.total} trades)</span
				>
				<ChartInfo metric="streak" {lang} />
			</h2>
			<div class="grid grid-cols-3 gap-3 text-center text-xs">
				<div class="rounded-lg border bg-secondary/40 p-3">
					<div class="text-[10px] text-muted-foreground uppercase">Max Win Streak</div>
					<div class="mt-1 font-mono text-2xl font-bold text-green-400">{ss.maxWin}</div>
					<div class="text-[10px] text-muted-foreground">consecutive wins</div>
				</div>
				<div class="rounded-lg border bg-secondary/40 p-3">
					<div class="text-[10px] text-muted-foreground uppercase">Current Streak</div>
					<div
						class="mt-1 font-mono text-2xl font-bold {ss.isWinStreak
							? 'text-green-400'
							: 'text-red-400'}"
					>
						{ss.currentStreak}
					</div>
					<div class="text-[10px] {ss.isWinStreak ? 'text-green-400' : 'text-red-400'}">
						{ss.isWinStreak ? 'win' : 'loss'} streak
					</div>
				</div>
				<div class="rounded-lg border bg-secondary/40 p-3">
					<div class="text-[10px] text-muted-foreground uppercase">Max Loss Streak</div>
					<div class="mt-1 font-mono text-2xl font-bold text-red-400">{ss.maxLoss}</div>
					<div class="text-[10px] text-muted-foreground">consecutive losses</div>
				</div>
			</div>
		</section>
	{/if}

	{#if expectancy}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<div class="mb-4 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Expectancy Breakdown <span class="ml-1 text-xs font-normal text-muted-foreground"
						>({expectancy.n} trades)</span
					>
					<ChartInfo metric="expectancy" {lang} />
				</h2>
				<span
					class="font-mono text-sm font-bold {expectancy.expectancyVal > 0
						? 'text-green-400'
						: 'text-red-400'}"
				>
					E = {expectancy.expectancyVal >= 0 ? '+' : ''}{expectancy.expectancyVal.toFixed(2)}%
				</span>
			</div>
			<div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
				<div class="rounded-lg bg-secondary/40 px-4 py-3">
					<div class="text-[10px] text-muted-foreground uppercase">Win Rate</div>
					<div
						class="mt-1 font-mono text-xl font-bold {expectancy.wr >= 0.5
							? 'text-green-400'
							: 'text-red-400'}"
					>
						{(expectancy.wr * 100).toFixed(1)}%
					</div>
					<div class="text-[10px] text-muted-foreground">
						{expectancy.wins}W / {expectancy.losses}L
					</div>
				</div>
				<div class="rounded-lg bg-secondary/40 px-4 py-3">
					<div class="text-[10px] text-muted-foreground uppercase">Avg Win</div>
					<div class="mt-1 font-mono text-xl font-bold text-green-400">
						+{expectancy.avgWin.toFixed(2)}%
					</div>
					<div class="text-[10px] text-muted-foreground">per winning trade</div>
				</div>
				<div class="rounded-lg bg-secondary/40 px-4 py-3">
					<div class="text-[10px] text-muted-foreground uppercase">Avg Loss</div>
					<div class="mt-1 font-mono text-xl font-bold text-red-400">
						−{expectancy.avgLoss.toFixed(2)}%
					</div>
					<div class="text-[10px] text-muted-foreground">per losing trade</div>
				</div>
				<div class="rounded-lg bg-secondary/40 px-4 py-3">
					<div class="text-[10px] text-muted-foreground uppercase">Payoff Ratio</div>
					<div
						class="mt-1 font-mono text-xl font-bold {(expectancy.payoffRatio ?? 0) >= 1
							? 'text-green-400'
							: 'text-yellow-400'}"
					>
						{expectancy.payoffRatio != null ? expectancy.payoffRatio.toFixed(2) : '—'}×
					</div>
					<div class="text-[10px] text-muted-foreground">win / loss size</div>
				</div>
			</div>
			<div class="mt-3 rounded bg-secondary/30 px-4 py-2 font-mono text-xs text-muted-foreground">
				E = WR × Avg Win − (1 − WR) × Avg Loss = {(expectancy.wr * 100).toFixed(1)}% × {expectancy.avgWin.toFixed(
					2
				)} − {((1 - expectancy.wr) * 100).toFixed(1)}% × {expectancy.avgLoss.toFixed(2)} =
				<span
					class="{expectancy.expectancyVal > 0 ? 'text-green-400' : 'text-red-400'} font-semibold"
					>{expectancy.expectancyVal >= 0 ? '+' : ''}{expectancy.expectancyVal.toFixed(3)}%</span
				>
			</div>
		</section>
	{/if}

	{#if monthlyPnl}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Monthly P&L Calendar <span class="ml-1 text-xs font-normal text-muted-foreground"
						>({monthlyPnl.winMonths}/{monthlyPnl.total_months} green months)</span
					>
					<ChartInfo metric="calendar" {lang} />
				</h2>
				<span class="font-mono text-xs {monthlyPnl.total >= 0 ? 'text-green-400' : 'text-red-400'}"
					>{monthlyPnl.total >= 0 ? '+' : ''}{monthlyPnl.total.toFixed(0)} USDT total</span
				>
			</div>
			<div class="overflow-x-auto">
				<table class="w-full min-w-[480px] text-[10px]">
					<thead>
						<tr>
							<th class="pr-2 text-right font-normal text-muted-foreground">Year</th>
							{#each monthlyPnl.MONTHS as m, _i (_i)}
								<th class="w-9 text-center font-normal text-muted-foreground">{m}</th>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each monthlyPnl.grid as row, yi (yi)}
							<tr>
								<td class="pr-2 text-right font-mono text-muted-foreground"
									>{monthlyPnl.years[yi]}</td
								>
								{#each row as cell, _i (_i)}
									<td class="p-0.5">
										{#if cell.v != null}
											{@const alpha = Math.min(0.9, 0.15 + Math.abs(cell.pct) * 0.75)}
											<div
												class="flex h-7 w-full items-center justify-center rounded font-mono text-[9px] leading-none font-semibold"
												style="background:rgba({cell.v >= 0
													? '34,197,94'
													: '248,113,113'},{alpha});color:{cell.v >= 0 ? '#86efac' : '#fca5a5'}"
												title="{cell.key}: {cell.v >= 0 ? '+' : ''}{cell.v.toFixed(0)} USDT"
											>
												{cell.v >= 0 ? '+' : ''}{Math.abs(cell.v) >= 1000
													? (cell.v / 1000).toFixed(1) + 'k'
													: cell.v.toFixed(0)}
											</div>
										{:else}
											<div class="h-7 w-full rounded bg-muted/20"></div>
										{/if}
									</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{/if}

	{#if extremeTrades}
		{@const et = extremeTrades}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Best & Worst Trades <span class="ml-1 text-xs font-normal text-muted-foreground"
					>(by absolute P&L · best run)</span
				>
				<ChartInfo metric="totalProfit" {lang} />
			</h2>
			<div class="grid gap-4 sm:grid-cols-2">
				<div>
					<p class="mb-2 text-[11px] font-semibold tracking-wider text-green-400 uppercase">
						Top 3 Wins
					</p>
					<div class="space-y-1.5">
						{#each et.best as t, _i (_i)}
							<div
								class="flex items-center justify-between rounded border border-green-800/30 bg-green-950/15 px-3 py-2 font-mono text-xs"
							>
								<span class="truncate font-semibold text-foreground">{t.pair}</span>
								<span class="ml-2 shrink-0 text-[10px] text-muted-foreground"
									>{t.trade_duration_min != null
										? t.trade_duration_min < 60
											? t.trade_duration_min + 'm'
											: (t.trade_duration_min / 60).toFixed(0) + 'h'
										: '—'}</span
								>
								<span class="ml-2 shrink-0 font-semibold text-green-400"
									>+{t.profit_abs!.toFixed(2)}</span
								>
								<span class="ml-1.5 shrink-0 text-[10px] text-green-300"
									>{t.profit_pct != null ? '+' + t.profit_pct.toFixed(2) + '%' : ''}</span
								>
							</div>
						{/each}
					</div>
				</div>
				<div>
					<p class="mb-2 text-[11px] font-semibold tracking-wider text-red-400 uppercase">
						Top 3 Losses
					</p>
					<div class="space-y-1.5">
						{#each et.worst as t, _i (_i)}
							<div
								class="flex items-center justify-between rounded border border-red-800/30 bg-red-950/15 px-3 py-2 font-mono text-xs"
							>
								<span class="truncate font-semibold text-foreground">{t.pair}</span>
								<span class="ml-2 shrink-0 text-[10px] text-muted-foreground"
									>{t.trade_duration_min != null
										? t.trade_duration_min < 60
											? t.trade_duration_min + 'm'
											: (t.trade_duration_min / 60).toFixed(0) + 'h'
										: '—'}</span
								>
								<span class="ml-2 shrink-0 font-semibold text-red-400"
									>{t.profit_abs!.toFixed(2)}</span
								>
								<span class="ml-1.5 shrink-0 text-[10px] text-red-300"
									>{t.profit_pct != null ? t.profit_pct.toFixed(2) + '%' : ''}</span
								>
							</div>
						{/each}
					</div>
				</div>
			</div>
		</section>
	{/if}

	{#if durationHistogram}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<h2 class="mb-4 text-sm font-semibold">
				Hold Duration Distribution <span class="ml-1 text-xs font-normal text-muted-foreground"
					>(best run · {calendarTrades.length} trades)</span
				>
				<ChartInfo metric="distribution" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each durationHistogram as b, _i (_i)}
					{#if b.count > 0}
						<div class="flex items-center gap-2 text-xs">
							<span class="w-12 shrink-0 text-right font-mono text-muted-foreground">{b.label}</span
							>
							<div class="relative h-5 flex-1 rounded-sm bg-muted/20">
								<div
									class="absolute inset-y-0 left-0 rounded-sm"
									style="width:{(b.pct * 100).toFixed(1)}%; background: hsl({Math.round(
										b.wr * 120
									)}, 60%, 40%)"
								></div>
								<span
									class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px] text-foreground"
									>{b.count} trades</span
								>
							</div>
							<span
								class="w-12 shrink-0 font-mono text-[10px]"
								class:text-green-400={b.wr >= 0.5}
								class:text-red-400={b.wr < 0.5}>{(b.wr * 100).toFixed(0)}% WR</span
							>
						</div>
					{/if}
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Bar width = relative count · Bar color: green = high WR, red = low WR
			</p>
		</section>
	{/if}

	{#if entryHourChart}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<h2 class="mb-4 text-sm font-semibold">
				Trade Entry Hour (UTC) <span class="ml-1 text-xs font-normal text-muted-foreground"
					>(when strategy enters trades · {calendarTrades.length} trades)</span
				>
				<ChartInfo metric="holdingTime" {lang} />
			</h2>
			<div class="flex items-end gap-px">
				{#each entryHourChart as h, _i (_i)}
					<div
						class="flex flex-1 flex-col items-center gap-0.5"
						title="Hour {h.h}:00 UTC: {h.count} entries · WR {h.count > 0
							? (h.wr * 100).toFixed(0)
							: 0}%"
					>
						<div
							class="w-full rounded-t-sm"
							style="height:{Math.max(1, Math.round(h.barPct * 0.6))}px; background:{h.count === 0
								? 'var(--ch-axis-faint)'
								: h.wr >= 0.55
									? 'var(--ch-profit)'
									: h.wr >= 0.45
										? 'var(--ch-warn-light)'
										: 'var(--ch-loss-light)'}"
						></div>
						{#if h.h % 6 === 0}
							<span class="font-mono text-[8px] text-muted-foreground">{h.h}h</span>
						{/if}
					</div>
				{/each}
			</div>
			<div class="mt-2 flex gap-4 text-[10px] text-muted-foreground">
				<span class="flex items-center gap-1"
					><span class="inline-block h-2 w-2 rounded-sm bg-green-500/60"></span>WR≥55%</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-2 w-2 rounded-sm bg-yellow-400/55"></span>45-55%</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-2 w-2 rounded-sm bg-red-500/55"></span>&lt;45%</span
				>
				<span class="ml-auto font-mono">Asia 0-8 · EU 8-16 · US 14-22</span>
			</div>
		</section>
	{/if}

	{#if profitByDuration && profitByDuration.length > 1}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<h2 class="mb-4 text-sm font-semibold">
				Profit by Hold Duration <span class="ml-1 text-xs font-normal text-muted-foreground"
					>(best run · {calendarTrades.length} trades)</span
				>
				<ChartInfo metric="holdingTime" {lang} />
			</h2>
			<div class="flex gap-3">
				{#each profitByDuration as tier, _i (_i)}
					<div
						class="flex flex-1 flex-col items-center gap-1 rounded-lg border bg-secondary/20 p-3"
					>
						<span
							class="text-center font-mono text-[9px] leading-tight whitespace-pre-line text-muted-foreground"
							>{tier.label}</span
						>
						<span
							class="font-mono text-base font-bold {tier.wr >= 0.5
								? 'text-green-400'
								: 'text-red-400'}">{(tier.wr * 100).toFixed(0)}%</span
						>
						<span class="font-mono text-[9px] text-muted-foreground">WR</span>
						<span class="font-mono text-[10px] {tier.positive ? 'text-green-400' : 'text-red-400'}"
							>{tier.totalProfit >= 0 ? '+' : ''}{tier.totalProfit.toFixed(0)}</span
						>
						<span class="font-mono text-[9px] text-muted-foreground">{tier.count} trades</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				WR = individual trade win rate · profit = cumulative USDT for that tier
			</p>
		</section>
	{/if}

	{#if dowPnl}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<h2 class="mb-4 text-sm font-semibold">
				Day-of-Week P&amp;L <span class="ml-1 text-xs font-normal text-muted-foreground"
					>(cumulative profit per weekday · best run)</span
				>
				<ChartInfo metric="totalProfit" {lang} />
			</h2>
			<div class="flex gap-2">
				{#each dowPnl as d, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-1">
						<span class="font-mono text-[9px] text-muted-foreground"
							>{d.count > 0 ? (d.sum >= 0 ? '+' : '') + d.sum.toFixed(0) : '—'}</span
						>
						<div class="relative w-full" style="height:64px">
							{#if d.count > 0}
								{@const h = Math.round(d.barPct * 0.56)}
								<div
									class="absolute right-0 bottom-0 left-0 rounded-t-sm"
									style="height:{h}px; background:{d.positive
										? 'var(--ch-profit-light)'
										: 'var(--ch-loss-light)'}"
								></div>
							{/if}
						</div>
						<span class="font-mono text-[10px] font-semibold">{d.label}</span>
						{#if d.count > 0}
							<span
								class="font-mono text-[9px]"
								class:text-green-400={d.wr >= 0.5}
								class:text-red-400={d.wr < 0.5}>{(d.wr * 100).toFixed(0)}%</span
							>
						{/if}
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Bar height = relative P&amp;L magnitude · green = net positive day · % = win rate
			</p>
		</section>
	{/if}

	{#if exitReasons}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<h2 class="mb-4 text-sm font-semibold">
				Exit Reason Breakdown <span class="ml-1 text-xs font-normal text-muted-foreground"
					>(best run)</span
				>
				<ChartInfo metric="exitReason" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each exitReasons as r, _i (_i)}
					<div class="flex items-center gap-2 text-xs">
						<span class="w-32 shrink-0 truncate font-mono text-muted-foreground" title={r.reason}
							>{r.reason}</span
						>
						<div class="relative h-5 flex-1 rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm transition-all"
								style="width:{r.barPct.toFixed(1)}%; background: hsl({Math.round(
									r.wr * 120
								)},55%,38%)"
							></div>
							<span
								class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px] text-foreground"
								>{r.count}×</span
							>
						</div>
						<span
							class="w-16 shrink-0 text-right font-mono text-[10px]"
							class:text-green-400={r.totalProfit > 0}
							class:text-red-400={r.totalProfit < 0}
							>{r.totalProfit >= 0 ? '+' : ''}{r.totalProfit.toFixed(0)} USDT</span
						>
						<span
							class="w-12 shrink-0 text-right font-mono text-[10px]"
							class:text-green-400={r.wr >= 0.5}
							class:text-red-400={r.wr < 0.5}>{(r.wr * 100).toFixed(0)}%WR</span
						>
					</div>
				{/each}
			</div>
		</section>
	{/if}

	{#if pairStats && pairStats.length > 1}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Pair Contribution <span class="ml-1 text-xs font-normal text-muted-foreground"
					>(best run · {pairStats.length} pairs)</span
				>
				<ChartInfo metric="leaderboard" {lang} />
			</h2>
			<div class="overflow-x-auto">
				<table class="w-full text-xs">
					<thead class="text-[10px] text-muted-foreground uppercase">
						<tr>
							<th class="pb-2 text-left">Pair</th>
							<th class="pb-2 text-right">Trades</th>
							<th class="pb-2 text-right">Win%</th>
							<th class="pb-2 text-right">Total USDT</th>
							<th class="pb-2 pl-3">Contribution</th>
						</tr>
					</thead>
					<tbody class="font-mono">
						{#each pairStats as p (p.pair)}
							{@const maxAbs = Math.max(1, ...pairStats.map((x) => Math.abs(x.profit)))}
							{@const barW = ((Math.abs(p.profit) / maxAbs) * 100).toFixed(1)}
							<tr class="border-t border-border">
								<td class="py-1.5 pr-3 font-semibold text-foreground">{p.pair}</td>
								<td class="py-1.5 text-right text-muted-foreground">{p.count}</td>
								<td
									class="py-1.5 text-right"
									class:text-green-400={p.wr >= 0.5}
									class:text-red-400={p.wr < 0.5}>{(p.wr * 100).toFixed(0)}%</td
								>
								<td
									class="py-1.5 text-right"
									class:text-green-400={p.profit > 0}
									class:text-red-400={p.profit < 0}
									>{p.profit >= 0 ? '+' : ''}{p.profit.toFixed(0)}</td
								>
								<td class="py-1.5 pl-3">
									<div class="relative h-3 w-32 rounded-sm bg-muted/20">
										<div
											class="absolute inset-y-0 rounded-sm {p.profit >= 0
												? 'left-0 bg-green-500/50'
												: 'right-0 bg-red-500/50'}"
											style="width:{barW}%"
										></div>
									</div>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{/if}

	{#if enterTagStats && enterTagStats.length > 1}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Entry Signal Performance <span class="ml-1 text-xs font-normal text-muted-foreground"
					>(best run · by enter_tag)</span
				>
				<ChartInfo metric="enterTag" {lang} />
			</h2>
			<div class="overflow-x-auto">
				<table class="w-full text-xs">
					<thead class="text-[10px] text-muted-foreground uppercase">
						<tr>
							<th class="pb-2 text-left">Tag</th>
							<th class="pb-2 text-right">Count</th>
							<th class="pb-2 text-right">Win%</th>
							<th class="pb-2 text-right">Avg%</th>
							<th class="pb-2 text-right">Total USDT</th>
						</tr>
					</thead>
					<tbody class="font-mono">
						{#each enterTagStats as e (e.tag)}
							<tr class="border-t border-border hover:bg-accent/30">
								<td class="py-1.5 pr-3 font-semibold text-foreground">{e.tag}</td>
								<td class="py-1.5 text-right text-muted-foreground">{e.count}</td>
								<td
									class="py-1.5 text-right"
									class:text-green-400={e.wr >= 0.5}
									class:text-red-400={e.wr < 0.5}>{(e.wr * 100).toFixed(0)}%</td
								>
								<td
									class="py-1.5 text-right"
									class:text-green-400={e.avgPct > 0}
									class:text-red-400={e.avgPct < 0}
									>{e.avgPct >= 0 ? '+' : ''}{e.avgPct.toFixed(2)}%</td
								>
								<td
									class="py-1.5 text-right"
									class:text-green-400={e.profit > 0}
									class:text-red-400={e.profit < 0}
									>{e.profit >= 0 ? '+' : ''}{e.profit.toFixed(0)}</td
								>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{/if}

	{#if enterTagProfitShare && enterTagProfitShare.rows.length >= 2}
		{@const etps = enterTagProfitShare}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Enter-Tag Profit Contribution <span class="ml-1 text-xs font-normal text-muted-foreground"
						>(best run)</span
					>
					<ChartInfo metric="enterTag" {lang} />
				</h2>
				<span class="font-mono text-xs {etps.totalProfit >= 0 ? 'text-green-400' : 'text-red-400'}"
					>{etps.totalProfit >= 0 ? '+' : ''}{etps.totalProfit.toFixed(0)} USDT total</span
				>
			</div>
			<div class="space-y-1.5">
				{#each etps.rows as row, _i (_i)}
					{@const sharePct = (Math.abs(row.profit) / etps.totalAbs) * 100}
					<div class="flex items-center gap-2 text-xs">
						<span class="w-28 shrink-0 truncate font-mono" title={row.tag}>{row.tag}</span>
						<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm"
								style="width:{sharePct.toFixed(1)}%; background:{row.profit >= 0
									? 'var(--ch-profit-light)'
									: 'var(--ch-loss-light)'}"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]"
								>{sharePct.toFixed(0)}% share</span
							>
						</div>
						<span
							class="w-20 shrink-0 text-right font-mono text-[10px] {row.profit >= 0
								? 'text-green-400'
								: 'text-red-400'}">{row.profit >= 0 ? '+' : ''}{row.profit.toFixed(0)}</span
						>
						<span
							class="w-10 shrink-0 text-right font-mono text-[10px] {row.wr >= 0.5
								? 'text-green-400'
								: 'text-red-400'}">{(row.wr * 100).toFixed(0)}%WR</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Bar width = share of gross profit · USDT = cumulative profit for that tag
			</p>
		</section>
	{/if}

	{#if monteCarloData}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Monte Carlo <span class="ml-1 text-xs font-normal text-muted-foreground"
						>({N_SIMS} simulations · p5/p50/p95 bands)</span
					>
					<ChartInfo metric="monteCarlo" {lang} />
				</h2>
				<div class="flex items-center gap-3 font-mono text-xs">
					<span class="text-muted-foreground"
						>p5 <span
							class:text-green-400={monteCarloData.p5final > 1}
							class:text-red-400={monteCarloData.p5final <= 1}
							>{((monteCarloData.p5final - 1) * 100).toFixed(1)}%</span
						></span
					>
					<span class="text-muted-foreground"
						>p50 <span
							class:text-green-400={monteCarloData.finalP50 > 1}
							class:text-red-400={monteCarloData.finalP50 <= 1}
							>{((monteCarloData.finalP50 - 1) * 100).toFixed(1)}%</span
						></span
					>
					<span class="text-muted-foreground"
						>p95 <span class="text-green-400"
							>{((monteCarloData.p95final - 1) * 100).toFixed(1)}%</span
						></span
					>
					<span class="text-amber-400">obs {((monteCarloData.finalObs - 1) * 100).toFixed(1)}%</span
					>
				</div>
			</div>
			<div class="overflow-x-auto">
				<svg
					viewBox="0 0 {monteCarloData.W} {monteCarloData.H}"
					class="w-full"
					style="height:{monteCarloData.H}px; min-width:300px"
				>
					<!-- Band p5-p95 -->
					<polygon points={monteCarloData.bandPath} fill="var(--ch-violet-light)" />
					<!-- Baseline (breakeven) -->
					<line
						x1="0"
						y1={monteCarloData.zeroY}
						x2={monteCarloData.W}
						y2={monteCarloData.zeroY}
						stroke="var(--ch-rule)"
						stroke-width="1"
						stroke-dasharray="4 3"
					/>
					<!-- p50 median -->
					<polyline
						points={monteCarloData.p50line}
						fill="none"
						stroke="rgba(129,140,248,0.7)"
						stroke-width="1.5"
					/>
					<!-- Observed actual -->
					<polyline
						points={monteCarloData.obsline}
						fill="none"
						stroke="rgb(251,191,36)"
						stroke-width="2"
					/>
				</svg>
			</div>
			<div class="mt-2 flex items-center gap-4 text-[10px] text-muted-foreground">
				<span class="flex items-center gap-1"
					><span class="inline-block h-2 w-4 rounded" style="background:var(--ch-violet-light)"
					></span>p5–p95 band</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-0.5 w-4 rounded bg-indigo-400"></span>median (p50)</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-0.5 w-4 rounded bg-amber-400"></span>observed</span
				>
				<span class="ml-auto">Bootstraps {monteCarloData.steps - 1} trades × {N_SIMS} draws</span>
			</div>
		</section>
	{/if}

	{#if runRiskScatter}
		{@const rs = runRiskScatter}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<div class="mb-2 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Run Risk-Adjusted Scatter <span class="ml-1 text-xs font-normal text-muted-foreground"
						>({runs.length} runs · Sharpe × Calmar)</span
					>
					<ChartInfo metric="scatter" {lang} />
				</h2>
				<div class="flex gap-2 text-[10px] text-muted-foreground">
					<span
						><span class="mr-1 inline-block h-2 w-2 rounded-full bg-green-400"></span>high profit</span
					>
					<span><span class="mr-1 inline-block h-2 w-2 rounded-full bg-yellow-400"></span>mid</span>
					<span><span class="mr-1 inline-block h-2 w-2 rounded-full bg-red-400"></span>low</span>
				</div>
			</div>
			<div class="overflow-x-auto">
				<svg viewBox="0 0 {rs.W} {rs.H}" class="w-full" style="height:140px;min-width:240px">
					<!-- Grid lines -->
					{#each [0.25, 0.5, 0.75, 1] as f, _i (_i)}
						{@const gx = rs.PL + f * (rs.W - rs.PL - rs.PR)}
						{@const gy = rs.PT + (1 - f) * (rs.H - rs.PT - rs.PB)}
						<line
							x1={gx}
							y1={rs.PT}
							x2={gx}
							y2={rs.H - rs.PB}
							stroke="var(--ch-rule-faint)"
							stroke-width="1"
						/>
						<text x={gx} y={rs.H} text-anchor="middle" font-size="7" fill="var(--ch-rule-strong)"
							>{(rs.xMin + f * (rs.xMax - rs.xMin)).toFixed(1)}</text
						>
						<line
							x1={rs.PL}
							y1={gy}
							x2={rs.W - rs.PR}
							y2={gy}
							stroke="var(--ch-rule-faint)"
							stroke-width="1"
						/>
						<text
							x={rs.PL - 3}
							y={gy + 3}
							text-anchor="end"
							font-size="7"
							fill="var(--ch-rule-strong)">{(rs.yMin + f * (rs.yMax - rs.yMin)).toFixed(1)}</text
						>
					{/each}
					<!-- Axis labels -->
					<text
						x={(rs.PL + rs.W - rs.PR) / 2}
						y={rs.H}
						text-anchor="middle"
						font-size="8"
						fill="var(--ch-rule-strong)">Sharpe →</text
					>
					<!-- Dots -->
					{#each rs.dots as d, _i (_i)}
						<circle
							cx={d.cx.toFixed(1)}
							cy={d.cy.toFixed(1)}
							r={d.isBest ? 5 : 3}
							fill={d.color}
							fill-opacity={d.isBest ? 1 : 0.65}
							stroke={d.isBest ? '#fff' : 'none'}
							stroke-width="1"
						>
							<title>{d.tip}</title>
						</circle>
					{/each}
				</svg>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Upper-right = best · white ring = best run · color = profit tier (green top-third)
			</p>
		</section>
	{/if}

	{#if tradeScatter}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Duration vs Profit Scatter <span class="ml-1 text-xs font-normal text-muted-foreground"
						>({calendarTrades.length} trades · log x-axis)</span
					>
					<ChartInfo metric="scatter" {lang} />
				</h2>
				<div class="flex gap-3 text-[10px] text-muted-foreground">
					<span><span class="mr-1 inline-block h-2 w-2 rounded-full bg-green-500"></span>Win</span>
					<span><span class="mr-1 inline-block h-2 w-2 rounded-full bg-red-500"></span>Loss</span>
				</div>
			</div>
			<div class="overflow-x-auto">
				<svg
					viewBox="0 0 {tradeScatter.W} {tradeScatter.H}"
					class="w-full"
					style="height:120px;min-width:300px"
				>
					<!-- Zero line -->
					<line
						x1={tradeScatter.PAD}
						y1={tradeScatter.zeroY}
						x2={tradeScatter.W - tradeScatter.PAD}
						y2={tradeScatter.zeroY}
						stroke="var(--ch-rule-strong)"
						stroke-width="1"
						stroke-dasharray="4 3"
					/>
					<!-- Duration grid lines -->
					{#each tradeScatter.gridDurations as g, _i (_i)}
						<line
							x1={g.x}
							y1={tradeScatter.PAD}
							x2={g.x}
							y2={tradeScatter.H - tradeScatter.PAD}
							stroke="var(--ch-rule-faint)"
							stroke-width="1"
						/>
						<text
							x={g.x}
							y={tradeScatter.H - 1}
							text-anchor="middle"
							font-size="8"
							fill="var(--ch-rule-strong)">{g.label}</text
						>
					{/each}
					<!-- Dots -->
					{#each tradeScatter.dots as d, _i (_i)}
						<circle
							cx={d.x}
							cy={d.y}
							r="2.5"
							fill={d.win ? 'var(--ch-profit)' : 'var(--ch-loss-light)'}
							stroke={d.win ? 'var(--ch-profit-strong)' : 'var(--ch-loss-strong)'}
							stroke-width="0.5"
						>
							<title>{d.tip}</title>
						</circle>
					{/each}
				</svg>
			</div>
		</section>
	{/if}

	{#if equityCurve}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Equity Curve <span class="ml-1 text-xs font-normal text-muted-foreground"
						>(best run · {calendarTrades.length} trades · cumulative USDT P&L)</span
					>
					<ChartInfo metric="calendar" {lang} />
				</h2>
				<div class="flex items-center gap-3 font-mono text-[11px]">
					<span class="text-muted-foreground"
						>peak <span class="text-foreground"
							>{equityCurve.peak >= 0 ? '+' : ''}{equityCurve.peak.toFixed(0)}</span
						></span
					>
					<span class="text-muted-foreground"
						>final <span
							class:text-green-400={equityCurve.final > 0}
							class:text-red-400={equityCurve.final < 0}
							class="font-semibold"
							>{equityCurve.final >= 0 ? '+' : ''}{equityCurve.final.toFixed(0)}</span
						></span
					>
				</div>
			</div>
			<div class="overflow-x-auto">
				<svg
					viewBox="0 0 {equityCurve.W} {equityCurve.H}"
					class="w-full"
					style="height:100px;min-width:280px"
				>
					<defs>
						<linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
							<stop
								offset="0%"
								stop-color={equityCurve.final >= 0
									? 'var(--ch-profit-light)'
									: 'var(--ch-loss-light)'}
							/>
							<stop
								offset="100%"
								stop-color={equityCurve.final >= 0
									? 'var(--ch-profit-light)'
									: 'var(--ch-loss-light)'}
							/>
						</linearGradient>
					</defs>
					<line
						x1={equityCurve.PAD}
						y1={equityCurve.zeroY}
						x2={equityCurve.W - equityCurve.PAD}
						y2={equityCurve.zeroY}
						stroke="var(--ch-rule)"
						stroke-width="1"
						stroke-dasharray="4 3"
					/>
					<polygon points={equityCurve.areaPts} fill="url(#eqGrad)" />
					<polyline
						points={equityCurve.linePts}
						fill="none"
						stroke={equityCurve.final >= 0 ? 'var(--ch-profit-strong)' : 'var(--ch-loss-strong)'}
						stroke-width="1.5"
						stroke-linejoin="round"
					/>
				</svg>
			</div>
			<div class="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground">
				<span>{equityCurve.firstDate}</span>
				<span>{equityCurve.lastDate}</span>
			</div>
		</section>
	{/if}

	{#if underwaterChart}
		{@const uw = underwaterChart}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<div class="mb-2 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Underwater Drawdown <span class="ml-1 text-xs font-normal text-muted-foreground"
						>(% below equity peak)</span
					>
					<ChartInfo metric="maxDrawdown" {lang} />
				</h2>
				<div class="flex gap-4 font-mono text-xs">
					<span class="text-muted-foreground"
						>MaxDD <span class="text-red-400">{uw.maxDD.toFixed(1)}%</span></span
					>
					<span class="text-muted-foreground"
						>AvgDD <span class="text-foreground">{uw.avgDD.toFixed(1)}%</span></span
					>
				</div>
			</div>
			<svg viewBox="0 0 {uw.W} {uw.H}" class="w-full" style="height:60px;min-width:280px">
				<defs>
					<linearGradient id="uwGrad" x1="0" y1="1" x2="0" y2="0">
						<stop offset="0%" stop-color="var(--ch-loss-light)" />
						<stop offset="100%" stop-color="var(--ch-loss-light)" />
					</linearGradient>
				</defs>
				<polygon points={uw.areaPts} fill="url(#uwGrad)" />
				<polyline
					points={uw.linePts}
					fill="none"
					stroke="var(--ch-loss-light)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<line
					x1={uw.PAD}
					y1={uw.PAD}
					x2={uw.W - uw.PAD}
					y2={uw.PAD}
					stroke="var(--ch-rule)"
					stroke-width="0.5"
					stroke-dasharray="4 3"
				/>
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Red depth = % drawdown from running equity peak · flat at top = at all-time high
			</p>
		</section>
	{/if}

	{#if timeHeatmap}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Exit Time Heatmap <span class="ml-1 text-xs font-normal text-muted-foreground"
						>(UTC hour × weekday · avg profit%)</span
					>
					<ChartInfo metric="exitReason" {lang} />
				</h2>
			</div>
			<div class="overflow-x-auto">
				<div class="min-w-max">
					<!-- Hour labels -->
					<div class="mb-0.5 flex">
						<div class="w-9 shrink-0"></div>
						{#each Array.from({ length: 24 }, (_, h) => h) as h, _i (_i)}
							<div class="w-5 shrink-0 text-center font-mono text-[9px] text-muted-foreground">
								{h === 0 || h % 4 === 0 ? h : ''}
							</div>
						{/each}
					</div>
					{#each Array.from({ length: 7 }, (_, d) => d) as d, _i (_i)}
						<div class="mb-0.5 flex items-center">
							<div class="w-9 shrink-0 text-[10px] text-muted-foreground">{DOW_LABELS[d]}</div>
							{#each Array.from({ length: 24 }, (_, h) => h) as h, _i (_i)}
								{@const cell = timeHeatmap.grid[`${d}-${h}`]}
								{@const avg = cell ? cell.sum / cell.count : null}
								<div
									class="h-4 w-5 shrink-0 rounded-sm {heatColor(
										cell?.sum,
										cell?.count,
										timeHeatmap.maxAbs
									)}"
									title="{DOW_LABELS[d]} {h}:00 UTC — {cell
										? cell.count + ' trades, avg ' + avg!.toFixed(2) + '%'
										: 'no trades'}"
								></div>
							{/each}
						</div>
					{/each}
				</div>
			</div>
			<div class="mt-2 flex items-center gap-3 text-[10px] text-muted-foreground">
				<span class="flex items-center gap-1"
					><span class="inline-block h-3 w-3 rounded-sm bg-green-500"></span>Best avg%</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-3 w-3 rounded-sm bg-red-500"></span>Worst avg%</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-3 w-3 rounded-sm bg-muted/15"></span>No trades</span
				>
				<span class="ml-auto">Based on trade close time (UTC)</span>
			</div>
		</section>
	{/if}

	{#if entryHeatmap}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Entry Time Heatmap <span class="ml-1 text-xs font-normal text-muted-foreground"
						>(UTC hour × weekday · entry count)</span
					>
					<ChartInfo metric="holdingTime" {lang} />
				</h2>
			</div>
			<div class="overflow-x-auto">
				<div class="min-w-max">
					<div class="mb-0.5 flex">
						<div class="w-9 shrink-0"></div>
						{#each Array.from({ length: 24 }, (_, h) => h) as h, _i (_i)}
							<div class="w-5 shrink-0 text-center font-mono text-[9px] text-muted-foreground">
								{h === 0 || h % 4 === 0 ? h : ''}
							</div>
						{/each}
					</div>
					{#each Array.from({ length: 7 }, (_, d) => d) as d, _i (_i)}
						<div class="mb-0.5 flex items-center">
							<div class="w-9 shrink-0 text-[10px] text-muted-foreground">{DOW_LABELS[d]}</div>
							{#each Array.from({ length: 24 }, (_, h) => h) as h, _i (_i)}
								{@const count = entryHeatmap.grid[`${d}-${h}`] ?? 0}
								{@const intensity = count / entryHeatmap.maxCount}
								<div
									class="h-4 w-5 shrink-0 rounded-sm {count === 0
										? 'bg-muted/15'
										: intensity > 0.7
											? 'bg-indigo-500'
											: intensity > 0.4
												? 'bg-indigo-700/60'
												: 'bg-indigo-900/40'}"
									title="{DOW_LABELS[d]} {h}:00 UTC — {count} entries"
								></div>
							{/each}
						</div>
					{/each}
				</div>
			</div>
			<div class="mt-2 flex items-center gap-3 text-[10px] text-muted-foreground">
				<span class="flex items-center gap-1"
					><span class="inline-block h-3 w-3 rounded-sm bg-indigo-500"></span>Most entries</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-3 w-3 rounded-sm bg-muted/15"></span>No entries</span
				>
				<span class="ml-auto">Based on trade open time (UTC)</span>
			</div>
		</section>
	{/if}

	{#if wfLatest.length > 0}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">{t(lang, 'detail.wf')}</h2>
				<span class="text-xs text-muted-foreground"
					>{fmt('detail.wfRunDate', { d: fmtTime(wfDate) })}</span
				>
			</div>
			<div class="space-y-1.5">
				{#each wfLatest as w (w.window_label)}
					{@const p = w.tot_profit_pct ?? 0}
					{@const width = (Math.abs(p) / wfMax) * 100}
					{@const barPosCls =
						p > 0 ? 'bg-green-500 left-1/2' : p < 0 ? 'bg-red-500 right-1/2' : 'bg-muted left-1/2'}
					<div class="flex items-center gap-2 font-mono text-xs">
						<span class="w-16 shrink-0 text-muted-foreground">{w.window_label}</span>
						<span class="w-24 shrink-0 text-muted-foreground"
							>{fmtTime(w.window_start).slice(0, 10)}</span
						>
						<div class="relative h-4 flex-1 rounded bg-muted/30">
							<div
								class="absolute top-0 h-full rounded {barPosCls}"
								style="width: {width / 2}%"
							></div>
							<div class="absolute inset-y-0 left-1/2 w-px bg-border"></div>
						</div>
						<span class="w-20 shrink-0 text-right {signClass(p)}">{fmtPct(p)}</span>
						<span class="w-14 shrink-0 text-right text-muted-foreground">{w.trades ?? 0}t</span>
					</div>
				{/each}
			</div>
			<p class="mt-3 text-xs text-muted-foreground">
				{t(lang, 'detail.wfFoot')}
				<a class="text-primary hover:underline" href="/wf">{t(lang, 'detail.wfLink')}</a>
			</p>
		</section>
	{/if}

	{#if similarStrategies.length > 0}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Similar Strategies <ChartInfo metric="leaderboard" {lang} />
				</h2>
				<span class="text-xs text-muted-foreground"
					>Same assets &amp; mode · Jaccard similarity</span
				>
			</div>
			<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
				{#each similarStrategies as s, _i (_i)}
					{@const pct = Math.round(s.score * 100)}
					<a
						href="/strategies/{s.name}"
						class="group flex flex-col gap-1.5 rounded-lg border bg-secondary/40 p-3 transition hover:bg-accent/40"
					>
						<div class="flex items-center justify-between">
							<span
								class="mr-2 truncate text-xs font-semibold transition-colors group-hover:text-primary"
								>{s.name}</span
							>
							<span
								class="shrink-0 rounded-full px-1.5 py-0.5 font-mono text-[10px]
								{s.mode === 'spot'
									? 'bg-green-500/20 text-green-400'
									: s.mode === 'futures'
										? 'bg-red-500/20 text-red-400'
										: 'bg-violet-500/20 text-violet-400'}">{s.mode}</span
							>
						</div>
						<div class="flex items-center gap-1.5">
							<div class="h-1.5 flex-1 overflow-hidden rounded-full bg-muted/40">
								<div class="h-full rounded-full bg-primary/70" style="width:{pct}%"></div>
							</div>
							<span class="font-mono text-[10px] text-muted-foreground">{pct}%</span>
						</div>
						<span class="text-[10px] text-muted-foreground capitalize">{s.status}</span>
					</a>
				{/each}
			</div>
		</section>
	{/if}

	{#if meta?.reports?.length}
		<section class="mb-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">{t(lang, 'detail.reports')}</h2>
			<ul class="space-y-1 text-sm">
				{#each meta.reports as r, _i (_i)}
					<li>
						<a href={r.path} class="text-primary hover:underline">{r.label}</a>
						<span class="ml-2 font-mono text-xs text-muted-foreground">{r.path}</span>
					</li>
				{/each}
			</ul>
		</section>
	{/if}

	{#if weeklyPnlBars}
		{@const wpb = weeklyPnlBars}
		<section class="mt-6 rounded-lg border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Weekly P&amp;L Bars <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({wpb.winWeeks}/{wpb.weeks} profitable weeks · best run)</span
				>
				<ChartInfo metric="totalProfit" {lang} />
			</h2>
			<svg viewBox="0 0 {wpb.W} {wpb.H}" class="w-full" style="height:{wpb.H}px">
				<line
					x1="0"
					y1={wpb.H / 2}
					x2={wpb.W}
					y2={wpb.H / 2}
					stroke="var(--ch-rule-faint)"
					stroke-width="0.5"
				/>
				{#each wpb.bars as b, _i (_i)}
					<rect
						x={b.x.toFixed(1)}
						width={wpb.barW.toFixed(1)}
						y={b.positive ? (wpb.H / 2 - b.h).toFixed(1) : (wpb.H / 2).toFixed(1)}
						height={Math.max(1, b.h).toFixed(1)}
						fill={b.positive ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					>
						<title
							>{b.week} · {b.sum >= 0 ? '+' : ''}{b.sum.toFixed(2)} USDT · {b.count} trades</title
						>
					</rect>
				{/each}
			</svg>
			<div class="mt-1 flex justify-between text-[10px] text-muted-foreground">
				<span>{wpb.winWeeks}/{wpb.weeks} green weeks</span>
				<span class:text-green-400={wpb.total >= 0} class:text-red-400={wpb.total < 0}
					>total {wpb.total >= 0 ? '+' : ''}{wpb.total.toFixed(2)} USDT</span
				>
			</div>
		</section>
	{/if}

	{#if pairProfitRanking}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Pair Profit Ranking
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(cumulative profit% per pair from best backtest run)</span
				>
				<ChartInfo metric="totalProfit" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each pairProfitRanking as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span
							class="w-28 shrink-0 truncate font-mono text-[10px] text-muted-foreground"
							title={r.pair}>{r.pair}</span
						>
						<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm"
								style="width:{r.barPct.toFixed(1)}%; background:{r.sum >= 0
									? 'var(--ch-profit-light)'
									: 'var(--ch-loss-light)'}"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
								{r.sum >= 0 ? '+' : ''}{r.sum.toFixed(1)}%
							</span>
						</div>
						<span class="w-10 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
							>{r.count}×</span
						>
						<span
							class="w-14 shrink-0 text-right font-mono text-[10px]"
							class:text-green-400={r.wr >= 0.5}
							class:text-red-400={r.wr < 0.5}
						>
							WR {(r.wr * 100).toFixed(0)}%
						</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Sum of profit% across all trades for each pair · shows which pairs contribute most to
				returns
			</p>
		</section>
	{/if}

	{#if monthlyReturnHeatmap}
		{@const mrh = monthlyReturnHeatmap}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Monthly Return Heatmap
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(cumulative profit% per calendar month)</span
				>
				<ChartInfo metric="totalProfit" {lang} />
			</h2>
			<div class="overflow-x-auto">
				<table class="w-full text-[10px]">
					<thead>
						<tr>
							<th class="w-10 pr-3 text-left font-normal text-muted-foreground">Year</th>
							{#each mrh.MONTH_LABELS as ml, _i (_i)}
								<th class="px-1 text-center font-normal text-muted-foreground">{ml}</th>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each mrh.grid as row, _i (_i)}
							<tr class="border-t border-border/20">
								<td class="py-1 pr-3 font-mono text-[10px] text-muted-foreground">{row.year}</td>
								{#each row.cells as cell, _i (_i)}
									<td class="px-0.5 py-1 text-center">
										{#if cell}
											<span
												class="inline-flex h-6 w-9 items-center justify-center rounded font-mono text-[9px] font-semibold"
												style="background:{cell.sum >= 0
													? `rgba(34,197,94,${(cell.intensity * 0.75 + 0.1).toFixed(2)})`
													: `rgba(239,68,68,${(cell.intensity * 0.75 + 0.1).toFixed(2)})`}; color:white"
												title="{cell.count} trades · WR {(cell.wr * 100).toFixed(0)}%"
											>
												{cell.sum >= 0 ? '+' : ''}{cell.sum.toFixed(1)}
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
				Green = profit · red = loss · intensity ∝ magnitude · hover for trade count and win rate
			</p>
		</section>
	{/if}

	{#if tradeDurationVsProfit}
		{@const tdvp = tradeDurationVsProfit}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-2 text-sm font-semibold">
				Hold Duration vs Profit Scatter
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>({tdvp.dots.length} trades · r = {tdvp.corr >= 0 ? '+' : ''}{tdvp.corr.toFixed(2)})</span
				>
				<ChartInfo metric="scatter" {lang} />
			</h2>
			<svg viewBox="0 0 {tdvp.W} {tdvp.H}" class="w-full" style="height:{tdvp.H}px">
				<line
					x1={tdvp.PAD}
					y1={tdvp.zeroY.toFixed(1)}
					x2={tdvp.W - tdvp.PAD}
					y2={tdvp.zeroY.toFixed(1)}
					stroke="var(--ch-rule)"
					stroke-width="1"
					stroke-dasharray="3 2"
				/>
				{#each tdvp.dots as d, _i (_i)}
					<circle
						cx={d.x.toFixed(1)}
						cy={d.y.toFixed(1)}
						r="2.5"
						fill={d.profit > 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)'}
						stroke="none"
					>
						<title
							>{Math.round(d.min / 60)}h hold · {d.profit >= 0 ? '+' : ''}{(d.profit * 100).toFixed(
								2
							)}%</title
						>
					</circle>
				{/each}
				<text x={tdvp.PAD} y={tdvp.H - 3} font-size="7" fill="var(--ch-rule)">0</text>
				<text
					x={tdvp.W - tdvp.PAD}
					y={tdvp.H - 3}
					font-size="7"
					fill="var(--ch-rule)"
					text-anchor="end">{Math.round(tdvp.xMax / 60)}h</text
				>
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				x = hold duration · y = profit% · Pearson r = {tdvp.corr >= 0 ? '+' : ''}{tdvp.corr.toFixed(
					2
				)} · hover for details
			</p>
		</section>
	{/if}

	{#if exitReasonAvgProfit}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Avg Profit by Exit Reason
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(avg profit% per exit type · sorted best → worst)</span
				>
				<ChartInfo metric="avgProfit" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each exitReasonAvgProfit as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-32 shrink-0 truncate font-mono text-[10px]" title={r.reason}
							>{r.reason}</span
						>
						<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm"
								style="width:{r.barPct.toFixed(1)}%; background:{r.avgProfit >= 0
									? 'var(--ch-profit-light)'
									: 'var(--ch-loss-light)'}"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
								{r.avgProfit >= 0 ? '+' : ''}{(r.avgProfit * 100).toFixed(2)}%
							</span>
						</div>
						<span class="w-24 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
							WR {(r.wr * 100).toFixed(0)}% · {r.count}×
						</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Bar = avg profit% per exit reason · green = profitable · right = win rate and count
			</p>
		</section>
	{/if}

	{#if runImportTimeline}
		{@const rit = runImportTimeline}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Research Activity Timeline
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>({rit.total} total runs · last 12 weeks)</span
				>
				<ChartInfo metric="leaderboard" {lang} />
			</h2>
			<div class="flex items-end gap-1" style="height:64px">
				{#each rit.weeks as w, i (i)}
					<div
						class="flex flex-1 flex-col items-center justify-end gap-0.5"
						title="{w.label}: {w.count} runs"
					>
						<div
							class="w-full rounded-t-sm transition-all"
							style="height:{Math.max(2, (w.count / rit.maxCount) * 52)}px; background:{i >= 8
								? 'var(--ch-violet)'
								: 'var(--ch-violet-light)'}"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{rit.weeks[0].label}</span><span>{rit.weeks[5].label}</span><span
					>{rit.weeks[11].label}</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Bars = runs imported per week · darker = recent 4 weeks
			</p>
		</section>
	{/if}

	{#if avgProfitByMonth}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Monthly Avg Trade Profit %
				<span class="ml-1 text-xs font-normal text-muted-foreground">(last 12 months)</span>
				<ChartInfo metric="avgProfit" {lang} />
			</h2>
			<div class="flex items-end gap-1" style="height:72px">
				{#each avgProfitByMonth as m, _i (_i)}
					<div
						class="flex flex-1 flex-col items-center justify-center gap-0.5"
						title="{m.label}: {m.count} trades · avg {m.avg != null
							? (m.avg >= 0 ? '+' : '') + m.avg.toFixed(2) + '%'
							: 'no data'}"
					>
						{#if m.avg != null && m.avg >= 0}
							<div
								class="w-full rounded-t-sm"
								style="height:{Math.max(2, m.barPct * 0.6)}px; background:var(--ch-profit)"
							></div>
							<div style="height:{0.6 * 100 - m.barPct * 0.6}px"></div>
						{:else if m.avg != null && m.avg < 0}
							<div style="height:{0.6 * 100 - m.barPct * 0.6}px"></div>
							<div
								class="w-full rounded-b-sm"
								style="height:{Math.max(2, m.barPct * 0.6)}px; background:var(--ch-loss-light)"
							></div>
						{:else}
							<div class="w-full opacity-20" style="height:2px; background:var(--ch-rule)"></div>
						{/if}
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				{#each avgProfitByMonth as m, i (i)}
					{#if i === 0 || i === 5 || i === 11}
						<span>{m.label}</span>
					{/if}
				{/each}
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Bar height = avg profit% per closed trade · green = positive · red = negative · empty = no
				trades that month
			</p>
		</section>
	{/if}

	{#if pairWinRate}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Win Rate by Pair
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(% of trades profitable · min 3 trades · top 14 pairs)</span
				>
				<ChartInfo metric="winRate" {lang} />
			</h2>
			<div class="space-y-1">
				{#each pairWinRate as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-24 shrink-0 truncate font-mono text-[10px]"
							>{r.pair.replace('/USDT:USDT', '').replace('/USDT', '')}</span
						>
						<div class="relative h-4 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm transition-all"
								style="width:{(r.wr * 100).toFixed(1)}%; background:{r.wr >= 0.6
									? 'var(--ch-profit)'
									: r.wr >= 0.45
										? 'var(--ch-warn-light)'
										: 'var(--ch-loss-light)'}"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
								{(r.wr * 100).toFixed(0)}%
							</span>
						</div>
						<span class="w-14 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
							>{r.wins}/{r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Bar = win rate · right = wins/total trades · green ≥60% · yellow 45–60% · red &lt;45% ·
				ranked by WR
			</p>
		</section>
	{/if}

	{#if enterTagWinRate}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Entry Tag Win Rate
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(% of trades profitable per entry condition · min 3 trades)</span
				>
				<ChartInfo metric="winRate" {lang} />
			</h2>
			<div class="space-y-1">
				{#each enterTagWinRate as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-32 shrink-0 truncate font-mono text-[10px]" title={r.tag}>{r.tag}</span>
						<div class="relative h-4 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm transition-all"
								style="width:{(r.wr * 100).toFixed(1)}%; background:{r.wr >= 0.6
									? 'var(--ch-profit)'
									: r.wr >= 0.45
										? 'var(--ch-warn-light)'
										: 'var(--ch-loss-light)'}"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
								{(r.wr * 100).toFixed(0)}%
							</span>
						</div>
						<span class="w-14 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
							>{r.wins}/{r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Bar = win rate per entry tag · green ≥60% · yellow 45–60% · red &lt;45% · ranked by win rate
			</p>
		</section>
	{/if}

	{#if exitHourAnalysis}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Exit Hour Analysis (UTC)
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(avg profit% per close hour · which hours produce best exits?)</span
				>
				<ChartInfo metric="exitReason" {lang} />
			</h2>
			<div class="flex items-end gap-px" style="height:60px">
				{#each exitHourAnalysis as h, _i (_i)}
					<div
						class="flex flex-1 flex-col items-center justify-end"
						title="Hour {h.label} UTC: {h.count} exits · avg {h.avg != null
							? (h.avg >= 0 ? '+' : '') + h.avg.toFixed(2) + '%'
							: '—'} · WR {h.wr != null ? (h.wr * 100).toFixed(0) + '%' : '—'}"
					>
						{#if h.avg != null && h.count > 0}
							<div
								class="w-full rounded-t-sm"
								style="height:{Math.max(2, h.barPct * 0.54)}px; background:{h.avg >= 0
									? 'var(--ch-profit)'
									: 'var(--ch-loss)'}"
							></div>
						{:else}
							<div class="w-full" style="height:1px; background:var(--ch-rule-faint)"></div>
						{/if}
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>00h</span><span>06h</span><span>12h</span><span>18h</span><span>23h</span>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Green = positive avg profit · red = negative · bar height ∝ magnitude · empty = no exits
				that hour
			</p>
		</section>
	{/if}

	{#if pairHoldingTimeRanking}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Avg Holding Time by Pair
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(pairs ranked longest to shortest average hold · min–max range shown)</span
				>
				<ChartInfo metric="holdingTime" {lang} />
			</h2>
			<div class="mt-3 space-y-1.5">
				{#each pairHoldingTimeRanking as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-28 truncate font-mono text-[10px]" title={r.pair}>{r.pair}</span>
						<div class="relative flex-1" style="height:14px">
							<div
								class="absolute rounded"
								style="height:100%; width:{r.barPct}%; background:var(--ch-violet-light)"
							></div>
						</div>
						<span class="w-14 text-right font-mono text-[10px]">{r.avgLabel}</span>
						<span class="w-16 text-right font-mono text-[9px] text-muted-foreground"
							>max {r.maxLabel}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Average trade hold time per pair · longer bars = pair tends to be held longer · compare with
				win rate to spot slow-bleed pairs
			</p>
		</section>
	{/if}

	{#if exitReasonProfitProfile}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Exit Reason Profit Profile
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(avg profit% and win rate per exit reason · ranked best to worst)</span
				>
				<ChartInfo metric="winRate" {lang} />
			</h2>
			<div class="mt-3 space-y-1.5">
				{#each exitReasonProfitProfile as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-36 truncate font-mono text-[10px]" title={r.reason}>{r.reason}</span>
						<div class="relative flex-1" style="height:14px">
							<div
								class="absolute rounded"
								style="height:100%; width:{r.barPct}%; background:{r.avg >= 0
									? 'var(--ch-profit-light)'
									: 'var(--ch-loss-light)'}"
							></div>
						</div>
						<span
							class="w-16 text-right font-mono text-[10px]"
							style="color:{r.avg >= 0 ? 'rgb(74,222,128)' : 'rgb(248,113,113)'}"
							>{r.avg >= 0 ? '+' : ''}{r.avg.toFixed(2)}%</span
						>
						<span class="w-14 text-right font-mono text-[9px] text-muted-foreground"
							>{(r.wr * 100).toFixed(0)}%wr</span
						>
						<span class="w-10 text-right font-mono text-[9px] text-muted-foreground">{r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Avg profit per exit reason · positive = strategy exits profitably via that path · wr = win
				rate for that exit type
			</p>
		</section>
	{/if}

	{#if pairWorstTrade}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Worst Single-Trade Loss by Pair
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(pairs ranked by their worst individual trade outcome)</span
				>
				<ChartInfo metric="totalProfit" {lang} />
			</h2>
			<div class="mt-3 space-y-1.5">
				{#each pairWorstTrade as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-28 truncate font-mono text-[10px]" title={r.pair}>{r.pair}</span>
						<div class="relative flex-1" style="height:14px">
							<div
								class="absolute rounded"
								style="height:100%; width:{r.barPct}%; background:var(--ch-loss-light)"
							></div>
						</div>
						<span class="w-16 text-right font-mono text-[10px] text-red-400"
							>{r.worst.toFixed(1)}%</span
						>
						<span class="w-12 text-right font-mono text-[9px] text-muted-foreground"
							>{(r.wr * 100).toFixed(0)}%wr</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Worst trade per pair · longer bar = bigger single-trade loss · wr = overall win rate for
				that pair
			</p>
		</section>
	{/if}

	{#if runCalmarTimeline}
		{@const rct = runCalmarTimeline}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Calmar Ratio Over Runs
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(risk-adjusted return trend across {rct.count} runs · {rct.trend >= 0
						? '↑ improving'
						: '↓ declining'})</span
				>
				<ChartInfo metric="calmar" {lang} />
			</h2>
			<svg viewBox="0 0 {rct.W} {rct.H}" class="w-full" style="height:72px">
				<line
					x1={rct.PAD}
					x2={rct.W - rct.PAD}
					y1={rct.zeroY}
					y2={rct.zeroY}
					stroke="var(--ch-rule)"
					stroke-width="1"
					stroke-dasharray="4 3"
				/>
				<polyline
					points={rct.polyline}
					fill="none"
					stroke={rct.trend >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					stroke-width="1.5"
				/>
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>Calmar {rct.mn.toFixed(2)}</span><span>→ runs by import date →</span><span
					>{rct.mx.toFixed(2)}</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Each point = one run's Calmar ratio sorted by import date · upward = risk-adjusted returns
				improving over time
			</p>
		</section>
	{/if}

	{#if tradeMonthlyVolume}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Trade Volume by Month
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(how many trades closed each calendar month)</span
				>
				<ChartInfo metric="tradeCount" {lang} />
			</h2>
			<div class="mt-3 flex items-end gap-0.5" style="height:64px">
				{#each tradeMonthlyVolume as m, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-0.5">
						<div
							class="w-full rounded-t"
							style="height:{Math.max(2, m.barPct * 0.56)}px; background:var(--ch-violet-light)"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{tradeMonthlyVolume[0]?.ym}</span>
				<span>→ month →</span>
				<span>{tradeMonthlyVolume[tradeMonthlyVolume.length - 1]?.ym}</span>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Each bar = number of trades closed in that month · spikes = high-activity periods
			</p>
		</section>
	{/if}

	{#if meta?.docSlug}
		<section class="rounded-lg border border-dashed bg-card p-4 text-sm">
			<span class="text-muted-foreground">{t(lang, 'detail.doc')}</span>
			<a class="text-primary hover:underline" href={`/docs/strategies/${meta.docSlug}/`}>
				/docs/strategies/{meta.docSlug}/ ↗
			</a>
		</section>
	{/if}

	{#if stakeAmountProfile}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Profit by Stake Size <ChartInfo metric="totalProfit" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Average profit% per trade grouped by stake amount bucket
			</p>
			<div class="mt-3 space-y-1.5">
				{#each stakeAmountProfile as b, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-24 truncate font-mono text-[10px] text-muted-foreground">{b.label}</span>
						<div
							class="flex-1 overflow-hidden rounded-sm"
							style="height:14px; background:var(--ch-rule-faint)"
						>
							<div
								class="h-full rounded-sm"
								style="width:{b.barPct}%; background:{b.avg >= 0
									? 'var(--ch-profit)'
									: 'var(--ch-loss)'}"
							></div>
						</div>
						<span
							class="w-10 text-right font-mono text-[10px]"
							style="color:{b.avg >= 0 ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
							>{b.avg >= 0 ? '+' : ''}{b.avg.toFixed(2)}%</span
						>
						<span class="w-12 text-right font-mono text-[9px] text-muted-foreground"
							>WR {(b.wr * 100).toFixed(0)}% n={b.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Shows whether the strategy performs differently at different position sizes · useful for DCA
				and adaptive-stake strategies
			</p>
		</section>
	{/if}

	{#if enterTagProfitProfile}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Enter Tag Profit Profile <ChartInfo metric="enterTag" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Average profit% and win rate per entry signal tag (min 3 trades)
			</p>
			<div class="mt-3 space-y-1.5">
				{#each enterTagProfitProfile as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-32 truncate font-mono text-[10px] text-muted-foreground">{r.tag}</span>
						<div
							class="flex-1 overflow-hidden rounded-sm"
							style="height:14px; background:var(--ch-rule-faint)"
						>
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:{r.avg >= 0
									? 'var(--ch-profit)'
									: 'var(--ch-loss)'}"
							></div>
						</div>
						<span
							class="w-12 text-right font-mono text-[10px]"
							style="color:{r.avg >= 0 ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
							>{r.avg >= 0 ? '+' : ''}{r.avg.toFixed(2)}%</span
						>
						<span class="w-14 text-right font-mono text-[9px] text-muted-foreground"
							>WR {(r.wr * 100).toFixed(0)}% n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Compare entry tags to identify which signals produce the most profitable trades · sorted by
				avg profit
			</p>
		</section>
	{/if}

	{#if pairProfitTrend}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Pair Profit Trend (Early vs Late) <ChartInfo metric="scatter" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Change in avg profit% from first half to second half of trades per pair (min 6 trades)
			</p>
			<div class="mt-3 space-y-1.5">
				{#each pairProfitTrend as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-24 truncate font-mono text-[10px] text-muted-foreground">{r.pair}</span>
						<div
							class="flex-1 overflow-hidden rounded-sm"
							style="height:14px; background:var(--ch-rule-faint)"
						>
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:{r.delta >= 0
									? 'var(--ch-profit)'
									: 'var(--ch-loss)'}"
							></div>
						</div>
						<span
							class="w-14 text-right font-mono text-[10px]"
							style="color:{r.delta >= 0 ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
							>{r.delta >= 0 ? '+' : ''}{r.delta.toFixed(2)}%</span
						>
						<span class="w-10 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Green = improving pair over time · red = degrading · helps identify pairs where the edge may
				be eroding
			</p>
		</section>
	{/if}

	{#if pairTradeCountVsProfit}
		{@const ptcvp = pairTradeCountVsProfit}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Pair Trade Count vs Avg Profit Scatter <ChartInfo metric="tradeCount" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Each dot = one pair · X = number of trades · Y = avg profit% · reveals if heavily traded
				pairs outperform
			</p>
			<svg viewBox="0 0 {ptcvp.W} {ptcvp.H}" class="mt-2 w-full" style="height:80px">
				<line
					x1={ptcvp.PAD}
					y1={ptcvp.H -
						ptcvp.PAD -
						((0 - ptcvp.yMin) / (ptcvp.yMax - ptcvp.yMin)) * (ptcvp.H - ptcvp.PAD * 2)}
					x2={ptcvp.W - ptcvp.PAD}
					y2={ptcvp.H -
						ptcvp.PAD -
						((0 - ptcvp.yMin) / (ptcvp.yMax - ptcvp.yMin)) * (ptcvp.H - ptcvp.PAD * 2)}
					stroke="var(--ch-rule)"
					stroke-width="0.5"
				/>
				{#each ptcvp.dots as d, _i (_i)}
					<circle
						cx={d.cx}
						cy={d.cy}
						r="2.5"
						fill={d.pos ? 'var(--ch-profit)' : 'var(--ch-loss-light)'}
					/>
				{/each}
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{ptcvp.xMin} trades</span><span>→ trade count per pair →</span><span
					>{ptcvp.xMax}</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Green = avg profitable pair · upward trend = more trades = better edge · scattered = pair
				profitability is independent of activity
			</p>
		</section>
	{/if}

	{#if tradeProfitByHour}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Avg Profit% by Hour of Day (UTC Close) <ChartInfo metric="avgProfit" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Average trade profit% per UTC close hour — highlights which market sessions yield best
				results
			</p>
			<div class="mt-3 flex items-end gap-px" style="height:60px">
				{#each tradeProfitByHour as d, _i (_i)}
					<div class="flex flex-1 flex-col items-center">
						{#if d.avg != null}
							<div
								class="w-full rounded-sm"
								style="height:{d.barPct}%; background:{d.avg >= 0
									? 'var(--ch-profit)'
									: 'var(--ch-loss-light)'}; min-height:{d.count >= 2 ? 1 : 0}px"
							></div>
						{:else}
							<div class="w-full" style="height:1px; background:var(--ch-rule-faint)"></div>
						{/if}
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[8px] text-muted-foreground">
				<span>00h</span><span>06h</span><span>12h</span><span>18h</span><span>23h</span>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Green = profitable hour on average · Asia session 00–08h · London 08–16h · NY 13–21h · hours
				with fewer than 2 trades shown as flat
			</p>
		</section>
	{/if}

	{#if tradeProfitByDayOfWeek}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Avg Profit% by Day of Week (Close Date) <ChartInfo metric="avgProfit" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Average trade profit% grouped by the day trades closed — reveals weekday edge patterns
			</p>
			<div class="mt-3 flex items-end gap-1" style="height:72px">
				{#each tradeProfitByDayOfWeek as d, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-0.5">
						{#if d.avg != null}
							<span
								class="font-mono text-[8px]"
								style="color:{d.avg >= 0 ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
							>
								{d.avg >= 0 ? '+' : ''}{d.avg.toFixed(1)}
							</span>
							<div
								class="w-full rounded-sm"
								style="height:{d.barPct}%; background:{d.avg >= 0
									? 'var(--ch-profit)'
									: 'var(--ch-loss-light)'}; min-height:{d.count > 0 ? 2 : 0}px"
							></div>
						{:else}
							<div class="w-full"></div>
						{/if}
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-around font-mono text-[9px] text-muted-foreground">
				{#each tradeProfitByDayOfWeek as d, _i (_i)}
					<span class="flex-1 text-center">{d.day}</span>
				{/each}
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Green = positive average · red = negative average · n={tradeProfitByDayOfWeek.reduce(
					(s, d) => s + d.count,
					0
				)} trades · grey day = fewer than 2 closes
			</p>
		</section>
	{/if}

	{#if tradeStreakAnalysis}
		{@const tsa = tradeStreakAnalysis}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Trade Streak Analysis <ChartInfo metric="streak" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Win/loss streak statistics across {tsa.total} chronological trades
			</p>
			<div class="mt-3 grid grid-cols-3 gap-3">
				<div class="rounded-lg border border-border bg-card/60 p-3 text-center">
					<div class="font-mono text-2xl font-semibold" style="color:var(--ch-profit-solid)">
						{tsa.maxWin}
					</div>
					<div class="mt-0.5 text-[10px] text-muted-foreground">longest win streak</div>
				</div>
				<div class="rounded-lg border border-border bg-card/60 p-3 text-center">
					<div class="font-mono text-2xl font-semibold" style="color:var(--ch-loss-solid)">
						{tsa.maxLoss}
					</div>
					<div class="mt-0.5 text-[10px] text-muted-foreground">longest loss streak</div>
				</div>
				<div class="rounded-lg border border-border bg-card/60 p-3 text-center">
					<div
						class="font-mono text-2xl font-semibold"
						style="color:{tsa.currentIsWin ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
					>
						{tsa.currentStreak > 0 ? '+' : ''}{tsa.currentStreak}
					</div>
					<div class="mt-0.5 text-[10px] text-muted-foreground">current streak</div>
				</div>
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Long win streaks = momentum periods · long loss streaks = regime mismatch · current streak
				shows recent momentum direction
			</p>
		</section>
	{/if}

	{#if tradeMonthlyWinRate}
		{@const tmwr = tradeMonthlyWinRate}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">Monthly Win Rate <ChartInfo metric="winRate" {lang} /></h2>
			<p class="mb-2 text-[11px] text-muted-foreground">
				Win rate per calendar month · avg {(tmwr.avgWr * 100).toFixed(1)}% · dashed line = 50%
			</p>
			<svg viewBox="0 0 {tmwr.W} {tmwr.H}" class="w-full" style="height:64px">
				<line
					x1={tmwr.PAD}
					y1={tmwr.zeroY}
					x2={tmwr.W - tmwr.PAD}
					y2={tmwr.zeroY}
					stroke="var(--ch-rule-strong)"
					stroke-width="0.8"
					stroke-dasharray="3,3"
				/>
				<polyline
					points={tmwr.poly}
					fill="none"
					stroke={tmwr.avgWr >= 0.5 ? 'var(--ch-profit-strong)' : 'var(--ch-loss-strong)'}
					stroke-width="1.5"
				/>
				{#each tmwr.rows as r, i (i)}
					<circle
						cx={tmwr.PAD + (i / Math.max(1, tmwr.rows.length - 1)) * (tmwr.W - tmwr.PAD * 2)}
						cy={tmwr.H - tmwr.PAD - r.wr * (tmwr.H - tmwr.PAD * 2)}
						r="2"
						fill={r.wr >= 0.5 ? 'var(--ch-profit-strong)' : 'var(--ch-loss-strong)'}
					/>
				{/each}
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{tmwr.rows[0].ym}</span><span>← month →</span><span
					>{tmwr.rows[tmwr.rows.length - 1].ym}</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Green dot = &gt;50% WR · red dot = &lt;50% WR · persistent green = strategy profitable
				across diverse market regimes
			</p>
		</section>
	{/if}

	{#if tradePairWinRate}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">Win Rate by Pair <ChartInfo metric="winRate" {lang} /></h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Win rate per trading pair (≥3 trades) sorted by win rate descending
			</p>
			<div class="space-y-1">
				{#each tradePairWinRate as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-24 truncate text-right font-mono text-[11px] text-muted-foreground"
							>{r.pair.replace('/USDT:USDT', '').replace('/USDT', '')}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:{r.wr >= 0.5
									? 'var(--ch-profit)'
									: 'var(--ch-loss)'}"
							></div>
						</div>
						<span
							class="w-12 text-right font-mono text-[10px]"
							style="color:{r.wr >= 0.5 ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
							>{(r.wr * 100).toFixed(0)}%</span
						>
						<span
							class="w-14 text-right font-mono text-[10px]"
							style="color:{r.avgProfit >= 0 ? 'var(--ch-violet-strong)' : 'var(--ch-loss-strong)'}"
							>{r.avgProfit > 0 ? '+' : ''}{r.avgProfit.toFixed(2)}%</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.total}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				High WR + positive avg profit = core pairs · high WR + negative avg profit = small wins
				overwhelmed by rare large losses
			</p>
		</section>
	{/if}

	{#if tradeHoldingBucketWinRate}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Win Rate by Holding Duration <ChartInfo metric="winRate" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Win rate and avg profit% across holding-time buckets (≥3 trades per bucket)
			</p>
			<div class="space-y-1.5">
				{#each tradeHoldingBucketWinRate as b, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-20 shrink-0 text-right font-mono text-[9px] text-muted-foreground"
							>{b.label}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div
								class="h-full rounded-sm"
								style="width:{b.wr * 100}%; background:{b.wr >= 0.5
									? 'var(--ch-profit)'
									: 'var(--ch-loss)'}"
							></div>
						</div>
						<span
							class="w-12 text-right font-mono text-[10px]"
							style="color:{b.wr >= 0.5 ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
							>{(b.wr * 100).toFixed(0)}% WR</span
						>
						<span
							class="w-14 text-right font-mono text-[10px]"
							style="color:{b.avg >= 0 ? 'var(--ch-violet-strong)' : 'var(--ch-loss-strong)'}"
							>{b.avg > 0 ? '+' : ''}{b.avg.toFixed(2)}%</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground"
							>n={b.total}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Best WR bucket = optimal holding window · very short trades = noise trading · very long =
				trapped positions waiting for recovery
			</p>
		</section>
	{/if}

	{#if tradeProfitCumulativeTimeline}
		{@const tpct = tradeProfitCumulativeTimeline}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Cumulative Profit Timeline <ChartInfo metric="totalProfit" {lang} />
			</h2>
			<p class="mb-2 text-[11px] text-muted-foreground">
				Running sum of trade profit% across {tpct.total} trades · final: {tpct.positive
					? '+'
					: ''}{tpct.final.toFixed(1)}%
			</p>
			<svg viewBox="0 0 {tpct.W} {tpct.H}" class="w-full" style="height:64px">
				<line
					x1={tpct.PAD}
					y1={tpct.zeroY}
					x2={tpct.W - tpct.PAD}
					y2={tpct.zeroY}
					stroke="var(--ch-rule)"
					stroke-width="0.8"
					stroke-dasharray="3,2"
				/>
				<polyline
					points={tpct.poly}
					fill="none"
					stroke={tpct.positive ? 'var(--ch-profit-strong)' : 'var(--ch-loss-strong)'}
					stroke-width="1.5"
				/>
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{tpct.first}</span><span>← trade close date →</span><span>{tpct.last}</span>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Steady upward slope = consistent edge · drawdowns = losing streaks · V-shaped recoveries =
				resilient strategy · flat periods = no trades
			</p>
		</section>
	{/if}

	{#if tradeEnterTagHourHeatmap}
		{@const teh = tradeEnterTagHourHeatmap}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Enter Tag Win Rate by Hour <ChartInfo metric="winRate" {lang} />
			</h2>
			<p class="mb-2 text-[11px] text-muted-foreground">
				Win rate per entry signal × hour of day (UTC) · green = high success rate at that hour ·
				grey = insufficient trades
			</p>
			<div class="overflow-x-auto">
				<table class="w-full text-[8px]">
					<thead>
						<tr>
							<th class="pr-1 text-right font-mono text-muted-foreground">Tag</th>
							{#each teh.hours as h, _i (_i)}
								<th class="px-0.5 text-center font-mono text-muted-foreground">{h}</th>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each teh.cells as row, _i (_i)}
							<tr class="border-t border-border/30">
								<td
									class="max-w-[6rem] truncate py-0.5 pr-1 text-right font-mono text-muted-foreground"
									>{row.tag}</td
								>
								{#each row.hours as cell, _i (_i)}
									<td class="px-0.5 py-0.5 text-center">
										{#if cell.wr != null}
											<span
												class="inline-block h-3 w-3 rounded-sm"
												style="background:{cell.wr >= 0.6
													? `rgba(34,197,94,${0.3 + cell.wr * 0.5})`
													: cell.wr >= 0.4
														? `rgba(234,179,8,${0.3 + cell.wr * 0.4})`
														: `rgba(239,68,68,${0.3 + (1 - cell.wr) * 0.4})`}"
												title="{cell.h}:00 WR {(cell.wr * 100).toFixed(0)}% ({cell.total} trades)"
											></span>
										{:else}
											<span class="inline-block h-3 w-3 rounded-sm bg-muted/30"></span>
										{/if}
									</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Green = high win rate at that hour · red = poor win rate · use to time entry signals or
				filter by session (Asia/EU/US hours)
			</p>
		</section>
	{/if}
	{#if runTimeframeComparisonTable}
		<section class="rounded-lg border border-border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Timeframe Performance Comparison <ChartInfo metric="timeframe" {lang} />
			</h2>
			<div class="overflow-x-auto">
				<table class="w-full text-xs">
					<thead>
						<tr class="border-b border-border text-left text-muted-foreground">
							<th class="pr-4 pb-2">Timeframe</th>
							<th class="pr-4 pb-2 text-right">Avg Profit %</th>
							<th class="pr-4 pb-2 text-right">Win Rate</th>
							<th class="pr-4 pb-2 text-right">Avg Calmar</th>
							<th class="pb-2 text-right">Runs</th>
						</tr>
					</thead>
					<tbody>
						{#each runTimeframeComparisonTable as row, _i (_i)}
							{@const profitColor =
								row.avg == null
									? '#888'
									: row.avg > 5
										? 'var(--ch-profit-strong)'
										: row.avg > 0
											? 'var(--ch-profit)'
											: row.avg > -5
												? 'var(--ch-loss)'
												: 'var(--ch-loss-strong)'}
							{@const wrColor =
								row.wr == null
									? '#888'
									: row.wr > 0.6
										? 'var(--ch-profit-strong)'
										: row.wr > 0.5
											? 'var(--ch-profit)'
											: row.wr > 0.4
												? 'var(--ch-loss-light)'
												: 'var(--ch-loss-strong)'}
							<tr class="border-b border-border/40 last:border-0">
								<td class="py-1.5 pr-4 font-mono font-medium">{row.tf}</td>
								<td class="py-1.5 pr-4 text-right font-mono" style="color:{profitColor}">
									{row.avg != null ? (row.avg > 0 ? '+' : '') + row.avg.toFixed(2) + '%' : '—'}
								</td>
								<td class="py-1.5 pr-4 text-right font-mono" style="color:{wrColor}">
									{row.wr != null ? (row.wr * 100).toFixed(1) + '%' : '—'}
								</td>
								<td
									class="py-1.5 pr-4 text-right font-mono"
									style="color:{row.calmar != null && row.calmar > 0
										? 'var(--ch-violet-strong)'
										: '#888'}"
								>
									{row.calmar != null ? row.calmar.toFixed(2) : '—'}
								</td>
								<td class="py-1.5 text-right text-muted-foreground">{row.count}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Avg profit/win-rate/calmar by timeframe across all backtest runs for this strategy · green =
				favorable · red = underperforming timeframe
			</p>
		</section>
	{/if}
	{#if runProfitFactorTimeline}
		{@const rpft = runProfitFactorTimeline}
		<section class="rounded-lg border border-border bg-card p-4">
			<h2 class="mb-1 text-sm font-semibold">
				Profit Factor Timeline <ChartInfo metric="profitFactor" {lang} />
			</h2>
			<p class="mb-2 text-[11px] text-muted-foreground">
				Profit_factor across backtest runs sorted by import date · avg {rpft.avg.toFixed(2)} · range {rpft.vMin.toFixed(
					2
				)}–{rpft.vMax.toFixed(2)}
			</p>
			<svg viewBox="0 0 {rpft.W} {rpft.H}" class="w-full" style="height:72px">
				<line
					x1={rpft.PAD}
					y1={rpft.y1}
					x2={rpft.W - rpft.PAD}
					y2={rpft.y1}
					stroke="var(--ch-axis-muted)"
					stroke-width="1"
					stroke-dasharray="4,3"
				/>
				<polyline
					points={rpft.poly}
					fill="none"
					stroke="var(--ch-violet-strong)"
					stroke-width="1.5"
				/>
				{#each rpft.pts as p, i (i)}
					{@const x = rpft.PAD + (i / Math.max(1, rpft.pts.length - 1)) * (rpft.W - rpft.PAD * 2)}
					{@const y =
						rpft.H -
						rpft.PAD -
						((p.pf - rpft.vMin) / (rpft.vMax - rpft.vMin || 0.001)) * (rpft.H - rpft.PAD * 2)}
					<circle
						cx={x}
						cy={y}
						r="2"
						fill={p.pf >= 1.5
							? 'var(--ch-profit-strong)'
							: p.pf >= 1
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					/>
				{/each}
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{rpft.first}</span><span>← runs by import date →</span><span>{rpft.last}</span>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Green ≥1.5 = strong edge · yellow ≥1 = marginal · red &lt;1 = losing · dashed line =
				breakeven (PF=1) · trend direction shows if edge is strengthening
			</p>
		</section>
	{/if}
	{#if tradeExitReasonTimeline}
		{@const ert = tradeExitReasonTimeline}
		<section class="rounded-lg border border-border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Exit Reason Timeline (Monthly) <ChartInfo metric="exitReason" {lang} />
			</h2>
			<div class="flex h-28 items-end gap-0.5">
				{#each ert.months as m, _i (_i)}
					{@const total = [...ert.grid.get(m)!.values()].reduce((s, x) => s + x, 0)}
					{@const heightPct = (total / ert.maxTotal) * 100}
					<div class="relative flex flex-1 flex-col justify-end" style="height:{heightPct}%">
						{#each ert.reasons as reason, ri (ri)}
							{@const count = ert.grid.get(m)!.get(reason) ?? 0}
							{@const pct = total > 0 ? (count / total) * 100 : 0}
							{#if count > 0}
								<div
									class="w-full"
									style="height:{pct}%; background:{ert.COLORS[ri]}; min-height:1px"
									title="{m} {reason}: {count}"
								></div>
							{/if}
						{/each}
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{ert.months[0]}</span><span>← monthly exit mix →</span><span
					>{ert.months[ert.months.length - 1]}</span
				>
			</div>
			<div class="mt-2 flex flex-wrap gap-3">
				{#each ert.reasons as reason, ri (ri)}
					<span class="flex items-center gap-1 text-[9px]"
						><span class="inline-block h-2 w-3 rounded-sm" style="background:{ert.COLORS[ri]}"
						></span>{reason}</span
					>
				{/each}
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Stacked bars = exit reason mix per month · shifting colors = exit strategy change ·
				consistent mix = stable behavior · ROI dominance = profit-target driven
			</p>
		</section>
	{/if}
	{#if runDrawdownTimeline}
		<section class="rounded-xl border border-border bg-card p-4">
			<h2 class="mb-1 text-sm font-semibold">
				Max Drawdown Over Time <ChartInfo metric="maxDrawdown" {lang} />
			</h2>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Max drawdown % per backtest run ordered by import date · shows whether optimization is
				reducing or worsening drawdown over time · trend {runDrawdownTimeline.trend > 0.5
					? '↑ worsening'
					: runDrawdownTimeline.trend < -0.5
						? '↓ improving'
						: '→ stable'}
			</p>
			<svg viewBox="0 0 {runDrawdownTimeline.W} {runDrawdownTimeline.H}" class="w-full">
				<line
					x1="0"
					y1={runDrawdownTimeline.avgY}
					x2={runDrawdownTimeline.W}
					y2={runDrawdownTimeline.avgY}
					stroke="var(--ch-warn-light)"
					stroke-width="1"
					stroke-dasharray="4,3"
				/>
				<polyline
					points={runDrawdownTimeline.polyline}
					fill="none"
					stroke="var(--ch-loss)"
					stroke-width="1.5"
				/>
				{#each runDrawdownTimeline.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="2.5" fill="var(--ch-loss)" />
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Each dot = one run · higher = worse drawdown · yellow dashed = avg {runDrawdownTimeline.avg.toFixed(
					1
				)}% · max {runDrawdownTimeline.maxDd.toFixed(1)}%
			</p>
		</section>
	{/if}
	{#if runSharpeTimeline}
		<section class="rounded-xl border border-border bg-card p-4">
			<h2 class="mb-1 text-sm font-semibold">
				Sharpe Ratio Over Time <ChartInfo metric="sharpe" {lang} />
			</h2>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Sharpe ratio per backtest run ordered by import date · latest {runSharpeTimeline.latest.toFixed(
					2
				)} · avg {runSharpeTimeline.avg.toFixed(2)} · trend {runSharpeTimeline.trend > 0.1
					? '↑ improving'
					: runSharpeTimeline.trend < -0.1
						? '↓ declining'
						: '→ stable'}
			</p>
			<svg viewBox="0 0 {runSharpeTimeline.W} {runSharpeTimeline.H}" class="w-full">
				<line
					x1="0"
					y1={runSharpeTimeline.zeroY}
					x2={runSharpeTimeline.W}
					y2={runSharpeTimeline.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="1"
					stroke-dasharray="4,3"
				/>
				<line
					x1="0"
					y1={runSharpeTimeline.avgY}
					x2={runSharpeTimeline.W}
					y2={runSharpeTimeline.avgY}
					stroke="var(--ch-warn-light)"
					stroke-width="1"
					stroke-dasharray="4,3"
				/>
				<polyline
					points={runSharpeTimeline.polyline}
					fill="none"
					stroke="var(--ch-violet)"
					stroke-width="1.5"
				/>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{runSharpeTimeline.count} runs · yellow dashed = avg · white dashed = zero · rising trend = optimization
				improving risk-adjusted returns over time
			</p>
		</section>
	{/if}

	{#if runProfitFactorByTimeframe}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Profit Factor by Timeframe</h3>
			<p class="mb-3 text-[10px] text-muted-foreground">
				Median profit factor (gross profit ÷ gross loss) grouped by timeframe across all runs ·
				higher = better · count shows how many runs exist per timeframe
			</p>
			<div class="space-y-2">
				{#each runProfitFactorByTimeframe.rows as row, _i (_i)}
					<div class="flex items-center gap-2 text-xs">
						<span class="w-10 shrink-0 font-mono text-muted-foreground">{row.tf}</span>
						<div class="relative h-4 flex-1 overflow-hidden rounded bg-muted/30">
							<div
								class="h-full rounded"
								style="width:{((row.median / runProfitFactorByTimeframe.maxVal) * 100).toFixed(
									1
								)}%; background:rgba(34,197,94,{Math.min(
									0.85,
									0.3 + (row.median / runProfitFactorByTimeframe.maxVal) * 0.55
								)})"
							></div>
						</div>
						<span class="w-12 text-right font-mono">{row.median.toFixed(2)}</span>
						<span class="w-12 text-right text-[9px] text-muted-foreground">n={row.count}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				PF &gt; 1 = profitable · PF &gt; 1.5 = strong · best timeframe = {runProfitFactorByTimeframe
					.rows[0].tf} (median {runProfitFactorByTimeframe.rows[0].median.toFixed(2)})
			</p>
		</section>
	{/if}

	{#if runWinRateByTimeframe}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Median Win Rate by Timeframe</h3>
			<p class="mb-3 text-[10px] text-muted-foreground">
				Median win_rate_pct across all backtest runs grouped by timeframe · reveals which timeframes
				produce the most consistent accuracy for this strategy
			</p>
			<div class="space-y-2">
				{#each runWinRateByTimeframe.rows as row, _i (_i)}
					{@const pct = (row.median / runWinRateByTimeframe.maxVal) * 100}
					<div class="flex items-center gap-2 text-xs">
						<span class="w-10 shrink-0 font-mono text-muted-foreground">{row.tf}</span>
						<div class="relative h-4 flex-1 overflow-hidden rounded bg-muted/30">
							<div
								class="h-full rounded"
								style="width:{pct.toFixed(1)}%; background:rgba(99,102,241,{Math.min(
									0.85,
									0.3 + (pct / 100) * 0.55
								)})"
							></div>
						</div>
						<span class="w-14 text-right font-mono">{row.median.toFixed(1)}%</span>
						<span class="w-20 text-right text-[9px] text-muted-foreground"
							>{row.min.toFixed(0)}–{row.max.toFixed(0)}% · n={row.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Best timeframe = {runWinRateByTimeframe.rows[0].tf} at {runWinRateByTimeframe.rows[0].median.toFixed(
					1
				)}% median win rate · range shows spread between best and worst run for that timeframe
			</p>
		</section>
	{/if}

	{#if runCalmarByTimeframe}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Median Calmar Ratio by Timeframe</h3>
			<p class="mb-3 text-[10px] text-muted-foreground">
				Median Calmar (annual return ÷ max drawdown) across runs grouped by timeframe · higher =
				better return per unit of drawdown risk · compare across timeframes to find sweet spot
			</p>
			<div class="space-y-2">
				{#each runCalmarByTimeframe.rows as row, _i (_i)}
					{@const color = row.median > 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					<div class="flex items-center gap-2 text-xs">
						<span class="w-10 shrink-0 font-mono text-muted-foreground">{row.tf}</span>
						<div class="relative h-4 flex-1 overflow-hidden rounded bg-muted/30">
							<div
								class="h-full rounded"
								style="width:{((Math.abs(row.median) / runCalmarByTimeframe.absMax) * 100).toFixed(
									1
								)}%; background:{color}"
							></div>
						</div>
						<span class="w-14 text-right font-mono" style="color:{color}"
							>{row.median.toFixed(2)}</span
						>
						<span class="w-10 text-right text-[9px] text-muted-foreground">n={row.count}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Best timeframe by Calmar = {runCalmarByTimeframe.rows[0].tf} (median {runCalmarByTimeframe.rows[0].median.toFixed(
					2
				)}) · Calmar &gt;1 = solid · &gt;2 = excellent risk-adjusted return
			</p>
		</section>
	{/if}

	{#if tradePairProfitDistribution}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Trade Profit Distribution by Top Pairs</h3>
			<p class="mb-3 text-[10px] text-muted-foreground">
				Histogram of trade profit % for the 5 most-traded pairs · right-skewed = occasional big
				winners · left-skewed = frequent small losses
			</p>
			<div class="space-y-3">
				{#each tradePairProfitDistribution.pairs as p, _i (_i)}
					<div>
						<div class="mb-1 flex items-center justify-between text-[10px]">
							<span class="font-mono font-medium">{p.pair}</span>
							<span class="text-muted-foreground"
								>{p.mn.toFixed(1)}% – {p.mx.toFixed(1)}% · n={p.n}</span
							>
						</div>
						<div class="flex h-8 w-full items-end gap-px overflow-hidden rounded">
							{#each p.buckets as b, _i (_i)}
								<div
									class="flex-1 rounded-t"
									style="height:{((b.count / p.maxCount) * 100).toFixed(0)}%; background:{b.lo >= 0
										? 'var(--ch-profit)'
										: 'var(--ch-loss)'}"
								></div>
							{/each}
						</div>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Green bars = profitable trade buckets · red = losing · bar height = trade count in that
				profit range · top 5 pairs by trade count shown
			</p>
		</section>
	{/if}

	{#if tradeAvgHoldingByMonth}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Monthly Avg Holding Time</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Average trade duration in minutes per calendar month · rising = strategy holding longer
				(regime shift or fewer signals) · dashed = overall average
			</p>
			<svg viewBox="0 0 {tradeAvgHoldingByMonth.W} {tradeAvgHoldingByMonth.H}" class="w-full">
				<line
					x1="0"
					y1={tradeAvgHoldingByMonth.avgY}
					x2={tradeAvgHoldingByMonth.W}
					y2={tradeAvgHoldingByMonth.avgY}
					stroke="var(--ch-axis-muted)"
					stroke-width="1"
					stroke-dasharray="4,3"
				/>
				{#each tradeAvgHoldingByMonth.bars as b, _i (_i)}
					<rect x={b.x} y={b.y} width={tradeAvgHoldingByMonth.barW} height={b.h} fill={b.color} />
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{tradeAvgHoldingByMonth.total} months · overall avg {(
					tradeAvgHoldingByMonth.globalAvg / 60
				).toFixed(1)}h · darker = longer holds · dashed = mean
			</p>
		</section>
	{/if}

	{#if tradeProfitByExitReason}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Avg Profit by Exit Reason</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Average profit % per trade grouped by exit reason · ROI exits should dominate positive side
				· stoploss exits reveal average loss size
			</p>
			<div class="space-y-1">
				{#each tradeProfitByExitReason.rows as row, _i (_i)}
					{@const color = row.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					{@const pct = ((Math.abs(row.avg) / tradeProfitByExitReason.maxAbs) * 50).toFixed(1)}
					<div class="flex items-center gap-2 text-[10px]">
						<span class="w-36 truncate font-mono text-[9px]">{row.reason}</span>
						<div class="relative flex h-3 flex-1 items-center">
							<div class="absolute left-1/2 h-full w-px bg-border opacity-40"></div>
							{#if row.avg >= 0}
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
							>{row.avg.toFixed(2)}%</span
						>
						<span class="w-10 text-right text-[9px] text-muted-foreground">n={row.count}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Bars diverge from center · positive = profitable exit type · negative = loss-generating ·
				high n on losing reason = systematic problem
			</p>
		</section>
	{/if}

	{#if tradeRunningPnlTimeline}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Cumulative P&amp;L Timeline</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Running sum of profit_abs across all trades sorted by close date · shows equity curve shape
				· drawdowns visible as dips
			</p>
			<svg viewBox="0 0 {tradeRunningPnlTimeline.W} {tradeRunningPnlTimeline.H}" class="w-full">
				{#if tradeRunningPnlTimeline.zeroY !== null}
					<line
						x1="0"
						y1={tradeRunningPnlTimeline.zeroY}
						x2={tradeRunningPnlTimeline.W}
						y2={tradeRunningPnlTimeline.zeroY}
						stroke="var(--ch-axis-muted)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				<polyline
					points={tradeRunningPnlTimeline.polyline}
					fill="none"
					stroke={tradeRunningPnlTimeline.color}
					stroke-width="1.5"
				/>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{tradeRunningPnlTimeline.count} trades · final P&amp;L {tradeRunningPnlTimeline.final} · range
				[{tradeRunningPnlTimeline.mn}–{tradeRunningPnlTimeline.mx}] · steep dips = drawdown periods
			</p>
		</section>
	{/if}

	{#if tradePairHoldingProfile}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Holding Time by Pair
			</h3>
			<div class="space-y-1">
				{#each tradePairHoldingProfile.rows as row, _i (_i)}
					{@const pct = ((row.avg / tradePairHoldingProfile.maxAvg) * 100).toFixed(1)}
					<div class="flex items-center gap-2">
						<span class="w-20 shrink-0 truncate text-[9px] text-muted-foreground">{row.pair}</span>
						<div class="relative h-3 flex-1 rounded bg-muted/30">
							<div
								class="absolute top-0 left-0 h-full rounded"
								style="width:{pct}%; background:var(--ch-violet)"
							></div>
						</div>
						<span class="w-12 text-right font-mono text-[9px] text-muted-foreground"
							>{tradePairHoldingProfile.toHrs(row.avg)}</span
						>
						<span class="w-10 text-right text-[9px] text-muted-foreground">n={row.count}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Avg trade duration per pair · longer holding = trend-following · short = mean-reversion ·
				pairs sorted by avg hold descending
			</p>
		</section>
	{/if}

	{#if tradeEntryTagProfitSummary}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Performance by Entry Tag
			</h3>
			<div class="space-y-1">
				{#each tradeEntryTagProfitSummary.rows as row, _i (_i)}
					{@const pct = ((Math.abs(row.avg) / tradeEntryTagProfitSummary.maxAbs) * 50).toFixed(1)}
					{@const isPos = row.avg >= 0}
					{@const color = isPos ? 'var(--ch-profit-strong)' : 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-24 shrink-0 truncate text-[9px] text-muted-foreground">{row.tag}</span>
						<div class="relative h-3 flex-1 rounded bg-muted/20">
							{#if isPos}
								<div
									class="absolute top-0 left-1/2 h-full rounded-r"
									style="width:{pct}%; background:{color}"
								></div>
							{:else}
								<div
									class="absolute top-0 h-full rounded-l"
									style="right:50%; width:{pct}%; background:{color}"
								></div>
							{/if}
						</div>
						<span class="w-14 text-right font-mono text-[9px]" style="color:{color}"
							>{row.avg.toFixed(3)}%</span
						>
						<span class="w-10 text-right text-[9px] text-muted-foreground"
							>{row.winRate.toFixed(0)}%WR</span
						>
						<span class="w-6 text-right text-[9px] text-muted-foreground">n={row.count}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Avg profit per entry signal tag · WR = win rate · identify which signals are most profitable
				for this strategy
			</p>
		</section>
	{/if}

	{#if tradeExitReasonProfitProfile}
		<section class="rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Exit Reason Profit Profile
			</h3>
			<div class="space-y-1.5">
				{#each tradeExitReasonProfitProfile.rows as row, _i (_i)}
					{@const pct = Math.abs(row.avg) / tradeExitReasonProfitProfile.maxAbs}
					{@const color = row.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-28 truncate text-right font-mono text-[10px] text-muted-foreground"
							>{row.reason}</span
						>
						<div class="relative flex h-4 flex-1 items-center">
							<div class="absolute left-1/2 h-full w-px bg-border/40"></div>
							{#if row.avg >= 0}
								<div
									class="absolute left-1/2 h-3 rounded-r-sm"
									style="width:{(pct * 50).toFixed(1)}%; background:{color}"
								></div>
							{:else}
								<div
									class="absolute right-1/2 h-3 rounded-l-sm"
									style="width:{(pct * 50).toFixed(1)}%; background:{color}"
								></div>
							{/if}
						</div>
						<span
							class="w-14 text-right text-[10px]"
							style="color:{row.avg >= 0 ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
							>{row.avg >= 0 ? '+' : ''}{row.avg.toFixed(2)}%</span
						>
						<span class="w-10 text-right text-[9px] text-muted-foreground"
							>WR {row.wr.toFixed(0)}%</span
						>
						<span class="w-8 text-right text-[9px] text-muted-foreground">n={row.count}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Avg profit per exit reason · diverging bars from center · n = number of trades · helps
				identify which exit types drive returns
			</p>
		</section>
	{/if}

	{#if tradeProfitByMonth}
		<section class="rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Monthly Avg Trade Profit (last 12m)
			</h3>
			<svg
				viewBox="0 0 {tradeProfitByMonth.W} {tradeProfitByMonth.H}"
				class="w-full"
				style="height:80px"
			>
				<line
					x1="0"
					y1={tradeProfitByMonth.H / 2}
					x2={tradeProfitByMonth.W}
					y2={tradeProfitByMonth.H / 2}
					stroke="var(--ch-axis-faint)"
					stroke-width="1"
				/>
				{#each tradeProfitByMonth.rows as row, i (i)}
					{@const x =
						tradeProfitByMonth.PAD +
						i *
							((tradeProfitByMonth.W - tradeProfitByMonth.PAD * 2) /
								tradeProfitByMonth.rows.length)}
					{@const midY = tradeProfitByMonth.H / 2}
					{@const barH = Math.max(
						1,
						(Math.abs(row.avg) / tradeProfitByMonth.maxAbs) * (midY - tradeProfitByMonth.PAD - 6)
					)}
					{@const color = row.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					{#if row.avg >= 0}
						<rect
							{x}
							y={midY - barH}
							width={tradeProfitByMonth.barW}
							height={barH}
							rx="1"
							fill={color}
						/>
					{:else}
						<rect {x} y={midY} width={tradeProfitByMonth.barW} height={barH} rx="1" fill={color} />
					{/if}
					<text
						x={x + tradeProfitByMonth.barW / 2}
						y={tradeProfitByMonth.H - 2}
						text-anchor="middle"
						font-size="7"
						fill="var(--ch-axis)">{row.mo}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg trade profit % per calendar month · green = positive · red = negative · bars above/below
				center · last 12 months of closed trades
			</p>
		</section>
	{/if}

	{#if tradeStakeSizeDistribution}
		<section class="rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Stake Size Distribution
			</h3>
			<svg
				viewBox="0 0 {tradeStakeSizeDistribution.W} {tradeStakeSizeDistribution.H}"
				class="w-full"
				style="height:70px"
			>
				{#each tradeStakeSizeDistribution.counts as b, i (i)}
					{@const x = tradeStakeSizeDistribution.PAD + i * (tradeStakeSizeDistribution.barW + 1)}
					{@const barH = Math.max(
						1,
						(b.count / tradeStakeSizeDistribution.maxCount) *
							(tradeStakeSizeDistribution.H - tradeStakeSizeDistribution.PAD * 2 - 8)
					)}
					<rect
						{x}
						y={tradeStakeSizeDistribution.H - 8 - barH}
						width={tradeStakeSizeDistribution.barW}
						height={barH}
						rx="1"
						fill="var(--ch-violet)"
					/>
					{#if i === 0 || i === tradeStakeSizeDistribution.counts.length - 1}
						<text
							x={x + tradeStakeSizeDistribution.barW / 2}
							y={tradeStakeSizeDistribution.H - 1}
							text-anchor="middle"
							font-size="7"
							fill="var(--ch-axis)">{b.label}</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Histogram of stake_amount per trade · range ${tradeStakeSizeDistribution.mn}–${tradeStakeSizeDistribution.mx}
				USDT · shows DCA scaling effect on position sizes
			</p>
		</section>
	{/if}

	{#if tradeWinLossStreakTimeline}
		<section class="rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win/Loss Streak Timeline (last 60 trades)
			</h3>
			<svg
				viewBox="0 0 {tradeWinLossStreakTimeline.W} {tradeWinLossStreakTimeline.H}"
				class="w-full"
				style="height:60px"
			>
				<line
					x1="0"
					y1={tradeWinLossStreakTimeline.H / 2}
					x2={tradeWinLossStreakTimeline.W}
					y2={tradeWinLossStreakTimeline.H / 2}
					stroke="var(--ch-axis-faint)"
					stroke-width="1"
				/>
				{#each tradeWinLossStreakTimeline.pts as pt, i (i)}
					{@const x = tradeWinLossStreakTimeline.PAD + i * (tradeWinLossStreakTimeline.barW + 1)}
					{@const midY = tradeWinLossStreakTimeline.H / 2}
					{@const barH = Math.max(
						1,
						(Math.abs(pt.streak) / tradeWinLossStreakTimeline.maxStreak) *
							(midY - tradeWinLossStreakTimeline.PAD - 2)
					)}
					{@const color = pt.win ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					{#if pt.win}
						<rect
							{x}
							y={midY - barH}
							width={tradeWinLossStreakTimeline.barW}
							height={barH}
							fill={color}
						/>
					{:else}
						<rect {x} y={midY} width={tradeWinLossStreakTimeline.barW} height={barH} fill={color} />
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Running win/loss streak length per trade · green = consecutive wins · red = consecutive
				losses · height = streak length · chronological order
			</p>
		</section>
	{/if}

	{#if tradeProfitByPair}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit by Pair
			</h3>
			<svg
				viewBox="0 0 {tradeProfitByPair.W} {tradeProfitByPair.H}"
				class="w-full"
				style="height:{tradeProfitByPair.H}px"
			>
				<line
					x1={tradeProfitByPair.midX}
					y1={tradeProfitByPair.PAD}
					x2={tradeProfitByPair.midX}
					y2={tradeProfitByPair.H - tradeProfitByPair.PAD}
					stroke="var(--ch-axis-muted)"
					stroke-width="0.8"
				/>
				{#each tradeProfitByPair.rows as row, i (i)}
					{@const cy = tradeProfitByPair.PAD + i * 14 + 7}
					{@const bw = (Math.abs(row.avg) / tradeProfitByPair.maxAbs) * tradeProfitByPair.barMaxW}
					{@const positive = row.avg >= 0}
					{@const color = positive ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					<rect
						x={positive ? tradeProfitByPair.midX : tradeProfitByPair.midX - bw}
						y={cy - 5}
						width={bw}
						height={10}
						rx="1"
						fill={color}
					/>
					<text
						x={tradeProfitByPair.midX - 4}
						y={cy + 3.5}
						text-anchor="end"
						font-size="7"
						fill="var(--ch-axis-strong)">{row.pair}</text
					>
					<text x={tradeProfitByPair.midX + bw + 3} y={cy + 3.5} font-size="7" fill={color}
						>{row.avg >= 0 ? '+' : ''}{row.avg.toFixed(2)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg profit % per pair across all backtest trades · green = net profitable · red = net losing
				· identifies strongest and weakest pairs
			</p>
		</section>
	{/if}

	{#if tradeHoldingTimeHistogram}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Trade Holding Time Distribution
			</h3>
			<svg
				viewBox="0 0 {tradeHoldingTimeHistogram.W} {tradeHoldingTimeHistogram.H}"
				class="w-full"
				style="height:70px"
			>
				{#each tradeHoldingTimeHistogram.counts as b, i (i)}
					{@const x = tradeHoldingTimeHistogram.PAD + i * (tradeHoldingTimeHistogram.barW + 1)}
					{@const barH = Math.max(
						1,
						(b.count / tradeHoldingTimeHistogram.maxCount) *
							(tradeHoldingTimeHistogram.H - tradeHoldingTimeHistogram.PAD * 2 - 8)
					)}
					<rect
						{x}
						y={tradeHoldingTimeHistogram.H - 8 - barH}
						width={tradeHoldingTimeHistogram.barW}
						height={barH}
						rx="1"
						fill="var(--ch-violet)"
					/>
				{/each}
				<text
					x={tradeHoldingTimeHistogram.PAD}
					y={tradeHoldingTimeHistogram.H - 1}
					font-size="7"
					fill="var(--ch-axis)">0h</text
				>
				<text
					x={tradeHoldingTimeHistogram.W - tradeHoldingTimeHistogram.PAD}
					y={tradeHoldingTimeHistogram.H - 1}
					text-anchor="end"
					font-size="7"
					fill="var(--ch-axis)">{tradeHoldingTimeHistogram.mx}h+</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{tradeHoldingTimeHistogram.total} trades · avg {tradeHoldingTimeHistogram.avgH}h ·
				distribution of trade durations · peaked short = scalp-like · peaked long = swing-like
			</p>
		</section>
	{/if}

	{#if tradeMonthlyProfitHeatmap}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Monthly Avg Trade Profit (last 12 months)
			</h3>
			<svg
				viewBox="0 0 {tradeMonthlyProfitHeatmap.W} {tradeMonthlyProfitHeatmap.H}"
				class="w-full"
				style="height:60px"
			>
				<line
					x1={tradeMonthlyProfitHeatmap.PAD}
					y1={tradeMonthlyProfitHeatmap.midY}
					x2={tradeMonthlyProfitHeatmap.W - tradeMonthlyProfitHeatmap.PAD}
					y2={tradeMonthlyProfitHeatmap.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.8"
				/>
				{#each tradeMonthlyProfitHeatmap.rows as row, i (i)}
					{@const x =
						tradeMonthlyProfitHeatmap.PAD +
						i *
							((tradeMonthlyProfitHeatmap.W - tradeMonthlyProfitHeatmap.PAD * 2) /
								tradeMonthlyProfitHeatmap.rows.length)}
					{@const barH = Math.max(
						1,
						(Math.abs(row.avg) / tradeMonthlyProfitHeatmap.maxAbs) *
							(tradeMonthlyProfitHeatmap.midY - tradeMonthlyProfitHeatmap.PAD - 2)
					)}
					{@const color = row.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					{#if row.avg >= 0}
						<rect
							{x}
							y={tradeMonthlyProfitHeatmap.midY - barH}
							width={tradeMonthlyProfitHeatmap.barW}
							height={barH}
							fill={color}
							rx="1"
						/>
					{:else}
						<rect
							{x}
							y={tradeMonthlyProfitHeatmap.midY}
							width={tradeMonthlyProfitHeatmap.barW}
							height={barH}
							fill={color}
							rx="1"
						/>
					{/if}
					<text
						x={x + tradeMonthlyProfitHeatmap.barW / 2}
						y={tradeMonthlyProfitHeatmap.H - 1}
						text-anchor="middle"
						font-size="6.5"
						fill="var(--ch-axis)">{row.label}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg trade profit % per calendar month · green = net positive month · red = net negative ·
				shows seasonal patterns across the last year
			</p>
		</section>
	{/if}

	{#if tradeEntryHourDistribution}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Trade Entry by UTC Hour
			</h3>
			<svg
				viewBox="0 0 {tradeEntryHourDistribution.W} {tradeEntryHourDistribution.H}"
				class="w-full"
				style="height:65px"
			>
				{#each tradeEntryHourDistribution.counts as c, i (i)}
					{@const x = tradeEntryHourDistribution.PAD + i * (tradeEntryHourDistribution.barW + 1)}
					{@const barH = Math.max(
						1,
						(c.count / tradeEntryHourDistribution.maxCount) *
							(tradeEntryHourDistribution.H - tradeEntryHourDistribution.PAD * 2 - 10)
					)}
					{@const avgP = c.count > 0 ? c.profitSum / c.count : 0}
					{@const color = avgP >= 0 ? 'var(--ch-violet)' : 'var(--ch-loss)'}
					<rect
						{x}
						y={tradeEntryHourDistribution.H - 10 - barH}
						width={tradeEntryHourDistribution.barW}
						height={barH}
						rx="1"
						fill={color}
					/>
					{#if i % 6 === 0}
						<text
							x={x + tradeEntryHourDistribution.barW / 2}
							y={tradeEntryHourDistribution.H - 1}
							text-anchor="middle"
							font-size="7"
							fill="var(--ch-axis)">{String(i).padStart(2, '0')}h</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Trade entries per UTC hour (0–23) · bar height = trade count · color = avg profit sign at
				that hour · reveals intraday timing bias
			</p>
		</section>
	{/if}

	{#if tradeProfitQuantiles}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Trade Profit % Distribution — Box Plot ({tradeProfitQuantiles.count} trades)
			</h3>
			<svg
				viewBox="0 0 {tradeProfitQuantiles.W} {tradeProfitQuantiles.H}"
				class="w-full"
				style="height:60px"
			>
				<!-- whiskers -->
				<line
					x1={tradeProfitQuantiles.toX(tradeProfitQuantiles.p5)}
					y1={tradeProfitQuantiles.midY}
					x2={tradeProfitQuantiles.toX(tradeProfitQuantiles.p25)}
					y2={tradeProfitQuantiles.midY}
					stroke="var(--ch-axis-muted)"
					stroke-width="1.5"
				/>
				<line
					x1={tradeProfitQuantiles.toX(tradeProfitQuantiles.p75)}
					y1={tradeProfitQuantiles.midY}
					x2={tradeProfitQuantiles.toX(tradeProfitQuantiles.p95)}
					y2={tradeProfitQuantiles.midY}
					stroke="var(--ch-axis-muted)"
					stroke-width="1.5"
				/>
				<!-- IQR box -->
				<rect
					x={tradeProfitQuantiles.toX(tradeProfitQuantiles.p25)}
					y={tradeProfitQuantiles.midY - 10}
					width={tradeProfitQuantiles.toX(tradeProfitQuantiles.p75) -
						tradeProfitQuantiles.toX(tradeProfitQuantiles.p25)}
					height={20}
					rx="2"
					fill={tradeProfitQuantiles.p50 >= 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)'}
					stroke={tradeProfitQuantiles.p50 >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					stroke-width="1"
				/>
				<!-- median line -->
				<line
					x1={tradeProfitQuantiles.toX(tradeProfitQuantiles.p50)}
					y1={tradeProfitQuantiles.midY - 10}
					x2={tradeProfitQuantiles.toX(tradeProfitQuantiles.p50)}
					y2={tradeProfitQuantiles.midY + 10}
					stroke="var(--ch-warn)"
					stroke-width="2"
				/>
				<!-- zero line -->
				{#if tradeProfitQuantiles.mn < 0 && tradeProfitQuantiles.mx > 0}
					<line
						x1={tradeProfitQuantiles.toX(0)}
						y1={tradeProfitQuantiles.midY - 14}
						x2={tradeProfitQuantiles.toX(0)}
						y2={tradeProfitQuantiles.midY + 14}
						stroke="var(--ch-axis-muted)"
						stroke-width="0.8"
						stroke-dasharray="3,2"
					/>
				{/if}
				<text
					x={tradeProfitQuantiles.toX(tradeProfitQuantiles.p5)}
					y={tradeProfitQuantiles.H - 2}
					text-anchor="middle"
					font-size="6.5"
					fill="var(--ch-axis)">{tradeProfitQuantiles.p5.toFixed(1)}%</text
				>
				<text
					x={tradeProfitQuantiles.toX(tradeProfitQuantiles.p50)}
					y={6}
					text-anchor="middle"
					font-size="6.5"
					fill="var(--ch-warn)">p50 {tradeProfitQuantiles.p50.toFixed(1)}%</text
				>
				<text
					x={tradeProfitQuantiles.toX(tradeProfitQuantiles.p95)}
					y={tradeProfitQuantiles.H - 2}
					text-anchor="middle"
					font-size="6.5"
					fill="var(--ch-axis)">{tradeProfitQuantiles.p95.toFixed(1)}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Box = IQR (p25–p75) · yellow line = median · whiskers = p5–p95 · positive median = more than
				half of trades are profitable
			</p>
		</section>
	{/if}

	{#if tradePairWinLossBalance}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win/Loss Balance by Pair (top {tradePairWinLossBalance.rows.length} by win rate)
			</h3>
			<svg
				viewBox="0 0 {tradePairWinLossBalance.W} {tradePairWinLossBalance.H}"
				class="w-full"
				style="height:90px"
			>
				{#each tradePairWinLossBalance.rows as row, i (i)}
					{@const y = tradePairWinLossBalance.PAD + i * (tradePairWinLossBalance.barH + 2)}
					{@const winW =
						(row.wins / row.total) *
						(tradePairWinLossBalance.W - tradePairWinLossBalance.PAD * 2 - 45)}
					{@const lossW =
						(row.losses / row.total) *
						(tradePairWinLossBalance.W - tradePairWinLossBalance.PAD * 2 - 45)}
					<text
						x={tradePairWinLossBalance.PAD}
						y={y + tradePairWinLossBalance.barH - 1}
						font-size="6.5"
						fill="var(--ch-axis)">{row.pair}</text
					>
					<rect
						x={tradePairWinLossBalance.PAD + 30}
						{y}
						width={winW}
						height={tradePairWinLossBalance.barH}
						rx="1"
						fill="var(--ch-profit)"
					/>
					<rect
						x={tradePairWinLossBalance.PAD + 30 + winW}
						{y}
						width={lossW}
						height={tradePairWinLossBalance.barH}
						rx="1"
						fill="var(--ch-loss-light)"
					/>
					<text
						x={tradePairWinLossBalance.W - tradePairWinLossBalance.PAD + 2}
						y={y + tradePairWinLossBalance.barH - 1}
						font-size="6"
						fill="var(--ch-axis)">{row.wr.toFixed(0)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Green=wins · red=losses · sorted by win rate desc · pairs with more green have better hit
				rates for this strategy
			</p>
		</section>
	{/if}

	{#if tradeExitReasonHoldingTime}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Median Holding Time by Exit Reason
			</h3>
			<div class="space-y-1.5">
				{#each tradeExitReasonHoldingTime.rows as row, i (i)}
					{@const pct = ((row.med / tradeExitReasonHoldingTime.maxMed) * 100).toFixed(1)}
					{@const label =
						row.med >= 24 ? `${(row.med / 24).toFixed(1)}d` : `${row.med.toFixed(1)}h`}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right text-[9px] text-muted-foreground">{i + 1}.</span>
						<span class="w-32 truncate text-[9px] text-muted-foreground">{row.tag}</span>
						<div class="h-3 flex-1 overflow-hidden rounded bg-muted/20">
							<div class="h-full rounded" style="width:{pct}%; background:var(--ch-violet)"></div>
						</div>
						<span class="w-10 text-right font-mono text-[10px] text-muted-foreground">{label}</span>
						<span class="w-6 text-right text-[9px] text-muted-foreground">{row.count}t</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Median hold time per exit type · long-held exits may be stoploss or trailing · short-held =
				ROI or signal-based exits · reveals exit mechanism patterns
			</p>
		</section>
	{/if}
	{#if tradeDowAvgProfitBars}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit % by Day of Week (entry UTC)
			</h3>
			<svg
				viewBox="0 0 {tradeDowAvgProfitBars.W} {tradeDowAvgProfitBars.H}"
				class="w-full"
				style="height:70px"
			>
				<line
					x1={tradeDowAvgProfitBars.PAD}
					y1={tradeDowAvgProfitBars.midY}
					x2={tradeDowAvgProfitBars.W - tradeDowAvgProfitBars.PAD}
					y2={tradeDowAvgProfitBars.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each tradeDowAvgProfitBars.rows as row, i (i)}
					{@const x = tradeDowAvgProfitBars.PAD + i * (tradeDowAvgProfitBars.barW + 2)}
					{@const bh = tradeDowAvgProfitBars.toH(row.avg)}
					{@const color = row.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					{@const y = row.avg >= 0 ? tradeDowAvgProfitBars.midY - bh : tradeDowAvgProfitBars.midY}
					<rect {x} {y} width={tradeDowAvgProfitBars.barW} height={bh} rx="1" fill={color} />
					<text
						x={x + tradeDowAvgProfitBars.barW / 2}
						y={tradeDowAvgProfitBars.H - 1}
						text-anchor="middle"
						font-size="6.5"
						fill="var(--ch-axis)">{row.label}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg trade profit by entry day (UTC) · green=positive · red=negative · reveals which weekdays
				produce better entries for this strategy
			</p>
		</section>
	{/if}
	{#if tradeCumProfitByExitReason}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Cumulative Profit by Exit Reason (top {tradeCumProfitByExitReason.polylines.length})
			</h3>
			<svg
				viewBox="0 0 {tradeCumProfitByExitReason.W} {tradeCumProfitByExitReason.H}"
				class="w-full"
				style="height:85px"
			>
				<line
					x1={tradeCumProfitByExitReason.PAD}
					y1={tradeCumProfitByExitReason.zeroY}
					x2={tradeCumProfitByExitReason.W - tradeCumProfitByExitReason.PAD}
					y2={tradeCumProfitByExitReason.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.8"
					stroke-dasharray="3,2"
				/>
				{#each tradeCumProfitByExitReason.polylines as line, _i (_i)}
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
				{#each tradeCumProfitByExitReason.polylines as line, _i (_i)}
					<span class="text-[9px]" style="color:{line.color}">■ {line.reason}</span>
				{/each}
				<span class="text-[9px] text-muted-foreground"
					>· rising line = exit reason accumulating gains · reveals which exit mechanism drives
					returns</span
				>
			</div>
		</section>
	{/if}
	{#if tradeMonthlyWinRateTrend}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Monthly Win Rate Trend ({tradeMonthlyWinRateTrend.pts.length} months)
			</h3>
			<svg
				viewBox="0 0 {tradeMonthlyWinRateTrend.W} {tradeMonthlyWinRateTrend.H}"
				class="w-full"
				style="height:70px"
			>
				<line
					x1={tradeMonthlyWinRateTrend.PAD}
					y1={tradeMonthlyWinRateTrend.y50}
					x2={tradeMonthlyWinRateTrend.W - tradeMonthlyWinRateTrend.PAD}
					y2={tradeMonthlyWinRateTrend.y50}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				<polygon points={tradeMonthlyWinRateTrend.area} fill="var(--ch-profit-light)" />
				<polyline
					points={tradeMonthlyWinRateTrend.poly}
					fill="none"
					stroke="var(--ch-profit)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				{#each tradeMonthlyWinRateTrend.pts as p, i (i)}
					{#if i % Math.max(1, Math.floor(tradeMonthlyWinRateTrend.pts.length / 6)) === 0}
						{@const x =
							tradeMonthlyWinRateTrend.PAD +
							(i / Math.max(tradeMonthlyWinRateTrend.pts.length - 1, 1)) *
								(tradeMonthlyWinRateTrend.W - tradeMonthlyWinRateTrend.PAD * 2)}
						<text
							{x}
							y={tradeMonthlyWinRateTrend.H - 1}
							text-anchor="middle"
							font-size="6.5"
							fill="var(--ch-axis-muted)">{p.mo}</text
						>
					{/if}
				{/each}
				<text
					x={tradeMonthlyWinRateTrend.PAD}
					y={tradeMonthlyWinRateTrend.y50 - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">50%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				% of trades closed at profit each month · above dashed 50% = more wins than losses · area
				fill shows trend · reveals consistency of strategy win rate over time
			</p>
		</section>
	{/if}
	{#if tradePairProfitHeatmap}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Pair × Month Avg Profit Heatmap
			</h3>
			<svg
				viewBox="0 0 {tradePairProfitHeatmap.W} {tradePairProfitHeatmap.H}"
				class="w-full"
				style="height:{tradePairProfitHeatmap.H}px"
			>
				{#each tradePairProfitHeatmap.recentMonths as mo, mi (mi)}
					<text
						x={tradePairProfitHeatmap.PAD +
							80 +
							mi * tradePairProfitHeatmap.CW +
							tradePairProfitHeatmap.CW / 2}
						y={tradePairProfitHeatmap.PAD + 8}
						text-anchor="middle"
						font-size="6"
						fill="var(--ch-axis-muted)">{mo.slice(5)}</text
					>
				{/each}
				{#each tradePairProfitHeatmap.topPairs as pair, pi (pi)}
					{@const y = tradePairProfitHeatmap.PAD + 12 + pi * tradePairProfitHeatmap.CH}
					<text
						x={tradePairProfitHeatmap.PAD}
						y={y + tradePairProfitHeatmap.CH - 3}
						font-size="6.5"
						fill="var(--ch-axis-strong)">{pair.slice(0, 10)}</text
					>
					{#each tradePairProfitHeatmap.recentMonths, mi (mi)}
						{@const val = tradePairProfitHeatmap.grid[pi][mi]}
						{@const x = tradePairProfitHeatmap.PAD + 80 + mi * tradePairProfitHeatmap.CW}
						{@const alpha =
							val == null
								? 0
								: Math.min(0.85, 0.15 + (Math.abs(val) / tradePairProfitHeatmap.maxAbs) * 0.7)}
						{@const fill =
							val == null
								? 'var(--ch-axis-faint)'
								: val >= 0
									? `rgba(34,197,94,${alpha})`
									: `rgba(239,68,68,${alpha})`}
						<rect
							{x}
							{y}
							width={tradePairProfitHeatmap.CW - 2}
							height={tradePairProfitHeatmap.CH - 2}
							rx="1"
							{fill}
						/>
						{#if val != null}
							<text
								x={x + tradePairProfitHeatmap.CW / 2}
								y={y + tradePairProfitHeatmap.CH - 4}
								text-anchor="middle"
								font-size="5.5"
								fill="var(--ch-axis-strong)">{val >= 0 ? '+' : ''}{val.toFixed(1)}</text
							>
						{/if}
					{/each}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg profit % per pair per month (last 6 months · top 6 pairs) · green=positive ·
				red=negative · darker=stronger signal · identifies which pairs drive returns each month
			</p>
		</section>
	{/if}
	{#if tradeExitReasonWinRate}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win Rate by Exit Reason
			</h3>
			<svg
				viewBox="0 0 {tradeExitReasonWinRate.W} {tradeExitReasonWinRate.H}"
				class="w-full"
				style="height:{tradeExitReasonWinRate.H}px"
			>
				<line
					x1={140 + tradeExitReasonWinRate.barMaxW * 0.5}
					y1="0"
					x2={140 + tradeExitReasonWinRate.barMaxW * 0.5}
					y2={tradeExitReasonWinRate.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="2,2"
				/>
				{#each tradeExitReasonWinRate.rows as row, i (i)}
					{@const y = i * 16 + 2}
					{@const bw = Math.max(2, (row.wr / 100) * tradeExitReasonWinRate.barMaxW)}
					{@const color =
						row.wr >= 60 ? 'var(--ch-profit)' : row.wr >= 45 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<text x="0" y={y + 9} font-size="7" fill="var(--ch-axis-strong)">{row.reason}</text>
					<rect x="140" {y} width={bw} height="11" rx="2" fill={color} />
					<text x={140 + bw + 3} y={y + 9} font-size="7" fill={color}>{row.wr.toFixed(0)}%</text>
					<text
						x={tradeExitReasonWinRate.W - 2}
						y={y + 9}
						text-anchor="end"
						font-size="6"
						fill="var(--ch-axis-muted)">{row.total}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				% profitable trades per exit reason · green≥60% · yellow≥45% · red&lt;45% · dashed = 50% ·
				count shown right · reveals which exit signals actually produce winning trades
			</p>
		</section>
	{/if}
	{#if tradeProfitBySizeQuartile}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit by Stake Size Quartile
			</h3>
			<svg
				viewBox="0 0 {tradeProfitBySizeQuartile.W} {tradeProfitBySizeQuartile.H}"
				class="w-full"
				style="height:72px"
			>
				<line
					x1={tradeProfitBySizeQuartile.PAD}
					y1={tradeProfitBySizeQuartile.midY}
					x2={tradeProfitBySizeQuartile.W - tradeProfitBySizeQuartile.PAD}
					y2={tradeProfitBySizeQuartile.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each tradeProfitBySizeQuartile.rows as row, i (i)}
					{@const x = tradeProfitBySizeQuartile.PAD + i * (tradeProfitBySizeQuartile.barW + 4)}
					{@const bh = Math.max(
						2,
						(Math.abs(row.avg) / tradeProfitBySizeQuartile.maxAbs) *
							(tradeProfitBySizeQuartile.midY - tradeProfitBySizeQuartile.PAD)
					)}
					{@const color = row.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					<rect
						{x}
						y={row.avg >= 0 ? tradeProfitBySizeQuartile.midY - bh : tradeProfitBySizeQuartile.midY}
						width={tradeProfitBySizeQuartile.barW}
						height={bh}
						rx="1"
						fill={color}
					/>
					<text
						x={x + tradeProfitBySizeQuartile.barW / 2}
						y={tradeProfitBySizeQuartile.H - 8}
						text-anchor="middle"
						font-size="6"
						fill="var(--ch-axis)">{row.label}</text
					>
					<text
						x={x + tradeProfitBySizeQuartile.barW / 2}
						y={tradeProfitBySizeQuartile.H - 1}
						text-anchor="middle"
						font-size="5.5"
						fill="var(--ch-axis-muted)">{row.wr.toFixed(0)}%wr</text
					>
					<text
						x={x + tradeProfitBySizeQuartile.barW / 2}
						y={row.avg >= 0
							? tradeProfitBySizeQuartile.midY - bh - 2
							: tradeProfitBySizeQuartile.midY + bh + 7}
						text-anchor="middle"
						font-size="6"
						fill={color}>{row.avg >= 0 ? '+' : ''}{row.avg.toFixed(2)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Trades split into 4 equal quartiles by stake size · avg profit % per quartile · %wr = win
				rate · reveals whether larger or smaller position sizes perform better
			</p>
		</section>
	{/if}

	{#if tradeDowHourHeatmap && tradeDowHourHeatmap.count > 0}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Exit Activity Heatmap — Day × 4h Block
			</h3>
			<svg
				viewBox="0 0 {tradeDowHourHeatmap.W} {tradeDowHourHeatmap.H}"
				class="w-full"
				style="height:90px"
			>
				{#each tradeDowHourHeatmap.DAYS as day, row (row)}
					<text
						x="0"
						y={10 + row * tradeDowHourHeatmap.cellH + tradeDowHourHeatmap.cellH / 2}
						font-size="6.5"
						fill="var(--ch-axis)"
						dominant-baseline="middle">{day}</text
					>
					{#each tradeDowHourHeatmap.HOURS, col (col)}
						{@const val = tradeDowHourHeatmap.grid[row][col]}
						{@const alpha = val === 0 ? 0.04 : 0.12 + (val / tradeDowHourHeatmap.maxVal) * 0.72}
						<rect
							x={30 + col * tradeDowHourHeatmap.cellW + 1}
							y={row * tradeDowHourHeatmap.cellH + 2}
							width={tradeDowHourHeatmap.cellW - 2}
							height={tradeDowHourHeatmap.cellH - 2}
							rx="2"
							fill="rgba(99,102,241,{alpha})"
						/>
						{#if val > 0}
							<text
								x={30 + col * tradeDowHourHeatmap.cellW + tradeDowHourHeatmap.cellW / 2}
								y={row * tradeDowHourHeatmap.cellH + tradeDowHourHeatmap.cellH / 2 + 2}
								text-anchor="middle"
								font-size="5.5"
								fill="var(--ch-axis-strong)"
								dominant-baseline="middle">{val}</text
							>
						{/if}
					{/each}
				{/each}
				{#each tradeDowHourHeatmap.HOURS as h, col (col)}
					<text
						x={30 + col * tradeDowHourHeatmap.cellW + tradeDowHourHeatmap.cellW / 2}
						y={tradeDowHourHeatmap.H - 1}
						text-anchor="middle"
						font-size="5.5"
						fill="var(--ch-axis-muted)">{String(h).padStart(2, '0')}h</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Trade exit count by day-of-week × 4h UTC block · darker = more exits · reveals when this
				strategy is most active
			</p>
		</section>
	{/if}

	{#if tradeMonthlyProfitBars}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Monthly Avg Profit ({tradeMonthlyProfitBars.count} months)
			</h3>
			<svg
				viewBox="0 0 {tradeMonthlyProfitBars.W} {tradeMonthlyProfitBars.H}"
				class="w-full"
				style="height:72px"
			>
				<line
					x1={tradeMonthlyProfitBars.PAD}
					y1={tradeMonthlyProfitBars.midY}
					x2={tradeMonthlyProfitBars.W - tradeMonthlyProfitBars.PAD}
					y2={tradeMonthlyProfitBars.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each tradeMonthlyProfitBars.bars as bar, i (i)}
					<rect
						x={bar.x}
						y={bar.avg >= 0 ? tradeMonthlyProfitBars.midY - bar.h : tradeMonthlyProfitBars.midY}
						width={tradeMonthlyProfitBars.bw}
						height={bar.h}
						rx="1"
						fill={bar.color}
					/>
					{#if i % Math.max(1, Math.floor(tradeMonthlyProfitBars.bars.length / 7)) === 0}
						<text
							x={bar.x + tradeMonthlyProfitBars.bw / 2}
							y={tradeMonthlyProfitBars.H - 1}
							text-anchor="middle"
							font-size="5.5"
							fill="var(--ch-axis-muted)">{bar.mo}</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Monthly avg profit % per bar · green=positive · red=negative · diverging from zero baseline
				· reveals seasonal performance patterns for this strategy
			</p>
		</section>
	{/if}
	{#if tradeAvgProfitByPair}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit % by Pair
			</h3>
			<svg
				viewBox="0 0 {tradeAvgProfitByPair.W} {tradeAvgProfitByPair.H}"
				class="w-full"
				style="height:{tradeAvgProfitByPair.H}px"
			>
				<line
					x1={tradeAvgProfitByPair.zeroX}
					y1="0"
					x2={tradeAvgProfitByPair.zeroX}
					y2={tradeAvgProfitByPair.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each tradeAvgProfitByPair.rows as row, i (i)}
					{@const y = i * 16 + 2}
					{@const bw = Math.max(
						2,
						(Math.abs(row.avg) / tradeAvgProfitByPair.maxAbs) * (tradeAvgProfitByPair.barMaxW / 2)
					)}
					{@const x = row.avg >= 0 ? tradeAvgProfitByPair.zeroX : tradeAvgProfitByPair.zeroX - bw}
					{@const color =
						row.avg >= 0.5
							? 'var(--ch-profit)'
							: row.avg >= 0
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					<text x={tradeAvgProfitByPair.PAD} y={y + 10} font-size="7" fill="var(--ch-axis-strong)"
						>{row.pair}</text
					>
					<rect {x} {y} width={bw} height="12" rx="2" fill={color} />
					<text
						x={row.avg >= 0
							? tradeAvgProfitByPair.zeroX + bw + 3
							: tradeAvgProfitByPair.zeroX - bw - 3}
						y={y + 10}
						text-anchor={row.avg >= 0 ? 'start' : 'end'}
						font-size="7"
						fill={color}>{row.avg >= 0 ? '+' : ''}{row.avg.toFixed(2)}%</text
					>
					<text
						x={tradeAvgProfitByPair.W - 2}
						y={y + 10}
						text-anchor="end"
						font-size="6"
						fill="var(--ch-axis-muted)">{row.count}t</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg profit % per pair (min 2 trades) · diverging from center zero · green=positive avg ·
				red=negative avg · count=trades · reveals best and worst pairs for this strategy
			</p>
		</section>
	{/if}
	{#if tradeCumProfitTimeline}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Cumulative Profit % Over Time
			</h3>
			<svg
				viewBox="0 0 {tradeCumProfitTimeline.W} {tradeCumProfitTimeline.H}"
				class="w-full"
				style="height:{tradeCumProfitTimeline.H}px"
			>
				<line
					x1={tradeCumProfitTimeline.PAD}
					y1={tradeCumProfitTimeline.zeroY}
					x2={tradeCumProfitTimeline.W - tradeCumProfitTimeline.PAD}
					y2={tradeCumProfitTimeline.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				<polygon points={tradeCumProfitTimeline.area} fill={tradeCumProfitTimeline.fillColor} />
				<polyline
					points={tradeCumProfitTimeline.polyline}
					fill="none"
					stroke={tradeCumProfitTimeline.color}
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={tradeCumProfitTimeline.PAD}
					y={tradeCumProfitTimeline.H - 2}
					font-size="7"
					fill="var(--ch-axis-muted)">{tradeCumProfitTimeline.firstDate}</text
				>
				<text
					x={tradeCumProfitTimeline.W - tradeCumProfitTimeline.PAD}
					y={tradeCumProfitTimeline.H - 2}
					text-anchor="end"
					font-size="7"
					fill="var(--ch-axis-muted)">{tradeCumProfitTimeline.lastDate}</text
				>
				<text
					x={tradeCumProfitTimeline.W - tradeCumProfitTimeline.PAD}
					y={tradeCumProfitTimeline.PAD + 5}
					text-anchor="end"
					font-size="7"
					fill={tradeCumProfitTimeline.color}
					>{tradeCumProfitTimeline.finalCum >= 0
						? '+'
						: ''}{tradeCumProfitTimeline.finalCum.toFixed(1)}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Cumulative sum of trade profit % sorted by close date · green=net positive · red=net
				negative · zero baseline · reveals equity curve shape and drawdown periods for this strategy
			</p>
		</section>
	{/if}
	{#if tradeHoldTimeVsProfit}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Hold Time vs Profit %
			</h3>
			<svg
				viewBox="0 0 {tradeHoldTimeVsProfit.W} {tradeHoldTimeVsProfit.H}"
				class="w-full"
				style="height:{tradeHoldTimeVsProfit.H}px"
			>
				<line
					x1={tradeHoldTimeVsProfit.PAD}
					y1={tradeHoldTimeVsProfit.zeroY}
					x2={tradeHoldTimeVsProfit.W - tradeHoldTimeVsProfit.PAD}
					y2={tradeHoldTimeVsProfit.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each tradeHoldTimeVsProfit.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="1.6" fill={d.color} />
				{/each}
				<text
					x={tradeHoldTimeVsProfit.PAD}
					y={tradeHoldTimeVsProfit.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">0h</text
				>
				<text
					x={tradeHoldTimeVsProfit.W - tradeHoldTimeVsProfit.PAD}
					y={tradeHoldTimeVsProfit.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{tradeHoldTimeVsProfit.maxH}h</text
				>
				<text
					x={tradeHoldTimeVsProfit.W - tradeHoldTimeVsProfit.PAD}
					y={tradeHoldTimeVsProfit.PAD + 5}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{tradeHoldTimeVsProfit.maxP}%</text
				>
				<text
					x={tradeHoldTimeVsProfit.W - tradeHoldTimeVsProfit.PAD}
					y={tradeHoldTimeVsProfit.H - tradeHoldTimeVsProfit.PAD + 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{tradeHoldTimeVsProfit.minP}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				x=hold time (hours) · y=profit % · green=win · red=loss · zero baseline · reveals whether
				longer holds correlate with better or worse outcomes for this strategy
			</p>
		</section>
	{/if}
	{#if tradeWinRateByExitReason}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win Rate by Exit Reason
			</h3>
			<svg
				viewBox="0 0 {tradeWinRateByExitReason.W} {tradeWinRateByExitReason.H}"
				class="w-full"
				style="height:{tradeWinRateByExitReason.H}px"
			>
				<line
					x1={tradeWinRateByExitReason.PAD + tradeWinRateByExitReason.barMaxW / 2}
					y1="0"
					x2={tradeWinRateByExitReason.PAD + tradeWinRateByExitReason.barMaxW / 2}
					y2={tradeWinRateByExitReason.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each tradeWinRateByExitReason.rows as row, i (i)}
					{@const y = i * 16 + 2}
					{@const bw = Math.max(2, (row.wr / 100) * tradeWinRateByExitReason.barMaxW)}
					{@const color =
						row.wr >= 60 ? 'var(--ch-profit)' : row.wr >= 50 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<text
						x={tradeWinRateByExitReason.PAD}
						y={y + 10}
						font-size="7"
						fill="var(--ch-axis-strong)">{row.reason}</text
					>
					<rect
						x={tradeWinRateByExitReason.PAD + 96}
						{y}
						width={bw}
						height="12"
						rx="2"
						fill={color}
					/>
					<text x={tradeWinRateByExitReason.PAD + 96 + bw + 3} y={y + 10} font-size="7" fill={color}
						>{row.wr.toFixed(1)}%</text
					>
					<text
						x={tradeWinRateByExitReason.W - 2}
						y={y + 10}
						text-anchor="end"
						font-size="6"
						fill="var(--ch-axis-muted)">{row.count}t</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Win rate % per exit reason (min 2 trades) · green≥60% · yellow≥50% · red&lt;50% ·
				count=trades · reveals which exit signals produce the most reliable wins
			</p>
		</section>
	{/if}
	{#if tradeProfitByEntryHour}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit % by Entry Hour (UTC)
			</h3>
			<svg
				viewBox="0 0 {tradeProfitByEntryHour.W} {tradeProfitByEntryHour.H}"
				class="w-full"
				style="height:{tradeProfitByEntryHour.H}px"
			>
				<line
					x1={tradeProfitByEntryHour.PAD}
					y1={tradeProfitByEntryHour.midY}
					x2={tradeProfitByEntryHour.W - tradeProfitByEntryHour.PAD}
					y2={tradeProfitByEntryHour.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each tradeProfitByEntryHour.rows as row, i (i)}
					{@const x = tradeProfitByEntryHour.PAD + i * (tradeProfitByEntryHour.bw + 1)}
					{@const bh = tradeProfitByEntryHour.toH(row.avg)}
					{@const color = row.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					{@const y = row.avg >= 0 ? tradeProfitByEntryHour.midY - bh : tradeProfitByEntryHour.midY}
					<rect
						{x}
						{y}
						width={tradeProfitByEntryHour.bw}
						height={Math.max(1, bh)}
						rx="1"
						fill={color}
					/>
					{#if i % 6 === 0}
						<text
							x={x + tradeProfitByEntryHour.bw / 2}
							y={tradeProfitByEntryHour.H - 1}
							text-anchor="middle"
							font-size="5.5"
							fill="var(--ch-axis)">{row.h}h</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg profit % per UTC hour of trade entry · green=positive · red=negative · reveals
				time-of-day patterns in entry quality
			</p>
		</section>
	{/if}
	{#if tradeDurationHistogram}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Trade Duration Distribution (hours)
			</h3>
			<svg
				viewBox="0 0 {tradeDurationHistogram.W} {tradeDurationHistogram.H}"
				class="w-full"
				style="height:{tradeDurationHistogram.H}px"
			>
				{#each tradeDurationHistogram.buckets as b, i (i)}
					{@const x = tradeDurationHistogram.PAD + i * (tradeDurationHistogram.bw + 1)}
					{@const bh = Math.max(
						2,
						(b.count / tradeDurationHistogram.maxC) *
							(tradeDurationHistogram.H - tradeDurationHistogram.PAD * 2 - 10)
					)}
					{@const y = tradeDurationHistogram.H - tradeDurationHistogram.PAD - 10 - bh}
					<rect
						{x}
						{y}
						width={tradeDurationHistogram.bw}
						height={bh}
						rx="1"
						fill="var(--ch-warn)"
					/>
				{/each}
				<text
					x={tradeDurationHistogram.PAD}
					y={tradeDurationHistogram.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">0h</text
				>
				<text
					x={tradeDurationHistogram.W - tradeDurationHistogram.PAD}
					y={tradeDurationHistogram.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{tradeDurationHistogram.maxH}h</text
				>
				<text
					x={tradeDurationHistogram.W / 2}
					y={tradeDurationHistogram.H - 2}
					text-anchor="middle"
					font-size="6"
					fill="var(--ch-axis-muted)">n={tradeDurationHistogram.total}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Distribution of trade hold times in hours · orange bars · reveals whether strategy favors
				scalping (left-skewed) or swing trading (right-skewed)
			</p>
		</section>
	{/if}
	{#if tradeMonthlyWinLoss}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Monthly Win vs Loss Count
			</h3>
			<svg
				viewBox="0 0 {tradeMonthlyWinLoss.W} {tradeMonthlyWinLoss.H}"
				class="w-full"
				style="height:{tradeMonthlyWinLoss.H}px"
			>
				{#each tradeMonthlyWinLoss.data as d, i (i)}
					{@const x = tradeMonthlyWinLoss.toX(i)}
					{@const wh = tradeMonthlyWinLoss.toH(d.wins)}
					{@const lh = tradeMonthlyWinLoss.toH(d.losses)}
					{@const baseY = tradeMonthlyWinLoss.H - tradeMonthlyWinLoss.PAD - 10}
					<rect
						{x}
						y={baseY - wh}
						width={tradeMonthlyWinLoss.bw}
						height={Math.max(1, wh)}
						rx="1"
						fill="var(--ch-profit)"
					/>
					<rect
						{x}
						y={baseY - wh - lh}
						width={tradeMonthlyWinLoss.bw}
						height={Math.max(1, lh)}
						rx="1"
						fill="var(--ch-loss-light)"
					/>
					{#if i % 3 === 0}
						<text
							x={x + tradeMonthlyWinLoss.bw / 2}
							y={tradeMonthlyWinLoss.H - 2}
							text-anchor="middle"
							font-size="5.5"
							fill="var(--ch-axis-muted)">{d.m}</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Monthly win count (green, bottom) + loss count (red, stacked above) · reveals seasonal
				patterns in trade outcomes and periods of strategy underperformance
			</p>
		</section>
	{/if}
	{#if tradePairProfitRanking}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Pairs by Avg Profit %
			</h3>
			<svg
				viewBox="0 0 {tradePairProfitRanking.W} {tradePairProfitRanking.H}"
				class="w-full"
				style="height:{tradePairProfitRanking.H}px"
			>
				<line
					x1={tradePairProfitRanking.zeroX}
					y1="0"
					x2={tradePairProfitRanking.zeroX}
					y2={tradePairProfitRanking.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each tradePairProfitRanking.rows as row, i (i)}
					{@const y = tradePairProfitRanking.PAD + i * 16}
					{@const bw = Math.max(
						2,
						(Math.abs(row.avg) / tradePairProfitRanking.maxAbs) *
							(tradePairProfitRanking.barMaxW / 2)
					)}
					{@const x =
						row.avg >= 0 ? tradePairProfitRanking.zeroX : tradePairProfitRanking.zeroX - bw}
					{@const color =
						row.avg >= 0.5
							? 'var(--ch-profit)'
							: row.avg >= 0
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					<text x={tradePairProfitRanking.PAD} y={y + 11} font-size="7" fill="var(--ch-axis-strong)"
						>{row.pair}</text
					>
					<rect {x} {y} width={bw} height="12" rx="1" fill={color} />
					<text
						x={row.avg >= 0
							? tradePairProfitRanking.zeroX + bw + 2
							: tradePairProfitRanking.zeroX - bw - 2}
						y={y + 11}
						text-anchor={row.avg >= 0 ? 'start' : 'end'}
						font-size="6.5"
						fill={color}>{row.avg.toFixed(2)}%</text
					>
					<text
						x={tradePairProfitRanking.W - 2}
						y={y + 11}
						text-anchor="end"
						font-size="5.5"
						fill="var(--ch-axis-muted)">{row.count}t</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Pairs ranked by avg profit % per trade (min 2 trades) · green≥0.5% · yellow≥0% · red&lt;0% ·
				reveals which pairs this strategy profits from most reliably
			</p>
		</section>
	{/if}
	{#if tradeExitHourDistribution}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Trade Exit Hour Distribution (UTC)
			</h3>
			<svg
				viewBox="0 0 {tradeExitHourDistribution.W} {tradeExitHourDistribution.H}"
				class="w-full"
				style="height:{tradeExitHourDistribution.H}px"
			>
				{#each tradeExitHourDistribution.counts as count, h (h)}
					{@const x = tradeExitHourDistribution.PAD + h * tradeExitHourDistribution.barW}
					{@const bh = Math.max(
						2,
						(count / tradeExitHourDistribution.maxCount) *
							(tradeExitHourDistribution.H - tradeExitHourDistribution.PAD * 2)
					)}
					<rect
						{x}
						y={tradeExitHourDistribution.H - tradeExitHourDistribution.PAD - bh}
						width={tradeExitHourDistribution.barW - 1}
						height={bh}
						fill={`rgba(99,102,241,${((count / tradeExitHourDistribution.maxCount) * 0.7 + 0.15).toFixed(2)})`}
					/>
					{#if h % 6 === 0}
						<text
							x={x + tradeExitHourDistribution.barW / 2}
							y={tradeExitHourDistribution.H - 1}
							text-anchor="middle"
							font-size="5.5"
							fill="var(--ch-axis-muted)">{h}h</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Distribution of trade close times by UTC hour · indigo intensity = more exits at that hour ·
				identifies peak activity windows and potential time-of-day patterns
			</p>
		</section>
	{/if}
	{#if tradeAvgProfitByStake}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit% by Stake Size Bucket
			</h3>
			<svg
				viewBox="0 0 {tradeAvgProfitByStake.W} {tradeAvgProfitByStake.H}"
				class="w-full"
				style="height:{tradeAvgProfitByStake.H}px"
			>
				<line
					x1={tradeAvgProfitByStake.PAD}
					y1={tradeAvgProfitByStake.midY}
					x2={tradeAvgProfitByStake.W - tradeAvgProfitByStake.PAD}
					y2={tradeAvgProfitByStake.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each tradeAvgProfitByStake.rows as row, i (i)}
					{@const x = tradeAvgProfitByStake.PAD + i * (tradeAvgProfitByStake.bw + 2)}
					{@const bh = Math.max(
						2,
						(Math.abs(row.avg) / tradeAvgProfitByStake.maxAbs) *
							(tradeAvgProfitByStake.midY - tradeAvgProfitByStake.PAD)
					)}
					{@const y = row.avg >= 0 ? tradeAvgProfitByStake.midY - bh : tradeAvgProfitByStake.midY}
					{@const color = row.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					<rect {x} {y} width={tradeAvgProfitByStake.bw} height={bh} fill={color} />
					<text
						x={x + tradeAvgProfitByStake.bw / 2}
						y={tradeAvgProfitByStake.H - 2}
						text-anchor="middle"
						font-size="5.5"
						fill="var(--ch-axis-muted)">{row.label}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg profit% per trade grouped by stake size bucket (USDT) · green=positive · red=negative ·
				reveals if larger position sizes produce better or worse returns
			</p>
		</section>
	{/if}
	{#if tradeProfitByDow}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit% by Day of Week (Entry)
			</h3>
			<svg
				viewBox="0 0 {tradeProfitByDow.W} {tradeProfitByDow.H}"
				class="w-full"
				style="height:{tradeProfitByDow.H}px"
			>
				<line
					x1={tradeProfitByDow.PAD}
					y1={tradeProfitByDow.midY}
					x2={tradeProfitByDow.W - tradeProfitByDow.PAD}
					y2={tradeProfitByDow.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each tradeProfitByDow.rows as row, i (i)}
					{@const x = tradeProfitByDow.PAD + i * (tradeProfitByDow.bw + 2)}
					{@const bh = Math.max(
						2,
						(Math.abs(row.avg) / tradeProfitByDow.maxAbs) *
							(tradeProfitByDow.midY - tradeProfitByDow.PAD)
					)}
					{@const y = row.avg >= 0 ? tradeProfitByDow.midY - bh : tradeProfitByDow.midY}
					{@const color = row.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					<rect {x} {y} width={tradeProfitByDow.bw} height={bh} rx="1" fill={color} />
					<text
						x={x + tradeProfitByDow.bw / 2}
						y={tradeProfitByDow.H - 2}
						text-anchor="middle"
						font-size="7"
						fill="var(--ch-axis)">{row.label}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg profit% per trade grouped by UTC day-of-week at trade entry · green=positive ·
				red=negative · reveals if certain weekdays produce consistently better results for this
				strategy
			</p>
		</section>
	{/if}
	{#if tradeRollingWinRate}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Rolling 20-Trade Win Rate
			</h3>
			<svg
				viewBox="0 0 {tradeRollingWinRate.W} {tradeRollingWinRate.H}"
				class="w-full"
				style="height:{tradeRollingWinRate.H}px"
			>
				<line
					x1={tradeRollingWinRate.PAD}
					y1={tradeRollingWinRate.fiftyY}
					x2={tradeRollingWinRate.W - tradeRollingWinRate.PAD}
					y2={tradeRollingWinRate.fiftyY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				<polyline
					points={tradeRollingWinRate.polyline}
					fill="none"
					stroke={tradeRollingWinRate.color}
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={tradeRollingWinRate.W - tradeRollingWinRate.PAD}
					y={tradeRollingWinRate.PAD + 7}
					text-anchor="end"
					font-size="7"
					fill={tradeRollingWinRate.color}>{tradeRollingWinRate.last}%</text
				>
				<text
					x={tradeRollingWinRate.PAD}
					y={tradeRollingWinRate.fiftyY - 2}
					font-size="5.5"
					fill="var(--ch-axis-muted)">50%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Rolling 20-trade win rate % over time (sorted by open date) · green≥55% · yellow≥45% ·
				red&lt;45% · dashed line at 50% · reveals consistency of edge and if strategy degrades over
				time
			</p>
		</section>
	{/if}
	{#if tradeProfitCDF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Profit% Cumulative Distribution (CDF)
			</h3>
			<svg
				viewBox="0 0 {tradeProfitCDF.W} {tradeProfitCDF.H}"
				class="w-full"
				style="height:{tradeProfitCDF.H}px"
			>
				<line
					x1={tradeProfitCDF.zeroX}
					y1={tradeProfitCDF.PAD}
					x2={tradeProfitCDF.zeroX}
					y2={tradeProfitCDF.H - tradeProfitCDF.PAD}
					stroke="var(--ch-axis-muted)"
					stroke-width="1"
					stroke-dasharray="3,2"
				/>
				<polyline
					points={tradeProfitCDF.polyline}
					fill="none"
					stroke="var(--ch-violet-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={tradeProfitCDF.PAD}
					y={tradeProfitCDF.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{tradeProfitCDF.minP}%</text
				>
				<text
					x={tradeProfitCDF.W - tradeProfitCDF.PAD}
					y={tradeProfitCDF.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{tradeProfitCDF.maxP}%</text
				>
				<text
					x={tradeProfitCDF.W / 2}
					y={tradeProfitCDF.PAD + 8}
					text-anchor="middle"
					font-size="7"
					fill="var(--ch-violet-strong)">median {tradeProfitCDF.median}%</text
				>
				<text
					x={tradeProfitCDF.PAD}
					y={tradeProfitCDF.PAD + 8}
					font-size="6"
					fill="var(--ch-axis-muted)">p25: {tradeProfitCDF.p25}%</text
				>
				<text
					x={tradeProfitCDF.W - tradeProfitCDF.PAD}
					y={tradeProfitCDF.PAD + 8}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">p75: {tradeProfitCDF.p75}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Cumulative distribution of trade profit% · indigo S-curve · steep center = many trades near
				zero · long tails = fat-tail distribution · p25/median/p75 annotated
			</p>
		</section>
	{/if}
	{#if tradeHoldTimeByMonth}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Hold Time (hrs) by Month
			</h3>
			<svg
				viewBox="0 0 {tradeHoldTimeByMonth.W} {tradeHoldTimeByMonth.H}"
				class="w-full"
				style="height:{tradeHoldTimeByMonth.H}px"
			>
				{#each tradeHoldTimeByMonth.pts as p, i (i)}
					{@const x = tradeHoldTimeByMonth.PAD + i * (tradeHoldTimeByMonth.bw + 1)}
					{@const bh = Math.max(
						1,
						(p.avg / tradeHoldTimeByMonth.maxAvg) *
							(tradeHoldTimeByMonth.H - tradeHoldTimeByMonth.PAD * 2)
					)}
					{@const y = tradeHoldTimeByMonth.H - tradeHoldTimeByMonth.PAD - bh}
					<rect
						{x}
						{y}
						width={tradeHoldTimeByMonth.bw}
						height={bh}
						rx="1"
						fill="var(--ch-violet)"
					/>
					{#if i % 3 === 0}
						<text
							x={x + tradeHoldTimeByMonth.bw / 2}
							y={tradeHoldTimeByMonth.H - 1}
							text-anchor="middle"
							font-size="5.5"
							fill="var(--ch-axis-muted)">{p.m}</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Monthly avg trade hold time in hours · indigo bars · rising months indicate strategy holds
				longer · useful for detecting trend/regime shifts affecting hold duration
			</p>
		</section>
	{/if}
	{#if tradePairHoldTimeRanking}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Hold Time (hrs) by Pair
			</h3>
			<svg
				viewBox="0 0 {tradePairHoldTimeRanking.W} {tradePairHoldTimeRanking.H}"
				class="w-full"
				style="height:{tradePairHoldTimeRanking.H}px"
			>
				{#each tradePairHoldTimeRanking.rows as row, i (i)}
					{@const y = tradePairHoldTimeRanking.PAD + i * 18}
					{@const bw = Math.max(
						2,
						(row.avg / tradePairHoldTimeRanking.maxAvg) * tradePairHoldTimeRanking.barMaxW
					)}
					<text
						x={tradePairHoldTimeRanking.PAD}
						y={y + 12}
						font-size="7"
						fill="var(--ch-axis-strong)">{row.pair}</text
					>
					<rect
						x={tradePairHoldTimeRanking.PAD + 48}
						{y}
						width={bw}
						height="13"
						rx="2"
						fill="var(--ch-violet)"
					/>
					<text
						x={tradePairHoldTimeRanking.PAD + 48 + bw + 3}
						y={y + 12}
						font-size="6.5"
						fill="var(--ch-violet-strong)">{row.avg.toFixed(1)}h</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg trade hold time in hours per pair · indigo bars · pairs with long hold times may be
				stuck in ranging conditions or have poor liquidity exits
			</p>
		</section>
	{/if}
	{#if tradeExitReasonByMonth}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Exit Reason Count Heatmap (by Month)
			</h3>
			<svg
				viewBox="0 0 {tradeExitReasonByMonth.W} {tradeExitReasonByMonth.H}"
				class="w-full"
				style="height:{tradeExitReasonByMonth.H}px"
			>
				{#each tradeExitReasonByMonth.allReasons as r, ri (ri)}
					<text
						x={tradeExitReasonByMonth.PAD}
						y={tradeExitReasonByMonth.PAD + (ri + 1) * tradeExitReasonByMonth.cellH + 11}
						font-size="5.5"
						fill="var(--ch-axis)">{r}</text
					>
				{/each}
				{#each tradeExitReasonByMonth.months as mo, mi (mi)}
					<text
						x={tradeExitReasonByMonth.PAD +
							(mi + 1) * tradeExitReasonByMonth.cellW +
							tradeExitReasonByMonth.cellW / 2}
						y={tradeExitReasonByMonth.PAD + 8}
						text-anchor="middle"
						font-size="5"
						fill="var(--ch-axis)">{mo.slice(5)}</text
					>
					{#each tradeExitReasonByMonth.allReasons as r, ri (ri)}
						{@const count = tradeExitReasonByMonth.map.get(mo)?.get(r) ?? 0}
						{@const alpha =
							count === 0
								? '0.06'
								: ((count / tradeExitReasonByMonth.maxCount) * 0.6 + 0.1).toFixed(2)}
						{@const fill = count === 0 ? 'var(--ch-axis-faint)' : tradeExitReasonByMonth.COLORS[ri]}
						{@const x = tradeExitReasonByMonth.PAD + (mi + 1) * tradeExitReasonByMonth.cellW}
						{@const y = tradeExitReasonByMonth.PAD + (ri + 1) * tradeExitReasonByMonth.cellH}
						<rect
							{x}
							{y}
							width={tradeExitReasonByMonth.cellW - 2}
							height={tradeExitReasonByMonth.cellH - 2}
							rx="2"
							style="fill:{fill};fill-opacity:{alpha}"
						/>
						{#if count > 0}
							<text
								x={x + tradeExitReasonByMonth.cellW / 2 - 1}
								y={y + 10}
								text-anchor="middle"
								font-size="5"
								fill="var(--ch-axis-strong)">{count}</text
							>
						{/if}
					{/each}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Exit reason frequency heatmap by month (last 8 months, top 4 reasons) · color intensity =
				count · reveals shifts in how trades are closed over time
			</p>
		</section>
	{/if}
	{#if tradeEntryTagWinRate}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win Rate by Entry Tag
			</h3>
			<svg
				viewBox="0 0 {tradeEntryTagWinRate.W} {tradeEntryTagWinRate.H}"
				class="w-full"
				style="height:{tradeEntryTagWinRate.H}px"
			>
				<line
					x1={tradeEntryTagWinRate.PAD + 60}
					y1={tradeEntryTagWinRate.PAD}
					x2={tradeEntryTagWinRate.PAD + 60 + tradeEntryTagWinRate.barMaxW / 2}
					y2={tradeEntryTagWinRate.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each tradeEntryTagWinRate.rows as row, i (i)}
					{@const y = tradeEntryTagWinRate.PAD + i * 18}
					{@const bw = Math.max(2, row.wr * tradeEntryTagWinRate.barMaxW)}
					{@const color =
						row.wr >= 0.6
							? 'var(--ch-profit)'
							: row.wr >= 0.45
								? 'var(--ch-violet)'
								: 'var(--ch-loss)'}
					<text x={tradeEntryTagWinRate.PAD} y={y + 12} font-size="7" fill="var(--ch-axis-strong)"
						>{row.tag}</text
					>
					<rect
						x={tradeEntryTagWinRate.PAD + 60}
						{y}
						width={bw}
						height="13"
						rx="2"
						style="fill:{color}"
					/>
					<text
						x={tradeEntryTagWinRate.PAD + 60 + bw + 3}
						y={y + 12}
						font-size="6.5"
						fill="var(--ch-axis)">{(row.wr * 100).toFixed(0)}% ({row.total})</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Win rate per entry signal tag · green≥60% · indigo 45-60% · red&lt;45% · shows which entry
				conditions consistently find profitable setups
			</p>
		</section>
	{/if}
	{#if tradeSizeTrend}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Stake Size Trend (by Month)
			</h3>
			<svg
				viewBox="0 0 {tradeSizeTrend.W} {tradeSizeTrend.H}"
				class="w-full"
				style="height:{tradeSizeTrend.H}px"
			>
				<polyline
					points={tradeSizeTrend.pts}
					fill="none"
					stroke="var(--ch-warn)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={tradeSizeTrend.PAD}
					y={tradeSizeTrend.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{tradeSizeTrend.minV}</text
				>
				<text
					x={tradeSizeTrend.W - tradeSizeTrend.PAD}
					y={tradeSizeTrend.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{tradeSizeTrend.maxV}</text
				>
				<text
					x={tradeSizeTrend.PAD}
					y={tradeSizeTrend.PAD + 8}
					font-size="6.5"
					fill="var(--ch-warn)">{tradeSizeTrend.months[0]}</text
				>
				<text
					x={tradeSizeTrend.W - tradeSizeTrend.PAD}
					y={tradeSizeTrend.PAD + 8}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-warn)">{tradeSizeTrend.months[tradeSizeTrend.months.length - 1]}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Monthly avg stake size (USDT) · orange trend line · rising = position sizing increase or DCA
				scaling up · falling = risk reduction
			</p>
		</section>
	{/if}
	{#if tradeMonthlyWinLossCount}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Monthly Win/Loss Count
			</h3>
			<svg
				viewBox="0 0 {tradeMonthlyWinLossCount.W} {tradeMonthlyWinLossCount.H}"
				class="w-full"
				style="height:{tradeMonthlyWinLossCount.H}px"
			>
				{#each tradeMonthlyWinLossCount.pts as p, i (i)}
					{@const x = tradeMonthlyWinLossCount.PAD + i * (tradeMonthlyWinLossCount.bw + 1)}
					{@const totalH = tradeMonthlyWinLossCount.H - tradeMonthlyWinLossCount.PAD * 2}
					{@const winH = Math.max(1, (p.wins / tradeMonthlyWinLossCount.maxCount) * totalH)}
					{@const lossH = Math.max(1, (p.losses / tradeMonthlyWinLossCount.maxCount) * totalH)}
					<rect
						{x}
						y={tradeMonthlyWinLossCount.H - tradeMonthlyWinLossCount.PAD - winH}
						width={tradeMonthlyWinLossCount.bw / 2 - 0.5}
						height={winH}
						rx="1"
						fill="var(--ch-profit)"
					/>
					<rect
						x={x + tradeMonthlyWinLossCount.bw / 2 + 0.5}
						y={tradeMonthlyWinLossCount.H - tradeMonthlyWinLossCount.PAD - lossH}
						width={tradeMonthlyWinLossCount.bw / 2 - 0.5}
						height={lossH}
						rx="1"
						fill="var(--ch-loss)"
					/>
				{/each}
				<text
					x={tradeMonthlyWinLossCount.PAD}
					y={tradeMonthlyWinLossCount.H - 1}
					font-size="5.5"
					fill="var(--ch-axis-muted)">{tradeMonthlyWinLossCount.months[0].slice(5)}</text
				>
				<text
					x={tradeMonthlyWinLossCount.W - tradeMonthlyWinLossCount.PAD}
					y={tradeMonthlyWinLossCount.H - 1}
					text-anchor="end"
					font-size="5.5"
					fill="var(--ch-axis-muted)"
					>{tradeMonthlyWinLossCount.months[tradeMonthlyWinLossCount.months.length - 1].slice(
						5
					)}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Monthly win (green left) vs loss (red right) trade count · side-by-side bars · months where
				green dominates signal consistent positive edge
			</p>
		</section>
	{/if}
	{#if tradeProfitByPairCountBucket}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit% by Pair Count Bucket
			</h3>
			<svg
				viewBox="0 0 {tradeProfitByPairCountBucket.W} {tradeProfitByPairCountBucket.H}"
				class="w-full"
				style="height:{tradeProfitByPairCountBucket.H}px"
			>
				<line
					x1={tradeProfitByPairCountBucket.zeroX}
					y1="0"
					x2={tradeProfitByPairCountBucket.zeroX}
					y2={tradeProfitByPairCountBucket.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="1"
				/>
				{#each tradeProfitByPairCountBucket.rows as row, i (i)}
					{@const y = tradeProfitByPairCountBucket.PAD + i * 22}
					{@const bw = Math.max(
						2,
						(Math.abs(row.avg) / tradeProfitByPairCountBucket.maxAbs) *
							(tradeProfitByPairCountBucket.barMaxW / 2)
					)}
					{@const x =
						row.avg >= 0
							? tradeProfitByPairCountBucket.zeroX
							: tradeProfitByPairCountBucket.zeroX - bw}
					{@const color = row.avg >= 0 ? 'var(--ch-violet)' : 'var(--ch-loss)'}
					<text
						x={tradeProfitByPairCountBucket.PAD}
						y={y + 14}
						font-size="8"
						fill="var(--ch-axis-strong)">{row.k}</text
					>
					<rect {x} {y} width={bw} height="15" rx="2" fill={color} />
					<text
						x={row.avg >= 0
							? tradeProfitByPairCountBucket.zeroX + bw + 2
							: tradeProfitByPairCountBucket.zeroX - bw - 2}
						y={y + 12}
						text-anchor={row.avg >= 0 ? 'start' : 'end'}
						font-size="6.5"
						fill={color}>{row.avg.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg total profit% by pair count group across all runs · indigo=positive · red=negative ·
				reveals if diversification (more pairs) improves or hurts returns
			</p>
		</section>
	{/if}
	{#if tradeStakeHistogram}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Trade Stake Amount Distribution
			</h3>
			<svg
				viewBox="0 0 {tradeStakeHistogram.W} {tradeStakeHistogram.H}"
				class="w-full"
				style="height:{tradeStakeHistogram.H}px"
			>
				{#each tradeStakeHistogram.bins as bin, i (i)}
					{@const y = tradeStakeHistogram.H - tradeStakeHistogram.PAD - 10 - bin.h}
					{@const color = i < 3 ? 'var(--ch-violet)' : i < 7 ? 'var(--ch-teal)' : 'var(--ch-warn)'}
					<rect
						x={bin.x}
						{y}
						width={tradeStakeHistogram.bw}
						height={bin.h}
						rx="1"
						style="fill:{color}"
					/>
				{/each}
				<text
					x={tradeStakeHistogram.PAD}
					y={tradeStakeHistogram.H - 1}
					font-size="5.5"
					fill="var(--ch-axis-muted)">{tradeStakeHistogram.minV}</text
				>
				<text
					x={tradeStakeHistogram.W - tradeStakeHistogram.PAD}
					y={tradeStakeHistogram.H - 1}
					text-anchor="end"
					font-size="5.5"
					fill="var(--ch-axis-muted)">{tradeStakeHistogram.maxV}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				10-bin histogram of individual trade stake amounts · indigo=low · teal=mid · yellow=high
				stake · shape reveals if position sizing is uniform or skewed
			</p>
		</section>
	{/if}
	{#if tradeExitWinRateTrend}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win Rate% by Exit Reason
			</h3>
			<svg
				viewBox="0 0 {tradeExitWinRateTrend.W} {tradeExitWinRateTrend.H}"
				class="w-full"
				style="height:{tradeExitWinRateTrend.H}px"
			>
				{#each tradeExitWinRateTrend.rows as row, i (i)}
					{@const y = tradeExitWinRateTrend.PAD + i * 18}
					{@const bw = Math.max(2, (row.wr / 100) * tradeExitWinRateTrend.barMaxW)}
					{@const color =
						row.wr >= 60 ? 'var(--ch-profit)' : row.wr >= 45 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
					<text
						x={tradeExitWinRateTrend.PAD}
						y={y + 12}
						font-size="6.5"
						fill="var(--ch-axis-strong)">{row.reason}</text
					>
					<rect x={tradeExitWinRateTrend.PAD + 90} {y} width={bw} height="13" rx="2" fill={color} />
					<text x={tradeExitWinRateTrend.PAD + 90 + bw + 3} y={y + 12} font-size="6" fill={color}
						>{row.wr.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Win rate% per exit reason (min 3 trades) · green≥60% · teal≥45% · red&lt;45% · stoploss
				exits with high win rate = tight stop is rarely triggered
			</p>
		</section>
	{/if}
	{#if tradeWeeklyWinRate}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win Rate% by Day of Week
			</h3>
			<svg
				viewBox="0 0 {tradeWeeklyWinRate.W} {tradeWeeklyWinRate.H}"
				class="w-full"
				style="height:{tradeWeeklyWinRate.H}px"
			>
				{#each tradeWeeklyWinRate.rows as row, i (i)}
					{@const x = tradeWeeklyWinRate.PAD + i * (tradeWeeklyWinRate.bw + 1)}
					{@const bh = Math.max(
						2,
						(row.wr / 100) * (tradeWeeklyWinRate.H - tradeWeeklyWinRate.PAD * 2 - 12)
					)}
					{@const y = tradeWeeklyWinRate.H - tradeWeeklyWinRate.PAD - 12 - bh}
					{@const color =
						row.wr >= 60 ? 'var(--ch-profit)' : row.wr >= 50 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
					<rect {x} {y} width={tradeWeeklyWinRate.bw} height={bh} rx="1" fill={color} />
					<text
						x={x + tradeWeeklyWinRate.bw / 2}
						y={tradeWeeklyWinRate.H - 12}
						text-anchor="middle"
						font-size="6.5"
						fill="var(--ch-axis)">{row.d}</text
					>
					<text
						x={x + tradeWeeklyWinRate.bw / 2}
						y={y - 2}
						text-anchor="middle"
						font-size="6"
						fill={color}>{row.wr.toFixed(0)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Win rate% by trade open day of week · green≥60% · teal≥50% · red&lt;50% · persistent edge on
				specific days may indicate market microstructure patterns
			</p>
		</section>
	{/if}
	{#if tradeWeeklyProfitTrend}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Weekly Avg Profit% Trend
			</h3>
			<svg
				viewBox="0 0 {tradeWeeklyProfitTrend.W} {tradeWeeklyProfitTrend.H}"
				class="w-full"
				style="height:{tradeWeeklyProfitTrend.H}px"
			>
				<line
					x1={tradeWeeklyProfitTrend.PAD}
					y1={tradeWeeklyProfitTrend.midY}
					x2={tradeWeeklyProfitTrend.W - tradeWeeklyProfitTrend.PAD}
					y2={tradeWeeklyProfitTrend.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each tradeWeeklyProfitTrend.pts as p, i (i)}
					{@const x = tradeWeeklyProfitTrend.PAD + i * (tradeWeeklyProfitTrend.bw + 0.5)}
					{@const bh = Math.max(
						1,
						(Math.abs(p.avg) / tradeWeeklyProfitTrend.maxAbs) *
							(tradeWeeklyProfitTrend.H / 2 - tradeWeeklyProfitTrend.PAD)
					)}
					{@const y = p.avg >= 0 ? tradeWeeklyProfitTrend.midY - bh : tradeWeeklyProfitTrend.midY}
					{@const color = p.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					<rect {x} {y} width={tradeWeeklyProfitTrend.bw} height={bh} fill={color} />
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Weekly avg trade profit% · green=positive · red=negative · diverging bars from midline ·
				consecutive red weeks = strategy may need review · rising trend = improving edge
			</p>
		</section>
	{/if}
	{#if tradeStakeProfitScatter}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Stake Amount vs Profit%
			</h3>
			<svg
				viewBox="0 0 {tradeStakeProfitScatter.W} {tradeStakeProfitScatter.H}"
				class="w-full"
				style="height:{tradeStakeProfitScatter.H}px"
			>
				<line
					x1={tradeStakeProfitScatter.PAD}
					y1={tradeStakeProfitScatter.midY}
					x2={tradeStakeProfitScatter.W - tradeStakeProfitScatter.PAD}
					y2={tradeStakeProfitScatter.midY}
					stroke="var(--ch-axis-muted)"
					stroke-width="0.5"
				/>
				{#each tradeStakeProfitScatter.pts as p, _i (_i)}
					{@const cx =
						tradeStakeProfitScatter.PAD +
						(p.stake / tradeStakeProfitScatter.maxStake) *
							(tradeStakeProfitScatter.W - tradeStakeProfitScatter.PAD * 2)}
					{@const cy =
						tradeStakeProfitScatter.midY -
						(p.profit / tradeStakeProfitScatter.maxP) *
							(tradeStakeProfitScatter.midY - tradeStakeProfitScatter.PAD)}
					{@const color =
						p.profit > 1
							? 'var(--ch-profit-light)'
							: p.profit > 0
								? 'var(--ch-teal-light)'
								: 'var(--ch-loss-light)'}
					<circle {cx} {cy} r="2" fill={color} />
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Scatter: stake amount (X) vs profit% (Y) · green=winning · red=losing · clustering above
				midline for any stake range = the strategy edge is independent of position size
			</p>
		</section>
	{/if}
	{#if tradeEntryTagCount}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Trades by Entry Tag
			</h3>
			<svg
				viewBox="0 0 {tradeEntryTagCount.W} {tradeEntryTagCount.H}"
				class="w-full"
				style="height:{tradeEntryTagCount.H}px"
			>
				{#each tradeEntryTagCount.rows as row, i (i)}
					{@const y = tradeEntryTagCount.PAD + i * 18}
					{@const bw = Math.max(
						2,
						(row.count / tradeEntryTagCount.maxCount) * tradeEntryTagCount.barMaxW
					)}
					{@const color =
						row.count >= tradeEntryTagCount.maxCount * 0.6
							? 'var(--ch-teal-strong)'
							: row.count >= tradeEntryTagCount.maxCount * 0.3
								? 'var(--ch-violet)'
								: 'var(--ch-axis-muted)'}
					<text x={tradeEntryTagCount.PAD} y={y + 12} font-size="7" fill="var(--ch-axis-strong)"
						>{row.tag}</text
					>
					<rect x={tradeEntryTagCount.PAD + 90} {y} width={bw} height="14" rx="2" fill={color} />
					<text x={tradeEntryTagCount.PAD + 90 + bw + 3} y={y + 11} font-size="6.5" fill={color}
						>{row.count}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Trade count by entry tag · top 10 · teal = dominant signals · reveals which entry conditions
				are triggering most often
			</p>
		</section>
	{/if}
	{#if tradeExitTagWinRate}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win Rate% by Exit Reason
			</h3>
			<svg
				viewBox="0 0 {tradeExitTagWinRate.W} {tradeExitTagWinRate.H}"
				class="w-full"
				style="height:{tradeExitTagWinRate.H}px"
			>
				{#each tradeExitTagWinRate.rows as row, i (i)}
					{@const y = tradeExitTagWinRate.PAD + i * 20}
					{@const bw = Math.max(2, (row.wr / 100) * tradeExitTagWinRate.barMaxW)}
					{@const color =
						row.wr >= 55 ? 'var(--ch-profit)' : row.wr >= 45 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
					<text x={tradeExitTagWinRate.PAD} y={y + 13} font-size="7" fill="var(--ch-axis-strong)"
						>{row.tag}</text
					>
					<rect x={tradeExitTagWinRate.PAD + 90} {y} width={bw} height="14" rx="2" fill={color} />
					<text x={tradeExitTagWinRate.PAD + 90 + bw + 3} y={y + 12} font-size="6.5" fill={color}
						>{row.wr.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Win rate% per exit reason · green≥55% · teal≥45% · red&lt;45% · ROI exits typically have
				high win rates · stop-loss exits always 0% · reveals exit quality
			</p>
		</section>
	{/if}
	{#if tradeMonthlyAvgHoldTime}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Monthly Avg Hold Time (hours)
			</h3>
			<svg
				viewBox="0 0 {tradeMonthlyAvgHoldTime.W} {tradeMonthlyAvgHoldTime.H}"
				class="w-full"
				style="height:{tradeMonthlyAvgHoldTime.H}px"
			>
				<polyline
					points={tradeMonthlyAvgHoldTime.polyline}
					fill="none"
					stroke="var(--ch-violet-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				{#each tradeMonthlyAvgHoldTime.pts as p, i (i)}
					{#if i % Math.max(1, Math.floor(tradeMonthlyAvgHoldTime.pts.length / 6)) === 0}
						<text
							x={tradeMonthlyAvgHoldTime.toX(i).toFixed(1)}
							y={tradeMonthlyAvgHoldTime.H}
							text-anchor="middle"
							font-size="5.5"
							fill="var(--ch-axis-muted)">{p.mo}</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Monthly avg trade hold time in hours · indigo line · rising = strategy holding longer over
				time (trend-following adaptation) · falling = faster exits (momentum tightening)
			</p>
		</section>
	{/if}
	{#if tradePairProfitCDF}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">Per-Pair Avg Profit CDF</h3>
			<svg
				viewBox={`0 0 ${tradePairProfitCDF.W} ${tradePairProfitCDF.H}`}
				width="100%"
				style="height:65px"
			>
				<line
					x1={tradePairProfitCDF.toX(0).toFixed(1)}
					y1={tradePairProfitCDF.H - tradePairProfitCDF.PAD}
					x2={tradePairProfitCDF.toX(tradePairProfitCDF.maxV).toFixed(1)}
					y2={tradePairProfitCDF.H - tradePairProfitCDF.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				<line
					x1={tradePairProfitCDF.toX(0).toFixed(1)}
					y1={tradePairProfitCDF.PAD}
					x2={tradePairProfitCDF.toX(0).toFixed(1)}
					y2={tradePairProfitCDF.H - tradePairProfitCDF.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				<polyline
					points={tradePairProfitCDF.polyline}
					fill="none"
					stroke="var(--ch-profit-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				{#each tradePairProfitCDF.sorted as p, i (i)}
					{#if i === 0 || i === Math.floor(tradePairProfitCDF.sorted.length / 2) || i === tradePairProfitCDF.sorted.length - 1}
						<circle
							cx={tradePairProfitCDF.toX(p.avg).toFixed(1)}
							cy={tradePairProfitCDF.toY(i).toFixed(1)}
							r="2"
							fill="var(--ch-profit)"
						/>
						<text
							x={tradePairProfitCDF.toX(p.avg).toFixed(1)}
							y={Number(tradePairProfitCDF.toY(i).toFixed(1)) - 3}
							text-anchor="middle"
							font-size="5.5"
							fill="var(--ch-axis)">{p.avg.toFixed(1)}%</text
						>
					{/if}
				{/each}
				<text
					x={tradePairProfitCDF.PAD}
					y={tradePairProfitCDF.PAD + 5}
					font-size="5.5"
					fill="var(--ch-axis-muted)">{tradePairProfitCDF.minV.toFixed(1)}%</text
				>
				<text
					x={tradePairProfitCDF.W - tradePairProfitCDF.PAD}
					y={tradePairProfitCDF.PAD + 5}
					text-anchor="end"
					font-size="5.5"
					fill="var(--ch-axis-muted)">{tradePairProfitCDF.maxV.toFixed(1)}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				CDF of per-pair avg profit% · green S-curve · left tail = loss pairs · right = top
				performers · steep middle = most pairs cluster near median
			</p>
		</section>
	{/if}
	{#if tradeExitHourWinRate}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">Win Rate% by Exit Hour (UTC)</h3>
			<svg
				viewBox={`0 0 ${tradeExitHourWinRate.W} ${tradeExitHourWinRate.H}`}
				width="100%"
				style="height:65px"
			>
				{#each tradeExitHourWinRate.bars as b, i (i)}
					{@const bh =
						(b.wr / tradeExitHourWinRate.maxWR) *
						(tradeExitHourWinRate.H - tradeExitHourWinRate.PAD * 2)}
					{@const x = tradeExitHourWinRate.PAD + i * (tradeExitHourWinRate.bw + 1)}
					{@const y = tradeExitHourWinRate.H - tradeExitHourWinRate.PAD - bh}
					{@const color =
						b.wr >= 55
							? 'var(--ch-profit)'
							: b.wr >= 45
								? 'var(--ch-teal)'
								: 'var(--ch-loss-light)'}
					<rect {x} {y} width={tradeExitHourWinRate.bw} height={bh} fill={color} rx="0.5" />
					{#if i % 4 === 0}
						<text
							x={x + tradeExitHourWinRate.bw / 2}
							y={tradeExitHourWinRate.H}
							text-anchor="middle"
							font-size="5"
							fill="var(--ch-axis-muted)">{b.hr}h</text
						>
					{/if}
				{/each}
				<line
					x1={tradeExitHourWinRate.PAD}
					y1={tradeExitHourWinRate.H -
						tradeExitHourWinRate.PAD -
						(50 / tradeExitHourWinRate.maxWR) *
							(tradeExitHourWinRate.H - tradeExitHourWinRate.PAD * 2)}
					x2={tradeExitHourWinRate.W - tradeExitHourWinRate.PAD}
					y2={tradeExitHourWinRate.H -
						tradeExitHourWinRate.PAD -
						(50 / tradeExitHourWinRate.maxWR) *
							(tradeExitHourWinRate.H - tradeExitHourWinRate.PAD * 2)}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
					stroke-dasharray="2,2"
				/>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Win rate% by UTC hour of trade exit · green≥55% · teal≥45% · red&lt;45% · dashed line at 50%
				· reveals intraday timing edge
			</p>
		</section>
	{/if}
	{#if tradeOpenHourHeatmap}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">
				Profit% Heatmap: Hour × Day (UTC)
			</h3>
			<svg
				viewBox={`0 0 ${tradeOpenHourHeatmap.W} ${tradeOpenHourHeatmap.H}`}
				width="100%"
				style="height:80px"
			>
				{#each tradeOpenHourHeatmap.cells as c, _i (_i)}
					{@const x = tradeOpenHourHeatmap.PAD + c.hr * tradeOpenHourHeatmap.cw}
					{@const y = tradeOpenHourHeatmap.PAD + c.dow * tradeOpenHourHeatmap.ch}
					{@const intensity = Math.min(1, Math.abs(c.avg) / tradeOpenHourHeatmap.maxAbs)}
					{@const color =
						c.avg >= 0
							? `rgba(34,197,94,${(intensity * 0.8 + 0.1).toFixed(2)})`
							: `rgba(239,68,68,${(intensity * 0.8 + 0.1).toFixed(2)})`}
					<rect
						{x}
						{y}
						width={tradeOpenHourHeatmap.cw - 0.5}
						height={tradeOpenHourHeatmap.ch - 0.5}
						fill={color}
						rx="0.5"
					/>
				{/each}
				{#each tradeOpenHourHeatmap.DOW as d, i (i)}
					<text
						x={tradeOpenHourHeatmap.PAD - 1}
						y={tradeOpenHourHeatmap.PAD +
							i * tradeOpenHourHeatmap.ch +
							tradeOpenHourHeatmap.ch / 2 +
							2}
						text-anchor="end"
						font-size="5"
						fill="var(--ch-axis)">{d}</text
					>
				{/each}
				{#each [0, 6, 12, 18, 23] as h, _i (_i)}
					<text
						x={tradeOpenHourHeatmap.PAD + h * tradeOpenHourHeatmap.cw + tradeOpenHourHeatmap.cw / 2}
						y={tradeOpenHourHeatmap.H}
						text-anchor="middle"
						font-size="4.5"
						fill="var(--ch-axis-muted)">{h}h</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Profit% heatmap by trade open hour (X) and day of week (Y) · green=positive · red=negative ·
				darker = stronger signal · reveals optimal entry timing windows
			</p>
		</section>
	{/if}
	{#if tradeProfitBySide}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">Avg Profit% by Trade Side</h3>
			<svg
				viewBox={`0 0 ${tradeProfitBySide.W} ${tradeProfitBySide.H}`}
				width="100%"
				style="height:65px"
			>
				<line
					x1={tradeProfitBySide.PAD}
					y1={tradeProfitBySide.midY}
					x2={tradeProfitBySide.W - tradeProfitBySide.PAD}
					y2={tradeProfitBySide.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
					stroke-dasharray="2,2"
				/>
				{#each tradeProfitBySide.bars as b, i (i)}
					{@const bh =
						(Math.abs(b.avgProfit) / tradeProfitBySide.maxAbsProfit) *
						(tradeProfitBySide.midY - tradeProfitBySide.PAD)}
					{@const x = tradeProfitBySide.PAD + i * (tradeProfitBySide.bw + 10)}
					{@const y = b.avgProfit >= 0 ? tradeProfitBySide.midY - bh : tradeProfitBySide.midY}
					{@const color = b.avgProfit >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					<rect {x} {y} width={tradeProfitBySide.bw} height={bh} fill={color} rx="2" />
					<text
						x={x + tradeProfitBySide.bw / 2}
						y={tradeProfitBySide.H}
						text-anchor="middle"
						font-size="8"
						fill="var(--ch-axis-strong)">{b.side}</text
					>
					<text
						x={x + tradeProfitBySide.bw / 2}
						y={b.avgProfit >= 0 ? y - 3 : y + bh + 9}
						text-anchor="middle"
						font-size="7"
						fill={color}>{b.avgProfit.toFixed(2)}%</text
					>
					<text
						x={x + tradeProfitBySide.bw / 2}
						y={b.avgProfit >= 0 ? y - 10 : y + bh + 16}
						text-anchor="middle"
						font-size="5.5"
						fill="var(--ch-axis-muted)">WR {b.wr.toFixed(0)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg profit% and win rate by trade direction · long vs short comparison · imbalance reveals
				directional bias in the strategy's edge
			</p>
		</section>
	{/if}
	{#if tradeSmoothedWinRate}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">Rolling Win Rate Trend</h3>
			<svg
				viewBox={`0 0 ${tradeSmoothedWinRate.W} ${tradeSmoothedWinRate.H}`}
				width="100%"
				style="height:65px"
			>
				<line
					x1={tradeSmoothedWinRate.PAD}
					y1={tradeSmoothedWinRate.toY(50)}
					x2={tradeSmoothedWinRate.W - tradeSmoothedWinRate.PAD}
					y2={tradeSmoothedWinRate.toY(50)}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
					stroke-dasharray="2,2"
				/>
				<line
					x1={tradeSmoothedWinRate.PAD}
					y1={tradeSmoothedWinRate.H - tradeSmoothedWinRate.PAD}
					x2={tradeSmoothedWinRate.W - tradeSmoothedWinRate.PAD}
					y2={tradeSmoothedWinRate.H - tradeSmoothedWinRate.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				<polyline
					points={tradeSmoothedWinRate.polyline}
					fill="none"
					stroke="var(--ch-profit-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={tradeSmoothedWinRate.PAD}
					y={tradeSmoothedWinRate.PAD + 7}
					font-size="6"
					fill="var(--ch-axis-muted)">100%</text
				>
				<text
					x={tradeSmoothedWinRate.PAD}
					y={tradeSmoothedWinRate.H - tradeSmoothedWinRate.PAD - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">0%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Rolling win rate% over trade sequence · green line · dashed at 50% · rising trend =
				improving signal quality · falling = signal degradation or adverse regime
			</p>
		</section>
	{/if}
	{#if tradeDurationByExitReason}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">Avg Hold Time by Exit Reason</h3>
			<svg
				viewBox={`0 0 ${tradeDurationByExitReason.W} ${tradeDurationByExitReason.H}`}
				width="100%"
				style="height:{tradeDurationByExitReason.H}px"
			>
				{#each tradeDurationByExitReason.bars as b, i (i)}
					{@const bw = Math.max(
						2,
						(b.avg / tradeDurationByExitReason.maxAvg) * tradeDurationByExitReason.barMaxW
					)}
					{@const y = tradeDurationByExitReason.PAD + i * 18}
					{@const color =
						b.avg <= 24 ? 'var(--ch-teal)' : b.avg <= 72 ? 'var(--ch-warn)' : 'var(--ch-violet)'}
					<text
						x={tradeDurationByExitReason.PAD}
						y={y + 12}
						font-size="6.5"
						fill="var(--ch-axis-strong)">{b.reason}</text
					>
					<rect
						x={tradeDurationByExitReason.PAD + 72}
						{y}
						width={bw}
						height="13"
						fill={color}
						rx="1"
					/>
					<text
						x={tradeDurationByExitReason.PAD + 72 + bw + 3}
						y={y + 10}
						font-size="6"
						fill={color}>{b.avg.toFixed(1)}h</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg hold time in hours by exit reason · teal≤24h · orange≤72h · purple&gt;72h · stoploss
				exits are usually short · ROI and trailing exits reveal holding patience
			</p>
		</section>
	{/if}
</main>
