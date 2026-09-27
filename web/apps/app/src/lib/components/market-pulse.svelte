<script lang="ts">
	// "Semis market pulse" — the news-driven-in-spirit card (timsun.net's thesis box), but every
	// word is derived from real Yahoo closes in quant.semi_universe. No fabricated headlines: a
	// templated read over breadth + tier rotation + weekly movers. Refreshes when semi_analysis.py
	// re-runs. Honest by construction — we only state what the numbers say.
	import { page } from '$app/stores';
	import { type Lang } from '$lib/i18n';

	type Mover = { symbol: string; ret_1w: number | null; ret_1m: number | null };
	type Tier = { tier: string; avg_ret_1m: number | null; members: number };
	type Pulse = {
		total: number;
		up: number;
		leaders: Mover[];
		laggards: Mover[];
		tiers: Tier[];
		nvda_ret_1w: number | null;
		updated_at: string;
	};

	let { pulse }: { pulse: Pulse | null } = $props();

	const lang = $derived<Lang>($page.data.lang ?? 'zh');
	const en = $derived(lang === 'en');

	const TIER_LABEL: Record<string, [zh: string, en: string]> = {
		core: ['核心 (NVDA)', 'core (NVDA)'],
		upstream: ['上游', 'upstream'],
		peer: ['同业', 'peer'],
		downstream: ['下游', 'downstream']
	};
	const tierName = (t: string) => (TIER_LABEL[t] ? (en ? TIER_LABEL[t][1] : TIER_LABEL[t][0]) : t);
	const sign = (v: number | null | undefined, d = 1) =>
		v === null || v === undefined ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(d)}%`;

	// Breadth tone drives the headline verb.
	const tone = $derived.by(() => {
		if (!pulse) return 'mixed';
		const r = pulse.up / pulse.total;
		return r < 0.4 ? 'weak' : r > 0.6 ? 'broad' : 'mixed';
	});

	const thesis = $derived.by(() => {
		if (!pulse) return '';
		const lead = pulse.tiers[0];
		const lag = pulse.tiers[pulse.tiers.length - 1];
		const topMover = pulse.leaders[0];
		const verb = en
			? { weak: 'pulled back', broad: 'broadly higher', mixed: 'mixed' }[tone]
			: { weak: '回调承压', broad: '普涨', mixed: '涨跌分化' }[tone];
		if (en) {
			return (
				`Semis ${verb} this week — ${pulse.up}/${pulse.total} names up, ` +
				`NVDA ${sign(pulse.nvda_ret_1w)}. Momentum leads in ${tierName(lead?.tier ?? '')} ` +
				`(${sign(lead?.avg_ret_1m)} 1m) over ${tierName(lag?.tier ?? '')}; ` +
				`${topMover?.symbol ?? ''} tops the tape at ${sign(topMover?.ret_1w)}.`
			);
		}
		return (
			`本周半导体${verb} —— ${pulse.total} 只中 ${pulse.up} 只上涨，` +
			`NVDA ${sign(pulse.nvda_ret_1w)}。动能领先在${tierName(lead?.tier ?? '')}` +
			`(月 ${sign(lead?.avg_ret_1m)})，${tierName(lag?.tier ?? '')}落后；` +
			`${topMover?.symbol ?? ''} 领涨 ${sign(topMover?.ret_1w)}。`
		);
	});

	const maxTierAbs = $derived(
		pulse ? Math.max(1, ...pulse.tiers.map((t) => Math.abs(t.avg_ret_1m ?? 0))) : 1
	);
	const asOf = $derived(pulse ? pulse.updated_at.slice(0, 10) : '');
</script>

{#if pulse}
	<section class="mb-8 overflow-hidden rounded-2xl border bg-card p-5 sm:p-6">
		<div class="flex flex-wrap items-baseline justify-between gap-2">
			<div class="flex items-center gap-2">
				<h2 class="text-sm font-semibold tracking-wide text-muted-foreground uppercase">
					{en ? 'Semis market pulse' : '半导体市场快照'}
				</h2>
				<span class="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
					{en ? 'auto · real closes' : '自动 · 真实收盘'}
				</span>
			</div>
			<a href="/semis" class="text-xs text-primary hover:underline"
				>{en ? 'Full universe →' : '完整产业链 →'}</a
			>
		</div>

		<!-- Data-derived thesis (timsun-style read, honest). -->
		<p class="mt-3 text-base leading-relaxed text-foreground">{thesis}</p>

		<div class="mt-5 grid gap-5 lg:grid-cols-3">
			<!-- Breadth -->
			<div>
				<div class="text-xs font-medium text-muted-foreground">
					{en ? 'Breadth (1w)' : '广度 (周)'}
				</div>
				<div class="mt-1.5 flex items-baseline gap-2">
					<span class="text-2xl font-bold tabular-nums">{pulse.up}/{pulse.total}</span>
					<span class="text-xs text-muted-foreground">{en ? 'up' : '上涨'}</span>
				</div>
				<div class="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted">
					<div
						class="h-full rounded-full {tone === 'weak'
							? 'bg-red-500'
							: tone === 'broad'
								? 'bg-emerald-500'
								: 'bg-amber-500'}"
						style="width: {(pulse.up / pulse.total) * 100}%"
					></div>
				</div>
			</div>

			<!-- Tier rotation -->
			<div>
				<div class="text-xs font-medium text-muted-foreground">
					{en ? 'Tier rotation (1m)' : '梯队轮动 (月)'}
				</div>
				<div class="mt-2 space-y-1.5">
					{#each pulse.tiers as t, _i (_i)}
						<div class="flex items-center gap-2 text-xs">
							<span class="w-20 shrink-0 text-muted-foreground">{tierName(t.tier)}</span>
							<div class="relative h-3 flex-1 rounded bg-muted/50">
								<div
									class="absolute inset-y-0 rounded {(t.avg_ret_1m ?? 0) >= 0
										? 'bg-emerald-500/70'
										: 'bg-red-500/70'}"
									style="width: {(Math.abs(t.avg_ret_1m ?? 0) / maxTierAbs) * 100}%"
								></div>
							</div>
							<span class="w-14 shrink-0 text-right font-mono tabular-nums"
								>{sign(t.avg_ret_1m)}</span
							>
						</div>
					{/each}
				</div>
			</div>

			<!-- Movers -->
			<div>
				<div class="text-xs font-medium text-muted-foreground">
					{en ? 'Weekly movers' : '本周异动'}
				</div>
				<div class="mt-2 space-y-2">
					<div class="flex flex-wrap gap-1.5">
						{#each pulse.leaders as m, _i (_i)}
							<span class="rounded bg-emerald-500/10 px-2 py-1 text-xs text-emerald-500">
								{m.symbol}
								{sign(m.ret_1w)}
							</span>
						{/each}
					</div>
					<div class="flex flex-wrap gap-1.5">
						{#each pulse.laggards as m, _i (_i)}
							<span class="rounded bg-red-500/10 px-2 py-1 text-xs text-red-500">
								{m.symbol}
								{sign(m.ret_1w)}
							</span>
						{/each}
					</div>
				</div>
			</div>
		</div>

		<p class="mt-4 text-xs text-muted-foreground">
			{en
				? `Derived from ${pulse.total} semiconductor-chain names, real Yahoo closes as of ${asOf}. Not investment advice.`
				: `基于 ${pulse.total} 只半导体产业链个股、截至 ${asOf} 的真实雅虎收盘价计算。非投资建议。`}
		</p>
	</section>
{/if}
