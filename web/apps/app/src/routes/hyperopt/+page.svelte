<script lang="ts">
	import type { PageData } from './$types';
	import type { HyperoptEpoch } from '$lib/types';
	import { t, type Lang } from '$lib/i18n';
	import ChartInfo from '$lib/components/chart-info.svelte';

	let { data }: { data: PageData } = $props();
	const lang = $derived<Lang>(data.lang ?? 'zh');

	// ---- strategy selector ----
	const strategies = $derived(Object.keys(data.byStrategy).sort());
	let activeStrategy = $state('');
	const currentStrategy = $derived(
		activeStrategy && data.byStrategy[activeStrategy] ? activeStrategy : (strategies[0] ?? '')
	);
	const epochs = $derived<HyperoptEpoch[]>(
		currentStrategy ? (data.byStrategy[currentStrategy] ?? []) : []
	);
	const hasData = $derived(strategies.length > 0);

	// Metrics referenced by a few optional charts that are NOT part of the
	// api.hyperopt_epochs row (only present on legacy raw-hyperopt payloads).
	// Read via this cast so those charts degrade to "no data" instead of
	// failing the type-check.
	type EpochLegacy = { profit_factor?: number | null; timeframe?: string | null };
	const legacyEpoch = (e: HyperoptEpoch): EpochLegacy => e as HyperoptEpoch & EpochLegacy;

	// ---- loss curve SVG ----
	// Clip outliers: ignore loss > 500 for the y-scale
	const CLIP_LOSS = 500;
	const SVG_W = 800;
	const SVG_H = 200;
	const PAD = { top: 20, right: 20, bottom: 30, left: 55 };

	const chartEpochs = $derived(epochs.filter((e) => e.loss !== null));
	const clippedEpochs = $derived(chartEpochs.filter((e) => (e.loss ?? 0) <= CLIP_LOSS));

	const xMin = $derived(chartEpochs.length > 0 ? Math.min(...chartEpochs.map((e) => e.epoch)) : 0);
	const xMax = $derived(chartEpochs.length > 0 ? Math.max(...chartEpochs.map((e) => e.epoch)) : 1);
	const yVals = $derived(clippedEpochs.map((e) => e.loss ?? 0));
	const yMin = $derived(yVals.length > 0 ? Math.min(...yVals) : 0);
	const yMax = $derived(yVals.length > 0 ? Math.max(...yVals) : 1);
	const yRange = $derived(Math.max(yMax - yMin, 0.001));

	const plotW = SVG_W - PAD.left - PAD.right;
	const plotH = SVG_H - PAD.top - PAD.bottom;

	function toX(epoch: number): number {
		if (xMax === xMin) return PAD.left + plotW / 2;
		return PAD.left + ((epoch - xMin) / (xMax - xMin)) * plotW;
	}
	function toY(loss: number): number {
		const clamped = Math.min(loss, CLIP_LOSS);
		return PAD.top + plotH - ((clamped - yMin) / yRange) * plotH;
	}

	// best epoch on chart
	const bestEpoch = $derived(
		chartEpochs.length > 0
			? chartEpochs.reduce((a, b) => ((a.loss ?? Infinity) < (b.loss ?? Infinity) ? a : b))
			: null
	);

	// y-axis ticks: 5 evenly spaced
	const yTicks = $derived.by(() => {
		const ticks: number[] = [];
		for (let i = 0; i <= 4; i++) ticks.push(yMin + (yRange * i) / 4);
		return ticks;
	});

	// ---- top-20 table ----
	type SortKey = keyof Pick<
		HyperoptEpoch,
		| 'epoch'
		| 'loss'
		| 'sharpe'
		| 'calmar'
		| 'sortino'
		| 'profit_total'
		| 'winrate'
		| 'total_trades'
		| 'max_drawdown'
	>;
	let sortKey = $state<SortKey>('loss');
	let sortAsc = $state(true);

	function setSort(k: SortKey) {
		if (sortKey === k) {
			sortAsc = !sortAsc;
		} else {
			sortKey = k;
			sortAsc = k === 'loss'; // loss asc by default; others desc
		}
	}

	const top20 = $derived.by(() => {
		const sorted = [...epochs].sort((a, b) => {
			const av = a[sortKey] ?? (sortAsc ? Infinity : -Infinity);
			const bv = b[sortKey] ?? (sortAsc ? Infinity : -Infinity);
			return sortAsc ? (av as number) - (bv as number) : (bv as number) - (av as number);
		});
		return sorted.slice(0, 20);
	});

	function fmtN(v: number | null | undefined, dp = 3): string {
		if (v == null) return '—';
		return v.toFixed(dp);
	}
	function fmtPct(v: number | null | undefined): string {
		if (v == null) return '—';
		return (v * 100).toFixed(1) + '%';
	}

	// ---- param scatter grids ----
	// Collect param keys from all epochs
	const paramKeys = $derived.by(() => {
		const keys = new Set<string>();
		for (const e of epochs) {
			if (e.params) for (const k of Object.keys(e.params)) keys.add(k);
		}
		return [...keys].sort();
	});

	// For each param key, build scatter points {x: paramVal, y: loss}
	type ScatterPt = { x: number; y: number; isBest: boolean };
	function scatterPts(key: string): ScatterPt[] {
		return epochs
			.filter(
				(e) => e.params != null && e.params[key] != null && e.loss != null && e.loss <= CLIP_LOSS
			)
			.map((e) => ({ x: e.params![key], y: e.loss!, isBest: !!e.is_best }));
	}

	// Parameter importance: |Pearson correlation| between param values and loss
	const paramImportance = $derived.by(() => {
		if (paramKeys.length === 0 || epochs.length < 5) return [];
		const validEpochs = epochs.filter(
			(e) => e.loss != null && e.loss <= CLIP_LOSS && e.params != null
		);
		if (validEpochs.length < 5) return [];
		const lossVals = validEpochs.map((e) => e.loss!);
		const lossMean = lossVals.reduce((a, b) => a + b, 0) / lossVals.length;
		const lossStd =
			Math.sqrt(lossVals.reduce((s, v) => s + (v - lossMean) ** 2, 0) / lossVals.length) || 1;
		return paramKeys
			.map((k) => {
				const pairs = validEpochs
					.map((e) => [e.params![k], e.loss!] as [number, number])
					.filter(([x]) => typeof x === 'number' && !isNaN(x));
				if (pairs.length < 5) return { key: k, corr: 0 };
				const xs = pairs.map((p) => p[0]);
				const xMean = xs.reduce((a, b) => a + b, 0) / xs.length;
				const xStd = Math.sqrt(xs.reduce((s, v) => s + (v - xMean) ** 2, 0) / xs.length) || 1;
				const corr =
					pairs.reduce((s, [x, y]) => s + ((x - xMean) / xStd) * ((y - lossMean) / lossStd), 0) /
					pairs.length;
				return { key: k, corr };
			})
			.filter((p) => !isNaN(p.corr))
			.sort((a, b) => Math.abs(b.corr) - Math.abs(a.corr));
	});

	const S_W = 180;
	const S_H = 100;
	const S_PAD = { top: 8, right: 8, bottom: 20, left: 30 };

	function scatterX(pts: ScatterPt[], v: number): number {
		const xs = pts.map((p) => p.x);
		const mn = Math.min(...xs);
		const mx = Math.max(...xs);
		const range = mx === mn ? 1 : mx - mn;
		return S_PAD.left + ((v - mn) / range) * (S_W - S_PAD.left - S_PAD.right);
	}
	function scatterY(pts: ScatterPt[], v: number): number {
		const ys = pts.map((p) => p.y);
		const mn = Math.min(...ys);
		const mx = Math.max(...ys);
		const range = mx === mn ? 1 : mx - mn;
		return (
			S_PAD.top +
			(S_H - S_PAD.top - S_PAD.bottom) -
			((v - mn) / range) * (S_H - S_PAD.top - S_PAD.bottom)
		);
	}

	// Parameter search range: min / median / max per param across all epochs
	const paramRangeStats = $derived.by(() => {
		if (paramKeys.length === 0 || epochs.length < 3) return null;
		return paramKeys
			.map((k) => {
				const vals = epochs
					.filter((e) => e.params != null && e.params[k] != null && typeof e.params[k] === 'number')
					.map((e) => e.params![k] as number)
					.sort((a, b) => a - b);
				if (vals.length === 0) return null;
				const median = vals[Math.floor(vals.length / 2)];
				const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
				return { key: k, min: vals[0], max: vals[vals.length - 1], median, mean, n: vals.length };
			})
			.filter(Boolean) as {
			key: string;
			min: number;
			max: number;
			median: number;
			mean: number;
			n: number;
		}[];
	});

	// Running best: cumulative minimum loss per epoch (convergence step line)
	const runningBestLine = $derived.by(() => {
		if (clippedEpochs.length < 3) return null;
		const sorted = [...clippedEpochs].sort((a, b) => a.epoch - b.epoch);
		let best = Infinity;
		const pts: string[] = [];
		for (const e of sorted) {
			if ((e.loss ?? Infinity) < best) best = e.loss!;
			pts.push(`${toX(e.epoch).toFixed(1)},${toY(best).toFixed(1)}`);
		}
		return pts.join(' ');
	});

	// Epoch profit histogram
	const epochProfitHist = $derived.by(() => {
		const vals = epochs.filter((e) => e.profit_total != null).map((e) => e.profit_total! * 100);
		if (vals.length < 5) return null;
		const mn = Math.floor(Math.min(...vals) / 5) * 5;
		const mx = Math.ceil(Math.max(...vals) / 5) * 5;
		const BINS = 16;
		const step = Math.max(0.5, (mx - mn) / BINS);
		const buckets = Array.from({ length: BINS }, (_, i) => ({ lo: mn + i * step, count: 0 }));
		for (const v of vals) {
			const idx = Math.min(BINS - 1, Math.max(0, Math.floor((v - mn) / step)));
			buckets[idx].count++;
		}
		const maxCount = Math.max(1, ...buckets.map((b) => b.count));
		const W = 560,
			H = 70;
		const bw = W / BINS;
		const zeroX = Math.max(0, Math.min(W, ((0 - mn) / (mx - mn || 1)) * W));
		const bestVal = epochs.find((e) => e.is_best)?.profit_total;
		const bestX =
			bestVal != null
				? Math.max(0, Math.min(W, ((bestVal * 100 - mn) / (mx - mn || 1)) * W))
				: null;
		return { buckets, maxCount, W, H, bw, zeroX, bestX, mn, mx, step, total: vals.length };
	});

	// Loss vs profit scatter
	const lossVsProfitScatter = $derived.by(() => {
		const pts = epochs.filter(
			(e) => e.loss != null && e.profit_total != null && e.loss <= CLIP_LOSS
		);
		if (pts.length < 5) return null;
		const losses = pts.map((e) => e.loss!);
		const profits = pts.map((e) => e.profit_total!);
		const lMin = Math.min(...losses),
			lMax = Math.max(...losses);
		const pMin = Math.min(...profits) * 1.05,
			pMax = Math.max(...profits) * 1.05;
		const W = 560,
			H = 120,
			PAD = 8;
		const toX = (l: number) => PAD + ((l - lMin) / (lMax - lMin || 1)) * (W - PAD * 2);
		const toY = (p: number) => H - PAD - ((p - pMin) / (pMax - pMin || 1)) * (H - PAD * 2);
		const zeroY = toY(0);
		const dots = pts.map((e) => ({
			x: toX(e.loss!),
			y: toY(e.profit_total!),
			best: e.is_best ?? false,
			tip: `epoch ${e.epoch} · loss ${e.loss!.toFixed(4)} · profit ${(e.profit_total! * 100).toFixed(1)}%`
		}));
		return { dots, W, H, PAD, zeroY, lMin, lMax, pMin, pMax };
	});

	// Best profit discovery curve — running-best profit at each epoch
	const bestProfitCurve = $derived.by(() => {
		const sorted = [...epochs]
			.filter((e) => e.profit_total != null)
			.sort((a, b) => a.epoch - b.epoch);
		if (sorted.length < 5) return null;
		let runBest = -Infinity;
		const pts: { epoch: number; best: number }[] = [];
		for (const e of sorted) {
			if (e.profit_total! > runBest) runBest = e.profit_total!;
			pts.push({ epoch: e.epoch, best: runBest });
		}
		const eMin = pts[0].epoch,
			eMax = pts[pts.length - 1].epoch;
		const pMin = Math.min(0, ...pts.map((p) => p.best));
		const pMax = Math.max(0.001, ...pts.map((p) => p.best));
		const W = 560,
			H = 80,
			PAD = 8;
		const toX = (e: number) => PAD + ((e - eMin) / Math.max(1, eMax - eMin)) * (W - PAD * 2);
		const toY = (p: number) =>
			H - PAD - ((p - pMin) / Math.max(0.0001, pMax - pMin)) * (H - PAD * 2);
		const polyline = pts
			.map((p) => `${toX(p.epoch).toFixed(1)},${toY(p.best).toFixed(1)}`)
			.join(' ');
		const zeroY = toY(0);
		const finalBest = pts[pts.length - 1].best;
		const firstJump = pts.find((p) => p.best > pMin + (pMax - pMin) * 0.5);
		const earlyDiscovery = firstJump
			? (firstJump.epoch - eMin) / Math.max(1, eMax - eMin) < 0.3
			: false;
		return {
			polyline,
			W,
			H,
			PAD,
			zeroY,
			pMin,
			pMax,
			eMin,
			eMax,
			finalBest,
			earlyDiscovery,
			total: pts.length
		};
	});

	// Epoch batch profitability: 20-epoch windows, what % are profitable
	const epochBatchProfitability = $derived.by(() => {
		const sorted = [...epochs]
			.filter((e) => e.profit_total != null)
			.sort((a, b) => a.epoch - b.epoch);
		if (sorted.length < 20) return null;
		const BATCH = 20;
		const batches: { label: string; pct: number; count: number }[] = [];
		for (let i = 0; i + BATCH <= sorted.length; i += BATCH) {
			const slice = sorted.slice(i, i + BATCH);
			const profitable = slice.filter((e) => (e.profit_total ?? 0) > 0).length;
			batches.push({
				label: `${slice[0].epoch}-${slice[slice.length - 1].epoch}`,
				pct: profitable / BATCH,
				count: BATCH
			});
		}
		if (batches.length < 2) return null;
		const W = 560,
			H = 70,
			PAD = 6;
		const toX = (i: number) => PAD + (i / Math.max(1, batches.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - v * (H - PAD * 2);
		const polyline = batches
			.map((b, i) => `${toX(i).toFixed(1)},${toY(b.pct).toFixed(1)}`)
			.join(' ');
		const fiftyY = toY(0.5);
		const avg = batches.reduce((s, b) => s + b.pct, 0) / batches.length;
		return { batches, polyline, W, H, PAD, fiftyY, avg };
	});

	// Cross-strategy best epoch comparison
	// Winrate vs trade count scatter for current strategy epochs
	const winrateTradeScatter = $derived.by(() => {
		const pts = epochs.filter(
			(e) => e.winrate != null && e.total_trades != null && e.total_trades > 0
		);
		if (pts.length < 6) return null;
		const xs = pts.map((e) => e.total_trades!);
		const ys = pts.map((e) => e.winrate! * 100);
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
		const dots = pts.map((e) => ({
			x: toX(e.total_trades!),
			y: toY(e.winrate! * 100),
			wr: e.winrate! * 100,
			trades: e.total_trades!,
			profit: e.profit_total,
			best: e.is_best
		}));
		return { dots, W, H, PAD, fiftyY, xMin, xMax, yMin, yMax };
	});

	// Drawdown distribution across all epochs for current strategy
	const drawdownDistribution = $derived.by(() => {
		const vals = epochs
			.filter((e) => e.max_drawdown != null && e.max_drawdown >= 0)
			.map((e) => e.max_drawdown! * 100);
		if (vals.length < 5) return null;
		const BUCKETS = [
			{ label: '<5%', lo: 0, hi: 5, count: 0, color: 'var(--ch-profit)' },
			{ label: '5–15%', lo: 5, hi: 15, count: 0, color: 'var(--ch-profit-light)' },
			{ label: '15–25%', lo: 15, hi: 25, count: 0, color: 'var(--ch-warn-light)' },
			{ label: '25–40%', lo: 25, hi: 40, count: 0, color: 'var(--ch-loss-light)' },
			{ label: '40%+', lo: 40, hi: Infinity, count: 0, color: 'var(--ch-loss)' }
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

	// Trade count vs profit scatter: does running more trades per epoch yield better profit?
	const tradeCountVsProfit = $derived.by(() => {
		const pts = epochs.filter(
			(e) => e.total_trades != null && e.total_trades > 0 && e.profit_total != null
		);
		if (pts.length < 8) return null;
		const xs = pts.map((e) => e.total_trades!);
		const ys = pts.map((e) => e.profit_total! * 100);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, 0.001);
		const W = 520,
			H = 110,
			PAD = 20;
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin || 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin || 0.001)) * (H - PAD * 2);
		const zeroY = toY(0);
		const dots = pts.map((e) => ({
			x: toX(e.total_trades!),
			y: toY(e.profit_total! * 100),
			profit: e.profit_total! * 100,
			trades: e.total_trades!,
			isBest: e.is_best ?? false
		}));
		const corr = (() => {
			const n = xs.length;
			const mx = xs.reduce((a, b) => a + b, 0) / n;
			const my = ys.reduce((a, b) => a + b, 0) / n;
			const num = xs.reduce((s, x, i) => s + (x - mx) * (ys[i] - my), 0);
			const den = Math.sqrt(
				xs.reduce((s, x) => s + (x - mx) ** 2, 0) * ys.reduce((s, y) => s + (y - my) ** 2, 0)
			);
			return den === 0 ? 0 : num / den;
		})();
		return { dots, W, H, PAD, zeroY, xMin, xMax, yMin, yMax, corr };
	});

	// Epoch loss convergence: cumulative best loss per epoch to show optimization speed
	const epochLossConvergence = $derived.by(() => {
		const valid = epochs.filter((e) => e.loss != null && isFinite(e.loss) && e.loss < 1e6);
		if (valid.length < 8) return null;
		const W = 520,
			H = 80,
			PAD = 8;
		let best = valid[0].loss!;
		const pts: { i: number; best: number }[] = [];
		for (let i = 0; i < valid.length; i++) {
			if (valid[i].loss! < best) best = valid[i].loss!;
			pts.push({ i, best });
		}
		const vMin = Math.min(...pts.map((p) => p.best));
		const vMax = Math.max(...pts.map((p) => p.best), vMin + 0.001);
		const toX = (i: number) => PAD + (i / Math.max(1, pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - vMin) / (vMax - vMin)) * (H - PAD * 2);
		const polyline = pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.best).toFixed(1)}`).join(' ');
		const bestEpoch = pts.findIndex((p) => p.best === vMin) + 1;
		return { polyline, W, H, PAD, vMin, vMax, total: pts.length, bestEpoch };
	});

	// Avg holding hours vs profit scatter: do longer-held epochs perform better?
	// Win rate bucket profit: avg profit per WR bucket to see if higher WR = higher profit
	const winrateBucketProfit = $derived.by(() => {
		const pts = epochs.filter((e) => e.winrate != null && e.profit_total != null);
		if (pts.length < 8) return null;
		const BUCKETS = [
			{ label: '<40%', lo: 0, hi: 40 },
			{ label: '40–50%', lo: 40, hi: 50 },
			{ label: '50–60%', lo: 50, hi: 60 },
			{ label: '60–70%', lo: 60, hi: 70 },
			{ label: '70%+', lo: 70, hi: 101 }
		];
		const rows = BUCKETS.map((b) => {
			const bucket = pts.filter((e) => e.winrate! * 100 >= b.lo && e.winrate! * 100 < b.hi);
			if (bucket.length === 0) return { ...b, count: 0, avgProfit: null };
			const avg = bucket.reduce((s, e) => s + e.profit_total!, 0) / bucket.length;
			return { ...b, count: bucket.length, avgProfit: avg };
		}).filter((r) => r.count > 0);
		if (rows.length < 2) return null;
		const maxAbsProfit = Math.max(0.001, ...rows.map((r) => Math.abs(r.avgProfit ?? 0)));
		return rows.map((r) => ({
			...r,
			barPct: r.avgProfit != null ? (Math.abs(r.avgProfit) / maxAbsProfit) * 100 : 0
		}));
	});

	const holdingVsProfit = $derived.by(() => {
		const pts = epochs.filter(
			(e) => e.holding_avg_hours != null && e.holding_avg_hours > 0 && e.profit_total != null
		);
		if (pts.length < 6) return null;
		const xs = pts.map((e) => e.holding_avg_hours!);
		const ys = pts.map((e) => e.profit_total!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, 0.001);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, 0.001);
		const W = 520,
			H = 110,
			PAD = 20;
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin || 0.001)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin || 0.001)) * (H - PAD * 2);
		const zeroY = toY(0);
		const n = xs.length;
		const mx = xs.reduce((a, b) => a + b, 0) / n,
			my = ys.reduce((a, b) => a + b, 0) / n;
		const num = xs.reduce((s, x, i) => s + (x - mx) * (ys[i] - my), 0);
		const den = Math.sqrt(
			xs.reduce((s, x) => s + (x - mx) ** 2, 0) * ys.reduce((s, y) => s + (y - my) ** 2, 0)
		);
		const corr = den === 0 ? 0 : num / den;
		const dots = pts.map((e) => ({
			x: toX(e.holding_avg_hours!),
			y: toY(e.profit_total!),
			hours: e.holding_avg_hours!,
			profit: e.profit_total!,
			isBest: e.is_best ?? false
		}));
		return { dots, W, H, PAD, zeroY, xMin, xMax, corr };
	});

	// Best-epoch param comparison: median param value in best epochs vs all epochs
	const bestEpochParamComparison = $derived.by(() => {
		const bestEpochs = epochs.filter((e) => e.is_best && e.params);
		if (paramKeys.length === 0 || bestEpochs.length < 2 || epochs.length < 5) return null;
		const rows = paramKeys
			.slice(0, 6)
			.map((k) => {
				const allVals = epochs
					.filter((e) => e.params?.[k] != null)
					.map((e) => e.params![k] as number)
					.sort((a, b) => a - b);
				const bestVals = bestEpochs
					.filter((e) => e.params?.[k] != null)
					.map((e) => e.params![k] as number)
					.sort((a, b) => a - b);
				if (allVals.length < 2) return null;
				const allMed = allVals[Math.floor(allVals.length / 2)];
				const bestMed = bestVals.length ? bestVals[Math.floor(bestVals.length / 2)] : null;
				const range = allVals[allVals.length - 1] - allVals[0] || 0.001;
				return {
					key: k,
					allMed,
					bestMed,
					min: allVals[0],
					max: allVals[allVals.length - 1],
					range
				};
			})
			.filter((r): r is NonNullable<typeof r> => r !== null);
		if (rows.length < 1) return null;
		return rows;
	});

	// Drawdown vs profit scatter: risk/reward map of all epochs explored by optimizer
	const epochDrawdownProfile = $derived.by(() => {
		const pts = epochs.filter(
			(e) => e.max_drawdown != null && e.max_drawdown >= 0 && e.profit_total != null
		);
		if (pts.length < 8) return null;
		const xs = pts.map((e) => e.max_drawdown! * 100);
		const ys = pts.map((e) => e.profit_total!);
		const xMax = Math.max(...xs, 0.001);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, 0.001);
		const W = 520,
			H = 120,
			PAD = 20;
		const toX = (v: number) => PAD + (v / xMax) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin || 0.001)) * (H - PAD * 2);
		const zeroY = toY(0);
		const n = xs.length;
		const mx = xs.reduce((a, b) => a + b, 0) / n,
			my = ys.reduce((a, b) => a + b, 0) / n;
		const num = xs.reduce((s, x, i) => s + (x - mx) * (ys[i] - my), 0);
		const den = Math.sqrt(
			xs.reduce((s, x) => s + (x - mx) ** 2, 0) * ys.reduce((s, y) => s + (y - my) ** 2, 0)
		);
		const corr = den === 0 ? 0 : num / den;
		const dots = pts.map((e) => ({
			x: toX(e.max_drawdown! * 100),
			y: toY(e.profit_total!),
			dd: e.max_drawdown! * 100,
			profit: e.profit_total!,
			isBest: e.is_best ?? false
		}));
		return { dots, W, H, PAD, zeroY, xMax, corr };
	});

	// Sortino bucket avg profit: does higher sortino correlate with higher profit?
	const epochSortinoBuckets = $derived.by(() => {
		const pts = epochs.filter(
			(e) =>
				e.sortino != null &&
				isFinite(e.sortino!) &&
				e.sortino! > -20 &&
				e.sortino! < 100 &&
				e.profit_total != null
		);
		if (pts.length < 8) return null;
		const BUCKETS = [
			{ label: '<0', lo: -Infinity, hi: 0, vals: [] as number[] },
			{ label: '0–1', lo: 0, hi: 1, vals: [] as number[] },
			{ label: '1–3', lo: 1, hi: 3, vals: [] as number[] },
			{ label: '3–6', lo: 3, hi: 6, vals: [] as number[] },
			{ label: '6+', lo: 6, hi: Infinity, vals: [] as number[] }
		];
		for (const e of pts) {
			const b = BUCKETS.find((bk) => e.sortino! >= bk.lo && e.sortino! < bk.hi);
			if (b) b.vals.push(e.profit_total!);
		}
		const rows = BUCKETS.map((b) => ({
			label: b.label,
			count: b.vals.length,
			avg: b.vals.length ? b.vals.reduce((a, x) => a + x, 0) / b.vals.length : null
		})).filter((r) => r.count > 0);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(0.001, ...rows.map((r) => Math.abs(r.avg ?? 0)));
		return rows.map((r) => ({
			...r,
			barPct: r.avg != null ? (Math.abs(r.avg) / maxAbs) * 100 : 0
		}));
	});

	// SQN vs profit scatter: System Quality Number as predictor of epoch profitability
	const sqnVsProfit = $derived.by(() => {
		const pts = epochs.filter(
			(e) =>
				e.sqn != null && isFinite(e.sqn!) && e.sqn! > -20 && e.sqn! < 50 && e.profit_total != null
		);
		if (pts.length < 8) return null;
		const xs = pts.map((e) => e.sqn!);
		const ys = pts.map((e) => e.profit_total!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 0.01);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, 0.001);
		const W = 520,
			H = 110,
			PAD = 20;
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin || 0.001)) * (H - PAD * 2);
		const zeroY = toY(0);
		const n = xs.length;
		const mx = xs.reduce((a, b) => a + b, 0) / n,
			my = ys.reduce((a, b) => a + b, 0) / n;
		const num = xs.reduce((s, x, i) => s + (x - mx) * (ys[i] - my), 0);
		const den = Math.sqrt(
			xs.reduce((s, x) => s + (x - mx) ** 2, 0) * ys.reduce((s, y) => s + (y - my) ** 2, 0)
		);
		const corr = den === 0 ? 0 : num / den;
		const dots = pts.map((e) => ({
			x: toX(e.sqn!),
			y: toY(e.profit_total!),
			sqn: e.sqn!,
			profit: e.profit_total!,
			isBest: e.is_best ?? false
		}));
		return { dots, W, H, PAD, zeroY, xMin, xMax, corr };
	});

	const crossStrategyBest = $derived.by(() => {
		if (strategies.length < 2) return null;
		return strategies.map((s) => {
			const eps = data.byStrategy[s] ?? [];
			const best = eps
				.filter((e) => e.loss != null)
				.reduce<(typeof eps)[0] | null>(
					(a, b) => (a == null || (b.loss ?? Infinity) < (a.loss ?? Infinity) ? b : a),
					null
				);
			const totalEpochs = eps.length;
			const bestEpochNum = eps.findIndex((e) => e.is_best) + 1 || null;
			return { strategy: s, best, totalEpochs, bestEpochNum };
		});
	});

	// Calmar buckets: avg profit_total per Calmar range — do higher Calmar epochs profit more?
	const calmarBuckets = $derived.by(() => {
		const pts = epochs.filter(
			(e) =>
				e.calmar != null &&
				isFinite(e.calmar!) &&
				e.calmar! > -50 &&
				e.calmar! < 200 &&
				e.profit_total != null
		);
		if (pts.length < 10) return null;
		const BUCKETS = [
			{ lo: -Infinity, hi: 0, label: '<0' },
			{ lo: 0, hi: 0.5, label: '0–0.5' },
			{ lo: 0.5, hi: 1, label: '0.5–1' },
			{ lo: 1, hi: 2, label: '1–2' },
			{ lo: 2, hi: 5, label: '2–5' },
			{ lo: 5, hi: Infinity, label: '>5' }
		].map((b) => ({ ...b, profits: [] as number[] }));
		for (const e of pts) {
			const b = BUCKETS.find((bk) => e.calmar! >= bk.lo && e.calmar! < bk.hi);
			if (b) b.profits.push(e.profit_total!);
		}
		const rows = BUCKETS.map((b) => ({
			label: b.label,
			count: b.profits.length,
			avg: b.profits.length ? b.profits.reduce((a, v) => a + v, 0) / b.profits.length : null
		})).filter((r) => r.count > 0);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(0.001, ...rows.map((r) => Math.abs(r.avg ?? 0)));
		return rows.map((r) => ({
			...r,
			barPct: r.avg != null ? (Math.abs(r.avg) / maxAbs) * 100 : 0
		}));
	});

	const epochSqnTimeline = $derived.by(() => {
		const valid = epochs
			.filter((e) => e.sqn != null && isFinite(e.sqn!) && e.sqn! > -20 && e.sqn! < 50)
			.sort((a, b) => a.epoch - b.epoch);
		if (valid.length < 12) return null;
		const WINDOW = 10;
		const pts: { epoch: number; avg: number }[] = [];
		for (let i = WINDOW - 1; i < valid.length; i++) {
			const slice = valid.slice(i - WINDOW + 1, i + 1);
			const avg = slice.reduce((s, e) => s + e.sqn!, 0) / slice.length;
			pts.push({ epoch: valid[i].epoch, avg });
		}
		if (pts.length < 4) return null;
		const W = 560,
			H = 64,
			PAD = 8;
		const avgs = pts.map((p) => p.avg);
		const mn = Math.min(...avgs),
			mx = Math.max(...avgs, mn + 0.1);
		const toX = (i: number) => PAD + (i / Math.max(1, pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / (mx - mn)) * (H - PAD * 2);
		const zeroY = mn < 0 ? toY(0) : H - PAD;
		const polyline = pts.map((p, i) => `${toX(i).toFixed(1)},${toY(p.avg).toFixed(1)}`).join(' ');
		const trend = avgs[avgs.length - 1] - avgs[0];
		return { polyline, W, H, PAD, zeroY, mn, mx, trend, count: valid.length };
	});

	const epochDrawdownTrend = $derived.by(() => {
		const valid = epochs
			.filter((e) => e.max_drawdown != null && e.max_drawdown >= 0)
			.sort((a, b) => a.epoch - b.epoch);
		if (valid.length < 12) return null;
		const WINDOW = 10;
		const pts: { epoch: number; avg: number }[] = [];
		for (let i = WINDOW - 1; i < valid.length; i++) {
			const slice = valid.slice(i - WINDOW + 1, i + 1);
			const avg = slice.reduce((s, e) => s + e.max_drawdown! * 100, 0) / slice.length;
			pts.push({ epoch: valid[i].epoch, avg });
		}
		if (pts.length < 4) return null;
		const W = 560,
			H = 64,
			PAD = 8;
		const avgs = pts.map((p) => p.avg);
		const mn = Math.min(...avgs),
			mx = Math.max(...avgs, mn + 0.1);
		const toX = (i: number) => PAD + (i / Math.max(1, pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / (mx - mn)) * (H - PAD * 2);
		const polyline = pts.map((p, i) => `${toX(i).toFixed(1)},${toY(p.avg).toFixed(1)}`).join(' ');
		const trend = avgs[avgs.length - 1] - avgs[0];
		return { polyline, W, H, PAD, mn, mx, trend, count: valid.length };
	});

	// Sortino vs Calmar scatter: do epochs with higher Sortino also achieve higher Calmar?
	const epochSortinoCalmarScatter = $derived.by(() => {
		const pts = epochs.filter(
			(e) =>
				e.sortino != null &&
				isFinite(e.sortino!) &&
				e.sortino! > -20 &&
				e.sortino! < 100 &&
				e.calmar != null &&
				isFinite(e.calmar!) &&
				e.calmar! > -50 &&
				e.calmar! < 200 &&
				e.profit_total != null
		);
		if (pts.length < 8) return null;
		const xs = pts.map((e) => e.sortino!);
		const ys = pts.map((e) => e.calmar!);
		const profits = pts.map((e) => e.profit_total!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 0.01);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.01);
		const pMin = Math.min(...profits),
			pMax = Math.max(...profits, pMin + 0.001);
		const W = 520,
			H = 120,
			PAD = 20;
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const n = xs.length;
		const mx = xs.reduce((a, b) => a + b, 0) / n,
			my = ys.reduce((a, b) => a + b, 0) / n;
		const num = xs.reduce((s, x, i) => s + (x - mx) * (ys[i] - my), 0);
		const den = Math.sqrt(
			xs.reduce((s, x) => s + (x - mx) ** 2, 0) * ys.reduce((s, y) => s + (y - my) ** 2, 0)
		);
		const corr = den === 0 ? 0 : num / den;
		const zeroX = xMin < 0 ? toX(0) : null;
		const zeroY = yMin < 0 ? toY(0) : null;
		const colorFor = (p: number) => {
			const t = Math.max(0, Math.min(1, (p - pMin) / (pMax - pMin || 0.001)));
			if (t > 0.66) return 'var(--ch-profit)';
			if (t > 0.33) return 'var(--ch-warn)';
			return 'var(--ch-loss)';
		};
		const dots = pts.map((e) => ({
			x: toX(e.sortino!),
			y: toY(e.calmar!),
			sortino: e.sortino!,
			calmar: e.calmar!,
			color: colorFor(e.profit_total!),
			isBest: e.is_best ?? false
		}));
		return { dots, W, H, PAD, xMin, xMax, yMin, yMax, corr, zeroX, zeroY };
	});

	// Rolling 10-epoch avg win rate trend (distinct from epochSqnTimeline/epochDrawdownTrend and winrateBucketProfit static analysis)
	const epochWinrateTrend = $derived.by(() => {
		const valid = [...epochs].filter((e) => e.winrate != null).sort((a, b) => a.epoch - b.epoch);
		if (valid.length < 12) return null;
		const WINDOW = 10;
		const pts: { epoch: number; avg: number }[] = [];
		for (let i = WINDOW - 1; i < valid.length; i++) {
			const slice = valid.slice(i - WINDOW + 1, i + 1);
			const avg = slice.reduce((s, e) => s + e.winrate!, 0) / WINDOW;
			pts.push({ epoch: valid[i].epoch, avg });
		}
		const vals = pts.map((p) => p.avg);
		const mn = Math.min(...vals),
			mx = Math.max(...vals, mn + 0.001);
		const W = 560,
			H = 64,
			PAD = 6;
		const toX = (i: number) => PAD + (i / Math.max(1, pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / (mx - mn)) * (H - PAD * 2);
		const fiftyY = mn < 0.5 && mx > 0.5 ? toY(0.5) : null;
		const polyline = pts.map((p, i) => `${toX(i).toFixed(1)},${toY(p.avg).toFixed(1)}`).join(' ');
		const trend = vals[vals.length - 1] - vals[0];
		const latest = vals[vals.length - 1];
		return { polyline, W, H, PAD, mn, mx, fiftyY, trend, latest, count: pts.length };
	});

	const holdingTimeHistogram = $derived.by(() => {
		const vals = epochs
			.filter(
				(e) =>
					e.holding_avg_hours != null && isFinite(e.holding_avg_hours) && e.holding_avg_hours > 0
			)
			.map((e) => e.holding_avg_hours!);
		if (vals.length < 10) return null;
		const maxH = Math.max(...vals);
		const step = maxH / 8;
		const buckets = Array.from({ length: 8 }, (_, i) => ({
			label:
				i === 7
					? `>${(step * i).toFixed(0)}h`
					: `${(step * i).toFixed(0)}–${(step * (i + 1)).toFixed(0)}h`,
			lo: step * i,
			hi: step * (i + 1),
			count: 0
		}));
		for (const v of vals) {
			const idx = Math.min(7, Math.floor(v / step));
			buckets[idx].count++;
		}
		const maxCount = Math.max(1, ...buckets.map((b) => b.count));
		return buckets.map((b) => ({ ...b, barPct: (b.count / maxCount) * 100 }));
	});

	const epochExplorationDensity = $derived.by(() => {
		if (epochs.length < 20) return null;
		const windowSize = 20;
		const windows: { label: string; unique: number; total: number }[] = [];
		for (let i = 0; i + windowSize <= epochs.length; i += windowSize) {
			const slice = epochs.slice(i, i + windowSize);
			const seen = new Set(slice.map((e) => JSON.stringify(e.params ?? {})));
			windows.push({ label: `${i + 1}–${i + windowSize}`, unique: seen.size, total: slice.length });
		}
		if (windows.length < 2) return null;
		const maxUniq = Math.max(1, ...windows.map((w) => w.unique));
		return windows.map((w) => ({
			...w,
			barPct: (w.unique / maxUniq) * 100,
			diversity: w.unique / w.total
		}));
	});

	const epochBestEverTimeline = $derived.by(() => {
		const vals = epochs
			.map((e) => e.profit_total ?? null)
			.filter((v): v is number => v != null && isFinite(v));
		if (vals.length < 10) return null;
		let best = -Infinity;
		const running = vals.map((v) => {
			if (v > best) best = v;
			return best;
		});
		const mn = running[0],
			mx = running[running.length - 1];
		const range = mx - mn || 1;
		const W = 400,
			H = 60,
			PAD = 6;
		const toX = (i: number) => PAD + (i / Math.max(1, running.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / range) * (H - PAD * 2);
		const poly = running.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
		const finalBest = running[running.length - 1];
		const halfIdx = Math.floor(running.length / 2);
		const halfBest = running[halfIdx];
		const lateGain = finalBest - halfBest;
		return { poly, W, H, PAD, mn, mx: finalBest, lateGain };
	});

	const epochCalmarDistribution = $derived.by(() => {
		const vals = epochs
			.filter((e) => e.calmar != null && isFinite(e.calmar) && e.calmar > 0 && e.calmar < 20)
			.map((e) => e.calmar!);
		if (vals.length < 10) return null;
		const BINS = 8,
			mx = Math.max(...vals);
		const step = mx / BINS;
		const buckets = Array.from({ length: BINS }, (_, i) => ({
			label: `${(i * step).toFixed(1)}–${((i + 1) * step).toFixed(1)}`,
			count: 0
		}));
		for (const v of vals) {
			const idx = Math.min(BINS - 1, Math.floor(v / step));
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

	const epochHoldingTimeProfile = $derived.by(() => {
		const vals = epochs
			.filter(
				(e) =>
					e.holding_avg_hours != null &&
					isFinite(e.holding_avg_hours) &&
					e.holding_avg_hours > 0 &&
					e.holding_avg_hours < 2000
			)
			.map((e) => e.holding_avg_hours!);
		if (vals.length < 10) return null;
		const mn = Math.min(...vals),
			mx = Math.max(...vals);
		const range = mx - mn || 1;
		const BINS = 8;
		const step = range / BINS;
		const buckets = Array.from({ length: BINS }, (_, i) => ({
			lo: mn + i * step,
			hi: mn + (i + 1) * step,
			count: 0,
			label: `${(mn + i * step).toFixed(0)}h`
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

	const epochProfitVsDrawdown = $derived.by(() => {
		const pts = epochs.filter(
			(e) =>
				e.profit_total != null &&
				e.max_drawdown != null &&
				isFinite(e.profit_total) &&
				isFinite(e.max_drawdown) &&
				e.max_drawdown >= 0 &&
				e.max_drawdown < 1
		);
		if (pts.length < 10) return null;
		const W = 360,
			H = 80,
			PAD = 8;
		const xs = pts.map((e) => e.max_drawdown!),
			ys = pts.map((e) => e.profit_total!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 0.001);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.001);
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const dots = pts.map((e) => ({
			cx: toX(e.max_drawdown!),
			cy: toY(e.profit_total!),
			best: e.is_best === true,
			pos: e.profit_total! > 0
		}));
		return { dots, W, H, PAD, xMin, xMax, yMin, yMax };
	});

	const epochWinrateSqnScatter = $derived.by(() => {
		const pts = epochs.filter(
			(e) =>
				e.winrate != null &&
				e.sqn != null &&
				isFinite(e.winrate) &&
				isFinite(e.sqn) &&
				e.sqn > -10 &&
				e.sqn < 10 &&
				e.winrate >= 0 &&
				e.winrate <= 1
		);
		if (pts.length < 10) return null;
		const W = 360,
			H = 80,
			PAD = 8;
		const xs = pts.map((e) => e.winrate!),
			ys = pts.map((e) => e.sqn!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs, xMin + 0.01);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys, yMin + 0.01);
		const toX = (v: number) => PAD + ((v - xMin) / (xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - PAD * 2);
		const dots = pts.map((e) => ({
			cx: toX(e.winrate!),
			cy: toY(e.sqn!),
			best: e.is_best === true,
			pos: e.sqn! >= 0
		}));
		return { dots, W, H, PAD, xMin, xMax, yMin, yMax };
	});

	const epochSqnDistribution = $derived.by(() => {
		const vals = epochs
			.filter((e) => e.sqn != null && isFinite(e.sqn) && e.sqn > -10 && e.sqn < 10)
			.map((e) => e.sqn!);
		if (vals.length < 10) return null;
		const mn = Math.min(...vals),
			mx = Math.max(...vals);
		const range = mx - mn || 1;
		const BINS = 8;
		const step = range / BINS;
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

	const epochBestCalmarTimeline = $derived.by(() => {
		const valid = epochs.filter(
			(e) => e.calmar != null && isFinite(e.calmar) && e.calmar > -50 && e.calmar < 200
		);
		if (valid.length < 10) return null;
		let bestSoFar = -Infinity;
		const pts: number[] = [];
		for (const e of valid) {
			if (e.calmar! > bestSoFar) bestSoFar = e.calmar!;
			pts.push(bestSoFar);
		}
		const mn = pts[0],
			mx = pts[pts.length - 1];
		const range = mx - mn || 1;
		const W = 360,
			H = 60,
			PAD = 6;
		const toX = (i: number) => PAD + (i / Math.max(1, pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / range) * (H - PAD * 2);
		const poly = pts.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
		return { poly, W, H, PAD, mn, mx, positive: mx > 0, total: valid.length };
	});

	const epochProfitDistribution = $derived.by(() => {
		const vals = epochs
			.filter(
				(e) =>
					e.profit_total != null &&
					isFinite(e.profit_total) &&
					e.profit_total > -500 &&
					e.profit_total < 500
			)
			.map((e) => e.profit_total!);
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

	const epochWinrateDistribution = $derived.by(() => {
		const vals = epochs
			.filter((e) => e.winrate != null && isFinite(e.winrate) && e.winrate >= 0 && e.winrate <= 1)
			.map((e) => e.winrate! * 100);
		if (vals.length < 10) return null;
		const BINS = 8,
			step = 100 / BINS;
		const buckets = Array.from({ length: BINS }, (_, i) => ({
			lo: i * step,
			hi: (i + 1) * step,
			label: `${(i * step).toFixed(0)}%`,
			count: 0
		}));
		for (const v of vals) {
			const idx = Math.min(BINS - 1, Math.floor(v / step));
			buckets[idx].count++;
		}
		const maxCount = Math.max(1, ...buckets.map((b) => b.count));
		const sorted = [...vals].sort((a, b) => a - b);
		const median = sorted[Math.floor(sorted.length / 2)];
		const above50 = vals.filter((v) => v >= 50).length;
		return {
			buckets: buckets.map((b) => ({ ...b, barPct: (b.count / maxCount) * 100, good: b.lo >= 50 })),
			median,
			total: vals.length,
			above50
		};
	});

	const epochCalmarVsHolding = $derived.by(() => {
		const pts = epochs.filter(
			(e) =>
				e.calmar != null &&
				isFinite(e.calmar) &&
				e.calmar > -20 &&
				e.calmar < 100 &&
				e.holding_avg_hours != null &&
				isFinite(e.holding_avg_hours) &&
				e.holding_avg_hours > 0 &&
				e.holding_avg_hours < 10000
		);
		if (pts.length < 10) return null;
		const xs = pts.map((p) => Math.log1p(p.holding_avg_hours!));
		const ys = pts.map((p) => p.calmar!);
		const xMin = Math.min(...xs),
			xMax = Math.max(...xs);
		const yMin = Math.min(...ys),
			yMax = Math.max(...ys);
		const W = 400,
			H = 100,
			PAD = 12;
		const toX = (v: number) => PAD + ((v - xMin) / Math.max(0.01, xMax - xMin)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - yMin) / Math.max(0.01, yMax - yMin)) * (H - PAD * 2);
		const zero_y = toY(0);
		const dots = pts.map((p) => ({
			cx: toX(Math.log1p(p.holding_avg_hours!)),
			cy: toY(p.calmar!),
			best: p.is_best === true,
			positive: p.calmar! > 0,
			hours: p.holding_avg_hours!,
			calmar: p.calmar!
		}));
		const hMin = Math.exp(xMin) - 1,
			hMax = Math.exp(xMax) - 1;
		return { dots, W, H, PAD, zero_y, yMin, yMax, hMin, hMax };
	});

	const epochLossDistribution = $derived.by(() => {
		const best = epochs
			.filter((e) => e.is_best === true && e.loss != null && isFinite(e.loss!))
			.map((e) => e.loss!);
		const rest = epochs
			.filter((e) => e.is_best !== true && e.loss != null && isFinite(e.loss!))
			.map((e) => e.loss!);
		if (best.length < 3 || rest.length < 5) return null;
		const allVals = [...best, ...rest];
		const lo = Math.min(...allVals),
			hi = Math.max(...allVals);
		if (hi - lo < 0.001) return null;
		const BINS = 10;
		const step = (hi - lo) / BINS;
		const makeBuckets = (vals: number[]) =>
			Array.from({ length: BINS }, (_, i) => {
				const count = vals.filter(
					(v) => v >= lo + i * step && (i === BINS - 1 ? v <= hi : v < lo + (i + 1) * step)
				).length;
				return { label: (lo + i * step).toFixed(2), count };
			});
		const bestBuckets = makeBuckets(best);
		const restBuckets = makeBuckets(rest);
		const maxCount = Math.max(
			1,
			...bestBuckets.map((b) => b.count),
			...restBuckets.map((b) => b.count)
		);
		const avgBest = best.reduce((s, v) => s + v, 0) / best.length;
		const avgRest = rest.reduce((s, v) => s + v, 0) / rest.length;
		return {
			bestBuckets: bestBuckets.map((b) => ({ ...b, pct: (b.count / maxCount) * 100 })),
			restBuckets: restBuckets.map((b) => ({ ...b, pct: (b.count / maxCount) * 100 })),
			avgBest,
			avgRest,
			lo,
			hi,
			total: epochs.length
		};
	});

	const epochParamBestRanges = $derived.by(() => {
		const bestEpochs = epochs.filter((e) => e.is_best === true && e.params);
		const restEpochs = epochs.filter((e) => e.is_best !== true && e.params);
		if (bestEpochs.length < 3) return null;
		const allParams = [...new Set(bestEpochs.flatMap((e) => Object.keys(e.params ?? {})))];
		const numericParams = allParams
			.filter((p) => bestEpochs.some((e) => e.params && typeof e.params[p] === 'number'))
			.slice(0, 10);
		if (numericParams.length < 2) return null;
		const rows = numericParams
			.map((param) => {
				const bestVals = bestEpochs
					.map((e) => e.params?.[param])
					.filter((v): v is number => typeof v === 'number');
				const restVals = restEpochs
					.map((e) => e.params?.[param])
					.filter((v): v is number => typeof v === 'number');
				if (bestVals.length < 2) return null;
				const avgBest = bestVals.reduce((s, v) => s + v, 0) / bestVals.length;
				const avgRest =
					restVals.length > 0 ? restVals.reduce((s, v) => s + v, 0) / restVals.length : null;
				const minB = Math.min(...bestVals),
					maxB = Math.max(...bestVals);
				return { param, avgBest, avgRest, minB, maxB, n: bestVals.length };
			})
			.filter((r): r is NonNullable<typeof r> => r !== null);
		if (rows.length < 2) return null;
		return rows;
	});

	// Total trades distribution: best vs non-best epochs (median/p25/p75 summary)
	const epochTradeCountComparison = $derived.by(() => {
		function stats(arr: number[]) {
			if (arr.length === 0) return null;
			const s = [...arr].sort((a, b) => a - b);
			const med =
				s.length % 2
					? s[Math.floor(s.length / 2)]
					: (s[Math.floor(s.length / 2) - 1] + s[Math.floor(s.length / 2)]) / 2;
			const p25 = s[Math.floor(s.length * 0.25)];
			const p75 = s[Math.floor(s.length * 0.75)];
			return { med, p25, p75, min: s[0], max: s[s.length - 1], n: s.length };
		}
		const bestVals = epochs
			.filter((e) => e.is_best && e.total_trades != null && e.total_trades > 0)
			.map((e) => e.total_trades!);
		const restVals = epochs
			.filter((e) => !e.is_best && e.total_trades != null && e.total_trades > 0)
			.map((e) => e.total_trades!);
		if (bestVals.length < 3 || restVals.length < 3) return null;
		const best = stats(bestVals)!;
		const rest = stats(restVals)!;
		const maxVal = Math.max(best.max, rest.max, 1);
		return { best, rest, maxVal };
	});

	// Max drawdown distribution: best vs non-best epochs (IQR box style)
	const epochMaxDrawdownComparison = $derived.by(() => {
		function stats(arr: number[]) {
			if (arr.length < 2) return null;
			const s = [...arr].sort((a, b) => a - b);
			const med =
				s.length % 2
					? s[Math.floor(s.length / 2)]
					: (s[Math.floor(s.length / 2) - 1] + s[Math.floor(s.length / 2)]) / 2;
			return {
				med,
				p25: s[Math.floor(s.length * 0.25)],
				p75: s[Math.floor(s.length * 0.75)],
				min: s[0],
				max: s[s.length - 1],
				n: s.length
			};
		}
		const bestVals = epochs
			.filter((e) => e.is_best && e.max_drawdown != null && e.max_drawdown >= 0)
			.map((e) => e.max_drawdown!);
		const restVals = epochs
			.filter((e) => !e.is_best && e.max_drawdown != null && e.max_drawdown >= 0)
			.map((e) => e.max_drawdown!);
		if (bestVals.length < 3 || restVals.length < 3) return null;
		const best = stats(bestVals)!,
			rest = stats(restVals)!;
		if (!best || !rest) return null;
		const maxVal = Math.max(best.max, rest.max, 0.01);
		return { best, rest, maxVal };
	});

	const epochBestWinrateTimeline = $derived.by(() => {
		const sorted = [...epochs]
			.sort((a, b) => a.epoch - b.epoch)
			.filter((e) => e.winrate != null && isFinite(e.winrate));
		if (sorted.length < 5) return null;
		let bestSoFar = -Infinity;
		const pts = sorted.map((e) => {
			if (e.winrate! > bestSoFar) bestSoFar = e.winrate!;
			return { epoch: e.epoch, wr: e.winrate!, best: bestSoFar, isBest: e.is_best };
		});
		const W = 560,
			H = 72,
			PAD = 8;
		const maxWr = Math.max(0.01, ...pts.map((p) => p.best));
		const minWr = Math.min(...pts.map((p) => p.wr));
		const range = maxWr - minWr || 0.01;
		const toX = (i: number) => PAD + (i / Math.max(1, pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - minWr) / range) * (H - PAD * 2);
		const allPoly = pts.map((p, i) => `${toX(i).toFixed(1)},${toY(p.wr).toFixed(1)}`).join(' ');
		const bestPoly = pts.map((p, i) => `${toX(i).toFixed(1)},${toY(p.best).toFixed(1)}`).join(' ');
		const fiftyY = minWr < 0.5 && maxWr > 0.5 ? toY(0.5) : null;
		const finalBest = pts[pts.length - 1].best;
		return { W, H, allPoly, bestPoly, fiftyY, finalBest, total: pts.length };
	});

	const epochBestSortinoTimeline = $derived.by(() => {
		const sorted = [...epochs]
			.sort((a, b) => a.epoch - b.epoch)
			.filter(
				(e) => e.sortino != null && isFinite(e.sortino) && e.sortino > -100 && e.sortino < 500
			);
		if (sorted.length < 5) return null;
		let bestSoFar = -Infinity;
		const pts = sorted.map((e) => {
			if (e.sortino! > bestSoFar) bestSoFar = e.sortino!;
			return { epoch: e.epoch, sortino: e.sortino!, best: bestSoFar };
		});
		const W = 560,
			H = 72,
			PAD = 8;
		const allVals = pts.map((p) => p.sortino),
			bestVals = pts.map((p) => p.best);
		const mn = Math.min(...allVals),
			mx = Math.max(...bestVals, mn + 0.01);
		const range = mx - mn || 0.01;
		const toX = (i: number) => PAD + (i / Math.max(1, pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / range) * (H - PAD * 2);
		const allPoly = pts
			.map((p, i) => `${toX(i).toFixed(1)},${toY(p.sortino).toFixed(1)}`)
			.join(' ');
		const bestPoly = pts.map((p, i) => `${toX(i).toFixed(1)},${toY(p.best).toFixed(1)}`).join(' ');
		const zeroY = mn < 0 && mx > 0 ? toY(0) : null;
		const finalBest = pts[pts.length - 1].best;
		return { W, H, allPoly, bestPoly, zeroY, finalBest, total: pts.length };
	});

	const epochLossVsTradeCount = $derived.by(() => {
		const pts = epochs
			.filter(
				(e) =>
					e.loss != null &&
					isFinite(e.loss) &&
					Math.abs(e.loss) < 1e6 &&
					e.total_trades != null &&
					e.total_trades > 0
			)
			.map((e) => ({ loss: e.loss!, trades: e.total_trades!, best: e.is_best ?? false }));
		if (pts.length < 8) return null;
		const losses = pts.map((p) => p.loss),
			trades = pts.map((p) => p.trades);
		const lMin = Math.min(...losses),
			lMax = Math.max(...losses, lMin + 0.01);
		const tMin = Math.min(...trades),
			tMax = Math.max(...trades, tMin + 1);
		const W = 560,
			H = 140,
			PAD = 12;
		const toX = (t: number) => PAD + ((t - tMin) / (tMax - tMin)) * (W - PAD * 2);
		const toY = (l: number) => H - PAD - ((l - lMin) / (lMax - lMin)) * (H - PAD * 2);
		const dots = pts.map((p) => ({ cx: toX(p.trades), cy: toY(p.loss), best: p.best }));
		const zeroY = lMin < 0 && lMax > 0 ? toY(0) : null;
		return { W, H, dots, zeroY, lMin, lMax, tMin, tMax, total: pts.length };
	});

	const epochHoldingVsWinrate = $derived.by(() => {
		const pts = epochs
			.filter(
				(e) =>
					e.holding_avg_hours != null &&
					isFinite(e.holding_avg_hours) &&
					e.holding_avg_hours > 0 &&
					e.holding_avg_hours < 8760 &&
					e.winrate != null &&
					isFinite(e.winrate) &&
					e.winrate >= 0 &&
					e.winrate <= 1
			)
			.map((e) => ({ h: e.holding_avg_hours!, wr: e.winrate! * 100, best: e.is_best ?? false }));
		if (pts.length < 8) return null;
		const hMin = Math.min(...pts.map((p) => p.h)),
			hMax = Math.max(...pts.map((p) => p.h), hMin + 0.01);
		const wMin = Math.min(...pts.map((p) => p.wr)),
			wMax = Math.max(...pts.map((p) => p.wr), wMin + 1);
		const W = 560,
			H = 130,
			PAD = 10;
		const toX = (h: number) => PAD + ((h - hMin) / (hMax - hMin)) * (W - PAD * 2);
		const toY = (w: number) => H - PAD - ((w - wMin) / (wMax - wMin)) * (H - PAD * 2);
		const dots = pts.map((p) => ({ cx: toX(p.h), cy: toY(p.wr), best: p.best }));
		return {
			W,
			H,
			dots,
			hMin: hMin.toFixed(1),
			hMax: hMax.toFixed(1),
			wMin: wMin.toFixed(1),
			wMax: wMax.toFixed(1),
			total: pts.length
		};
	});

	const epochProfitPerTrade = $derived.by(() => {
		const pts = epochs
			.filter(
				(e) =>
					e.profit_total != null &&
					isFinite(e.profit_total) &&
					e.total_trades != null &&
					e.total_trades > 0
			)
			.map((e) => e.profit_total! / e.total_trades!)
			.filter((v) => isFinite(v) && v > -1 && v < 2);
		if (pts.length < 8) return null;
		const mn = Math.min(...pts),
			mx = Math.max(...pts, mn + 0.001);
		const bucketCount = 20;
		const step = (mx - mn) / bucketCount;
		const buckets = Array.from({ length: bucketCount }, (_, i) => ({
			lo: mn + i * step,
			hi: mn + (i + 1) * step,
			count: 0
		}));
		for (const v of pts) {
			const idx = Math.min(bucketCount - 1, Math.floor((v - mn) / step));
			buckets[idx].count++;
		}
		const maxCount = Math.max(...buckets.map((b) => b.count), 1);
		const W = 560,
			H = 80,
			PAD = 8;
		const zeroX = mn < 0 && mx > 0 ? PAD + (-mn / (mx - mn)) * (W - PAD * 2) : null;
		const bars = buckets.map((b, i) => ({
			x: PAD + i * ((W - PAD * 2) / bucketCount),
			w: Math.max(1, (W - PAD * 2) / bucketCount - 1),
			h: (b.count / maxCount) * (H - PAD * 2),
			positive: (b.lo + b.hi) / 2 >= 0
		}));
		const avg = pts.reduce((a, b) => a + b, 0) / pts.length;
		return { W, H, bars, zeroX, avg, mn: mn.toFixed(4), mx: mx.toFixed(4), total: pts.length, PAD };
	});

	const epochSortinoVsWinrate = $derived.by(() => {
		const pts = epochs
			.filter(
				(e) =>
					e.sortino != null &&
					isFinite(e.sortino) &&
					e.sortino > -100 &&
					e.sortino < 500 &&
					e.winrate != null &&
					isFinite(e.winrate) &&
					e.winrate >= 0 &&
					e.winrate <= 1
			)
			.map((e) => ({ sortino: e.sortino!, wr: e.winrate! * 100, best: e.is_best ?? false }));
		if (pts.length < 8) return null;
		const sMin = Math.min(...pts.map((p) => p.sortino)),
			sMax = Math.max(...pts.map((p) => p.sortino), sMin + 0.01);
		const wMin = Math.min(...pts.map((p) => p.wr)),
			wMax = Math.max(...pts.map((p) => p.wr), wMin + 1);
		const W = 560,
			H = 130,
			PAD = 10;
		const toX = (w: number) => PAD + ((w - wMin) / (wMax - wMin)) * (W - PAD * 2);
		const toY = (s: number) => H - PAD - ((s - sMin) / (sMax - sMin)) * (H - PAD * 2);
		const zeroY = sMin < 0 && sMax > 0 ? toY(0) : null;
		const dots = pts.map((p) => ({ cx: toX(p.wr), cy: toY(p.sortino), best: p.best }));
		const topRight = pts.filter((p) => p.sortino > 0 && p.wr > 50).length;
		return {
			W,
			H,
			dots,
			zeroY,
			wMin: wMin.toFixed(0),
			wMax: wMax.toFixed(0),
			sMin: sMin.toFixed(1),
			sMax: sMax.toFixed(1),
			total: pts.length,
			topRight
		};
	});

	const epochCalmarVsSortino = $derived.by(() => {
		const pts = epochs
			.filter(
				(e) =>
					e.calmar != null &&
					isFinite(e.calmar) &&
					e.calmar > -200 &&
					e.calmar < 500 &&
					e.sortino != null &&
					isFinite(e.sortino) &&
					e.sortino > -100 &&
					e.sortino < 500
			)
			.map((e) => ({ calmar: e.calmar!, sortino: e.sortino!, best: e.is_best ?? false }));
		if (pts.length < 8) return null;
		const cMin = Math.min(...pts.map((p) => p.calmar)),
			cMax = Math.max(...pts.map((p) => p.calmar), cMin + 0.01);
		const sMin = Math.min(...pts.map((p) => p.sortino)),
			sMax = Math.max(...pts.map((p) => p.sortino), sMin + 0.01);
		const W = 560,
			H = 130,
			PAD = 10;
		const toX = (c: number) => PAD + ((c - cMin) / (cMax - cMin)) * (W - PAD * 2);
		const toY = (s: number) => H - PAD - ((s - sMin) / (sMax - sMin)) * (H - PAD * 2);
		const zeroX = cMin < 0 && cMax > 0 ? toX(0) : null;
		const zeroY = sMin < 0 && sMax > 0 ? toY(0) : null;
		const dots = pts.map((p) => ({ cx: toX(p.calmar), cy: toY(p.sortino), best: p.best }));
		const aligned = pts.filter((p) => p.calmar > 0 && p.sortino > 0).length;
		return {
			W,
			H,
			dots,
			zeroX,
			zeroY,
			cMin: cMin.toFixed(1),
			cMax: cMax.toFixed(1),
			sMin: sMin.toFixed(1),
			sMax: sMax.toFixed(1),
			total: pts.length,
			aligned
		};
	});

	const epochDrawdownVsProfit = $derived.by(() => {
		const pts = epochs
			.filter(
				(e) =>
					e.max_drawdown != null &&
					isFinite(e.max_drawdown) &&
					e.max_drawdown >= 0 &&
					e.profit_total != null &&
					isFinite(e.profit_total)
			)
			.map((e) => ({
				dd: e.max_drawdown! * 100,
				profit: e.profit_total!,
				best: e.is_best ?? false
			}));
		if (pts.length < 8) return null;
		const dMin = Math.min(...pts.map((p) => p.dd)),
			dMax = Math.max(...pts.map((p) => p.dd), dMin + 0.01);
		const pMin = Math.min(...pts.map((p) => p.profit)),
			pMax = Math.max(...pts.map((p) => p.profit), pMin + 0.01);
		const W = 560,
			H = 130,
			PAD = 10;
		const toX = (d: number) => PAD + ((d - dMin) / (dMax - dMin)) * (W - PAD * 2);
		const toY = (p: number) => H - PAD - ((p - pMin) / (pMax - pMin)) * (H - PAD * 2);
		const zeroY = pMin < 0 && pMax > 0 ? toY(0) : null;
		const dots = pts.map((p) => ({ cx: toX(p.dd), cy: toY(p.profit), best: p.best }));
		const topLeft = pts.filter(
			(p) => p.dd < dMin + (dMax - dMin) * 0.33 && p.profit > pMin + (pMax - pMin) * 0.67
		).length;
		return {
			W,
			H,
			dots,
			zeroY,
			dMin: dMin.toFixed(1),
			dMax: dMax.toFixed(1),
			pMin: pMin.toFixed(3),
			pMax: pMax.toFixed(3),
			total: pts.length,
			topLeft
		};
	});

	const epochCalmarConvergence = $derived.by(() => {
		const valid = epochs
			.filter((e) => e.calmar != null && isFinite(e.calmar) && e.calmar > -200 && e.calmar < 500)
			.map((e) => e.calmar!);
		if (valid.length < 8) return null;
		// rolling 10-epoch avg to show convergence trend
		const window = 10;
		const smoothed = valid.slice(window - 1).map((_, i) => {
			const slice = valid.slice(i, i + window);
			return slice.reduce((a, b) => a + b, 0) / slice.length;
		});
		const mn = Math.min(...smoothed),
			mx = Math.max(...smoothed, mn + 0.01);
		const W = 560,
			H = 80,
			PAD = 8;
		const toX = (i: number) => PAD + (i / Math.max(1, smoothed.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / (mx - mn)) * (H - PAD * 2);
		const polyline = smoothed.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
		const zeroY = mn < 0 && mx > 0 ? toY(0) : null;
		const latest = smoothed[smoothed.length - 1];
		return {
			W,
			H,
			polyline,
			zeroY,
			mn: mn.toFixed(2),
			mx: mx.toFixed(2),
			latest: latest.toFixed(2),
			count: smoothed.length
		};
	});

	const epochSQNBestTimeline = $derived.by(() => {
		const valid = epochs
			.filter((e) => e.sqn != null && isFinite(e.sqn) && Math.abs(e.sqn) < 100)
			.map((e) => e.sqn!);
		if (valid.length < 6) return null;
		let best = -Infinity;
		const running = valid.map((v) => {
			best = Math.max(best, v);
			return best;
		});
		const mn = Math.min(...running),
			mx = Math.max(...running, mn + 0.01);
		const W = 560,
			H = 80,
			PAD = 8;
		const toX = (i: number) => PAD + (i / Math.max(1, running.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / (mx - mn)) * (H - PAD * 2);
		const polyline = running.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
		const zeroY = mn < 0 && mx > 0 ? toY(0) : null;
		const latest = running[running.length - 1];
		const SQN_LABELS = [
			{ v: 1.6, label: 'Average' },
			{ v: 2.0, label: 'Good' },
			{ v: 2.5, label: 'Excellent' },
			{ v: 3.0, label: 'Superior' }
		];
		const qual = SQN_LABELS.filter((s) => latest >= s.v).pop()?.label ?? 'Poor';
		return {
			W,
			H,
			polyline,
			zeroY,
			mn: mn.toFixed(2),
			mx: mx.toFixed(2),
			latest: latest.toFixed(2),
			count: running.length,
			qual
		};
	});

	const epochWinrateConvergence = $derived.by(() => {
		const valid = epochs
			.filter((e) => e.winrate != null && isFinite(e.winrate!))
			.map((e) => e.winrate! * 100);
		if (valid.length < 6) return null;
		const W = 560,
			H = 80,
			PAD = 8;
		const mn = Math.min(...valid),
			mx = Math.max(...valid, mn + 0.5);
		const toX = (i: number) => PAD + (i / Math.max(1, valid.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / (mx - mn)) * (H - PAD * 2);
		const rawPolyline = valid.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
		let runBest = 0;
		const bestLine = valid.map((v) => {
			runBest = Math.max(runBest, v);
			return runBest;
		});
		const bestPolyline = bestLine
			.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`)
			.join(' ');
		const y50 = mn <= 50 && mx >= 50 ? toY(50) : null;
		const latest = valid[valid.length - 1];
		const best = bestLine[bestLine.length - 1];
		return {
			W,
			H,
			rawPolyline,
			bestPolyline,
			y50,
			mn: mn.toFixed(1),
			mx: mx.toFixed(1),
			latest: latest.toFixed(1),
			best: best.toFixed(1),
			count: valid.length
		};
	});

	const epochBestProfitFactorTimeline = $derived.by(() => {
		const valid = epochs
			.filter((e) => e.profit_total != null && isFinite(e.profit_total))
			.map((e) => e.profit_total!);
		if (valid.length < 6) return null;
		const W = 560,
			H = 80,
			PAD = 8;
		const mn = Math.min(...valid),
			mx = Math.max(...valid, mn + 0.01);
		const toX = (i: number) => PAD + (i / Math.max(1, valid.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / (mx - mn)) * (H - PAD * 2);
		const polyline = valid.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
		const zeroY = mn < 0 && mx > 0 ? toY(0) : null;
		let runBest = -Infinity;
		const bestLine = valid.map((v) => {
			runBest = Math.max(runBest, v);
			return runBest;
		});
		const bestPolyline = bestLine
			.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`)
			.join(' ');
		const latest = valid[valid.length - 1];
		const best = bestLine[bestLine.length - 1];
		return {
			W,
			H,
			polyline,
			bestPolyline,
			zeroY,
			mn: mn.toFixed(4),
			mx: mx.toFixed(4),
			latest: latest.toFixed(4),
			best: best.toFixed(4),
			count: valid.length
		};
	});

	const epochMaxDrawdownTrend = $derived.by(() => {
		const valid = epochs
			.filter((e) => e.max_drawdown != null && isFinite(e.max_drawdown!))
			.map((e) => e.max_drawdown!);
		if (valid.length < 6) return null;
		const W = 560,
			H = 70,
			PAD = 8;
		const mn = 0,
			mx = Math.max(...valid, 0.01);
		const toX = (i: number) => PAD + (i / Math.max(1, valid.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mn) / (mx - mn)) * (H - PAD * 2);
		const polyline = valid.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
		let runMin = Infinity;
		const minLine = valid.map((v) => {
			runMin = Math.min(runMin, v);
			return runMin;
		});
		const minPolyline = minLine
			.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`)
			.join(' ');
		const latest = valid[valid.length - 1];
		const best = minLine[minLine.length - 1];
		return {
			W,
			H,
			polyline,
			minPolyline,
			mn: mn.toFixed(3),
			mx: mx.toFixed(3),
			latest: latest.toFixed(3),
			best: best.toFixed(3),
			count: valid.length
		};
	});

	const epochHoldingTimeDistribution = $derived.by(() => {
		const vals = epochs
			.filter(
				(e) =>
					e.holding_avg_hours != null && isFinite(e.holding_avg_hours!) && e.holding_avg_hours! > 0
			)
			.map((e) => e.holding_avg_hours!);
		if (vals.length < 5) return null;
		const mn = Math.min(...vals),
			mx = Math.max(...vals, mn + 0.1);
		const BUCKETS = 10,
			step = (mx - mn) / BUCKETS;
		const counts = Array.from({ length: BUCKETS }, (_, i) => {
			const lo = mn + i * step,
				hi = lo + step;
			const cnt = vals.filter((v) => v >= lo && (i === BUCKETS - 1 ? v <= hi : v < hi)).length;
			return { lo, cnt, label: lo.toFixed(0) };
		});
		const maxCnt = Math.max(...counts.map((b) => b.cnt), 1);
		const W = 440,
			H = 70,
			PAD = 8,
			barW = Math.floor((W - PAD * 2) / BUCKETS) - 1;
		const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
		return { counts, maxCnt, W, H, PAD, barW, avg: avg.toFixed(1), count: vals.length };
	});

	const epochLossFunctionHeatmap = $derived.by(() => {
		const valid = epochs
			.filter(
				(e) => e.loss != null && isFinite(e.loss!) && e.winrate != null && isFinite(e.winrate!)
			)
			.map((e) => ({ loss: e.loss!, wr: e.winrate! * 100, is_best: e.is_best ?? false }));
		if (valid.length < 6) return null;
		const W = 520,
			H = 90,
			PAD = 10;
		const mnL = Math.min(...valid.map((p) => p.loss)),
			mxL = Math.max(...valid.map((p) => p.loss), mnL + 0.01);
		const mnW = Math.min(...valid.map((p) => p.wr)),
			mxW = Math.max(...valid.map((p) => p.wr), mnW + 1);
		const toX = (v: number) => PAD + ((v - mnL) / (mxL - mnL)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - mnW) / (mxW - mnW)) * (H - PAD * 2);
		const dots = valid.map((p) => ({
			cx: toX(p.loss),
			cy: toY(p.wr),
			r: p.is_best ? 4 : 2,
			color: p.is_best ? 'var(--ch-warn)' : 'var(--ch-violet-light)'
		}));
		return { W, H, dots, count: valid.length };
	});

	const epochCalmarTimeline = $derived.by(() => {
		const valid = epochs.filter(
			(e) => e.calmar != null && isFinite(e.calmar) && e.calmar > 0 && e.calmar < 50
		);
		if (valid.length < 4) return null;
		const W = 520,
			H = 90,
			PAD = 16;
		const maxC = Math.max(...valid.map((e) => e.calmar!), 0.01);
		const toX = (i: number) => PAD + (i / (valid.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - (v / maxC) * (H - PAD * 2);
		let bestSoFar = -Infinity;
		const pts = valid.map((e, i) => {
			if (e.calmar! > bestSoFar) bestSoFar = e.calmar!;
			return { cx: toX(i), cy: toY(e.calmar!), best: toY(bestSoFar), isBest: e.is_best };
		});
		const polyline = pts.map((p) => `${p.cx.toFixed(1)},${p.cy.toFixed(1)}`).join(' ');
		const bestLine = pts.map((p) => `${p.cx.toFixed(1)},${p.best.toFixed(1)}`).join(' ');
		return { pts, polyline, bestLine, W, H, PAD, maxC, count: valid.length };
	});

	const epochSqnVsCalmarScatter = $derived.by(() => {
		const valid = epochs.filter(
			(e) =>
				e.sqn != null &&
				e.calmar != null &&
				isFinite(e.sqn!) &&
				isFinite(e.calmar!) &&
				e.calmar! > 0 &&
				e.calmar! < 50
		);
		if (valid.length < 5) return null;
		const W = 400,
			H = 120,
			PAD = 18;
		const maxS = Math.max(...valid.map((e) => Math.abs(e.sqn!)), 0.01);
		const maxC = Math.max(...valid.map((e) => e.calmar!), 0.01);
		const toX = (v: number) => PAD + ((v + maxS) / (maxS * 2)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - (v / maxC) * (H - PAD * 2);
		const dots = valid.map((e) => ({
			cx: toX(e.sqn!),
			cy: toY(e.calmar!),
			isBest: e.is_best,
			color: e.is_best
				? 'var(--ch-warn)'
				: e.calmar! >= 1.5
					? 'var(--ch-violet-light)'
					: 'var(--ch-axis-muted)'
		}));
		const zeroX = toX(0);
		return { dots, W, H, PAD, zeroX, count: valid.length };
	});

	const epochWinrateHistogram = $derived.by(() => {
		const vals = epochs
			.filter((e) => e.winrate != null && isFinite(e.winrate!))
			.map((e) => e.winrate! * 100);
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
			H = 70,
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

	const epochBestVsNonBestProfit = $derived.by(() => {
		const best = epochs.filter(
			(e) => e.is_best === true && e.profit_total != null && isFinite(e.profit_total!)
		);
		const rest = epochs.filter(
			(e) => e.is_best !== true && e.profit_total != null && isFinite(e.profit_total!)
		);
		if (best.length < 2 || rest.length < 2) return null;
		const avgBest = best.reduce((a, e) => a + e.profit_total!, 0) / best.length;
		const avgRest = rest.reduce((a, e) => a + e.profit_total!, 0) / rest.length;
		const maxAbs = Math.max(Math.abs(avgBest), Math.abs(avgRest), 0.01);
		const W = 300,
			H = 70,
			PAD = 12,
			midX = W / 2,
			barW = 60;
		const bestX = midX - barW - 10,
			restX = midX + 10;
		const toH = (v: number) => Math.max(2, (Math.abs(v) / maxAbs) * (H - PAD * 2 - 14));
		const bestH = toH(avgBest),
			restH = toH(avgRest);
		const bestColor = avgBest >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)';
		const restColor = avgRest >= 0 ? 'var(--ch-violet)' : 'var(--ch-loss)';
		return {
			avgBest,
			avgRest,
			W,
			H,
			PAD,
			midX,
			barW,
			bestX,
			restX,
			bestH,
			restH,
			bestColor,
			restColor,
			bestCount: best.length,
			restCount: rest.length
		};
	});

	const epochInitialVsOptimizedProfit = $derived.by(() => {
		const initial = epochs.filter(
			(e) => e.is_initial_point === true && e.profit_total != null && isFinite(e.profit_total!)
		);
		const optimized = epochs.filter(
			(e) => e.is_initial_point === false && e.profit_total != null && isFinite(e.profit_total!)
		);
		if (initial.length < 2 || optimized.length < 2) return null;
		const avgInit = initial.reduce((a, e) => a + e.profit_total!, 0) / initial.length;
		const avgOpt = optimized.reduce((a, e) => a + e.profit_total!, 0) / optimized.length;
		const maxAbs = Math.max(Math.abs(avgInit), Math.abs(avgOpt), 0.01);
		const W = 300,
			H = 70,
			PAD = 12,
			barW = 60;
		const initX = PAD + 20,
			optX = W / 2 + 10;
		const toH = (v: number) => Math.max(2, (Math.abs(v) / maxAbs) * (H - PAD * 2 - 14));
		const initH = toH(avgInit),
			optH = toH(avgOpt);
		const initColor = avgInit >= 0 ? 'var(--ch-axis)' : 'var(--ch-loss)';
		const optColor = avgOpt >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)';
		const baseY = H - PAD - 14;
		return {
			avgInit,
			avgOpt,
			W,
			H,
			PAD,
			barW,
			initX,
			optX,
			initH,
			optH,
			initColor,
			optColor,
			baseY,
			initCount: initial.length,
			optCount: optimized.length
		};
	});

	const epochProfitRunLength = $derived.by(() => {
		if (epochs.length < 10) return null;
		const sorted = [...epochs].sort((a, b) => (a.loss ?? 0) - (b.loss ?? 0));
		const W = 400,
			H = 75,
			PAD = 10;
		const profits = sorted.map((e) => e.profit_total ?? 0).filter((v) => isFinite(v));
		if (profits.length < 5) return null;
		const mn = Math.min(...profits),
			mx = Math.max(...profits);
		const range = mx - mn || 1;
		const pts = profits.map((v, i) => ({
			x: PAD + (i / (profits.length - 1)) * (W - PAD * 2),
			y: PAD + (1 - (v - mn) / range) * (H - PAD * 2)
		}));
		const polyline = pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
		const zeroY = PAD + (1 - (0 - mn) / range) * (H - PAD * 2);
		return {
			pts,
			polyline,
			W,
			H,
			PAD,
			zeroY: Math.max(PAD, Math.min(H - PAD, zeroY)),
			mn: mn.toFixed(2),
			mx: mx.toFixed(2),
			count: profits.length
		};
	});

	const epochDrawdownHistogram = $derived.by(() => {
		const vals = epochs
			.filter((e) => e.max_drawdown != null && isFinite(e.max_drawdown))
			.map((e) => e.max_drawdown! * 100);
		if (vals.length < 6) return null;
		const mn = 0,
			mx = Math.min(Math.max(...vals), 100);
		const bins = 12,
			step = Math.max(0.1, (mx - mn) / bins);
		const counts = Array.from({ length: bins }, (_, i) => {
			const lo = mn + i * step,
				hi = lo + step;
			return {
				lo,
				count: vals.filter((v) => v >= lo && (i === bins - 1 ? v <= mx : v < hi)).length
			};
		});
		const maxCount = Math.max(...counts.map((c) => c.count), 1);
		const W = 380,
			H = 72,
			PAD = 8,
			barW = Math.floor((W - PAD * 2) / bins) - 1;
		const avg = (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1);
		return { counts, maxCount, W, H, PAD, barW, mx: mx.toFixed(0), avg, total: vals.length };
	});

	const epochProfitRollingVolatility = $derived.by(() => {
		const sorted = [...epochs]
			.filter((e) => e.profit_total != null && isFinite(e.profit_total))
			.sort((a, b) => (a.epoch ?? 0) - (b.epoch ?? 0));
		if (sorted.length < 10) return null;
		const WIN = 10;
		const pts: { i: number; std: number }[] = [];
		for (let i = WIN - 1; i < sorted.length; i++) {
			const window = sorted.slice(i - WIN + 1, i + 1).map((e) => e.profit_total!);
			const mean = window.reduce((a, b) => a + b, 0) / WIN;
			const variance = window.reduce((s, v) => s + (v - mean) ** 2, 0) / WIN;
			pts.push({ i, std: Math.sqrt(variance) });
		}
		if (pts.length < 5) return null;
		const maxStd = Math.max(...pts.map((p) => p.std), 0.01);
		const W = 380,
			H = 70,
			PAD = 8;
		const toX = (i: number) => PAD + (i / (sorted.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - v / maxStd) * (H - PAD * 2);
		const poly = pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.std).toFixed(1)}`).join(' ');
		return { poly, W, H, PAD, maxStd: maxStd.toFixed(2), total: sorted.length };
	});

	const epochBestNMeanTrend = $derived.by(() => {
		const sorted = [...epochs]
			.filter((e) => e.profit_total != null && isFinite(e.profit_total))
			.sort((a, b) => (a.epoch ?? 0) - (b.epoch ?? 0));
		if (sorted.length < 15) return null;
		const N = Math.min(10, Math.floor(sorted.length / 5));
		const pts: { i: number; mean: number }[] = [];
		for (let i = N - 1; i < sorted.length; i++) {
			const window = sorted.slice(0, i + 1).map((e) => e.profit_total!);
			const topN = [...window].sort((a, b) => b - a).slice(0, N);
			pts.push({ i, mean: topN.reduce((a, b) => a + b, 0) / topN.length });
		}
		if (pts.length < 5) return null;
		const mnP = Math.min(...pts.map((p) => p.mean)),
			mxP = Math.max(...pts.map((p) => p.mean), mnP + 0.01);
		const W = 380,
			H = 72,
			PAD = 8;
		const toX = (i: number) => PAD + (i / (sorted.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - mnP) / (mxP - mnP)) * (H - PAD * 2);
		const poly = pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.mean).toFixed(1)}`).join(' ');
		const last = pts[pts.length - 1].mean;
		return { poly, W, H, PAD, N, total: sorted.length, last: (last * 100).toFixed(1) };
	});

	const epochSharpeTimeline = $derived.by(() => {
		const sorted = [...epochs]
			.filter((e) => e.sharpe != null && isFinite(e.sharpe) && Math.abs(e.sharpe) < 100)
			.sort((a, b) => (a.epoch ?? 0) - (b.epoch ?? 0));
		if (sorted.length < 8) return null;
		let bestSharpe = -Infinity;
		const pts = sorted.map((e, i) => {
			const s = e.sharpe!;
			if (s > bestSharpe) bestSharpe = s;
			return { i, best: bestSharpe, cur: s };
		});
		const mnS = Math.min(...pts.map((p) => Math.min(p.best, p.cur))),
			mxS = Math.max(...pts.map((p) => p.best), mnS + 0.1);
		const W = 380,
			H = 72,
			PAD = 8;
		const toX = (i: number) => PAD + (i / Math.max(sorted.length - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - mnS) / (mxS - mnS)) * (H - PAD * 2);
		const bestPoly = pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.best).toFixed(1)}`).join(' ');
		const curPoly = pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.cur).toFixed(1)}`).join(' ');
		const finalBest = pts[pts.length - 1].best.toFixed(2);
		return { bestPoly, curPoly, W, H, PAD, total: sorted.length, finalBest };
	});

	const epochCalmarBuckets = $derived.by(() => {
		const vals = epochs
			.filter((e) => e.calmar != null && isFinite(e.calmar) && Math.abs(e.calmar) < 200)
			.map((e) => e.calmar!);
		if (vals.length < 10) return null;
		const mn = Math.min(...vals),
			mx = Math.max(...vals);
		const BIN = 10,
			step = (mx - mn) / BIN || 1;
		const bins = Array.from({ length: BIN }, (_, i) => ({
			lo: mn + i * step,
			hi: mn + (i + 1) * step,
			count: 0
		}));
		for (const v of vals) {
			const bi = Math.min(BIN - 1, Math.floor((v - mn) / step));
			bins[bi].count++;
		}
		const maxCount = Math.max(...bins.map((b) => b.count), 1);
		const W = 320,
			H = 65,
			PAD = 8,
			barW = Math.floor((W - PAD * 2) / BIN) - 2;
		return { bins, maxCount, mn, mx, W, H, PAD, barW, total: vals.length };
	});

	const epochProfitVsTradeCount = $derived.by(() => {
		const pts = epochs
			.filter(
				(e) =>
					e.profit_total != null &&
					isFinite(e.profit_total) &&
					e.total_trades != null &&
					isFinite(e.total_trades) &&
					e.total_trades > 0
			)
			.map((e) => ({ profit: e.profit_total!, trades: e.total_trades!, best: e.is_best ?? false }));
		if (pts.length < 8) return null;
		const pMin = Math.min(...pts.map((p) => p.profit)),
			pMax = Math.max(...pts.map((p) => p.profit), pMin + 0.1);
		const tMin = Math.min(...pts.map((p) => p.trades)),
			tMax = Math.max(...pts.map((p) => p.trades), tMin + 1);
		const W = 360,
			H = 88,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - tMin) / (tMax - tMin)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - pMin) / (pMax - pMin)) * (H - PAD * 2);
		const zeroY = Math.max(PAD, Math.min(H - PAD, toY(0)));
		const dots = pts.map((p) => ({
			cx: toX(p.trades),
			cy: toY(p.profit),
			best: p.best,
			color: p.best
				? 'var(--ch-warn)'
				: p.profit >= 0
					? 'var(--ch-profit-light)'
					: 'var(--ch-loss-light)'
		}));
		return {
			dots,
			W,
			H,
			PAD,
			zeroY,
			tMin,
			tMax,
			pMin: pMin.toFixed(0),
			pMax: pMax.toFixed(0),
			count: pts.length
		};
	});

	const epochSortinoBestTimeline = $derived.by(() => {
		const sorted = [...epochs]
			.filter((e) => e.sortino != null && isFinite(e.sortino) && Math.abs(e.sortino) < 200)
			.sort((a, b) => (a.epoch ?? 0) - (b.epoch ?? 0));
		if (sorted.length < 8) return null;
		let best = -Infinity;
		const pts = sorted.map((e, i) => {
			const s = e.sortino!;
			if (s > best) best = s;
			return { i, best, cur: s };
		});
		const mnS = Math.min(...pts.map((p) => Math.min(p.cur, p.best))),
			mxS = Math.max(...pts.map((p) => p.best), mnS + 0.1);
		const W = 380,
			H = 68,
			PAD = 8;
		const toX = (i: number) => PAD + (i / Math.max(sorted.length - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - mnS) / (mxS - mnS)) * (H - PAD * 2);
		const bestPoly = pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.best).toFixed(1)}`).join(' ');
		const curPoly = pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.cur).toFixed(1)}`).join(' ');
		const finalBest = pts[pts.length - 1].best.toFixed(2);
		return { bestPoly, curPoly, W, H, PAD, total: sorted.length, finalBest };
	});

	const epochTradeCountTimeline = $derived.by(() => {
		const sorted = [...epochs]
			.filter((e) => e.total_trades != null && isFinite(e.total_trades) && e.total_trades >= 0)
			.sort((a, b) => (a.epoch ?? 0) - (b.epoch ?? 0));
		if (sorted.length < 8) return null;
		const counts = sorted.map((e) => e.total_trades!);
		const mn = 0,
			mx = Math.max(...counts, 1);
		const W = 380,
			H = 68,
			PAD = 8;
		const toX = (i: number) => PAD + (i / Math.max(sorted.length - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - (v - mn) / (mx - mn)) * (H - PAD * 2);
		let bestIdx = -1;
		for (let i = 0; i < sorted.length; i++) {
			if ((sorted[i].profit_total ?? -Infinity) > (sorted[bestIdx]?.profit_total ?? -Infinity))
				bestIdx = i;
		}
		const dots = sorted.map((e, i) => ({
			cx: toX(i),
			cy: toY(e.total_trades!),
			isBest: i === bestIdx,
			color: i === bestIdx ? 'var(--ch-violet-strong)' : 'var(--ch-axis-muted)'
		}));
		const poly = dots.map((d) => `${d.cx.toFixed(1)},${d.cy.toFixed(1)}`).join(' ');
		return {
			dots,
			poly,
			W,
			H,
			PAD,
			mn,
			mx,
			bestCount: sorted[bestIdx]?.total_trades ?? 0,
			total: sorted.length
		};
	});

	const epochWinRateTimeline = $derived.by(() => {
		const sorted = [...epochs]
			.filter((e) => e.winrate != null && isFinite(e.winrate))
			.sort((a, b) => (a.epoch ?? 0) - (b.epoch ?? 0));
		if (sorted.length < 8) return null;
		const W = 380,
			H = 68,
			PAD = 8;
		const toX = (i: number) => PAD + (i / Math.max(sorted.length - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (1 - v) * (H - PAD * 2);
		let best = -Infinity;
		const pts = sorted.map((e, i) => {
			const wr = e.winrate!;
			if (wr > best) best = wr;
			return { i, cur: wr, best };
		});
		const curPoly = pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.cur).toFixed(1)}`).join(' ');
		const bestPoly = pts.map((p) => `${toX(p.i).toFixed(1)},${toY(p.best).toFixed(1)}`).join(' ');
		const y50 = toY(0.5);
		const finalBest = (pts[pts.length - 1].best * 100).toFixed(1);
		return { curPoly, bestPoly, W, H, PAD, y50, total: sorted.length, finalBest };
	});

	const epochSharpeVsDrawdown = $derived.by(() => {
		const pts = epochs
			.filter(
				(e) =>
					e.sharpe != null &&
					isFinite(e.sharpe) &&
					Math.abs(e.sharpe) < 100 &&
					e.max_drawdown != null &&
					isFinite(e.max_drawdown) &&
					e.max_drawdown >= 0
			)
			.map((e) => ({
				sharpe: e.sharpe!,
				dd: e.max_drawdown!,
				profit: (e.profit_total ?? 0) * 100
			}));
		if (pts.length < 5) return null;
		const sMin = Math.min(...pts.map((p) => p.sharpe)),
			sMax = Math.max(...pts.map((p) => p.sharpe), sMin + 0.1);
		const ddMax = Math.max(...pts.map((p) => p.dd), 0.1);
		const W = 380,
			H = 88,
			PAD = 12;
		const toX = (v: number) => PAD + ((v - sMin) / (sMax - sMin)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (v / ddMax) * (H - PAD * 2);
		const zeroX = Math.max(PAD, Math.min(W - PAD, toX(0)));
		const dots = pts.map((p) => ({
			cx: toX(p.sharpe),
			cy: toY(p.dd),
			color:
				p.profit >= 5
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
			sMin: sMin.toFixed(1),
			sMax: sMax.toFixed(1),
			ddMax: ddMax.toFixed(1)
		};
	});

	const epochProfitHistogram = $derived.by(() => {
		const vals = epochs
			.filter((e) => e.profit_total != null && isFinite(e.profit_total))
			.map((e) => e.profit_total! * 100);
		if (vals.length < 8) return null;
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
		const W = 380,
			H = 68,
			PAD = 10;
		const bw = (W - PAD * 2) / bins - 1;
		const zeroX =
			PAD +
			Math.max(0, Math.min(bins - 1, Math.floor((0 - mn) / binSize))) * ((W - PAD * 2) / bins);
		const bars = buckets.map((b, i) => ({
			x: PAD + i * ((W - PAD * 2) / bins),
			h: Math.max(2, (b.count / maxC) * (H - PAD - 14)),
			color: b.lo >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss-light)'
		}));
		return { bars, bw, W, H, PAD, zeroX, mn: mn.toFixed(1), mx: mx.toFixed(1), total: vals.length };
	});

	const epochBestExplorationCurve = $derived.by(() => {
		const sorted = epochs
			.filter((e) => e.epoch != null && e.profit_total != null && isFinite(e.profit_total))
			.sort((a, b) => a.epoch! - b.epoch!);
		if (sorted.length < 5) return null;
		let best = -Infinity;
		const cumBest = sorted.map((e) => {
			best = Math.max(best, e.profit_total! * 100);
			return { ep: e.epoch!, best };
		});
		const minBest = Math.min(...cumBest.map((p) => p.best));
		const maxBest = Math.max(...cumBest.map((p) => p.best));
		const range = maxBest - minBest || 1;
		const W = 380,
			H = 68,
			PAD = 10;
		const epMin = sorted[0].epoch!;
		const epMax = sorted[sorted.length - 1].epoch!;
		const pts = cumBest.map((p) => {
			const x = PAD + ((p.ep - epMin) / (epMax - epMin || 1)) * (W - PAD * 2);
			const y = PAD + ((maxBest - p.best) / range) * (H - PAD * 2);
			return `${x},${y}`;
		});
		const polyline = pts.join(' ');
		const lastPt = `${W - PAD},${H - PAD}`;
		const firstPt = `${PAD},${H - PAD}`;
		const area = `${firstPt} ${polyline} ${lastPt}`;
		const color = maxBest >= 0 ? 'var(--ch-profit-strong)' : 'var(--ch-loss-strong)';
		const fillColor = maxBest >= 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)';
		return {
			polyline,
			area,
			W,
			H,
			PAD,
			color,
			fillColor,
			minBest: minBest.toFixed(1),
			maxBest: maxBest.toFixed(1),
			totalEpochs: sorted.length
		};
	});

	const epochDrawdownByBucket = $derived.by(() => {
		const sorted = epochs
			.filter(
				(e) =>
					e.epoch != null &&
					e.max_drawdown != null &&
					isFinite(e.max_drawdown) &&
					e.max_drawdown >= 0
			)
			.sort((a, b) => a.epoch! - b.epoch!);
		if (sorted.length < 8) return null;
		const bucketSize = Math.ceil(sorted.length / 12);
		const buckets = [];
		for (let i = 0; i < sorted.length; i += bucketSize) {
			const chunk = sorted.slice(i, i + bucketSize);
			const avg = chunk.reduce((a, e) => a + e.max_drawdown!, 0) / chunk.length;
			const label = chunk[0].epoch!;
			buckets.push({ label, avg });
		}
		const maxDD = Math.max(...buckets.map((b) => b.avg), 0.01);
		const W = 380,
			H = 68,
			PAD = 10;
		const toX = (i: number) => PAD + (i / (buckets.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => PAD + (v / maxDD) * (H - PAD * 2);
		const pts = buckets.map((b, i) => `${toX(i)},${toY(b.avg)}`);
		const polyline = pts.join(' ');
		const area = `${toX(0)},${H - PAD} ${polyline} ${toX(buckets.length - 1)},${H - PAD}`;
		return {
			polyline,
			area,
			W,
			H,
			PAD,
			maxDD: maxDD.toFixed(1),
			firstEp: buckets[0].label,
			lastEp: buckets[buckets.length - 1].label
		};
	});

	const epochWinRateVsProfit = $derived.by(() => {
		if (!epochs || epochs.length < 8) return null;
		const pts = epochs
			.filter((e) => e.winrate != null && legacyEpoch(e).profit_factor != null)
			.map((e) => ({
				wr: (e.winrate ?? 0) * 100,
				pf: legacyEpoch(e).profit_factor ?? 0,
				profit: e.profit_total ?? 0
			}));
		if (pts.length < 6) return null;
		const wrMax = Math.max(...pts.map((p) => p.wr), 100);
		const pfMax = Math.max(...pts.map((p) => p.pf), 1);
		const W = 320,
			H = 120,
			PAD = 14;
		const toX = (wr: number) => PAD + (wr / wrMax) * (W - PAD * 2);
		const toY = (pf: number) => H - PAD - (pf / pfMax) * (H - PAD * 2);
		return { pts, W, H, PAD, toX, toY, wrMax: wrMax.toFixed(0), pfMax: pfMax.toFixed(2) };
	});

	const epochCalmarTrend = $derived.by(() => {
		if (!epochs || epochs.length < 8) return null;
		const bins = 10;
		const size = Math.ceil(epochs.length / bins);
		const buckets = Array.from({ length: bins }, (_, i) => {
			const slice = epochs.slice(i * size, (i + 1) * size);
			const vals = slice.map((e) => e.calmar ?? 0).filter((v) => v !== 0);
			return {
				label: String(i * size + 1),
				avg: vals.length ? vals.reduce((a, v) => a + v, 0) / vals.length : 0
			};
		}).filter((b) => b.avg !== 0);
		if (buckets.length < 4) return null;
		const maxAbs = Math.max(...buckets.map((b) => Math.abs(b.avg)), 0.01);
		const W = 380,
			H = 68,
			PAD = 10;
		const toX = (i: number) => PAD + (i / (buckets.length - 1)) * (W - PAD * 2);
		const midY = H / 2;
		const toH = (v: number) => (Math.abs(v) / maxAbs) * (midY - PAD);
		return { buckets, W, H, PAD, toX, midY, toH, maxAbs: maxAbs.toFixed(2) };
	});

	const epochBestProfitTimeline = $derived.by(() => {
		if (!epochs || epochs.length < 8) return null;
		let best = -Infinity;
		const pts = epochs.map((e, i) => {
			const p = e.profit_total ?? e.profit_total ?? 0;
			if (p > best) best = p;
			return { i, best };
		});
		const maxV = Math.max(...pts.map((p) => p.best), 0.01);
		const minV = Math.min(...pts.map((p) => p.best), 0);
		const range = maxV - minV || 0.01;
		const W = 380,
			H = 68,
			PAD = 10;
		const toX = (i: number) => PAD + (i / (pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - minV) / range) * (H - PAD * 2);
		const polyline = pts.map((p) => `${toX(p.i)},${toY(p.best)}`).join(' ');
		const zeroY = toY(0);
		const area = `${toX(0)},${zeroY} ${polyline} ${toX(pts.length - 1)},${zeroY}`;
		const last = pts[pts.length - 1].best;
		const color = last >= 0 ? 'var(--ch-profit-strong)' : 'var(--ch-loss-strong)';
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
			last: last.toFixed(4)
		};
	});

	const epochSharpeVsDrawdownNew = $derived.by(() => {
		if (!epochs || epochs.length < 8) return null;
		const pts = epochs
			.filter((e) => e.sharpe != null && e.max_drawdown != null)
			.map((e) => ({
				sh: e.sharpe as number,
				dd: e.max_drawdown as number,
				profit: e.profit_total ?? 0
			}));
		if (pts.length < 6) return null;
		const ddMax = Math.max(...pts.map((p) => p.dd), 0.01);
		const shMin = Math.min(...pts.map((p) => p.sh), 0);
		const shMax = Math.max(...pts.map((p) => p.sh), 1);
		const range = shMax - shMin || 0.01;
		const W = 320,
			H = 110,
			PAD = 14;
		const toX = (dd: number) => PAD + (dd / ddMax) * (W - PAD * 2);
		const toY = (sh: number) => H - PAD - ((sh - shMin) / range) * (H - PAD * 2);
		return { pts, W, H, PAD, toX, toY, ddMax: ddMax.toFixed(1), shMax: shMax.toFixed(2) };
	});

	const epochWinRateHistogram = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const wrs = epochs
			.filter((e) => e.winrate != null && e.total_trades != null && (e.total_trades as number) > 0)
			.map((e) => (e.winrate as number) * 100);
		if (wrs.length < 8) return null;
		const bins = 14;
		const counts = new Array(bins).fill(0);
		for (const wr of wrs) {
			const b = Math.min(Math.floor((wr / 100) * bins), bins - 1);
			counts[b]++;
		}
		const maxCount = Math.max(...counts, 1);
		const W = 320,
			H = 68,
			PAD = 8;
		const barW = (W - PAD * 2) / bins;
		return { counts, maxCount, W, H, PAD, barW, bins };
	});

	const epochSortinoVsWinRate = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const pts = epochs
			.filter(
				(e) =>
					e.sortino != null &&
					e.winrate != null &&
					e.total_trades != null &&
					(e.total_trades as number) > 0
			)
			.map((e) => ({
				wr: (e.winrate as number) * 100,
				so: e.sortino as number,
				profit: e.profit_total ?? 0
			}));
		if (pts.length < 6) return null;
		const wrMax = Math.max(...pts.map((p) => p.wr), 100);
		const soMin = Math.min(...pts.map((p) => p.so), 0);
		const soMax = Math.max(...pts.map((p) => p.so), 0.01);
		const range = soMax - soMin || 0.01;
		const W = 300,
			H = 100,
			PAD = 12;
		const toX = (wr: number) => PAD + (wr / wrMax) * (W - PAD * 2);
		const toY = (so: number) => H - PAD - ((so - soMin) / range) * (H - PAD * 2);
		return { pts, W, H, PAD, toX, toY, wrMax: wrMax.toFixed(0), soMax: soMax.toFixed(2) };
	});

	const epochCalmarSortinoScatter = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const pts = epochs
			.filter((e) => e.calmar != null && e.sortino != null)
			.map((e) => ({
				ca: e.calmar as number,
				so: e.sortino as number,
				profit: e.profit_total ?? 0
			}));
		if (pts.length < 6) return null;
		const caMax = Math.max(...pts.map((p) => p.ca), 0.01);
		const soMin = Math.min(...pts.map((p) => p.so), 0);
		const soMax = Math.max(...pts.map((p) => p.so), 0.01);
		const range = soMax - soMin || 0.01;
		const W = 300,
			H = 100,
			PAD = 12;
		const toX = (ca: number) => PAD + (ca / caMax) * (W - PAD * 2);
		const toY = (so: number) => H - PAD - ((so - soMin) / range) * (H - PAD * 2);
		return { pts, W, H, PAD, toX, toY, caMax: caMax.toFixed(2), soMax: soMax.toFixed(2) };
	});

	const epochProfitByDrawdownBucket = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const map = new Map<number, number[]>();
		for (const e of epochs) {
			if (e.max_drawdown == null || e.profit_total == null) continue;
			const dd = e.max_drawdown as number;
			const bucket = dd <= 5 ? 5 : dd <= 10 ? 10 : dd <= 20 ? 20 : dd <= 30 ? 30 : 50;
			const arr = map.get(bucket) ?? [];
			arr.push(e.profit_total as number);
			map.set(bucket, arr);
		}
		if (map.size < 3) return null;
		const buckets = [...map.keys()].sort((a, b) => a - b);
		const rows = buckets.map((b) => {
			const arr = map.get(b)!;
			return { b: `≤${b}%`, avg: arr.reduce((a, v) => a + v, 0) / arr.length };
		});
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.001);
		const W = 300,
			H = 68,
			PAD = 8;
		const bw = (W - PAD * 2) / rows.length - 2;
		const midY = H / 2;
		return { rows, maxAbs, W, H, PAD, bw, midY };
	});

	const epochSortinoDistribution = $derived.by(() => {
		if (!epochs || epochs.length < 15) return null;
		const vals = epochs.filter((e) => e.sortino != null).map((e) => e.sortino as number);
		if (vals.length < 15) return null;
		vals.sort((a, b) => a - b);
		const minV = vals[0],
			maxV = vals[vals.length - 1];
		const range = maxV - minV || 0.01;
		const BINS = 12;
		const bins = new Array(BINS).fill(0);
		for (const v of vals) {
			const bi = Math.min(BINS - 1, Math.floor(((v - minV) / range) * BINS));
			bins[bi]++;
		}
		const maxCount = Math.max(...bins, 1);
		const W = 300,
			H = 68,
			PAD = 8;
		const bw = (W - PAD * 2) / BINS;
		const zeroX = minV < 0 ? PAD + (-minV / range) * (W - PAD * 2) : PAD;
		return { bins, maxCount, W, H, PAD, bw, minV: minV.toFixed(2), maxV: maxV.toFixed(2), zeroX };
	});

	const epochProfitCumulative = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const sorted = [...epochs]
			.filter((e) => e.profit_total != null)
			.sort((a, b) => (a.profit_total as number) - (b.profit_total as number));
		if (sorted.length < 10) return null;
		const profits = sorted.map((e) => e.profit_total as number);
		const minP = profits[0],
			maxP = profits[profits.length - 1];
		const range = maxP - minP || 0.01;
		const W = 300,
			H = 80,
			PAD = 10;
		const toX = (i: number) => PAD + (i / (profits.length - 1)) * (W - PAD * 2);
		const toY = (p: number) => H - PAD - ((p - minP) / range) * (H - PAD * 2);
		const polyline = profits.map((p, i) => `${toX(i)},${toY(p)}`).join(' ');
		const zeroY = toY(0);
		const pct80 = profits[Math.floor(profits.length * 0.8)];
		return {
			polyline,
			W,
			H,
			PAD,
			zeroY,
			minP: minP.toFixed(4),
			maxP: maxP.toFixed(4),
			pct80: pct80.toFixed(4)
		};
	});

	const epochDrawdownCDF = $derived.by(() => {
		if (!epochs || epochs.length < 15) return null;
		const vals = epochs
			.filter((e) => e.max_drawdown != null)
			.map((e) => e.max_drawdown as number)
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
		const p20X = toX(vals[Math.floor(vals.length * 0.2)]);
		const p20 = vals[Math.floor(vals.length * 0.2)];
		const median = vals[Math.floor(vals.length * 0.5)];
		return {
			polyline,
			W,
			H,
			PAD,
			p20X,
			minV: minV.toFixed(1),
			maxV: maxV.toFixed(1),
			median: median.toFixed(1),
			p20: p20.toFixed(1)
		};
	});

	const epochTradeCountByDrawdown = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const map = new Map<number, number[]>();
		for (const e of epochs) {
			const dd = e.max_drawdown;
			const tc = e.total_trades;
			if (dd == null || tc == null) continue;
			const bucket =
				(dd as number) <= 5
					? 5
					: (dd as number) <= 10
						? 10
						: (dd as number) <= 20
							? 20
							: (dd as number) <= 30
								? 30
								: 50;
			const arr = map.get(bucket) ?? [];
			arr.push(tc as number);
			map.set(bucket, arr);
		}
		if (map.size < 3) return null;
		const buckets = [...map.keys()].sort((a, b) => a - b);
		const rows = buckets.map((b) => {
			const arr = map.get(b)!;
			return { b: `≤${b}%`, avg: arr.reduce((a, v) => a + v, 0) / arr.length };
		});
		const maxAvg = Math.max(...rows.map((r) => r.avg), 1);
		const W = 300,
			H = 64,
			PAD = 8;
		const bw = (W - PAD * 2) / rows.length - 2;
		return { rows, maxAvg, W, H, PAD, bw };
	});

	const epochWinRateByDrawdownBucket = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const map = new Map<number, number[]>();
		for (const e of epochs) {
			const dd = e.max_drawdown;
			const wr = e.winrate;
			if (dd == null || wr == null) continue;
			const bucket =
				(dd as number) <= 5
					? 5
					: (dd as number) <= 10
						? 10
						: (dd as number) <= 20
							? 20
							: (dd as number) <= 30
								? 30
								: 50;
			const arr = map.get(bucket) ?? [];
			arr.push((wr as number) * 100);
			map.set(bucket, arr);
		}
		if (map.size < 3) return null;
		const buckets = [...map.keys()].sort((a, b) => a - b);
		const rows = buckets.map((b) => {
			const arr = map.get(b)!;
			return { b: `≤${b}%`, avgWr: arr.reduce((s, v) => s + v, 0) / arr.length };
		});
		const maxWr = Math.max(...rows.map((r) => r.avgWr), 1);
		const W = 300,
			H = 64,
			PAD = 8;
		const bw = (W - PAD * 2) / rows.length - 2;
		return { rows, maxWr, W, H, PAD, bw };
	});

	const epochLossCDF = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const vals = epochs
			.map((e) => e.loss as number)
			.filter((v) => isFinite(v))
			.sort((a, b) => a - b);
		if (vals.length < 5) return null;
		const minV = vals[0],
			maxV = vals[vals.length - 1];
		if (maxV === minV) return null;
		const W = 300,
			H = 60,
			PAD = 8;
		const pts = vals
			.map((v, i) => {
				const x = PAD + ((v - minV) / (maxV - minV)) * (W - PAD * 2);
				const y = PAD + (1 - i / (vals.length - 1)) * (H - PAD * 2);
				return `${x.toFixed(1)},${y.toFixed(1)}`;
			})
			.join(' ');
		const medLoss = vals[Math.floor(vals.length / 2)].toFixed(3);
		const p10 = vals[Math.floor(vals.length * 0.1)];
		const p10X = (PAD + ((p10 - minV) / (maxV - minV)) * (W - PAD * 2)).toFixed(1);
		return { pts, minV: minV.toFixed(3), maxV: maxV.toFixed(3), medLoss, p10X, W, H, PAD };
	});

	const epochSharpeHistogram = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const vals = epochs.filter((e) => e.sharpe != null).map((e) => e.sharpe as number);
		if (vals.length < 5) return null;
		const minV = Math.min(...vals),
			maxV = Math.max(...vals, minV + 0.1);
		const BINS = 12;
		const step = (maxV - minV) / BINS;
		const counts = Array(BINS).fill(0);
		for (const v of vals) {
			const bi = Math.min(Math.floor((v - minV) / step), BINS - 1);
			counts[bi]++;
		}
		const maxCount = Math.max(...counts, 1);
		const W = 300,
			H = 60,
			PAD = 8,
			bw = (W - PAD * 2) / BINS - 1;
		return {
			counts,
			maxCount,
			minV: minV.toFixed(2),
			maxV: maxV.toFixed(2),
			step,
			BINS,
			W,
			H,
			PAD,
			bw
		};
	});

	const epochRollingBestCalmar = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const sorted = [...epochs].sort((a, b) => (a.epoch as number) - (b.epoch as number));
		let best = -Infinity;
		const pts: { epoch: number; best: number }[] = [];
		for (const e of sorted) {
			const c = e.calmar;
			if (c == null) continue;
			if ((c as number) > best) best = c as number;
			pts.push({ epoch: e.epoch as number, best });
		}
		if (pts.length < 5) return null;
		const minE = pts[0].epoch,
			maxE = pts[pts.length - 1].epoch;
		const minC = Math.min(...pts.map((p) => p.best)),
			maxC = Math.max(...pts.map((p) => p.best), minC + 0.1);
		const W = 300,
			H = 60,
			PAD = 8;
		const toX = (e: number) => PAD + ((e - minE) / Math.max(maxE - minE, 1)) * (W - PAD * 2);
		const toY = (c: number) => PAD + (1 - (c - minC) / (maxC - minC)) * (H - PAD * 2);
		const polyline = pts
			.map((p) => `${toX(p.epoch).toFixed(1)},${toY(p.best).toFixed(1)}`)
			.join(' ');
		return {
			polyline,
			W,
			H,
			PAD,
			minC: minC.toFixed(2),
			maxC: maxC.toFixed(2),
			lastBest: pts[pts.length - 1].best.toFixed(2)
		};
	});

	const epochProfitVsSortino = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const pts = epochs
			.filter((e) => legacyEpoch(e).profit_factor != null && e.sortino != null)
			.map((e) => ({
				profit: legacyEpoch(e).profit_factor as number,
				sortino: e.sortino as number
			}));
		if (pts.length < 8) return null;
		const minP = Math.min(...pts.map((p) => p.profit)),
			maxP = Math.max(...pts.map((p) => p.profit));
		const minS = Math.min(...pts.map((p) => p.sortino)),
			maxS = Math.max(...pts.map((p) => p.sortino));
		if (maxP === minP || maxS === minS) return null;
		const W = 300,
			H = 80,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - minP) / (maxP - minP)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - minS) / (maxS - minS)) * (H - PAD * 2);
		const zeroX = toX(1),
			zeroY = toY(0);
		return {
			pts,
			toX,
			toY,
			zeroX,
			zeroY,
			W,
			H,
			PAD,
			minP: minP.toFixed(1),
			maxP: maxP.toFixed(1),
			minS: minS.toFixed(1),
			maxS: maxS.toFixed(1)
		};
	});

	const epochWinRateByEpochQuartile = $derived.by(() => {
		if (!epochs || epochs.length < 20) return null;
		const sorted = [...epochs].sort((a, b) => (a.epoch as number) - (b.epoch as number));
		const qSize = Math.floor(sorted.length / 4);
		const labels = ['Q1', 'Q2', 'Q3', 'Q4'];
		const rows = labels.map((label, qi) => {
			const slice = sorted.slice(qi * qSize, (qi + 1) * qSize);
			const wins = slice.filter((e) => (e.winrate ?? 0) > 0.5).length;
			const wr = (wins / Math.max(slice.length, 1)) * 100;
			return { label, wr };
		});
		const W = 260,
			H = 60,
			PAD = 8;
		const bw = (W - PAD * 2) / rows.length - 2;
		return { rows, bw, W, H, PAD };
	});

	const epochBestSharpeByTF = $derived.by(() => {
		if (!epochs || epochs.length < 5) return null;
		const map = new Map<string, number>();
		for (const e of epochs) {
			const tf = legacyEpoch(e).timeframe ?? undefined;
			const s = e.sharpe as number | undefined;
			if (!tf || s == null) continue;
			const prev = map.get(tf) ?? -Infinity;
			if (s > prev) map.set(tf, s);
		}
		if (map.size < 2) return null;
		const rows = [...map.entries()]
			.map(([tf, best]) => ({ tf, best }))
			.sort((a, b) => b.best - a.best);
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.best)), 0.01);
		const W = 280,
			H = rows.length * 20 + 8,
			PAD = 8,
			barMaxW = W - PAD * 2 - 40;
		const zeroX = PAD + 30 + barMaxW / 2;
		return { rows, maxAbs, W, H, PAD, barMaxW, zeroX };
	});

	const epochDrawdownByStrategy = $derived.by(() => {
		if (!epochs || epochs.length < 8) return null;
		const map = new Map<string, number[]>();
		for (const e of epochs) {
			const strat = e.strategy as string | undefined;
			const dd = e.max_drawdown ?? e.max_drawdown;
			if (!strat || dd == null) continue;
			const arr = map.get(strat) ?? [];
			arr.push(Math.abs(dd as number) * 100);
			map.set(strat, arr);
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

	const epochCalmarByWinRateBucket = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const buckets = [
			{ label: '0-25%', min: 0, max: 25 },
			{ label: '25-50%', min: 25, max: 50 },
			{ label: '50-75%', min: 50, max: 75 },
			{ label: '75-100%', min: 75, max: 100 }
		];
		const rows = buckets
			.map((b) => {
				const vals = epochs
					.filter((e) => e.winrate != null && e.calmar != null)
					.filter((e) => {
						const wr = (e.winrate as number) * 100;
						return wr >= b.min && wr < b.max;
					})
					.map((e) => e.calmar as number);
				const avg = vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : 0;
				return { label: b.label, avg, n: vals.length };
			})
			.filter((r) => r.n > 0);
		if (rows.length < 2) return null;
		const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avg)), 0.01);
		const W = 280,
			H = 80,
			PAD = 8,
			midY = H / 2;
		const bw = (W - PAD * 2) / rows.length - 2;
		return { rows, maxAbs, bw, W, H, PAD, midY };
	});

	const epochTradeCountCDF = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const vals = epochs
			.filter((e) => e.total_trades != null)
			.map((e) => e.total_trades as number)
			.sort((a, b) => a - b);
		if (vals.length < 10) return null;
		const minV = vals[0],
			maxV = vals[vals.length - 1];
		const W = 280,
			H = 70,
			PAD = 8;
		const points = vals.map((v, i) => {
			const x = PAD + ((v - minV) / Math.max(maxV - minV, 1)) * (W - PAD * 2);
			const y = H - PAD - ((i + 1) / vals.length) * (H - PAD * 2);
			return `${x},${y}`;
		});
		const median = vals[Math.floor(vals.length / 2)];
		return { polyline: points.join(' '), minV, maxV, median, W, H, PAD };
	});

	const epochProfitByDrawdownQuartile = $derived.by(() => {
		if (!epochs || epochs.length < 12) return null;
		const vals = epochs
			.filter((e) => e.max_drawdown != null)
			.map((e) => e.max_drawdown as number)
			.sort((a, b) => a - b);
		if (vals.length < 12) return null;
		const q25 = vals[Math.floor(vals.length * 0.25)];
		const q50 = vals[Math.floor(vals.length * 0.5)];
		const q75 = vals[Math.floor(vals.length * 0.75)];
		const buckets = [
			{ label: 'Q1 DD', min: -Infinity, max: q25 },
			{ label: 'Q2 DD', min: q25, max: q50 },
			{ label: 'Q3 DD', min: q50, max: q75 },
			{ label: 'Q4 DD', min: q75, max: Infinity }
		];
		const rows = buckets
			.map((b) => {
				const eList = epochs.filter((e) => {
					const dd = e.max_drawdown as number | null;
					const pf = legacyEpoch(e).profit_factor as number | null;
					return dd != null && pf != null && dd >= b.min && dd < b.max;
				});
				const avg = eList.length
					? eList.reduce((s, e) => s + (legacyEpoch(e).profit_factor as number), 0) / eList.length
					: 0;
				return { label: b.label, avg, n: eList.length };
			})
			.filter((r) => r.n > 0);
		if (rows.length < 2) return null;
		const maxAvg = Math.max(...rows.map((r) => r.avg), 1);
		const W = 280,
			H = 75,
			PAD = 10;
		const bw = (W - PAD * 2) / rows.length - 2;
		return { rows, maxAvg, bw, W, H, PAD };
	});

	const epochSharpeVsCalmarScatter2 = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const pts = epochs
			.filter((e) => e.sharpe != null && e.calmar != null)
			.map((e) => ({
				x: e.sharpe as number,
				y: e.calmar as number,
				wr: ((e.winrate as number) ?? 0) * 100
			}));
		if (pts.length < 10) return null;
		const maxX = Math.max(...pts.map((p) => Math.abs(p.x)), 0.01);
		const maxY = Math.max(...pts.map((p) => Math.abs(p.y)), 0.01);
		const W = 280,
			H = 100,
			PAD = 12,
			midX = W / 2,
			midY = H / 2;
		return { pts, maxX, maxY, W, H, PAD, midX, midY };
	});

	const epochWinRateTrend = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const winRates = epochs
			.filter((e) => e.winrate != null)
			.map((e, i) => ({ idx: i, wr: (e.winrate as number) * 100 }));
		if (winRates.length < 10) return null;
		const window = Math.max(3, Math.floor(winRates.length / 10));
		const smoothed = winRates.map((p, i) => {
			const slice = winRates.slice(Math.max(0, i - window), i + window + 1);
			return { idx: p.idx, wr: slice.reduce((s, x) => s + x.wr, 0) / slice.length };
		});
		const maxWR = Math.max(...smoothed.map((p) => p.wr), 1);
		const minWR = Math.min(...smoothed.map((p) => p.wr), 0);
		const rng = maxWR - minWR || 1;
		const W = 300,
			H = 65,
			PAD = 10;
		const toX = (i: number) => PAD + (i / Math.max(smoothed.length - 1, 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v - minWR) / rng) * (H - PAD * 2);
		const polyline = smoothed
			.map((p, i) => `${toX(i).toFixed(1)},${toY(p.wr).toFixed(1)}`)
			.join(' ');
		return { smoothed, polyline, toX, toY, minWR, maxWR, W, H, PAD };
	});

	const epochSortinoBySharpeQuartile = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const valid = epochs.filter((e) => e.sharpe != null && e.sortino != null);
		if (valid.length < 8) return null;
		const sharpes = valid.map((e) => e.sharpe as number).sort((a, b) => a - b);
		const q1 = sharpes[Math.floor(sharpes.length * 0.25)];
		const q2 = sharpes[Math.floor(sharpes.length * 0.5)];
		const q3 = sharpes[Math.floor(sharpes.length * 0.75)];
		const buckets: Record<string, number[]> = { Q1: [], Q2: [], Q3: [], Q4: [] };
		for (const e of valid) {
			const sh = e.sharpe as number;
			const so = e.sortino as number;
			const bucket = sh < q1 ? 'Q1' : sh < q2 ? 'Q2' : sh < q3 ? 'Q3' : 'Q4';
			buckets[bucket].push(so);
		}
		const bars = (['Q1', 'Q2', 'Q3', 'Q4'] as const).map((k) => ({
			label: k,
			avg: buckets[k].length ? buckets[k].reduce((s, v) => s + v, 0) / buckets[k].length : 0,
			n: buckets[k].length
		}));
		const maxAbs = Math.max(...bars.map((b) => Math.abs(b.avg)), 0.01);
		const W = 280,
			H = 80,
			PAD = 8,
			midX = W / 2;
		const bh = Math.max(6, (H - PAD * 2) / bars.length - 2);
		return { bars, maxAbs, W, H, PAD, midX, bh };
	});

	const epochProfitFactorCDF = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const vals = epochs
			.filter(
				(e) =>
					legacyEpoch(e).profit_factor != null &&
					(legacyEpoch(e).profit_factor as number) > 0 &&
					(legacyEpoch(e).profit_factor as number) < 20
			)
			.map((e) => legacyEpoch(e).profit_factor as number)
			.sort((a, b) => a - b);
		if (vals.length < 8) return null;
		const minV = vals[0],
			maxV = vals[vals.length - 1],
			rng = maxV - minV || 1;
		const W = 300,
			H = 65,
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
			minV: minV.toFixed(2),
			maxV: maxV.toFixed(2),
			median: median.toFixed(2)
		};
	});

	const epochAvgTradeCountByWR = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const buckets: Record<string, number[]> = {
			'<40%': [],
			'40-50%': [],
			'50-60%': [],
			'>60%': []
		};
		for (const e of epochs) {
			const wr = ((e.winrate as number) ?? 0) * 100;
			const tc = (e.total_trades as number) ?? 0;
			if (tc <= 0) continue;
			const k = wr < 40 ? '<40%' : wr < 50 ? '40-50%' : wr < 60 ? '50-60%' : '>60%';
			buckets[k].push(tc);
		}
		const bars = (['<40%', '40-50%', '50-60%', '>60%'] as const)
			.map((k) => ({
				label: k,
				avg: buckets[k].length ? buckets[k].reduce((s, v) => s + v, 0) / buckets[k].length : 0,
				n: buckets[k].length
			}))
			.filter((b) => b.n > 0);
		if (bars.length < 2) return null;
		const maxAvg = Math.max(...bars.map((b) => b.avg), 1);
		const W = 300,
			H = 65,
			PAD = 8;
		const bw = Math.max(12, (W - PAD * 2) / bars.length - 4);
		return { bars, maxAvg, W, H, PAD, bw };
	});

	const epochMaxDrawdownCDF = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const vals = epochs
			.filter((e) => e.max_drawdown != null && (e.max_drawdown as number) >= 0)
			.map((e) => (e.max_drawdown as number) * 100)
			.sort((a, b) => a - b);
		if (vals.length < 8) return null;
		const minV = vals[0],
			maxV = vals[vals.length - 1],
			rng = maxV - minV || 1;
		const W = 300,
			H = 65,
			PAD = 10;
		const toX = (v: number) => PAD + ((v - minV) / rng) * (W - PAD * 2);
		const toY = (i: number) => H - PAD - (i / Math.max(vals.length - 1, 1)) * (H - PAD * 2);
		const polyline = vals.map((v, i) => `${toX(v).toFixed(1)},${toY(i).toFixed(1)}`).join(' ');
		const median = vals[Math.floor(vals.length / 2)];
		return {
			polyline,
			toX,
			W,
			H,
			PAD,
			minV: minV.toFixed(1),
			maxV: maxV.toFixed(1),
			median: median.toFixed(1)
		};
	});

	const epochRollingCalmar = $derived.by(() => {
		if (!epochs || epochs.length < 15) return null;
		const valid = epochs
			.filter((e) => e.calmar != null)
			.map((e, idx) => ({ idx, val: e.calmar as number }));
		if (valid.length < 15) return null;
		const win = 10;
		const smoothed = valid.slice(win - 1).map((_, i) => {
			const slice = valid.slice(i, i + win);
			return slice.reduce((s, v) => s + v.val, 0) / slice.length;
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

	const epochProfitCDFByLoss = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const allPF = epochs
			.filter((e) => legacyEpoch(e).profit_factor != null)
			.map((e) => legacyEpoch(e).profit_factor as number)
			.sort((a, b) => a - b);
		if (allPF.length < 8) return null;
		const clipped = allPF.filter((v) => v <= 5);
		if (clipped.length < 6) return null;
		const minV = clipped[0],
			maxV = clipped[clipped.length - 1];
		const W = 300,
			H = 65,
			PAD = 8;
		const toX = (v: number) => PAD + ((v - minV) / (maxV - minV || 1)) * (W - PAD * 2);
		const toY = (i: number) => H - PAD - (i / (clipped.length - 1)) * (H - PAD * 2);
		const polyline = clipped.map((v, i) => `${toX(v)},${toY(i)}`).join(' ');
		const median = clipped[Math.floor(clipped.length / 2)];
		return {
			polyline,
			W,
			H,
			PAD,
			toX,
			toY,
			minV: minV.toFixed(2),
			maxV: maxV.toFixed(2),
			median: median.toFixed(2)
		};
	});

	const epochSharpeByTradeCountBucket = $derived.by(() => {
		if (!epochs || epochs.length < 10) return null;
		const valid = epochs.filter((e) => e.sharpe != null && e.total_trades != null);
		if (valid.length < 8) return null;
		const tcs = valid.map((e) => e.total_trades as number).sort((a, b) => a - b);
		const q1 = tcs[Math.floor(tcs.length * 0.33)];
		const q2 = tcs[Math.floor(tcs.length * 0.67)];
		const buckets: Record<string, number[]> = { Low: [], Mid: [], High: [] };
		for (const e of valid) {
			const tc = e.total_trades as number;
			const sh = e.sharpe as number;
			const k = tc <= q1 ? 'Low' : tc <= q2 ? 'Mid' : 'High';
			buckets[k].push(sh);
		}
		const bars = (['Low', 'Mid', 'High'] as const)
			.map((k) => ({
				label: k,
				avg: buckets[k].length ? buckets[k].reduce((s, v) => s + v, 0) / buckets[k].length : 0,
				n: buckets[k].length
			}))
			.filter((b) => b.n > 0);
		if (bars.length < 2) return null;
		const maxAbs = Math.max(...bars.map((b) => Math.abs(b.avg)), 0.01);
		const W = 300,
			H = 65,
			PAD = 8,
			midY = H / 2;
		const bw = Math.max(20, (W - PAD * 2) / bars.length - 12);
		return { bars, maxAbs, W, H, PAD, midY, bw };
	});
</script>

<svelte:head>
	<title>{t(lang, 'hyperopt.title')} · Crypto Quant</title>
</svelte:head>

<main class="mx-auto w-full max-w-[1600px] px-4 py-8 sm:px-6">
	<h1 class="text-2xl font-semibold tracking-tight">{t(lang, 'hyperopt.title')}</h1>
	<p class="mt-1 max-w-3xl text-sm text-muted-foreground">{t(lang, 'hyperopt.subtitle')}</p>

	{#if !hasData}
		<!-- No-data callout -->
		<div
			class="mt-10 rounded-xl border border-dashed border-amber-500/40 bg-amber-500/5 p-8 text-center"
		>
			<p class="text-lg font-semibold text-amber-400">{t(lang, 'hyperopt.noData.title')}</p>
			<p class="mt-2 text-sm text-muted-foreground">{t(lang, 'hyperopt.noData.body')}</p>
			<pre
				class="mt-4 inline-block rounded-md bg-secondary px-4 py-2 text-left font-mono text-xs text-foreground">sops exec-env secrets.env 'python scripts/sync_hyperopt_to_db.py'</pre>
		</div>
	{:else}
		<!-- Strategy tab selector -->
		<div class="mt-6 flex flex-wrap gap-2">
			{#each strategies as s, _i (_i)}
				<button
					type="button"
					class="rounded-full border px-4 py-1.5 text-sm transition-colors"
					class:border-primary={currentStrategy === s}
					class:bg-primary={currentStrategy === s}
					class:text-primary-foreground={currentStrategy === s}
					class:border-border={currentStrategy !== s}
					class:text-muted-foreground={currentStrategy !== s}
					class:hover:bg-accent={currentStrategy !== s}
					onclick={() => {
						activeStrategy = s;
					}}
				>
					{s}
					<span class="ml-1.5 rounded-full bg-secondary px-1.5 font-mono text-[10px]">
						{data.byStrategy[s].length}
					</span>
				</button>
			{/each}
		</div>

		{#if epochs.length === 0}
			<p class="mt-6 text-sm text-muted-foreground">No epochs for this strategy.</p>
		{:else}
			<!-- Best epoch summary card -->
			{#if bestEpoch}
				<div class="mt-6 rounded-xl border border-amber-800/40 bg-amber-950/20 p-4">
					<div class="mb-3 flex items-center gap-2">
						<span class="text-xs font-semibold text-amber-400 uppercase"
							>★ {t(lang, 'hyperopt.bestLoss')} — Epoch #{bestEpoch.epoch}</span
						>
						<span class="rounded bg-amber-500/20 px-2 py-0.5 font-mono text-xs text-amber-400"
							>loss {fmtN(bestEpoch.loss, 4)}</span
						>
					</div>
					<div class="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
						{#each [['Sharpe', fmtN(bestEpoch.sharpe)], ['Calmar', fmtN(bestEpoch.calmar)], ['Profit', fmtPct(bestEpoch.profit_total)], ['Win%', fmtPct(bestEpoch.winrate)], ['Trades', String(bestEpoch.total_trades ?? '—')], ['MaxDD', fmtPct(bestEpoch.max_drawdown)]] as [label, val], _i (_i)}
							<div class="rounded bg-card/60 px-3 py-2">
								<div class="text-[10px] text-muted-foreground">{label}</div>
								<div class="font-mono text-sm font-semibold text-foreground">{val}</div>
							</div>
						{/each}
					</div>
					{#if bestEpoch.params && Object.keys(bestEpoch.params).length > 0}
						<div class="flex flex-wrap gap-1.5">
							{#each Object.entries(bestEpoch.params) as [pk, pv], _i (_i)}
								<span
									class="rounded border border-amber-800/40 bg-amber-900/20 px-2 py-0.5 font-mono text-[11px] text-amber-300"
								>
									{pk} = {typeof pv === 'number' ? (Number.isInteger(pv) ? pv : pv.toFixed(3)) : pv}
								</span>
							{/each}
						</div>
					{/if}
				</div>
			{/if}

			<!-- Loss curve chart -->
			<section class="mt-6 rounded-xl border bg-card p-4">
				<h2 class="mb-3 text-sm font-semibold">{t(lang, 'hyperopt.chart.title')}</h2>
				<svg
					viewBox="0 0 {SVG_W} {SVG_H}"
					width="100%"
					aria-label="Loss curve"
					class="overflow-visible"
				>
					<!-- Y-axis ticks -->
					{#each yTicks as tick, _i (_i)}
						{@const cy = toY(tick)}
						<line
							x1={PAD.left}
							y1={cy}
							x2={PAD.left + plotW}
							y2={cy}
							stroke="currentColor"
							stroke-opacity="0.08"
							stroke-width="1"
						/>
						<text
							x={PAD.left - 6}
							y={cy + 4}
							text-anchor="end"
							font-size="9"
							fill="currentColor"
							opacity="0.5"
						>
							{tick.toFixed(1)}
						</text>
					{/each}

					<!-- X-axis label -->
					<text
						x={PAD.left + plotW / 2}
						y={SVG_H - 2}
						text-anchor="middle"
						font-size="9"
						fill="currentColor"
						opacity="0.5"
					>
						Epoch
					</text>

					<!-- Best-loss horizontal dashed line -->
					{#if bestEpoch && bestEpoch.loss != null && bestEpoch.loss <= CLIP_LOSS}
						{@const by = toY(bestEpoch.loss)}
						<line
							x1={PAD.left}
							y1={by}
							x2={PAD.left + plotW}
							y2={by}
							stroke="#f59e0b"
							stroke-width="1"
							stroke-dasharray="4 3"
							opacity="0.6"
						/>
					{/if}

					<!-- Dots -->
					{#each clippedEpochs as e, _i (_i)}
						{@const cx = toX(e.epoch)}
						{@const cy = toY(e.loss ?? 0)}
						{@const isBest = !!e.is_best}
						<circle
							{cx}
							{cy}
							r={isBest ? 4 : 2.5}
							fill={isBest ? '#f59e0b' : 'currentColor'}
							opacity={isBest ? 1 : 0.35}
						>
							<title>Epoch {e.epoch} · loss {e.loss?.toFixed(4)}</title>
						</circle>
					{/each}

					<!-- Best point label -->
					{#if bestEpoch && bestEpoch.loss != null && bestEpoch.loss <= CLIP_LOSS}
						{@const cx = toX(bestEpoch.epoch)}
						{@const cy = toY(bestEpoch.loss)}
						<text x={cx + 6} y={cy - 4} font-size="9" fill="#f59e0b" font-weight="600">
							#{bestEpoch.epoch}
							{bestEpoch.loss.toFixed(3)}
						</text>
					{/if}

					<!-- Running best convergence line -->
					{#if runningBestLine}
						<polyline
							points={runningBestLine}
							fill="none"
							stroke="#34d399"
							stroke-width="1.5"
							stroke-linejoin="round"
							opacity="0.8"
						/>
						<text x={PAD.left + 4} y={PAD.top + 10} font-size="8" fill="#34d399" opacity="0.8"
							>running best ↓</text
						>
					{/if}

					<!-- Axes -->
					<line
						x1={PAD.left}
						y1={PAD.top}
						x2={PAD.left}
						y2={PAD.top + plotH}
						stroke="currentColor"
						stroke-opacity="0.3"
						stroke-width="1"
					/>
					<line
						x1={PAD.left}
						y1={PAD.top + plotH}
						x2={PAD.left + plotW}
						y2={PAD.top + plotH}
						stroke="currentColor"
						stroke-opacity="0.3"
						stroke-width="1"
					/>
				</svg>
				{#if chartEpochs.length > clippedEpochs.length}
					<p class="mt-1 text-[10px] text-muted-foreground">
						{chartEpochs.length - clippedEpochs.length} epoch(s) with loss &gt; {CLIP_LOSS} clipped from
						chart.
					</p>
				{/if}
			</section>

			<!-- Top-20 table -->
			<section class="mt-8">
				<h2 class="mb-3 text-sm font-semibold">{t(lang, 'hyperopt.table.title')}</h2>
				<div class="overflow-x-auto rounded-xl border bg-card">
					<table class="w-full text-xs">
						<thead class="bg-secondary text-[11px] text-muted-foreground uppercase">
							<tr>
								{#each [['epoch', 'hyperopt.col.epoch'], ['loss', 'hyperopt.col.loss'], ['sharpe', 'hyperopt.col.sharpe'], ['calmar', 'hyperopt.col.calmar'], ['sortino', 'hyperopt.col.sortino'], ['profit_total', 'hyperopt.col.profit'], ['winrate', 'hyperopt.col.winrate'], ['total_trades', 'hyperopt.col.trades'], ['max_drawdown', 'hyperopt.col.maxdd']] as [SortKey, string][] as [k, lk], _i (_i)}
									<th
										class="cursor-pointer px-3 py-2.5 text-left whitespace-nowrap select-none hover:text-foreground"
										onclick={() => setSort(k)}
									>
										{t(lang, lk)}
										{#if sortKey === k}
											<span class="ml-0.5 opacity-70">{sortAsc ? '↑' : '↓'}</span>
										{/if}
									</th>
								{/each}
								<th class="px-3 py-2.5 text-left whitespace-nowrap"
									>{t(lang, 'hyperopt.col.params')}</th
								>
							</tr>
						</thead>
						<tbody>
							{#each top20 as e, _i (_i)}
								<tr
									class="border-t border-border hover:bg-accent/40"
									class:border-l-2={!!e.is_best}
									class:border-l-amber-400={!!e.is_best}
								>
									<td class="px-3 py-2 font-mono">{e.epoch}</td>
									<td class="px-3 py-2 font-mono font-semibold" class:text-amber-400={!!e.is_best}>
										{fmtN(e.loss, 4)}
									</td>
									<td class="px-3 py-2 font-mono">{fmtN(e.sharpe)}</td>
									<td class="px-3 py-2 font-mono">{fmtN(e.calmar)}</td>
									<td class="px-3 py-2 font-mono">{fmtN(e.sortino)}</td>
									<td class="px-3 py-2 font-mono">{fmtPct(e.profit_total)}</td>
									<td class="px-3 py-2 font-mono">{fmtPct(e.winrate)}</td>
									<td class="px-3 py-2 font-mono">{e.total_trades ?? '—'}</td>
									<td class="px-3 py-2 font-mono text-red-400">{fmtPct(e.max_drawdown)}</td>
									<td class="px-3 py-2">
										<div class="flex flex-wrap gap-1">
											{#if e.params}
												{#each Object.entries(e.params) as [pk, pv], _i (_i)}
													<span class="rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px]">
														{pk}={typeof pv === 'number'
															? Number.isInteger(pv)
																? pv
																: pv.toFixed(3)
															: pv}
													</span>
												{/each}
											{/if}
										</div>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</section>

			<!-- Parameter importance -->
			{#if paramImportance.length > 0}
				<section class="mt-8 rounded-xl border bg-card p-5">
					<h2 class="mb-4 text-sm font-semibold">
						Parameter Importance <span class="ml-1 text-xs font-normal text-muted-foreground"
							>(|Pearson corr| with loss · higher = more impact)</span
						>
						<ChartInfo metric="hyperoptParam" {lang} />
					</h2>
					<div class="space-y-2">
						{#each paramImportance as p, _i (_i)}
							{@const absCorr = Math.abs(p.corr)}
							{@const maxCorr = Math.abs(paramImportance[0].corr)}
							{@const barPct = ((absCorr / (maxCorr || 1)) * 100).toFixed(1)}
							<div class="flex items-center gap-3 text-xs">
								<span class="w-36 shrink-0 truncate font-mono text-muted-foreground" title={p.key}
									>{p.key}</span
								>
								<div class="relative h-5 flex-1 rounded-sm bg-muted/20">
									<div
										class="absolute inset-y-0 left-0 rounded-sm transition-all"
										style="width:{barPct}%; background:{p.corr > 0
											? 'var(--ch-loss)'
											: 'var(--ch-profit)'}"
									></div>
									<span
										class="absolute inset-y-0 left-2 flex items-center font-mono text-[10px] text-foreground"
										>{absCorr.toFixed(3)}</span
									>
								</div>
								<span class="w-20 shrink-0 text-right font-mono text-[10px] text-muted-foreground"
									>{p.corr > 0 ? '↑ loss' : '↓ loss'}</span
								>
							</div>
						{/each}
					</div>
					<p class="mt-2 text-[10px] text-muted-foreground">
						Green = higher value → lower loss (better) · Red = higher value → higher loss (worse) ·
						Based on {epochs.filter((e) => e.loss != null && e.loss <= CLIP_LOSS).length} valid epochs
					</p>
				</section>
			{/if}

			<!-- Params scatter grid -->
			{#if paramKeys.length > 0}
				<section class="mt-8">
					<h2 class="mb-3 text-sm font-semibold">{t(lang, 'hyperopt.scatter.title')}</h2>
					<div
						class="grid gap-4"
						style="grid-template-columns: repeat(auto-fill, minmax(200px, 1fr))"
					>
						{#each paramKeys as pk, _i (_i)}
							{@const pts = scatterPts(pk)}
							{#if pts.length > 1}
								<div class="rounded-xl border bg-card p-3">
									<p class="mb-2 truncate font-mono text-[11px] text-muted-foreground">{pk}</p>
									<svg
										viewBox="0 0 {S_W} {S_H}"
										width="100%"
										aria-label="Scatter for {pk}"
										class="overflow-visible"
									>
										<!-- axes -->
										<line
											x1={S_PAD.left}
											y1={S_PAD.top}
											x2={S_PAD.left}
											y2={S_H - S_PAD.bottom}
											stroke="currentColor"
											stroke-opacity="0.2"
											stroke-width="1"
										/>
										<line
											x1={S_PAD.left}
											y1={S_H - S_PAD.bottom}
											x2={S_W - S_PAD.right}
											y2={S_H - S_PAD.bottom}
											stroke="currentColor"
											stroke-opacity="0.2"
											stroke-width="1"
										/>
										<!-- axis labels -->
										<text
											x={S_PAD.left - 3}
											y={S_H - S_PAD.bottom}
											text-anchor="end"
											font-size="7"
											fill="currentColor"
											opacity="0.4">loss</text
										>
										<!-- points -->
										{#each pts as pt, _i (_i)}
											<circle
												cx={scatterX(pts, pt.x)}
												cy={scatterY(pts, pt.y)}
												r={pt.isBest ? 3.5 : 2}
												fill={pt.isBest ? '#f59e0b' : 'currentColor'}
												opacity={pt.isBest ? 1 : 0.4}
											>
												<title>{pk}={pt.x} loss={pt.y.toFixed(3)}</title>
											</circle>
										{/each}
									</svg>
								</div>
							{/if}
						{/each}
					</div>
				</section>
			{/if}
		{/if}
	{/if}

	{#if bestProfitCurve}
		{@const bpc = bestProfitCurve}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Best Profit Discovery Curve <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({currentStrategy} · {bpc.total} epochs · running-best profit)</span
				>
				<ChartInfo metric="leaderboard" {lang} />
			</h2>
			<svg viewBox="0 0 {bpc.W} {bpc.H}" class="w-full" style="height:{bpc.H}px;min-width:240px">
				<!-- zero line -->
				{#if bpc.zeroY >= bpc.PAD && bpc.zeroY <= bpc.H - bpc.PAD}
					<line
						x1={bpc.PAD}
						y1={bpc.zeroY}
						x2={bpc.W - bpc.PAD}
						y2={bpc.zeroY}
						stroke="var(--ch-rule-strong)"
						stroke-width="1"
						stroke-dasharray="4 3"
					/>
					<text x={bpc.PAD + 2} y={bpc.zeroY - 3} font-size="7" fill="var(--ch-rule-strong)"
						>0%</text
					>
				{/if}
				<!-- fill area under curve -->
				<polygon
					points="{bpc.PAD},{bpc.H - bpc.PAD} {bpc.polyline} {bpc.W - bpc.PAD},{bpc.H - bpc.PAD}"
					fill={bpc.finalBest >= 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)'}
				/>
				<polyline
					points={bpc.polyline}
					fill="none"
					stroke={bpc.finalBest >= 0 ? '#34d399' : '#f87171'}
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<!-- axis labels -->
				<text x={bpc.PAD} y={bpc.H} font-size="7" fill="var(--ch-rule-strong)"
					>epoch {bpc.eMin}</text
				>
				<text
					x={bpc.W - bpc.PAD}
					y={bpc.H}
					font-size="7"
					fill="var(--ch-rule-strong)"
					text-anchor="end">epoch {bpc.eMax}</text
				>
				<text
					x={bpc.W - bpc.PAD}
					y="10"
					font-size="7"
					fill="var(--ch-axis-strong)"
					text-anchor="end">{(bpc.finalBest * 100).toFixed(1)}%</text
				>
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Step-function of running-best profit across epochs ·
				{#if bpc.earlyDiscovery}
					<span class="text-amber-400">Most gains found early — diminishing returns</span>
				{:else}
					<span class="text-green-400/80"
						>Improvements spread through run — exploration still active</span
					>
				{/if}
			</p>
		</section>
	{/if}

	{#if epochBatchProfitability}
		{@const ebp = epochBatchProfitability}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-sm font-semibold">
					Epoch Batch Profitability <span class="ml-1 text-xs font-normal text-muted-foreground"
						>({currentStrategy} · {ebp.batches.length} batches of 20)</span
					>
					<ChartInfo metric="hyperoptEpoch" {lang} />
				</h2>
				<span class="font-mono text-xs {ebp.avg >= 0.5 ? 'text-green-400' : 'text-amber-400'}"
					>avg {(ebp.avg * 100).toFixed(0)}% profitable</span
				>
			</div>
			<svg viewBox="0 0 {ebp.W} {ebp.H}" class="w-full" style="height:{ebp.H}px;min-width:240px">
				{#if ebp.fiftyY > ebp.PAD && ebp.fiftyY < ebp.H - ebp.PAD}
					<line
						x1={ebp.PAD}
						y1={ebp.fiftyY}
						x2={ebp.W - ebp.PAD}
						y2={ebp.fiftyY}
						stroke="var(--ch-rule-strong)"
						stroke-width="1"
						stroke-dasharray="4 3"
					/>
					<text x={ebp.PAD + 2} y={ebp.fiftyY - 2} font-size="7" fill="var(--ch-rule-strong)"
						>50%</text
					>
				{/if}
				<polygon
					points="{ebp.PAD},{ebp.H - ebp.PAD} {ebp.polyline} {ebp.W - ebp.PAD},{ebp.H - ebp.PAD}"
					fill={ebp.avg >= 0.5 ? 'var(--ch-profit-light)' : 'var(--ch-warn-light)'}
				/>
				<polyline
					points={ebp.polyline}
					fill="none"
					stroke={ebp.avg >= 0.5 ? '#34d399' : '#facc15'}
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				{#each ebp.batches as b, i (i)}
					{@const bx = ebp.PAD + (i / Math.max(1, ebp.batches.length - 1)) * (ebp.W - ebp.PAD * 2)}
					{@const by = ebp.H - ebp.PAD - b.pct * (ebp.H - ebp.PAD * 2)}
					<circle
						cx={bx.toFixed(1)}
						cy={by.toFixed(1)}
						r="2.5"
						fill={b.pct >= 0.5 ? '#34d399' : '#facc15'}
					>
						<title>Epochs {b.label}: {(b.pct * 100).toFixed(0)}% profitable</title>
					</circle>
				{/each}
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Each dot = 20-epoch batch · y = % of epochs with profit_total &gt; 0 · rising trend =
				optimizer improving
			</p>
		</section>
	{/if}

	{#if crossStrategyBest && crossStrategyBest.length >= 2}
		<section class="mt-10 rounded-xl border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Cross-Strategy Best Epoch <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({crossStrategyBest.length} strategies · best loss epoch each)</span
				>
				<ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<div class="overflow-x-auto">
				<table class="w-full font-mono text-xs">
					<thead class="bg-secondary text-[10px] text-muted-foreground uppercase">
						<tr>
							<th class="px-3 py-2 text-left">Strategy</th>
							<th class="px-3 py-2 text-right">Epochs</th>
							<th class="px-3 py-2 text-right">Best #</th>
							<th class="px-3 py-2 text-right">Loss</th>
							<th class="px-3 py-2 text-right">Sharpe</th>
							<th class="px-3 py-2 text-right">Profit</th>
							<th class="px-3 py-2 text-right">WR</th>
							<th class="px-3 py-2 text-right">MaxDD</th>
						</tr>
					</thead>
					<tbody>
						{#each crossStrategyBest as row, _i (_i)}
							<tr
								class="border-t border-border hover:bg-accent/30 {row.strategy === currentStrategy
									? 'bg-accent/10'
									: ''}"
							>
								<td class="px-3 py-2 font-semibold">
									<button
										type="button"
										onclick={() => {
											activeStrategy = row.strategy;
										}}
										class="text-left transition-colors hover:text-primary"
									>
										{row.strategy}
										{#if row.strategy === currentStrategy}<span
												class="ml-1 text-[9px] text-muted-foreground">viewing</span
											>{/if}
									</button>
								</td>
								<td class="px-3 py-2 text-right text-muted-foreground">{row.totalEpochs}</td>
								<td class="px-3 py-2 text-right text-amber-400">{row.bestEpochNum ?? '—'}</td>
								<td
									class="px-3 py-2 text-right {row.best?.loss != null && row.best.loss < 0
										? 'text-green-400'
										: ''}">{row.best?.loss != null ? row.best.loss.toFixed(4) : '—'}</td
								>
								<td class="px-3 py-2 text-right"
									>{row.best?.sharpe != null ? row.best.sharpe.toFixed(2) : '—'}</td
								>
								<td
									class="px-3 py-2 text-right {(row.best?.profit_total ?? 0) > 0
										? 'text-green-400'
										: 'text-red-400'}"
									>{row.best?.profit_total != null
										? (row.best.profit_total * 100).toFixed(1) + '%'
										: '—'}</td
								>
								<td class="px-3 py-2 text-right"
									>{row.best?.winrate != null ? (row.best.winrate * 100).toFixed(1) + '%' : '—'}</td
								>
								<td class="px-3 py-2 text-right text-red-400"
									>{row.best?.max_drawdown != null
										? (row.best.max_drawdown * 100).toFixed(1) + '%'
										: '—'}</td
								>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Click a strategy name to switch the view above. Best epoch = lowest loss epoch per strategy.
			</p>
		</section>
	{/if}

	{#if epochProfitHist}
		{@const eph = epochProfitHist}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Epoch Profit Distribution <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({currentStrategy} · {eph.total} epochs)</span
				>
				<ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<svg viewBox="0 0 {eph.W} {eph.H}" class="w-full" style="height:{eph.H}px;min-width:240px">
				{#if eph.zeroX > 0 && eph.zeroX < eph.W}
					<line
						x1={eph.zeroX}
						y1="0"
						x2={eph.zeroX}
						y2={eph.H - 12}
						stroke="var(--ch-rule)"
						stroke-width="1"
						stroke-dasharray="3 2"
					/>
					<text x={eph.zeroX + 2} y="10" font-size="7" fill="var(--ch-rule-strong)">0%</text>
				{/if}
				{#if eph.bestX != null}
					<line
						x1={eph.bestX}
						y1="0"
						x2={eph.bestX}
						y2={eph.H - 12}
						stroke="var(--ch-warn)"
						stroke-width="1.5"
						stroke-dasharray="4 2"
					/>
					<text x={eph.bestX + 2} y="10" font-size="7" fill="var(--ch-warn)">best</text>
				{/if}
				{#each eph.buckets as b, i (i)}
					{#if b.count > 0}
						{@const bh = (b.count / eph.maxCount) * (eph.H - 16)}
						<rect
							x={i * eph.bw + 0.5}
							y={eph.H - 12 - bh}
							width={Math.max(1, eph.bw - 1)}
							height={bh}
							fill={b.lo >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
							rx="1"
						>
							<title>{b.lo.toFixed(1)}%: {b.count} epochs</title>
						</rect>
					{/if}
				{/each}
				{#each [0, 0.5, 1] as f, _i (_i)}
					<text
						x={f * eph.W}
						y={eph.H}
						text-anchor="middle"
						font-size="7"
						fill="var(--ch-rule-strong)">{(eph.mn + f * (eph.mx - eph.mn)).toFixed(0)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Green = profitable epoch · amber line = best epoch · {eph.buckets.filter(
					(b) => b.lo >= 0 && b.count > 0
				).length}/{eph.buckets.filter((b) => b.count > 0).length} bins above zero
			</p>
		</section>
	{/if}

	{#if lossVsProfitScatter}
		{@const lvp = lossVsProfitScatter}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Loss vs Profit Scatter <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({currentStrategy} · {lvp.dots.length} epochs)</span
				>
				<ChartInfo metric="scatter" {lang} />
			</h2>
			<svg viewBox="0 0 {lvp.W} {lvp.H}" class="w-full" style="height:{lvp.H}px;min-width:280px">
				<!-- zero profit line -->
				{#if lvp.zeroY >= lvp.PAD && lvp.zeroY <= lvp.H - lvp.PAD}
					<line
						x1={lvp.PAD}
						y1={lvp.zeroY}
						x2={lvp.W - lvp.PAD}
						y2={lvp.zeroY}
						stroke="var(--ch-rule-strong)"
						stroke-width="1"
						stroke-dasharray="4 3"
					/>
					<text x={lvp.PAD + 2} y={lvp.zeroY - 2} font-size="7" fill="var(--ch-rule-strong)"
						>0%</text
					>
				{/if}
				{#each lvp.dots as d, _i (_i)}
					<circle
						cx={d.x.toFixed(1)}
						cy={d.y.toFixed(1)}
						r={d.best ? 4 : 2.5}
						fill={d.best
							? '#facc15'
							: d.y < lvp.zeroY
								? 'var(--ch-profit-light)'
								: 'var(--ch-loss-light)'}
						stroke={d.best ? '#fde047' : 'none'}
						stroke-width="1"
					>
						<title>{d.tip}</title>
					</circle>
				{/each}
				<text x={lvp.PAD} y={lvp.H - 2} font-size="7" fill="var(--ch-rule-strong)"
					>loss {lvp.lMin.toFixed(2)}</text
				>
				<text
					x={lvp.W - lvp.PAD}
					y={lvp.H - 2}
					font-size="7"
					fill="var(--ch-rule-strong)"
					text-anchor="end">loss {lvp.lMax.toFixed(2)}</text
				>
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				x = loss (lower=better) · y = profit% (higher=better) · yellow = best epoch · green =
				profitable
			</p>
		</section>
	{/if}

	{#if paramRangeStats && paramRangeStats.length > 0}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Parameter Search Range <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({currentStrategy} · {epochs.length} epochs)</span
				>
				<ChartInfo metric="hyperoptParam" {lang} />
			</h2>
			<div class="overflow-x-auto">
				<table class="w-full text-xs">
					<thead>
						<tr
							class="border-b border-border text-left text-[10px] text-muted-foreground uppercase"
						>
							<th class="px-3 py-2">Parameter</th>
							<th class="px-3 py-2 text-right">Min</th>
							<th class="px-3 py-2 text-right">Median</th>
							<th class="px-3 py-2 text-right">Mean</th>
							<th class="px-3 py-2 text-right">Max</th>
							<th class="px-3 py-2">Range</th>
						</tr>
					</thead>
					<tbody class="font-mono">
						{#each paramRangeStats as p, _i (_i)}
							{@const span = p.max - p.min || 0.001}
							{@const medPct = ((p.median - p.min) / span) * 100}
							<tr class="border-b border-border/40 hover:bg-accent/20">
								<td class="px-3 py-2 font-semibold text-foreground">{p.key}</td>
								<td class="px-3 py-2 text-right text-muted-foreground"
									>{Number.isInteger(p.min) ? p.min : p.min.toFixed(3)}</td
								>
								<td class="px-3 py-2 text-right text-indigo-300"
									>{Number.isInteger(p.median) ? p.median : p.median.toFixed(3)}</td
								>
								<td class="px-3 py-2 text-right text-muted-foreground"
									>{p.mean.toFixed(Number.isInteger(p.min) ? 1 : 3)}</td
								>
								<td class="px-3 py-2 text-right text-muted-foreground"
									>{Number.isInteger(p.max) ? p.max : p.max.toFixed(3)}</td
								>
								<td class="w-32 px-3 py-2">
									<div class="relative h-3 rounded bg-muted/30">
										<div
											class="absolute inset-y-0 left-0 rounded bg-indigo-500/40"
											style="width:100%"
										></div>
										<div
											class="absolute top-0 h-full w-0.5 rounded bg-indigo-300"
											style="left:{medPct.toFixed(1)}%"
										></div>
									</div>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Indigo line = median value · bar = full search range explored
			</p>
		</section>
	{/if}

	{#if drawdownDistribution}
		{@const ddd = drawdownDistribution}
		<section class="mt-6 rounded-lg border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Drawdown Distribution <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({ddd.total} epochs · avg {ddd.avg.toFixed(1)}%)</span
				>
				<ChartInfo metric="maxDrawdown" {lang} />
			</h2>
			<div class="flex h-20 items-end gap-2">
				{#each ddd.buckets as b, _i (_i)}
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
				Distribution of max drawdown explored by the optimizer · green = low DD · avg {ddd.avg.toFixed(
					1
				)}%
			</p>
		</section>
	{/if}

	{#if winrateTradeScatter}
		{@const wts = winrateTradeScatter}
		<section class="mt-6 rounded-lg border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Win Rate vs Trade Count <span class="ml-1 text-xs font-normal text-muted-foreground"
					>({wts.dots.length} epochs)</span
				>
				<ChartInfo metric="winRate" {lang} />
			</h2>
			<svg viewBox="0 0 {wts.W} {wts.H}" class="w-full" style="height:{wts.H}px">
				{#if wts.fiftyY > wts.PAD && wts.fiftyY < wts.H - wts.PAD}
					<line
						x1={wts.PAD}
						y1={wts.fiftyY}
						x2={wts.W - wts.PAD}
						y2={wts.fiftyY}
						stroke="var(--ch-rule)"
						stroke-width="1"
						stroke-dasharray="3 2"
					/>
					<text x={wts.PAD + 2} y={wts.fiftyY - 2} font-size="7" fill="var(--ch-rule-strong)"
						>WR 50%</text
					>
				{/if}
				{#each wts.dots as d, _i (_i)}
					<circle
						cx={d.x.toFixed(1)}
						cy={d.y.toFixed(1)}
						r={d.best ? 4.5 : 2.5}
						fill={d.best
							? 'var(--ch-warn)'
							: (d.profit ?? 0) > 0
								? 'var(--ch-profit-light)'
								: 'var(--ch-loss-light)'}
						stroke={d.best ? '#fde047' : 'none'}
						stroke-width="1"
					>
						<title
							>trades:{d.trades} · WR:{d.wr.toFixed(1)}% · profit:{d.profit != null
								? (d.profit * 100).toFixed(1) + '%'
								: '—'}{d.best ? ' ★ BEST' : ''}</title
						>
					</circle>
				{/each}
				<text x={wts.PAD} y={wts.H - 3} font-size="7" fill="var(--ch-rule)">{wts.xMin} trades</text>
				<text
					x={wts.W - wts.PAD}
					y={wts.H - 3}
					font-size="7"
					fill="var(--ch-rule)"
					text-anchor="end">{wts.xMax}</text
				>
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				x = trade count · y = win rate % · green = profitable epoch · yellow ★ = best epoch
			</p>
		</section>
	{/if}

	{#if tradeCountVsProfit}
		{@const tcp = tradeCountVsProfit}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Trade Count vs Profit Scatter
				<span class="ml-1 text-xs font-normal text-muted-foreground">
					({tcp.dots.length} epochs · r = {tcp.corr >= 0 ? '+' : ''}{tcp.corr.toFixed(2)})
				</span>
				<ChartInfo metric="tradeCount" {lang} />
			</h2>
			<svg viewBox="0 0 {tcp.W} {tcp.H}" class="w-full" style="height:{tcp.H}px">
				<line
					x1={tcp.PAD}
					y1={tcp.zeroY.toFixed(1)}
					x2={tcp.W - tcp.PAD}
					y2={tcp.zeroY.toFixed(1)}
					stroke="var(--ch-rule)"
					stroke-width="1"
					stroke-dasharray="3 2"
				/>
				{#each tcp.dots as d, _i (_i)}
					<circle
						cx={d.x.toFixed(1)}
						cy={d.y.toFixed(1)}
						r={d.isBest ? 4.5 : 2.5}
						fill={d.isBest
							? 'var(--ch-warn)'
							: d.profit > 0
								? 'var(--ch-profit-light)'
								: 'var(--ch-loss-light)'}
						stroke={d.isBest ? '#fde047' : 'none'}
						stroke-width="1"
					>
						<title
							>{d.trades} trades · {d.profit >= 0 ? '+' : ''}{(d.profit * 100).toFixed(2)}%{d.isBest
								? ' ★ best'
								: ''}</title
						>
					</circle>
				{/each}
				<text x={tcp.PAD} y={tcp.H - 3} font-size="7" fill="var(--ch-rule)">{tcp.xMin}</text>
				<text
					x={tcp.W - tcp.PAD}
					y={tcp.H - 3}
					font-size="7"
					fill="var(--ch-rule)"
					text-anchor="end">{tcp.xMax} trades</text
				>
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				x = trade count per epoch · y = profit% · Pearson r = {tcp.corr >= 0
					? '+'
					: ''}{tcp.corr.toFixed(2)} · yellow ★ = best epoch
			</p>
		</section>
	{/if}

	{#if epochLossConvergence}
		{@const elc = epochLossConvergence}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-2 text-sm font-semibold">
				Loss Convergence Curve
				<span class="ml-1 text-xs font-normal text-muted-foreground">
					({elc.total} epochs · best at epoch {elc.bestEpoch} · loss {elc.vMin.toFixed(3)})
				</span>
				<ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<svg viewBox="0 0 {elc.W} {elc.H}" class="w-full" style="height:{elc.H}px">
				<polyline
					points={elc.polyline}
					fill="none"
					stroke="var(--ch-violet-strong)"
					stroke-width="1.5"
				/>
				<text x={elc.PAD} y={elc.PAD + 8} font-size="7" fill="var(--ch-rule-strong)"
					>{elc.vMax.toFixed(2)}</text
				>
				<text x={elc.PAD} y={elc.H - 2} font-size="7" fill="var(--ch-rule-strong)"
					>{elc.vMin.toFixed(3)} best</text
				>
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Running minimum loss over epochs — steep early drop = fast convergence · flat tail =
				diminishing returns
			</p>
		</section>
	{/if}

	{#if bestEpochParamComparison}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Best-Epoch Param Fingerprint
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(median param value: all epochs vs best epochs · dot = median)</span
				>
				<ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<div class="space-y-2">
				{#each bestEpochParamComparison as r, _i (_i)}
					<div class="flex items-center gap-2">
						<span class="w-28 shrink-0 truncate font-mono text-[10px]" title={r.key}>{r.key}</span>
						<div class="relative h-5 flex-1 overflow-hidden rounded-sm bg-muted/20">
							<!-- all median marker -->
							<div
								class="absolute top-0 bottom-0 w-0.5 rounded-full bg-indigo-400/70"
								style="left:{(((r.allMed - r.min) / r.range) * 100).toFixed(1)}%"
							></div>
							<!-- best median marker -->
							{#if r.bestMed != null}
								<div
									class="absolute top-0 bottom-0 w-0.5 rounded-full bg-yellow-400/90"
									style="left:{(((r.bestMed - r.min) / r.range) * 100).toFixed(1)}%"
								></div>
							{/if}
						</div>
						<span class="w-28 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
							all {r.allMed.toFixed(1)} · ★{r.bestMed != null ? r.bestMed.toFixed(1) : '—'}
						</span>
					</div>
				{/each}
			</div>
			<div class="mt-2 flex gap-4 text-[10px] text-muted-foreground">
				<span class="flex items-center gap-1"
					><span class="inline-block h-3 w-0.5 rounded bg-indigo-400/70"></span>All epochs median</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-3 w-0.5 rounded bg-yellow-400/90"></span>Best epochs median</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Bar = full param range · line position = median · offset = best epochs prefer higher/lower
				values
			</p>
		</section>
	{/if}

	{#if winrateBucketProfit}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Win Rate vs Profit by Bucket
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(avg profit_total per WR tier · {epochs.length} epochs)</span
				>
				<ChartInfo metric="winRate" {lang} />
			</h2>
			<div class="flex items-end gap-3" style="height:80px">
				{#each winrateBucketProfit as b, _i (_i)}
					<div class="flex flex-1 flex-col items-center justify-end gap-1">
						{#if b.avgProfit != null}
							<span
								class="font-mono text-[9px]"
								class:text-green-400={b.avgProfit >= 0}
								class:text-red-400={b.avgProfit < 0}
							>
								{b.avgProfit >= 0 ? '+' : ''}{(b.avgProfit * 100).toFixed(1)}%
							</span>
							<div
								class="w-full rounded-t-sm"
								style="height:{Math.max(2, b.barPct * 0.6)}px; background:{b.avgProfit >= 0
									? 'var(--ch-profit-light)'
									: 'var(--ch-loss-light)'}"
							></div>
						{/if}
						<span class="text-center font-mono text-[10px] leading-tight font-semibold"
							>{b.label}</span
						>
						<span class="font-mono text-[9px] text-muted-foreground">{b.count}ep</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Does higher win rate reliably predict higher profit? · each bar = avg profit across epochs
				in that WR bucket
			</p>
		</section>
	{/if}

	{#if holdingVsProfit}
		{@const hvp = holdingVsProfit}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-2 text-sm font-semibold">
				Avg Hold Duration vs Profit
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>({hvp.dots.length} epochs · r = {hvp.corr >= 0 ? '+' : ''}{hvp.corr.toFixed(2)})</span
				>
				<ChartInfo metric="holdingTime" {lang} />
			</h2>
			<svg viewBox="0 0 {hvp.W} {hvp.H}" class="w-full" style="height:{hvp.H}px">
				<line
					x1={hvp.PAD}
					y1={hvp.zeroY.toFixed(1)}
					x2={hvp.W - hvp.PAD}
					y2={hvp.zeroY.toFixed(1)}
					stroke="var(--ch-rule)"
					stroke-width="1"
					stroke-dasharray="3 2"
				/>
				{#each hvp.dots as d, _i (_i)}
					<circle
						cx={d.x.toFixed(1)}
						cy={d.y.toFixed(1)}
						r={d.isBest ? 4.5 : 2.5}
						fill={d.isBest
							? 'var(--ch-warn)'
							: d.profit > 0
								? 'var(--ch-profit-light)'
								: 'var(--ch-loss-light)'}
						stroke={d.isBest ? '#fde047' : 'none'}
						stroke-width="1"
					>
						<title
							>{d.hours.toFixed(1)}h avg hold · profit {d.profit >= 0 ? '+' : ''}{(
								d.profit * 100
							).toFixed(2)}%{d.isBest ? ' ★ best' : ''}</title
						>
					</circle>
				{/each}
				<text x={hvp.PAD} y={hvp.H - 3} font-size="7" fill="var(--ch-rule)"
					>{hvp.xMin.toFixed(0)}h</text
				>
				<text
					x={hvp.W - hvp.PAD}
					y={hvp.H - 3}
					font-size="7"
					fill="var(--ch-rule)"
					text-anchor="end">{hvp.xMax.toFixed(0)}h</text
				>
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				x = avg holding hours per epoch · y = total profit · Pearson r = {hvp.corr >= 0
					? '+'
					: ''}{hvp.corr.toFixed(2)} · yellow ★ = best epoch
			</p>
		</section>
	{/if}

	{#if epochSortinoBuckets}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Avg Profit by Sortino Bucket
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(does higher Sortino predict higher profit?)</span
				>
				<ChartInfo metric="sortino" {lang} />
			</h2>
			<div class="flex items-end gap-3" style="height:72px">
				{#each epochSortinoBuckets as b, _i (_i)}
					<div
						class="flex flex-1 flex-col items-center justify-end gap-0.5"
						title="{b.label}: {b.count} epochs · avg {b.avg != null
							? (b.avg >= 0 ? '+' : '') + (b.avg * 100).toFixed(1) + '%'
							: '—'}"
					>
						{#if b.avg != null}
							<div
								class="w-full rounded-t-sm"
								style="height:{Math.max(2, b.barPct * 0.6)}px; background:{b.avg >= 0
									? 'var(--ch-profit)'
									: 'var(--ch-loss-light)'}"
							></div>
						{/if}
					</div>
				{/each}
			</div>
			<div class="mt-1 flex gap-3">
				{#each epochSortinoBuckets as b, _i (_i)}
					<div class="flex-1 text-center">
						<div class="font-mono text-[10px] font-semibold">{b.label}</div>
						<div class="font-mono text-[9px] text-muted-foreground">{b.count}ep</div>
						{#if b.avg != null}
							<div
								class="font-mono text-[9px]"
								class:text-green-400={b.avg >= 0}
								class:text-red-400={b.avg < 0}
							>
								{b.avg >= 0 ? '+' : ''}{(b.avg * 100).toFixed(1)}%
							</div>
						{/if}
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Each column = avg total profit across epochs in that Sortino range · higher Sortino buckets
				should yield more profit if metric is predictive
			</p>
		</section>
	{/if}

	{#if epochDrawdownProfile}
		{@const edp = epochDrawdownProfile}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-2 text-sm font-semibold">
				Drawdown vs Profit Risk Map
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>({edp.dots.length} epochs · r = {edp.corr >= 0 ? '+' : ''}{edp.corr.toFixed(2)})</span
				>
				<ChartInfo metric="maxDrawdown" {lang} />
			</h2>
			<svg viewBox="0 0 {edp.W} {edp.H}" class="w-full" style="height:{edp.H}px">
				<line
					x1={edp.PAD}
					y1={edp.zeroY.toFixed(1)}
					x2={edp.W - edp.PAD}
					y2={edp.zeroY.toFixed(1)}
					stroke="var(--ch-rule)"
					stroke-width="1"
					stroke-dasharray="3 2"
				/>
				{#each edp.dots as d, _i (_i)}
					<circle
						cx={d.x.toFixed(1)}
						cy={d.y.toFixed(1)}
						r={d.isBest ? 5 : 2.5}
						fill={d.isBest
							? 'var(--ch-warn)'
							: d.dd < 15
								? 'var(--ch-profit-light)'
								: d.dd < 30
									? 'var(--ch-warn-light)'
									: 'var(--ch-loss-light)'}
						stroke={d.isBest ? '#fde047' : 'none'}
						stroke-width="1"
					>
						<title
							>DD {d.dd.toFixed(1)}% · profit {d.profit >= 0 ? '+' : ''}{(d.profit * 100).toFixed(
								2
							)}%{d.isBest ? ' ★ best' : ''}</title
						>
					</circle>
				{/each}
				<text x={edp.PAD} y={edp.H - 3} font-size="7" fill="var(--ch-rule)">0%</text>
				<text
					x={edp.W - edp.PAD}
					y={edp.H - 3}
					font-size="7"
					fill="var(--ch-rule)"
					text-anchor="end">{edp.xMax.toFixed(0)}% DD</text
				>
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				x = max drawdown % · y = total profit · green = DD &lt;15% · yellow = 15–30% · red = DD
				&gt;30% · ★ = best epoch · r = {edp.corr >= 0 ? '+' : ''}{edp.corr.toFixed(2)}
			</p>
		</section>
	{/if}

	{#if sqnVsProfit}
		{@const svp = sqnVsProfit}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-2 text-sm font-semibold">
				SQN vs Profit
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>({svp.dots.length} epochs · r = {svp.corr >= 0 ? '+' : ''}{svp.corr.toFixed(2)})</span
				>
				<ChartInfo metric="scatter" {lang} />
			</h2>
			<svg viewBox="0 0 {svp.W} {svp.H}" class="w-full" style="height:{svp.H}px">
				<line
					x1={svp.PAD}
					y1={svp.zeroY.toFixed(1)}
					x2={svp.W - svp.PAD}
					y2={svp.zeroY.toFixed(1)}
					stroke="var(--ch-rule)"
					stroke-width="1"
					stroke-dasharray="3 2"
				/>
				{#each svp.dots as d, _i (_i)}
					<circle
						cx={d.x.toFixed(1)}
						cy={d.y.toFixed(1)}
						r={d.isBest ? 5 : 2.5}
						fill={d.isBest
							? 'var(--ch-warn)'
							: d.sqn >= 2
								? 'var(--ch-profit-light)'
								: d.sqn >= 0
									? 'var(--ch-warn-light)'
									: 'var(--ch-loss-light)'}
						stroke={d.isBest ? '#fde047' : 'none'}
						stroke-width="1"
					>
						<title
							>SQN {d.sqn.toFixed(2)} · profit {d.profit >= 0 ? '+' : ''}{(d.profit * 100).toFixed(
								2
							)}%{d.isBest ? ' ★ best' : ''}</title
						>
					</circle>
				{/each}
				<text x={svp.PAD} y={svp.H - 3} font-size="7" fill="var(--ch-rule)"
					>{svp.xMin.toFixed(1)}</text
				>
				<text
					x={svp.W - svp.PAD}
					y={svp.H - 3}
					font-size="7"
					fill="var(--ch-rule)"
					text-anchor="end">SQN {svp.xMax.toFixed(1)}</text
				>
			</svg>
			<p class="mt-1 text-[10px] text-muted-foreground">
				x = System Quality Number · y = total profit · green SQN ≥2 (good) · yellow 0–2 · r = {svp.corr >=
				0
					? '+'
					: ''}{svp.corr.toFixed(2)} · ★ = best epoch
			</p>
		</section>
	{/if}

	{#if calmarBuckets}
		<section class="mt-6 rounded-lg border bg-card p-5">
			<h2 class="mb-3 text-sm font-semibold">
				Calmar Ratio vs Avg Profit
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(avg profit_total per Calmar bucket · do higher-Calmar epochs earn more?)</span
				>
				<ChartInfo metric="calmar" {lang} />
			</h2>
			<div class="flex items-end gap-2" style="height:72px">
				{#each calmarBuckets as b, _i (_i)}
					<div
						class="flex flex-1 flex-col items-center justify-end gap-1"
						title="Calmar {b.label}: {b.count} epochs · avg profit {b.avg != null
							? (b.avg >= 0 ? '+' : '') + (b.avg * 100).toFixed(1) + '%'
							: '—'}"
					>
						{#if b.avg != null}
							<span class="font-mono text-[8px] text-muted-foreground"
								>{(b.avg * 100).toFixed(0)}%</span
							>
							<div
								class="w-full rounded-t-sm"
								style="height:{Math.max(2, b.barPct * 0.56)}px; background:{b.avg >= 0
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
				{#each calmarBuckets as b, _i (_i)}
					<span class="flex-1 text-center">{b.label}</span>
				{/each}
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Calmar = annualized return / max drawdown · green = profitable avg · n = epoch count per
				bucket
			</p>
		</section>
	{/if}
	{#if holdingTimeHistogram}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Epoch Holding Time Distribution
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(how epochs spread across avg holding duration)</span
				>
				<ChartInfo metric="holdingTime" {lang} />
			</h2>
			<div class="mt-3 flex items-end gap-1" style="height:72px">
				{#each holdingTimeHistogram as b, _i (_i)}
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
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				{#each holdingTimeHistogram as b, i (i)}
					{#if i === 0 || i === 4 || i === 7}
						<span>{b.label}</span>
					{/if}
				{/each}
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Distribution of avg holding hours across hyperopt epochs — reveals whether optimizer favors
				short or long trades
			</p>
		</section>
	{/if}
	{#if epochSqnTimeline}
		{@const est = epochSqnTimeline}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Rolling SQN Trend
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(10-epoch rolling avg System Quality Number · {est.trend >= 0
						? '↑ improving'
						: '↓ declining'})</span
				>
				<ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<svg viewBox="0 0 {est.W} {est.H}" class="w-full" style="height:64px">
				<line
					x1={est.PAD}
					x2={est.W - est.PAD}
					y1={est.zeroY}
					y2={est.zeroY}
					stroke="var(--ch-rule)"
					stroke-width="1"
					stroke-dasharray="3 3"
				/>
				<polyline
					points={est.polyline}
					fill="none"
					stroke={est.trend >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					stroke-width="1.5"
				/>
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>SQN {est.mn.toFixed(2)}</span><span>→ epochs →</span><span>{est.mx.toFixed(2)}</span>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				SQN &gt;2 = good system · upward trend = optimizer finding consistently higher-quality
				parameter sets
			</p>
		</section>
	{/if}
	{#if epochDrawdownTrend}
		{@const edt = epochDrawdownTrend}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Rolling Drawdown Trend
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(10-epoch rolling avg max drawdown% · {edt.trend <= 0
						? '↓ improving'
						: '↑ worsening'})</span
				>
				<ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<svg viewBox="0 0 {edt.W} {edt.H}" class="w-full" style="height:64px">
				<polyline
					points={edt.polyline}
					fill="none"
					stroke={edt.trend <= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					stroke-width="1.5"
				/>
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>DD {edt.mn.toFixed(1)}%</span><span>→ epochs →</span><span>{edt.mx.toFixed(1)}%</span>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Downward trend = optimizer converging to lower-drawdown parameters · green = improving risk
				control
			</p>
		</section>
	{/if}
	{#if epochSortinoCalmarScatter}
		{@const scs = epochSortinoCalmarScatter}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Sortino vs Calmar Scatter
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(each dot = one epoch · color = profit · Pearson r {scs.corr >= 0
						? '+'
						: ''}{scs.corr.toFixed(2)})</span
				>
				<ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<svg viewBox="0 0 {scs.W} {scs.H}" class="mt-3 w-full" style="height:120px">
				{#if scs.zeroX != null}
					<line
						x1={scs.zeroX}
						x2={scs.zeroX}
						y1={scs.PAD}
						y2={scs.H - scs.PAD}
						stroke="var(--ch-rule)"
						stroke-width="1"
						stroke-dasharray="3 3"
					/>
				{/if}
				{#if scs.zeroY != null}
					<line
						x1={scs.PAD}
						x2={scs.W - scs.PAD}
						y1={scs.zeroY}
						y2={scs.zeroY}
						stroke="var(--ch-rule)"
						stroke-width="1"
						stroke-dasharray="3 3"
					/>
				{/if}
				{#each scs.dots as d, _i (_i)}
					<circle
						cx={d.x}
						cy={d.y}
						r={d.isBest ? 5 : 3}
						style="fill:{d.color}"
						opacity={d.isBest ? 1 : 0.65}
					/>
					{#if d.isBest}
						<circle
							cx={d.x}
							cy={d.y}
							r={7}
							fill="none"
							stroke="var(--ch-warn)"
							stroke-width="1.5"
						/>
					{/if}
				{/each}
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>Sortino {scs.xMin.toFixed(1)}</span><span>→ Sortino →</span><span
					>{scs.xMax.toFixed(1)}</span
				>
			</div>
			<div class="mt-0.5 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>↑ Calmar {scs.yMin.toFixed(1)} → {scs.yMax.toFixed(1)}</span>
				<span class="flex gap-3">
					<span style="color:var(--ch-profit-strong)">■ high profit</span>
					<span style="color:var(--ch-warn)">■ mid</span>
					<span style="color:var(--ch-loss-strong)">■ low</span>
				</span>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Sortino (downside risk) vs Calmar (drawdown risk) · strong r = optimizer finds consistent
				risk profile · ★ = best epoch
			</p>
		</section>
	{/if}
	{#if epochWinrateTrend}
		{@const ewt = epochWinrateTrend}
		<section class="mt-8 rounded-lg border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Rolling Win Rate Trend
				<span class="ml-1 text-xs font-normal text-muted-foreground"
					>(10-epoch rolling avg win rate · latest {(ewt.latest * 100).toFixed(1)}% · {ewt.trend >=
					0
						? '↑ improving'
						: '↓ declining'})</span
				>
				<ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<svg viewBox="0 0 {ewt.W} {ewt.H}" class="mt-3 w-full" style="height:64px">
				{#if ewt.fiftyY != null}
					<line
						x1={ewt.PAD}
						x2={ewt.W - ewt.PAD}
						y1={ewt.fiftyY}
						y2={ewt.fiftyY}
						stroke="var(--ch-rule)"
						stroke-width="1"
						stroke-dasharray="4 3"
					/>
				{/if}
				<polyline
					points={ewt.polyline}
					fill="none"
					stroke={ewt.trend >= 0 ? 'var(--ch-profit-strong)' : 'var(--ch-loss)'}
					stroke-width="1.5"
				/>
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>WR {(ewt.mn * 100).toFixed(1)}%</span><span>→ epochs →</span><span
					>{(ewt.mx * 100).toFixed(1)}%</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				10-epoch rolling average win rate · dashed = 50% break-even · upward trend = optimizer
				finding higher win-rate parameter sets
			</p>
		</section>
	{/if}

	{#if epochExplorationDensity}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Optimizer Exploration Density <ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Unique param combos per 20-epoch window — higher = broader search, lower = converging
			</p>
			<div class="mt-3 flex items-end gap-1.5" style="height:72px">
				{#each epochExplorationDensity as w, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-0.5">
						<span class="font-mono text-[8px] text-muted-foreground">{w.unique}</span>
						<div
							class="w-full rounded-sm"
							style="height:{w.barPct}%; background:rgba({Math.round(
								60 + w.diversity * 140
							)},{Math.round(100 + w.diversity * 97)},200,0.75); min-height:{w.unique > 0
								? 2
								: 0}px"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[8px] text-muted-foreground">
				{#each epochExplorationDensity as w, _i (_i)}
					<span class="flex-1 truncate text-center">{w.label}</span>
				{/each}
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Blue intensity = diversity ratio · fading bars = optimizer converging on a region · useful
				for diagnosing premature convergence
			</p>
		</section>
	{/if}

	{#if epochBestEverTimeline}
		{@const ebet = epochBestEverTimeline}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Best-Ever Profit Convergence <ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Running maximum profit found across all epochs · late gain {ebet.lateGain >= 0 ? '+' : ''}{(
					ebet.lateGain * 100
				).toFixed(1)}% in second half
			</p>
			<svg viewBox="0 0 {ebet.W} {ebet.H}" class="mt-2 w-full" style="height:60px">
				<polyline
					points={ebet.poly}
					fill="none"
					stroke="var(--ch-violet-strong)"
					stroke-width="1.5"
				/>
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{(ebet.mn * 100).toFixed(1)}%</span><span>→ epochs →</span><span
					>best: {(ebet.mx * 100).toFixed(1)}%</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Flat plateau = optimizer stuck · steep late climb = good gains still possible · helps decide
				whether to run more epochs
			</p>
		</section>
	{/if}

	{#if epochCalmarDistribution}
		{@const ecd = epochCalmarDistribution}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Epoch Calmar Distribution <ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Histogram of Calmar ratios across {ecd.total} epochs · median {ecd.median.toFixed(2)}
			</p>
			<div class="mt-3 flex items-end gap-1" style="height:72px">
				{#each ecd.buckets as b, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-0.5">
						<span class="font-mono text-[8px] text-muted-foreground"
							>{b.count > 0 ? b.count : ''}</span
						>
						<div
							class="w-full rounded-sm"
							style="height:{b.barPct}%; background:var(--ch-teal); min-height:{b.count > 0
								? 2
								: 0}px"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>0</span><span>→ Calmar →</span><span
					>{ecd.buckets[ecd.buckets.length - 1].label.split('–')[1]}</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Right-skewed = optimizer finding high-Calmar configs · mass on left = most trials have poor
				risk-adjusted returns
			</p>
		</section>
	{/if}

	{#if epochHoldingTimeProfile}
		{@const ehp = epochHoldingTimeProfile}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Epoch Avg Holding Time Distribution <ChartInfo metric="holdingTime" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Histogram of average holding hours per epoch across {ehp.total} epochs · median {ehp.median.toFixed(
					1
				)}h
			</p>
			<div class="mt-3 flex items-end gap-1" style="height:72px">
				{#each ehp.buckets as b, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-0.5">
						<span class="font-mono text-[8px] text-muted-foreground"
							>{b.count > 0 ? b.count : ''}</span
						>
						<div
							class="w-full rounded-sm"
							style="height:{b.barPct}%; background:var(--ch-teal); min-height:{b.count > 0
								? 2
								: 0}px"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{ehp.mn.toFixed(0)}h</span><span>→ avg holding hours →</span><span
					>{ehp.mx.toFixed(0)}h</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Left peak = short-term configs · right peak = swing/position configs · multi-modal =
				optimizer exploring multiple trade-duration regimes
			</p>
		</section>
	{/if}

	{#if epochProfitVsDrawdown}
		{@const epvd = epochProfitVsDrawdown}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Epoch Profit vs Max Drawdown <ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Each dot = one epoch · X = max drawdown · Y = total profit · top-left = ideal (low DD, high
				profit)
			</p>
			<svg viewBox="0 0 {epvd.W} {epvd.H}" class="mt-2 w-full" style="height:80px">
				<line
					x1={epvd.PAD}
					y1={epvd.H -
						epvd.PAD -
						((0 - epvd.yMin) / (epvd.yMax - epvd.yMin)) * (epvd.H - epvd.PAD * 2)}
					x2={epvd.W - epvd.PAD}
					y2={epvd.H -
						epvd.PAD -
						((0 - epvd.yMin) / (epvd.yMax - epvd.yMin)) * (epvd.H - epvd.PAD * 2)}
					stroke="var(--ch-rule)"
					stroke-width="0.5"
				/>
				{#each epvd.dots as d, _i (_i)}
					<circle
						cx={d.cx}
						cy={d.cy}
						r={d.best ? 3.5 : 1.8}
						fill={d.best
							? 'var(--ch-warn)'
							: d.pos
								? 'var(--ch-profit-light)'
								: 'var(--ch-loss-light)'}
					/>
				{/each}
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>DD {(epvd.xMin * 100).toFixed(1)}%</span><span>→ max drawdown →</span><span
					>{(epvd.xMax * 100).toFixed(1)}%</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Gold = best-ever epochs · green = profitable configs · cluster in top-left = efficient
				risk-return frontier · avoid bottom-right (high DD, low profit)
			</p>
		</section>
	{/if}

	{#if epochWinrateSqnScatter}
		{@const ewss = epochWinrateSqnScatter}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Epoch Winrate vs SQN Scatter <ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Each dot = one epoch · X = win rate · Y = SQN · top-right = high win rate + high system
				quality
			</p>
			<svg viewBox="0 0 {ewss.W} {ewss.H}" class="mt-2 w-full" style="height:80px">
				<line
					x1={ewss.PAD}
					y1={ewss.H -
						ewss.PAD -
						((0 - ewss.yMin) / (ewss.yMax - ewss.yMin)) * (ewss.H - ewss.PAD * 2)}
					x2={ewss.W - ewss.PAD}
					y2={ewss.H -
						ewss.PAD -
						((0 - ewss.yMin) / (ewss.yMax - ewss.yMin)) * (ewss.H - ewss.PAD * 2)}
					stroke="var(--ch-rule)"
					stroke-width="0.5"
				/>
				{#each ewss.dots as d, _i (_i)}
					<circle
						cx={d.cx}
						cy={d.cy}
						r={d.best ? 3.5 : 2}
						fill={d.best
							? 'var(--ch-warn)'
							: d.pos
								? 'var(--ch-profit-light)'
								: 'var(--ch-loss-light)'}
					/>
				{/each}
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>WR {(ewss.xMin * 100).toFixed(0)}%</span><span>→ win rate →</span><span
					>{(ewss.xMax * 100).toFixed(0)}%</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Gold = best-ever epochs · green = SQN≥0 · top-right cluster = ideal configs combining high
				win rate with system quality
			</p>
		</section>
	{/if}

	{#if epochSqnDistribution}
		{@const esd = epochSqnDistribution}
		<section class="mt-8 rounded-xl border border-border bg-card p-5">
			<h2 class="text-base font-semibold">
				Epoch SQN Distribution <ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<p class="mt-0.5 text-xs text-muted-foreground">
				Histogram of System Quality Number across {esd.total} epochs · median {esd.median.toFixed(
					2
				)}
			</p>
			<div class="mt-3 flex items-end gap-1" style="height:72px">
				{#each esd.buckets as b, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-0.5">
						<span class="font-mono text-[8px] text-muted-foreground"
							>{b.count > 0 ? b.count : ''}</span
						>
						<div
							class="w-full rounded-sm"
							style="height:{b.barPct}%; background:{b.lo >= 0
								? 'var(--ch-profit)'
								: 'var(--ch-loss)'}; min-height:{b.count > 0 ? 2 : 0}px"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{esd.mn.toFixed(1)}</span><span>→ SQN →</span><span>{esd.mx.toFixed(1)}</span>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				SQN &gt;1.6 = tradeable · &gt;2 = good · green bars (SQN≥0) = positive · right mass =
				optimizer finding good-quality systems
			</p>
		</section>
	{/if}

	{#if epochBestCalmarTimeline}
		{@const ect = epochBestCalmarTimeline}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Best Calmar Timeline <ChartInfo metric="calmar" {lang} />
			</h2>
			<p class="mb-2 text-[11px] text-muted-foreground">
				Best Calmar ratio found so far as optimization progresses · plateau = optimizer converging ·
				final {ect.positive ? '+' : ''}{ect.mx.toFixed(2)}
			</p>
			<svg viewBox="0 0 {ect.W} {ect.H}" class="w-full" style="height:64px">
				<polyline
					points={ect.poly}
					fill="none"
					stroke={ect.positive ? 'var(--ch-violet-strong)' : 'var(--ch-loss-strong)'}
					stroke-width="1.5"
				/>
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>epoch 1</span><span>← optimization progress →</span><span>epoch {ect.total}</span>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Calmar = annual return / max drawdown · rising curve = optimizer improving risk-adjusted
				quality · early plateau = search space exhausted
			</p>
		</section>
	{/if}

	{#if epochProfitDistribution}
		{@const epd = epochProfitDistribution}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Epoch Profit Distribution <ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Histogram of total profit% across all hyperopt epochs · median {epd.median.toFixed(1)}% · {epd.positive}/{epd.total}
				profitable
			</p>
			<div class="flex items-end gap-1" style="height:64px">
				{#each epd.buckets as b, _i (_i)}
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
				<span>{epd.buckets[0].label}</span><span>← epoch profit →</span><span
					>{epd.buckets[epd.buckets.length - 1].label}</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Right mass = optimizer finding many profitable configs · left tail = loss-making parameter
				space · narrow distribution = constrained search space
			</p>
		</section>
	{/if}

	{#if epochWinrateDistribution}
		{@const ewd = epochWinrateDistribution}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Epoch Win Rate Distribution <ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<p class="mb-3 text-[11px] text-muted-foreground">
				Histogram of win rate% across all hyperopt epochs · median {ewd.median.toFixed(1)}% · {ewd.above50}/{ewd.total}
				above 50%
			</p>
			<div class="flex items-end gap-1" style="height:64px">
				{#each ewd.buckets as b, _i (_i)}
					<div class="flex flex-1 flex-col items-center gap-0.5">
						<span class="font-mono text-[7px] text-muted-foreground"
							>{b.count > 0 ? b.count : ''}</span
						>
						<div
							class="w-full rounded-sm"
							style="height:{b.barPct}%; background:{b.good
								? 'var(--ch-profit)'
								: 'var(--ch-loss-light)'}; min-height:{b.count > 0 ? 2 : 0}px"
						></div>
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>0%</span><span>← win rate →</span><span>100%</span>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Green = &gt;50% WR · right-skewed = optimizer finding high-frequency winning configs · WR
				alone insufficient without profit factor context
			</p>
		</section>
	{/if}

	{#if epochCalmarVsHolding}
		{@const ech = epochCalmarVsHolding}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Calmar vs Holding Time Scatter <ChartInfo metric="holdingTime" {lang} />
			</h2>
			<p class="mb-2 text-[11px] text-muted-foreground">
				Log-scaled holding time (x) vs Calmar ratio (y) · gold = best epochs · upper-left = high
				Calmar with short holding
			</p>
			<svg viewBox="0 0 {ech.W} {ech.H}" class="w-full" style="height:100px">
				{#if ech.zero_y >= ech.PAD && ech.zero_y <= ech.H - ech.PAD}
					<line
						x1={ech.PAD}
						y1={ech.zero_y}
						x2={ech.W - ech.PAD}
						y2={ech.zero_y}
						stroke="var(--ch-axis-faint)"
						stroke-width="0.6"
						stroke-dasharray="3,2"
					/>
				{/if}
				{#each ech.dots as d, _i (_i)}
					<circle
						cx={d.cx}
						cy={d.cy}
						r={d.best ? 3.5 : 2}
						fill={d.best
							? 'var(--ch-warn)'
							: d.positive
								? 'var(--ch-profit-light)'
								: 'var(--ch-loss-light)'}
						><title>Calmar {d.calmar.toFixed(2)}, {d.hours.toFixed(0)}h holding</title></circle
					>
				{/each}
			</svg>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{ech.hMin.toFixed(0)}h</span><span>← holding time (log scale) →</span><span
					>{ech.hMax.toFixed(0)}h</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Calmar = annual return / max drawdown · longer holding often reduces Calmar via larger
				drawdowns · optimal zone = high Calmar, moderate holding
			</p>
		</section>
	{/if}

	{#if epochLossDistribution}
		{@const eld = epochLossDistribution}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-sm font-semibold">
				Loss Distribution: Best vs All Epochs <ChartInfo metric="leaderboard" {lang} />
			</h2>
			<p class="mb-2 text-[11px] text-muted-foreground">
				Histogram of hyperopt loss values · gold = best-flagged epochs · grey = all others · lower
				loss = better optimizer score
			</p>
			<div class="flex items-end gap-0.5" style="height:64px">
				{#each eld.restBuckets, i (i)}
					<div class="flex flex-1 flex-col items-center gap-0" style="position:relative">
						<div
							class="w-full rounded-sm"
							style="height:{eld.restBuckets[i]
								.pct}%; background:var(--ch-axis-muted); min-height:{eld.restBuckets[i].count > 0
								? 1
								: 0}px; position:absolute; bottom:0"
						></div>
						{#if eld.bestBuckets[i].count > 0}
							<div
								class="w-full rounded-sm"
								style="height:{eld.bestBuckets[i]
									.pct}%; background:var(--ch-warn); min-height:2px; position:absolute; bottom:0; z-index:1"
							></div>
						{/if}
					</div>
				{/each}
			</div>
			<div class="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
				<span>{eld.lo.toFixed(2)}</span><span>← loss value →</span><span>{eld.hi.toFixed(2)}</span>
			</div>
			<div class="mt-1 flex gap-4 text-[9px]">
				<span class="flex items-center gap-1"
					><span class="inline-block h-2 w-3 rounded-sm" style="background:var(--ch-warn)"
					></span>Best avg {eld.avgBest.toFixed(3)}</span
				>
				<span class="flex items-center gap-1"
					><span class="inline-block h-2 w-3 rounded-sm bg-muted"></span>Rest avg {eld.avgRest.toFixed(
						3
					)}</span
				>
			</div>
			<p class="mt-1 text-[10px] text-muted-foreground">
				Gold bars = where best epochs cluster in loss space · left-skewed gold = optimizer reliably
				finds low-loss configurations · wide spread = noisy loss landscape
			</p>
		</section>
	{/if}
	{#if epochParamBestRanges}
		<section class="rounded-lg border border-border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Best-Epoch Parameter Ranges vs Rest <ChartInfo metric="hyperoptEpoch" {lang} />
			</h2>
			<div class="overflow-x-auto">
				<table class="w-full text-xs">
					<thead>
						<tr class="border-b border-border text-left text-muted-foreground">
							<th class="pr-4 pb-2">Parameter</th>
							<th class="pr-4 pb-2 text-right">Best Avg</th>
							<th class="pr-4 pb-2 text-right">Rest Avg</th>
							<th class="pr-4 pb-2 text-right">Best Min</th>
							<th class="pr-4 pb-2 text-right">Best Max</th>
							<th class="pb-2 text-right">N Best</th>
						</tr>
					</thead>
					<tbody>
						{#each epochParamBestRanges as row, _i (_i)}
							{@const diff = row.avgRest != null ? row.avgBest - row.avgRest : null}
							{@const diffColor =
								diff == null
									? '#888'
									: diff > 0
										? 'var(--ch-profit-strong)'
										: 'var(--ch-loss-strong)'}
							<tr class="border-b border-border/40 last:border-0">
								<td class="py-1.5 pr-4 font-mono">{row.param}</td>
								<td class="py-1.5 pr-4 text-right font-mono" style="color:var(--ch-warn)"
									>{row.avgBest.toFixed(4)}</td
								>
								<td class="py-1.5 pr-4 text-right font-mono text-muted-foreground"
									>{row.avgRest != null ? row.avgRest.toFixed(4) : '—'}</td
								>
								<td class="py-1.5 pr-4 text-right font-mono text-muted-foreground"
									>{row.minB.toFixed(4)}</td
								>
								<td class="py-1.5 pr-4 text-right font-mono text-muted-foreground"
									>{row.maxB.toFixed(4)}</td
								>
								<td class="py-1.5 text-right" style="color:{diffColor}">{row.n}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Gold = avg param value in best epochs · compare to rest to find which param ranges the
				optimizer favors · narrow best-range = stable optimum · wide = insensitive param
			</p>
		</section>
	{/if}
	{#if epochTradeCountComparison}
		{@const etc = epochTradeCountComparison}
		<section class="rounded-lg border border-border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Trade Count: Best vs Non-Best Epochs <ChartInfo metric="tradeCount" {lang} />
			</h2>
			<div class="space-y-4">
				{#each [{ label: 'Best epochs', s: etc.best, color: 'var(--ch-warn)' }, { label: 'Non-best epochs', s: etc.rest, color: 'var(--ch-violet)' }] as row, _i (_i)}
					<div>
						<div class="mb-1 flex justify-between text-[10px] text-muted-foreground">
							<span class="font-medium" style="color:{row.color}">{row.label}</span>
							<span class="font-mono"
								>med={row.s.med} · p25={row.s.p25} · p75={row.s.p75} · n={row.s.n}</span
							>
						</div>
						<div class="relative h-5 w-full overflow-hidden rounded-sm bg-muted">
							<div
								class="absolute h-full rounded-sm opacity-30"
								style="left:{((row.s.min / etc.maxVal) * 100).toFixed(1)}%; width:{(
									((row.s.max - row.s.min) / etc.maxVal) *
									100
								).toFixed(1)}%; background:{row.color}"
							></div>
							<div
								class="absolute h-full rounded-sm"
								style="left:{((row.s.p25 / etc.maxVal) * 100).toFixed(1)}%; width:{(
									((row.s.p75 - row.s.p25) / etc.maxVal) *
									100
								).toFixed(1)}%; background:{row.color}"
							></div>
							<div
								class="absolute top-0 h-full w-0.5 rounded"
								style="left:{((row.s.med / etc.maxVal) * 100).toFixed(
									1
								)}%; background:white; opacity:0.9"
							></div>
						</div>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Box = p25–p75 interquartile range · white line = median · faint fill = min–max range · best
				epochs trading more = high-frequency config · less = selective entry optimization
			</p>
		</section>
	{/if}
	{#if epochMaxDrawdownComparison}
		{@const emd = epochMaxDrawdownComparison}
		<section class="rounded-lg border border-border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">
				Max Drawdown: Best vs Non-Best Epochs <ChartInfo metric="maxDrawdown" {lang} />
			</h2>
			<div class="space-y-4">
				{#each [{ label: 'Best epochs', s: emd.best, color: 'var(--ch-warn)' }, { label: 'Non-best epochs', s: emd.rest, color: 'var(--ch-loss)' }] as row, _i (_i)}
					<div>
						<div class="mb-1 flex justify-between text-[10px] text-muted-foreground">
							<span class="font-medium" style="color:{row.color}">{row.label}</span>
							<span class="font-mono"
								>med={row.s.med.toFixed(3)} · p25={row.s.p25.toFixed(3)} · p75={row.s.p75.toFixed(
									3
								)} · n={row.s.n}</span
							>
						</div>
						<div class="relative h-5 w-full overflow-hidden rounded-sm bg-muted">
							<div
								class="absolute h-full rounded-sm opacity-30"
								style="left:{((row.s.min / emd.maxVal) * 100).toFixed(1)}%; width:{(
									((row.s.max - row.s.min) / emd.maxVal) *
									100
								).toFixed(1)}%; background:{row.color}"
							></div>
							<div
								class="absolute h-full rounded-sm"
								style="left:{((row.s.p25 / emd.maxVal) * 100).toFixed(1)}%; width:{(
									((row.s.p75 - row.s.p25) / emd.maxVal) *
									100
								).toFixed(1)}%; background:{row.color}"
							></div>
							<div
								class="absolute top-0 h-full w-0.5"
								style="left:{((row.s.med / emd.maxVal) * 100).toFixed(
									1
								)}%; background:white; opacity:0.9"
							></div>
						</div>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] text-muted-foreground">
				Gold = best epoch drawdown range · red = non-best · gold shifted left = optimizer finds
				lower-drawdown configs · overlapping ranges = drawdown not a key differentiator
			</p>
		</section>
	{/if}
	{#if epochBestWinrateTimeline}
		<section class="rounded-xl border border-border bg-card p-4">
			<h2 class="mb-1 text-sm font-semibold">
				Running Best Win Rate over Epochs <ChartInfo metric="winRate" {lang} />
			</h2>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Gold line = best win rate discovered so far · grey = all epoch win rates · {epochBestWinrateTimeline.total}
				epochs · best achieved: {(epochBestWinrateTimeline.finalBest * 100).toFixed(1)}%
			</p>
			<svg viewBox="0 0 {epochBestWinrateTimeline.W} {epochBestWinrateTimeline.H}" class="w-full">
				{#if epochBestWinrateTimeline.fiftyY !== null}
					<line
						x1="0"
						y1={epochBestWinrateTimeline.fiftyY}
						x2={epochBestWinrateTimeline.W}
						y2={epochBestWinrateTimeline.fiftyY}
						stroke="var(--ch-axis-muted)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				<polyline
					points={epochBestWinrateTimeline.allPoly}
					fill="none"
					stroke="var(--ch-axis-muted)"
					stroke-width="1"
				/>
				<polyline
					points={epochBestWinrateTimeline.bestPoly}
					fill="none"
					stroke="var(--ch-warn)"
					stroke-width="2"
				/>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Monotone gold step = running best · grey cloud = all epochs · dashed at 50% win rate · steep
				early rise = fast convergence on win rate
			</p>
		</section>
	{/if}
	{#if epochBestSortinoTimeline}
		<section class="rounded-xl border border-border bg-card p-4">
			<h2 class="mb-1 text-sm font-semibold">
				Running Best Sortino over Epochs <ChartInfo metric="sortino" {lang} />
			</h2>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Teal line = best Sortino discovered so far · grey = all epoch Sortino values · {epochBestSortinoTimeline.total}
				epochs · best achieved: {epochBestSortinoTimeline.finalBest.toFixed(2)}
			</p>
			<svg viewBox="0 0 {epochBestSortinoTimeline.W} {epochBestSortinoTimeline.H}" class="w-full">
				{#if epochBestSortinoTimeline.zeroY !== null}
					<line
						x1="0"
						y1={epochBestSortinoTimeline.zeroY}
						x2={epochBestSortinoTimeline.W}
						y2={epochBestSortinoTimeline.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				<polyline
					points={epochBestSortinoTimeline.allPoly}
					fill="none"
					stroke="var(--ch-axis-muted)"
					stroke-width="1"
				/>
				<polyline
					points={epochBestSortinoTimeline.bestPoly}
					fill="none"
					stroke="var(--ch-teal-strong)"
					stroke-width="2"
				/>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Monotone teal step = running best Sortino · grey cloud = all epochs · Sortino penalizes only
				downside volatility · complements win rate and Calmar timelines
			</p>
		</section>
	{/if}

	{#if epochLossVsTradeCount}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Epoch Loss vs Trade Count</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Scatter of optimizer loss score against trade count per epoch · reveals whether low-loss
				solutions cluster at high or low trade frequencies · gold = best epochs
			</p>
			<svg viewBox="0 0 {epochLossVsTradeCount.W} {epochLossVsTradeCount.H}" class="w-full">
				{#if epochLossVsTradeCount.zeroY !== null}
					<line
						x1="0"
						y1={epochLossVsTradeCount.zeroY}
						x2={epochLossVsTradeCount.W}
						y2={epochLossVsTradeCount.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				{#each epochLossVsTradeCount.dots as d, _i (_i)}
					<circle
						cx={d.cx}
						cy={d.cy}
						r={d.best ? 3 : 1.8}
						fill={d.best ? 'var(--ch-warn)' : 'var(--ch-violet-light)'}
					/>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{epochLossVsTradeCount.total} epochs · x=trade count ({epochLossVsTradeCount.tMin}–{epochLossVsTradeCount.tMax})
				· y=loss ({epochLossVsTradeCount.lMin.toFixed(2)}–{epochLossVsTradeCount.lMax.toFixed(2)}) ·
				gold = is_best epochs
			</p>
		</section>
	{/if}

	{#if epochHoldingVsWinrate}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Avg Holding Time vs Win Rate</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Scatter of avg holding hours vs win rate % per epoch · reveals whether longer-held trades
				improve accuracy · gold = is_best epochs
			</p>
			<svg viewBox="0 0 {epochHoldingVsWinrate.W} {epochHoldingVsWinrate.H}" class="w-full">
				{#each epochHoldingVsWinrate.dots as d, _i (_i)}
					<circle
						cx={d.cx}
						cy={d.cy}
						r={d.best ? 3 : 1.8}
						fill={d.best ? 'var(--ch-warn)' : 'var(--ch-teal-light)'}
					/>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{epochHoldingVsWinrate.total} epochs · x=holding hours ({epochHoldingVsWinrate.hMin}h–{epochHoldingVsWinrate.hMax}h)
				· y=win rate ({epochHoldingVsWinrate.wMin}%–{epochHoldingVsWinrate.wMax}%) · teal = all
				epochs · gold = best
			</p>
		</section>
	{/if}

	{#if epochProfitPerTrade}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Profit per Trade Distribution</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Histogram of profit_total ÷ total_trades per epoch · shows whether hyperopt is finding
				solutions with high per-trade efficiency · right skew = better
			</p>
			<svg viewBox="0 0 {epochProfitPerTrade.W} {epochProfitPerTrade.H}" class="w-full">
				{#if epochProfitPerTrade.zeroX !== null}
					<line
						x1={epochProfitPerTrade.zeroX}
						y1="0"
						x2={epochProfitPerTrade.zeroX}
						y2={epochProfitPerTrade.H}
						stroke="var(--ch-axis-muted)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				{#each epochProfitPerTrade.bars as b, _i (_i)}
					<rect
						x={b.x}
						y={epochProfitPerTrade.H - epochProfitPerTrade.PAD - b.h}
						width={b.w}
						height={b.h}
						fill={b.positive ? 'var(--ch-profit)' : 'var(--ch-loss)'}
						rx="1"
					/>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{epochProfitPerTrade.total} epochs · range [{epochProfitPerTrade.mn}–{epochProfitPerTrade.mx}]
				· avg per-trade profit = {epochProfitPerTrade.avg.toFixed(4)} · green = positive · red = negative
				per-trade
			</p>
		</section>
	{/if}

	{#if epochSortinoVsWinrate}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Sortino vs Win Rate per Epoch</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Scatter of Sortino ratio vs win rate % per epoch · top-right = high accuracy AND strong
				downside protection · gold = is_best epochs
			</p>
			<svg viewBox="0 0 {epochSortinoVsWinrate.W} {epochSortinoVsWinrate.H}" class="w-full">
				{#if epochSortinoVsWinrate.zeroY !== null}
					<line
						x1="0"
						y1={epochSortinoVsWinrate.zeroY}
						x2={epochSortinoVsWinrate.W}
						y2={epochSortinoVsWinrate.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				{#each epochSortinoVsWinrate.dots as d, _i (_i)}
					<circle
						cx={d.cx}
						cy={d.cy}
						r={d.best ? 3 : 1.8}
						fill={d.best ? 'var(--ch-warn)' : 'var(--ch-violet-light)'}
					/>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{epochSortinoVsWinrate.total} epochs · {epochSortinoVsWinrate.topRight} in top-right quadrant
				· WR [{epochSortinoVsWinrate.wMin}%–{epochSortinoVsWinrate.wMax}%] · Sortino [{epochSortinoVsWinrate.sMin}–{epochSortinoVsWinrate.sMax}]
				· gold = best
			</p>
		</section>
	{/if}

	{#if epochCalmarVsSortino}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Epoch Calmar vs Sortino</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Each dot = one hyperopt epoch · x = Calmar ratio · y = Sortino ratio · top-right = both
				drawdown-adjusted metrics strong · gold = is_best epoch
			</p>
			<svg viewBox="0 0 {epochCalmarVsSortino.W} {epochCalmarVsSortino.H}" class="w-full">
				{#if epochCalmarVsSortino.zeroX !== null}
					<line
						x1={epochCalmarVsSortino.zeroX}
						y1="0"
						x2={epochCalmarVsSortino.zeroX}
						y2={epochCalmarVsSortino.H}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				{#if epochCalmarVsSortino.zeroY !== null}
					<line
						x1="0"
						y1={epochCalmarVsSortino.zeroY}
						x2={epochCalmarVsSortino.W}
						y2={epochCalmarVsSortino.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				{#each epochCalmarVsSortino.dots as d, _i (_i)}
					<circle
						cx={d.cx}
						cy={d.cy}
						r={d.best ? 3 : 1.8}
						fill={d.best ? 'var(--ch-warn)' : 'var(--ch-teal-light)'}
					/>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{epochCalmarVsSortino.total} epochs · {epochCalmarVsSortino.aligned} with Calmar&gt;0 &amp; Sortino&gt;0
				· Calmar [{epochCalmarVsSortino.cMin}–{epochCalmarVsSortino.cMax}] · Sortino [{epochCalmarVsSortino.sMin}–{epochCalmarVsSortino.sMax}]
				· gold = best epoch
			</p>
		</section>
	{/if}

	{#if epochDrawdownVsProfit}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Epoch Max Drawdown vs Profit</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				Each dot = one hyperopt epoch · x = max drawdown % · y = total profit · ideal = left side
				(low DD) + high y · gold = is_best epoch
			</p>
			<svg viewBox="0 0 {epochDrawdownVsProfit.W} {epochDrawdownVsProfit.H}" class="w-full">
				{#if epochDrawdownVsProfit.zeroY !== null}
					<line
						x1="0"
						y1={epochDrawdownVsProfit.zeroY}
						x2={epochDrawdownVsProfit.W}
						y2={epochDrawdownVsProfit.zeroY}
						stroke="var(--ch-axis-faint)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				{#each epochDrawdownVsProfit.dots as d, _i (_i)}
					<circle
						cx={d.cx}
						cy={d.cy}
						r={d.best ? 3 : 1.8}
						fill={d.best ? 'var(--ch-warn)' : 'var(--ch-loss-light)'}
					/>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{epochDrawdownVsProfit.total} epochs · {epochDrawdownVsProfit.topLeft} in low-DD/high-profit zone
				· DD [{epochDrawdownVsProfit.dMin}%–{epochDrawdownVsProfit.dMax}%] · profit [{epochDrawdownVsProfit.pMin}–{epochDrawdownVsProfit.pMax}]
				· gold = best
			</p>
		</section>
	{/if}

	{#if epochCalmarConvergence}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-1 text-sm font-semibold">Calmar 10-Epoch Rolling Avg</h3>
			<p class="mb-2 text-[10px] text-muted-foreground">
				10-epoch rolling average of Calmar ratio as hyperopt progresses · rising = search improving
				· flat = plateau · falling = overfitting region
			</p>
			<svg viewBox="0 0 {epochCalmarConvergence.W} {epochCalmarConvergence.H}" class="w-full">
				{#if epochCalmarConvergence.zeroY !== null}
					<line
						x1="0"
						y1={epochCalmarConvergence.zeroY}
						x2={epochCalmarConvergence.W}
						y2={epochCalmarConvergence.zeroY}
						stroke="var(--ch-axis-muted)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				<polyline
					points={epochCalmarConvergence.polyline}
					fill="none"
					stroke="var(--ch-warn)"
					stroke-width="2"
				/>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{epochCalmarConvergence.count} data points · latest avg Calmar {epochCalmarConvergence.latest}
				· range [{epochCalmarConvergence.mn}–{epochCalmarConvergence.mx}] · smooth = stable
				convergence
			</p>
		</section>
	{/if}

	{#if epochSQNBestTimeline}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Running Best SQN — System Quality Number
			</h3>
			<svg
				viewBox="0 0 {epochSQNBestTimeline.W} {epochSQNBestTimeline.H}"
				class="w-full"
				style="height:80px"
			>
				{#if epochSQNBestTimeline.zeroY !== null}
					<line
						x1="0"
						y1={epochSQNBestTimeline.zeroY}
						x2={epochSQNBestTimeline.W}
						y2={epochSQNBestTimeline.zeroY}
						stroke="var(--ch-axis-muted)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				<polyline
					points={epochSQNBestTimeline.polyline}
					fill="none"
					stroke="var(--ch-teal-strong)"
					stroke-width="2"
					stroke-linejoin="round"
				/>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{epochSQNBestTimeline.count} epochs · best SQN so far: {epochSQNBestTimeline.latest} ({epochSQNBestTimeline.qual})
				· SQN&gt;2.5 = excellent · Van Tharp scale
			</p>
		</section>
	{/if}

	{#if epochBestProfitFactorTimeline}
		<section class="mt-6 rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Total Profit per Epoch + Running Best
			</h3>
			<svg
				viewBox="0 0 {epochBestProfitFactorTimeline.W} {epochBestProfitFactorTimeline.H}"
				class="w-full"
				style="height:80px"
			>
				{#if epochBestProfitFactorTimeline.zeroY !== null}
					<line
						x1="0"
						y1={epochBestProfitFactorTimeline.zeroY}
						x2={epochBestProfitFactorTimeline.W}
						y2={epochBestProfitFactorTimeline.zeroY}
						stroke="var(--ch-axis-muted)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				<polyline
					points={epochBestProfitFactorTimeline.polyline}
					fill="none"
					stroke="var(--ch-violet-light)"
					stroke-width="1"
					stroke-linejoin="round"
				/>
				<polyline
					points={epochBestProfitFactorTimeline.bestPolyline}
					fill="none"
					stroke="var(--ch-profit-strong)"
					stroke-width="2"
					stroke-linejoin="round"
				/>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{epochBestProfitFactorTimeline.count} epochs · latest: {epochBestProfitFactorTimeline.latest}
				· best ever: {epochBestProfitFactorTimeline.best} · green = running best · indigo = each epoch
			</p>
		</section>
	{/if}

	{#if epochWinrateConvergence}
		<section class="rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win Rate Convergence
			</h3>
			<svg
				viewBox="0 0 {epochWinrateConvergence.W} {epochWinrateConvergence.H}"
				class="w-full"
				style="height:80px"
			>
				{#if epochWinrateConvergence.y50 !== null}
					<line
						x1="0"
						y1={epochWinrateConvergence.y50}
						x2={epochWinrateConvergence.W}
						y2={epochWinrateConvergence.y50}
						stroke="var(--ch-axis-muted)"
						stroke-width="1"
						stroke-dasharray="4,3"
					/>
				{/if}
				<polyline
					points={epochWinrateConvergence.rawPolyline}
					fill="none"
					stroke="var(--ch-violet-light)"
					stroke-width="1"
					stroke-linejoin="round"
				/>
				<polyline
					points={epochWinrateConvergence.bestPolyline}
					fill="none"
					stroke="var(--ch-profit-strong)"
					stroke-width="2"
					stroke-linejoin="round"
				/>
			</svg>
			<div class="mt-1 flex justify-between text-[9px] text-muted-foreground">
				<span>epoch 1</span>
				<span
					>latest WR: {epochWinrateConvergence.latest}% · best: {epochWinrateConvergence.best}% · {epochWinrateConvergence.count}
					epochs · green = running best</span
				>
				<span>epoch {epochWinrateConvergence.count}</span>
			</div>
		</section>
	{/if}

	{#if epochMaxDrawdownTrend}
		<section class="rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Max Drawdown per Epoch
			</h3>
			<svg
				viewBox="0 0 {epochMaxDrawdownTrend.W} {epochMaxDrawdownTrend.H}"
				class="w-full"
				style="height:70px"
			>
				<polyline
					points={epochMaxDrawdownTrend.polyline}
					fill="none"
					stroke="var(--ch-loss-light)"
					stroke-width="1"
					stroke-linejoin="round"
				/>
				<polyline
					points={epochMaxDrawdownTrend.minPolyline}
					fill="none"
					stroke="var(--ch-profit-strong)"
					stroke-width="2"
					stroke-linejoin="round"
				/>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{epochMaxDrawdownTrend.count} epochs · latest DD: {epochMaxDrawdownTrend.latest} · best (lowest)
				ever: {epochMaxDrawdownTrend.best} · green = running minimum · red = each epoch · lower is better
			</p>
		</section>
	{/if}

	{#if epochHoldingTimeDistribution}
		<section class="rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Holding Time Distribution Across Epochs
			</h3>
			<svg
				viewBox="0 0 {epochHoldingTimeDistribution.W} {epochHoldingTimeDistribution.H}"
				class="w-full"
				style="height:70px"
			>
				{#each epochHoldingTimeDistribution.counts as b, i (i)}
					{@const x =
						epochHoldingTimeDistribution.PAD + i * (epochHoldingTimeDistribution.barW + 1)}
					{@const barH = Math.max(
						1,
						(b.cnt / epochHoldingTimeDistribution.maxCnt) *
							(epochHoldingTimeDistribution.H - epochHoldingTimeDistribution.PAD * 2 - 8)
					)}
					<rect
						{x}
						y={epochHoldingTimeDistribution.H - 8 - barH}
						width={epochHoldingTimeDistribution.barW}
						height={barH}
						rx="1"
						fill="var(--ch-warn)"
					/>
					{#if i === 0 || i === epochHoldingTimeDistribution.counts.length - 1}
						<text
							x={x + epochHoldingTimeDistribution.barW / 2}
							y={epochHoldingTimeDistribution.H - 1}
							text-anchor="middle"
							font-size="7"
							fill="var(--ch-axis)">{b.label}h</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{epochHoldingTimeDistribution.count} epochs · avg holding: {epochHoldingTimeDistribution.avg}h
				· distribution shows what holding durations the optimizer explores most
			</p>
		</section>
	{/if}

	{#if epochLossFunctionHeatmap}
		<section class="rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Loss Function vs Win Rate Scatter ({epochLossFunctionHeatmap.count} epochs)
			</h3>
			<svg
				viewBox="0 0 {epochLossFunctionHeatmap.W} {epochLossFunctionHeatmap.H}"
				class="w-full"
				style="height:90px"
			>
				{#each epochLossFunctionHeatmap.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r={d.r} fill={d.color} stroke="none" />
				{/each}
			</svg>
			<div class="mt-1 flex justify-between text-[9px] text-muted-foreground">
				<span>← low loss</span>
				<span>x=loss value · y=win rate % · yellow=best epochs · indigo=all epochs</span>
				<span>high loss →</span>
			</div>
		</section>
	{/if}

	{#if epochCalmarTimeline}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Calmar Ratio Timeline ({epochCalmarTimeline.count} epochs)
			</h3>
			<svg
				viewBox="0 0 {epochCalmarTimeline.W} {epochCalmarTimeline.H}"
				class="w-full"
				style="height:90px"
			>
				{#each [0.5, 1, 2] as lvl, _i (_i)}
					{@const y =
						epochCalmarTimeline.H -
						epochCalmarTimeline.PAD -
						(lvl / epochCalmarTimeline.maxC) *
							(epochCalmarTimeline.H - epochCalmarTimeline.PAD * 2)}
					<line
						x1={epochCalmarTimeline.PAD}
						y1={y}
						x2={epochCalmarTimeline.W - epochCalmarTimeline.PAD}
						y2={y}
						stroke="var(--ch-axis-faint)"
						stroke-width="0.6"
					/>
					<text
						x={epochCalmarTimeline.PAD - 2}
						y={y + 3}
						text-anchor="end"
						font-size="6"
						fill="var(--ch-axis-muted)">{lvl}</text
					>
				{/each}
				<polyline
					points={epochCalmarTimeline.polyline}
					fill="none"
					stroke="var(--ch-violet-light)"
					stroke-width="1"
				/>
				<polyline
					points={epochCalmarTimeline.bestLine}
					fill="none"
					stroke="var(--ch-profit-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				{#each epochCalmarTimeline.pts as p, _i (_i)}
					{#if p.isBest}
						<circle cx={p.cx} cy={p.cy} r="3" fill="var(--ch-warn)" />
					{/if}
				{/each}
			</svg>
			<div class="mt-1 flex justify-between text-[9px] text-muted-foreground">
				<span>epoch 1</span>
				<span>indigo=per-epoch Calmar · green=running best · yellow=best epochs</span>
				<span>epoch {epochCalmarTimeline.count}</span>
			</div>
		</section>
	{/if}

	{#if epochSqnVsCalmarScatter}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				SQN vs Calmar Scatter ({epochSqnVsCalmarScatter.count} epochs)
			</h3>
			<svg
				viewBox="0 0 {epochSqnVsCalmarScatter.W} {epochSqnVsCalmarScatter.H}"
				class="w-full"
				style="height:120px"
			>
				<line
					x1={epochSqnVsCalmarScatter.zeroX}
					y1={epochSqnVsCalmarScatter.PAD}
					x2={epochSqnVsCalmarScatter.zeroX}
					y2={epochSqnVsCalmarScatter.H - epochSqnVsCalmarScatter.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.8"
					stroke-dasharray="3,2"
				/>
				{#each epochSqnVsCalmarScatter.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r={d.isBest ? 4 : 2} fill={d.color} />
				{/each}
			</svg>
			<div class="mt-1 flex justify-between text-[9px] text-muted-foreground">
				<span>← negative SQN</span>
				<span>x=SQN · y=Calmar · yellow=best epochs · indigo=Calmar≥1.5 · dashed=SQN zero</span>
				<span>positive SQN →</span>
			</div>
		</section>
	{/if}

	{#if epochWinrateHistogram}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win Rate Distribution Across Epochs
			</h3>
			<svg
				viewBox="0 0 {epochWinrateHistogram.W} {epochWinrateHistogram.H}"
				class="w-full"
				style="height:70px"
			>
				{#each epochWinrateHistogram.counts as b, i (i)}
					{@const x = epochWinrateHistogram.PAD + i * (epochWinrateHistogram.barW + 1)}
					{@const barH = Math.max(
						1,
						(b.count / epochWinrateHistogram.maxCount) *
							(epochWinrateHistogram.H - epochWinrateHistogram.PAD * 2 - 8)
					)}
					{@const color =
						b.lo >= 55 ? 'var(--ch-profit)' : b.lo >= 45 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<rect
						{x}
						y={epochWinrateHistogram.H - 8 - barH}
						width={epochWinrateHistogram.barW}
						height={barH}
						rx="1"
						fill={color}
					/>
				{/each}
				<text
					x={epochWinrateHistogram.PAD}
					y={epochWinrateHistogram.H - 1}
					font-size="7"
					fill="var(--ch-axis)">{epochWinrateHistogram.mn}%</text
				>
				<text
					x={epochWinrateHistogram.W - epochWinrateHistogram.PAD}
					y={epochWinrateHistogram.H - 1}
					text-anchor="end"
					font-size="7"
					fill="var(--ch-axis)">{epochWinrateHistogram.mx}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				{epochWinrateHistogram.total} epochs · avg win rate {epochWinrateHistogram.avg}% · green
				≥55% · yellow 45–55% · red &lt;45% · shape shows optimizer search space coverage
			</p>
		</section>
	{/if}

	{#if epochBestVsNonBestProfit}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Epochs vs All Others — Avg Profit
			</h3>
			<svg
				viewBox="0 0 {epochBestVsNonBestProfit.W} {epochBestVsNonBestProfit.H}"
				class="w-full"
				style="height:70px"
			>
				<line
					x1={epochBestVsNonBestProfit.PAD}
					y1={epochBestVsNonBestProfit.H - epochBestVsNonBestProfit.PAD - 14}
					x2={epochBestVsNonBestProfit.W - epochBestVsNonBestProfit.PAD}
					y2={epochBestVsNonBestProfit.H - epochBestVsNonBestProfit.PAD - 14}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				<rect
					x={epochBestVsNonBestProfit.bestX}
					y={epochBestVsNonBestProfit.H -
						epochBestVsNonBestProfit.PAD -
						14 -
						epochBestVsNonBestProfit.bestH}
					width={epochBestVsNonBestProfit.barW}
					height={epochBestVsNonBestProfit.bestH}
					rx="2"
					fill={epochBestVsNonBestProfit.bestColor}
				/>
				<rect
					x={epochBestVsNonBestProfit.restX}
					y={epochBestVsNonBestProfit.H -
						epochBestVsNonBestProfit.PAD -
						14 -
						epochBestVsNonBestProfit.restH}
					width={epochBestVsNonBestProfit.barW}
					height={epochBestVsNonBestProfit.restH}
					rx="2"
					fill={epochBestVsNonBestProfit.restColor}
				/>
				<text
					x={epochBestVsNonBestProfit.bestX + epochBestVsNonBestProfit.barW / 2}
					y={epochBestVsNonBestProfit.H - 1}
					text-anchor="middle"
					font-size="8"
					fill="var(--ch-axis-strong)">Best ({epochBestVsNonBestProfit.bestCount})</text
				>
				<text
					x={epochBestVsNonBestProfit.restX + epochBestVsNonBestProfit.barW / 2}
					y={epochBestVsNonBestProfit.H - 1}
					text-anchor="middle"
					font-size="8"
					fill="var(--ch-axis-strong)">Others ({epochBestVsNonBestProfit.restCount})</text
				>
				<text
					x={epochBestVsNonBestProfit.bestX + epochBestVsNonBestProfit.barW / 2}
					y={epochBestVsNonBestProfit.H -
						epochBestVsNonBestProfit.PAD -
						16 -
						epochBestVsNonBestProfit.bestH}
					text-anchor="middle"
					font-size="8"
					fill={epochBestVsNonBestProfit.bestColor}
					>{epochBestVsNonBestProfit.avgBest >= 0
						? '+'
						: ''}{epochBestVsNonBestProfit.avgBest.toFixed(2)}%</text
				>
				<text
					x={epochBestVsNonBestProfit.restX + epochBestVsNonBestProfit.barW / 2}
					y={epochBestVsNonBestProfit.H -
						epochBestVsNonBestProfit.PAD -
						16 -
						epochBestVsNonBestProfit.restH}
					text-anchor="middle"
					font-size="8"
					fill={epochBestVsNonBestProfit.restColor}
					>{epochBestVsNonBestProfit.avgRest >= 0
						? '+'
						: ''}{epochBestVsNonBestProfit.avgRest.toFixed(2)}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg total profit % for is_best epochs vs all others · gap between bars shows optimizer
				improvement over random/initial search · larger gap = effective optimization
			</p>
		</section>
	{/if}

	{#if epochInitialVsOptimizedProfit}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Initial Random Points vs Optimizer Epochs — Avg Profit
			</h3>
			<svg
				viewBox="0 0 {epochInitialVsOptimizedProfit.W} {epochInitialVsOptimizedProfit.H}"
				class="w-full"
				style="height:70px"
			>
				<line
					x1={epochInitialVsOptimizedProfit.PAD}
					y1={epochInitialVsOptimizedProfit.baseY}
					x2={epochInitialVsOptimizedProfit.W - epochInitialVsOptimizedProfit.PAD}
					y2={epochInitialVsOptimizedProfit.baseY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				<rect
					x={epochInitialVsOptimizedProfit.initX}
					y={epochInitialVsOptimizedProfit.baseY - epochInitialVsOptimizedProfit.initH}
					width={epochInitialVsOptimizedProfit.barW}
					height={epochInitialVsOptimizedProfit.initH}
					rx="2"
					fill={epochInitialVsOptimizedProfit.initColor}
				/>
				<rect
					x={epochInitialVsOptimizedProfit.optX}
					y={epochInitialVsOptimizedProfit.baseY - epochInitialVsOptimizedProfit.optH}
					width={epochInitialVsOptimizedProfit.barW}
					height={epochInitialVsOptimizedProfit.optH}
					rx="2"
					fill={epochInitialVsOptimizedProfit.optColor}
				/>
				<text
					x={epochInitialVsOptimizedProfit.initX + epochInitialVsOptimizedProfit.barW / 2}
					y={epochInitialVsOptimizedProfit.H - 1}
					text-anchor="middle"
					font-size="8"
					fill="var(--ch-axis-strong)">Initial ({epochInitialVsOptimizedProfit.initCount})</text
				>
				<text
					x={epochInitialVsOptimizedProfit.optX + epochInitialVsOptimizedProfit.barW / 2}
					y={epochInitialVsOptimizedProfit.H - 1}
					text-anchor="middle"
					font-size="8"
					fill="var(--ch-axis-strong)">Optimized ({epochInitialVsOptimizedProfit.optCount})</text
				>
				<text
					x={epochInitialVsOptimizedProfit.initX + epochInitialVsOptimizedProfit.barW / 2}
					y={epochInitialVsOptimizedProfit.baseY - epochInitialVsOptimizedProfit.initH - 3}
					text-anchor="middle"
					font-size="7.5"
					fill={epochInitialVsOptimizedProfit.initColor}
					>{epochInitialVsOptimizedProfit.avgInit >= 0
						? '+'
						: ''}{epochInitialVsOptimizedProfit.avgInit.toFixed(2)}%</text
				>
				<text
					x={epochInitialVsOptimizedProfit.optX + epochInitialVsOptimizedProfit.barW / 2}
					y={epochInitialVsOptimizedProfit.baseY - epochInitialVsOptimizedProfit.optH - 3}
					text-anchor="middle"
					font-size="7.5"
					fill={epochInitialVsOptimizedProfit.optColor}
					>{epochInitialVsOptimizedProfit.avgOpt >= 0
						? '+'
						: ''}{epochInitialVsOptimizedProfit.avgOpt.toFixed(2)}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg profit of random initial points vs optimizer-driven epochs · green lift = optimization
				is effectively finding better params · gray = baseline random search
			</p>
		</section>
	{/if}

	{#if epochProfitRunLength}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Epoch Profit by Loss-Function Rank ({epochProfitRunLength.count} epochs)
			</h3>
			<svg
				viewBox="0 0 {epochProfitRunLength.W} {epochProfitRunLength.H}"
				class="w-full"
				style="height:75px"
			>
				<line
					x1={epochProfitRunLength.PAD}
					y1={epochProfitRunLength.zeroY}
					x2={epochProfitRunLength.W - epochProfitRunLength.PAD}
					y2={epochProfitRunLength.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.8"
					stroke-dasharray="3,2"
				/>
				<polyline
					points={epochProfitRunLength.polyline}
					fill="none"
					stroke="var(--ch-violet)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				{#each epochProfitRunLength.pts.filter((_, i) => i % Math.max(1, Math.floor(epochProfitRunLength.pts.length / 20)) === 0) as p, _i (_i)}
					<circle
						cx={p.x}
						cy={p.y}
						r="2"
						fill={p.y <= epochProfitRunLength.zeroY ? 'var(--ch-profit-strong)' : 'var(--ch-loss)'}
					/>
				{/each}
				<text
					x={epochProfitRunLength.PAD}
					y={epochProfitRunLength.H - 2}
					font-size="6.5"
					fill="var(--ch-axis-muted)">best loss</text
				>
				<text
					x={epochProfitRunLength.W - epochProfitRunLength.PAD}
					y={epochProfitRunLength.H - 2}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-axis-muted)">worst loss</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Epochs sorted by loss function rank (best→worst) · y=profit % · downward slope left means
				low-loss epochs are more profitable · reveals correlation between loss fn and actual profit
			</p>
		</section>
	{/if}

	{#if epochDrawdownHistogram}
		<section class="mt-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Epoch Max Drawdown Distribution ({epochDrawdownHistogram.total} epochs · avg {epochDrawdownHistogram.avg}%)
			</h3>
			<svg
				viewBox="0 0 {epochDrawdownHistogram.W} {epochDrawdownHistogram.H}"
				class="w-full"
				style="height:72px"
			>
				{#each epochDrawdownHistogram.counts as b, i (i)}
					{@const x = epochDrawdownHistogram.PAD + i * (epochDrawdownHistogram.barW + 1)}
					{@const barH = Math.max(
						1,
						(b.count / epochDrawdownHistogram.maxCount) *
							(epochDrawdownHistogram.H - epochDrawdownHistogram.PAD * 2 - 10)
					)}
					{@const color =
						b.lo <= 10 ? 'var(--ch-profit)' : b.lo <= 25 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<rect
						{x}
						y={epochDrawdownHistogram.H - 10 - barH}
						width={epochDrawdownHistogram.barW}
						height={barH}
						rx="1"
						fill={color}
					/>
				{/each}
				<text
					x={epochDrawdownHistogram.PAD}
					y={epochDrawdownHistogram.H - 1}
					font-size="7"
					fill="var(--ch-axis)">0%</text
				>
				<text
					x={epochDrawdownHistogram.W - epochDrawdownHistogram.PAD}
					y={epochDrawdownHistogram.H - 1}
					text-anchor="end"
					font-size="7"
					fill="var(--ch-axis)">{epochDrawdownHistogram.mx}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Max drawdown % per epoch · green ≤10% · yellow ≤25% · red &gt;25% · left-skewed = optimizer
				avoiding deep drawdowns · reveals risk profile of parameter search
			</p>
		</section>
	{/if}
	{#if epochProfitRollingVolatility}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Rolling Profit Volatility (10-epoch window · {epochProfitRollingVolatility.total} epochs)
			</h3>
			<svg
				viewBox="0 0 {epochProfitRollingVolatility.W} {epochProfitRollingVolatility.H}"
				class="w-full"
				style="height:70px"
			>
				<polyline
					points={epochProfitRollingVolatility.poly}
					fill="none"
					stroke="var(--ch-violet)"
					stroke-width="1.4"
					stroke-linejoin="round"
				/>
				<text
					x={epochProfitRollingVolatility.PAD}
					y={epochProfitRollingVolatility.PAD + 5}
					font-size="6.5"
					fill="var(--ch-axis-muted)">σ {epochProfitRollingVolatility.maxStd}</text
				>
				<text
					x={epochProfitRollingVolatility.W - epochProfitRollingVolatility.PAD}
					y={epochProfitRollingVolatility.H - 2}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-axis-muted)">epoch →</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Std-dev of profit over rolling 10-epoch windows · high volatility = optimizer exploring
				diverse parameter regions · flattening = convergence toward local optimum
			</p>
		</section>
	{/if}
	{#if epochBestNMeanTrend}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Top-{epochBestNMeanTrend.N} Epoch Mean Profit Trend ({epochBestNMeanTrend.total} epochs · current
				{epochBestNMeanTrend.last}%)
			</h3>
			<svg
				viewBox="0 0 {epochBestNMeanTrend.W} {epochBestNMeanTrend.H}"
				class="w-full"
				style="height:72px"
			>
				<polyline
					points={epochBestNMeanTrend.poly}
					fill="none"
					stroke="var(--ch-profit)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={epochBestNMeanTrend.PAD}
					y={epochBestNMeanTrend.H - 2}
					font-size="6.5"
					fill="var(--ch-axis-muted)">epoch 1</text
				>
				<text
					x={epochBestNMeanTrend.W - epochBestNMeanTrend.PAD}
					y={epochBestNMeanTrend.H - 2}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-axis-muted)">{epochBestNMeanTrend.total}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Running mean of top-{epochBestNMeanTrend.N} best epochs seen so far · rising = optimizer finding
				progressively better parameter combinations · plateau = search converging
			</p>
		</section>
	{/if}
	{#if epochSharpeTimeline}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Sharpe Timeline — Running Best vs Per-Epoch ({epochSharpeTimeline.total} epochs · best {epochSharpeTimeline.finalBest})
			</h3>
			<svg
				viewBox="0 0 {epochSharpeTimeline.W} {epochSharpeTimeline.H}"
				class="w-full"
				style="height:72px"
			>
				<polyline
					points={epochSharpeTimeline.curPoly}
					fill="none"
					stroke="var(--ch-axis-muted)"
					stroke-width="0.8"
					stroke-linejoin="round"
				/>
				<polyline
					points={epochSharpeTimeline.bestPoly}
					fill="none"
					stroke="var(--ch-profit-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={epochSharpeTimeline.PAD}
					y={epochSharpeTimeline.H - 2}
					font-size="6.5"
					fill="var(--ch-axis-muted)">epoch 1</text
				>
				<text
					x={epochSharpeTimeline.W - epochSharpeTimeline.PAD}
					y={epochSharpeTimeline.H - 2}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-axis-muted)">{epochSharpeTimeline.total}</text
				>
			</svg>
			<div class="mt-1 flex gap-3 text-[9px] text-muted-foreground">
				<span style="color:var(--ch-profit-strong)">— running best Sharpe</span>
				<span style="color:var(--ch-axis-muted)">— per-epoch Sharpe</span>
				<span
					>· monotonically rising green = optimizer consistently improving · flat = search stalled</span
				>
			</div>
		</section>
	{/if}
	{#if epochCalmarBuckets}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Calmar Ratio Distribution ({epochCalmarBuckets.total} epochs)
			</h3>
			<svg
				viewBox="0 0 {epochCalmarBuckets.W} {epochCalmarBuckets.H}"
				class="w-full"
				style="height:65px"
			>
				{#each epochCalmarBuckets.bins as bin, i (i)}
					{@const x = epochCalmarBuckets.PAD + i * (epochCalmarBuckets.barW + 2)}
					{@const bh = Math.max(
						2,
						(bin.count / epochCalmarBuckets.maxCount) *
							(epochCalmarBuckets.H - epochCalmarBuckets.PAD * 2 - 10)
					)}
					{@const midVal = (bin.lo + bin.hi) / 2}
					{@const color =
						midVal >= 1 ? 'var(--ch-profit)' : midVal >= 0 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<rect
						{x}
						y={epochCalmarBuckets.H - epochCalmarBuckets.PAD - 10 - bh}
						width={epochCalmarBuckets.barW}
						height={bh}
						rx="1"
						fill={color}
					/>
					<text
						x={x + epochCalmarBuckets.barW / 2}
						y={epochCalmarBuckets.H - epochCalmarBuckets.PAD - 2}
						text-anchor="middle"
						font-size="5.5"
						fill="var(--ch-axis-muted)">{midVal.toFixed(0)}</text
					>
					{#if bin.count > 0}
						<text
							x={x + epochCalmarBuckets.barW / 2}
							y={epochCalmarBuckets.H - epochCalmarBuckets.PAD - 10 - bh - 2}
							text-anchor="middle"
							font-size="5.5"
							fill={color}>{bin.count}</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Histogram of Calmar ratios across all epochs · green≥1 · yellow≥0 · red=negative ·
				right-skewed shape = optimizer finding high-Calmar solutions
			</p>
		</section>
	{/if}
	{#if epochProfitVsTradeCount}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Total Profit vs Trade Count ({epochProfitVsTradeCount.count} epochs)
			</h3>
			<svg
				viewBox="0 0 {epochProfitVsTradeCount.W} {epochProfitVsTradeCount.H}"
				class="w-full"
				style="height:88px"
			>
				<line
					x1={epochProfitVsTradeCount.PAD}
					y1={epochProfitVsTradeCount.zeroY}
					x2={epochProfitVsTradeCount.W - epochProfitVsTradeCount.PAD}
					y2={epochProfitVsTradeCount.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each epochProfitVsTradeCount.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r={d.best ? 3.5 : 2} fill={d.color} />
				{/each}
				<text
					x={epochProfitVsTradeCount.PAD}
					y={epochProfitVsTradeCount.H - 2}
					font-size="6.5"
					fill="var(--ch-axis-muted)">{epochProfitVsTradeCount.tMin} trades</text
				>
				<text
					x={epochProfitVsTradeCount.W - epochProfitVsTradeCount.PAD}
					y={epochProfitVsTradeCount.H - 2}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-axis-muted)">{epochProfitVsTradeCount.tMax}</text
				>
				<text
					x={epochProfitVsTradeCount.PAD}
					y={epochProfitVsTradeCount.PAD + 4}
					font-size="6"
					fill="var(--ch-axis-muted)">profit {epochProfitVsTradeCount.pMax}</text
				>
			</svg>
			<div class="mt-1 flex gap-3 text-[9px] text-muted-foreground">
				<span style="color:var(--ch-warn)">● best epochs</span>
				<span style="color:var(--ch-profit)">● profit≥0</span>
				<span style="color:var(--ch-loss-light)">● losing</span>
				<span
					>· x=trade count · y=total profit · reveals if more trades = more profit or diminishing
					returns</span
				>
			</div>
		</section>
	{/if}
	{#if epochSortinoBestTimeline}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Sortino Timeline — Running Best vs Per-Epoch ({epochSortinoBestTimeline.total} epochs · best {epochSortinoBestTimeline.finalBest})
			</h3>
			<svg
				viewBox="0 0 {epochSortinoBestTimeline.W} {epochSortinoBestTimeline.H}"
				class="w-full"
				style="height:68px"
			>
				<polyline
					points={epochSortinoBestTimeline.curPoly}
					fill="none"
					stroke="var(--ch-axis-muted)"
					stroke-width="0.8"
					stroke-linejoin="round"
				/>
				<polyline
					points={epochSortinoBestTimeline.bestPoly}
					fill="none"
					stroke="var(--ch-violet-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={epochSortinoBestTimeline.PAD}
					y={epochSortinoBestTimeline.H - 2}
					font-size="6.5"
					fill="var(--ch-axis-muted)">epoch 1</text
				>
				<text
					x={epochSortinoBestTimeline.W - epochSortinoBestTimeline.PAD}
					y={epochSortinoBestTimeline.H - 2}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-axis-muted)">{epochSortinoBestTimeline.total}</text
				>
			</svg>
			<div class="mt-1 flex gap-3 text-[9px] text-muted-foreground">
				<span style="color:var(--ch-violet-strong)">— running best Sortino</span>
				<span style="color:var(--ch-axis-muted)">— per-epoch Sortino</span>
				<span
					>· Sortino penalizes only downside volatility · rising blue = optimizer finding
					downside-safer solutions</span
				>
			</div>
		</section>
	{/if}

	{#if epochTradeCountTimeline}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Trade Count per Epoch ({epochTradeCountTimeline.total} epochs)
			</h3>
			<svg
				viewBox="0 0 {epochTradeCountTimeline.W} {epochTradeCountTimeline.H}"
				class="w-full"
				style="height:68px"
			>
				<polyline
					points={epochTradeCountTimeline.poly}
					fill="none"
					stroke="var(--ch-axis-faint)"
					stroke-width="0.8"
					stroke-linejoin="round"
				/>
				{#each epochTradeCountTimeline.dots as d, _i (_i)}
					{#if d.isBest}
						<circle cx={d.cx} cy={d.cy} r="4" fill="var(--ch-violet-strong)" />
					{:else if epochTradeCountTimeline.dots.indexOf(d) % Math.max(1, Math.floor(epochTradeCountTimeline.total / 60)) === 0}
						<circle cx={d.cx} cy={d.cy} r="1.5" fill={d.color} />
					{/if}
				{/each}
				<text
					x={epochTradeCountTimeline.PAD}
					y={epochTradeCountTimeline.H - 2}
					font-size="6.5"
					fill="var(--ch-axis-muted)">epoch 1</text
				>
				<text
					x={epochTradeCountTimeline.W - epochTradeCountTimeline.PAD}
					y={epochTradeCountTimeline.H - 2}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-axis-muted)">{epochTradeCountTimeline.total}</text
				>
				<text
					x={epochTradeCountTimeline.PAD}
					y={epochTradeCountTimeline.PAD + 5}
					font-size="6"
					fill="var(--ch-axis-muted)">{epochTradeCountTimeline.mx} trades</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Number of trades per epoch · indigo dot = best profit epoch · reveals whether optimizer
				prefers high or low frequency configurations
			</p>
		</section>
	{/if}

	{#if epochWinRateTimeline}
		<section class="mb-6 rounded-xl border border-border bg-card p-5">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win Rate per Epoch · Running Best {epochWinRateTimeline.finalBest}%
			</h3>
			<svg
				viewBox="0 0 {epochWinRateTimeline.W} {epochWinRateTimeline.H}"
				class="w-full"
				style="height:68px"
			>
				{#if epochWinRateTimeline.y50 >= epochWinRateTimeline.PAD && epochWinRateTimeline.y50 <= epochWinRateTimeline.H - epochWinRateTimeline.PAD}
					<line
						x1={epochWinRateTimeline.PAD}
						y1={epochWinRateTimeline.y50}
						x2={epochWinRateTimeline.W - epochWinRateTimeline.PAD}
						y2={epochWinRateTimeline.y50}
						stroke="var(--ch-axis-faint)"
						stroke-width="0.7"
						stroke-dasharray="3,2"
					/>
					<text
						x={epochWinRateTimeline.W - epochWinRateTimeline.PAD + 1}
						y={epochWinRateTimeline.y50 + 3}
						font-size="5.5"
						fill="var(--ch-axis-muted)">50%</text
					>
				{/if}
				<polyline
					points={epochWinRateTimeline.curPoly}
					fill="none"
					stroke="var(--ch-axis-muted)"
					stroke-width="0.8"
					stroke-linejoin="round"
				/>
				<polyline
					points={epochWinRateTimeline.bestPoly}
					fill="none"
					stroke="var(--ch-profit-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={epochWinRateTimeline.PAD}
					y={epochWinRateTimeline.H - 2}
					font-size="6.5"
					fill="var(--ch-axis-muted)">epoch 1</text
				>
				<text
					x={epochWinRateTimeline.W - epochWinRateTimeline.PAD}
					y={epochWinRateTimeline.H - 2}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-axis-muted)">{epochWinRateTimeline.total}</text
				>
			</svg>
			<div class="mt-1 flex gap-3 text-[9px] text-muted-foreground">
				<span style="color:var(--ch-profit-strong)">— running best win rate</span>
				<span style="color:var(--ch-axis-muted)">— per-epoch win rate</span>
				<span>· dashed line = 50% · best = {epochWinRateTimeline.finalBest}%</span>
			</div>
		</section>
	{/if}
	{#if epochProfitHistogram}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Epoch Profit % Distribution
			</h3>
			<svg
				viewBox="0 0 {epochProfitHistogram.W} {epochProfitHistogram.H}"
				class="w-full"
				style="height:{epochProfitHistogram.H}px"
			>
				<line
					x1={epochProfitHistogram.zeroX}
					y1="0"
					x2={epochProfitHistogram.zeroX}
					y2={epochProfitHistogram.H - 14}
					stroke="var(--ch-axis-muted)"
					stroke-width="0.8"
				/>
				{#each epochProfitHistogram.bars as bar, _i (_i)}
					<rect
						x={bar.x}
						y={epochProfitHistogram.H - 14 - bar.h}
						width={epochProfitHistogram.bw}
						height={bar.h}
						rx="1"
						fill={bar.color}
					/>
				{/each}
				<text
					x={epochProfitHistogram.PAD}
					y={epochProfitHistogram.H - 2}
					font-size="7"
					fill="var(--ch-axis)">{epochProfitHistogram.mn}%</text
				>
				<text
					x={epochProfitHistogram.W - epochProfitHistogram.PAD}
					y={epochProfitHistogram.H - 2}
					text-anchor="end"
					font-size="7"
					fill="var(--ch-axis)">{epochProfitHistogram.mx}%</text
				>
				<text
					x={epochProfitHistogram.W / 2}
					y={epochProfitHistogram.H - 2}
					text-anchor="middle"
					font-size="7"
					fill="var(--ch-axis-muted)">n={epochProfitHistogram.total}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Distribution of profit % across all hyperopt epochs · green=profit≥0 · red=loss · zero line
				shows profit boundary · reveals how often hyperopt finds profitable parameter sets
			</p>
		</section>
	{/if}
	{#if epochSharpeVsDrawdown}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Epoch Sharpe vs Max Drawdown
			</h3>
			<svg
				viewBox="0 0 {epochSharpeVsDrawdown.W} {epochSharpeVsDrawdown.H}"
				class="w-full"
				style="height:{epochSharpeVsDrawdown.H}px"
			>
				<line
					x1={epochSharpeVsDrawdown.zeroX}
					y1={epochSharpeVsDrawdown.PAD}
					x2={epochSharpeVsDrawdown.zeroX}
					y2={epochSharpeVsDrawdown.H - epochSharpeVsDrawdown.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.8"
					stroke-dasharray="3,2"
				/>
				{#each epochSharpeVsDrawdown.dots as d, _i (_i)}
					<circle cx={d.cx} cy={d.cy} r="1.8" fill={d.color} />
				{/each}
				<text
					x={epochSharpeVsDrawdown.PAD}
					y={epochSharpeVsDrawdown.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">Sharpe {epochSharpeVsDrawdown.sMin}</text
				>
				<text
					x={epochSharpeVsDrawdown.W - epochSharpeVsDrawdown.PAD}
					y={epochSharpeVsDrawdown.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{epochSharpeVsDrawdown.sMax}</text
				>
				<text
					x={epochSharpeVsDrawdown.PAD}
					y={epochSharpeVsDrawdown.PAD + 4}
					font-size="6"
					fill="var(--ch-axis-muted)">DD {epochSharpeVsDrawdown.ddMax}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				x=Sharpe · y=max drawdown % per epoch · green=profit≥5% · yellow=profit≥0% · red=loss ·
				ideal cluster = high Sharpe + low drawdown (bottom-right)
			</p>
		</section>
	{/if}
	{#if epochBestExplorationCurve}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Profit Discovery Curve
			</h3>
			<svg
				viewBox="0 0 {epochBestExplorationCurve.W} {epochBestExplorationCurve.H}"
				class="w-full"
				style="height:{epochBestExplorationCurve.H}px"
			>
				<polygon
					points={epochBestExplorationCurve.area}
					fill={epochBestExplorationCurve.fillColor}
				/>
				<polyline
					points={epochBestExplorationCurve.polyline}
					fill="none"
					stroke={epochBestExplorationCurve.color}
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={epochBestExplorationCurve.PAD}
					y={epochBestExplorationCurve.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">epoch 1</text
				>
				<text
					x={epochBestExplorationCurve.W - epochBestExplorationCurve.PAD}
					y={epochBestExplorationCurve.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{epochBestExplorationCurve.totalEpochs}</text
				>
				<text
					x={epochBestExplorationCurve.W - epochBestExplorationCurve.PAD}
					y={epochBestExplorationCurve.PAD + 5}
					text-anchor="end"
					font-size="7"
					fill={epochBestExplorationCurve.color}>{epochBestExplorationCurve.maxBest}%</text
				>
				<text
					x={epochBestExplorationCurve.PAD}
					y={epochBestExplorationCurve.PAD + 5}
					font-size="6"
					fill="var(--ch-axis-muted)">best so far</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Cumulative best profit % discovered as hyperopt explores epochs · plateaus show no
				improvement · steep drops reveal rapid gains · reveals optimization convergence speed
			</p>
		</section>
	{/if}
	{#if epochDrawdownByBucket}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Max Drawdown Trend Over Epochs
			</h3>
			<svg
				viewBox="0 0 {epochDrawdownByBucket.W} {epochDrawdownByBucket.H}"
				class="w-full"
				style="height:{epochDrawdownByBucket.H}px"
			>
				<polygon points={epochDrawdownByBucket.area} fill="var(--ch-loss-light)" />
				<polyline
					points={epochDrawdownByBucket.polyline}
					fill="none"
					stroke="var(--ch-loss)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={epochDrawdownByBucket.PAD}
					y={epochDrawdownByBucket.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">ep {epochDrawdownByBucket.firstEp}</text
				>
				<text
					x={epochDrawdownByBucket.W - epochDrawdownByBucket.PAD}
					y={epochDrawdownByBucket.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{epochDrawdownByBucket.lastEp}</text
				>
				<text
					x={epochDrawdownByBucket.PAD}
					y={epochDrawdownByBucket.PAD + 6}
					font-size="7"
					fill="var(--ch-loss)">max {epochDrawdownByBucket.maxDD}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg max drawdown % per epoch bucket (12 segments) · red area · reveals whether hyperopt is
				finding lower-drawdown parameter sets as search progresses · downward trend is ideal
			</p>
		</section>
	{/if}
	{#if epochWinRateVsProfit}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win Rate vs Profit Factor (per Epoch)
			</h3>
			<svg
				viewBox="0 0 {epochWinRateVsProfit.W} {epochWinRateVsProfit.H}"
				class="w-full"
				style="height:{epochWinRateVsProfit.H}px"
			>
				<line
					x1={epochWinRateVsProfit.PAD}
					y1={epochWinRateVsProfit.H - epochWinRateVsProfit.PAD}
					x2={epochWinRateVsProfit.W - epochWinRateVsProfit.PAD}
					y2={epochWinRateVsProfit.H - epochWinRateVsProfit.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				<line
					x1={epochWinRateVsProfit.PAD}
					y1={epochWinRateVsProfit.PAD}
					x2={epochWinRateVsProfit.PAD}
					y2={epochWinRateVsProfit.H - epochWinRateVsProfit.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each epochWinRateVsProfit.pts as p, _i (_i)}
					{@const cx = epochWinRateVsProfit.toX(p.wr)}
					{@const cy = epochWinRateVsProfit.toY(p.pf)}
					{@const col = p.profit >= 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)'}
					<circle {cx} {cy} r="2.2" fill={col} />
				{/each}
				<text
					x={epochWinRateVsProfit.PAD}
					y={epochWinRateVsProfit.PAD + 5}
					font-size="6"
					fill="var(--ch-axis-muted)">pf {epochWinRateVsProfit.pfMax}</text
				>
				<text
					x={epochWinRateVsProfit.W - epochWinRateVsProfit.PAD}
					y={epochWinRateVsProfit.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">wr {epochWinRateVsProfit.wrMax}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Scatter of epoch win rate % (X) vs profit factor (Y) · green=positive mean profit ·
				red=negative · upper-right corner is ideal combination
			</p>
		</section>
	{/if}
	{#if epochCalmarTrend}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Calmar Ratio Trend over Epochs
			</h3>
			<svg
				viewBox="0 0 {epochCalmarTrend.W} {epochCalmarTrend.H}"
				class="w-full"
				style="height:{epochCalmarTrend.H}px"
			>
				<line
					x1={epochCalmarTrend.PAD}
					y1={epochCalmarTrend.midY}
					x2={epochCalmarTrend.W - epochCalmarTrend.PAD}
					y2={epochCalmarTrend.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each epochCalmarTrend.buckets as b, i (i)}
					{@const cx = epochCalmarTrend.toX(i)}
					{@const bh = epochCalmarTrend.toH(b.avg)}
					{@const color = b.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					{@const y = b.avg >= 0 ? epochCalmarTrend.midY - bh : epochCalmarTrend.midY}
					<rect x={cx - 6} {y} width="12" height={Math.max(1, bh)} rx="1" fill={color} />
				{/each}
				<text
					x={epochCalmarTrend.PAD}
					y={epochCalmarTrend.PAD + 6}
					font-size="7"
					fill="var(--ch-axis-muted)">±{epochCalmarTrend.maxAbs}</text
				>
				<text
					x={epochCalmarTrend.W - epochCalmarTrend.PAD}
					y={epochCalmarTrend.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">later epochs →</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg Calmar ratio per epoch bucket (10 segments) · green=positive · red=negative · upward
				trend means hyperopt is finding better return/drawdown parameter sets
			</p>
		</section>
	{/if}
	{#if epochBestProfitTimeline}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Profit Discovered over Epochs
			</h3>
			<svg
				viewBox="0 0 {epochBestProfitTimeline.W} {epochBestProfitTimeline.H}"
				class="w-full"
				style="height:{epochBestProfitTimeline.H}px"
			>
				<polygon points={epochBestProfitTimeline.area} fill={epochBestProfitTimeline.fillColor} />
				<line
					x1={epochBestProfitTimeline.PAD}
					y1={epochBestProfitTimeline.zeroY}
					x2={epochBestProfitTimeline.W - epochBestProfitTimeline.PAD}
					y2={epochBestProfitTimeline.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				<polyline
					points={epochBestProfitTimeline.polyline}
					fill="none"
					stroke={epochBestProfitTimeline.color}
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={epochBestProfitTimeline.W - epochBestProfitTimeline.PAD}
					y={epochBestProfitTimeline.PAD + 6}
					text-anchor="end"
					font-size="7"
					fill={epochBestProfitTimeline.color}>{epochBestProfitTimeline.last}</text
				>
				<text
					x={epochBestProfitTimeline.PAD}
					y={epochBestProfitTimeline.PAD + 6}
					font-size="6"
					fill="var(--ch-axis-muted)">best mean profit</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Running best mean profit discovered as epochs progress · monotonically increasing · steeper
				early slope = faster convergence · flat tail = search space exhausted
			</p>
		</section>
	{/if}
	{#if epochSharpeVsDrawdownNew}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Epoch Sharpe vs Max Drawdown
			</h3>
			<svg
				viewBox="0 0 {epochSharpeVsDrawdownNew.W} {epochSharpeVsDrawdownNew.H}"
				class="w-full"
				style="height:{epochSharpeVsDrawdownNew.H}px"
			>
				<line
					x1={epochSharpeVsDrawdownNew.PAD}
					y1={epochSharpeVsDrawdownNew.H - epochSharpeVsDrawdownNew.PAD}
					x2={epochSharpeVsDrawdownNew.W - epochSharpeVsDrawdownNew.PAD}
					y2={epochSharpeVsDrawdownNew.H - epochSharpeVsDrawdownNew.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				<line
					x1={epochSharpeVsDrawdownNew.PAD}
					y1={epochSharpeVsDrawdownNew.PAD}
					x2={epochSharpeVsDrawdownNew.PAD}
					y2={epochSharpeVsDrawdownNew.H - epochSharpeVsDrawdownNew.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each epochSharpeVsDrawdownNew.pts as p, _i (_i)}
					{@const cx = epochSharpeVsDrawdownNew.toX(p.dd)}
					{@const cy = epochSharpeVsDrawdownNew.toY(p.sh)}
					{@const col = p.profit >= 0 ? 'var(--ch-profit-light)' : 'var(--ch-loss-light)'}
					<circle {cx} {cy} r="2" fill={col} />
				{/each}
				<text
					x={epochSharpeVsDrawdownNew.PAD}
					y={epochSharpeVsDrawdownNew.PAD + 6}
					font-size="6"
					fill="var(--ch-axis-muted)">sh {epochSharpeVsDrawdownNew.shMax}</text
				>
				<text
					x={epochSharpeVsDrawdownNew.W - epochSharpeVsDrawdownNew.PAD}
					y={epochSharpeVsDrawdownNew.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">dd {epochSharpeVsDrawdownNew.ddMax}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Scatter of max drawdown % (X) vs Sharpe (Y) per epoch · green=positive mean profit ·
				red=negative · upper-left corner is ideal: high Sharpe with low drawdown
			</p>
		</section>
	{/if}
	{#if epochWinRateHistogram}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Epoch Win Rate Distribution
			</h3>
			<svg
				viewBox="0 0 {epochWinRateHistogram.W} {epochWinRateHistogram.H}"
				class="w-full"
				style="height:{epochWinRateHistogram.H}px"
			>
				{#each epochWinRateHistogram.counts as count, i (i)}
					{@const x = epochWinRateHistogram.PAD + i * epochWinRateHistogram.barW}
					{@const bh = Math.max(
						2,
						(count / epochWinRateHistogram.maxCount) *
							(epochWinRateHistogram.H - epochWinRateHistogram.PAD * 2)
					)}
					{@const pct = (i / epochWinRateHistogram.bins) * 100}
					{@const color =
						pct >= 60 ? 'var(--ch-profit)' : pct >= 45 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<rect
						{x}
						y={epochWinRateHistogram.H - epochWinRateHistogram.PAD - bh}
						width={epochWinRateHistogram.barW - 1}
						height={bh}
						fill={color}
					/>
					{#if i % 4 === 0}
						<text
							x={x + epochWinRateHistogram.barW / 2}
							y={epochWinRateHistogram.H - 1}
							text-anchor="middle"
							font-size="5.5"
							fill="var(--ch-axis-muted)">{Math.round(pct)}%</text
						>
					{/if}
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Distribution of win rate % across all epochs · green≥60% · yellow≥45% · red&lt;45% ·
				rightward skew indicates hyperopt finding high-frequency strategies
			</p>
		</section>
	{/if}
	{#if epochSortinoVsWinRate}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Sortino vs Win Rate Scatter
			</h3>
			<svg
				viewBox="0 0 {epochSortinoVsWinRate.W} {epochSortinoVsWinRate.H}"
				class="w-full"
				style="height:{epochSortinoVsWinRate.H}px"
			>
				<line
					x1={epochSortinoVsWinRate.PAD}
					y1={epochSortinoVsWinRate.PAD}
					x2={epochSortinoVsWinRate.PAD}
					y2={epochSortinoVsWinRate.H - epochSortinoVsWinRate.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each epochSortinoVsWinRate.pts as p, _i (_i)}
					{@const cx = epochSortinoVsWinRate.toX(p.wr)}
					{@const cy = epochSortinoVsWinRate.toY(p.so)}
					{@const col = p.profit >= 0 ? 'var(--ch-violet-light)' : 'var(--ch-loss-light)'}
					<circle {cx} {cy} r="2" fill={col} />
				{/each}
				<text
					x={epochSortinoVsWinRate.PAD}
					y={epochSortinoVsWinRate.PAD + 7}
					font-size="6"
					fill="var(--ch-axis-muted)">so {epochSortinoVsWinRate.soMax}</text
				>
				<text
					x={epochSortinoVsWinRate.W - epochSortinoVsWinRate.PAD}
					y={epochSortinoVsWinRate.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">wr {epochSortinoVsWinRate.wrMax}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Scatter of win rate % (X) vs Sortino ratio (Y) per epoch · indigo=positive mean profit ·
				red=negative · upper-right corner is ideal: high win rate with high downside-risk-adjusted
				return
			</p>
		</section>
	{/if}
	{#if epochCalmarSortinoScatter}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Calmar vs Sortino Scatter
			</h3>
			<svg
				viewBox="0 0 {epochCalmarSortinoScatter.W} {epochCalmarSortinoScatter.H}"
				class="w-full"
				style="height:{epochCalmarSortinoScatter.H}px"
			>
				<line
					x1={epochCalmarSortinoScatter.PAD}
					y1={epochCalmarSortinoScatter.PAD}
					x2={epochCalmarSortinoScatter.PAD}
					y2={epochCalmarSortinoScatter.H - epochCalmarSortinoScatter.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
				/>
				{#each epochCalmarSortinoScatter.pts as p, _i (_i)}
					{@const cx = epochCalmarSortinoScatter.toX(p.ca)}
					{@const cy = epochCalmarSortinoScatter.toY(p.so)}
					{@const col = p.profit >= 0 ? 'var(--ch-teal-light)' : 'var(--ch-loss-light)'}
					<circle {cx} {cy} r="2" fill={col} />
				{/each}
				<text
					x={epochCalmarSortinoScatter.PAD}
					y={epochCalmarSortinoScatter.PAD + 7}
					font-size="6"
					fill="var(--ch-axis-muted)">so {epochCalmarSortinoScatter.soMax}</text
				>
				<text
					x={epochCalmarSortinoScatter.W - epochCalmarSortinoScatter.PAD}
					y={epochCalmarSortinoScatter.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">ca {epochCalmarSortinoScatter.caMax}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Scatter of Calmar ratio (X) vs Sortino ratio (Y) per epoch · teal=positive mean profit ·
				red=negative · upper-right = best risk-adjusted profile on both metrics simultaneously
			</p>
		</section>
	{/if}
	{#if epochProfitByDrawdownBucket}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Mean Profit by Drawdown Bucket
			</h3>
			<svg
				viewBox="0 0 {epochProfitByDrawdownBucket.W} {epochProfitByDrawdownBucket.H}"
				class="w-full"
				style="height:{epochProfitByDrawdownBucket.H}px"
			>
				<line
					x1={epochProfitByDrawdownBucket.PAD}
					y1={epochProfitByDrawdownBucket.midY}
					x2={epochProfitByDrawdownBucket.W - epochProfitByDrawdownBucket.PAD}
					y2={epochProfitByDrawdownBucket.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each epochProfitByDrawdownBucket.rows as row, i (i)}
					{@const x = epochProfitByDrawdownBucket.PAD + i * (epochProfitByDrawdownBucket.bw + 2)}
					{@const bh = Math.max(
						2,
						(Math.abs(row.avg) / epochProfitByDrawdownBucket.maxAbs) *
							(epochProfitByDrawdownBucket.midY - epochProfitByDrawdownBucket.PAD)
					)}
					{@const y =
						row.avg >= 0 ? epochProfitByDrawdownBucket.midY - bh : epochProfitByDrawdownBucket.midY}
					{@const color = row.avg >= 0 ? 'var(--ch-profit)' : 'var(--ch-loss)'}
					<rect {x} {y} width={epochProfitByDrawdownBucket.bw} height={bh} rx="1" fill={color} />
					<text
						x={x + epochProfitByDrawdownBucket.bw / 2}
						y={epochProfitByDrawdownBucket.H - 2}
						text-anchor="middle"
						font-size="6"
						fill="var(--ch-axis-muted)">{row.b}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg mean profit per epoch grouped by max drawdown bucket · green=positive · red=negative ·
				reveals whether low-drawdown epochs also achieve positive mean profit
			</p>
		</section>
	{/if}
	{#if epochSortinoDistribution}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Sortino Ratio Distribution (Epochs)
			</h3>
			<svg
				viewBox="0 0 {epochSortinoDistribution.W} {epochSortinoDistribution.H}"
				class="w-full"
				style="height:{epochSortinoDistribution.H}px"
			>
				<line
					x1={epochSortinoDistribution.zeroX}
					y1="0"
					x2={epochSortinoDistribution.zeroX}
					y2={epochSortinoDistribution.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="1"
					stroke-dasharray="3,2"
				/>
				{#each epochSortinoDistribution.bins as count, i (i)}
					{@const x = epochSortinoDistribution.PAD + i * epochSortinoDistribution.bw}
					{@const bh = Math.max(
						1,
						(count / epochSortinoDistribution.maxCount) *
							(epochSortinoDistribution.H - epochSortinoDistribution.PAD * 2)
					)}
					{@const y = epochSortinoDistribution.H - epochSortinoDistribution.PAD - bh}
					{@const cx = x + epochSortinoDistribution.bw / 2}
					{@const isPos = cx >= epochSortinoDistribution.zeroX}
					<rect
						{x}
						{y}
						width={epochSortinoDistribution.bw - 1}
						height={bh}
						rx="1"
						fill={isPos ? 'var(--ch-teal)' : 'var(--ch-loss)'}
					/>
				{/each}
				<text
					x={epochSortinoDistribution.PAD}
					y={epochSortinoDistribution.H - 1}
					font-size="6"
					fill="var(--ch-axis-muted)">{epochSortinoDistribution.minV}</text
				>
				<text
					x={epochSortinoDistribution.W - epochSortinoDistribution.PAD}
					y={epochSortinoDistribution.H - 1}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{epochSortinoDistribution.maxV}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Distribution of Sortino ratios across all hyperopt epochs · teal=positive · red=negative ·
				right-skewed distribution indicates optimization is finding epochs with positive
				risk-adjusted returns
			</p>
		</section>
	{/if}
	{#if epochProfitCumulative}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Epoch Mean Profit Sorted (CDF-Style)
			</h3>
			<svg
				viewBox="0 0 {epochProfitCumulative.W} {epochProfitCumulative.H}"
				class="w-full"
				style="height:{epochProfitCumulative.H}px"
			>
				<line
					x1={epochProfitCumulative.PAD}
					y1={epochProfitCumulative.zeroY}
					x2={epochProfitCumulative.W - epochProfitCumulative.PAD}
					y2={epochProfitCumulative.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="1"
					stroke-dasharray="3,2"
				/>
				<polyline
					points={epochProfitCumulative.polyline}
					fill="none"
					stroke="var(--ch-warn)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={epochProfitCumulative.PAD}
					y={epochProfitCumulative.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{epochProfitCumulative.minP}</text
				>
				<text
					x={epochProfitCumulative.W - epochProfitCumulative.PAD}
					y={epochProfitCumulative.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{epochProfitCumulative.maxP}</text
				>
				<text
					x={epochProfitCumulative.W - epochProfitCumulative.PAD}
					y={epochProfitCumulative.PAD + 8}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-warn)">p80: {epochProfitCumulative.pct80}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Epochs sorted by mean profit (ascending) · amber S-curve · steep top-right = few very
				profitable epochs · dashed zero line · reveals distribution skew and outlier sensitivity
			</p>
		</section>
	{/if}
	{#if epochDrawdownCDF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Max Drawdown% CDF (Epochs)
			</h3>
			<svg
				viewBox="0 0 {epochDrawdownCDF.W} {epochDrawdownCDF.H}"
				class="w-full"
				style="height:{epochDrawdownCDF.H}px"
			>
				<line
					x1={epochDrawdownCDF.p20X}
					y1={epochDrawdownCDF.PAD}
					x2={epochDrawdownCDF.p20X}
					y2={epochDrawdownCDF.H - epochDrawdownCDF.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				<polyline
					points={epochDrawdownCDF.polyline}
					fill="none"
					stroke="var(--ch-loss-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={epochDrawdownCDF.PAD}
					y={epochDrawdownCDF.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{epochDrawdownCDF.minV}%</text
				>
				<text
					x={epochDrawdownCDF.W - epochDrawdownCDF.PAD}
					y={epochDrawdownCDF.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{epochDrawdownCDF.maxV}%</text
				>
				<text
					x={epochDrawdownCDF.W / 2}
					y={epochDrawdownCDF.PAD + 8}
					text-anchor="middle"
					font-size="7"
					fill="var(--ch-loss-strong)"
					>median {epochDrawdownCDF.median}% · p20 {epochDrawdownCDF.p20}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Cumulative distribution of max drawdown% across hyperopt epochs · red S-curve · dashed p20
				line · left-skewed = most epochs have low drawdown · right tail shows worst risk outcomes
			</p>
		</section>
	{/if}
	{#if epochTradeCountByDrawdown}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Trade Count by Drawdown Bucket
			</h3>
			<svg
				viewBox="0 0 {epochTradeCountByDrawdown.W} {epochTradeCountByDrawdown.H}"
				class="w-full"
				style="height:{epochTradeCountByDrawdown.H}px"
			>
				{#each epochTradeCountByDrawdown.rows as row, i (i)}
					{@const x = epochTradeCountByDrawdown.PAD + i * (epochTradeCountByDrawdown.bw + 2)}
					{@const bh = Math.max(
						1,
						(row.avg / epochTradeCountByDrawdown.maxAvg) *
							(epochTradeCountByDrawdown.H - epochTradeCountByDrawdown.PAD * 2)
					)}
					{@const y = epochTradeCountByDrawdown.H - epochTradeCountByDrawdown.PAD - bh}
					{@const color =
						i <= 1 ? 'var(--ch-profit)' : i === 2 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<rect {x} {y} width={epochTradeCountByDrawdown.bw} height={bh} rx="2" fill={color} />
					<text
						x={x + epochTradeCountByDrawdown.bw / 2}
						y={epochTradeCountByDrawdown.H - 2}
						text-anchor="middle"
						font-size="6"
						fill="var(--ch-axis-muted)">{row.b}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg trade count per epoch grouped by max drawdown bucket · green=low DD · red=high DD · high
				trade count with low drawdown = efficient high-frequency strategy
			</p>
		</section>
	{/if}
	{#if epochWinRateByDrawdownBucket}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Win Rate by Drawdown Bucket
			</h3>
			<svg
				viewBox="0 0 {epochWinRateByDrawdownBucket.W} {epochWinRateByDrawdownBucket.H}"
				class="w-full"
				style="height:{epochWinRateByDrawdownBucket.H}px"
			>
				{#each epochWinRateByDrawdownBucket.rows as row, i (i)}
					{@const x = epochWinRateByDrawdownBucket.PAD + i * (epochWinRateByDrawdownBucket.bw + 2)}
					{@const bh = Math.max(
						1,
						(row.avgWr / epochWinRateByDrawdownBucket.maxWr) *
							(epochWinRateByDrawdownBucket.H - epochWinRateByDrawdownBucket.PAD * 2)
					)}
					{@const y = epochWinRateByDrawdownBucket.H - epochWinRateByDrawdownBucket.PAD - bh}
					{@const color = i <= 1 ? 'var(--ch-teal)' : i === 2 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<rect
						{x}
						{y}
						width={epochWinRateByDrawdownBucket.bw}
						height={bh}
						rx="2"
						style="fill:{color}"
					/>
					<text
						x={x + epochWinRateByDrawdownBucket.bw / 2}
						y={epochWinRateByDrawdownBucket.H - 2}
						text-anchor="middle"
						font-size="6"
						fill="var(--ch-axis-muted)">{row.b}</text
					>
					<text
						x={x + epochWinRateByDrawdownBucket.bw / 2}
						y={y - 2}
						text-anchor="middle"
						font-size="6"
						fill="var(--ch-axis-strong)">{row.avgWr.toFixed(0)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg win rate% per epoch by max drawdown bucket · teal=low DD · red=high DD · high win rate
				with high drawdown = choppy strategy with big losers
			</p>
		</section>
	{/if}
	{#if epochLossCDF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Loss Function CDF (Epochs)
			</h3>
			<svg
				viewBox="0 0 {epochLossCDF.W} {epochLossCDF.H}"
				class="w-full"
				style="height:{epochLossCDF.H}px"
			>
				<line
					x1={epochLossCDF.p10X}
					y1={epochLossCDF.PAD}
					x2={epochLossCDF.p10X}
					y2={epochLossCDF.H - epochLossCDF.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				<polyline
					points={epochLossCDF.pts}
					fill="none"
					stroke="var(--ch-teal-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text x={epochLossCDF.PAD} y={epochLossCDF.H - 2} font-size="6" fill="var(--ch-axis-muted)"
					>{epochLossCDF.minV}</text
				>
				<text
					x={epochLossCDF.W - epochLossCDF.PAD}
					y={epochLossCDF.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{epochLossCDF.maxV}</text
				>
				<text
					x={epochLossCDF.W / 2}
					y={epochLossCDF.PAD + 8}
					text-anchor="middle"
					font-size="7"
					fill="var(--ch-teal-strong)">median {epochLossCDF.medLoss}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				CDF of hyperopt loss function values · teal S-curve · dashed p10 line · left-skewed = most
				epochs achieve low loss · steep right tail = few poorly-tuned configs
			</p>
		</section>
	{/if}
	{#if epochSharpeHistogram}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Sharpe Ratio Distribution (Epochs)
			</h3>
			<svg
				viewBox="0 0 {epochSharpeHistogram.W} {epochSharpeHistogram.H}"
				class="w-full"
				style="height:{epochSharpeHistogram.H}px"
			>
				{#each epochSharpeHistogram.counts as count, i (i)}
					{@const x = epochSharpeHistogram.PAD + i * (epochSharpeHistogram.bw + 1)}
					{@const bh = Math.max(
						1,
						(count / epochSharpeHistogram.maxCount) *
							(epochSharpeHistogram.H - epochSharpeHistogram.PAD * 2)
					)}
					{@const y = epochSharpeHistogram.H - epochSharpeHistogram.PAD - bh}
					{@const binMid =
						Number(epochSharpeHistogram.minV) + (i + 0.5) * epochSharpeHistogram.step}
					{@const color =
						binMid >= 1 ? 'var(--ch-profit)' : binMid >= 0 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
					<rect {x} {y} width={epochSharpeHistogram.bw} height={bh} rx="1" style="fill:{color}" />
				{/each}
				<text
					x={epochSharpeHistogram.PAD}
					y={epochSharpeHistogram.H - 1}
					font-size="6"
					fill="var(--ch-axis-muted)">{epochSharpeHistogram.minV}</text
				>
				<text
					x={epochSharpeHistogram.W - epochSharpeHistogram.PAD}
					y={epochSharpeHistogram.H - 1}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{epochSharpeHistogram.maxV}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				12-bin histogram of Sharpe ratios across epochs · green≥1 · teal 0-1 · red&lt;0 ·
				right-skewed = most configs achieve positive risk-adjusted returns
			</p>
		</section>
	{/if}
	{#if epochRollingBestCalmar}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Rolling Best Calmar Exploration Curve
			</h3>
			<svg
				viewBox="0 0 {epochRollingBestCalmar.W} {epochRollingBestCalmar.H}"
				class="w-full"
				style="height:{epochRollingBestCalmar.H}px"
			>
				<polyline
					points={epochRollingBestCalmar.polyline}
					fill="none"
					stroke="var(--ch-violet-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={epochRollingBestCalmar.PAD}
					y={epochRollingBestCalmar.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{epochRollingBestCalmar.minC}</text
				>
				<text
					x={epochRollingBestCalmar.W - epochRollingBestCalmar.PAD}
					y={epochRollingBestCalmar.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{epochRollingBestCalmar.maxC}</text
				>
				<text
					x={epochRollingBestCalmar.W - epochRollingBestCalmar.PAD}
					y={epochRollingBestCalmar.PAD + 8}
					text-anchor="end"
					font-size="6.5"
					fill="var(--ch-violet-strong)">best {epochRollingBestCalmar.lastBest}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Rolling best Calmar ratio as hyperopt progresses · purple monotonic curve · flat plateau =
				search converged · sharp jump = major improvement found late
			</p>
		</section>
	{/if}
	{#if epochProfitVsSortino}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Profit Factor vs Sortino Scatter
			</h3>
			<svg
				viewBox="0 0 {epochProfitVsSortino.W} {epochProfitVsSortino.H}"
				class="w-full"
				style="height:{epochProfitVsSortino.H}px"
			>
				<line
					x1={epochProfitVsSortino.zeroX}
					y1={epochProfitVsSortino.PAD}
					x2={epochProfitVsSortino.zeroX}
					y2={epochProfitVsSortino.H - epochProfitVsSortino.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				<line
					x1={epochProfitVsSortino.PAD}
					y1={epochProfitVsSortino.zeroY}
					x2={epochProfitVsSortino.W - epochProfitVsSortino.PAD}
					y2={epochProfitVsSortino.zeroY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.7"
					stroke-dasharray="3,2"
				/>
				{#each epochProfitVsSortino.pts as p, _i (_i)}
					{@const cx = epochProfitVsSortino.toX(p.profit)}
					{@const cy = epochProfitVsSortino.toY(p.sortino)}
					{@const color =
						p.profit > 1 && p.sortino > 0
							? 'var(--ch-teal)'
							: p.profit > 1
								? 'var(--ch-warn-light)'
								: 'var(--ch-loss-light)'}
					<circle {cx} {cy} r="2" style="fill:{color}" />
				{/each}
				<text
					x={epochProfitVsSortino.PAD}
					y={epochProfitVsSortino.H - 2}
					font-size="5.5"
					fill="var(--ch-axis-muted)">{epochProfitVsSortino.minP}</text
				>
				<text
					x={epochProfitVsSortino.W - epochProfitVsSortino.PAD}
					y={epochProfitVsSortino.H - 2}
					text-anchor="end"
					font-size="5.5"
					fill="var(--ch-axis-muted)">{epochProfitVsSortino.maxP}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Profit factor (X) vs Sortino ratio (Y) per epoch · teal=both positive · yellow=PF&gt;1 only
				· red=PF≤1 · top-right = configs that profit efficiently with low downside risk
			</p>
		</section>
	{/if}
	{#if epochWinRateByEpochQuartile}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Win Rate% by Epoch Quartile
			</h3>
			<svg
				viewBox="0 0 {epochWinRateByEpochQuartile.W} {epochWinRateByEpochQuartile.H}"
				class="w-full"
				style="height:{epochWinRateByEpochQuartile.H}px"
			>
				{#each epochWinRateByEpochQuartile.rows as row, i (i)}
					{@const x = epochWinRateByEpochQuartile.PAD + i * (epochWinRateByEpochQuartile.bw + 2)}
					{@const bh = Math.max(
						2,
						(row.wr / 100) *
							(epochWinRateByEpochQuartile.H - epochWinRateByEpochQuartile.PAD * 2 - 12)
					)}
					{@const y = epochWinRateByEpochQuartile.H - epochWinRateByEpochQuartile.PAD - 12 - bh}
					{@const color =
						row.wr >= 55 ? 'var(--ch-profit)' : row.wr >= 45 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
					<rect
						{x}
						{y}
						width={epochWinRateByEpochQuartile.bw}
						height={bh}
						rx="2"
						style="fill:{color}"
					/>
					<text
						x={x + epochWinRateByEpochQuartile.bw / 2}
						y={epochWinRateByEpochQuartile.H - 12}
						text-anchor="middle"
						font-size="7.5"
						fill="var(--ch-axis-strong)">{row.label}</text
					>
					<text
						x={x + epochWinRateByEpochQuartile.bw / 2}
						y={y - 2}
						text-anchor="middle"
						font-size="6.5"
						fill={color}>{row.wr.toFixed(0)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				% epochs with win ratio &gt;50% by search quartile (Q1=early, Q4=late) · rising Q4 = search
				converges toward better configs · falling = early results dominated
			</p>
		</section>
	{/if}
	{#if epochBestSharpeByTF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Best Sharpe by Timeframe (Epochs)
			</h3>
			<svg
				viewBox="0 0 {epochBestSharpeByTF.W} {epochBestSharpeByTF.H}"
				class="w-full"
				style="height:{epochBestSharpeByTF.H}px"
			>
				<line
					x1={epochBestSharpeByTF.zeroX}
					y1="0"
					x2={epochBestSharpeByTF.zeroX}
					y2={epochBestSharpeByTF.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.8"
				/>
				{#each epochBestSharpeByTF.rows as row, i (i)}
					{@const y = epochBestSharpeByTF.PAD + i * 20}
					{@const bw = Math.max(
						2,
						(Math.abs(row.best) / epochBestSharpeByTF.maxAbs) * (epochBestSharpeByTF.barMaxW / 2)
					)}
					{@const x = row.best >= 0 ? epochBestSharpeByTF.zeroX : epochBestSharpeByTF.zeroX - bw}
					{@const color =
						row.best >= 1
							? 'var(--ch-profit)'
							: row.best >= 0
								? 'var(--ch-teal)'
								: 'var(--ch-loss)'}
					<text x={epochBestSharpeByTF.PAD} y={y + 13} font-size="8" fill="var(--ch-axis-strong)"
						>{row.tf}</text
					>
					<rect {x} {y} width={bw} height="14" rx="2" fill={color} />
					<text
						x={row.best >= 0
							? epochBestSharpeByTF.zeroX + bw + 2
							: epochBestSharpeByTF.zeroX - bw - 2}
						y={y + 11}
						text-anchor={row.best >= 0 ? 'start' : 'end'}
						font-size="6.5"
						fill={color}>{row.best.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Best Sharpe achieved per timeframe across all epochs · green≥1 · teal≥0 · red&lt;0 · reveals
				which timeframes produce the highest risk-adjusted hyperopt results
			</p>
		</section>
	{/if}
	{#if epochDrawdownByStrategy}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Avg Max Drawdown% by Strategy (Epochs)
			</h3>
			<svg
				viewBox="0 0 {epochDrawdownByStrategy.W} {epochDrawdownByStrategy.H}"
				class="w-full"
				style="height:{epochDrawdownByStrategy.H}px"
			>
				{#each epochDrawdownByStrategy.rows as row, i (i)}
					{@const y = epochDrawdownByStrategy.PAD + i * 18}
					{@const bw = Math.max(
						2,
						(row.avg / epochDrawdownByStrategy.maxAvg) * epochDrawdownByStrategy.barMaxW
					)}
					{@const color =
						row.avg <= 8 ? 'var(--ch-profit)' : row.avg <= 20 ? 'var(--ch-warn)' : 'var(--ch-loss)'}
					<text
						x={epochDrawdownByStrategy.PAD}
						y={y + 12}
						font-size="7"
						fill="var(--ch-axis-strong)">{row.name}</text
					>
					<rect
						x={epochDrawdownByStrategy.PAD + 80}
						{y}
						width={bw}
						height="13"
						rx="2"
						fill={color}
					/>
					<text
						x={epochDrawdownByStrategy.PAD + 80 + bw + 3}
						y={y + 12}
						font-size="6.5"
						fill={color}>{row.avg.toFixed(1)}%</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg max drawdown% per strategy across epochs · green≤8% · yellow≤20% · red&gt;20% ·
				strategies with low avg DD are more stable hyperopt candidates
			</p>
		</section>
	{/if}
	{#if epochCalmarByWinRateBucket}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Calmar Ratio by Win Rate Bucket
			</h3>
			<svg
				viewBox="0 0 {epochCalmarByWinRateBucket.W} {epochCalmarByWinRateBucket.H}"
				class="w-full"
				style="height:{epochCalmarByWinRateBucket.H}px"
			>
				<line
					x1={epochCalmarByWinRateBucket.PAD}
					y1={epochCalmarByWinRateBucket.midY}
					x2={epochCalmarByWinRateBucket.W - epochCalmarByWinRateBucket.PAD}
					y2={epochCalmarByWinRateBucket.midY}
					stroke="var(--ch-axis-muted)"
					stroke-width="0.5"
				/>
				{#each epochCalmarByWinRateBucket.rows as row, i (i)}
					{@const x = epochCalmarByWinRateBucket.PAD + i * (epochCalmarByWinRateBucket.bw + 2)}
					{@const barH = Math.max(
						2,
						(Math.abs(row.avg) / epochCalmarByWinRateBucket.maxAbs) *
							(epochCalmarByWinRateBucket.midY - 6)
					)}
					{@const y =
						row.avg >= 0 ? epochCalmarByWinRateBucket.midY - barH : epochCalmarByWinRateBucket.midY}
					{@const color =
						row.avg >= 1 ? 'var(--ch-profit)' : row.avg >= 0 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
					<rect {x} {y} width={epochCalmarByWinRateBucket.bw} height={barH} rx="2" fill={color} />
					<text
						x={x + epochCalmarByWinRateBucket.bw / 2}
						y={epochCalmarByWinRateBucket.H - 1}
						text-anchor="middle"
						font-size="6.5"
						fill="var(--ch-axis-strong)">{row.label}</text
					>
					<text
						x={x + epochCalmarByWinRateBucket.bw / 2}
						y={row.avg >= 0 ? y - 2 : y + barH + 8}
						text-anchor="middle"
						font-size="6"
						fill={color}>{row.avg.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg Calmar ratio by win rate quartile · green≥1 · teal≥0 · red&lt;0 · reveals if higher win
				rate also delivers better risk-adjusted return per unit of drawdown
			</p>
		</section>
	{/if}
	{#if epochTradeCountCDF}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Epoch Trade Count CDF
			</h3>
			<svg
				viewBox="0 0 {epochTradeCountCDF.W} {epochTradeCountCDF.H}"
				class="w-full"
				style="height:{epochTradeCountCDF.H}px"
			>
				<polyline
					points={epochTradeCountCDF.polyline}
					fill="none"
					stroke="var(--ch-teal-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={epochTradeCountCDF.PAD}
					y={epochTradeCountCDF.H - 2}
					font-size="6"
					fill="var(--ch-axis-muted)">{epochTradeCountCDF.minV}</text
				>
				<text
					x={epochTradeCountCDF.W - epochTradeCountCDF.PAD}
					y={epochTradeCountCDF.H - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">{epochTradeCountCDF.maxV}</text
				>
				<text
					x={epochTradeCountCDF.W / 2}
					y={epochTradeCountCDF.PAD + 8}
					text-anchor="middle"
					font-size="7"
					fill="var(--ch-teal-strong)">median {epochTradeCountCDF.median}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				CDF of trade count per hyperopt epoch · teal S-curve · left tail = epochs with sparse trades
				(unreliable metrics) · high median = optimisation found strategies trading frequently
			</p>
		</section>
	{/if}
	{#if epochProfitByDrawdownQuartile}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Profit Factor by Drawdown Quartile
			</h3>
			<svg
				viewBox="0 0 {epochProfitByDrawdownQuartile.W} {epochProfitByDrawdownQuartile.H}"
				class="w-full"
				style="height:{epochProfitByDrawdownQuartile.H}px"
			>
				{#each epochProfitByDrawdownQuartile.rows as row, i (i)}
					{@const x =
						epochProfitByDrawdownQuartile.PAD + i * (epochProfitByDrawdownQuartile.bw + 2)}
					{@const barH = Math.max(
						2,
						(row.avg / epochProfitByDrawdownQuartile.maxAvg) *
							(epochProfitByDrawdownQuartile.H - 16)
					)}
					{@const y = epochProfitByDrawdownQuartile.H - barH - 8}
					{@const color =
						row.avg >= 1.5
							? 'var(--ch-profit)'
							: row.avg >= 1
								? 'var(--ch-teal)'
								: 'var(--ch-warn)'}
					<rect
						{x}
						{y}
						width={epochProfitByDrawdownQuartile.bw}
						height={barH}
						rx="2"
						fill={color}
					/>
					<text
						x={x + epochProfitByDrawdownQuartile.bw / 2}
						y={epochProfitByDrawdownQuartile.H - 1}
						text-anchor="middle"
						font-size="6.5"
						fill="var(--ch-axis-strong)">{row.label}</text
					>
					<text
						x={x + epochProfitByDrawdownQuartile.bw / 2}
						y={y - 2}
						text-anchor="middle"
						font-size="6"
						fill={color}>{row.avg.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg profit factor by drawdown quartile · Q1=lowest DD · green≥1.5 · teal≥1 · low DD epochs
				should still maintain profit factor above 1 — confirms resilience under drawdown constraint
			</p>
		</section>
	{/if}
	{#if epochSharpeVsCalmarScatter2}
		<section class="rounded-xl border border-border bg-card p-4">
			<h3 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Sharpe vs Calmar Scatter
			</h3>
			<svg
				viewBox="0 0 {epochSharpeVsCalmarScatter2.W} {epochSharpeVsCalmarScatter2.H}"
				class="w-full"
				style="height:{epochSharpeVsCalmarScatter2.H}px"
			>
				<line
					x1={epochSharpeVsCalmarScatter2.midX}
					y1={0}
					x2={epochSharpeVsCalmarScatter2.midX}
					y2={epochSharpeVsCalmarScatter2.H}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				<line
					x1={0}
					y1={epochSharpeVsCalmarScatter2.midY}
					x2={epochSharpeVsCalmarScatter2.W}
					y2={epochSharpeVsCalmarScatter2.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				{#each epochSharpeVsCalmarScatter2.pts as p, _i (_i)}
					{@const cx =
						epochSharpeVsCalmarScatter2.midX +
						(p.x / epochSharpeVsCalmarScatter2.maxX) *
							(epochSharpeVsCalmarScatter2.W / 2 - epochSharpeVsCalmarScatter2.PAD)}
					{@const cy =
						epochSharpeVsCalmarScatter2.midY -
						(p.y / epochSharpeVsCalmarScatter2.maxY) *
							(epochSharpeVsCalmarScatter2.H / 2 - epochSharpeVsCalmarScatter2.PAD)}
					{@const color =
						p.wr >= 55
							? 'var(--ch-profit-light)'
							: p.wr >= 45
								? 'var(--ch-teal-light)'
								: 'var(--ch-loss-light)'}
					<circle {cx} {cy} r="2" fill={color} />
				{/each}
				<text
					x={epochSharpeVsCalmarScatter2.W - 2}
					y={epochSharpeVsCalmarScatter2.midY - 2}
					text-anchor="end"
					font-size="6"
					fill="var(--ch-axis-muted)">Sharpe→</text
				>
				<text
					x={epochSharpeVsCalmarScatter2.PAD}
					y={epochSharpeVsCalmarScatter2.PAD + 6}
					font-size="6"
					fill="var(--ch-axis-muted)">Calmar↑</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Scatter: Sharpe (X) vs Calmar (Y) · green=WR≥55% · teal=WR≥45% · red=WR&lt;45% · top-right
				quadrant = best epochs with both high Sharpe and high Calmar
			</p>
		</section>
	{/if}
	{#if epochWinRateTrend}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">Win Rate Trend (Smoothed)</h3>
			<svg
				viewBox={`0 0 ${epochWinRateTrend.W} ${epochWinRateTrend.H}`}
				width="100%"
				style="height:65px"
			>
				<line
					x1={epochWinRateTrend.PAD}
					y1={epochWinRateTrend.H - epochWinRateTrend.PAD}
					x2={epochWinRateTrend.W - epochWinRateTrend.PAD}
					y2={epochWinRateTrend.H - epochWinRateTrend.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				<line
					x1={epochWinRateTrend.PAD}
					y1={epochWinRateTrend.toY(50)}
					x2={epochWinRateTrend.W - epochWinRateTrend.PAD}
					y2={epochWinRateTrend.toY(50)}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
					stroke-dasharray="2,2"
				/>
				<polyline
					points={epochWinRateTrend.polyline}
					fill="none"
					stroke="var(--ch-teal-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={epochWinRateTrend.PAD}
					y={epochWinRateTrend.PAD + 6}
					font-size="5.5"
					fill="var(--ch-axis-muted)">{epochWinRateTrend.maxWR.toFixed(1)}%</text
				>
				<text
					x={epochWinRateTrend.PAD}
					y={epochWinRateTrend.H - epochWinRateTrend.PAD - 1}
					font-size="5.5"
					fill="var(--ch-axis-muted)">{epochWinRateTrend.minWR.toFixed(1)}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Rolling-smoothed win rate% across epoch index · teal line · dashed at 50% · rising trend =
				optimizer finding better entry conditions over time
			</p>
		</section>
	{/if}
	{#if epochSortinoBySharpeQuartile}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">
				Avg Sortino by Sharpe Quartile
			</h3>
			<svg
				viewBox={`0 0 ${epochSortinoBySharpeQuartile.W} ${epochSortinoBySharpeQuartile.H}`}
				width="100%"
				style="height:80px"
			>
				<line
					x1={epochSortinoBySharpeQuartile.midX}
					y1={epochSortinoBySharpeQuartile.PAD}
					x2={epochSortinoBySharpeQuartile.midX}
					y2={epochSortinoBySharpeQuartile.H - epochSortinoBySharpeQuartile.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				{#each epochSortinoBySharpeQuartile.bars as b, i (i)}
					{@const barW =
						(Math.abs(b.avg) / epochSortinoBySharpeQuartile.maxAbs) *
						(epochSortinoBySharpeQuartile.midX - epochSortinoBySharpeQuartile.PAD)}
					{@const y = epochSortinoBySharpeQuartile.PAD + i * (epochSortinoBySharpeQuartile.bh + 2)}
					{@const color = b.avg >= 0 ? 'var(--ch-teal)' : 'var(--ch-loss)'}
					{@const x =
						b.avg >= 0
							? epochSortinoBySharpeQuartile.midX
							: epochSortinoBySharpeQuartile.midX - barW}
					<rect {x} {y} width={barW} height={epochSortinoBySharpeQuartile.bh} fill={color} rx="1" />
					<text
						x={epochSortinoBySharpeQuartile.midX - 2}
						y={y + epochSortinoBySharpeQuartile.bh / 2 + 2}
						text-anchor="end"
						font-size="6"
						fill="var(--ch-axis)">{b.label}</text
					>
					<text
						x={epochSortinoBySharpeQuartile.midX + barW + 2}
						y={y + epochSortinoBySharpeQuartile.bh / 2 + 2}
						font-size="5.5"
						fill="var(--ch-axis)">{b.avg.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg Sortino ratio by Sharpe quartile (Q1=lowest Sharpe, Q4=highest) · teal=positive ·
				red=negative · high Sharpe should correlate with high Sortino
			</p>
		</section>
	{/if}
	{#if epochProfitFactorCDF}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">Profit Factor CDF</h3>
			<svg
				viewBox={`0 0 ${epochProfitFactorCDF.W} ${epochProfitFactorCDF.H}`}
				width="100%"
				style="height:65px"
			>
				<line
					x1={epochProfitFactorCDF.PAD}
					y1={epochProfitFactorCDF.H - epochProfitFactorCDF.PAD}
					x2={epochProfitFactorCDF.W - epochProfitFactorCDF.PAD}
					y2={epochProfitFactorCDF.H - epochProfitFactorCDF.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				<line
					x1={epochProfitFactorCDF.toX(1)}
					y1={epochProfitFactorCDF.PAD}
					x2={epochProfitFactorCDF.toX(1)}
					y2={epochProfitFactorCDF.H - epochProfitFactorCDF.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
					stroke-dasharray="2,2"
				/>
				<polyline
					points={epochProfitFactorCDF.polyline}
					fill="none"
					stroke="var(--ch-warn)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={epochProfitFactorCDF.PAD}
					y={epochProfitFactorCDF.H - 2}
					font-size="5.5"
					fill="var(--ch-axis-muted)">{epochProfitFactorCDF.minV}</text
				>
				<text
					x={epochProfitFactorCDF.W - epochProfitFactorCDF.PAD}
					y={epochProfitFactorCDF.H - 2}
					text-anchor="end"
					font-size="5.5"
					fill="var(--ch-axis-muted)">{epochProfitFactorCDF.maxV}</text
				>
				<text
					x={epochProfitFactorCDF.W / 2}
					y={epochProfitFactorCDF.PAD + 8}
					text-anchor="middle"
					font-size="7"
					fill="var(--ch-warn)">median {epochProfitFactorCDF.median}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				CDF of profit factor across epochs · orange S-curve · dashed at PF=1 (breakeven) · most
				epochs above 1 = optimizer finding profitable configs · fat right tail = high PF outliers
			</p>
		</section>
	{/if}
	{#if epochAvgTradeCountByWR}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">
				Avg Trade Count by Win Rate Bucket
			</h3>
			<svg
				viewBox={`0 0 ${epochAvgTradeCountByWR.W} ${epochAvgTradeCountByWR.H}`}
				width="100%"
				style="height:65px"
			>
				{#each epochAvgTradeCountByWR.bars as b, i (i)}
					{@const bh =
						(b.avg / epochAvgTradeCountByWR.maxAvg) *
						(epochAvgTradeCountByWR.H - epochAvgTradeCountByWR.PAD * 2)}
					{@const x = epochAvgTradeCountByWR.PAD + i * (epochAvgTradeCountByWR.bw + 4)}
					{@const y = epochAvgTradeCountByWR.H - epochAvgTradeCountByWR.PAD - bh}
					{@const color =
						b.label === '>60%'
							? 'var(--ch-profit)'
							: b.label === '50-60%'
								? 'var(--ch-teal)'
								: b.label === '40-50%'
									? 'var(--ch-warn)'
									: 'var(--ch-loss)'}
					<rect {x} {y} width={epochAvgTradeCountByWR.bw} height={bh} fill={color} rx="1" />
					<text
						x={x + epochAvgTradeCountByWR.bw / 2}
						y={epochAvgTradeCountByWR.H}
						text-anchor="middle"
						font-size="6"
						fill="var(--ch-axis)">{b.label}</text
					>
					<text
						x={x + epochAvgTradeCountByWR.bw / 2}
						y={y - 2}
						text-anchor="middle"
						font-size="5.5"
						fill={color}>{b.avg.toFixed(0)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg trade count by win rate bucket · green=WR&gt;60% · teal=50-60% · yellow=40-50% ·
				red&lt;40% · low trade count at high WR may indicate overfitting
			</p>
		</section>
	{/if}
	{#if epochMaxDrawdownCDF}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">Max Drawdown% CDF</h3>
			<svg
				viewBox={`0 0 ${epochMaxDrawdownCDF.W} ${epochMaxDrawdownCDF.H}`}
				width="100%"
				style="height:65px"
			>
				<line
					x1={epochMaxDrawdownCDF.PAD}
					y1={epochMaxDrawdownCDF.H - epochMaxDrawdownCDF.PAD}
					x2={epochMaxDrawdownCDF.W - epochMaxDrawdownCDF.PAD}
					y2={epochMaxDrawdownCDF.H - epochMaxDrawdownCDF.PAD}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
				/>
				<polyline
					points={epochMaxDrawdownCDF.polyline}
					fill="none"
					stroke="var(--ch-loss-strong)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={epochMaxDrawdownCDF.PAD}
					y={epochMaxDrawdownCDF.H - 2}
					font-size="5.5"
					fill="var(--ch-axis-muted)">{epochMaxDrawdownCDF.minV}%</text
				>
				<text
					x={epochMaxDrawdownCDF.W - epochMaxDrawdownCDF.PAD}
					y={epochMaxDrawdownCDF.H - 2}
					text-anchor="end"
					font-size="5.5"
					fill="var(--ch-axis-muted)">{epochMaxDrawdownCDF.maxV}%</text
				>
				<text
					x={epochMaxDrawdownCDF.W / 2}
					y={epochMaxDrawdownCDF.PAD + 8}
					text-anchor="middle"
					font-size="7"
					fill="var(--ch-loss-strong)">median {epochMaxDrawdownCDF.median}%</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				CDF of max drawdown% across epochs · red curve · steep left = most configs have low DD ·
				right tail = high-DD outlier configs that should be filtered out
			</p>
		</section>
	{/if}
	{#if epochSharpeByTradeCountBucket}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">
				Avg Sharpe by Trade Count Bucket
			</h3>
			<svg
				viewBox={`0 0 ${epochSharpeByTradeCountBucket.W} ${epochSharpeByTradeCountBucket.H}`}
				width="100%"
				style="height:65px"
			>
				<line
					x1={epochSharpeByTradeCountBucket.PAD}
					y1={epochSharpeByTradeCountBucket.midY}
					x2={epochSharpeByTradeCountBucket.W - epochSharpeByTradeCountBucket.PAD}
					y2={epochSharpeByTradeCountBucket.midY}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
					stroke-dasharray="2,2"
				/>
				{#each epochSharpeByTradeCountBucket.bars as b, i (i)}
					{@const bh =
						(Math.abs(b.avg) / epochSharpeByTradeCountBucket.maxAbs) *
						(epochSharpeByTradeCountBucket.midY - epochSharpeByTradeCountBucket.PAD)}
					{@const x =
						epochSharpeByTradeCountBucket.PAD + i * (epochSharpeByTradeCountBucket.bw + 12)}
					{@const y =
						b.avg >= 0
							? epochSharpeByTradeCountBucket.midY - bh
							: epochSharpeByTradeCountBucket.midY}
					{@const color =
						b.label === 'High'
							? 'var(--ch-profit)'
							: b.label === 'Mid'
								? 'var(--ch-teal)'
								: 'var(--ch-warn)'}
					<rect {x} {y} width={epochSharpeByTradeCountBucket.bw} height={bh} fill={color} rx="2" />
					<text
						x={x + epochSharpeByTradeCountBucket.bw / 2}
						y={epochSharpeByTradeCountBucket.H}
						text-anchor="middle"
						font-size="7"
						fill="var(--ch-axis-strong)">{b.label}</text
					>
					<text
						x={x + epochSharpeByTradeCountBucket.bw / 2}
						y={b.avg >= 0 ? y - 3 : y + bh + 9}
						text-anchor="middle"
						font-size="6.5"
						fill={color}>{b.avg.toFixed(2)}</text
					>
				{/each}
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				Avg Sharpe by trade count bucket (Low/Mid/High) · high trade count = more data → more
				reliable Sharpe · low count high Sharpe may be noise
			</p>
		</section>
	{/if}
	{#if epochRollingCalmar}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">
				Rolling Calmar Ratio Trend (10-epoch window)
			</h3>
			<svg
				viewBox={`0 0 ${epochRollingCalmar.W} ${epochRollingCalmar.H}`}
				width="100%"
				style="height:65px"
			>
				<line
					x1={epochRollingCalmar.PAD}
					y1={epochRollingCalmar.y0}
					x2={epochRollingCalmar.W - epochRollingCalmar.PAD}
					y2={epochRollingCalmar.y0}
					stroke="var(--ch-axis-faint)"
					stroke-width="0.5"
					stroke-dasharray="2,2"
				/>
				<polyline
					points={epochRollingCalmar.polyline}
					fill="none"
					stroke="var(--ch-warn)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={epochRollingCalmar.PAD}
					y={epochRollingCalmar.H}
					font-size="5.5"
					fill="var(--ch-axis-muted)">{epochRollingCalmar.minV}</text
				>
				<text
					x={epochRollingCalmar.W - epochRollingCalmar.PAD}
					y={epochRollingCalmar.H}
					text-anchor="end"
					font-size="5.5"
					fill="var(--ch-axis-muted)">{epochRollingCalmar.maxV}</text
				>
				<text
					x={epochRollingCalmar.PAD}
					y={epochRollingCalmar.y0 - 2}
					font-size="5"
					fill="var(--ch-axis-muted)">0</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				10-epoch rolling Calmar ratio across {epochRollingCalmar.n} hyperopt epochs · orange line · rising
				trend = hyperopt discovering better return-to-DD configurations
			</p>
		</section>
	{/if}
	{#if epochProfitCDFByLoss}
		<section class="rounded-lg border border-border bg-card p-3">
			<h3 class="mb-1 text-xs font-semibold text-muted-foreground">
				Profit Factor CDF (all epochs)
			</h3>
			<svg
				viewBox={`0 0 ${epochProfitCDFByLoss.W} ${epochProfitCDFByLoss.H}`}
				width="100%"
				style="height:65px"
			>
				<line
					x1={epochProfitCDFByLoss.toX(1)}
					y1={epochProfitCDFByLoss.PAD}
					x2={epochProfitCDFByLoss.toX(1)}
					y2={epochProfitCDFByLoss.H - epochProfitCDFByLoss.PAD}
					stroke="var(--ch-axis-muted)"
					stroke-width="0.6"
					stroke-dasharray="2,2"
				/>
				<polyline
					points={epochProfitCDFByLoss.polyline}
					fill="none"
					stroke="var(--ch-violet)"
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text
					x={epochProfitCDFByLoss.PAD}
					y={epochProfitCDFByLoss.H}
					font-size="5.5"
					fill="var(--ch-axis-muted)">PF {epochProfitCDFByLoss.minV}</text
				>
				<text
					x={epochProfitCDFByLoss.W - epochProfitCDFByLoss.PAD}
					y={epochProfitCDFByLoss.H}
					text-anchor="end"
					font-size="5.5"
					fill="var(--ch-axis-muted)">{epochProfitCDFByLoss.maxV}</text
				>
				<text
					x={epochProfitCDFByLoss.toX(1) + 3}
					y={epochProfitCDFByLoss.PAD + 7}
					font-size="5"
					fill="var(--ch-axis-muted)">PF=1</text
				>
				<text
					x={epochProfitCDFByLoss.W / 2}
					y={epochProfitCDFByLoss.PAD + 7}
					text-anchor="middle"
					font-size="6"
					fill="var(--ch-violet)">med {epochProfitCDFByLoss.median}</text
				>
			</svg>
			<p class="mt-1 text-[9px] text-muted-foreground">
				CDF of profit factor across hyperopt epochs · purple S-curve · dashed at PF=1 (breakeven) ·
				median annotated · right-skewed = most epochs profitable
			</p>
		</section>
	{/if}
</main>
