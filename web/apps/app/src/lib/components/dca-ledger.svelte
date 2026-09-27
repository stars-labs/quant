<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { session } from '$lib/auth';
	import { loadPrefs } from '$lib/userPrefs';
	import { COIN_SYMBOLS, type CoinSymbol } from '$lib/dcaSim';
	import {
		myExecutions,
		logExecution,
		deleteExecution,
		fetchSpotPrices,
		type DcaBreakdown,
		type DcaExecution
	} from '$lib/dcaLedger';
	import { fmtUSD, fmtPct, fmtTime } from '$lib/utils';
	import type { Lang } from '$lib/i18n';

	const lang = $derived<Lang>($page.data.lang ?? 'zh');

	let loaded = $state(false);
	let errMsg = $state('');
	let execs = $state<DcaExecution[]>([]);
	let spot = $state<Partial<Record<CoinSymbol, number>>>({});

	// Log form — per-coin USDT amounts are the source of truth; the total
	// input re-splits them by the saved plan's mix (default 100% BTC).
	let totalInput = $state(500);
	let amounts = $state<Record<CoinSymbol, number>>({ BTC: 500, ETH: 0, BNB: 0, SOL: 0 });
	let planMix: Partial<Record<CoinSymbol, number>> = { BTC: 100 };
	let logStatus = $state<'idle' | 'saving' | 'ok' | 'err'>('idle');
	let logMsg = $state('');

	// Number() guard: amounts can hold NaN when an input is cleared.
	const formTotal = $derived(COIN_SYMBOLS.reduce((s, c) => s + (Number(amounts[c]) || 0), 0));

	function splitByMix(total: number) {
		const t = Number(total) || 0;
		const mixSum = COIN_SYMBOLS.reduce((s, c) => s + (Number(planMix[c]) || 0), 0);
		const next: Record<CoinSymbol, number> = { BTC: 0, ETH: 0, BNB: 0, SOL: 0 };
		if (mixSum > 0) {
			for (const c of COIN_SYMBOLS) next[c] = Math.round(t * ((Number(planMix[c]) || 0) / mixSum));
		} else {
			next.BTC = Math.round(t);
		}
		amounts = next;
	}

	onMount(async () => {
		if (!$session) {
			loaded = true;
			return;
		}
		try {
			// Prefs only prefill the form — a missing row must not block the ledger.
			const [prefs, rows] = await Promise.all([
				loadPrefs(fetch).catch(() => null),
				myExecutions(fetch)
			]);
			if (prefs?.dca_plan) {
				if (prefs.dca_plan.mix) planMix = prefs.dca_plan.mix;
				const m = Number(prefs.dca_plan.monthly_usdt);
				if (m > 0) totalInput = m;
			}
			splitByMix(totalInput);
			execs = rows;
			spot = await fetchSpotPrices(COIN_SYMBOLS);
		} catch (e) {
			errMsg = (e as Error).message;
		} finally {
			loaded = true;
		}
	});

	async function logNow() {
		if (!$session) return;
		logStatus = 'saving';
		logMsg = '';
		try {
			const coins = COIN_SYMBOLS.filter((c) => (Number(amounts[c]) || 0) > 0);
			if (coins.length === 0)
				throw new Error(lang === 'en' ? 'enter an amount first' : '先填一个金额');
			const prices = await fetchSpotPrices(coins);
			const breakdown: DcaBreakdown = {};
			for (const c of coins) {
				const px = prices[c];
				if (!px)
					throw new Error(
						lang === 'en' ? `no live price for ${c}, retry later` : `拿不到 ${c} 现价,稍后再试`
					);
				breakdown[c] = { amount: Number(amounts[c]) || 0, price: px };
			}
			const row = await logExecution({
				user_id: $session.user.sub!,
				total_usdt: formTotal,
				breakdown
			});
			execs = [row, ...execs];
			spot = { ...spot, ...prices };
			logStatus = 'ok';
			setTimeout(() => (logStatus = 'idle'), 2500);
		} catch (e) {
			logStatus = 'err';
			logMsg = (e as Error).message;
		}
	}

	async function remove(id: number) {
		if (!confirm(lang === 'en' ? 'Delete this entry?' : '删除这条记录?')) return;
		try {
			await deleteExecution(id);
			execs = execs.filter((e) => e.id !== id);
		} catch (e) {
			errMsg = (e as Error).message;
		}
	}

	// ===== The money stats — computed client-side from executions + spot =====

	interface CoinStat {
		coin: CoinSymbol;
		invested: number;
		units: number;
		avgCost: number;
		spot: number | null;
		diffPct: number | null;
	}

	const stats = $derived.by(() => {
		if (execs.length === 0) return null;
		const invested: Record<CoinSymbol, number> = { BTC: 0, ETH: 0, BNB: 0, SOL: 0 };
		const units: Record<CoinSymbol, number> = { BTC: 0, ETH: 0, BNB: 0, SOL: 0 };
		const firstPx: Partial<Record<CoinSymbol, number>> = {};
		const lastPx: Partial<Record<CoinSymbol, number>> = {};
		// execs are newest-first; walk oldest-first so first/last prices land right.
		const chrono = [...execs].reverse();
		for (const e of chrono) {
			for (const c of COIN_SYMBOLS) {
				const b = e.breakdown?.[c];
				if (!b) continue;
				// Number() guard: breakdown comes from a jsonb column.
				const amt = Number(b.amount) || 0;
				const px = Number(b.price) || 0;
				if (amt <= 0 || px <= 0) continue;
				invested[c] += amt;
				units[c] += amt / px;
				if (firstPx[c] == null) firstPx[c] = px;
				lastPx[c] = px;
			}
		}
		const totalInvested = chrono.reduce((s, e) => s + (Number(e.total_usdt) || 0), 0);
		const coins: CoinStat[] = [];
		let currentValue = 0;
		let lumpValue = 0;
		for (const c of COIN_SYMBOLS) {
			if (units[c] <= 0) continue;
			const avgCost = invested[c] / units[c];
			const px = spot[c] ?? lastPx[c] ?? null;
			coins.push({
				coin: c,
				invested: invested[c],
				units: units[c],
				avgCost,
				spot: px,
				diffPct: px != null ? ((px - avgCost) / avgCost) * 100 : null
			});
			if (px != null) {
				currentValue += units[c] * px;
				// Lump-sum counterfactual: the same per-coin spend, all bought at
				// the price of the first log that included that coin.
				const f0 = firstPx[c];
				if (f0) lumpValue += (invested[c] / f0) * px;
			}
		}
		const pnl = currentValue - totalInvested;
		// Streak: consecutive calendar months with ≥1 log, ending at the
		// current or previous month (UTC, matching the ts strings). Walk
		// month indices as plain ints — no mutable Date in a runes component.
		const monthSet = new Set(execs.map((e) => e.ts.slice(0, 7)));
		const key = (y: number, m: number) => `${y}-${String(m + 1).padStart(2, '0')}`;
		const now = new Date();
		let y = now.getUTCFullYear();
		let m = now.getUTCMonth();
		const prev = () => {
			m--;
			if (m < 0) {
				m = 11;
				y--;
			}
		};
		if (!monthSet.has(key(y, m))) prev();
		let streak = 0;
		while (monthSet.has(key(y, m))) {
			streak++;
			prev();
		}
		return {
			totalInvested,
			currentValue,
			pnl,
			pnlPct: totalInvested > 0 ? (pnl / totalInvested) * 100 : 0,
			coins,
			lumpValue,
			lumpDiff: currentValue - lumpValue,
			streak,
			firstDate: chrono[0].ts.slice(0, 10)
		};
	});

	function fmtSignedUSD(n: number): string {
		return `${n >= 0 ? '+' : '−'}$${Math.round(Math.abs(n)).toLocaleString()}`;
	}

	const coinColor: Record<CoinSymbol, string> = {
		BTC: 'bg-orange-950 text-orange-300 border-orange-800',
		ETH: 'bg-blue-950 text-blue-300 border-blue-800',
		BNB: 'bg-yellow-950 text-yellow-300 border-yellow-800',
		SOL: 'bg-purple-950 text-purple-300 border-purple-800'
	};
