<script lang="ts">
	import type { PageData } from './$types';
	import type { Lang } from '$lib/i18n';
	import type { SemiTicker, SemiSegment } from '$lib/types';

	let { data }: { data: PageData } = $props();
	const lang = $derived<Lang>((data as { lang?: Lang }).lang ?? 'zh');
	const tr = (zh: string, en: string) => (lang === 'zh' ? zh : en);

	const universe = $derived(data.universe as SemiTicker[]);
	const bySym = $derived(new Map(universe.map((t) => [t.symbol, t])));
	const tradeable = $derived(universe.filter((t) => t.tier !== 'benchmark'));

	// System-level value-chain bottleneck matrix (HBM/CoWoS/substrate/MLCC/VRM/cooling/power/optical).
	const segments = $derived((data as { segments?: SemiSegment[] }).segments ?? []);
	// 1-5 score → heat colour: 5 =极强瓶颈/强定价权 (hot) … 1 = 普通周期品 (cool).
	const heat = (s: number) =>
		s >= 5
			? 'var(--loss)'
			: s === 4
				? 'var(--warn)'
				: s === 3
					? 'var(--gold-500)'
					: 'var(--muted-foreground)';

	// ----- technology-trend lens: click a trend to highlight every stock exposed to it -----
	let selectedTrend = $state<string | null>(null);
	const allTrends = $derived.by(() => {
		const m = new Map<string, number>();
		for (const t of tradeable) for (const tag of t.trends ?? []) m.set(tag, (m.get(tag) ?? 0) + 1);
		return [...m.entries()].sort((a, b) => b[1] - a[1]);
	});
	const trendDimmed = (sym: string) =>
		selectedTrend != null && !(bySym.get(sym)?.trends?.includes(selectedTrend) ?? false);

	// ----- value-chain stages (left → right, from raw materials to demand) -----
	const LAYERS: { title: [string, string]; syms: string[] }[] = [
		{ title: ['原材料', 'Materials'], syms: ['LIN', 'ENTG', 'DD'] },
		{ title: ['设备', 'Equipment'], syms: ['ASML', 'AMAT', 'LRCX', 'KLAC', 'TER', 'MKSI'] },
		{ title: ['EDA · IP', 'EDA · IP'], syms: ['SNPS', 'CDNS', 'ARM'] },
		{ title: ['代工 · 内存', 'Foundry · Memory'], syms: ['TSM', 'MU', 'UMC', 'GFS'] },
		{ title: ['封测', 'OSAT'], syms: ['ASX', 'AMKR'] },
		{
			title: ['芯片设计', 'Chip designers'],
			syms: ['NVDA', 'AVGO', 'AMD', 'QCOM', 'TXN', 'MRVL', 'INTC']
		},
		{ title: ['互联', 'Interconnect'], syms: ['ANET', 'COHR', 'CRDO'] },
		{ title: ['系统', 'Systems'], syms: ['DELL', 'HPE', 'SMCI'] },
		{
			title: ['需求 · 云厂商', 'Demand · hyperscalers'],
			syms: ['GOOGL', 'MSFT', 'AMZN', 'ORCL', 'META']
		}
	];
	// directed supply edges [from → to]
	const EDGES: [string, string][] = [
		// materials + equipment → fab
		['LIN', 'TSM'],
		['ENTG', 'TSM'],
		['DD', 'TSM'],
		['ASML', 'TSM'],
		['AMAT', 'TSM'],
		['LRCX', 'TSM'],
		['KLAC', 'TSM'],
		['TER', 'TSM'],
		['MKSI', 'TSM'],
		// EDA/IP → designers
		['SNPS', 'NVDA'],
		['CDNS', 'NVDA'],
		['ARM', 'NVDA'],
		['ARM', 'AMD'],
		['ARM', 'QCOM'],
		['SNPS', 'AVGO'],
		// foundry/memory → designers
		['TSM', 'NVDA'],
		['TSM', 'AMD'],
		['TSM', 'AVGO'],
		['TSM', 'MRVL'],
		['TSM', 'QCOM'],
		['GFS', 'AMD'],
		['UMC', 'TXN'],
		['MU', 'NVDA'],
		['MU', 'AMD'],
		// designers → OSAT (advanced packaging) → systems
		['NVDA', 'AMKR'],
		['AMD', 'AMKR'],
		['AVGO', 'ASX'],
		['AMKR', 'DELL'],
		['ASX', 'SMCI'],
		// designers → interconnect
		['NVDA', 'ANET'],
		['NVDA', 'CRDO'],
		['AVGO', 'ANET'],
		['MRVL', 'COHR'],
		// interconnect → systems
		['ANET', 'DELL'],
		['CRDO', 'SMCI'],
		['COHR', 'SMCI'],
		// designers → systems (direct)
		['NVDA', 'DELL'],
		['NVDA', 'SMCI'],
		['AMD', 'HPE'],
		// systems → hyperscalers
		['DELL', 'MSFT'],
		['SMCI', 'META'],
		['HPE', 'AMZN'],
		['SMCI', 'GOOGL'],
		// designers → hyperscalers (direct GPU buys)
		['NVDA', 'MSFT'],
		['NVDA', 'GOOGL'],
		['NVDA', 'AMZN'],
		['NVDA', 'META'],
		['NVDA', 'ORCL']
	];

	// ----- layout (vertical: stages stack top→bottom; nodes spread across each band) -----
	const W = 1080;
	const BAND = 152;
	const TOP = 30;
	const H = TOP + LAYERS.length * BAND + 18;
	const ROWY = LAYERS.map((_, i) => TOP + i * BAND); // band top
	const maxCap = $derived(Math.max(...tradeable.map((t) => t.market_cap ?? 0), 1));

	type Node = { t: SemiTicker; x: number; y: number; r: number };
	const nodes = $derived.by(() => {
		const m = new Map<string, Node>();
		const left = 70,
			right = W - 50,
			span = right - left;
		LAYERS.forEach((layer, li) => {
			const members = layer.syms.map((s) => bySym.get(s)).filter(Boolean) as SemiTicker[];
			const cy = ROWY[li] + BAND * 0.52; // nodes sit below the band header
			members.forEach((t, i) => {
				const x =
					members.length === 1 ? (left + right) / 2 : left + (span * i) / (members.length - 1);
				const r = 10 + 24 * Math.sqrt((t.market_cap ?? 0) / maxCap);
				m.set(t.symbol, { t, x, y: cy, r });
			});
		});
		return m;
	});

	type Edge = { i: number; from: string; to: string; path: string; hub: boolean };
	const edges = $derived.by(
		() =>
			EDGES.map(([a, b], i): Edge | null => {
				const s = nodes.get(a),
					d = nodes.get(b);
				if (!s || !d) return null;
				const y1 = s.y + s.r,
					y2 = d.y - d.r,
					my = (y1 + y2) / 2;
				return {
					i,
					from: a,
					to: b,
					path: `M${s.x},${y1} C${s.x},${my} ${d.x},${my} ${d.x},${y2}`,
					hub: a === 'NVDA' || b === 'NVDA'
				};
			}).filter(Boolean) as Edge[]
	);

	// ----- edge interaction: hover (or tap to pin) highlights the link + its two nodes -----
	let hover = $state(-1);
	let pin = $state(-1);
	const active = $derived(pin >= 0 ? pin : hover);
	const activeEdge = $derived(active >= 0 ? (edges.find((e) => e.i === active) ?? null) : null);
	const activeNodes = $derived(activeEdge ? new Set([activeEdge.from, activeEdge.to]) : null);
	const activeInfo = $derived(activeEdge ? edgeInfo(activeEdge.from, activeEdge.to) : null);

	const STAGE_KIND = [
		'materials',
		'equipment',
		'eda',
		'fab',
		'osat',
		'design',
		'interconnect',
		'systems',
		'demand'
	];
	function stageOf(sym: string): string {
		for (let i = 0; i < LAYERS.length; i++) if (LAYERS[i].syms.includes(sym)) return STAGE_KIND[i];
		return '';
	}
	// Explain what the upstream→downstream relationship actually is — the "order" flowing on the edge.
	function edgeInfo(a: string, b: string): { zh: string; en: string } {
		const fn = bySym.get(a)?.name ?? a,
			tn = bySym.get(b)?.name ?? b;
		const sk = stageOf(a),
			tk = stageOf(b),
			mem = a === 'MU';
		if (sk === 'materials')
			return {
				zh: `${fn} 向 ${tn} 的晶圆厂供应电子级材料 / 特种气体 —— 蚀刻、沉积、光刻每一步都在消耗的耗材。无料停产。`,
				en: `${fn} supplies fab-grade materials / specialty gases to ${tn}'s fabs — consumables burned in every etch, deposition and litho step. No supply, no wafers.`
			};
		if (sk === 'equipment')
			return {
				zh: `${fn} 向 ${tn} 提供「${bySym.get(a)?.role ?? '制程设备'}」—— 产线上的机器，决定 ${tn} 能做到多先进的制程。`,
				en: `${fn} ships ${tn} its “${bySym.get(a)?.role ?? 'process equipment'}” — the tools on the line that cap how advanced a node ${tn} can run.`
			};
		if (sk === 'eda')
			return {
				zh: `${tn} 用 ${fn} 的${a === 'ARM' ? ' CPU 架构授权 / IP ' : ' EDA 设计软件 '}来设计芯片 —— 没有它，芯片根本画不出来。`,
				en: `${tn} designs its chips with ${fn}'s ${a === 'ARM' ? 'CPU IP / architecture license' : 'EDA software'} — without it the chip can't even be drawn.`
			};
		if (sk === 'fab' && !mem)
			return {
				zh: `${tn} 是 fabless（只设计、不建厂），把版图交给 ${fn} 代工制造。先进制程产能是 AI 芯片最硬的瓶颈。`,
				en: `${tn} is fabless — it hands the layout to ${fn} to manufacture. Leading-edge capacity is the single hardest bottleneck for AI silicon.`
			};
		if (mem)
			return {
				zh: `${fn} 向 ${tn} 供应 HBM 高带宽显存，直接堆叠封装进 AI GPU —— HBM 供给是当前最紧的环节之一。`,
				en: `${fn} supplies HBM to ${tn}, stacked straight onto the AI GPU package — HBM is one of the tightest links in the whole chain right now.`
			};
		if (sk === 'design' && tk === 'osat')
			return {
				zh: `${fn} 的裸片送到 ${tn} 做先进封装与测试（如 CoWoS）—— 把 GPU 与 HBM 集成成一颗。封装产能直接卡住出货。`,
				en: `${fn}'s die go to ${tn} for advanced packaging & test (e.g. CoWoS) — fusing the GPU with its HBM. Packaging capacity directly gates shipments.`
			};
		if (sk === 'design' && tk === 'interconnect')
			return {
				zh: `${tn} 提供把成千上万张 ${fn} GPU 连成一个集群的网络 / 互联 —— AI 训练的「胶水」，越大的集群越依赖它。`,
				en: `${tn} provides the fabric that wires thousands of ${fn} GPUs into one cluster — the “glue” of AI training; bigger clusters lean on it harder.`
			};
		if (sk === 'design' && tk === 'systems')
			return {
				zh: `${tn} 用 ${fn} 的芯片组装 AI 服务器，机架级整机交付给云厂商。`,
				en: `${tn} builds AI servers around ${fn}'s chips and ships rack-scale systems to the clouds.`
			};
		if (sk === 'design' && tk === 'demand')
			return {
				zh: `${tn} 直接向 ${fn} 下大额 GPU 订单 —— 云厂商资本开支正是 ${fn} 收入的最大来源，这条边就是「钱」。`,
				en: `${tn} places large GPU orders directly with ${fn} — hyperscaler capex is ${fn}'s single biggest revenue source. This edge is the money.`
			};
		if (sk === 'osat')
			return {
				zh: `${tn} 把 ${fn} 封装测试好的芯片装进服务器系统。`,
				en: `${tn} drops ${fn}-packaged, tested chips into its server systems.`
			};
		if (sk === 'interconnect')
			return {
				zh: `${fn} 的互联 / 网络设备进入 ${tn} 的 AI 系统，决定集群带宽。`,
				en: `${fn}'s interconnect goes into ${tn}'s AI systems, setting the cluster's bandwidth.`
			};
		if (sk === 'systems')
			return {
				zh: `${tn} 采购 ${fn} 的 AI 服务器来扩建数据中心。`,
				en: `${tn} buys ${fn}'s AI servers to build out its data centers.`
			};
		return { zh: `${fn} → ${tn}：供给关系。`, en: `${fn} → ${tn}: a supply link.` };
	}

	function pct(v: number | null | undefined, dgt = 1): string {
		if (v == null) return '—';
		return (v > 0 ? '+' : '') + v.toFixed(dgt) + '%';
	}
	function cap(v: number | null | undefined): string {
		if (v == null) return '—';
		if (v >= 1e12) return (v / 1e12).toFixed(2) + 'T';
		if (v >= 1e9) return Math.round(v / 1e9) + 'B';
		return Math.round(v / 1e6) + 'M';
	}
	function stroke(v: number | null | undefined): string {
		if (v == null) return 'var(--border)';
		return v > 0 ? 'var(--profit)' : 'var(--loss)';
	}
	function tone(v: number | null | undefined): string {
		if (v == null) return 'text-muted-foreground';
		return v > 0 ? 'text-[var(--profit)]' : v < 0 ? 'text-[var(--loss)]' : 'text-muted-foreground';
	}

	const updated = $derived(
		bySym.get('NVDA')?.updated_at
			? new Date(bySym.get('NVDA')!.updated_at).toLocaleDateString()
			: ''
	);

	// alpha buckets
	const leaders = $derived(
		[...tradeable]
			.filter((t) => (t.mom_score ?? -9) > 0.6)
			.sort((a, b) => (b.alpha_score ?? -9) - (a.alpha_score ?? -9))
			.slice(0, 5)
	);
	const laggards = $derived(
		[...tradeable]
			.filter((t) => (t.mom_score ?? 9) < -0.4)
			.sort((a, b) => (a.mom_score ?? 9) - (b.mom_score ?? 9))
			.slice(0, 5)
	);
	const diversifiers = $derived(
		[...tradeable]
			.filter((t) => t.corr_nvda != null && t.corr_nvda < 0.4)
			.sort((a, b) => (a.corr_nvda ?? 9) - (b.corr_nvda ?? 9))
			.slice(0, 5)
	);
	const catchup = $derived(
		[...tradeable]
			.filter((t) => (t.corr_nvda ?? 0) >= 0.5 && (t.rs_vs_nvda ?? 0) < 0)
			.sort((a, b) => (a.rs_vs_nvda ?? 0) - (b.rs_vs_nvda ?? 0))
			.slice(0, 5)
	);
