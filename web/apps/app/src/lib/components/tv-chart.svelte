<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import type {
		IChartApi,
		ISeriesApi,
		ISeriesMarkersPluginApi,
		SeriesMarker,
		Time,
		UTCTimestamp
	} from 'lightweight-charts';
	import type { OhlcRow, BacktestTrade } from '$lib/types';

	interface Props {
		rows: OhlcRow[];
		trades?: BacktestTrade[];
		height?: number;
	}

	let { rows, trades = [], height = 520 }: Props = $props();

	let containerEl: HTMLDivElement;

	// chart internals — assigned after mount
	let chart: IChartApi | null = null;
	let candleSeries: ISeriesApi<'Candlestick'> | null = null;
	let volumeSeries: ISeriesApi<'Histogram'> | null = null;
	let emaSeries: ISeriesApi<'Line'> | null = null;
	let candleMarkers: ISeriesMarkersPluginApi<Time> | null = null; // v5: separate markers primitive
	let ro: ResizeObserver | null = null;

	// ── helpers ────────────────────────────────────────────────────────────────

	function toUnix(iso: string): UTCTimestamp {
		return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
	}

	function calcEma(data: { time: UTCTimestamp; value: number }[], period: number) {
		const k = 2 / (period + 1);
		const out: { time: UTCTimestamp; value: number }[] = [];
		let prev = data[0].value;
		for (const d of data) {
			prev = d.value * k + prev * (1 - k);
			out.push({ time: d.time, value: prev });
		}
		return out.slice(period);
	}

	function mapCandles() {
		return rows.map((r) => ({
			time: toUnix(r.bucket),
			open: r.open,
			high: r.high,
			low: r.low,
			close: r.close
		}));
	}

	function mapVolume() {
		// lightweight-charts canvas colors must be resolved hex/rgba — read
		// the live computed value of our BDV vars at chart-paint time so
		// volume bars retune for the current theme.
		const css = getComputedStyle(document.documentElement);
		const profit = (css.getPropertyValue('--profit').trim() || '#4ADE80') + '40';
		const loss = (css.getPropertyValue('--loss').trim() || '#FF5C7A') + '40';
		return rows.map((r) => ({
			time: toUnix(r.bucket),
			value: r.volume,
			color: r.close >= r.open ? profit : loss
		}));
	}

	function buildMarkers() {
		const markers: SeriesMarker<UTCTimestamp>[] = [];

		for (const trade of trades) {
			// Entry marker
			markers.push({
				time: toUnix(trade.open_date),
				position: 'belowBar',
				shape: 'arrowUp',
				color:
					getComputedStyle(document.documentElement).getPropertyValue('--gold-500').trim() ||
					'#F5B340',
				text: '▲'
			});

			// Exit marker
			if (trade.close_date) {
				const isWinner = (trade.profit_abs ?? 0) > 0;
				const absVal = Math.abs(trade.profit_abs ?? 0);
				const css = getComputedStyle(document.documentElement);
				markers.push({
					time: toUnix(trade.close_date),
					position: 'aboveBar',
					shape: 'arrowDown',
					color: isWinner
						? css.getPropertyValue('--profit').trim() || '#4ADE80'
						: css.getPropertyValue('--loss').trim() || '#FF5C7A',
					text: isWinner ? `$+${absVal.toFixed(0)}` : `-$${absVal.toFixed(0)}`
				});
			}
		}

		// lightweight-charts requires markers sorted by time ascending
		markers.sort((a, b) => a.time - b.time);
		return markers;
	}

	function applyData() {
		if (!candleSeries || !volumeSeries || !emaSeries) return;

		const candles = mapCandles();
		const volume = mapVolume();

		candleSeries.setData(candles);
		volumeSeries.setData(volume);

		if (candles.length > 20) {
			const closes = candles.map((c) => ({ time: c.time, value: c.close }));
			emaSeries.setData(calcEma(closes, 20));
		} else {
			emaSeries.setData([]);
		}

		// markers — v5 uses createSeriesMarkers primitive (set up in onMount)
		const markers = buildMarkers();
		if (candleMarkers) {
			candleMarkers.setMarkers(markers);
		}

		// Force the time scale to fit all candles. Without this, lightweight-
		// charts sometimes initializes with an empty visible range when the
		// chart was created with width 0 (which happens during the
		// SvelteKit hydration / sidebar-layout transition).
		if (candles.length > 0 && chart) {
			chart.timeScale().fitContent();
		}
	}

	// ── lifecycle ───────────────────────────────────────────────────────────────

	onMount(async () => {
		// v5 API: series types are imported as symbols, then passed to addSeries(SeriesType, options).
		// The v4 helper methods (addCandlestickSeries, etc.) were removed.
		const {
			createChart,
			CrosshairMode,
			CandlestickSeries,
			LineSeries,
			HistogramSeries,
			createSeriesMarkers
		} = await import('lightweight-charts');

		// Resolve BDV theme vars to concrete hex/rgba so lightweight-charts
		// (canvas-based) renders with the current dark/light palette.
		const css = getComputedStyle(document.documentElement);
		const v = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
		const bg = v('--card', '#14132A');
		const fg = v('--foreground', '#F4F2FF');
		const grid = v('--border', 'rgba(255,255,255,0.10)');
		const profit = v('--profit', '#4ADE80');
		const loss = v('--loss', '#FF5C7A');
		const gold = v('--gold-500', '#F5B340');

		chart = createChart(containerEl, {
			width: containerEl.clientWidth,
			height,
			layout: {
				background: { color: bg },
				textColor: fg
			},
			grid: {
				vertLines: { color: grid },
				horzLines: { color: grid }
			},
			crosshair: {
				mode: CrosshairMode.Normal
			},
			rightPriceScale: {
				borderColor: grid
			},
			timeScale: {
				borderColor: grid,
				timeVisible: true,
				secondsVisible: false
			}
		});

		// ── top pane: candlestick ──────────────────────────────────────────────
		candleSeries = chart.addSeries(CandlestickSeries, {
			upColor: profit,
			downColor: loss,
			borderUpColor: profit,
			borderDownColor: loss,
			wickUpColor: profit,
			wickDownColor: loss
		});

		// v5: markers are now a separate primitive attached to a series
		candleMarkers = createSeriesMarkers(candleSeries, []);

		// ── top pane: EMA overlay (bear-eye gold) ─────────────────────────────
		emaSeries = chart.addSeries(LineSeries, {
			color: gold,
			lineWidth: 1,
			priceLineVisible: false,
			lastValueVisible: false
		});

		// ── bottom pane: volume histogram ─────────────────────────────────────
		volumeSeries = chart.addSeries(HistogramSeries, {
			priceFormat: { type: 'volume' },
			priceScaleId: 'volume',
			color: profit + '40'
		});

		chart.priceScale('volume').applyOptions({
			scaleMargins: { top: 0.8, bottom: 0 }
		});

		applyData();

		// Responsive resize
		ro = new ResizeObserver((entries) => {
			const entry = entries[0];
			if (entry && chart) {
				chart.resize(entry.contentRect.width, height);
			}
		});
		ro.observe(containerEl);
	});

	onDestroy(() => {
		ro?.disconnect();
		chart?.remove();
	});

	// React to prop changes after mount
	$effect(() => {
		// Touch reactive dependencies
		void rows;
		void trades;
		applyData();
	});
</script>

<div bind:this={containerEl} style="height: {height}px;"></div>
