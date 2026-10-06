<script lang="ts">
	import type { RunnerFundingEvent } from '$lib/execution';
	let { items, lang }: { items: RunnerFundingEvent[]; lang: string } = $props();
	const money = (value: number) =>
		new Intl.NumberFormat(lang === 'zh' ? 'zh-CN' : 'en-US', {
			minimumFractionDigits: 2,
			maximumFractionDigits: 2,
			signDisplay: 'exceptZero'
		}).format(value) + ' USDT';
	const date = (value: string) => new Date(value).toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US');
	const names = $derived(
		lang === 'zh'
			? { deposit: '入金', withdrawal: '提款', allocation: '预算调拨', carry: '定投结转' }
			: {
					deposit: 'Deposit',
					withdrawal: 'Withdrawal',
					allocation: 'Allocation',
					carry: 'DCA carry'
				}
	);
</script>

<h3 class="mt-6 font-medium">
	{lang === 'zh' ? '资金与预算流水' : 'Funding and allocation history'}
</h3>
<p class="mt-2 text-xs text-muted-foreground">
	{lang === 'zh'
		? '最近 100 条本地确认记录。预算调拨与结转不产生现金进出。确认时间未知时保留为空。'
		: 'Latest 100 locally confirmed records. Allocation changes and carry do not move cash. Unknown confirmation times remain unrecorded.'}
</p>
<div class="mt-3 space-y-3 md:hidden">
	{#each items as item, index (index)}
		<article class="rounded-lg border border-border p-3">
			<p class="font-medium">{names[item.kind]} · {item.month.slice(0, 7)}</p>
			<p class="mt-1 text-xs break-all text-muted-foreground">{item.reference}</p>
			<p class="mt-1 text-xs text-muted-foreground">
				{item.confirmed_at
					? date(item.confirmed_at)
					: lang === 'zh'
						? '确认时间未记录'
						: 'Confirmation time unrecorded'}
			</p>
			<div class="mt-3 grid grid-cols-3 gap-2 text-xs">
				<div>
					<span class="text-muted-foreground">{lang === 'zh' ? '现金变动' : 'Cash'}</span>
					<p class="mt-1 break-all">{money(item.cash_delta_usdt)}</p>
				</div>
				<div>
					<span class="text-muted-foreground">{lang === 'zh' ? '趋势预算' : 'Trend'}</span>
					<p class="mt-1 break-all">{money(item.trend_delta_usdt)}</p>
				</div>
				<div>
					<span class="text-muted-foreground">{lang === 'zh' ? '定投预算' : 'DCA'}</span>
					<p class="mt-1 break-all">{money(item.dca_delta_usdt)}</p>
				</div>
			</div>
		</article>
	{/each}
</div>
<div class="mt-3 hidden overflow-x-auto md:block">
	<table class="w-full text-left text-sm">
		<thead
			><tr
				><th class="py-2 pr-4">{lang === 'zh' ? '确认时间 / 月份' : 'Confirmed / month'}</th><th
					class="pr-4">{lang === 'zh' ? '类型 / 编号' : 'Type / reference'}</th
				><th class="pr-4">{lang === 'zh' ? '现金变动' : 'Cash change'}</th><th class="pr-4"
					>{lang === 'zh' ? '趋势预算' : 'Trend allocation'}</th
				><th>{lang === 'zh' ? '定投预算' : 'DCA allocation'}</th></tr
			></thead
		>
		<tbody
			>{#each items as item, index (index)}<tr class="border-t border-border"
					><td class="py-2 pr-4 whitespace-nowrap"
						>{item.confirmed_at
							? date(item.confirmed_at)
							: lang === 'zh'
								? '确认时间未记录'
								: 'Confirmation time unrecorded'}<span class="block text-xs text-muted-foreground"
							>{item.month.slice(0, 7)}</span
						></td
					><td class="pr-4"
						><span>{names[item.kind]}</span><span
							class="block max-w-48 text-xs break-all text-muted-foreground">{item.reference}</span
						></td
					><td class="pr-4">{money(item.cash_delta_usdt)}</td><td class="pr-4"
						>{money(item.trend_delta_usdt)}</td
					><td>{money(item.dca_delta_usdt)}</td></tr
				>{/each}</tbody
		>
	</table>
</div>