</script>

<section
	class="mb-8 rounded-xl border-2 border-primary/40 bg-gradient-to-br from-primary/5 to-transparent p-5"
>
	<h2 class="text-base font-semibold">
		📒 {lang === 'en' ? 'My real DCA ledger' : '我的真实定投账本'}
	</h2>
	<p class="mt-1 text-xs text-muted-foreground">
		{lang === 'en'
			? 'The plan above is a simulation — this records what you actually bought. One tap per buy; the numbers below show whether discipline is paying.'
			: '上面的计划是模拟 —— 这里记你真实买入的每一笔。一键记账,用下面的数字看到坚持有没有回报。'}
	</p>

	{#if !$session}
		<a
			href="/login"
			class="mt-4 inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
		>
			{lang === 'en' ? 'Log in to start your ledger →' : '登录开始记账 →'}
		</a>
	{:else if !loaded}
		<p class="mt-2 text-sm text-muted-foreground">{lang === 'en' ? 'Loading…' : '加载中…'}</p>
	{:else}
		<!-- LOG FORM -->
		<div class="mt-4 rounded-lg border bg-card p-4">
			<div class="flex flex-wrap items-end gap-3">
				<label class="flex flex-col gap-1 text-xs text-muted-foreground">
					{lang === 'en' ? 'This buy (USDT)' : '这次买了 (USDT)'}
					<input
						type="number"
						min="1"
						max="1000000"
						step="10"
						value={totalInput}
						oninput={(e) => {
							totalInput = (e.currentTarget as HTMLInputElement).valueAsNumber || 0;
							splitByMix(totalInput);
						}}
						class="w-32 rounded-md border border-border bg-background px-3 py-2 font-mono text-sm text-foreground"
					/>
				</label>
				{#each COIN_SYMBOLS as c (c)}
					<label class="flex flex-col gap-1 text-xs text-muted-foreground">
						<span
							class="rounded border px-1.5 py-0.5 text-center font-mono text-[10px] {coinColor[c]}"
						>
							{c}
						</span>
						<input
							type="number"
							min="0"
							step="1"
							value={amounts[c]}
							oninput={(e) =>
								(amounts = {
									...amounts,
									[c]: (e.currentTarget as HTMLInputElement).valueAsNumber || 0
								})}
							class="w-24 rounded-md border border-border bg-background px-2 py-2 text-right font-mono text-xs"
						/>
					</label>
				{/each}
				<button
					type="button"
					onclick={logNow}
					disabled={logStatus === 'saving' || formTotal <= 0}
					class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
				>
					{logStatus === 'saving' ? '…' : lang === 'en' ? '✓ I bought — log it' : '✓ 我买了,记一笔'}
				</button>
			</div>
			<p class="mt-2 text-[11px] text-muted-foreground">
				{lang === 'en'
					? `Total $${formTotal} · split prefilled from your saved plan, edit per coin · price snapshot from Binance at log time`
					: `合计 $${formTotal} · 按你保存的计划自动拆分,可手改每个币 · 记账时自动抓 Binance 现价`}
			</p>
			{#if logStatus === 'ok'}
				<p class="mt-2 text-xs text-green-500">
					{lang === 'en'
						? '✓ Logged. Keep going — the stats below do the talking.'
						: '✓ 已记上。坚持住 —— 下面的数字会说话。'}
				</p>
			{:else if logStatus === 'err'}
				<p class="mt-2 text-xs text-red-500">
					{lang === 'en' ? 'Error: ' : '出错:'}{logMsg}
				</p>
			{/if}
		</div>

		<!-- THE MONEY STATS -->
		{#if stats}
			<div class="mt-5 grid gap-3 text-center font-mono sm:grid-cols-2 lg:grid-cols-4">
				<div class="rounded-lg border bg-card p-3">
					<div class="text-[10px] text-muted-foreground uppercase">
						{lang === 'en' ? 'Total invested' : '总投入'}
					</div>
					<div class="mt-1 text-lg font-semibold">{fmtUSD(stats.totalInvested)}</div>
				</div>
				<div class="rounded-lg border bg-card p-3">
					<div class="text-[10px] text-muted-foreground uppercase">
						{lang === 'en' ? 'Current value' : '当前价值'}
					</div>
					<div class="mt-1 text-lg font-semibold">{fmtUSD(stats.currentValue)}</div>
				</div>
				<div class="rounded-lg border bg-card p-3">
					<div class="text-[10px] text-muted-foreground uppercase">
						{lang === 'en' ? 'Unrealized P&L' : '浮动盈亏'}
					</div>
					<div
						class="mt-1 text-lg font-semibold"
						class:text-green-500={stats.pnl > 0}
						class:text-red-500={stats.pnl < 0}
					>
						{fmtSignedUSD(stats.pnl)} ({fmtPct(stats.pnlPct)})
					</div>
				</div>
				<div class="rounded-lg border bg-card p-3">
					<div class="text-[10px] text-muted-foreground uppercase">
						{lang === 'en' ? 'Streak' : '坚持'}
					</div>
					<div class="mt-1 text-lg font-semibold">
						{stats.streak}
						{lang === 'en' ? (stats.streak === 1 ? 'month' : 'months') : '个月'}
						{stats.streak > 0 ? '🔥' : ''}
					</div>
				</div>
			</div>

			<div class="mt-4 overflow-x-auto rounded-lg border bg-card">
				<table class="w-full text-xs">
					<thead class="bg-secondary text-left text-[10px] text-muted-foreground uppercase">
						<tr>
							<th class="px-3 py-2">{lang === 'en' ? 'Coin' : '币'}</th>
							<th class="px-3 text-right">{lang === 'en' ? 'Invested' : '投入'}</th>
							<th class="px-3 text-right">{lang === 'en' ? 'Units' : '持仓数量'}</th>
							<th class="px-3 text-right">{lang === 'en' ? 'Real avg cost' : '真实均价'}</th>
							<th class="px-3 text-right">{lang === 'en' ? 'Now' : '现价'}</th>
							<th class="px-3 text-right">{lang === 'en' ? 'vs avg' : '对比均价'}</th>
						</tr>
					</thead>
					<tbody class="font-mono">
						{#each stats.coins as cs (cs.coin)}
							<tr class="border-t border-border">
								<td class="px-3 py-1.5">
									<span class="rounded border px-1.5 py-0.5 text-[10px] {coinColor[cs.coin]}">
										{cs.coin}
									</span>
								</td>
								<td class="px-3 text-right">{fmtUSD(cs.invested)}</td>
								<td class="px-3 text-right">{cs.units.toFixed(cs.coin === 'BTC' ? 6 : 4)}</td>
								<td class="px-3 text-right">{fmtUSD(cs.avgCost)}</td>
								<td class="px-3 text-right">{cs.spot == null ? '—' : fmtUSD(cs.spot)}</td>
								<td
									class="px-3 text-right"
									class:text-green-500={(cs.diffPct ?? 0) > 0}
									class:text-red-500={(cs.diffPct ?? 0) < 0}
								>
									{cs.diffPct == null ? '—' : fmtPct(cs.diffPct)}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>

			<!-- vs lump sum at first buy — honest in both directions -->
			<div class="mt-3 rounded-lg border bg-card p-4 text-xs">
				<div class="text-[10px] font-semibold text-muted-foreground uppercase">
					{lang === 'en' ? 'vs lump sum at your first buy' : '对比一次性买入'}
				</div>
				<p class="mt-1.5 text-muted-foreground">
					{lang === 'en'
						? `If you had put it all in at each coin's first logged price (starting ${stats.firstDate}), it would be worth ${fmtUSD(stats.lumpValue)} now; your DCA is worth ${fmtUSD(stats.currentValue)}.`
						: `如果按各币种首次记账时的价格一次性买入(始于 ${stats.firstDate}),现在值 ${fmtUSD(stats.lumpValue)};你定投的现在值 ${fmtUSD(stats.currentValue)}。`}
				</p>
				<p
					class="mt-1.5 font-mono font-semibold"
					class:text-green-500={stats.lumpDiff >= 0}
					class:text-yellow-500={stats.lumpDiff < 0}
				>
					{#if stats.lumpDiff >= 0}
						{lang === 'en'
							? `Sticking to DCA ${stats.pnl >= 0 ? 'made you' : 'saved you'} ${fmtSignedUSD(stats.lumpDiff)} vs going all-in ✊`
							: `坚持定投比一把梭哈${stats.pnl >= 0 ? '多赚' : '少亏'} ${fmtSignedUSD(stats.lumpDiff)} ✊`}
					{:else}
						{lang === 'en'
							? `Over this stretch a lump sum would be ahead by $${Math.round(Math.abs(stats.lumpDiff)).toLocaleString()} — but only if you'd gone all-in on day one and held. DCA buys discipline and spread, not a win in every window.`
							: `这段时间一把梭哈会多 $${Math.round(Math.abs(stats.lumpDiff)).toLocaleString()} —— 但前提是第一天就敢全仓并拿住。定投买的是纪律和分散,不是每一段都赢。`}
					{/if}
				</p>
			</div>
		{/if}

		<!-- LEDGER LIST -->
		<div class="mt-5">
			<h3 class="mb-2 text-xs font-semibold text-muted-foreground uppercase">
				{lang === 'en' ? 'Recent entries' : '最近记录'}
			</h3>
			{#if execs.length === 0}
				<p
					class="rounded-lg border border-dashed bg-card p-5 text-center text-xs text-muted-foreground"
				>
					{lang === 'en'
						? 'No entries yet. The value of DCA only shows when you stick with it — start logging this month.'
						: '还没有记录。定投的价值要靠坚持才能看见 —— 从这个月开始记。'}
				</p>
			{:else}
				<ul class="space-y-1.5">
					{#each execs.slice(0, 20) as e (e.id)}
						<li
							class="flex flex-wrap items-center gap-2 rounded-lg border bg-card px-3 py-2 text-xs"
						>
							<span class="w-28 shrink-0 font-mono text-muted-foreground">{fmtTime(e.ts)}</span>
							<span class="font-mono font-semibold">{fmtUSD(e.total_usdt)}</span>
							<span class="flex flex-1 flex-wrap gap-1.5">
								{#each COIN_SYMBOLS as c (c)}
									{@const b = e.breakdown?.[c]}
									{#if b}
										<span class="rounded border px-1.5 py-0.5 font-mono text-[10px] {coinColor[c]}">
											{c} ${(Number(b.amount) || 0).toFixed(0)} @ {fmtUSD(Number(b.price) || 0)}
										</span>
									{/if}
								{/each}
							</span>
							{#if e.note}
								<span class="text-muted-foreground">{e.note}</span>
							{/if}
							<button
								type="button"
								onclick={() => remove(e.id)}
								class="text-muted-foreground transition-colors hover:text-red-500"
								title={lang === 'en' ? 'Delete' : '删除'}
							>
								✕
							</button>
						</li>
					{/each}
				</ul>
				{#if execs.length > 20}
					<p class="mt-1 text-[10px] text-muted-foreground">
						… {execs.length - 20}
						{lang === 'en' ? 'older entries' : '条更早的记录'}
					</p>
				{/if}
			{/if}
		</div>

		{#if errMsg}
			<div class="mt-3 text-xs text-red-500">{lang === 'en' ? 'Error: ' : '出错:'}{errMsg}</div>
		{/if}
	{/if}

	<p class="mt-4 border-t border-border pt-3 text-[11px] text-muted-foreground">
		{lang === 'en'
			? 'Your own ledger, your own responsibility — not investment advice.'
			: '自己记账,自己负责 —— 不构成投资建议。'}
	</p>
</section>