</script>

<svelte:head
	><title>{tr('半导体供应链图谱 · NVDA', 'Semiconductor supply-chain graph · NVDA')}</title
	></svelte:head
>

<main class="mx-auto w-full max-w-[1400px] px-4 py-10 sm:px-6">
	<div class="mb-6">
		<div class="bdv-eyebrow mb-2 text-[var(--gold-500)]">
			BearDawnVerse · {tr('半导体', 'Semiconductors')}
		</div>
		<h1 class="bdv-display text-[38px] leading-[1.05] font-bold tracking-[-0.02em]">
			{tr('半导体供应链图谱', 'The Semiconductor Supply-Chain Graph')}
		</h1>
		<p class="mt-3 max-w-3xl text-[14px] text-muted-foreground">
			{tr(
				'AI 算力是一张网络，不是一棵树。从上到下是价值流：① 原材料 → 设备 → EDA/IP → 代工/内存 → 封测 → 芯片设计 → 互联 → 系统 → ⑨ 云厂商需求。连线表示「谁供给谁」，节点大小是市值，边框颜色是近 3 月涨跌。NVDA 是中枢之一，不是根。真实日线数据。',
				'AI compute is a network, not a tree. Top→bottom is the value flow: ① materials → equipment → EDA/IP → foundry/memory → OSAT → chip designers → interconnect → systems → ⑨ hyperscaler demand. Edges show who supplies whom, node size is market cap, border color is 3-month performance. NVDA is a hub, not a root. Real daily data.'
			)}
		</p>
		{#if updated}<p class="mt-1 text-xs text-muted-foreground">
				{tr('更新于', 'Updated')}
				{updated}
			</p>{/if}
	</div>

	<!-- Technology-trend lens -->
	{#if allTrends.length}
		<div class="mb-4 flex flex-wrap items-center gap-1.5">
			<span class="mr-1 text-xs text-muted-foreground">{tr('技术趋势透镜', 'Trend lens')}</span>
			{#each allTrends as [tag, n] (tag)}
				<button
					type="button"
					onclick={() => (selectedTrend = selectedTrend === tag ? null : tag)}
					class="rounded-full border px-2 py-0.5 text-[11px] transition-colors {selectedTrend ===
					tag
						? 'border-[var(--gold-500)] bg-[color-mix(in_oklab,var(--gold-500)_18%,transparent)] text-[var(--gold-500)]'
						: 'border-border text-muted-foreground hover:text-foreground'}"
				>
					{tag} <span class="opacity-60">{n}</span>
				</button>
			{/each}
			{#if selectedTrend}
				<button
					type="button"
					onclick={() => (selectedTrend = null)}
					class="ml-1 text-[11px] text-muted-foreground hover:text-foreground"
					>{tr('清除 ✕', 'clear ✕')}</button
				>
			{/if}
		</div>
	{/if}

	<!-- Supply-chain network graph -->
	<section class="relative overflow-x-auto rounded-xl border border-border bg-card p-2 sm:p-4">
		<!-- relationship info card (shows on edge hover / tap) -->
		{#if activeEdge && activeInfo}
			{@const f = bySym.get(activeEdge.from)}
			{@const t = bySym.get(activeEdge.to)}
			<div
				class="pointer-events-auto absolute top-3 right-3 z-10 max-w-[340px] rounded-lg border border-[color-mix(in_oklab,var(--gold-500)_45%,transparent)] bg-card/95 p-3 text-sm shadow-xl backdrop-blur"
			>
				<div class="flex items-center gap-2 font-semibold">
					<span>{f?.name ?? activeEdge.from}</span>
					<span class="text-[var(--gold-500)]">→</span>
					<span>{t?.name ?? activeEdge.to}</span>
				</div>
				<div class="mt-0.5 mb-1.5 text-xs text-muted-foreground">
					{f?.symbol} <span class="text-[var(--gold-500)]">{cap(f?.market_cap)}</span>
					{tr('供给', 'supplies')}
					{t?.symbol} <span class="text-[var(--gold-500)]">{cap(t?.market_cap)}</span>
				</div>
				<div class="text-[13px] leading-relaxed">{tr(activeInfo.zh, activeInfo.en)}</div>
				{#if pin >= 0}
					<button
						onclick={() => (pin = -1)}
						class="mt-2 text-xs text-muted-foreground hover:text-foreground"
						>{tr('关闭 ✕', 'close ✕')}</button
					>
				{/if}
			</div>
		{/if}

		<svg
			viewBox="0 0 {W} {H}"
			style="min-width:600px;width:100%;height:auto"
			role="img"
			aria-label={tr('半导体供应链网络图', 'Semiconductor supply-chain network graph')}
		>
			<!-- stage band headers (top → bottom flow) -->
			{#each LAYERS as layer, li (li)}
				<line
					x1="40"
					y1={ROWY[li] + 22}
					x2={W - 30}
					y2={ROWY[li] + 22}
					stroke="var(--border)"
					stroke-dasharray="2 6"
					opacity="0.4"
				/>
				<text
					x="44"
					y={ROWY[li] + 17}
					text-anchor="start"
					class="fill-[var(--muted-foreground)]"
					style="font-size:13px;font-weight:600"
				>
					<tspan class="fill-[var(--dawn-500)]">{li + 1}</tspan>
					{tr(layer.title[0], layer.title[1])}
				</text>
			{/each}
			<!-- edges (visible) -->
			{#each edges as e, _i (_i)}
				{@const on = active === e.i}
				{@const dim = active >= 0 && !on}
				<path
					d={e.path}
					fill="none"
					stroke={on ? 'var(--gold-500)' : e.hub ? 'var(--dawn-500)' : 'var(--muted-foreground)'}
					stroke-width={on ? 2.8 : e.hub ? 1.4 : 0.8}
					opacity={dim ? 0.05 : on ? 0.98 : e.hub ? 0.5 : 0.22}
					style="transition:opacity .12s,stroke-width .12s"
				/>
			{/each}
			<!-- edge hit areas (wide + invisible, sit above visible edges but below nodes) -->
			{#each edges as e, _i (_i)}
				<path
					d={e.path}
					fill="none"
					stroke="transparent"
					stroke-width="16"
					style="cursor:pointer;pointer-events:stroke"
					role="button"
					tabindex="-1"
					aria-label="{e.from} → {e.to}"
					onmouseenter={() => (hover = e.i)}
					onmouseleave={() => (hover = -1)}
					onclick={() => (pin = pin === e.i ? -1 : e.i)}
				/>
			{/each}
			<!-- nodes -->
			{#each [...nodes.values()] as n, _i (_i)}
				{@const isNvda = n.t.symbol === 'NVDA'}
				{@const lit = activeNodes?.has(n.t.symbol)}
				{@const faded = (activeNodes && !lit) || trendDimmed(n.t.symbol)}
				<g opacity={faded ? 0.12 : 1} style="transition:opacity .12s">
					<title
						>{n.t.name} · {cap(n.t.market_cap)} · {pct(n.t.ret_3m)} 3M · ρNVDA {n.t.corr_nvda ??
							'—'}</title
					>
					<circle
						cx={n.x}
						cy={n.y}
						r={n.r}
						fill="color-mix(in oklab, {stroke(n.t.ret_3m)} 14%, var(--card))"
						stroke={lit ? 'var(--gold-500)' : isNvda ? 'var(--gold-500)' : stroke(n.t.ret_3m)}
						stroke-width={lit ? 3.2 : isNvda ? 2.5 : 1.5}
					/>
					<text
						x={n.x}
						y={n.y + 1}
						text-anchor="middle"
						class="fill-[var(--foreground)]"
						style="font-size:{Math.max(9, n.r * 0.42)}px;font-weight:700">{n.t.symbol}</text
					>
					<text
						x={n.x}
						y={n.y + n.r + 13}
						text-anchor="middle"
						class="fill-[var(--gold-500)]"
						style="font-size:10px;font-weight:600">{cap(n.t.market_cap)}</text
					>
					<text
						x={n.x}
						y={n.y + n.r + 25}
						text-anchor="middle"
						style="font-size:10px;fill:{n.t.ret_3m != null && n.t.ret_3m >= 0
							? 'var(--profit)'
							: 'var(--loss)'}">{pct(n.t.ret_3m, 0)}</text
					>
				</g>
			{/each}
		</svg>
	</section>
	<p class="mt-3 text-xs text-muted-foreground">
		{tr(
			'💡 悬停（或点击）任意连线，查看这条上下游关系的详细解释，并高亮这笔「订单」与两端公司。',
			'💡 Hover (or tap) any edge to see what that upstream→downstream relationship is, and highlight the link + the two companies.'
		)}
		{tr(
			'节点大小 = 市值，边框/数字颜色 = 近 3 月涨跌，金边 = NVDA。',
			'Node size = market cap; border/number color = 3M performance; gold ring = NVDA.'
		)}
	</p>

	<!-- System-level value-chain bottleneck matrix -->
	{#if segments.length}
		<section class="mt-12">
			<h2 class="mb-1 text-xl font-bold">
				{tr('价值链瓶颈矩阵', 'Value-chain bottleneck matrix')}
			</h2>
			<p class="mb-5 max-w-3xl text-xs text-muted-foreground">
				{tr(
					'上面的图谱讲「芯片」；这张矩阵把它扩展成「能不能交付整台 AI 服务器」—— 先进封装、IC 载板、PCB、MLCC、供电、液冷、光网络、电力并网都可能成为排产瓶颈。打分 1–5：瓶颈强度 / 定价权 / 替代风险。源自内部研报。',
					'The graph above is the chip story; this matrix extends it to "can the whole AI server ship" — advanced packaging, IC substrate, PCB, MLCC, power delivery, liquid cooling, optics and the grid can all gate output. Scores 1–5: bottleneck strength / pricing power / substitution risk. From internal research.'
				)}
			</p>
			<div class="grid gap-3 md:grid-cols-2">
				{#each segments as seg (seg.id)}
					<div
						class="rounded-xl border border-border bg-card p-4"
						style="border-left:3px solid color-mix(in oklab, {heat(
							seg.bottleneck
						)} 70%, transparent)"
					>
						<div class="flex items-start justify-between gap-3">
							<div class="leading-tight font-semibold">
								{lang === 'zh' ? seg.segment_zh : seg.segment}
							</div>
							<div class="flex shrink-0 flex-col gap-1 text-[10px]">
								{@render meter(tr('瓶颈', 'Bottleneck'), seg.bottleneck)}
								{@render meter(tr('定价权', 'Pricing'), seg.pricing_power)}
								{@render meter(tr('替代险', 'Sub-risk'), seg.sub_risk)}
							</div>
						</div>
						{#if seg.status_2026}
							<div
								class="mt-2.5 rounded-md border border-[color-mix(in_oklab,var(--gold-500)_25%,transparent)] bg-[color-mix(in_oklab,var(--gold-500)_7%,transparent)] p-2"
							>
								<div class="flex items-start gap-1.5">
									<span
										class="shrink-0 rounded bg-[var(--gold-500)] px-1 py-px text-[9px] font-bold text-[#0C0B1A]"
										>2026</span
									>
									<p class="text-[11px] leading-relaxed text-foreground/85">{seg.status_2026}</p>
								</div>
								{#if seg.source_url}
									<a
										href={seg.source_url}
										target="_blank"
										rel="noopener"
										class="mt-1 inline-block text-[10px] text-muted-foreground hover:text-[var(--gold-500)]"
										>{tr('来源', 'source')} · {seg.source_url
											.replace(/^https?:\/\/(www\.)?/, '')
											.split('/')[0]} ↗</a
									>
								{/if}
							</div>
						{/if}
						{#if lang === 'zh'}
							<p class="mt-2 text-xs leading-relaxed text-muted-foreground">{seg.note_zh}</p>
							<div class="mt-1.5 text-[11px] text-muted-foreground">
								<span class="text-foreground/70">跟踪</span> · {seg.track_metric}
							</div>
						{/if}
						<div class="mt-2.5 flex flex-wrap items-center gap-1.5">
							{#each seg.tickers as tk, _i (_i)}
								{@const t = bySym.get(tk)}
								<span
									class="rounded bg-secondary px-1.5 py-0.5 font-mono text-[11px] {t
										? 'text-foreground'
										: 'text-muted-foreground'}"
									title={t ? t.name : tr('非美股 / 未在股票宇宙', 'non-US / not in stock universe')}
									>{tk}</span
								>
							{/each}
						</div>
						<div class="mt-1.5 flex flex-wrap gap-1">
							{#each seg.trend_tags as tag, _i (_i)}
								<button
									type="button"
									onclick={() => (selectedTrend = selectedTrend === tag ? null : tag)}
									title={tr('用这个趋势透视上方图谱', 'Light up this trend in the graph above')}
									class="rounded-full border px-1.5 py-px text-[10px] transition-colors {selectedTrend ===
									tag
										? 'border-[var(--gold-500)] bg-[color-mix(in_oklab,var(--gold-500)_18%,transparent)] text-[var(--gold-500)]'
										: 'border-[color-mix(in_oklab,var(--gold-500)_30%,transparent)] text-[var(--gold-500)] hover:bg-[color-mix(in_oklab,var(--gold-500)_12%,transparent)]'}"
									>{tag}</button
								>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		</section>
	{/if}

	<!-- Alpha mining -->
	<section class="mt-10">
		<h2 class="mb-1 text-xl font-bold">{tr('潜在 Alpha', 'Potential Alpha')}</h2>
		<p class="mb-5 text-xs text-muted-foreground">
			{tr('从真实指标推导，非投资建议。', 'Derived from the real metrics — not investment advice.')}
		</p>
		<div class="grid gap-4 lg:grid-cols-2">
			{@render bucket(
				tr('动量领跑', 'Momentum leaders'),
				tr('相对强度最高，趋势策略顺风', 'Highest relative strength'),
				leaders,
				'good'
			)}
			{@render bucket(
				tr('落后 / 均值回归', 'Laggards / mean-reversion'),
				tr('动量垫底，只做反转或回避', 'Weakest momentum'),
				laggards,
				'bad'
			)}
			{@render bucket(
				tr('低相关分散', 'Low-correlation diversifiers'),
				tr('与 NVDA 相关性低，降组合 beta', 'Low NVDA correlation'),
				diversifiers,
				'neutral'
			)}
			{@render bucket(
				tr('补涨候选', 'Catch-up candidates'),
				tr('高相关但 3 月落后 —— 潜在补涨', 'Coupled to NVDA but lagging 3M'),
				catchup,
				'warn'
			)}
		</div>
	</section>
</main>

{#snippet meter(label: string, score: number)}
	<div class="flex items-center gap-1">
		<span class="w-10 text-right text-muted-foreground">{label}</span>
		<span class="flex gap-px">
			{#each [1, 2, 3, 4, 5] as n, _i (_i)}
				<span
					class="h-2 w-2 rounded-[1px]"
					style="background:{n <= score
						? heat(score)
						: 'color-mix(in oklab, var(--muted-foreground) 22%, transparent)'}"
				></span>
			{/each}
		</span>
	</div>
{/snippet}

{#snippet bucket(
	title: string,
	sub: string,
	items: SemiTicker[],
	kind: 'good' | 'bad' | 'neutral' | 'warn'
)}
	{@const ring =
		kind === 'good'
			? 'var(--profit)'
			: kind === 'bad'
				? 'var(--loss)'
				: kind === 'warn'
					? 'var(--warn)'
					: 'var(--dawn-500)'}
	<div
		class="rounded-xl border border-border bg-card p-4"
		style="border-top:2px solid color-mix(in oklab, {ring} 55%, transparent)"
	>
		<div class="font-semibold">{title}</div>
		<div class="mb-3 text-xs text-muted-foreground">{sub}</div>
		{#if items.length === 0}
			<div class="text-xs text-muted-foreground">
				{tr('当前无符合标的', 'No names match right now')}
			</div>
		{:else}
			<ul class="flex flex-col gap-2">
				{#each items as m, _i (_i)}
					<li class="flex items-start gap-3 text-sm">
						<span class="w-14 shrink-0 font-semibold">{m.symbol}</span>
						<span class="w-12 shrink-0 text-xs text-[var(--gold-500)] tabular-nums"
							>{cap(m.market_cap)}</span
						>
						<span class="w-14 shrink-0 text-xs tabular-nums {tone(m.ret_3m)}"
							>{pct(m.ret_3m, 0)}</span
						>
						<span class="text-xs text-muted-foreground">{m.alpha_note}</span>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
{/snippet}
