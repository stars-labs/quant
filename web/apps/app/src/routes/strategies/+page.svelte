<script lang="ts">
	import type { PageData } from './$types';
	import FactorBadges from '$lib/components/factor-badges.svelte';
	import { fmtPct } from '$lib/utils';
	import { t, type Lang } from '$lib/i18n';
	import ChartInfo from '$lib/components/chart-info.svelte';
	import StrategyInfo from '$lib/components/strategy-info.svelte';

	let { data }: { data: PageData } = $props();
	const lang = $derived<Lang>(data.lang ?? 'zh');
	const strategies = $derived(data.strategies);

	// Kelly verdict lookup by strategy name. The loader returns null when the
	// JSON snapshot is missing; the map then stays empty and StrategyInfo
	// falls back to its original behaviour with no Kelly block.
	const kellyByName = $derived.by(() => {
		const m = new Map<string, NonNullable<typeof data.kellyStatus>['strategies'][number]>();
		const ks = data.kellyStatus?.strategies ?? [];
		for (const e of ks) m.set(e.name, e);
		return m;
	});

	const statusTone: Record<string, string> = {
		live: 'bg-green-950 text-green-400 border-green-800',
		dryrun: 'bg-yellow-950 text-yellow-400 border-yellow-800',
		research: 'bg-blue-950 text-blue-400 border-blue-800',
		retired: 'bg-muted text-muted-foreground border-border'
	};

	const modeIcon: Record<string, string> = {
		spot: '🟢',
		futures: '🔴',
		hybrid: '🟣'
	};

	const rankEmoji = ['🥇', '🥈', '🥉'];

	// Controls state
	let statusFilter = $state<string>('all');
	let sortKey = $state('profit');
	let nameSearch = $state('');

	// Podium — top 3 by best_profit_pct, fixed (not affected by filters)
	const podium = $derived.by(() =>
		[...data.strategies]
			.sort((a, b) => (b.best_profit_pct ?? -Infinity) - (a.best_profit_pct ?? -Infinity))
			.slice(0, 3)
	);

	// Filtered + sorted list
	const filtered = $derived.by(() => {
		let xs = data.strategies.slice();
		if (statusFilter !== 'all') xs = xs.filter((s) => s.status === statusFilter);
		if (modeFilter !== 'all') xs = xs.filter((s) => s.mode === modeFilter);
		if (nameSearch.trim())
			xs = xs.filter((s) => s.name.toLowerCase().includes(nameSearch.trim().toLowerCase()));
		const sorts: Record<
			string,
			(a: (typeof data.strategies)[0], b: (typeof data.strategies)[0]) => number
		> = {
			profit: (a, b) => (b.best_profit_pct ?? -Infinity) - (a.best_profit_pct ?? -Infinity),
			calmar: (a, b) => (b.best_calmar ?? -Infinity) - (a.best_calmar ?? -Infinity),
			sharpe: (a, b) => (b.best_sharpe ?? -Infinity) - (a.best_sharpe ?? -Infinity),
			runs: (a, b) => b.runs - a.runs,
			name: (a, b) => a.name.localeCompare(b.name),
			updated: (a, b) => (b.last_imported ?? '').localeCompare(a.last_imported ?? '')
		};
		xs.sort(sorts[sortKey] ?? sorts.profit);
		return xs;
	});

	const STATUS_CHIPS = ['all', 'live', 'dryrun', 'research', 'retired'] as const;
	const MODE_CHIPS = ['all', 'spot', 'futures', 'hybrid'] as const;
	let modeFilter = $state<string>('all');

	// View mode toggle: 'card' | 'table'
	let viewMode = $state<'card' | 'table'>('card');

	// Status × mode breakdown: count matrix
	const statusModeBreakdown = $derived.by(() => {
		const statuses = ['live', 'dryrun', 'research', 'retired'] as const;
		const modes = ['spot', 'futures', 'hybrid'] as const;
		const total = data.strategies.length;
		if (total < 2) return null;
		const rows = statuses
			.map((status) => {
				const cells = modes.map((mode) => ({
					mode,
					count: data.strategies.filter((s) => s.status === status && s.mode === mode).length
				}));
				const rowTotal = cells.reduce((s, c) => s + c.count, 0);
				return { status, cells, rowTotal };
			})
			.filter((r) => r.rowTotal > 0);
		const maxRow = Math.max(1, ...rows.map((r) => r.rowTotal));
		return { rows, modes, maxRow, total };
	});

	// Efficient frontier scatter: Sharpe vs MaxDD
	const frontierData = $derived.by(() => {
		const pts = data.strategies
			.filter((s) => s.best_sharpe != null && s.worst_dd_pct != null)
			.map((s) => ({
				name: s.name,
				x: s.worst_dd_pct!,
				y: s.best_sharpe!,
				mode: s.mode,
				runs: s.runs
			}));
		if (pts.length < 3) return null;
		const W = 420,
			H = 160,
			PL = 32,
			PB = 24,
			PT = 8,
			PR = 8;
		const xMax = Math.max(...pts.map((p) => p.x), 1);
		const yMin = Math.min(...pts.map((p) => p.y), 0);
		const yMax = Math.max(...pts.map((p) => p.y), 1);
		const toX = (v: number) => PL + (v / xMax) * (W - PL - PR);
		const toY = (v: number) => PT + (1 - (v - yMin) / (yMax - yMin || 1)) * (H - PT - PB);
		const modeColor: Record<string, string> = {
			spot: '#22c55e',
			futures: '#f87171',
			hybrid: '#a78bfa'
		};
		// Pareto: strategies not dominated (lower DD and higher Sharpe than any other)
		const pareto = pts
			.filter((p) => !pts.some((q) => q.x <= p.x && q.y >= p.y && (q.x < p.x || q.y > p.y)))
			.sort((a, b) => a.x - b.x);
		const paretoLine = pareto.map((p) => `${toX(p.x).toFixed(1)},${toY(p.y).toFixed(1)}`).join(' ');
		return {
			pts: pts.map((p) => ({
				...p,
				cx: toX(p.x),
				cy: toY(p.y),
				color: modeColor[p.mode] ?? '#94a3b8'
			})),
			paretoLine,
			W,
			H,
			PL,
			PB,
			PT,
			PR,
			xMax,
			yMin,
			yMax
		};
	});

	// Profit distribution by status: avg & best profit per status group
	// Run depth distribution: how many strategies have few vs many runs
	const runDepthDistribution = $derived.by(() => {
		if (data.strategies.length < 3) return null;
		const BUCKETS = [
			{ label: '1–5', lo: 1, hi: 5 },
			{ label: '6–20', lo: 6, hi: 20 },
			{ label: '21–50', lo: 21, hi: 50 },
			{ label: '51–100', lo: 51, hi: 100 },
			{ label: '100+', lo: 101, hi: Infinity }
		];
		const rows = BUCKETS.map((b) => {
			const strats = data.strategies.filter((s) => s.runs >= b.lo && s.runs <= b.hi);
			const avgBestProfit =
				strats.length > 0
					? strats
							.filter((s) => s.best_profit_pct != null)
							.reduce((sum, s) => sum + s.best_profit_pct!, 0) /
						Math.max(1, strats.filter((s) => s.best_profit_pct != null).length)
					: null;
			return { label: b.label, count: strats.length, avgBestProfit };
		}).filter((r) => r.count > 0);
		if (rows.length < 2) return null;
		const maxCount = Math.max(1, ...rows.map((r) => r.count));
		return rows.map((r) => ({ ...r, barPct: (r.count / maxCount) * 100 }));
	});

	// Sharpe vs drawdown risk/reward scatter
	const sharpeVsDrawdown = $derived.by(() => {
		const pts = data.strategies.filter(
			(s) =>
				s.best_sharpe != null &&
				s.worst_dd_pct != null &&
				Number.isFinite(s.best_sharpe) &&
				Number.isFinite(s.worst_dd_pct)
		);
		if (pts.length < 4) return null;
		const xs = pts.map((s) => s.best_sharpe!);
		const ys = pts.map((s) => -s.worst_dd_pct!); // flip: higher = less drawdown = better
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 0.01);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.01);
		const W = 520,
			H = 140,
			PAD = 24;
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const STATUS_COLOR: Record<string, string> = {
			live: 'var(--ch-profit-strong)',
			dryrun: 'var(--ch-violet-strong)',
			research: 'var(--ch-warn)',
			retired: 'var(--ch-axis-muted)'
		};
		const dots = pts.map((s) => ({
			x: toX(s.best_sharpe!),
			y: toY(-s.worst_dd_pct!),
			color: STATUS_COLOR[s.status] ?? 'var(--ch-axis)',
			name: s.name,
			sharpe: s.best_sharpe!,
			dd: s.worst_dd_pct!
		}));
		const zeroX = toX(0);
		return { dots, W, H, PAD, xMin, xMax, yMin, yMax, zeroX };
	});

	// Strategy age (days since last import) vs run depth scatter
	const strategyAgeVsRuns = $derived.by(() => {
		const now = Date.now();
		const pts = data.strategies.filter((s) => s.last_imported && s.runs >= 1);
		if (pts.length < 4) return null;
		const xs = pts.map((s) => Math.floor((now - new Date(s.last_imported!).getTime()) / 86400000)); // days since last import
		const ys = pts.map((s) => s.runs);
		const xMax = Math.max(...xs, 1);
		const yMax = Math.max(...ys, 1);
		const W = 520,
			H = 130,
			PAD = 24;
		const toX = (v: number) => PAD + (v / xMax) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - (v / yMax) * (H - PAD * 2);
		const STATUS_COLOR: Record<string, string> = {
			live: 'var(--ch-profit-strong)',
			dryrun: 'var(--ch-violet-strong)',
			research: 'var(--ch-warn)',
			retired: 'var(--ch-axis-muted)'
		};
		const dots = pts.map((s, i) => ({
			x: toX(xs[i]),
			y: toY(ys[i]),
			color: STATUS_COLOR[s.status] ?? 'var(--ch-axis)',
			name: s.name,
			days: xs[i],
			runs: ys[i],
			status: s.status
		}));
		return { dots, W, H, PAD, xMax, yMax };
	});

	// Factor usage: count how many strategies use each factor
	const factorUsageBar = $derived.by(() => {
		const map = new Map<string, number>();
		for (const s of data.strategies) {
			for (const f of s.factors ?? []) {
				map.set(f, (map.get(f) ?? 0) + 1);
			}
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([factor, count]) => ({ factor, count }))
			.sort((a, b) => b.count - a.count)
			.slice(0, 10);
		const maxCount = Math.max(1, rows[0].count);
		return rows.map((r) => ({ ...r, barPct: (r.count / maxCount) * 100 }));
	});

	// Best win rate ranking: top 10 strategies by best_win_rate across all runs
	const bestWinRateRanking = $derived.by(() => {
		const rows = data.strategies
			.filter((s) => s.best_win_rate != null && s.best_win_rate > 0)
			.map((s) => ({ name: s.name, wr: s.best_win_rate!, status: s.status, runs: s.runs }))
			.sort((a, b) => b.wr - a.wr)
			.slice(0, 10);
		if (rows.length < 3) return null;
		return rows;
	});

	// Sortino leaderboard: top 10 strategies by best Sortino ratio
	const sortinoLeaderboard = $derived.by(() => {
		const rows = data.strategies
			.filter((s) => s.best_sortino != null && s.best_sortino > -50 && s.best_sortino < 200)
			.map((s) => ({ name: s.name, sortino: s.best_sortino!, status: s.status, runs: s.runs }))
			.sort((a, b) => b.sortino - a.sortino)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.sortino)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.sortino) / maxAbs) * 100 }));
	});

	const profitByStatus = $derived.by(() => {
		const statuses = ['live', 'dryrun', 'research', 'retired'] as const;
		const rows = statuses
			.map((status) => {
				const group = data.strategies.filter(
					(s) => s.status === status && s.best_profit_pct != null
				);
				if (group.length === 0) return null;
				const profits = group.map((s) => s.best_profit_pct!);
				const avg = profits.reduce((a, b) => a + b, 0) / profits.length;
				const best = Math.max(...profits);
				const worst = Math.min(...profits);
				return { status, count: group.length, avg, best, worst };
			})
			.filter((r): r is NonNullable<typeof r> => r !== null);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.best)));
		return rows.map((r) => ({
			...r,
			bestBarPct: (Math.abs(r.best) / maxAbs) * 100,
			avgBarPct: (Math.abs(r.avg) / maxAbs) * 100
		}));
	});

	// Calmar leaderboard: top 10 by best_calmar (risk-adjusted return vs max drawdown)
	const calmarLeaderboard = $derived.by(() => {
		const rows = data.strategies
			.filter(
				(s) =>
					s.best_calmar != null &&
					isFinite(s.best_calmar) &&
					s.best_calmar > 0 &&
					s.best_calmar < 500
			)
			.map((s) => ({ name: s.name, calmar: s.best_calmar!, runs: s.runs }))
			.sort((a, b) => b.calmar - a.calmar)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxCalmar = Math.max(0.01, rows[0].calmar);
		return rows.map((r) => ({ ...r, barPct: (r.calmar / maxCalmar) * 100 }));
	});

	// Least-drawdown ranking: top 10 by smallest worst_dd_pct (best drawdown control)
	const leastDrawdownRanking = $derived.by(() => {
		const rows = data.strategies
			.filter((s) => s.worst_dd_pct != null && isFinite(s.worst_dd_pct) && s.worst_dd_pct >= 0)
			.map((s) => ({ name: s.name, dd: s.worst_dd_pct!, runs: s.runs }))
			.sort((a, b) => a.dd - b.dd)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxDd = Math.max(0.01, rows[rows.length - 1].dd);
		return rows.map((r) => ({ ...r, barPct: (r.dd / maxDd) * 100 }));
	});

	const strategyWinRateVsDrawdown = $derived.by(() => {
		const pts = data.strategies.filter(
			(s) =>
				s.best_win_rate != null &&
				s.worst_dd_pct != null &&
				isFinite(s.best_win_rate) &&
				isFinite(s.worst_dd_pct)
		);
		if (pts.length < 5) return null;
		const W = 560,
			H = 110,
			PAD = 10;
		const xs = pts.map((s) => s.best_win_rate!),
			ys = pts.map((s) => s.worst_dd_pct!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 1);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 1);
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const maxRuns = Math.max(1, ...pts.map((s) => s.runs));
		const dots = pts.map((s) => ({
			cx: toX(s.best_win_rate!),
			cy: toY(s.worst_dd_pct!),
			r: 2 + Math.min(5, (s.runs / maxRuns) * 5),
			color:
				s.worst_dd_pct! < 10
					? 'var(--ch-profit)'
					: s.worst_dd_pct! < 25
						? 'var(--ch-warn-light)'
						: 'var(--ch-loss-light)',
			title: `${s.name} · wr ${s.best_win_rate!.toFixed(1)}% · dd ${s.worst_dd_pct!.toFixed(1)}% · ${s.runs} runs`
		}));
		return { dots, W, H, PAD, xMin, xMax, yMin, yMax };
	});

	const strategyModeComparison = $derived.by(() => {
		const MODES = ['live', 'dry_run', 'backtest'];
		const rows = MODES.map((mode) => {
			const strats = data.strategies.filter(
				(s) => s.mode === mode && s.best_sortino != null && isFinite(s.best_sortino)
			);
			if (strats.length < 2) return null;
			const avgSortino = strats.reduce((s, r) => s + r.best_sortino!, 0) / strats.length;
			const avgDd =
				strats.filter((s) => s.worst_dd_pct != null).reduce((s, r) => s + r.worst_dd_pct!, 0) /
				strats.filter((s) => s.worst_dd_pct != null).length;
			return { mode, avgSortino, avgDd, count: strats.length };
		}).filter((r): r is NonNullable<typeof r> => r !== null);
		if (rows.length < 2) return null;
		const maxSortino = Math.max(0.01, ...rows.map((r) => Math.abs(r.avgSortino)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.avgSortino) / maxSortino) * 100 }));
	});

	// Run depth vs best Calmar scatter: does more backtesting produce better Calmar? (distinct from strategyAgeVsRuns, sharpeVsDrawdown, strategyWinRateVsDrawdown)
	const runDepthVsCalmar = $derived.by(() => {
		const pts = data.strategies.filter(
			(s) =>
				s.runs >= 1 &&
				s.best_calmar != null &&
				isFinite(s.best_calmar) &&
				s.best_calmar > -50 &&
				s.best_calmar < 200
		);
		if (pts.length < 5) return null;
		const xs = pts.map((s) => s.runs);
		const ys = pts.map((s) => s.best_calmar!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 1);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.01);
		const W = 480,
			H = 130,
			PL = 28,
			PB = 18,
			PT = 8,
			PR = 8;
		const toX = (v: number) => PL + ((v - xMin) / (xMax - xMin || 1)) * (W - PL - PR);
		const toY = (v: number) => PT + (1 - (v - yMin) / (yMax - yMin || 0.01)) * (H - PT - PB);
		const zeroY = yMin < 0 ? toY(0) : null;
		const n = xs.length;
		const mx = xs.reduce((a, b) => a + b, 0) / n,
			my = ys.reduce((a, b) => a + b, 0) / n;
		const num = xs.reduce((s, x, i) => s + (x - mx) * (ys[i] - my), 0);
		const den = Math.sqrt(
			xs.reduce((s, x) => s + (x - mx) ** 2, 0) * ys.reduce((s, y) => s + (y - my) ** 2, 0)
		);
		const corr = den === 0 ? 0 : num / den;
		const dots = pts.map((s) => ({
			cx: toX(s.runs),
			cy: toY(s.best_calmar!),
			name: s.name,
			runs: s.runs,
			calmar: s.best_calmar!,
			color: s.best_calmar! > 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'
		}));
		return { dots, W, H, PL, PB, PT, PR, xMin, xMax, yMin, yMax, zeroY, corr };
	});

	// Factor count distribution: how many factors does each strategy use? (distinct from factorUsageBar popularity, runsPerStrategyHistogram run count)
	const strategyFactorCountDist = $derived.by(() => {
		const BUCKETS = [
			{ label: '0', lo: 0, hi: 1 },
			{ label: '1', lo: 1, hi: 2 },
			{ label: '2', lo: 2, hi: 3 },
			{ label: '3', lo: 3, hi: 4 },
			{ label: '4+', lo: 4, hi: Infinity }
		];
		const buckets = BUCKETS.map((b) => ({ ...b, count: 0 }));
		for (const s of data.strategies) {
			const n = (s.factors ?? []).length;
			const idx = buckets.findIndex((b) => n >= b.lo && n < b.hi);
			if (idx >= 0) buckets[idx].count++;
		}
		if (buckets.every((b) => b.count === 0)) return null;
		const maxCount = Math.max(1, ...buckets.map((b) => b.count));
		const total = data.strategies.length;
		return {
			buckets: buckets.map((b) => ({
				...b,
				barPct: (b.count / maxCount) * 100,
				share: b.count / total
			})),
			total
		};
	});

	const runsPerStrategyHistogram = $derived.by(() => {
		const BUCKETS = [
			{ label: '1', lo: 1, hi: 2 },
			{ label: '2–5', lo: 2, hi: 6 },
			{ label: '6–10', lo: 6, hi: 11 },
			{ label: '11–20', lo: 11, hi: 21 },
			{ label: '>20', lo: 21, hi: Infinity }
		];
		const buckets = BUCKETS.map((b) => ({ ...b, count: 0 }));
		for (const s of data.strategies) {
			const idx = buckets.findIndex((b) => s.runs >= b.lo && s.runs < b.hi);
			if (idx >= 0) buckets[idx].count++;
		}
		if (buckets.every((b) => b.count === 0)) return null;
		const maxCount = Math.max(1, ...buckets.map((b) => b.count));
		return buckets.map((b) => ({ ...b, barPct: (b.count / maxCount) * 100 }));
	});

	const strategyBestSortinoRanking = $derived.by(() => {
		const rows = data.strategies
			.filter((s) => s.best_sortino != null && isFinite(s.best_sortino) && s.best_sortino > 0)
			.map((s) => ({ name: s.name, sortino: s.best_sortino! }))
			.sort((a, b) => b.sortino - a.sortino)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxS = rows[0].sortino;
		return rows.map((r) => ({ ...r, barPct: (r.sortino / maxS) * 100 }));
	});

	const strategyLowestDrawdown = $derived.by(() => {
		const rows = data.strategies
			.filter(
				(s) =>
					s.worst_dd_pct != null && isFinite(s.worst_dd_pct) && s.worst_dd_pct >= 0 && s.runs >= 3
			)
			.map((s) => ({ name: s.name, dd: s.worst_dd_pct!, runs: s.runs }))
			.sort((a, b) => a.dd - b.dd)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxDd = Math.max(...rows.map((r) => r.dd), 0.01);
		return rows.map((r) => ({ ...r, barPct: (r.dd / maxDd) * 100 }));
	});

	const strategyAvgProfitRanking = $derived.by(() => {
		const rows = data.strategies
			.filter((s) => s.best_profit_pct != null && s.runs != null && (s.runs as number) >= 2)
			.map((s) => ({ name: s.name, avg: s.best_profit_pct as number, runs: s.runs as number }))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.avg)));
		return rows.map((r) => ({ ...r, barPct: (Math.abs(r.avg) / maxAbs) * 100 }));
	});

	const strategyRunsVsProfit = $derived.by(() => {
		const pts = data.strategies.filter(
			(s) => s.runs >= 2 && s.best_profit_pct != null && isFinite(s.best_profit_pct)
		);
		if (pts.length < 5) return null;
		const W = 360,
			H = 80,
			PAD = 8;
		const xs = pts.map((s) => s.runs),
			ys = pts.map((s) => s.best_profit_pct!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 1);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 1);
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const dots = pts.map((s) => ({
			cx: toX(s.runs),
			cy: toY(s.best_profit_pct!),
			pos: s.best_profit_pct! > 0
		}));
		return { dots, W, H, PAD, xMin, xMax, yMin, yMax };
	});

	const strategyBestCalmarRanking = $derived.by(() => {
		const rows = data.strategies
			.filter(
				(s) => s.best_calmar != null && isFinite(s.best_calmar) && s.best_calmar > 0 && s.runs >= 2
			)
			.map((s) => ({ name: s.name, calmar: s.best_calmar as number, runs: s.runs }))
			.sort((a, b) => b.calmar - a.calmar)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxCalmar = Math.max(0.01, ...rows.map((r) => r.calmar));
		return rows.map((r) => ({ ...r, barPct: (r.calmar / maxCalmar) * 100 }));
	});

	const strategyProfitDistribution = $derived.by(() => {
		const vals = data.strategies
			.filter((s) => s.best_profit_pct != null && isFinite(s.best_profit_pct))
			.map((s) => s.best_profit_pct as number);
		if (vals.length < 6) return null;
		const mn = Math.min(...vals),
			mx = Math.max(...vals);
		const range = mx - mn || 1;
		const BINS = 8,
			step = range / BINS;
		const buckets = Array.from({ length: BINS }, (_, i) => ({
			lo: mn + i * step,
			hi: mn + (i + 1) * step,
			count: 0
		}));
		for (const v of vals) {
			const idx = Math.min(BINS - 1, Math.floor((v - mn) / step));
			buckets[idx].count++;
		}
		const maxCount = Math.max(1, ...buckets.map((b) => b.count));
		const median = [...vals].sort((a, b) => a - b)[Math.floor(vals.length / 2)];
		return {
			buckets: buckets.map((b) => ({ ...b, barPct: (b.count / maxCount) * 100 })),
			median,
			mn,
			mx,
			total: vals.length
		};
	});

	const strategyTimeframeBreakdown = $derived.by(() => {
		const map = new Map<string, { count: number; sumProfit: number }>();
		for (const s of data.strategies) {
			const tf = s.timeframe ?? 'unknown';
			if (!map.has(tf)) map.set(tf, { count: 0, sumProfit: 0 });
			const e = map.get(tf)!;
			e.count++;
			if (s.best_profit_pct != null && isFinite(s.best_profit_pct))
				e.sumProfit += s.best_profit_pct;
		}
		if (map.size < 2) return null;
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
			'1w',
			'unknown'
		];
		const rows = [...map.entries()]
			.map(([tf, v]) => ({
				tf,
				count: v.count,
				avgProfit: v.count > 0 ? v.sumProfit / v.count : 0
			}))
			.sort((a, b) => TF_ORDER.indexOf(a.tf) - TF_ORDER.indexOf(b.tf) || b.count - a.count);
		const maxCount = Math.max(1, ...rows.map((r) => r.count));
		return rows.map((r) => ({ ...r, barPct: (r.count / maxCount) * 100 }));
	});

	const strategyWinRateVsRuns = $derived.by(() => {
		const pts = data.strategies.filter(
			(s) => s.best_win_rate != null && isFinite(s.best_win_rate) && s.runs >= 1
		);
		if (pts.length < 6) return null;
		const W = 360,
			H = 80,
			PAD = 8;
		const xs = pts.map((s) => s.runs),
			ys = pts.map((s) => s.best_win_rate!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 1);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.01);
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const zeroY = toY(50);
		const dots = pts.map((s) => ({
			cx: toX(s.runs),
			cy: toY(s.best_win_rate!),
			good: s.best_win_rate! >= 50 && s.runs >= 5,
			wr: s.best_win_rate!
		}));
		return { dots, W, H, zeroY, xMin, xMax, yMin, yMax };
	});

	const strategyModeBreakdown = $derived.by(() => {
		const map = new Map<string, { count: number; sumProfit: number; profitCount: number }>();
		for (const s of data.strategies) {
			const mode = s.mode ?? 'unknown';
			if (!map.has(mode)) map.set(mode, { count: 0, sumProfit: 0, profitCount: 0 });
			const e = map.get(mode)!;
			e.count++;
			if (s.best_profit_pct != null && isFinite(s.best_profit_pct)) {
				e.sumProfit += s.best_profit_pct;
				e.profitCount++;
			}
		}
		if (map.size < 2) return null;
		const MODE_COLORS: Record<string, string> = {
			live: 'var(--ch-profit)',
			paper: 'var(--ch-violet)',
			backtest: 'var(--ch-warn)',
			unknown: 'var(--ch-axis-muted)'
		};
		const rows = [...map.entries()]
			.map(([mode, v]) => ({
				mode,
				count: v.count,
				avgProfit: v.profitCount > 0 ? v.sumProfit / v.profitCount : 0
			}))
			.sort((a, b) => b.count - a.count);
		const maxCount = Math.max(1, ...rows.map((r) => r.count));
		return rows.map((r) => ({
			...r,
			barPct: (r.count / maxCount) * 100,
			color: MODE_COLORS[r.mode] ?? 'var(--ch-axis-muted)'
		}));
	});

	const strategyStatusBreakdown = $derived.by(() => {
		const counts = new Map<string, number>();
		for (const s of data.strategies) {
			const status = s.status ?? 'unknown';
			counts.set(status, (counts.get(status) ?? 0) + 1);
		}
		if (counts.size < 2) return null;
		const rows = [...counts.entries()]
			.map(([status, count]) => ({ status, count }))
			.sort((a, b) => b.count - a.count);
		const maxCount = Math.max(1, ...rows.map((r) => r.count));
		const COLORS: Record<string, string> = {
			live: 'var(--ch-profit)',
			paper: 'var(--ch-violet)',
			backtest: 'var(--ch-warn)',
			archived: 'var(--ch-axis)',
			unknown: 'var(--ch-axis-muted)'
		};
		return rows.map((r) => ({
			...r,
			barPct: (r.count / maxCount) * 100,
			color: COLORS[r.status] ?? 'var(--ch-axis-muted)'
		}));
	});

	const strategyCalmarVsWinRate = $derived.by(() => {
		const pts = data.strategies.filter(
			(s) =>
				s.best_calmar != null &&
				isFinite(s.best_calmar) &&
				s.best_calmar > -10 &&
				s.best_calmar < 50 &&
				s.best_win_rate != null &&
				isFinite(s.best_win_rate) &&
				s.best_win_rate >= 0 &&
				s.best_win_rate <= 1
		);
		if (pts.length < 5) return null;
		const xs = pts.map((p) => p.best_calmar!);
		const ys = pts.map((p) => p.best_win_rate!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys);
		const W = 400,
			H = 120,
			PAD = 14;
		const toX = (v: number) => PAD + ((v - xMin) / Math.max(0.01, xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) =>
			H - PAD - ((v - yMin) / Math.max(0.001, yMax - yMin)) * (H - PAD * 2);
		const modeColor: Record<string, string> = {
			live: 'var(--ch-profit)',
			paper: 'var(--ch-violet)',
			backtest: 'var(--ch-warn)'
		};
		const dots = pts.map((p) => ({
			cx: toX(p.best_calmar!),
			cy: toY(p.best_win_rate!),
			color: modeColor[p.mode ?? ''] ?? 'var(--ch-axis)',
			name: p.name,
			calmar: p.best_calmar!,
			wr: p.best_win_rate!
		}));
		const x1 = toX(0),
			y05 = toY(0.5);
		return { dots, W, H, PAD, xMin, xMax, yMin, yMax, x1, y05 };
	});

	const strategyLastImportTimeline = $derived.by(() => {
		const map = new Map<string, number>();
		for (const s of data.strategies) {
			const d = s.last_imported;
			if (!d) continue;
			const ym = d.slice(0, 7);
			map.set(ym, (map.get(ym) ?? 0) + 1);
		}
		const months = [...map.keys()].sort().slice(-18);
		if (months.length < 3) return null;
		const rows = months.map((ym) => ({ ym, count: map.get(ym) ?? 0 }));
		const maxCount = Math.max(1, ...rows.map((r) => r.count));
		return rows.map((r) => ({ ...r, barPct: (r.count / maxCount) * 100 }));
	});

	// Strategy asset coverage: how many assets each strategy is configured for
	const strategyAssetCoverage = $derived.by(() => {
		const rows = data.strategies
			.filter((s) => s.assets && s.assets.length > 0 && s.best_profit_pct != null)
			.map((s) => ({
				name: s.name,
				assetCount: s.assets.length,
				mode: s.mode,
				bestProfit: s.best_profit_pct!,
				status: s.status
			}))
			.sort((a, b) => b.assetCount - a.assetCount)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxCount = Math.max(1, ...rows.map((r) => r.assetCount));
		return rows.map((r) => ({ ...r, barPct: (r.assetCount / maxCount) * 100 }));
	});

	// Strategies ranked by best_sharpe ratio
	const strategySharpeRanking = $derived.by(() => {
		const rows = data.strategies
			.filter((s) => s.best_sharpe != null && isFinite(s.best_sharpe))
			.map((s) => ({ name: s.name, sharpe: s.best_sharpe!, status: s.status, runs: s.runs }))
			.sort((a, b) => b.sharpe - a.sharpe)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.sharpe)));
		return rows.map((r) => ({
			...r,
			barPct: (Math.abs(r.sharpe) / maxAbs) * 100,
			positive: r.sharpe > 0
		}));
	});

	const strategyProfitVsSortino = $derived.by(() => {
		const pts = data.strategies.filter(
			(s) =>
				s.best_profit_pct != null &&
				s.best_sortino != null &&
				isFinite(s.best_profit_pct) &&
				isFinite(s.best_sortino)
		);
		if (pts.length < 4) return null;
		const W = 360,
			H = 90,
			PAD = 10;
		const xs = pts.map((s) => s.best_sortino!),
			ys = pts.map((s) => s.best_profit_pct!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 0.01);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.01);
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const MODE_COLORS: Record<string, string> = {
			live: 'var(--ch-profit)',
			paper: 'var(--ch-violet)',
			backtest: 'var(--ch-warn)'
		};
		const dots = pts.map((s) => ({
			cx: toX(s.best_sortino!),
			cy: toY(s.best_profit_pct!),
			color: MODE_COLORS[s.mode] ?? 'var(--ch-axis)',
			name: s.name
		}));
		const zeroY = toY(0);
		return {
			W,
			H,
			dots,
			zeroY,
			xMin: xMin.toFixed(1),
			xMax: xMax.toFixed(1),
			yMin: yMin.toFixed(0),
			yMax: yMax.toFixed(0)
		};
	});

	const strategyDrawdownVsCalmar = $derived.by(() => {
		const pts = data.strategies.filter(
			(s) =>
				s.worst_dd_pct != null &&
				s.best_calmar != null &&
				isFinite(s.worst_dd_pct) &&
				isFinite(s.best_calmar) &&
				s.worst_dd_pct >= 0
		);
		if (pts.length < 4) return null;
		const W = 360,
			H = 90,
			PAD = 10;
		const xs = pts.map((s) => s.worst_dd_pct!),
			ys = pts.map((s) => s.best_calmar!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 0.01);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.01);
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const STATUS_COLOR: Record<string, string> = {
			active: 'var(--ch-profit)',
			inactive: 'var(--ch-axis-muted)',
			testing: 'var(--ch-warn)'
		};
		const dots = pts.map((s) => ({
			cx: toX(s.worst_dd_pct!),
			cy: toY(s.best_calmar!),
			color: STATUS_COLOR[s.status] ?? 'var(--ch-violet)',
			name: s.name
		}));
		const zeroY = yMin < 0 ? toY(0) : null;
		return {
			W,
			H,
			dots,
			zeroY,
			xMin: xMin.toFixed(1),
			xMax: xMax.toFixed(1),
			yMin: yMin.toFixed(1),
			yMax: yMax.toFixed(1)
		};
	});

	const strategyExpectedValueRanking = $derived.by(() => {
		const rows = filtered
			.filter(
				(s) =>
					s.best_win_rate != null &&
					isFinite(s.best_win_rate) &&
					s.best_win_rate > 0 &&
					s.best_profit_pct != null &&
					isFinite(s.best_profit_pct)
			)
			.map((s) => ({
				name: s.name,
				ev: (s.best_win_rate! / 100) * s.best_profit_pct!,
				mode: s.mode ?? 'unknown',
				wr: s.best_win_rate!,
				profit: s.best_profit_pct!
			}))
			.filter((r) => isFinite(r.ev))
			.sort((a, b) => b.ev - a.ev)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxEv = Math.max(...rows.map((r) => r.ev), 0.01);
		const MODE_COL: Record<string, string> = {
			long: 'var(--ch-profit)',
			short: 'var(--ch-loss)',
			'long/short': 'var(--ch-violet)'
		};
		return { rows, maxEv, MODE_COL };
	});

	const strategyDrawdownByMode = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const s of filtered) {
			if (s.worst_dd_pct == null || !isFinite(s.worst_dd_pct) || !s.mode) continue;
			if (!map[s.mode]) map[s.mode] = [];
			map[s.mode].push(s.worst_dd_pct);
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.length >= 1)
			.map(([mode, vals]) => {
				const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
				const max = Math.max(...vals);
				const min = Math.min(...vals);
				return { mode, avg, max, min, count: vals.length };
			})
			.sort((a, b) => a.avg - b.avg);
		if (rows.length < 1) return null;
		const maxAvg = Math.max(...rows.map((r) => r.avg), 0.01);
		const MODE_COL: Record<string, string> = {
			long: 'var(--ch-profit)',
			short: 'var(--ch-loss)',
			'long/short': 'var(--ch-violet)'
		};
		return { rows, maxAvg, MODE_COL };
	});

	const strategyProfitByAsset = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const s of filtered) {
			if (
				s.best_profit_pct == null ||
				!isFinite(s.best_profit_pct) ||
				!s.assets ||
				s.assets.length === 0
			)
				continue;
			const asset = s.assets[0];
			if (!map[asset]) map[asset] = [];
			map[asset].push(s.best_profit_pct);
		}
		const rows = Object.entries(map)
			.filter(([, v]) => v.length >= 1)
			.map(([asset, vals]) => ({
				asset,
				avg: vals.reduce((a, b) => a + b, 0) / vals.length,
				count: vals.length,
				best: Math.max(...vals)
			}))
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 10);
		if (rows.length < 2) return null;
		const maxAvg = Math.max(...rows.map((r) => r.avg), 0.01);
		return { rows, maxAvg };
	});

	const strategyWinRateByTimeframe = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const s of filtered) {
			if (s.best_win_rate == null || !isFinite(s.best_win_rate) || !s.timeframe) continue;
			if (!map[s.timeframe]) map[s.timeframe] = [];
			map[s.timeframe].push(s.best_win_rate);
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
			.filter(([, v]) => v.length >= 1)
			.map(([tf, vals]) => ({
				tf,
				avg: vals.reduce((a, b) => a + b, 0) / vals.length,
				count: vals.length,
				best: Math.max(...vals)
			}))
			.sort((a, b) => {
				const ai = TF_ORDER.indexOf(a.tf),
					bi = TF_ORDER.indexOf(b.tf);
				return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
			});
		if (rows.length < 2) return null;
		const maxAvg = Math.max(...rows.map((r) => r.avg), 1);
		return { rows, maxAvg };
	});

	const strategyRunCountByTimeframe = $derived.by(() => {
		const map: Record<string, number> = {};
		for (const s of filtered) {
			if (!s.timeframe) continue;
			map[s.timeframe] = (map[s.timeframe] ?? 0) + 1;
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
			.map(([tf, count]) => ({ tf, count }))
			.sort((a, b) => {
				const ai = TF_ORDER.indexOf(a.tf),
					bi = TF_ORDER.indexOf(b.tf);
				return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
			});
		if (rows.length < 2) return null;
		const maxCount = Math.max(...rows.map((r) => r.count), 1);
		const TF_COL: Record<string, string> = {
			'5m': 'var(--ch-violet)',
			'15m': 'var(--ch-profit)',
			'1h': 'var(--ch-warn)',
			'4h': 'var(--ch-loss)',
			'1d': 'var(--ch-teal)'
		};
		return { rows, maxCount, TF_COL };
	});

	const strategyTopSortinoLeaders = $derived.by(() => {
		const rows = filtered
			.filter(
				(s) => s.best_sortino != null && isFinite(s.best_sortino) && Math.abs(s.best_sortino) < 200
			)
			.map((s) => ({ name: s.name, sortino: s.best_sortino! }))
			.sort((a, b) => b.sortino - a.sortino)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.sortino)), 0.01);
		return { rows, maxAbs };
	});

	const strategyCalmarTierBreakdown = $derived.by(() => {
		const rows = filtered
			.filter(
				(s) => s.best_calmar != null && isFinite(s.best_calmar) && Math.abs(s.best_calmar) < 500
			)
			.map((s) => s.best_calmar!);
		if (rows.length < 4) return null;
		const tiers = [
			{ label: '>2', lo: 2, hi: Infinity, color: 'var(--ch-profit)' },
			{ label: '1–2', lo: 1, hi: 2, color: 'var(--ch-violet)' },
			{ label: '0–1', lo: 0, hi: 1, color: 'var(--ch-warn)' },
			{ label: '<0', lo: -Infinity, hi: 0, color: 'var(--ch-loss)' }
		];
		const buckets = tiers.map((t) => ({
			label: t.label,
			color: t.color,
			count: rows.filter((v) => v >= t.lo && v < t.hi).length
		}));
		const maxCount = Math.max(...buckets.map((b) => b.count), 1);
		const W = 320,
			H = 80,
			BAR_W = 56,
			GAP = 14,
			PAD_Y = 18;
		return { buckets, maxCount, total: rows.length, W, H, BAR_W, GAP, PAD_Y };
	});

	const strategyModeTimeframeMatrix = $derived.by(() => {
		const MODES = [...new Set(filtered.map((s) => s.mode).filter(Boolean))] as string[];
		const TF_ORDER = ['5m', '15m', '1h', '4h', '1d'];
		const TFS = TF_ORDER.filter((tf) => filtered.some((s) => s.timeframe === tf));
		if (MODES.length < 2 || TFS.length < 2) return null;
		const cells: { mode: string; tf: string; count: number }[] = [];
		for (const mode of MODES) {
			for (const tf of TFS) {
				const count = filtered.filter((s) => s.mode === mode && s.timeframe === tf).length;
				cells.push({ mode, tf, count });
			}
		}
		const maxCount = Math.max(...cells.map((c) => c.count), 1);
		return { MODES, TFS, cells, maxCount };
	});

	const strategyTopAssetsByBestProfit = $derived.by(() => {
		const ASSETS = [
			...new Set(filtered.flatMap((s) => s.assets ?? []).filter(Boolean))
		] as string[];
		if (ASSETS.length < 2) return null;
		const rows = ASSETS.map((asset) => {
			const matching = filtered.filter((s) => s.assets?.includes(asset));
			const profits = matching
				.map((s) => s.best_profit_pct)
				.filter((v): v is number => v != null && isFinite(v));
			if (profits.length === 0) return null;
			const avg = profits.reduce((a, b) => a + b, 0) / profits.length;
			const best = Math.max(...profits);
			return { asset, avg, best, count: matching.length };
		})
			.filter((r): r is NonNullable<typeof r> => r !== null && r.count >= 2)
			.sort((a, b) => b.avg - a.avg)
			.slice(0, 12);
		if (rows.length < 3) return null;
		const maxAvg = Math.max(...rows.map((r) => r.avg), 0.01);
		return { rows, maxAvg };
	});

	const strategyWinRateVsSortino = $derived.by(() => {
		const pts = data.strategies
			.filter(
				(s) =>
					s.best_win_rate != null &&
					isFinite(s.best_win_rate!) &&
					s.best_sortino != null &&
					isFinite(s.best_sortino!)
			)
			.map((s) => ({
				name: s.name,
				wr: s.best_win_rate!,
				sortino: s.best_sortino!,
				calmar: s.best_calmar ?? 0
			}));
		if (pts.length < 4) return null;
		const W = 520,
			H = 100,
			PAD = 12;
		const mnW = Math.min(...pts.map((p) => p.wr)),
			mxW = Math.max(...pts.map((p) => p.wr), mnW + 1);
		const mnS = Math.min(...pts.map((p) => p.sortino)),
			mxS = Math.max(...pts.map((p) => p.sortino), mnS + 0.01);
		const mxC = Math.max(...pts.map((p) => Math.abs(p.calmar)), 0.01);
		const toX = (v: number) => PAD + ((v - mnW) / (mxW - mnW)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mnS) / (mxS - mnS)) * (H - PAD * 2);
		const toR = (c: number) => 3 + (Math.abs(c) / mxC) * 7;
		const dots = pts.map((p) => ({
			cx: toX(p.wr),
			cy: toY(p.sortino),
			r: toR(p.calmar),
			color: p.sortino >= 0 ? 'var(--ch-violet-light)' : 'var(--ch-loss-light)'
		}));
		const zeroY = mnS <= 0 && mxS >= 0 ? toY(0) : null;
		return { W, H, dots, zeroY, count: pts.length };
	});

	const strategyBestProfitTimeline = $derived.by(() => {
		const pts = data.strategies
			.filter(
				(s) => s.last_imported != null && s.best_profit_pct != null && isFinite(s.best_profit_pct!)
			)
			.map((s) => ({ ts: new Date(s.last_imported!).getTime(), profit: s.best_profit_pct! }))
			.sort((a, b) => a.ts - b.ts);
		if (pts.length < 4) return null;
		const W = 560,
			H = 80,
			PAD = 8;
		const mnT = pts[0].ts,
			mxT = pts[pts.length - 1].ts;
		const mn = Math.min(...pts.map((p) => p.profit)),
			mx = Math.max(...pts.map((p) => p.profit), mn + 0.01);
		const toX = (t: number) => PAD + ((t - mnT) / Math.max(1, mxT - mnT)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / (mx - mn)) * (H - PAD * 2);
		const dots = pts.map((p) => ({
			cx: toX(p.ts),
			cy: toY(p.profit),
			color: p.profit >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'
		}));
		const zeroY = mn <= 0 && mx >= 0 ? toY(0) : null;
		return { W, H, dots, zeroY, count: pts.length };
	});

	const strategyRunCountDistribution = $derived.by(() => {
		const vals = data.strategies.filter((s) => s.runs != null && s.runs > 0).map((s) => s.runs!);
		if (vals.length < 4) return null;
		const mn = Math.min(...vals),
			mx = Math.max(...vals);
		if (mx <= mn) return null;
		const BUCKETS = 10,
			step = Math.ceil((mx - mn + 1) / BUCKETS);
		const counts = Array.from({ length: BUCKETS }, (_, i) => {
			const lo = mn + i * step,
				hi = lo + step;
			return { lo, count: vals.filter((v) => v >= lo && v < hi).length, label: String(lo) };
		});
		const maxCount = Math.max(...counts.map((b) => b.count), 1);
		const W = 440,
			H = 70,
			PAD = 8,
			barW = Math.floor((W - PAD * 2) / BUCKETS) - 1;
		return { counts, maxCount, W, H, PAD, barW };
	});

	const strategyCalmarVsBestProfit = $derived.by(() => {
		const pts = data.strategies
			.filter(
				(s) =>
					s.best_calmar != null &&
					isFinite(s.best_calmar!) &&
					s.best_profit_pct != null &&
					isFinite(s.best_profit_pct!)
			)
			.map((s) => ({ calmar: s.best_calmar!, profit: s.best_profit_pct!, name: s.name }));
		if (pts.length < 4) return null;
		const W = 520,
			H = 100,
			PAD = 10;
		const mnC = Math.min(...pts.map((p) => p.calmar)),
			mxC = Math.max(...pts.map((p) => p.calmar), mnC + 0.01);
		const mnP = Math.min(...pts.map((p) => p.profit)),
			mxP = Math.max(...pts.map((p) => p.profit), mnP + 0.01);
		const toX = (v: number) => PAD + ((v - mnC) / (mxC - mnC)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mnP) / (mxP - mnP)) * (H - PAD * 2);
		const dots = pts.map((p) => ({
			cx: toX(p.calmar),
			cy: toY(p.profit),
			color:
				p.calmar >= 0 && p.profit >= 0
					? 'var(--ch-profit)'
					: p.calmar < 0 || p.profit < 0
						? 'var(--ch-loss-light)'
						: 'var(--ch-warn)'
		}));
		const zeroX = mnC <= 0 && mxC >= 0 ? toX(0) : null;
		const zeroY = mnP <= 0 && mxP >= 0 ? toY(0) : null;
		return { W, H, dots, zeroX, zeroY, count: pts.length };
	});

	const strategyWorstDrawdownRanking = $derived.by(() => {
		const rows = strategies
			.filter((s) => s.worst_dd_pct != null && isFinite(s.worst_dd_pct))
			.map((s) => ({
				name: (s.name ?? '').slice(0, 24),
				dd: Math.abs(s.worst_dd_pct!),
				runs: s.runs
			}))
			.sort((a, b) => a.dd - b.dd)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxDD = Math.max(...rows.map((r) => r.dd), 0.01);
		return { rows, maxDD };
	});

	const strategyAvgTradesByTimeframe = $derived.by(() => {
		const map: Record<string, number[]> = {};
		for (const s of strategies) {
			if (!s.timeframe || s.runs == null) continue;
			if (!map[s.timeframe]) map[s.timeframe] = [];
			map[s.timeframe].push(s.runs);
		}
		const TF_ORD = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '8h', '1d'];
		const rows = Object.entries(map)
			.map(([tf, vals]) => ({
				tf,
				avg: vals.reduce((a, b) => a + b, 0) / vals.length,
				count: vals.length
			}))
			.sort(
				(a, b) =>
					(TF_ORD.indexOf(a.tf) === -1 ? 99 : TF_ORD.indexOf(a.tf)) -
					(TF_ORD.indexOf(b.tf) === -1 ? 99 : TF_ORD.indexOf(b.tf))
			);
		if (rows.length < 2) return null;
		const maxAvg = Math.max(...rows.map((r) => r.avg), 1);
		const W = 420,
			H = 80,
			PAD = 8,
			barW = Math.min(55, Math.floor((W - PAD * 2) / rows.length) - 3);
		return { rows, maxAvg, W, H, PAD, barW };
	});

	const strategyTopSortinoLeaderboard = $derived.by(() => {
		const rows = strategies
			.filter((s) => s.best_sortino != null && s.best_sortino > 0 && isFinite(s.best_sortino))
			.map((s) => ({ name: (s.name ?? '').slice(0, 24), sortino: s.best_sortino!, runs: s.runs }))
			.sort((a, b) => b.sortino - a.sortino)
			.slice(0, 14);
		if (rows.length < 3) return null;
		const maxSortino = Math.max(...rows.map((r) => r.sortino), 0.01);
		return { rows, maxSortino };
	});

	const strategyBestSharpeDistribution = $derived.by(() => {
		const vals = data.strategies
			.filter(
				(s) =>
					s.best_sharpe != null &&
					isFinite(s.best_sharpe) &&
					s.best_sharpe > -5 &&
					s.best_sharpe < 50
			)
			.map((s) => s.best_sharpe!);
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
			mn: mn.toFixed(1),
			mx: mx.toFixed(1),
			avg,
			total: vals.length
		};
	});

	const strategyBestCalmarDistribution = $derived.by(() => {
		const vals = data.strategies
			.filter(
				(s) =>
					s.best_calmar != null &&
					isFinite(s.best_calmar) &&
					s.best_calmar > -5 &&
					s.best_calmar < 100
			)
			.map((s) => s.best_calmar!);
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
			mn: mn.toFixed(1),
			mx: mx.toFixed(1),
			avg,
			total: vals.length
		};
	});

	const strategyTimeframeCountHeatmap = $derived.by(() => {
		const tfs = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d'];
		const map = new Map<string, Map<string, number>>();
		for (const s of data.strategies) {
			if (!s.name || !s.timeframe) continue;
			const tf = s.timeframe;
			const decade = (s.name ?? '').slice(0, 4);
			if (!map.has(decade)) map.set(decade, new Map());
			const inner = map.get(decade)!;
			inner.set(tf, (inner.get(tf) ?? 0) + 1);
		}
		const decades = [...map.keys()].sort().slice(0, 8);
		const usedTfs = tfs.filter((tf) => decades.some((d) => map.get(d)?.has(tf)));
		if (decades.length < 2 || usedTfs.length < 2) return null;
		const cells = decades.flatMap((d, di) =>
			usedTfs.map((tf, ti) => ({ d, tf, count: map.get(d)?.get(tf) ?? 0, di, ti }))
		);
		const maxCount = Math.max(...cells.map((c) => c.count), 1);
		const cellW = 28,
			cellH = 16,
			PAD = 30;
		const W = PAD + usedTfs.length * (cellW + 2),
			H = PAD + decades.length * (cellH + 2);
		return { cells, decades, usedTfs, maxCount, cellW, cellH, PAD, W, H };
	});

	const strategyRunCountVsBestProfit = $derived.by(() => {
		const pts = data.strategies
			.filter(
				(s) =>
					s.runs != null && s.runs >= 2 && s.best_profit_pct != null && isFinite(s.best_profit_pct)
			)
			.map((s) => ({
				runs: s.runs!,
				profit: s.best_profit_pct!,
				name: (s.name ?? '').slice(0, 10)
			}));
		if (pts.length < 5) return null;
		const rMax = Math.max(...pts.map((p) => p.runs), 1);
		const pMin = Math.min(...pts.map((p) => p.profit)),
			pMax = Math.max(...pts.map((p) => p.profit), pMin + 0.01);
		const W = 380,
			H = 100,
			PAD = 12;
		const toX = (v: number) => PAD + (v / rMax) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - pMin) / (pMax - pMin)) * (H - PAD * 2);
		const zeroY = Math.max(PAD, Math.min(H - PAD, toY(0)));
		const dots = pts.map((p) => ({
			cx: toX(p.runs),
			cy: toY(p.profit),
			color: p.profit >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss-light)'
		}));
		return {
			dots,
			W,
			H,
			PAD,
			zeroY,
			rMax,
			pMin: pMin.toFixed(0),
			pMax: pMax.toFixed(0),
			count: pts.length
		};
	});

	const strategyAvgCalmarByTimeframe = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const s of data.strategies) {
			if (!s.timeframe || s.best_calmar == null || !isFinite(s.best_calmar) || s.best_calmar > 50)
				continue;
			if (!map.has(s.timeframe)) map.set(s.timeframe, []);
			map.get(s.timeframe)!.push(s.best_calmar);
		}
		const tfs = [...map.keys()].sort();
		if (tfs.length < 2) return null;
		const rows = tfs.map((tf) => {
			const vals = map.get(tf)!;
			const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
			const med = [...vals].sort((a, b) => a - b)[Math.floor(vals.length / 2)];
			return { tf, avg, med, count: vals.length };
		});
		const maxAvg = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 340,
			H = 70,
			PAD = 8,
			barW = Math.max(8, Math.floor((W - PAD * 2) / tfs.length) - 3);
		const midY = H / 2;
		const toH = (v: number) => Math.max(2, (Math.abs(v) / maxAvg) * (H / 2 - PAD));
		return { rows, maxAvg: maxAvg.toFixed(1), W, H, PAD, barW, midY, toH };
	});

	const strategyModeWinRateComparison = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const s of data.strategies) {
			if (!s.mode || s.best_win_rate == null || !isFinite(s.best_win_rate)) continue;
			const mode = s.mode;
			if (!map.has(mode)) map.set(mode, []);
			map.get(mode)!.push(s.best_win_rate);
		}
		const rows = [...map.entries()]
			.filter(([, vals]) => vals.length >= 2)
			.map(([mode, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const med = sorted[Math.floor(sorted.length / 2)];
				const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
				return { mode, med, avg, count: vals.length };
			})
			.sort((a, b) => b.med - a.med);
		if (rows.length < 2) return null;
		const maxMed = Math.max(...rows.map((r) => r.med), 0.01);
		return { rows, maxMed };
	});

	const strategyBestProfitHistogram = $derived.by(() => {
		const vals = data.strategies
			.filter((s) => s.best_profit_pct != null && isFinite(s.best_profit_pct))
			.map((s) => s.best_profit_pct!);
		if (vals.length < 6) return null;
		const mn = Math.min(...vals),
			mx = Math.max(...vals);
		const BINS = 10,
			step = Math.max(0.01, (mx - mn) / BINS);
		const counts = Array.from({ length: BINS }, (_, i) => {
			const lo = mn + i * step,
				hi = lo + step;
			return {
				lo,
				count: vals.filter((v) => v >= lo && (i === BINS - 1 ? v <= mx : v < hi)).length
			};
		});
		const maxCount = Math.max(...counts.map((c) => c.count), 1);
		const W = 360,
			H = 70,
			PAD = 8,
			barW = Math.floor((W - PAD * 2) / BINS) - 1;
		const zeroX = Math.max(PAD, Math.min(W - PAD, PAD + ((0 - mn) / (mx - mn)) * (W - PAD * 2)));
		return {
			counts,
			maxCount,
			W,
			H,
			PAD,
			barW,
			mn: mn.toFixed(0),
			mx: mx.toFixed(0),
			zeroX,
			total: vals.length
		};
	});

	const strategyRunCountTimeline = $derived.by(() => {
		const map = new Map<string, Map<string, number>>();
		for (const s of data.strategies) {
			if (!s.name || !s.last_imported) continue;
			const mo = s.last_imported.slice(0, 7);
			if (!map.has(mo)) map.set(mo, new Map());
			map.get(mo)!.set(s.name, (map.get(mo)!.get(s.name) ?? 0) + 1);
		}
		const months = [...map.keys()].sort();
		if (months.length < 3) return null;
		const pts = months.map((mo, i) => ({ i, mo: mo.slice(5), count: map.get(mo)!.size }));
		const maxCount = Math.max(...pts.map((p) => p.count), 1);
		const W = 360,
			H = 65,
			PAD = 10;
		const toX = (i: number) => PAD + (i / Math.max(pts.length - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - v / maxCount) * (H - PAD * 2);
		const poly = pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.count).toFixed(1)}`).join(' ');
		const area =
			poly + ` ${toX(pts.length - 1).toFixed(1)},${H - PAD} ${toX(0).toFixed(1)},${H - PAD}`;
		return { pts, poly, area, maxCount, W, H, PAD };
	});

	const strategyRunCountHistogram = $derived.by(() => {
		const counts = data.strategies.map((s) => s.runs ?? 0).filter((r) => r > 0);
		if (counts.length < 5) return null;
		const maxR = Math.max(...counts);
		const bins = 10;
		const binSize = Math.ceil(maxR / bins);
		const buckets = Array.from({ length: bins }, (_, i) => ({
			lo: i * binSize + 1,
			hi: (i + 1) * binSize,
			count: 0
		}));
		for (const r of counts) {
			const bi = Math.min(bins - 1, Math.floor((r - 1) / binSize));
			buckets[bi].count++;
		}
		const maxCount = Math.max(...buckets.map((b) => b.count), 1);
		const W = 360,
			H = 72,
			PAD = 10;
		const bw = (W - PAD * 2) / bins - 2;
		const toH = (c: number) => Math.max(2, (c / maxCount) * (H - PAD - 14));
		const bars = buckets.map((b, i) => ({
			x: PAD + i * ((W - PAD * 2) / bins),
			h: toH(b.count),
			count: b.count,
			label: b.count > 0 ? `${b.lo}` : ''
		}));
		return { bars, bw, W, H, PAD, maxCount, total: counts.length };
	});

	const strategySharpeVsWinRateScatter = $derived.by(() => {
		const pts = data.strategies
			.filter(
				(s) =>
					s.best_sharpe != null &&
					isFinite(s.best_sharpe) &&
					Math.abs(s.best_sharpe) < 50 &&
					s.best_win_rate != null &&
					isFinite(s.best_win_rate) &&
					s.best_profit_pct != null &&
					isFinite(s.best_profit_pct)
			)
			.map((s) => ({
				name: s.name?.slice(0, 10) ?? '',
				sharpe: s.best_sharpe!,
				wr: s.best_win_rate!,
				profit: s.best_profit_pct!
			}));
		if (pts.length < 5) return null;
		const sMin = Math.min(...pts.map((p) => p.sharpe)),
			sMax = Math.max(...pts.map((p) => p.sharpe), sMin + 0.1);
		const wMin = Math.min(...pts.map((p) => p.wr)),
			wMax = Math.max(...pts.map((p) => p.wr), wMin + 0.1);
		const W = 360,
			H = 92,
			PAD = 12;
		const toX = (v: number) => PAD + ((v - wMin) / (wMax - wMin)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - sMin) / (sMax - sMin)) * (H - PAD * 2);
		const zeroY = Math.max(PAD, Math.min(H - PAD, toY(0)));
		const dots = pts.map((p) => ({
			cx: toX(p.wr),
			cy: toY(p.sharpe),
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
			wMin: wMin.toFixed(0),
			wMax: wMax.toFixed(0),
			sMin: sMin.toFixed(1),
			sMax: sMax.toFixed(1),
			count: pts.length
		};
	});

	const strategyStatusProfitComparison = $derived.by(() => {
		const statuses = ['active', 'inactive', 'archived'];
		const rows = statuses
			.map((s) => {
				const group = data.strategies.filter(
					(st) => st.status === s && st.best_profit_pct != null && isFinite(st.best_profit_pct)
				);
				if (group.length === 0) return null;
				const profits = group.map((st) => st.best_profit_pct!).sort((a, b) => a - b);
				const avg = profits.reduce((a, v) => a + v, 0) / profits.length;
				const mid = Math.floor(profits.length / 2);
				const median = profits.length % 2 ? profits[mid] : (profits[mid - 1] + profits[mid]) / 2;
				const q1 = profits[Math.floor(profits.length / 4)];
				const q3 = profits[Math.floor((profits.length * 3) / 4)];
				return { status: s, avg, median, q1, q3, count: profits.length };
			})
			.filter(Boolean) as {
			status: string;
			avg: number;
			median: number;
			q1: number;
			q3: number;
			count: number;
		}[];
		if (rows.length < 2) return null;
		const allVals = rows.flatMap((r) => [r.q1, r.q3, r.avg]);
		const mn = Math.min(...allVals),
			mx = Math.max(...allVals, mn + 0.1);
		const W = 300,
			H = rows.length * 28 + 10,
			PAD = 8,
			barMaxW = W - 100,
			midX = PAD + barMaxW / 2;
		const toX = (v: number) => PAD + ((v - mn) / (mx - mn)) * barMaxW;
		const zeroX = Math.max(PAD, Math.min(PAD + barMaxW, toX(0)));
		const COLORS: Record<string, string> = {
			active: 'var(--ch-profit)',
			inactive: 'var(--ch-axis)',
			archived: 'var(--ch-loss)'
		};
		const items = rows.map((r) => ({
			...r,
			avgX: toX(r.avg),
			q1X: toX(r.q1),
			q3X: toX(r.q3),
			color: COLORS[r.status] ?? 'var(--ch-violet)'
		}));
		return { items, W, H, PAD, barMaxW, midX, zeroX, mn: mn.toFixed(1), mx: mx.toFixed(1) };
	});

	const strategySortinoBars = $derived.by(() => {
		const rows = data.strategies
			.filter(
				(s) => s.best_sortino != null && isFinite(s.best_sortino) && Math.abs(s.best_sortino) < 200
			)
			.map((s) => ({ name: (s.name ?? '').slice(0, 18), sortino: s.best_sortino!, runs: s.runs }))
			.sort((a, b) => b.sortino - a.sortino)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.sortino)), 0.01);
		const W = 340,
			H = rows.length * 16 + 6,
			PAD = 8,
			barMaxW = W - 100;
		return { rows, maxAbs, W, H, PAD, barMaxW };
	});

	const strategyCalmarHistogram = $derived.by(() => {
		const vals = data.strategies
			.filter(
				(s) =>
					s.best_calmar != null &&
					isFinite(s.best_calmar) &&
					s.best_calmar > -50 &&
					s.best_calmar < 200
			)
			.map((s) => s.best_calmar!);
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
			count: b.count,
			color: b.lo >= 0 ? 'var(--ch-violet-light)' : 'var(--ch-loss-light)',
			label: b.lo.toFixed(1)
		}));
		return { bars, bw, W, H, PAD, zeroX, mn: mn.toFixed(1), mx: mx.toFixed(1), total: vals.length };
	});

	const strategyAvgWinRateByStatus = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const s of data.strategies) {
			if (!s.status || s.best_win_rate == null || !isFinite(s.best_win_rate)) continue;
			const arr = map.get(s.status) ?? [];
			arr.push(s.best_win_rate);
			map.set(s.status, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([status, vals]) => ({
				status,
				avg: vals.reduce((a, v) => a + v, 0) / vals.length,
				count: vals.length
			}))
			.sort((a, b) => b.avg - a.avg);
		const maxVal = Math.max(...rows.map((r) => r.avg), 0.01);
		const W = 280,
			H = 72,
			PAD = 10;
		const bw = Math.max(20, Math.floor((W - PAD * 2) / rows.length) - 8);
		const bars = rows.map((r, i) => ({
			x: PAD + i * ((W - PAD * 2) / rows.length) + 4,
			h: Math.max(4, (r.avg / maxVal) * (H - PAD * 2 - 14)),
			avg: r.avg,
			status: r.status,
			count: r.count,
			color:
				r.status === 'active'
					? 'var(--ch-profit)'
					: r.status === 'inactive'
						? 'var(--ch-warn)'
						: 'var(--ch-axis-muted)'
		}));
		return { bars, bw, W, H, PAD };
	});

	const strategyTopRunsLeaderboard = $derived.by(() => {
		const rows = data.strategies
			.filter((s) => s.runs != null && s.runs > 0)
			.map((s) => ({
				name: (s.name ?? '').slice(0, 18),
				runs: s.runs,
				profit: s.best_profit_pct ?? 0,
				status: s.status ?? ''
			}))
			.sort((a, b) => b.runs - a.runs)
			.slice(0, 10);
		if (rows.length < 3) return null;
		const maxRuns = Math.max(...rows.map((r) => r.runs), 1);
		const W = 340,
			H = rows.length * 16 + 6,
			PAD = 8,
			barMaxW = W - 100;
		return { rows, maxRuns, W, H, PAD, barMaxW };
	});

	const strategyBestProfitVsRunCount = $derived.by(() => {
		const pts = data.strategies
			.filter(
				(s) =>
					s.runs != null && s.runs > 0 && s.best_profit_pct != null && isFinite(s.best_profit_pct)
			)
			.map((s) => ({ runs: s.runs, profit: s.best_profit_pct!, status: s.status ?? '' }));
		if (pts.length < 5) return null;
		const maxRuns = Math.max(...pts.map((p) => p.runs), 1);
		const minP = Math.min(...pts.map((p) => p.profit));
		const maxP = Math.max(...pts.map((p) => p.profit));
		const rangeP = maxP - minP || 1;
		const W = 360,
			H = 80,
			PAD = 12;
		const zeroY = Math.max(PAD, Math.min(H - PAD, PAD + (maxP / rangeP) * (H - PAD * 2)));
		const dots = pts.map((p) => ({
			cx: PAD + (p.runs / maxRuns) * (W - PAD * 2),
			cy: PAD + ((maxP - p.profit) / rangeP) * (H - PAD * 2),
			color:
				p.status === 'active'
					? 'var(--ch-profit)'
					: p.status === 'inactive'
						? 'var(--ch-warn-light)'
						: 'var(--ch-axis-muted)'
		}));
		return { dots, W, H, PAD, zeroY, maxRuns, minP: minP.toFixed(1), maxP: maxP.toFixed(1) };
	});

	const strategyMedianSharpeByTF = $derived.by(() => {
		const map = new Map<string, number[]>();
		for (const s of data.strategies) {
			if (
				!s.timeframe ||
				s.best_sharpe == null ||
				!isFinite(s.best_sharpe) ||
				Math.abs(s.best_sharpe) > 50
			)
				continue;
			const arr = map.get(s.timeframe) ?? [];
			arr.push(s.best_sharpe);
			map.set(s.timeframe, arr);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([tf, vals]) => {
				const sorted = [...vals].sort((a, b) => a - b);
				const mid = Math.floor(sorted.length / 2);
				const median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
				return { tf, median, count: vals.length };
			})
			.sort((a, b) => b.median - a.median);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.median)), 0.01);
		const W = 320,
			H = 72,
			PAD = 10;
		const bw = Math.max(4, Math.floor((W - PAD * 2) / rows.length) - 4);
		const midY = H / 2;
		const bars = rows.map((r, i) => ({
			x: PAD + i * ((W - PAD * 2) / rows.length) + 2,
			h: Math.max(2, (Math.abs(r.median) / maxAbs) * (midY - PAD - 4)),
			tf: r.tf,
			median: r.median,
			count: r.count,
			color:
				r.median >= 1 ? 'var(--ch-profit)' : r.median >= 0 ? 'var(--ch-warn)' : 'var(--ch-loss)'
		}));
		return { bars, bw, W, H, PAD, midY };
	});

	const strategyTopSharpeLeaderboard = $derived.by(() => {
		if (!strategies || strategies.length < 3) return null;
		const rows = [...strategies]
			.filter((s) => s.best_sharpe != null)
			.map((s) => ({ name: (s.name ?? '').slice(0, 16), sharpe: s.best_sharpe as number }))
			.sort((a, b) => b.sharpe - a.sharpe)
			.slice(0, 8);
		if (rows.length < 3) return null;
		const maxSharpe = Math.max(...rows.map((r) => r.sharpe), 0.01);
		const W = 300,
			H = rows.length * 18 + 6,
			PAD = 8,
			barMaxW = W - 110;
		return { rows, maxSharpe, W, H, PAD, barMaxW };
	});

	const strategyTopWinRateLeaderboard = $derived.by(() => {
		if (!strategies || strategies.length < 3) return null;
		const rows = [...strategies]
			.filter((s) => s.best_win_rate != null)
			.map((s) => ({ name: (s.name ?? '').slice(0, 16), wr: (s.best_win_rate as number) * 100 }))
			.sort((a, b) => b.wr - a.wr)
			.slice(0, 8);
		if (rows.length < 3) return null;
		const maxWR = Math.max(...rows.map((r) => r.wr), 1);
		const W = 300,
			H = rows.length * 18 + 6,
			PAD = 8,
			barMaxW = W - 110;
		return { rows, maxWR, W, H, PAD, barMaxW };
	});

	const strategyAvgProfitVsDrawdownScatter = $derived.by(() => {
		if (!strategies || strategies.length < 5) return null;
		const pts = strategies
			.filter((s) => s.best_profit_pct != null && s.worst_dd_pct != null)
			.map((s) => ({
				x: s.worst_dd_pct as number,
				y: s.best_profit_pct as number,
				name: ((s.name as string) ?? '').slice(0, 8)
			}))
			.filter((p) => p.x > 0 && p.x < 100);
		if (pts.length < 4) return null;
		const maxX = Math.max(...pts.map((p) => p.x), 1);
		const maxAbsY = Math.max(...pts.map((p) => Math.abs(p.y)), 0.01);
		const W = 280,
			H = 100,
			PAD = 12,
			midY = H / 2;
		return { pts, maxX, maxAbsY, W, H, PAD, midY };
	});

	const strategyTotalRunsByTF = $derived.by(() => {
		if (!strategies || strategies.length < 3) return null;
		const byTF = new Map<string, number>();
		for (const s of strategies) {
			if (s.timeframe == null) continue;
			byTF.set(
				s.timeframe as string,
				(byTF.get(s.timeframe as string) ?? 0) + ((s.runs as number) ?? 1)
			);
		}
		if (byTF.size < 2) return null;
		const bars = [...byTF.entries()]
			.sort(([, a], [, b]) => b - a)
			.map(([tf, cnt]) => ({ tf, cnt }));
		const maxCnt = Math.max(...bars.map((b) => b.cnt), 1);
		const W = 300,
			H = 65,
			PAD = 8;
		const bw = Math.max(8, (W - PAD * 2) / bars.length - 2);
		return { bars, maxCnt, W, H, PAD, bw };
	});

	const strategyCalmarTrend = $derived.by(() => {
		if (!strategies || strategies.length < 5) return null;
		const byMonth = new Map<string, number[]>();
		for (const s of strategies) {
			if (!s.last_imported || s.best_calmar == null) continue;
			const mo = (s.last_imported as string).slice(0, 7);
			const arr = byMonth.get(mo) ?? [];
			arr.push(s.best_calmar as number);
			byMonth.set(mo, arr);
		}
		if (byMonth.size < 3) return null;
		const pts = [...byMonth.entries()]
			.sort(([a], [b]) => a.localeCompare(b))
			.map(([mo, arr]) => ({ mo: mo.slice(5), avg: arr.reduce((s, v) => s + v, 0) / arr.length }));
		const minV = Math.min(...pts.map((p) => p.avg));
		const maxV = Math.max(...pts.map((p) => p.avg), minV + 0.01);
		const W = 300,
			H = 65,
			PAD = 10;
		const toX = (i: number) => PAD + (i / Math.max(pts.length - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - minV) / (maxV - minV)) * (H - PAD * 2);
		const polyline = pts.map((p, i) => `${toX(i).toFixed(1)},${toY(p.avg).toFixed(1)}`).join(' ');
		return { pts, polyline, toX, W, H, PAD, minV: minV.toFixed(2), maxV: maxV.toFixed(2) };
	});

	const strategyProfitHistogram = $derived.by(() => {
		if (!strategies || strategies.length < 8) return null;
		const vals = strategies
			.filter((s) => s.best_profit_pct != null)
			.map((s) => s.best_profit_pct as number)
			.sort((a, b) => a - b);
		if (vals.length < 6) return null;
		const minV = vals[0],
			maxV = vals[vals.length - 1];
		const bins = 10;
		const binW = (maxV - minV) / bins || 1;
		const counts = Array(bins).fill(0);
		for (const v of vals) {
			const idx = Math.min(bins - 1, Math.floor((v - minV) / binW));
			counts[idx]++;
		}
		const maxCnt = Math.max(...counts, 1);
		const W = 300,
			H = 65,
			PAD = 8;
		const bw = (W - PAD * 2) / bins - 1;
		const zeroX = PAD + (-minV / (maxV - minV)) * (W - PAD * 2);
		return {
			counts,
			maxCnt,
			bins,
			binW,
			W,
			H,
			PAD,
			bw,
			minV: minV.toFixed(1),
			maxV: maxV.toFixed(1),
			zeroX
		};
	});

	const strategyTopCalmarLeaderboard = $derived.by(() => {
		if (!strategies || strategies.length < 4) return null;
		const rows = [...strategies]
			.filter((s) => s.best_calmar != null)
			.sort((a, b) => (b.best_calmar as number) - (a.best_calmar as number))
			.slice(0, 10)
			.map((s) => ({
				name: ((s.name as string) ?? '').slice(0, 16),
				calmar: s.best_calmar as number
			}));
		if (rows.length < 3) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.calmar)), 0.01);
		const W = 300,
			H = rows.length * 18 + 10,
			PAD = 8,
			midX = W / 2;
		const bh = 12;
		return { rows, maxAbs, W, H, PAD, midX, bh };
	});

	const strategyTopSharpeByTF = $derived.by(() => {
		if (!strategies || strategies.length < 5) return null;
		const byTF = new Map<string, number[]>();
		for (const s of strategies) {
			if (!s.timeframe || s.best_sharpe == null) continue;
			const arr = byTF.get(s.timeframe as string) ?? [];
			arr.push(s.best_sharpe as number);
			byTF.set(s.timeframe as string, arr);
		}
		const bars = [...byTF.entries()]
			.filter(([, arr]) => arr.length >= 2)
			.map(([tf, arr]) => ({ label: tf, avg: arr.reduce((s, v) => s + v, 0) / arr.length }))
			.sort((a, b) => b.avg - a.avg);
		if (bars.length < 2) return null;
		const maxAbs = Math.max(...bars.map((b) => Math.abs(b.avg)), 0.01);
		const W = 300,
			H = 65,
			PAD = 8,
			midY = H / 2;
		const bw = Math.max(16, (W - PAD * 2) / bars.length - 4);
		return { bars, maxAbs, W, H, PAD, midY, bw };
	});

	const strategyWinRateVsSortinoScatter = $derived.by(() => {
		if (!strategies || strategies.length < 8) return null;
		const pts = strategies
			.filter((s) => s.best_win_rate != null && s.best_sortino != null)
			.map((s) => ({
				x: s.best_win_rate as number,
				y: s.best_sortino as number,
				name: s.name as string
			}));
		if (pts.length < 6) return null;
		const xs = pts.map((p) => p.x),
			ys = pts.map((p) => p.y);
		const minX = Math.min(...xs),
			maxX = Math.max(...xs),
			minY = Math.min(...ys),
			maxY = Math.max(...ys);
		const W = 300,
			H = 80,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - minX) / (maxX - minX || 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - minY) / (maxY - minY || 1)) * (H - PAD * 2);
		return { pts, W, H, PAD, toX, toY, minX: minX.toFixed(0), maxX: maxX.toFixed(0) };
	});

	const strategyDrawdownHistogram = $derived.by(() => {
		if (!strategies || strategies.length < 8) return null;
		const vals = strategies
			.filter((s) => s.worst_dd_pct != null && (s.worst_dd_pct as number) >= 0)
			.map((s) => s.worst_dd_pct as number)
			.sort((a, b) => a - b);
		if (vals.length < 6) return null;
		const minV = vals[0],
			maxV = Math.min(vals[vals.length - 1], 100);
		const bins = 10;
		const binW = (maxV - minV) / bins || 1;
		const counts = Array(bins).fill(0);
		for (const v of vals) {
			if (v > maxV) continue;
			const idx = Math.min(bins - 1, Math.floor((v - minV) / binW));
			counts[idx]++;
		}
		const maxCnt = Math.max(...counts, 1);
		const W = 300,
			H = 65,
			PAD = 8;
		const bw = (W - PAD * 2) / bins - 1;
		return {
			counts,
			maxCnt,
			bins,
			binW,
			W,
			H,
			PAD,
			bw,
			minV: minV.toFixed(1),
			maxV: maxV.toFixed(1)
		};
	});
</script>

<svelte:head><title>{t(lang, 'strategies.title')}</title></svelte:head>

<main class="mx-auto w-full max-w-[1600px] px-4 py-8 sm:px-6">
	<header class="mb-8">
		<h1 class="text-2xl font-semibold tracking-tight">{t(lang, 'strategies.title')}</h1>
		<p class="mt-2 max-w-3xl text-sm text-muted-foreground">{t(lang, 'strategies.subtitle')}</p>
	</header>

	<!-- Podium: top-3 by best_profit_pct -->
	{#if podium.length > 0}
		<section class="mb-6">
			<h2 class="mb-3 text-xs font-semibold tracking-widest text-muted-foreground uppercase">
				Top Performers <ChartInfo metric="leaderboard" {lang} />
			</h2>
			<div class="grid gap-3 sm:grid-cols-3">
				{#each podium as s, i (s.name)}
					<!-- StrategyInfo (a <button>) lives outside the <a> so HTML is valid. -->
					<div
						class="flex items-center gap-3 rounded-lg border bg-card p-3 transition-colors hover:border-primary"
					>
						<a href={`/strategies/${s.name}`} class="flex min-w-0 flex-1 items-center gap-3">
							<span class="text-2xl leading-none">{rankEmoji[i]}</span>
							<div class="min-w-0 flex-1">
								<p class="truncate text-sm font-semibold text-foreground">{s.name}</p>
								<div class="mt-1 flex items-center gap-3 font-mono text-xs text-muted-foreground">
									<span
										class:text-green-500={(s.best_profit_pct ?? 0) > 0}
										class:text-red-500={(s.best_profit_pct ?? 0) < 0}
									>
										{fmtPct(s.best_profit_pct)}
									</span>
									<span>S {s.best_sharpe == null ? '—' : s.best_sharpe.toFixed(2)}</span>
									<span>C {s.best_calmar == null ? '—' : s.best_calmar.toFixed(2)}</span>
								</div>
							</div>
						</a>
						<StrategyInfo
							strategy={s.name}
							{lang}
							kelly={kellyByName.get(s.name) ?? null}
							size="xs"
						/>
					</div>
				{/each}
			</div>
		</section>
	{/if}

	<!-- Efficient frontier scatter -->
	{#if frontierData}
		{@const fd = frontierData}
		<section class="mb-6 rounded-lg border bg-card p-4">
			<div class="mb-2 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Efficient Frontier <span class="ml-1 text-xs font-normal text-muted-foreground"
						>Sharpe vs MaxDD · lower-left = worse, upper-left = best</span
					>
					<ChartInfo metric="scatter" {lang} />
				</h2>
				<div class="flex gap-3 text-[10px] text-muted-foreground">
					<span><span class="mr-1 inline-block h-2 w-2 rounded-full bg-green-500"></span>spot</span>
					<span><span class="mr-1 inline-block h-2 w-2 rounded-full bg-red-400"></span>futures</span
					>
					<span
						><span class="mr-1 inline-block h-2 w-2 rounded-full bg-violet-400"></span>hybrid</span
					>
				</div>
			</div>
			<div class="overflow-x-auto">
				<svg viewBox="0 0 {fd.W} {fd.H}" class="w-full" style="height:140px;min-width:280px">
					<!-- Grid -->
					{#each [0.25, 0.5, 0.75, 1] as f, _i (_i)}
						<line
							x1={fd.PL + f * (fd.W - fd.PL - fd.PR)}
							y1={fd.PT}
							x2={fd.PL + f * (fd.W - fd.PL - fd.PR)}
							y2={fd.H - fd.PB}
							stroke="var(--ch-rule-faint)"
							stroke-width="1"
						/>
						<text
							x={fd.PL + f * (fd.W - fd.PL - fd.PR)}
							y={fd.H - 4}
							text-anchor="middle"
							font-size="7"
							fill="var(--ch-rule-strong)">{(fd.xMax * f).toFixed(0)}%</text
						>
					{/each}
					{#each [0.25, 0.5, 0.75, 1] as f, _i (_i)}
						{@const y = fd.PT + (1 - f) * (fd.H - fd.PT - fd.PB)}
						<line
							x1={fd.PL}
							y1={y}
							x2={fd.W - fd.PR}
							y2={y}
							stroke="var(--ch-rule-faint)"
							stroke-width="1"
						/>
						<text
							x={fd.PL - 3}
							y={y + 3}
							text-anchor="end"
							font-size="7"
							fill="var(--ch-rule-strong)">{(fd.yMin + (fd.yMax - fd.yMin) * f).toFixed(1)}</text
						>
					{/each}
					<!-- Axis labels -->
					<text
						x={(fd.PL + fd.W - fd.PR) / 2}
						y={fd.H}
						text-anchor="middle"
						font-size="8"
						fill="var(--ch-rule-strong)">MaxDD% →</text
					>
					<!-- Pareto frontier line -->
					{#if fd.paretoLine}
						<polyline
							points={fd.paretoLine}
							fill="none"
							stroke="var(--ch-warn-light)"
							stroke-width="1"
							stroke-dasharray="3 2"
						/>
					{/if}
					<!-- Dots -->
					{#each fd.pts as p, _i (_i)}
						<circle
							cx={p.cx.toFixed(1)}
							cy={p.cy.toFixed(1)}
							r={Math.min(6, Math.max(3, p.runs * 0.3))}
							fill={p.color}
							fill-opacity="0.7"
							stroke={p.color}
							stroke-width="0.5"
						>
							<title>{p.name} · Sharpe {p.y.toFixed(2)} · MaxDD {p.x.toFixed(1)}%</title>
						</circle>
					{/each}
				</svg>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Dashed amber line = Pareto frontier (not dominated by any other strategy) · dot size ∝ run
				count
			</p>
		</section>
	{/if}

	<!-- Controls bar -->
	<div class="mb-6 flex flex-col gap-3 rounded-xl border bg-card px-4 py-3">
		<div class="flex flex-wrap items-center gap-x-4 gap-y-2">
			<!-- Status filter chips -->
			<div class="flex flex-wrap gap-1.5">
				{#each STATUS_CHIPS as chip, _i (_i)}
					<button
						type="button"
						onclick={() => (statusFilter = chip)}
						class="rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors
							{statusFilter === chip
							? 'bg-primary text-primary-foreground'
							: 'border border-border bg-secondary text-muted-foreground hover:text-foreground'}"
					>
						{chip === 'all' ? 'All status' : chip}
					</button>
				{/each}
			</div>
			<div class="hidden h-4 w-px bg-border sm:block"></div>
			<!-- Mode filter chips -->
			<div class="flex flex-wrap gap-1.5">
				{#each MODE_CHIPS as chip, _i (_i)}
					{@const modeColor =
						chip === 'spot'
							? modeFilter === chip
								? 'bg-green-600 text-white'
								: 'border-green-800/50 text-green-400 hover:bg-green-950/40'
							: chip === 'futures'
								? modeFilter === chip
									? 'bg-red-600 text-white'
									: 'border-red-800/50 text-red-400 hover:bg-red-950/40'
								: chip === 'hybrid'
									? modeFilter === chip
										? 'bg-violet-600 text-white'
										: 'border-violet-800/50 text-violet-400 hover:bg-violet-950/40'
									: modeFilter === chip
										? 'bg-primary text-primary-foreground'
										: 'border border-border bg-secondary text-muted-foreground hover:text-foreground'}
					<button
						type="button"
						onclick={() => (modeFilter = chip)}
						class="rounded-full border px-3 py-1 text-xs font-medium capitalize transition-colors {modeColor}"
					>
						{chip === 'all' ? 'All modes' : chip}
					</button>
				{/each}
			</div>
		</div>
		<div class="flex items-center gap-3 sm:justify-end">
			<!-- Sort + Search -->
			<select
				bind:value={sortKey}
				class="rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus:ring-1 focus:ring-primary focus:outline-none"
			>
				<option value="profit">Best Profit ↓</option>
				<option value="calmar">Best Calmar ↓</option>
				<option value="sharpe">Best Sharpe ↓</option>
				<option value="runs">Most Runs</option>
				<option value="name">Name A→Z</option>
				<option value="updated">Last Updated</option>
			</select>
			<input
				bind:value={nameSearch}
				type="search"
				placeholder="Search name…"
				class="w-40 rounded-md border border-border bg-background px-3 py-1 font-mono text-xs text-foreground placeholder:text-muted-foreground focus:ring-1 focus:ring-primary focus:outline-none"
			/>
			<!-- View mode toggle -->
			<div class="ml-1 flex overflow-hidden rounded-md border border-border">
				<button
					type="button"
					onclick={() => (viewMode = 'card')}
					class="px-2.5 py-1 text-xs transition-colors {viewMode === 'card'
						? 'bg-primary text-primary-foreground'
						: 'bg-background text-muted-foreground hover:text-foreground'}"
					title="Card view">⊞</button
				>
				<button
					type="button"
					onclick={() => (viewMode = 'table')}
					class="border-l border-border px-2.5 py-1 text-xs transition-colors {viewMode === 'table'
						? 'bg-primary text-primary-foreground'
						: 'bg-background text-muted-foreground hover:text-foreground'}"
					title="Table view">≡</button
				>
			</div>
		</div>
	</div>

	<!-- Results count -->
	<p class="mb-4 text-xs text-muted-foreground">
		{filtered.length} / {data.strategies.length} strategies
	</p>

	{#if viewMode === 'table'}
		<!-- Compact table view -->
		<div class="overflow-x-auto rounded-xl border bg-card">
			<table class="w-full text-xs">
				<thead>
					<tr class="border-b border-border">
						<th class="px-3 py-2 text-left font-semibold text-muted-foreground">Strategy</th>
						<th class="px-3 py-2 text-left font-semibold text-muted-foreground">Mode</th>
						<th class="px-3 py-2 text-left font-semibold text-muted-foreground">Status</th>
						<th class="px-3 py-2 text-right font-semibold text-muted-foreground">Runs</th>
						<th class="px-3 py-2 text-right font-semibold text-muted-foreground">TF</th>
						<th class="px-3 py-2 text-right font-semibold text-muted-foreground">Best Profit%</th>
						<th class="px-3 py-2 text-right font-semibold text-muted-foreground">Sharpe</th>
						<th class="px-3 py-2 text-right font-semibold text-muted-foreground">Calmar</th>
						<th class="px-3 py-2 text-right font-semibold text-muted-foreground">MaxDD%</th>
					</tr>
				</thead>
				<tbody>
					{#each filtered as s (s.name)}
						<tr class="border-b border-border/50 transition-colors hover:bg-muted/30">
							<td class="px-3 py-2">
								<a
									href={`/strategies/${s.name}`}
									class="font-medium text-foreground hover:text-primary hover:underline">{s.name}</a
								>
								<StrategyInfo
									strategy={s.name}
									{lang}
									kelly={kellyByName.get(s.name) ?? null}
									size="xs"
								/>
							</td>
							<td class="px-3 py-2 text-muted-foreground">{modeIcon[s.mode] ?? '⚫'} {s.mode}</td>
							<td class="px-3 py-2">
								<span
									class="rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase {statusTone[
										s.status
									] ?? 'border-border bg-muted text-muted-foreground'}">{s.status}</span
								>
							</td>
							<td class="px-3 py-2 text-right font-mono text-foreground">{s.runs}</td>
							<td class="px-3 py-2 text-right font-mono text-muted-foreground">{s.timeframe}</td>
							<td
								class="px-3 py-2 text-right font-mono"
								class:text-green-500={(s.best_profit_pct ?? 0) > 0}
								class:text-red-500={(s.best_profit_pct ?? 0) < 0}>{fmtPct(s.best_profit_pct)}</td
							>
							<td class="px-3 py-2 text-right font-mono text-foreground"
								>{s.best_sharpe == null ? '—' : s.best_sharpe.toFixed(2)}</td
							>
							<td class="px-3 py-2 text-right font-mono text-foreground"
								>{s.best_calmar == null ? '—' : s.best_calmar.toFixed(2)}</td
							>
							<td
								class="px-3 py-2 text-right font-mono"
								class:text-red-500={(s.worst_dd_pct ?? 0) > 20}
								>{s.worst_dd_pct == null ? '—' : s.worst_dd_pct.toFixed(1) + '%'}</td
							>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else}
		<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
			{#each filtered as s (s.name)}
				<a
					href={`/strategies/${s.name}`}
					class="group flex flex-col rounded-xl border bg-card p-5 transition-colors hover:border-primary"
				>
					<div class="flex items-start justify-between gap-2">
						<div class="min-w-0">
							<div class="flex items-center gap-2">
								<span class="text-base">{modeIcon[s.mode] ?? '⚫'}</span>
								<h2 class="truncate font-semibold text-foreground">{s.name}</h2>
								<!-- StrategyInfo deliberately not rendered here: the card itself
								 is already an <a>, and a <button> nested in <a> is invalid
								 HTML. Tooltip is still reachable from the podium card above,
								 the table view, and the detail page header. -->
							</div>
							<p class="mt-1 text-xs text-muted-foreground">{s.tagline}</p>
						</div>
						<span
							class="shrink-0 rounded border px-2 py-0.5 font-mono text-[10px] uppercase {statusTone[
								s.status
							] ?? 'border-border bg-muted text-muted-foreground'}"
						>
							{t(lang, `strategies.status.${s.status}`)}
						</span>
					</div>

					<div class="mt-3">
						<FactorBadges factors={s.factors} size="xs" />
					</div>

					<dl class="mt-4 grid grid-cols-3 gap-2 text-xs">
						<div>
							<dt class="text-muted-foreground">{t(lang, 'strategies.card.runs')}</dt>
							<dd class="font-mono text-foreground">{s.runs}</dd>
						</div>
						<div>
							<dt class="text-muted-foreground">{t(lang, 'strategies.card.tf')}</dt>
							<dd class="font-mono text-foreground">{s.timeframe}</dd>
						</div>
						<div>
							<dt class="text-muted-foreground">{t(lang, 'strategies.card.bestProfit')}</dt>
							<dd
								class="font-mono"
								class:text-green-500={(s.best_profit_pct ?? 0) > 0}
								class:text-red-500={(s.best_profit_pct ?? 0) < 0}
							>
								{fmtPct(s.best_profit_pct)}
							</dd>
						</div>
						<div>
							<dt class="text-muted-foreground">{t(lang, 'strategies.card.bestCalmar')}</dt>
							<dd class="font-mono text-foreground">
								{s.best_calmar == null ? '—' : s.best_calmar.toFixed(2)}
							</dd>
						</div>
						<div>
							<dt class="text-muted-foreground">{t(lang, 'strategies.card.bestSharpe')}</dt>
							<dd class="font-mono text-foreground">
								{s.best_sharpe == null ? '—' : s.best_sharpe.toFixed(2)}
							</dd>
						</div>
						<div>
							<dt class="text-muted-foreground">{t(lang, 'strategies.card.worstDd')}</dt>
							<dd class="font-mono" class:text-red-500={(s.worst_dd_pct ?? 0) > 20}>
								{s.worst_dd_pct == null ? '—' : s.worst_dd_pct.toFixed(1) + '%'}
							</dd>
						</div>
					</dl>

					<div class="mt-4 border-t border-border pt-3 text-[11px] text-muted-foreground">
						{(s.assets ?? []).slice(0, 4).join(' · ')}
					</div>

					<span
						class="mt-4 text-xs text-primary opacity-0 transition-opacity group-hover:opacity-100"
					>
						{t(lang, 'common.detail')}
					</span>
				</a>
			{/each}
		</div>
	{/if}

	{#if statusModeBreakdown}
		{@const smb = statusModeBreakdown}
		<section class="mt-8 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Strategy Portfolio Matrix <span class="ml-1 text-xs font-normal text-muted-foreground"
					>(status × trading mode · {smb.total} strategies)</span
				>
				<ChartInfo metric="portfolio" {lang} />
			</h2>
			<div class="overflow-x-auto">
				<table class="w-full text-xs">
					<thead>
						<tr>
							<th class="pr-4 pb-2 text-left text-[10px] text-muted-foreground uppercase">Status</th
							>
							{#each smb.modes as mode, _i (_i)}
								<th class="px-3 pb-2 text-center text-[10px] text-muted-foreground uppercase"
									>{mode}</th
								>
							{/each}
							<th class="px-3 pb-2 text-center text-[10px] text-muted-foreground uppercase"
								>Total</th
							>
						</tr>
					</thead>
					<tbody>
						{#each smb.rows as row, _i (_i)}
							<tr class="border-t border-border/30">
								<td class="py-1.5 pr-4 font-mono text-[11px] text-muted-foreground capitalize"
									>{row.status}</td
								>
								{#each row.cells as cell, _i (_i)}
									<td class="px-3 py-1.5 text-center">
										{#if cell.count > 0}
											<span
												class="inline-flex items-center justify-center rounded px-2 py-0.5 font-mono text-[11px]"
												style="background:{cell.mode === 'spot'
													? 'var(--ch-profit-light)'
													: cell.mode === 'futures'
														? 'var(--ch-loss-light)'
														: 'rgba(167,139,250,0.15)'}; color:{cell.mode === 'spot'
													? '#4ade80'
													: cell.mode === 'futures'
														? '#f87171'
														: '#c4b5fd'}">{cell.count}</span
											>
										{:else}
											<span class="text-muted-foreground/30">—</span>
										{/if}
									</td>
								{/each}
								<td class="px-3 py-1.5 text-center font-mono text-[11px] text-foreground"
									>{row.rowTotal}</td
								>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Green = spot · red = futures · purple = hybrid
			</p>
		</section>
	{/if}

	{#if profitByStatus}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Best Profit by Status
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(best &amp; avg across strategies per lifecycle stage)</span
				>
				<ChartInfo metric="portfolio" {lang} />
			</h2>
			<div class="space-y-2">
				{#each profitByStatus as r, _i (_i)}
					<div class="flex items-center gap-3">
						<span class="w-20 shrink-0 text-xs font-medium capitalize"
							>{r.status}
							<span class="ml-1 text-[10px] font-normal text-muted-foreground">({r.count})</span>
						</span>
						<div class="flex-1 space-y-1">
							<div class="relative h-3 w-full overflow-hidden rounded-sm bg-muted/20">
								<div
									class="absolute inset-y-0 left-0 rounded-sm"
									style="width:{r.bestBarPct.toFixed(1)}%; background:{r.best >= 0
										? 'var(--ch-profit-light)'
										: 'var(--ch-loss-light)'}"
								></div>
								<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[9px]"
									>best {r.best >= 0 ? '+' : ''}{r.best.toFixed(1)}%</span
								>
							</div>
							<div class="relative h-3 w-full overflow-hidden rounded-sm bg-muted/20">
								<div
									class="absolute inset-y-0 left-0 rounded-sm"
									style="width:{r.avgBarPct.toFixed(1)}%; background:{r.avg >= 0
										? 'var(--ch-profit-light)'
										: 'var(--ch-loss-light)'}"
								></div>
								<span
									class="absolute inset-y-0 left-2 flex items-center font-mono text-[9px] text-muted-foreground"
									>avg {r.avg >= 0 ? '+' : ''}{r.avg.toFixed(1)}%</span
								>
							</div>
						</div>
						<span class="w-16 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
							worst {r.worst >= 0 ? '+' : ''}{r.worst.toFixed(1)}%
						</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Best profit = highest single backtest run per strategy · avg = mean across strategies in
				that stage
			</p>
		</section>
	{/if}

	{#if runDepthDistribution}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Strategy Research Depth
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(strategies grouped by total run count)</span
				>
				<ChartInfo metric="portfolio" {lang} />
			</h2>
			<div class="flex h-24 items-end gap-4">
				{#each runDepthDistribution as r, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-1">
						<span class="font-mono text-[9px] text-muted-foreground">{r.count}</span>
						<div
							class="w-full rounded-t-sm bg-indigo-500/50 transition-all"
							style="height:{Math.max(3, r.barPct * 0.72)}px"
						></div>
						<span class="text-center font-mono text-[10px] leading-tight font-semibold"
							>{r.label}</span
						>
						{#if r.avgBestProfit != null}
							<span
								class="text-center font-mono text-[9px] leading-tight"
								class:text-green-400={r.avgBestProfit >= 0}
								class:text-red-400={r.avgBestProfit < 0}
							>
								{r.avgBestProfit >= 0 ? '+' : ''}{r.avgBestProfit.toFixed(0)}%
							</span>
						{/if}
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Runs = backtest count per strategy · % below = avg best profit in that bucket · taller bar =
				more strategies at that depth
			</p>
		</section>
	{/if}

	{#if sharpeVsDrawdown}
		{@const svd = sharpeVsDrawdown}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Sharpe vs Drawdown Map
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>({svd.dots.length} strategies · right = higher Sharpe · up = lower drawdown)</span
				>
				<ChartInfo metric="maxDrawdown" {lang} />
			</h2>
			<svg viewBox="0 0 {svd.W} {svd.H}" class="w-full" style="height:140px">
				<!-- zero-sharpe line -->
				{#if svd.zeroX >= svd.PAD && svd.zeroX <= svd.W - svd.PAD}
					<line
						x1={svd.zeroX}
						y1={svd.PAD}
						x2={svd.zeroX}
						y2={svd.H - svd.PAD}
						stroke="var(--ch-axis-muted)"
						stroke-width="1"
						stroke-dasharray="3,3"
					/>
				{/if}
				{#each svd.dots as d, _i (_i)}
					<circle cx={d.x} cy={d.y} r="5" fill={d.color} opacity="0.85">
						<title>{d.name} · Sharpe {d.sharpe.toFixed(2)} · DD {(d.dd * 100).toFixed(1)}%</title>
					</circle>
				{/each}
			</svg>
			<div class="mt-2 flex flex-wrap gap-3 text-[10px] text-muted-foreground">
				<span class="flex items-center gap-1"
					><span class="inline-block h-2 w-2 rounded-full bg-green-500/80"></span>live</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-2 w-2 rounded-full bg-indigo-500/80"></span>dryrun</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-2 w-2 rounded-full bg-yellow-500/70"></span>research</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-2 w-2 rounded-full bg-gray-500/50"></span>retired</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Best-run Sharpe vs max drawdown · top-right = ideal · hover for details
			</p>
		</section>
	{/if}

	{#if strategyAgeVsRuns}
		{@const avr = strategyAgeVsRuns}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Strategy Age vs Run Depth
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>({avr.dots.length} strategies · left = recently active · up = heavily tested)</span
				>
				<ChartInfo metric="scatter" {lang} />
			</h2>
			<svg viewBox="0 0 {avr.W} {avr.H}" class="w-full" style="height:130px">
				{#each avr.dots as d, _i (_i)}
					<circle cx={d.x.toFixed(1)} cy={d.y.toFixed(1)} r="5" fill={d.color} opacity="0.85">
						<title>{d.name} · {d.days}d since last import · {d.runs} runs · {d.status}</title>
					</circle>
				{/each}
				<text x={avr.PAD} y={avr.H - 4} font-size="7" fill="var(--ch-rule)">recent</text>
				<text
					x={avr.W - avr.PAD}
					y={avr.H - 4}
					font-size="7"
					fill="var(--ch-rule)"
					text-anchor="end">{avr.xMax}d ago</text
				>
				<text x={avr.PAD - 2} y={avr.PAD + 2} font-size="7" fill="var(--ch-rule)" text-anchor="end"
					>{avr.yMax}r</text
				>
			</svg>
			<div class="mt-2 flex flex-wrap gap-3 text-[10px] text-muted-foreground">
				<span class="flex items-center gap-1"
					><span class="inline-block h-2 w-2 rounded-full bg-green-500/80"></span>live</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-2 w-2 rounded-full bg-indigo-500/80"></span>dryrun</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-2 w-2 rounded-full bg-yellow-500/70"></span>research</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-2 w-2 rounded-full bg-gray-500/50"></span>retired</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				x = days since last import · y = total run count · top-left = active &amp; well-tested
			</p>
		</section>
	{/if}

	{#if factorUsageBar}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Factor Usage Across Strategies
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(how many strategies use each factor)</span
				>
				<ChartInfo metric="portfolio" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each factorUsageBar as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
							>{i + 1}</span
						>
						<span class="w-36 shrink-0 truncate font-mono text-[10px]" title={r.factor}
							>{r.factor}</span
						>
						<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm bg-teal-500/50"
								style="width:{r.barPct.toFixed(1)}%"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]">
								{r.count}
								{r.count === 1 ? 'strategy' : 'strategies'}
							</span>
						</div>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Bar width = number of strategies using this factor · most popular factors ranked first
			</p>
		</section>
	{/if}

	{#if bestWinRateRanking}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Best Win Rate Ranking
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(best win rate achieved across all runs)</span
				>
				<ChartInfo metric="winRate" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each bestWinRateRanking as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
							>{i + 1}</span
						>
						<a
							href="/strategies/{r.name}"
							class="w-40 shrink-0 truncate font-mono text-[10px] transition-colors hover:text-primary"
							title={r.name}>{r.name}</a
						>
						<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm transition-all"
								style="width:{r.wr.toFixed(1)}%; background:{r.wr >= 65
									? 'var(--ch-profit)'
									: r.wr >= 50
										? 'var(--ch-warn-light)'
										: 'var(--ch-loss-light)'}"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]"
								>{r.wr.toFixed(1)}%</span
							>
						</div>
						<span class="w-16 shrink-0 text-right font-mono text-[9px] text-muted-foreground"
							>{r.runs} run{r.runs !== 1 ? 's' : ''}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Bar = best win rate % achieved · green ≥65% · yellow 50–65% · click name to view strategy
				detail
			</p>
		</section>
	{/if}

	{#if sortinoLeaderboard}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Best Sortino Ranking
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(best Sortino ratio achieved · return per unit of downside deviation)</span
				>
				<ChartInfo metric="sortino" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each sortinoLeaderboard as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
							>{i + 1}</span
						>
						<a
							href="/strategies/{r.name}"
							class="w-40 shrink-0 truncate font-mono text-[10px] transition-colors hover:text-primary"
							title={r.name}>{r.name}</a
						>
						<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<div
								class="absolute inset-y-0 left-0 rounded-sm transition-all"
								style="width:{r.barPct.toFixed(1)}%; background:{r.sortino >= 3
									? 'var(--ch-profit)'
									: r.sortino >= 1
										? 'var(--ch-warn-light)'
										: 'var(--ch-violet-light)'}"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]"
								>{r.sortino.toFixed(2)}</span
							>
						</div>
						<span class="w-16 shrink-0 text-right font-mono text-[9px] text-muted-foreground"
							>{r.runs} run{r.runs !== 1 ? 's' : ''}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Sortino penalizes only downside volatility · green ≥3 · yellow 1–3 · click name to view
				detail
			</p>
		</section>
	{/if}

	{#if calmarLeaderboard}
		<section class="mt-6 rounded-lg border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Calmar Ratio Leaderboard
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(best Calmar = annual return ÷ max drawdown · higher = better risk-adjusted return)</span
				>
				<ChartInfo metric="calmar" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each calmarLeaderboard as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
							>{i + 1}</span
						>
						<a
							href="/strategies/{r.name}"
							class="w-36 shrink-0 truncate text-xs text-foreground hover:text-primary hover:underline"
							>{r.name}</a
						>
						<div class="relative h-5 flex-1 overflow-hidden rounded bg-muted">
							<div
								class="absolute inset-y-0 left-0 rounded"
								style="width:{r.barPct.toFixed(1)}%; background:{r.calmar >= 2
									? 'var(--ch-profit-light)'
									: r.calmar >= 1
										? 'var(--ch-warn-light)'
										: 'var(--ch-violet-light)'}"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]"
								>{r.calmar.toFixed(2)}</span
							>
						</div>
						<span class="w-14 shrink-0 text-right font-mono text-[9px] text-muted-foreground"
							>{r.runs} run{r.runs !== 1 ? 's' : ''}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Calmar ≥2 green · ≥1 yellow · complementary to Sortino · click name to view detail
			</p>
		</section>
	{/if}

	{#if leastDrawdownRanking}
		<section class="mt-6 rounded-lg border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Lowest Max Drawdown Ranking
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(strategies with best drawdown control · shorter bar = less loss from peak)</span
				>
				<ChartInfo metric="maxDrawdown" {lang} />
			</h2>
			<div class="space-y-1.5">
				{#each leastDrawdownRanking as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground"
							>{i + 1}</span
						>
						<a
							href="/strategies/{r.name}"
							class="w-36 shrink-0 truncate text-xs text-foreground hover:text-primary hover:underline"
							>{r.name}</a
						>
						<div class="relative h-5 flex-1 overflow-hidden rounded bg-muted">
							<div
								class="absolute inset-y-0 left-0 rounded"
								style="width:{r.barPct.toFixed(1)}%; background:{r.dd < 10
									? 'var(--ch-profit-light)'
									: r.dd < 20
										? 'var(--ch-warn-light)'
										: 'var(--ch-loss-light)'}"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]"
								>{r.dd.toFixed(1)}%</span
							>
						</div>
						<span class="w-14 shrink-0 text-right font-mono text-[9px] text-muted-foreground"
							>{r.runs} run{r.runs !== 1 ? 's' : ''}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Green &lt;10% · yellow 10–20% · red &gt;20% · lower drawdown = capital better preserved ·
				click to view detail
			</p>
		</section>
	{/if}
	{#if runsPerStrategyHistogram}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Strategies by Run Count
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(how many strategies have been tested N times)</span
				>
				<ChartInfo metric="portfolio" {lang} />
			</h2>
			<div class="mt-3 flex items-end gap-2" style="height:72px">
				{#each runsPerStrategyHistogram as b, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-0.5">
						<span class="font-mono text-[8px] text-muted-foreground"
							>{b.count > 0 ? b.count : ''}</span
						>
						<div
							class="w-full rounded-t"
							style="height:{Math.max(2, b.barPct * 0.6)}px; background:var(--ch-violet-light)"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-around font-mono text-[9px] text-muted-foreground">
				{#each runsPerStrategyHistogram as b, _i (_i)}
					<span class="flex-1 text-center">{b.label}</span>
				{/each}
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Bar height = number of strategies with that many runs — strategies with many runs are
				well-explored
			</p>
		</section>
	{/if}
	{#if strategyWinRateVsDrawdown}
		{@const swd = strategyWinRateVsDrawdown}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Win Rate vs Drawdown
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(ideal = top-left: high win rate, low drawdown · dot size = run count)</span
				>
				<ChartInfo metric="winRate" {lang} />
			</h2>
			<svg viewBox="0 0 {swd.W} {swd.H}" class="w-full" style="height:110px">
				{#each swd.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r={d.r} fill={d.color} opacity="0.8"
						><title>{d.title}</title></circle
					>
				{/each}
			</svg>
			<div class="flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>WR {swd.xMin.toFixed(0)}%</span><span>→ best win rate →</span><span
					>{swd.xMax.toFixed(0)}%</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Y-axis = worst drawdown% · green &lt;10% dd · yellow 10–25% · red &gt;25% · larger dot =
				more runs tested
			</p>
		</section>
	{/if}
	{#if strategyModeComparison}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Avg Sortino by Trading Mode
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(how strategies perform across live, dry-run, and backtest modes)</span
				>
				<ChartInfo metric="sortino" {lang} />
			</h2>
			<div class="mt-3 space-y-2">
				{#each strategyModeComparison as r, _i (_i)}
					<div class="flex items-center gap-3">
						<span class="w-20 shrink-0 font-mono text-[10px] text-muted-foreground">{r.mode}</span>
						<div class="relative h-5 flex-1 overflow-hidden rounded bg-muted">
							<div
								class="absolute inset-y-0 left-0 rounded"
								style="width:{r.barPct.toFixed(1)}%; background:{r.avgSortino >= 2
									? 'var(--ch-profit)'
									: r.avgSortino >= 0
										? 'var(--ch-violet-light)'
										: 'var(--ch-loss-light)'}"
							></div>
							<span class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px]"
								>{r.avgSortino.toFixed(2)}</span
							>
						</div>
						<span class="w-20 shrink-0 text-right font-mono text-[9px] text-muted-foreground"
							>{r.count} strats · dd {r.avgDd?.toFixed(1) ?? '—'}%</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Avg best Sortino per strategy in each mode · reveals if live strategies outperform
				backtest-only ones
			</p>
		</section>
	{/if}
	{#if runDepthVsCalmar}
		{@const rdc = runDepthVsCalmar}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Run Depth vs Best Calmar
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(does more backtesting → higher Calmar? · r = {rdc.corr >= 0
						? '+'
						: ''}{rdc.corr.toFixed(2)})</span
				>
				<ChartInfo metric="calmar" {lang} />
			</h2>
			<svg viewBox="0 0 {rdc.W} {rdc.H}" class="mt-3 w-full" style="height:130px">
				{#if rdc.zeroY != null}
					<line
						x1={rdc.PL}
						x2={rdc.W - rdc.PR}
						y1={rdc.zeroY}
						y2={rdc.zeroY}
						stroke="var(--ch-rule)"
						stroke-width="1"
						stroke-dasharray="3 3"
					/>
				{/if}
				{#each rdc.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="4" style="fill:{d.color}" opacity="0.75"
						><title>{d.name} · {d.runs} runs · Calmar {d.calmar.toFixed(2)}</title></circle
					>
				{/each}
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>← {rdc.xMin} runs</span><span>→ run depth →</span><span>{rdc.xMax} runs →</span>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Each dot = one strategy · x = number of backtest runs · y = best Calmar ratio · {rdc.corr >
				0.2
					? 'positive correlation — more testing → better risk-adjusted return'
					: rdc.corr < -0.2
						? 'negative correlation — more runs not improving Calmar'
						: 'weak correlation — run depth does not predict Calmar'}
			</p>
		</section>
	{/if}
	{#if strategyFactorCountDist}
		{@const sfc = strategyFactorCountDist}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Factor Count Distribution
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(how many signal factors each strategy uses · {sfc.total} strategies total)</span
				>
				<ChartInfo metric="distribution" {lang} />
			</h2>
			<div class="mt-3 flex items-end gap-2" style="height:72px">
				{#each sfc.buckets as b, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-1">
						<span class="font-mono text-[9px] text-muted-foreground"
							>{b.count > 0 ? b.count : ''}</span
						>
						<div
							class="w-full rounded-t"
							style="height:{Math.max(2, b.barPct * 0.6)}px; background:var(--ch-violet-light)"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-around font-mono text-[9px] text-muted-foreground">
				{#each sfc.buckets as b, _i (_i)}
					<span class="flex-1 text-center">{b.label} factor{b.label === '1' ? '' : 's'}</span>
				{/each}
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Distribution of signal factor usage · most strategies use a single dominant factor or
				combine 2–3 complementary ones
			</p>
		</section>
	{/if}

	{#if strategyBestSortinoRanking}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Best Sortino Ranking <ChartInfo metric="sortino" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Top 10 strategies by peak Sortino ratio across all runs
			</p>
			<div class="mt-3 space-y-1.5">
				{#each strategyBestSortinoRanking as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right font-mono text-[10px] text-muted-foreground">{i + 1}</span>
						<span class="w-36 truncate font-mono text-[10px] text-muted-foreground">{r.name}</span>
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
							>{r.sortino.toFixed(2)}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Sortino weights only downside volatility · higher = smoother profit path relative to
				drawdown risk
			</p>
		</section>
	{/if}

	{#if strategyLowestDrawdown}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Lowest Drawdown Strategies <ChartInfo metric="maxDrawdown" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Top 10 strategies with the smallest worst max drawdown% (min 3 runs) — risk-first ranking
			</p>
			<div class="mt-3 space-y-1.5">
				{#each strategyLowestDrawdown as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right font-mono text-[10px] text-muted-foreground">{i + 1}</span>
						<span class="w-36 truncate font-mono text-[10px] text-muted-foreground">{r.name}</span>
						<div
							class="flex-1 overflow-hidden rounded-sm"
							style="height:14px; background:var(--ch-rule-faint)"
						>
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:var(--ch-loss-light)"
							></div>
						</div>
						<span class="w-14 text-right font-mono text-[10px]" style="color:var(--ch-profit-solid)"
							>{r.dd.toFixed(1)}% DD</span
						>
						<span class="w-10 text-right font-mono text-[9px] text-muted-foreground"
							>n={r.runs}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Shorter red bar = lower historical drawdown · prioritise these when capital preservation
				matters most
			</p>
		</section>
	{/if}

	{#if strategyAvgProfitRanking}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Top Strategies by Best Profit% <ChartInfo metric="leaderboard" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Top 10 strategies by their best recorded total profit% (min 2 runs) — identifies peak
				performers
			</p>
			<div class="mt-3 space-y-1.5">
				{#each strategyAvgProfitRanking as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right font-mono text-[10px] text-muted-foreground">{i + 1}</span>
						<span class="w-36 truncate font-mono text-[10px] text-muted-foreground">{r.name}</span>
						<div
							class="flex-1 overflow-hidden rounded-sm"
							style="height:14px; background:var(--ch-rule-faint)"
						>
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:{r.avg >= 0
									? 'var(--ch-profit)'
									: 'var(--ch-loss-light)'}"
							></div>
						</div>
						<span
							class="w-16 text-right font-mono text-[10px]"
							style="color:{r.avg >= 0 ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
							>{r.avg >= 0 ? '+' : ''}{r.avg.toFixed(1)}%</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground">n={r.runs}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Best profit% = highest single run total return · use alongside drawdown and Calmar to judge
				if peak return was luck or consistent skill
			</p>
		</section>
	{/if}

	{#if strategyRunsVsProfit}
		{@const srvp = strategyRunsVsProfit}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Run Count vs Best Profit Scatter <ChartInfo metric="scatter" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Each dot = one strategy · X = number of backtest runs · Y = best profit% achieved — does
				more research yield better results?
			</p>
			<svg viewBox="0 0 {srvp.W} {srvp.H}" class="mt-2 w-full" style="height:80px">
				<line
					x1={srvp.PAD}
					y1={srvp.H -
						srvp.PAD -
						((0 - srvp.yMin) / (srvp.yMax - srvp.yMin)) * (srvp.H - srvp.PAD * 2)}
					x2={srvp.W - srvp.PAD}
					y2={srvp.H -
						srvp.PAD -
						((0 - srvp.yMin) / (srvp.yMax - srvp.yMin)) * (srvp.H - srvp.PAD * 2)}
					stroke="var(--ch-rule)"
					stroke-width="0.5"
				/>
				{#each srvp.dots as d, _i (_i)}
					<circle
						cx={d.cx}
						cy={d.cy}
						r="2.5"
						fill={d.pos ? 'var(--ch-profit)' : 'var(--ch-loss-light)'}
					/>
				{/each}
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{srvp.xMin} runs</span><span>→ run count →</span><span>{srvp.xMax} runs</span>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Upward trend = more backtesting discovers higher-profit configs · scattered = profit is
				strategy-dependent not effort-dependent
			</p>
		</section>
	{/if}

	{#if strategyBestCalmarRanking}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Top Strategies by Best Calmar Ratio <ChartInfo metric="calmar" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Top 10 strategies by their best Calmar ratio (annualised return ÷ max drawdown, min 2 runs)
			</p>
			<div class="mt-3 space-y-1.5">
				{#each strategyBestCalmarRanking as r, i (i)}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right font-mono text-[10px] text-muted-foreground">{i + 1}</span>
						<span class="w-36 truncate font-mono text-[10px] text-muted-foreground">{r.name}</span>
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
							style="color:var(--ch-violet-strong)">{r.calmar.toFixed(2)}</span
						>
						<span class="w-8 text-right font-mono text-[9px] text-muted-foreground">n={r.runs}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Calmar &gt;1 = annual return exceeds max drawdown · strategies at top sustain strong returns
				without deep equity dips
			</p>
		</section>
	{/if}

	{#if strategyProfitDistribution}
		{@const spd = strategyProfitDistribution}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Strategy Best Profit Distribution <ChartInfo metric="distribution" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Histogram of best profit% across {spd.total} strategies · median {spd.median.toFixed(1)}% —
				overall portfolio quality shape
			</p>
			<div class="mt-3 flex items-end gap-1" style="height:72px">
				{#each spd.buckets as b, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-0.5">
						<span class="font-mono text-[8px] text-muted-foreground"
							>{b.count > 0 ? b.count : ''}</span
						>
						<div
							class="w-full rounded-sm"
							style="height:{b.barPct}%; background:{b.lo >= 0
								? 'var(--ch-profit)'
								: 'var(--ch-loss-light)'}; min-height:{b.count > 0 ? 2 : 0}px"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{spd.mn.toFixed(0)}%</span><span>→ best profit% →</span><span
					>{spd.mx.toFixed(0)}%</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Right-skewed = most strategies have strong best-run profit · green bars = profitable
				strategies · mass on right = high-quality research pipeline
			</p>
		</section>
	{/if}

	{#if strategyStatusBreakdown}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Strategy Status Breakdown <ChartInfo metric="portfolio" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Count of strategies by deployment status — portfolio composition at a glance
			</p>
			<div class="mt-3 space-y-1.5">
				{#each strategyStatusBreakdown as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-20 font-mono text-[10px] text-muted-foreground capitalize"
							>{r.status}</span
						>
						<div
							class="flex-1 overflow-hidden rounded-sm"
							style="height:14px; background:var(--ch-rule-faint)"
						>
							<div class="h-full rounded-sm" style="width:{r.barPct}%; background:{r.color}"></div>
						</div>
						<span class="w-8 text-right font-mono text-[10px] text-muted-foreground">{r.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Green = live · indigo = paper · yellow = backtest-only · grey = archived · shows how much
				research has been promoted to production
			</p>
		</section>
	{/if}

	{#if strategyTimeframeBreakdown}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Strategy Timeframe Breakdown <ChartInfo metric="timeframe" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Number of strategies per primary timeframe, with avg best profit
			</p>
			<div class="space-y-1">
				{#each strategyTimeframeBreakdown as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-10 text-right font-mono text-[11px] text-muted-foreground">{r.tf}</span>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:{r.avgProfit >= 0
									? 'var(--ch-violet)'
									: 'var(--ch-loss)'}"
							></div>
						</div>
						<span class="w-8 text-right font-mono text-[10px] text-muted-foreground">{r.count}</span
						>
						<span
							class="w-16 text-right font-mono text-[10px]"
							style="color:{r.avgProfit >= 0 ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
							>{r.avgProfit > 0 ? '+' : ''}{r.avgProfit.toFixed(1)}%</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Longer timeframes = fewer, higher-quality signals · shorter timeframes = more trades but
				higher noise · avg profit shows which TF produces best results
			</p>
		</section>
	{/if}

	{#if strategyWinRateVsRuns}
		{@const swr = strategyWinRateVsRuns}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Win Rate vs Run Count Scatter <ChartInfo metric="winRate" {lang} />
			</h2>
			<p class="mb-2 text-[11px] text-muted-foreground">
				Each dot = one strategy · x = number of backtest runs · y = best win rate% · upper-right =
				well-tested with high win rate
			</p>
			<svg viewBox="0 0 {swr.W} {swr.H}" class="w-full" style="height:90px">
				<line
					x1="8"
					y1={swr.zeroY}
					x2={swr.W - 8}
					y2={swr.zeroY}
					stroke="var(--ch-rule)"
					stroke-width="0.8"
					stroke-dasharray="3,2"
				/>
				{#each swr.dots as d, _i (_i)}
					<circle
						cx={d.cx}
						cy={d.cy}
						r="2.5"
						fill={d.good ? 'var(--ch-profit)' : 'var(--ch-loss-light)'}
					/>
				{/each}
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{swr.xMin} runs</span><span>← run count →</span><span>{swr.xMax} runs</span>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Green = ≥50% WR and ≥5 runs (well-validated) · red = under-tested or low win rate ·
				strategies needing more runs cluster left
			</p>
		</section>
	{/if}

	{#if strategyModeBreakdown}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Strategy Mode Breakdown <ChartInfo metric="portfolio" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Count of strategies per deployment mode with avg best profit
			</p>
			<div class="space-y-2">
				{#each strategyModeBreakdown as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span
							class="w-16 text-right font-mono text-[11px] font-semibold"
							style="color:{r.color.replace('0.7', '1').replace('0.6', '1').replace('0.5', '1')}"
							>{r.mode}</span
						>
						<div class="h-5 flex-1 overflow-hidden rounded-sm bg-muted">
							<div class="h-full rounded-sm" style="width:{r.barPct}%; background:{r.color}"></div>
						</div>
						<span class="w-10 text-right font-mono text-[10px] text-muted-foreground"
							>{r.count}</span
						>
						<span
							class="w-16 text-right font-mono text-[10px]"
							style="color:{r.avgProfit >= 0 ? 'var(--ch-profit-solid)' : 'var(--ch-loss-solid)'}"
							>{r.avgProfit > 0 ? '+' : ''}{r.avgProfit.toFixed(1)}%</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Live = deployed on exchange · paper = simulated with real data · backtest-only = research
				stage · avg profit shows promotion quality filter
			</p>
		</section>
	{/if}

	{#if strategyCalmarVsWinRate}
		{@const scw = strategyCalmarVsWinRate}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Calmar vs Win Rate Scatter <ChartInfo metric="calmar" {lang} />
			</h2>
			<p class="mb-2 text-[11px] text-muted-foreground">
				Best Calmar ratio vs best win rate per strategy · upper-right = strong risk-adjusted return
				+ high accuracy
			</p>
			<svg viewBox="0 0 {scw.W} {scw.H}" class="w-full" style="height:120px">
				{#if scw.x1 >= scw.PAD && scw.x1 <= scw.W - scw.PAD}
					<line
						x1={scw.x1}
						y1={scw.PAD}
						x2={scw.x1}
						y2={scw.H - scw.PAD}
						stroke="var(--ch-axis-faint)"
						stroke-width="0.6"
						stroke-dasharray="3,2"
					/>
				{/if}
				<line
					x1={scw.PAD}
					y1={scw.y05}
					x2={scw.W - scw.PAD}
					y2={scw.y05}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.6"
					stroke-dasharray="3,2"
				/>
				{#each scw.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="3" fill={d.color}
						><title>{d.name}: Calmar {d.calmar.toFixed(2)}, WR {(d.wr * 100).toFixed(0)}%</title
						></circle
					>
				{/each}
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>Calmar {scw.xMin.toFixed(1)}</span><span>← Calmar ratio →</span><span
					>{scw.xMax.toFixed(1)}</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Calmar = annual return / max drawdown · dashed lines at Calmar=0 and WR=50% · upper-right =
				best strategies for live deployment
			</p>
		</section>
	{/if}

	{#if strategyLastImportTimeline}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Research Activity by Month <ChartInfo metric="leaderboard" {lang} />
			</h2>
			<p class="mb-2 text-[11px] text-muted-foreground">
				Count of strategies with last import in each calendar month · shows research cadence and
				active periods
			</p>
			<div class="flex items-end gap-1" style="height:56px">
				{#each strategyLastImportTimeline as r, _i (_i)}
					<div
						class="flex flex-1 flex-col items-center gap-0.5"
						title="{r.ym}: {r.count} strategies"
					>
						<span class="font-mono text-[7px] text-muted-foreground"
							>{r.count > 0 ? r.count : ''}</span
						>
						<div
							class="w-full rounded-sm"
							style="height:{r.barPct}%; background:var(--ch-violet); min-height:{r.count > 0
								? 2
								: 0}px"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{strategyLastImportTimeline[0].ym}</span><span>← month →</span><span
					>{strategyLastImportTimeline[strategyLastImportTimeline.length - 1].ym}</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Tall months = high research activity · gaps = paused development · recent growth = active
				strategy iteration cycle
			</p>
		</section>
	{/if}
	{#if strategyAssetCoverage}
		<section class="rounded-lg border border-border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Strategy Asset Coverage <ChartInfo metric="portfolio" {lang} />
			</h2>
			<div class="space-y-1">
				{#each strategyAssetCoverage as r, _i (_i)}
					{@const modeColor =
						r.mode === 'futures'
							? 'var(--ch-warn)'
							: r.mode === 'hybrid'
								? 'var(--ch-violet-light)'
								: 'var(--ch-violet)'}
					{@const profitColor =
						r.bestProfit > 10
							? 'var(--ch-profit-strong)'
							: r.bestProfit > 0
								? 'var(--ch-profit)'
								: 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-36 truncate text-right font-mono text-[10px] text-muted-foreground"
							>{r.name}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div
								class="h-full rounded-sm"
								style="width:{r.barPct}%; background:{modeColor}"
							></div>
						</div>
						<span class="w-12 text-right font-mono text-[10px]" style="color:{modeColor}"
							>{r.assetCount} pairs</span
						>
						<span class="w-14 text-right font-mono text-[10px]" style="color:{profitColor}"
							>{r.bestProfit > 0 ? '+' : ''}{r.bestProfit.toFixed(1)}%</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Asset count = number of configured trading pairs · wider coverage = more diversified ·
				narrow = concentrated signal · color = mode (gold=futures, purple=hybrid, blue=spot)
			</p>
		</section>
	{/if}
	{#if strategySharpeRanking}
		<section class="rounded-lg border border-border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Strategy Sharpe Ratio Ranking <ChartInfo metric="sharpe" {lang} />
			</h2>
			<div class="space-y-1">
				{#each strategySharpeRanking as r, _i (_i)}
					{@const color = r.positive ? 'var(--ch-violet-strong)' : 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-36 truncate text-right font-mono text-[10px] text-muted-foreground"
							>{r.name}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
							<div class="h-full rounded-sm" style="width:{r.barPct}%; background:{color}"></div>
						</div>
						<span class="w-14 text-right font-mono text-[10px]" style="color:{color}"
							>{r.sharpe.toFixed(2)}</span
						>
						<span class="w-14 text-right font-mono text-[9px] text-muted-foreground"
							>{r.status} · {r.runs}r</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Best Sharpe ratio per strategy · total-volatility adjusted · complements Calmar
				(time/drawdown) and Sortino (downside-only) leaderboards
			</p>
		</section>
	{/if}
	{#if strategyProfitVsSortino}
		<section class="rounded-xl border border-border bg-card p-4">
			<h2 class="mb-1 text-sm font-semibold">
				Best Profit vs Best Sortino (Strategy Scatter) <ChartInfo metric="sortino" {lang} />
			</h2>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Each dot = one strategy · x = best Sortino · y = best profit % · color = mode
			</p>
			<svg viewBox="0 0 {strategyProfitVsSortino.W} {strategyProfitVsSortino.H}" class="w-full">
				<line
					x1="0"
					y1={strategyProfitVsSortino.zeroY}
					x2={strategyProfitVsSortino.W}
					y2={strategyProfitVsSortino.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="1"
					stroke-dasharray="4,3"
				/>
				{#each strategyProfitVsSortino.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="4" fill={d.color}><title>{d.name}</title></circle>
				{/each}
			</svg>
			<div class="mt-2 flex gap-4 text-[9px] text-muted-foreground">
				<span><span style="color:var(--ch-profit-strong)">●</span> live</span>
				<span><span style="color:var(--ch-violet-strong)">●</span> paper</span>
				<span><span style="color:var(--ch-warn)">●</span> backtest</span>
			</div>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Sortino [{strategyProfitVsSortino.xMin}…{strategyProfitVsSortino.xMax}] · Profit [{strategyProfitVsSortino.yMin}%…{strategyProfitVsSortino.yMax}%]
				· upper-right quadrant = high reward + downside-protected
			</p>
		</section>
	{/if}
	{#if strategyDrawdownVsCalmar}
		<section class="rounded-xl border border-border bg-card p-4">
			<h2 class="mb-1 text-sm font-semibold">
				Worst Drawdown vs Best Calmar (Strategy Scatter) <ChartInfo metric="calmar" {lang} />
			</h2>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Each dot = one strategy · x = worst drawdown % · y = best Calmar ratio · color = status ·
				upper-left = ideal (low drawdown, high Calmar)
			</p>
			<svg viewBox="0 0 {strategyDrawdownVsCalmar.W} {strategyDrawdownVsCalmar.H}" class="w-full">
				{#if strategyDrawdownVsCalmar.zeroY !== null}
					<line
						x1="0"
						y1={strategyDrawdownVsCalmar.zeroY}
						x2={strategyDrawdownVsCalmar.W}
						y2={strategyDrawdownVsCalmar.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				{#each strategyDrawdownVsCalmar.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="4" fill={d.color}><title>{d.name}</title></circle>
				{/each}
			</svg>
			<div class="mt-2 flex gap-4 text-[9px] text-muted-foreground">
				<span><span style="color:var(--ch-profit-strong)">●</span> active</span>
				<span><span style="color:var(--ch-warn)">●</span> testing</span>
				<span><span style="color:var(--ch-axis)">●</span> inactive</span>
			</div>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Drawdown [{strategyDrawdownVsCalmar.xMin}%…{strategyDrawdownVsCalmar.xMax}%] · Calmar [{strategyDrawdownVsCalmar.yMin}…{strategyDrawdownVsCalmar.yMax}]
				· dots clustered top-left = optimal risk/reward strategies
			</p>
		</section>
	{/if}

	{#if strategyExpectedValueRanking}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Strategy Expected Value Ranking</h3>
			<p class="mb-3 text-[10px] text-muted-foreground">
				Expected value = best_win_rate × best_profit_pct — combines hit rate and magnitude into one
				number · top 12 strategies ranked descending
			</p>
			<div class="space-y-1.5">
				{#each strategyExpectedValueRanking.rows as row, i (i)}
					<div class="flex items-center gap-2 text-xs">
						<span class="w-4 shrink-0 text-right text-muted-foreground">{i + 1}</span>
						<span class="w-32 shrink-0 truncate font-mono text-[10px]">{row.name}</span>
						<div class="relative h-4 flex-1 overflow-hidden rounded bg-muted/30">
							<div
								class="h-full rounded"
								style="width:{((row.ev / strategyExpectedValueRanking.maxEv) * 100).toFixed(
									1
								)}%; background:{strategyExpectedValueRanking.MODE_COL[row.mode] ??
									'var(--ch-axis)'}"
							></div>
						</div>
						<span class="w-12 text-right font-mono">{row.ev.toFixed(1)}%</span>
						<span class="w-16 text-right text-[9px] text-muted-foreground"
							>{row.wr.toFixed(0)}%wr</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				EV = win_rate × best_total_profit · color = trading mode · higher EV = more reliable
				compounding potential
			</p>
		</section>
	{/if}

	{#if strategyDrawdownByMode}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Avg Drawdown by Trading Mode</h3>
			<p class="mb-3 text-[10px] text-muted-foreground">
				Average worst_dd_pct grouped by trading mode · lower = better capital preservation · sorted
				by least drawdown first
			</p>
			<div class="space-y-2">
				{#each strategyDrawdownByMode.rows as row, _i (_i)}
					{@const color = strategyDrawdownByMode.MODE_COL[row.mode] ?? 'var(--ch-axis)'}
					<div class="flex items-center gap-2 text-xs">
						<span class="w-20 shrink-0 font-mono text-muted-foreground">{row.mode}</span>
						<div class="relative h-4 flex-1 overflow-hidden rounded bg-muted/30">
							<div
								class="h-full rounded"
								style="width:{((row.avg / strategyDrawdownByMode.maxAvg) * 100).toFixed(
									1
								)}%; background:{color}"
							></div>
						</div>
						<span class="w-14 text-right font-mono" style="color:{color}"
							>{row.avg.toFixed(1)}%</span
						>
						<span class="w-24 text-right text-[9px] text-muted-foreground"
							>{row.min.toFixed(0)}–{row.max.toFixed(0)}% · n={row.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Avg drawdown by mode · range shows spread across strategies in each mode · lower avg = mode
				is more capital-efficient on average
			</p>
		</section>
	{/if}

	{#if strategyProfitByAsset}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Avg Best Profit by Primary Asset</h3>
			<p class="mb-3 text-[10px] text-muted-foreground">
				Average best_profit_pct grouped by first asset in each strategy's asset list · reveals which
				underlying assets have historically produced the best returns
			</p>
			<div class="space-y-1.5">
				{#each strategyProfitByAsset.rows as row, _i (_i)}
					{@const color = row.avg > 0 ? 'var(--ch-profit-strong)' : 'var(--ch-loss)'}
					<div class="flex items-center gap-2 text-xs">
						<span class="w-20 shrink-0 font-mono text-muted-foreground">{row.asset}</span>
						<div class="relative h-4 flex-1 overflow-hidden rounded bg-muted/30">
							<div
								class="h-full rounded"
								style="width:{((Math.max(0, row.avg) / strategyProfitByAsset.maxAvg) * 100).toFixed(
									1
								)}%; background:{color}"
							></div>
						</div>
						<span class="w-14 text-right font-mono" style="color:{color}"
							>{row.avg.toFixed(1)}%</span
						>
						<span class="w-20 text-right text-[9px] text-muted-foreground"
							>best {row.best.toFixed(0)}% · n={row.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Top asset = {strategyProfitByAsset.rows[0].asset} (avg {strategyProfitByAsset.rows[0].avg.toFixed(
					1
				)}%) · avg across all strategies targeting that asset · higher = more consistently
				profitable asset class
			</p>
		</section>
	{/if}

	{#if strategyWinRateByTimeframe}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Avg Win Rate by Timeframe</h3>
			<p class="mb-3 text-[10px] text-muted-foreground">
				Average best_win_rate across strategies grouped by timeframe · sorted by timeframe order ·
				reveals which timeframes produce higher accuracy across the strategy universe
			</p>
			<div class="space-y-2">
				{#each strategyWinRateByTimeframe.rows as row, _i (_i)}
					{@const pct = (row.avg / strategyWinRateByTimeframe.maxAvg) * 100}
					<div class="flex items-center gap-2 text-xs">
						<span class="w-10 shrink-0 font-mono text-muted-foreground">{row.tf}</span>
						<div class="relative h-4 flex-1 overflow-hidden rounded bg-muted/30">
							<div
								class="h-full rounded"
								style="width:{pct.toFixed(1)}%; background:rgba(34,197,94,{Math.min(
									0.85,
									0.3 + (pct / 100) * 0.55
								)})"
							></div>
						</div>
						<span class="w-14 text-right font-mono">{row.avg.toFixed(1)}%</span>
						<span class="w-20 text-right text-[9px] text-muted-foreground"
							>best {row.best.toFixed(0)}% · n={row.count}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Avg win rate by timeframe across all strategies · longer TFs tend to have higher win rates
				but fewer trades · compare with profit ranking for full picture
			</p>
		</section>
	{/if}

	{#if strategyRunCountByTimeframe}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Strategy Count by Timeframe</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Number of strategies configured per timeframe · reveals which TFs have the most coverage in
				the portfolio
			</p>
			<div class="space-y-1">
				{#each strategyRunCountByTimeframe.rows as row, _i (_i)}
					{@const color = strategyRunCountByTimeframe.TF_COL[row.tf] ?? 'var(--ch-axis)'}
					{@const pct = ((row.count / strategyRunCountByTimeframe.maxCount) * 100).toFixed(1)}
					<div class="flex items-center gap-2 text-[10px]">
						<span class="w-10 font-mono text-muted-foreground">{row.tf}</span>
						<div class="flex h-3 flex-1 overflow-hidden rounded bg-muted/30">
							<div class="h-full rounded" style="width:{pct}%; background:{color}"></div>
						</div>
						<span class="w-8 text-right font-mono" style="color:{color}">{row.count}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Dominant TF = most actively developed · consider diversifying into underrepresented
				timeframes for regime robustness
			</p>
		</section>
	{/if}

	{#if strategyTopSortinoLeaders}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Top Strategies by Best Sortino</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Best Sortino ratio achieved per strategy across all runs · Sortino penalizes only downside
				volatility — higher = better risk-adjusted return on losing trades
			</p>
			<div class="space-y-1">
				{#each strategyTopSortinoLeaders.rows as row, _i (_i)}
					{@const pct = (
						(Math.max(0, row.sortino) / strategyTopSortinoLeaders.maxAbs) *
						100
					).toFixed(1)}
					{@const color =
						row.sortino >= 2
							? 'var(--ch-profit)'
							: row.sortino >= 0
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					<div class="flex items-center gap-2 text-[10px]">
						<span class="w-36 truncate font-mono text-[9px]">{row.name}</span>
						<div class="flex h-3 flex-1 overflow-hidden rounded bg-muted/30">
							<div class="h-full rounded" style="width:{pct}%; background:{color}"></div>
						</div>
						<span class="w-14 text-right font-mono" style="color:{color}"
							>{row.sortino.toFixed(2)}</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Sortino ≥2 = excellent · 1–2 = good · &lt;0 = net negative risk-adjusted · compare with
				Calmar for drawdown-adjusted view
			</p>
		</section>
	{/if}

	{#if strategyCalmarTierBreakdown}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Calmar Tier Distribution
			</h3>
			<svg
				viewBox="0 0 {strategyCalmarTierBreakdown.W} {strategyCalmarTierBreakdown.H}"
				class="w-full"
				style="height:80px"
			>
				{#each strategyCalmarTierBreakdown.buckets as b, i (i)}
					{@const x =
						strategyCalmarTierBreakdown.PAD_Y / 2 +
						i * (strategyCalmarTierBreakdown.BAR_W + strategyCalmarTierBreakdown.GAP)}
					{@const barH = Math.max(
						2,
						(b.count / strategyCalmarTierBreakdown.maxCount) *
							(strategyCalmarTierBreakdown.H - strategyCalmarTierBreakdown.PAD_Y - 12)
					)}
					{@const y = strategyCalmarTierBreakdown.H - 12 - barH}
					<rect
						{x}
						{y}
						width={strategyCalmarTierBreakdown.BAR_W}
						height={barH}
						rx="3"
						fill={b.color}
					/>
					<text
						x={x + strategyCalmarTierBreakdown.BAR_W / 2}
						y={strategyCalmarTierBreakdown.H - 2}
						text-anchor="middle"
						font-size="9"
						fill="var(--ch-axis-strong)">{b.label}</text
					>
					<text
						x={x + strategyCalmarTierBreakdown.BAR_W / 2}
						y={y - 2}
						text-anchor="middle"
						font-size="9"
						fill={b.color}>{b.count}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{strategyCalmarTierBreakdown.total} strategies · Calmar = annualised return / max drawdown · &gt;2
				is institutional-grade
			</p>
		</section>
	{/if}

	{#if strategyModeTimeframeMatrix}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Strategy Count — Mode × Timeframe
			</h3>
			<div class="overflow-x-auto">
				<table class="w-full text-[9px]">
					<thead>
						<tr>
							<th class="w-20 pb-1 text-left font-normal text-muted-foreground">Mode</th>
							{#each strategyModeTimeframeMatrix.TFS as tf, _i (_i)}
								<th class="px-1 pb-1 text-center font-normal text-muted-foreground">{tf}</th>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each strategyModeTimeframeMatrix.MODES as mode, _i (_i)}
							<tr>
								<td class="py-0.5 text-muted-foreground">{mode}</td>
								{#each strategyModeTimeframeMatrix.TFS as tf, _i (_i)}
									{@const cell = strategyModeTimeframeMatrix.cells.find(
										(c) => c.mode === mode && c.tf === tf
									)}
									{@const frac = cell ? cell.count / strategyModeTimeframeMatrix.maxCount : 0}
									{@const bg =
										frac > 0
											? `rgba(99,102,241,${(0.15 + frac * 0.75).toFixed(2)})`
											: 'transparent'}
									<td
										class="rounded px-1 py-0.5 text-center"
										style="background:{bg}; color:{frac > 0.5
											? 'var(--ch-axis-strong)'
											: 'var(--ch-axis-strong)'}"
									>
										{cell?.count ?? 0}
									</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Darker = more strategies at that mode/timeframe intersection · reveals coverage gaps
			</p>
		</section>
	{/if}

	{#if strategyTopAssetsByBestProfit}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Best Profit by Asset
			</h3>
			<div class="space-y-1">
				{#each strategyTopAssetsByBestProfit.rows as row, _i (_i)}
					{@const pct = ((row.avg / strategyTopAssetsByBestProfit.maxAvg) * 100).toFixed(1)}
					{@const color =
						row.avg >= 50
							? 'var(--ch-profit-strong)'
							: row.avg >= 20
								? 'var(--ch-violet)'
								: row.avg >= 5
									? 'var(--ch-warn)'
									: 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-20 shrink-0 truncate text-[9px] text-muted-foreground">{row.asset}</span>
						<div class="relative h-3 flex-1 rounded bg-muted/30">
							<div
								class="absolute top-0 left-0 h-full rounded"
								style="width:{pct}%; background:{color}"
							></div>
						</div>
						<span class="w-14 text-right font-mono text-[9px]" style="color:{color}"
							>{row.avg.toFixed(1)}%</span
						>
						<span class="w-10 text-right text-[9px] text-muted-foreground">n={row.count}</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Avg of best_profit_pct across strategies covering each asset · higher = strategies targeting
				this asset tend to outperform
			</p>
		</section>
	{/if}

	{#if strategyWinRateVsSortino}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win Rate vs Sortino Scatter ({strategyWinRateVsSortino.count} strategies)
			</h3>
			<svg
				viewBox="0 0 {strategyWinRateVsSortino.W} {strategyWinRateVsSortino.H}"
				class="w-full"
				style="height:100px"
			>
				{#if strategyWinRateVsSortino.zeroY !== null}
					<line
						x1="0"
						y1={strategyWinRateVsSortino.zeroY}
						x2={strategyWinRateVsSortino.W}
						y2={strategyWinRateVsSortino.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="3,3"
					/>
				{/if}
				{#each strategyWinRateVsSortino.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r={d.r} fill={d.color} stroke="none" />
				{/each}
			</svg>
			<div class="mt-1 flex justify-between text-[9px] text-muted-foreground">
				<span>← low win rate</span>
				<span>x=best win rate % · y=best Sortino · size=|Calmar| · indigo=positive Sortino</span>
				<span>high win rate →</span>
			</div>
		</section>
	{/if}

	{#if strategyBestProfitTimeline}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Strategy Best Profit by Import Date ({strategyBestProfitTimeline.count} strategies)
			</h3>
			<svg
				viewBox="0 0 {strategyBestProfitTimeline.W} {strategyBestProfitTimeline.H}"
				class="w-full"
				style="height:80px"
			>
				{#if strategyBestProfitTimeline.zeroY !== null}
					<line
						x1="0"
						y1={strategyBestProfitTimeline.zeroY}
						x2={strategyBestProfitTimeline.W}
						y2={strategyBestProfitTimeline.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="3,3"
					/>
				{/if}
				{#each strategyBestProfitTimeline.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="3" fill={d.color} stroke="none" />
				{/each}
			</svg>
			<div class="mt-1 flex justify-between text-[9px] text-muted-foreground">
				<span>oldest import</span>
				<span>x=last_imported date · y=best_profit_pct · green=profitable · dashed=zero line</span>
				<span>newest import</span>
			</div>
		</section>
	{/if}

	{#if strategyRunCountDistribution}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Strategy Run Count Distribution
			</h3>
			<svg
				viewBox="0 0 {strategyRunCountDistribution.W} {strategyRunCountDistribution.H}"
				class="w-full"
				style="height:70px"
			>
				{#each strategyRunCountDistribution.counts as b, i (i)}
					{@const x =
						strategyRunCountDistribution.PAD + i * (strategyRunCountDistribution.barW + 1)}
					{@const barH = Math.max(
						1,
						(b.count / strategyRunCountDistribution.maxCount) *
							(strategyRunCountDistribution.H - strategyRunCountDistribution.PAD * 2 - 8)
					)}
					<rect
						{x}
						y={strategyRunCountDistribution.H - 8 - barH}
						width={strategyRunCountDistribution.barW}
						height={barH}
						rx="1"
						fill="var(--ch-violet)"
					/>
					{#if i === 0 || i === strategyRunCountDistribution.counts.length - 1}
						<text
							x={x + strategyRunCountDistribution.barW / 2}
							y={strategyRunCountDistribution.H - 1}
							text-anchor="middle"
							font-size="7"
							fill="var(--ch-axis)">{b.label}</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Distribution of backtest run count per strategy · most strategies are run a few times ·
				outliers = heavily iterated strategies
			</p>
		</section>
	{/if}

	{#if strategyCalmarVsBestProfit}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Calmar vs Best Profit Scatter ({strategyCalmarVsBestProfit.count} strategies)
			</h3>
			<svg
				viewBox="0 0 {strategyCalmarVsBestProfit.W} {strategyCalmarVsBestProfit.H}"
				class="w-full"
				style="height:100px"
			>
				{#if strategyCalmarVsBestProfit.zeroX !== null}
					<line
						x1={strategyCalmarVsBestProfit.zeroX}
						y1="0"
						x2={strategyCalmarVsBestProfit.zeroX}
						y2={strategyCalmarVsBestProfit.H}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="3,3"
					/>
				{/if}
				{#if strategyCalmarVsBestProfit.zeroY !== null}
					<line
						x1="0"
						y1={strategyCalmarVsBestProfit.zeroY}
						x2={strategyCalmarVsBestProfit.W}
						y2={strategyCalmarVsBestProfit.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="3,3"
					/>
				{/if}
				{#each strategyCalmarVsBestProfit.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="3" fill={d.color} stroke="none" />
				{/each}
			</svg>
			<div class="mt-1 flex justify-between text-[9px] text-muted-foreground">
				<span>← low Calmar</span>
				<span
					>x=best Calmar · y=best profit % · green=both positive · top-right = ideal strategies</span
				>
				<span>high Calmar →</span>
			</div>
		</section>
	{/if}

	{#if strategyWorstDrawdownRanking}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Drawdown Control (lowest worst DD)
			</h3>
			<div class="space-y-1.5">
				{#each strategyWorstDrawdownRanking.rows as row, i (i)}
					{@const pct = ((row.dd / strategyWorstDrawdownRanking.maxDD) * 100).toFixed(1)}
					{@const color =
						row.dd <= 15 ? 'var(--ch-profit)' : row.dd <= 30 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right text-[9px] text-muted-foreground">{i + 1}.</span>
						<span class="w-36 truncate text-[9px] text-muted-foreground">{row.name}</span>
						<div class="h-3 flex-1 overflow-hidden rounded bg-muted/20">
							<div class="h-full rounded" style="width:{pct}%; background:{color}"></div>
						</div>
						<span class="w-14 text-right font-mono text-[10px]" style="color:{color}"
							>{row.dd.toFixed(1)}%</span
						>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Strategies ranked by lowest worst drawdown · green ≤15% · yellow ≤30% · red &gt;30% ·
				shorter bar = better capital preservation
			</p>
		</section>
	{/if}

	{#if strategyAvgTradesByTimeframe}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Run Count by Timeframe
			</h3>
			<svg
				viewBox="0 0 {strategyAvgTradesByTimeframe.W} {strategyAvgTradesByTimeframe.H}"
				class="w-full"
				style="height:80px"
			>
				{#each strategyAvgTradesByTimeframe.rows as row, i (i)}
					{@const x =
						strategyAvgTradesByTimeframe.PAD +
						i *
							((strategyAvgTradesByTimeframe.W - strategyAvgTradesByTimeframe.PAD * 2) /
								strategyAvgTradesByTimeframe.rows.length)}
					{@const barH = Math.max(
						2,
						(row.avg / strategyAvgTradesByTimeframe.maxAvg) *
							(strategyAvgTradesByTimeframe.H - strategyAvgTradesByTimeframe.PAD * 2 - 12)
					)}
					<rect
						{x}
						y={strategyAvgTradesByTimeframe.H - 12 - barH}
						width={strategyAvgTradesByTimeframe.barW}
						height={barH}
						rx="2"
						fill="var(--ch-violet)"
					/>
					<text
						x={x + strategyAvgTradesByTimeframe.barW / 2}
						y={strategyAvgTradesByTimeframe.H - 1}
						text-anchor="middle"
						font-size="8"
						fill="var(--ch-axis)">{row.tf}</text
					>
					<text
						x={x + strategyAvgTradesByTimeframe.barW / 2}
						y={strategyAvgTradesByTimeframe.H - 14 - barH}
						text-anchor="middle"
						font-size="7"
						fill="var(--ch-axis)">{row.avg.toFixed(1)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg number of backtest runs per strategy by timeframe · shows where most research effort is
				focused · {strategyAvgTradesByTimeframe.rows.reduce((a, b) => a + b.count, 0)} strategies total
			</p>
		</section>
	{/if}

	{#if strategyTopSortinoLeaderboard}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Sortino Ratio by Strategy
			</h3>
			<div class="space-y-1.5">
				{#each strategyTopSortinoLeaderboard.rows as row, i (i)}
					{@const pct = ((row.sortino / strategyTopSortinoLeaderboard.maxSortino) * 100).toFixed(1)}
					{@const color =
						row.sortino >= 3
							? 'var(--ch-profit)'
							: row.sortino >= 1.5
								? 'var(--ch-violet)'
								: 'var(--ch-warn)'}
					<div class="flex items-center gap-2">
						<span class="w-5 text-right text-[9px] text-muted-foreground">{i + 1}.</span>
						<span class="w-36 truncate text-[9px] text-muted-foreground">{row.name}</span>
						<div class="h-3 flex-1 overflow-hidden rounded bg-muted/20">
							<div class="h-full rounded" style="width:{pct}%; background:{color}"></div>
						</div>
						<span class="w-12 text-right font-mono text-[10px]" style="color:{color}"
							>{row.sortino.toFixed(2)}</span
						>
						<span class="w-12 text-right text-[9px] text-muted-foreground">{row.runs} runs</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Best Sortino ratio per strategy across all runs · green ≥3 · indigo ≥1.5 · yellow &lt;1.5 ·
				Sortino rewards upside volatility and penalises only downside risk
			</p>
		</section>
	{/if}

	{#if strategyBestSharpeDistribution}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Sharpe Distribution Across Strategies
			</h3>
			<svg
				viewBox="0 0 {strategyBestSharpeDistribution.W} {strategyBestSharpeDistribution.H}"
				class="w-full"
				style="height:72px"
			>
				{#each strategyBestSharpeDistribution.counts as b, i (i)}
					{@const x =
						strategyBestSharpeDistribution.PAD + i * (strategyBestSharpeDistribution.barW + 1)}
					{@const barH = Math.max(
						1,
						(b.count / strategyBestSharpeDistribution.maxCount) *
							(strategyBestSharpeDistribution.H - strategyBestSharpeDistribution.PAD * 2 - 10)
					)}
					{@const color =
						b.lo >= 2
							? 'var(--ch-profit)'
							: b.lo >= 1
								? 'var(--ch-violet)'
								: b.lo >= 0
									? 'var(--ch-warn)'
									: 'var(--ch-loss)'}
					<rect
						{x}
						y={strategyBestSharpeDistribution.H - 10 - barH}
						width={strategyBestSharpeDistribution.barW}
						height={barH}
						rx="1"
						fill={color}
					/>
				{/each}
				<text
					x={strategyBestSharpeDistribution.PAD}
					y={strategyBestSharpeDistribution.H - 1}
					font-size="7"
					fill="var(--ch-axis)">{strategyBestSharpeDistribution.mn}</text
				>
				<text
					x={strategyBestSharpeDistribution.W - strategyBestSharpeDistribution.PAD}
					y={strategyBestSharpeDistribution.H - 1}
					text-anchor="end"
					font-size="7"
					fill="var(--ch-axis)">{strategyBestSharpeDistribution.mx}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{strategyBestSharpeDistribution.total} strategies · avg best Sharpe {strategyBestSharpeDistribution.avg}
				· green ≥2 · indigo 1–2 · yellow 0–1 · red &lt;0 · right-skewed = most strategies achieve good
				risk-adjusted returns
			</p>
		</section>
	{/if}

	{#if strategyBestCalmarDistribution}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Calmar Distribution Across Strategies
			</h3>
			<svg
				viewBox="0 0 {strategyBestCalmarDistribution.W} {strategyBestCalmarDistribution.H}"
				class="w-full"
				style="height:72px"
			>
				{#each strategyBestCalmarDistribution.counts as b, i (i)}
					{@const x =
						strategyBestCalmarDistribution.PAD + i * (strategyBestCalmarDistribution.barW + 1)}
					{@const barH = Math.max(
						1,
						(b.count / strategyBestCalmarDistribution.maxCount) *
							(strategyBestCalmarDistribution.H - strategyBestCalmarDistribution.PAD * 2 - 10)
					)}
					{@const color =
						b.lo >= 3
							? 'var(--ch-profit)'
							: b.lo >= 1
								? 'var(--ch-violet)'
								: b.lo >= 0
									? 'var(--ch-warn)'
									: 'var(--ch-loss)'}
					<rect
						{x}
						y={strategyBestCalmarDistribution.H - 10 - barH}
						width={strategyBestCalmarDistribution.barW}
						height={barH}
						rx="1"
						fill={color}
					/>
				{/each}
				<text
					x={strategyBestCalmarDistribution.PAD}
					y={strategyBestCalmarDistribution.H - 1}
					font-size="7"
					fill="var(--ch-axis)">{strategyBestCalmarDistribution.mn}</text
				>
				<text
					x={strategyBestCalmarDistribution.W - strategyBestCalmarDistribution.PAD}
					y={strategyBestCalmarDistribution.H - 1}
					text-anchor="end"
					font-size="7"
					fill="var(--ch-axis)">{strategyBestCalmarDistribution.mx}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{strategyBestCalmarDistribution.total} strategies · avg best Calmar {strategyBestCalmarDistribution.avg}
				· green ≥3 · indigo 1–3 · yellow 0–1 · Calmar = annual return ÷ max drawdown · higher = better
				capital preservation
			</p>
		</section>
	{/if}

	{#if strategyTimeframeCountHeatmap}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Strategy Name Prefix × Best Timeframe Heatmap
			</h3>
			<svg
				viewBox="0 0 {strategyTimeframeCountHeatmap.W} {strategyTimeframeCountHeatmap.H}"
				class="w-full"
				style="height:{strategyTimeframeCountHeatmap.H}px"
			>
				{#each strategyTimeframeCountHeatmap.usedTfs as tf, ti (ti)}
					<text
						x={strategyTimeframeCountHeatmap.PAD +
							ti * (strategyTimeframeCountHeatmap.cellW + 2) +
							strategyTimeframeCountHeatmap.cellW / 2}
						y={10}
						text-anchor="middle"
						font-size="6.5"
						fill="var(--ch-axis)">{tf}</text
					>
				{/each}
				{#each strategyTimeframeCountHeatmap.decades as d, di (di)}
					<text
						x={strategyTimeframeCountHeatmap.PAD - 2}
						y={strategyTimeframeCountHeatmap.PAD +
							di * (strategyTimeframeCountHeatmap.cellH + 2) +
							strategyTimeframeCountHeatmap.cellH -
							2}
						text-anchor="end"
						font-size="6"
						fill="var(--ch-axis)">{d}</text
					>
				{/each}
				{#each strategyTimeframeCountHeatmap.cells as c, _i (_i)}
					{@const x =
						strategyTimeframeCountHeatmap.PAD + c.ti * (strategyTimeframeCountHeatmap.cellW + 2)}
					{@const y =
						strategyTimeframeCountHeatmap.PAD + c.di * (strategyTimeframeCountHeatmap.cellH + 2)}
					{@const alpha =
						c.count === 0 ? 0.04 : 0.15 + (c.count / strategyTimeframeCountHeatmap.maxCount) * 0.75}
					<rect
						{x}
						{y}
						width={strategyTimeframeCountHeatmap.cellW}
						height={strategyTimeframeCountHeatmap.cellH}
						rx="2"
						fill="rgba(99,102,241,{alpha.toFixed(2)})"
					/>
					{#if c.count > 0}
						<text
							x={x + strategyTimeframeCountHeatmap.cellW / 2}
							y={y + strategyTimeframeCountHeatmap.cellH - 3}
							text-anchor="middle"
							font-size="7"
							fill="var(--ch-axis-strong)">{c.count}</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Strategy name prefix (rows) × best timeframe (cols) · darker = more strategies in that combo
				· reveals which name families prefer which timeframes
			</p>
		</section>
	{/if}

	{#if strategyRunCountVsBestProfit}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Run Count vs Best Profit Scatter ({strategyRunCountVsBestProfit.count} strategies)
			</h3>
			<svg
				viewBox="0 0 {strategyRunCountVsBestProfit.W} {strategyRunCountVsBestProfit.H}"
				class="w-full"
				style="height:100px"
			>
				<line
					x1={strategyRunCountVsBestProfit.PAD}
					y1={strategyRunCountVsBestProfit.zeroY}
					x2={strategyRunCountVsBestProfit.W - strategyRunCountVsBestProfit.PAD}
					y2={strategyRunCountVsBestProfit.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.8"
					stroke-dasharray="3,2"
				/>
				{#each strategyRunCountVsBestProfit.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="2.5" fill={d.color} />
				{/each}
				<text
					x={strategyRunCountVsBestProfit.PAD}
					y={strategyRunCountVsBestProfit.H - 2}
					font-size="6.5"
					fill="var(--ch-axis-muted)">few runs</text
				>
				<text
					x={strategyRunCountVsBestProfit.W - strategyRunCountVsBestProfit.PAD}
					y={strategyRunCountVsBestProfit.H - 2}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-axis-muted)">{strategyRunCountVsBestProfit.rMax} runs</text
				>
				<text
					x={strategyRunCountVsBestProfit.PAD - 2}
					y={strategyRunCountVsBestProfit.PAD + 4}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{strategyRunCountVsBestProfit.pMax}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				x=total backtest runs · y=best profit % · green=positive · red=negative · strategies in
				top-right are heavily tested AND show high upside potential
			</p>
		</section>
	{/if}
	{#if strategyAvgCalmarByTimeframe}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Best Calmar by Timeframe
			</h3>
			<svg
				viewBox="0 0 {strategyAvgCalmarByTimeframe.W} {strategyAvgCalmarByTimeframe.H}"
				class="w-full"
				style="height:70px"
			>
				<line
					x1={strategyAvgCalmarByTimeframe.PAD}
					y1={strategyAvgCalmarByTimeframe.midY}
					x2={strategyAvgCalmarByTimeframe.W - strategyAvgCalmarByTimeframe.PAD}
					y2={strategyAvgCalmarByTimeframe.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each strategyAvgCalmarByTimeframe.rows as row, i (i)}
					{@const x =
						strategyAvgCalmarByTimeframe.PAD + i * (strategyAvgCalmarByTimeframe.barW + 3)}
					{@const bh = strategyAvgCalmarByTimeframe.toH(row.avg)}
					{@const color =
						row.avg >= 1 ? 'var(--ch-profit)' : row.avg >= 0 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					{@const y =
						row.avg >= 0
							? strategyAvgCalmarByTimeframe.midY - bh
							: strategyAvgCalmarByTimeframe.midY}
					<rect {x} {y} width={strategyAvgCalmarByTimeframe.barW} height={bh} rx="1" fill={color} />
					<text
						x={x + strategyAvgCalmarByTimeframe.barW / 2}
						y={strategyAvgCalmarByTimeframe.H - 1}
						text-anchor="middle"
						font-size="7"
						fill="var(--ch-axis)">{row.tf}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg best Calmar ratio grouped by timeframe · green≥1 · yellow≥0 · red&lt;0 · reveals which
				timeframes consistently produce better drawdown-adjusted returns
			</p>
		</section>
	{/if}
	{#if strategyModeWinRateComparison}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Win Rate by Trading Mode
			</h3>
			<div class="space-y-2">
				{#each strategyModeWinRateComparison.rows as row, _i (_i)}
					{@const medW = (row.med / strategyModeWinRateComparison.maxMed) * 100}
					{@const color =
						row.med >= 55
							? 'var(--ch-profit)'
							: row.med >= 45
								? 'var(--ch-warn)'
								: 'var(--ch-loss)'}
					<div class="flex items-center gap-2">
						<span class="w-20 text-right text-[10px] text-muted-foreground capitalize"
							>{row.mode}</span
						>
						<div class="h-4 flex-1 overflow-hidden rounded bg-secondary/40">
							<div
								class="h-4 rounded transition-all"
								style="width:{medW}%;background:{color}"
							></div>
						</div>
						<span class="w-14 text-right font-mono text-[10px]" style="color:{color}"
							>{row.med.toFixed(1)}% med</span
						>
						<span class="w-8 text-right text-[9px] text-muted-foreground">{row.count}s</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[9px] text-muted-foreground">
				Median best win rate per trading mode · green≥55% · yellow≥45% · reveals whether spot or
				futures strategies achieve higher win rates
			</p>
		</section>
	{/if}
	{#if strategyBestProfitHistogram}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Profit Distribution ({strategyBestProfitHistogram.total} strategies)
			</h3>
			<svg
				viewBox="0 0 {strategyBestProfitHistogram.W} {strategyBestProfitHistogram.H}"
				class="w-full"
				style="height:70px"
			>
				<line
					x1={strategyBestProfitHistogram.zeroX}
					y1={strategyBestProfitHistogram.PAD}
					x2={strategyBestProfitHistogram.zeroX}
					y2={strategyBestProfitHistogram.H - strategyBestProfitHistogram.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.8"
					stroke-dasharray="2,2"
				/>
				{#each strategyBestProfitHistogram.counts as b, i (i)}
					{@const x = strategyBestProfitHistogram.PAD + i * (strategyBestProfitHistogram.barW + 1)}
					{@const bh = Math.max(
						1,
						(b.count / strategyBestProfitHistogram.maxCount) *
							(strategyBestProfitHistogram.H - strategyBestProfitHistogram.PAD * 2 - 8)
					)}
					{@const color = b.lo >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					<rect
						{x}
						y={strategyBestProfitHistogram.H - 8 - bh}
						width={strategyBestProfitHistogram.barW}
						height={bh}
						rx="1"
						fill={color}
					/>
				{/each}
				<text
					x={strategyBestProfitHistogram.PAD}
					y={strategyBestProfitHistogram.H - 1}
					font-size="7"
					fill="var(--ch-axis-muted)">{strategyBestProfitHistogram.mn}%</text
				>
				<text
					x={strategyBestProfitHistogram.W - strategyBestProfitHistogram.PAD}
					y={strategyBestProfitHistogram.H - 1}
					text-anchor="end"
					font-size="7"
					fill="var(--ch-axis-muted)">{strategyBestProfitHistogram.mx}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Distribution of best profit % across all strategies · green=positive · red=negative ·
				right-skewed = most strategies have achieved positive returns at best
			</p>
		</section>
	{/if}
	{#if strategyRunCountTimeline}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Active Strategy Count by Month
			</h3>
			<svg
				viewBox="0 0 {strategyRunCountTimeline.W} {strategyRunCountTimeline.H}"
				class="w-full"
				style="height:65px"
			>
				<polygon points={strategyRunCountTimeline.area} fill="var(--ch-violet-light)" />
				<polyline
					points={strategyRunCountTimeline.poly}
					fill="none"
					stroke="var(--ch-violet)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				{#each strategyRunCountTimeline.pts as p, i (i)}
					{@const x =
						strategyRunCountTimeline.PAD +
						(i / Math.max(strategyRunCountTimeline.pts.length - 1, 1)) *
							(strategyRunCountTimeline.W - strategyRunCountTimeline.PAD * 2)}
					<circle
						cx={x}
						cy={strategyRunCountTimeline.PAD +
							(1 - p.count / strategyRunCountTimeline.maxCount) *
								(strategyRunCountTimeline.H - strategyRunCountTimeline.PAD * 2)}
						r="2"
						fill="var(--ch-violet-strong)"
					/>
					{#if i % Math.max(1, Math.floor(strategyRunCountTimeline.pts.length / 6)) === 0}
						<text
							{x}
							y={strategyRunCountTimeline.H - 1}
							text-anchor="middle"
							font-size="6.5"
							fill="var(--ch-axis-muted)">{p.mo}</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Number of distinct strategies with runs each month · rising = expanding strategy search ·
				flat = focused refinement of existing candidates
			</p>
		</section>
	{/if}
	{#if strategySharpeVsWinRateScatter}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Sharpe vs Best Win Rate ({strategySharpeVsWinRateScatter.count} strategies)
			</h3>
			<svg
				viewBox="0 0 {strategySharpeVsWinRateScatter.W} {strategySharpeVsWinRateScatter.H}"
				class="w-full"
				style="height:92px"
			>
				<line
					x1={strategySharpeVsWinRateScatter.PAD}
					y1={strategySharpeVsWinRateScatter.zeroY}
					x2={strategySharpeVsWinRateScatter.W - strategySharpeVsWinRateScatter.PAD}
					y2={strategySharpeVsWinRateScatter.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each strategySharpeVsWinRateScatter.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="2.5" fill={d.color} />
				{/each}
				<text
					x={strategySharpeVsWinRateScatter.PAD}
					y={strategySharpeVsWinRateScatter.H - 2}
					font-size="6.5"
					fill="var(--ch-axis-muted)">WR {strategySharpeVsWinRateScatter.wMin}%</text
				>
				<text
					x={strategySharpeVsWinRateScatter.W - strategySharpeVsWinRateScatter.PAD}
					y={strategySharpeVsWinRateScatter.H - 2}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-axis-muted)">{strategySharpeVsWinRateScatter.wMax}%</text
				>
				<text
					x={strategySharpeVsWinRateScatter.PAD}
					y={strategySharpeVsWinRateScatter.PAD + 5}
					font-size="6"
					fill="var(--ch-axis-muted)">Sharpe {strategySharpeVsWinRateScatter.sMax}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				x=best win rate % · y=best Sharpe ratio · green=best profit≥10% · yellow≥0% · red=losing ·
				top-right = high win rate AND high Sharpe simultaneously
			</p>
		</section>
	{/if}

	{#if strategyRunCountHistogram}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Strategy Run Count Distribution ({strategyRunCountHistogram.total} strategies)
			</h3>
			<svg
				viewBox="0 0 {strategyRunCountHistogram.W} {strategyRunCountHistogram.H}"
				class="w-full"
				style="height:72px"
			>
				{#each strategyRunCountHistogram.bars as bar, i (i)}
					{@const barH = bar.h}
					{@const y = strategyRunCountHistogram.H - strategyRunCountHistogram.PAD - barH}
					{@const intensity = bar.count / strategyRunCountHistogram.maxCount}
					<rect
						x={bar.x}
						{y}
						width={strategyRunCountHistogram.bw}
						height={barH}
						rx="2"
						fill="rgba(99,102,241,{0.3 + intensity * 0.5})"
					/>
					{#if bar.count > 0}
						<text
							x={bar.x + strategyRunCountHistogram.bw / 2}
							y={y - 2}
							text-anchor="middle"
							font-size="6"
							fill="var(--ch-axis-strong)">{bar.count}</text
						>
					{/if}
					{#if i % 2 === 0 && bar.label}
						<text
							x={bar.x + strategyRunCountHistogram.bw / 2}
							y={strategyRunCountHistogram.H - 2}
							text-anchor="middle"
							font-size="5.5"
							fill="var(--ch-axis-muted)">{bar.label}</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Histogram of how many backtest runs each strategy has · x-axis = run count · y-axis = number
				of strategies · darker = more strategies in that bucket
			</p>
		</section>
	{/if}

	{#if strategyStatusProfitComparison}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Profit Distribution by Status
			</h3>
			<svg
				viewBox="0 0 {strategyStatusProfitComparison.W} {strategyStatusProfitComparison.H}"
				class="w-full"
				style="height:{strategyStatusProfitComparison.H}px"
			>
				<line
					x1={strategyStatusProfitComparison.zeroX}
					y1="0"
					x2={strategyStatusProfitComparison.zeroX}
					y2={strategyStatusProfitComparison.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.8"
					stroke-dasharray="3,2"
				/>
				{#each strategyStatusProfitComparison.items as item, i (i)}
					{@const y = i * 28 + 8}
					{@const q1x = item.q1X}
					{@const q3x = item.q3X}
					{@const iqrW = Math.abs(q3x - q1x)}
					<text
						x={strategyStatusProfitComparison.PAD}
						y={y + 10}
						font-size="8"
						fill={item.color}
						font-weight="500">{item.status}</text
					>
					<rect
						x={Math.min(q1x, q3x)}
						{y}
						width={Math.max(2, iqrW)}
						height="14"
						rx="3"
						fill={item.color}
						opacity="0.4"
					/>
					<line
						x1={item.avgX}
						y1={y}
						x2={item.avgX}
						y2={y + 14}
						stroke={item.color}
						stroke-width="2"
					/>
					<text x={item.avgX + 3} y={y + 10} font-size="6.5" fill={item.color}
						>{item.avg >= 0 ? '+' : ''}{item.avg.toFixed(1)}%</text
					>
					<text
						x={strategyStatusProfitComparison.W - 2}
						y={y + 10}
						text-anchor="end"
						font-size="6"
						fill="var(--ch-axis-muted)">{item.count} strats</text
					>
				{/each}
				<text
					x={strategyStatusProfitComparison.PAD}
					y={strategyStatusProfitComparison.H - 1}
					font-size="5.5"
					fill="var(--ch-axis-muted)">{strategyStatusProfitComparison.mn}%</text
				>
				<text
					x={strategyStatusProfitComparison.PAD + strategyStatusProfitComparison.barMaxW}
					y={strategyStatusProfitComparison.H - 1}
					text-anchor="end"
					font-size="5.5"
					fill="var(--ch-axis-muted)">{strategyStatusProfitComparison.mx}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Best profit % IQR box per strategy status · bar = Q1–Q3 range · vertical line = mean ·
				green=active · gray=inactive · red=archived
			</p>
		</section>
	{/if}

	{#if strategySortinoBars}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Sortino Leaderboard — All Strategies (top 10)
			</h3>
			<svg
				viewBox="0 0 {strategySortinoBars.W} {strategySortinoBars.H}"
				class="w-full"
				style="height:{strategySortinoBars.H}px"
			>
				{#each strategySortinoBars.rows as row, i (i)}
					{@const y = i * 16 + 2}
					{@const bw = Math.max(
						2,
						(Math.abs(row.sortino) / strategySortinoBars.maxAbs) * strategySortinoBars.barMaxW
					)}
					{@const color =
						row.sortino >= 3
							? 'var(--ch-profit)'
							: row.sortino >= 0
								? 'var(--ch-violet)'
								: 'var(--ch-loss)'}
					<text x={strategySortinoBars.PAD} y={y + 10} font-size="7" fill="var(--ch-axis-strong)"
						>{row.name}</text
					>
					<rect x={strategySortinoBars.PAD + 115} {y} width={bw} height="12" rx="2" fill={color} />
					<text x={strategySortinoBars.PAD + 115 + bw + 3} y={y + 10} font-size="7" fill={color}
						>{row.sortino.toFixed(2)}</text
					>
					<text
						x={strategySortinoBars.W - 2}
						y={y + 10}
						text-anchor="end"
						font-size="6"
						fill="var(--ch-axis-muted)">{row.runs}r</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Strategies ranked by best Sortino ratio · Sortino penalizes only downside volatility ·
				green≥3 · indigo≥0 · count=total runs for that strategy
			</p>
		</section>
	{/if}
	{#if strategyCalmarHistogram}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Calmar Ratio Distribution
			</h3>
			<svg
				viewBox="0 0 {strategyCalmarHistogram.W} {strategyCalmarHistogram.H}"
				class="w-full"
				style="height:{strategyCalmarHistogram.H}px"
			>
				<line
					x1={strategyCalmarHistogram.zeroX}
					y1="0"
					x2={strategyCalmarHistogram.zeroX}
					y2={strategyCalmarHistogram.H - 16}
					stroke="var(--ch-axis-muted)"
					stroke-width="0.8"
				/>
				{#each strategyCalmarHistogram.bars as bar, _i (_i)}
					<rect
						x={bar.x}
						y={strategyCalmarHistogram.H - 16 - bar.h}
						width={strategyCalmarHistogram.bw}
						height={bar.h}
						rx="1"
						fill={bar.color}
					/>
				{/each}
				<text
					x={strategyCalmarHistogram.PAD}
					y={strategyCalmarHistogram.H - 3}
					font-size="7"
					fill="var(--ch-axis)">{strategyCalmarHistogram.mn}</text
				>
				<text
					x={strategyCalmarHistogram.W - strategyCalmarHistogram.PAD}
					y={strategyCalmarHistogram.H - 3}
					text-anchor="end"
					font-size="7"
					fill="var(--ch-axis)">{strategyCalmarHistogram.mx}</text
				>
				<text
					x={strategyCalmarHistogram.W / 2}
					y={strategyCalmarHistogram.H - 3}
					text-anchor="middle"
					font-size="7"
					fill="var(--ch-axis-muted)">n={strategyCalmarHistogram.total}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Distribution of best Calmar ratio per strategy · blue=Calmar≥0 · red=negative Calmar · zero
				line at profit/loss boundary · reveals how many strategies achieve risk-adjusted
				profitability
			</p>
		</section>
	{/if}
	{#if strategyAvgWinRateByStatus}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Best Win Rate by Status
			</h3>
			<svg
				viewBox="0 0 {strategyAvgWinRateByStatus.W} {strategyAvgWinRateByStatus.H}"
				class="w-full"
				style="height:{strategyAvgWinRateByStatus.H}px"
			>
				{#each strategyAvgWinRateByStatus.bars as bar, _i (_i)}
					<rect
						x={bar.x}
						y={strategyAvgWinRateByStatus.H - strategyAvgWinRateByStatus.PAD - 14 - bar.h}
						width={strategyAvgWinRateByStatus.bw}
						height={bar.h}
						rx="3"
						fill={bar.color}
					/>
					<text
						x={bar.x + strategyAvgWinRateByStatus.bw / 2}
						y={strategyAvgWinRateByStatus.H - strategyAvgWinRateByStatus.PAD - 14 - bar.h - 3}
						text-anchor="middle"
						font-size="7"
						fill={bar.color}>{bar.avg.toFixed(1)}%</text
					>
					<text
						x={bar.x + strategyAvgWinRateByStatus.bw / 2}
						y={strategyAvgWinRateByStatus.H - strategyAvgWinRateByStatus.PAD - 2}
						text-anchor="middle"
						font-size="7"
						fill="var(--ch-axis-strong)">{bar.status}</text
					>
					<text
						x={bar.x + strategyAvgWinRateByStatus.bw / 2}
						y={strategyAvgWinRateByStatus.H - 2}
						text-anchor="middle"
						font-size="6"
						fill="var(--ch-axis-muted)">{bar.count}s</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg best win rate % per strategy grouped by status · green=active · yellow=inactive ·
				gray=archived · count=strategies in group · reveals whether active strategies outperform
				retired ones
			</p>
		</section>
	{/if}
	{#if strategyTopRunsLeaderboard}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Most Backtested Strategies
			</h3>
			<svg
				viewBox="0 0 {strategyTopRunsLeaderboard.W} {strategyTopRunsLeaderboard.H}"
				class="w-full"
				style="height:{strategyTopRunsLeaderboard.H}px"
			>
				{#each strategyTopRunsLeaderboard.rows as row, i (i)}
					{@const y = i * 16 + 2}
					{@const bw = Math.max(
						2,
						(row.runs / strategyTopRunsLeaderboard.maxRuns) * strategyTopRunsLeaderboard.barMaxW
					)}
					{@const color =
						row.status === 'active'
							? 'var(--ch-profit)'
							: row.status === 'inactive'
								? 'var(--ch-warn-light)'
								: 'var(--ch-axis-muted)'}
					<text
						x={strategyTopRunsLeaderboard.PAD}
						y={y + 10}
						font-size="7"
						fill="var(--ch-axis-strong)">{row.name}</text
					>
					<rect
						x={strategyTopRunsLeaderboard.PAD + 118}
						{y}
						width={bw}
						height="12"
						rx="2"
						fill={color}
					/>
					<text
						x={strategyTopRunsLeaderboard.PAD + 118 + bw + 3}
						y={y + 10}
						font-size="7"
						fill="var(--ch-axis-strong)">{row.runs}r</text
					>
					<text
						x={strategyTopRunsLeaderboard.W - 2}
						y={y + 10}
						text-anchor="end"
						font-size="6"
						fill="var(--ch-axis-muted)">{row.profit >= 0 ? '+' : ''}{row.profit.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Strategies ranked by total backtest run count · bar color = status (green=active ·
				yellow=inactive · gray=archived) · right label = best profit % · reveals research intensity
				per strategy
			</p>
		</section>
	{/if}
	{#if strategyBestProfitVsRunCount}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Profit % vs Run Count
			</h3>
			<svg
				viewBox="0 0 {strategyBestProfitVsRunCount.W} {strategyBestProfitVsRunCount.H}"
				class="w-full"
				style="height:{strategyBestProfitVsRunCount.H}px"
			>
				<line
					x1={strategyBestProfitVsRunCount.PAD}
					y1={strategyBestProfitVsRunCount.zeroY}
					x2={strategyBestProfitVsRunCount.W - strategyBestProfitVsRunCount.PAD}
					y2={strategyBestProfitVsRunCount.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each strategyBestProfitVsRunCount.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="2" fill={d.color} />
				{/each}
				<text
					x={strategyBestProfitVsRunCount.PAD}
					y={strategyBestProfitVsRunCount.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">1 run</text
				>
				<text
					x={strategyBestProfitVsRunCount.W - strategyBestProfitVsRunCount.PAD}
					y={strategyBestProfitVsRunCount.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{strategyBestProfitVsRunCount.maxRuns}r</text
				>
				<text
					x={strategyBestProfitVsRunCount.PAD}
					y={strategyBestProfitVsRunCount.PAD + 5}
					font-size="6"
					fill="var(--ch-axis-muted)">{strategyBestProfitVsRunCount.maxP}%</text
				>
				<text
					x={strategyBestProfitVsRunCount.PAD}
					y={strategyBestProfitVsRunCount.H - strategyBestProfitVsRunCount.PAD + 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{strategyBestProfitVsRunCount.minP}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				x=run count · y=best profit % · green=active · yellow=inactive · gray=archived · zero
				baseline · reveals whether more research (more runs) correlates with better results
			</p>
		</section>
	{/if}
	{#if strategyMedianSharpeByTF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Median Best Sharpe by Timeframe
			</h3>
			<svg
				viewBox="0 0 {strategyMedianSharpeByTF.W} {strategyMedianSharpeByTF.H}"
				class="w-full"
				style="height:{strategyMedianSharpeByTF.H}px"
			>
				<line
					x1={strategyMedianSharpeByTF.PAD}
					y1={strategyMedianSharpeByTF.midY}
					x2={strategyMedianSharpeByTF.W - strategyMedianSharpeByTF.PAD}
					y2={strategyMedianSharpeByTF.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each strategyMedianSharpeByTF.bars as bar, _i (_i)}
					<rect
						x={bar.x}
						y={bar.median >= 0
							? strategyMedianSharpeByTF.midY - bar.h
							: strategyMedianSharpeByTF.midY}
						width={strategyMedianSharpeByTF.bw}
						height={bar.h}
						rx="1"
						fill={bar.color}
					/>
					<text
						x={bar.x + strategyMedianSharpeByTF.bw / 2}
						y={strategyMedianSharpeByTF.H - 2}
						text-anchor="middle"
						font-size="6.5"
						fill="var(--ch-axis)">{bar.tf}</text
					>
					<text
						x={bar.x + strategyMedianSharpeByTF.bw / 2}
						y={bar.median >= 0
							? strategyMedianSharpeByTF.midY - bar.h - 3
							: strategyMedianSharpeByTF.midY + bar.h + 9}
						text-anchor="middle"
						font-size="6"
						fill={bar.color}>{bar.median.toFixed(2)}</text
					>
					<text
						x={bar.x + strategyMedianSharpeByTF.bw / 2}
						y={strategyMedianSharpeByTF.PAD + 6}
						text-anchor="middle"
						font-size="5.5"
						fill="var(--ch-axis-muted)">{bar.count}s</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Median best Sharpe ratio per timeframe · green≥1 · yellow≥0 · red&lt;0 · diverging from
				center · count=strategies · reveals which timeframes tend to produce more risk-adjusted
				alpha
			</p>
		</section>
	{/if}
	{#if strategyTopSharpeLeaderboard}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Top Strategies by Best Sharpe
			</h3>
			<svg
				viewBox="0 0 {strategyTopSharpeLeaderboard.W} {strategyTopSharpeLeaderboard.H}"
				class="w-full"
				style="height:{strategyTopSharpeLeaderboard.H}px"
			>
				{#each strategyTopSharpeLeaderboard.rows as row, i (i)}
					{@const y = strategyTopSharpeLeaderboard.PAD + i * 18}
					{@const bw = Math.max(
						2,
						(row.sharpe / strategyTopSharpeLeaderboard.maxSharpe) *
							strategyTopSharpeLeaderboard.barMaxW
					)}
					{@const color =
						row.sharpe >= 2
							? 'var(--ch-profit)'
							: row.sharpe >= 1
								? 'var(--ch-violet)'
								: 'var(--ch-warn)'}
					<text
						x={strategyTopSharpeLeaderboard.PAD}
						y={y + 12}
						font-size="6.5"
						fill="var(--ch-axis-strong)">{row.name}</text
					>
					<rect
						x={strategyTopSharpeLeaderboard.PAD + 108}
						{y}
						width={bw}
						height="13"
						rx="2"
						fill={color}
					/>
					<text
						x={strategyTopSharpeLeaderboard.PAD + 108 + bw + 3}
						y={y + 12}
						font-size="6.5"
						fill={color}>{row.sharpe.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Top 8 strategies ranked by best Sharpe ratio across all runs · green≥2 · indigo≥1 ·
				yellow&lt;1 · identifies strategies with consistently strong risk-adjusted returns
			</p>
		</section>
	{/if}
	{#if strategyTopWinRateLeaderboard}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Top Strategies by Best Win Rate
			</h3>
			<svg
				viewBox="0 0 {strategyTopWinRateLeaderboard.W} {strategyTopWinRateLeaderboard.H}"
				class="w-full"
				style="height:{strategyTopWinRateLeaderboard.H}px"
			>
				{#each strategyTopWinRateLeaderboard.rows as row, i (i)}
					{@const y = strategyTopWinRateLeaderboard.PAD + i * 18}
					{@const bw = Math.max(
						2,
						(row.wr / strategyTopWinRateLeaderboard.maxWR) * strategyTopWinRateLeaderboard.barMaxW
					)}
					{@const color =
						row.wr >= 60
							? 'var(--ch-profit)'
							: row.wr >= 50
								? 'var(--ch-violet)'
								: 'var(--ch-warn)'}
					<text
						x={strategyTopWinRateLeaderboard.PAD}
						y={y + 12}
						font-size="6.5"
						fill="var(--ch-axis-strong)">{row.name}</text
					>
					<rect
						x={strategyTopWinRateLeaderboard.PAD + 108}
						{y}
						width={bw}
						height="13"
						rx="2"
						fill={color}
					/>
					<text
						x={strategyTopWinRateLeaderboard.PAD + 108 + bw + 3}
						y={y + 12}
						font-size="6.5"
						fill={color}>{row.wr.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Top 8 strategies by best win rate · green≥60% · indigo≥50% · yellow&lt;50% · strategies with
				consistently high win rates are easier to manage psychologically and compound better
			</p>
		</section>
	{/if}
	{#if strategyAvgProfitVsDrawdownScatter}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit% vs Avg Drawdown% Scatter
			</h3>
			<svg
				viewBox="0 0 {strategyAvgProfitVsDrawdownScatter.W} {strategyAvgProfitVsDrawdownScatter.H}"
				class="w-full"
				style="height:{strategyAvgProfitVsDrawdownScatter.H}px"
			>
				<line
					x1={strategyAvgProfitVsDrawdownScatter.PAD}
					y1={strategyAvgProfitVsDrawdownScatter.midY}
					x2={strategyAvgProfitVsDrawdownScatter.W - strategyAvgProfitVsDrawdownScatter.PAD}
					y2={strategyAvgProfitVsDrawdownScatter.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
					stroke-dasharray="2,2"
				/>
				<line
					x1={strategyAvgProfitVsDrawdownScatter.PAD}
					y1={strategyAvgProfitVsDrawdownScatter.PAD}
					x2={strategyAvgProfitVsDrawdownScatter.PAD}
					y2={strategyAvgProfitVsDrawdownScatter.H - strategyAvgProfitVsDrawdownScatter.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				{#each strategyAvgProfitVsDrawdownScatter.pts as p, _i (_i)}
					{@const cx =
						strategyAvgProfitVsDrawdownScatter.PAD +
						(p.x / strategyAvgProfitVsDrawdownScatter.maxX) *
							(strategyAvgProfitVsDrawdownScatter.W - strategyAvgProfitVsDrawdownScatter.PAD * 2)}
					{@const cy =
						strategyAvgProfitVsDrawdownScatter.midY -
						(p.y / strategyAvgProfitVsDrawdownScatter.maxAbsY) *
							(strategyAvgProfitVsDrawdownScatter.H / 2 - strategyAvgProfitVsDrawdownScatter.PAD)}
					{@const color = p.y > 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)'}
					<circle {cx} {cy} r="3" fill={color} />
					<text {cx} y={cy - 4} text-anchor="middle" font-size="5" fill="var(--ch-axis-muted)"
						>{p.name}</text
					>
				{/each}
				<text
					x={strategyAvgProfitVsDrawdownScatter.W - strategyAvgProfitVsDrawdownScatter.PAD}
					y={strategyAvgProfitVsDrawdownScatter.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">DD%→</text
				>
				<text
					x={strategyAvgProfitVsDrawdownScatter.PAD + 2}
					y={strategyAvgProfitVsDrawdownScatter.PAD + 7}
					font-size="6"
					fill="var(--ch-axis-muted)">Profit↑</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Scatter: Avg Drawdown% (X) vs Avg Profit% (Y) · green=profitable · red=losing · top-left =
				best strategies with high profit and low drawdown
			</p>
		</section>
	{/if}
	{#if strategyTotalRunsByTF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Run Count by Timeframe
			</h3>
			<svg
				viewBox="0 0 {strategyTotalRunsByTF.W} {strategyTotalRunsByTF.H}"
				class="w-full"
				style="height:{strategyTotalRunsByTF.H}px"
			>
				{#each strategyTotalRunsByTF.bars as b, i (i)}
					{@const bh = Math.max(
						2,
						(b.cnt / strategyTotalRunsByTF.maxCnt) *
							(strategyTotalRunsByTF.H - strategyTotalRunsByTF.PAD * 2)
					)}
					{@const x = strategyTotalRunsByTF.PAD + i * (strategyTotalRunsByTF.bw + 2)}
					{@const y = strategyTotalRunsByTF.H - strategyTotalRunsByTF.PAD - bh}
					<rect {x} {y} width={strategyTotalRunsByTF.bw} height={bh} fill="var(--ch-warn)" rx="1" />
					<text
						x={x + strategyTotalRunsByTF.bw / 2}
						y={strategyTotalRunsByTF.H}
						text-anchor="middle"
						font-size="6.5"
						fill="var(--ch-axis)">{b.tf}</text
					>
					<text
						x={x + strategyTotalRunsByTF.bw / 2}
						y={y - 2}
						text-anchor="middle"
						font-size="5.5"
						fill="var(--ch-warn)">{b.cnt}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Total backtest run count by timeframe · orange bars · most-tested timeframes indicate where
				optimization effort has been focused
			</p>
		</section>
	{/if}
	{#if strategyCalmarTrend}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Monthly Avg Calmar Trend
			</h3>
			<svg
				viewBox="0 0 {strategyCalmarTrend.W} {strategyCalmarTrend.H}"
				class="w-full"
				style="height:{strategyCalmarTrend.H}px"
			>
				<polyline
					points={strategyCalmarTrend.polyline}
					fill="none"
					stroke="var(--ch-teal-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				{#each strategyCalmarTrend.pts as p, i (i)}
					{#if i % Math.max(1, Math.floor(strategyCalmarTrend.pts.length / 6)) === 0}
						<text
							x={strategyCalmarTrend.toX(i).toFixed(1)}
							y={strategyCalmarTrend.H}
							text-anchor="middle"
							font-size="5.5"
							fill="var(--ch-axis-muted)">{p.mo}</text
						>
					{/if}
				{/each}
				<text
					x={strategyCalmarTrend.PAD}
					y={strategyCalmarTrend.PAD + 7}
					font-size="6"
					fill="var(--ch-teal)">{strategyCalmarTrend.maxV}</text
				>
				<text
					x={strategyCalmarTrend.PAD}
					y={strategyCalmarTrend.H - strategyCalmarTrend.PAD - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{strategyCalmarTrend.minV}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Monthly avg Calmar ratio trend across strategies · teal line · rising = strategies improving
				return-to-drawdown ratio over time · falling = recent strategies less risk-efficient
			</p>
		</section>
	{/if}
	{#if strategyProfitHistogram}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Profit% Distribution
			</h3>
			<svg
				viewBox="0 0 {strategyProfitHistogram.W} {strategyProfitHistogram.H}"
				class="w-full"
				style="height:{strategyProfitHistogram.H}px"
			>
				{#if strategyProfitHistogram.zeroX >= strategyProfitHistogram.PAD && strategyProfitHistogram.zeroX <= strategyProfitHistogram.W - strategyProfitHistogram.PAD}
					<line
						x1={strategyProfitHistogram.zeroX}
						y1={strategyProfitHistogram.PAD}
						x2={strategyProfitHistogram.zeroX}
						y2={strategyProfitHistogram.H - strategyProfitHistogram.PAD}
						stroke="var(--ch-axis-faint)"
						stroke-width="0.5"
						stroke-dasharray="2,2"
					/>
				{/if}
				{#each strategyProfitHistogram.counts as cnt, i (i)}
					{@const bh = Math.max(
						1,
						(cnt / strategyProfitHistogram.maxCnt) *
							(strategyProfitHistogram.H - strategyProfitHistogram.PAD * 2)
					)}
					{@const x = strategyProfitHistogram.PAD + i * (strategyProfitHistogram.bw + 1)}
					{@const y = strategyProfitHistogram.H - strategyProfitHistogram.PAD - bh}
					{@const binMid = +strategyProfitHistogram.minV + (i + 0.5) * strategyProfitHistogram.binW}
					{@const color = binMid >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss-light)'}
					<rect {x} {y} width={strategyProfitHistogram.bw} height={bh} fill={color} rx="1" />
					{#if i === 0 || i === strategyProfitHistogram.bins - 1}
						<text
							x={x + strategyProfitHistogram.bw / 2}
							y={strategyProfitHistogram.H}
							text-anchor="middle"
							font-size="5.5"
							fill="var(--ch-axis-muted)"
							>{i === 0 ? strategyProfitHistogram.minV : strategyProfitHistogram.maxV}%</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Distribution of avg profit% across all strategies · green=profitable bins · red=losing bins
				· dashed at 0% · right-skewed = majority of strategies are net profitable
			</p>
		</section>
	{/if}
	{#if strategyTopCalmarLeaderboard}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Top Calmar Leaderboard
			</h3>
			<svg
				viewBox="0 0 {strategyTopCalmarLeaderboard.W} {strategyTopCalmarLeaderboard.H}"
				class="w-full"
				style="height:{strategyTopCalmarLeaderboard.H}px"
			>
				<line
					x1={strategyTopCalmarLeaderboard.midX}
					y1={strategyTopCalmarLeaderboard.PAD}
					x2={strategyTopCalmarLeaderboard.midX}
					y2={strategyTopCalmarLeaderboard.H - strategyTopCalmarLeaderboard.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				{#each strategyTopCalmarLeaderboard.rows as r, i (i)}
					{@const bw =
						(Math.abs(r.calmar) / strategyTopCalmarLeaderboard.maxAbs) *
						(strategyTopCalmarLeaderboard.midX - strategyTopCalmarLeaderboard.PAD)}
					{@const y = strategyTopCalmarLeaderboard.PAD + i * (strategyTopCalmarLeaderboard.bh + 6)}
					{@const color =
						r.calmar >= 2
							? 'var(--ch-profit)'
							: r.calmar >= 0
								? 'var(--ch-teal)'
								: 'var(--ch-loss)'}
					{@const x =
						r.calmar >= 0
							? strategyTopCalmarLeaderboard.midX
							: strategyTopCalmarLeaderboard.midX - bw}
					<rect {x} {y} width={bw} height={strategyTopCalmarLeaderboard.bh} fill={color} rx="1" />
					<text
						x={strategyTopCalmarLeaderboard.midX - 3}
						y={y + strategyTopCalmarLeaderboard.bh / 2 + 2.5}
						text-anchor="end"
						font-size="6"
						fill="var(--ch-axis-strong)">{r.name}</text
					>
					<text
						x={r.calmar >= 0
							? strategyTopCalmarLeaderboard.midX + bw + 2
							: strategyTopCalmarLeaderboard.midX - bw - 2}
						y={y + strategyTopCalmarLeaderboard.bh / 2 + 2.5}
						text-anchor={r.calmar >= 0 ? 'start' : 'end'}
						font-size="5.5"
						fill={color}>{r.calmar.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Top strategies ranked by Calmar ratio · green≥2 · teal≥0 · Calmar = annual return / max
				drawdown · best strategies combine high returns with low DD
			</p>
		</section>
	{/if}
	{#if strategyDrawdownHistogram}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Drawdown% Distribution
			</h3>
			<svg
				viewBox="0 0 {strategyDrawdownHistogram.W} {strategyDrawdownHistogram.H}"
				class="w-full"
				style="height:{strategyDrawdownHistogram.H}px"
			>
				{#each strategyDrawdownHistogram.counts as cnt, i (i)}
					{@const bh = Math.max(
						1,
						(cnt / strategyDrawdownHistogram.maxCnt) *
							(strategyDrawdownHistogram.H - strategyDrawdownHistogram.PAD * 2)
					)}
					{@const x = strategyDrawdownHistogram.PAD + i * (strategyDrawdownHistogram.bw + 1)}
					{@const y = strategyDrawdownHistogram.H - strategyDrawdownHistogram.PAD - bh}
					{@const binMid =
						+strategyDrawdownHistogram.minV + (i + 0.5) * strategyDrawdownHistogram.binW}
					{@const color =
						binMid <= 10
							? 'var(--ch-profit)'
							: binMid <= 25
								? 'var(--ch-warn)'
								: 'var(--ch-loss-light)'}
					<rect {x} {y} width={strategyDrawdownHistogram.bw} height={bh} fill={color} rx="1" />
					{#if i === 0 || i === strategyDrawdownHistogram.bins - 1}
						<text
							x={x + strategyDrawdownHistogram.bw / 2}
							y={strategyDrawdownHistogram.H}
							text-anchor="middle"
							font-size="5.5"
							fill="var(--ch-axis-muted)"
							>{i === 0 ? strategyDrawdownHistogram.minV : strategyDrawdownHistogram.maxV}%</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Distribution of avg drawdown% across strategies · green≤10% · yellow≤25% · red&gt;25% ·
				left-skewed = most strategies maintain disciplined drawdown control
			</p>
		</section>
	{/if}
	{#if strategyTopSharpeByTF}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">Avg Sharpe by Timeframe</h3>
			<svg
				viewBox={`0 0 ${strategyTopSharpeByTF.W} ${strategyTopSharpeByTF.H}`}
				width="100%"
				style="height:65px"
			>
				<line
					x1={strategyTopSharpeByTF.PAD}
					y1={strategyTopSharpeByTF.midY}
					x2={strategyTopSharpeByTF.W - strategyTopSharpeByTF.PAD}
					y2={strategyTopSharpeByTF.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				{#each strategyTopSharpeByTF.bars as b, i (i)}
					{@const bh = Math.max(
						1,
						(Math.abs(b.avg) / strategyTopSharpeByTF.maxAbs) *
							(strategyTopSharpeByTF.midY - strategyTopSharpeByTF.PAD)
					)}
					{@const x = strategyTopSharpeByTF.PAD + i * (strategyTopSharpeByTF.bw + 4)}
					{@const y = b.avg >= 0 ? strategyTopSharpeByTF.midY - bh : strategyTopSharpeByTF.midY}
					{@const color =
						b.avg >= 1 ? 'var(--ch-profit)' : b.avg >= 0 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
					<rect {x} {y} width={strategyTopSharpeByTF.bw} height={bh} fill={color} rx="1" />
					<text
						x={x + strategyTopSharpeByTF.bw / 2}
						y={strategyTopSharpeByTF.H}
						text-anchor="middle"
						font-size="6"
						fill="var(--ch-axis)">{b.label}</text
					>
					<text
						x={x + strategyTopSharpeByTF.bw / 2}
						y={b.avg >= 0 ? y - 2 : y + bh + 7}
						text-anchor="middle"
						font-size="5.5"
						fill={color}>{b.avg.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg Sharpe ratio by backtest timeframe · green≥1 · teal≥0 · red&lt;0 · higher TF often
				reduces noise and improves Sharpe · compare across all strategies
			</p>
		</section>
	{/if}
	{#if strategyWinRateVsSortinoScatter}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">
				Win Rate% vs Avg Sortino Scatter
			</h3>
			<svg
				viewBox={`0 0 ${strategyWinRateVsSortinoScatter.W} ${strategyWinRateVsSortinoScatter.H}`}
				width="100%"
				style="height:80px"
			>
				<line
					x1={strategyWinRateVsSortinoScatter.PAD}
					y1={strategyWinRateVsSortinoScatter.toY(0)}
					x2={strategyWinRateVsSortinoScatter.W - strategyWinRateVsSortinoScatter.PAD}
					y2={strategyWinRateVsSortinoScatter.toY(0)}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
					stroke-dasharray="2,2"
				/>
				{#each strategyWinRateVsSortinoScatter.pts as p, _i (_i)}
					<circle
						cx={strategyWinRateVsSortinoScatter.toX(p.x)}
						cy={strategyWinRateVsSortinoScatter.toY(p.y)}
						r="3"
						fill={p.y >= 1
							? 'var(--ch-profit-light)'
							: p.y >= 0
								? 'var(--ch-teal-light)'
								: 'var(--ch-loss-light)'}
					/>
				{/each}
				<text
					x={strategyWinRateVsSortinoScatter.PAD}
					y={strategyWinRateVsSortinoScatter.H - 1}
					font-size="5.5"
					fill="var(--ch-axis-muted)">WR {strategyWinRateVsSortinoScatter.minX}%</text
				>
				<text
					x={strategyWinRateVsSortinoScatter.W - strategyWinRateVsSortinoScatter.PAD}
					y={strategyWinRateVsSortinoScatter.H - 1}
					text-anchor="end"
					font-size="5.5"
					fill="var(--ch-axis-muted)">{strategyWinRateVsSortinoScatter.maxX}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Strategy win rate% vs avg Sortino · green=Sortino≥1 · teal=Sortino≥0 · red=negative ·
				top-right cluster = high WR + strong risk-adjusted return
			</p>
		</section>
	{/if}
</main>
