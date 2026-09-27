<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/stores';
	import { user } from '$lib/auth';
	import { type Lang } from '$lib/i18n';
	import {
		submitBacktest,
		myJobs,
		jobResult,
		type BacktestJob,
		type BacktestResult,
		type QuantLabTable
	} from '$lib/backtests';
	import { track } from '$lib/track';
	import { onDestroy, onMount } from 'svelte';

	type Model =
		'gbm' | 'bsm' | 'markowitz' | 'garch' | 'cointegration' | 'hmm' | 'pca' | 'kelly' | 'copula';

	type ModelMeta = {
		zh: string;
		en: string;
		tech: string;
		desc: readonly [string, string];
	};

	const MODEL_META: Record<Model, ModelMeta> = {
		gbm: {
			zh: 'GBM 路径',
			en: 'GBM paths',
			tech: 'Geometric Brownian Motion',
			desc: [
				'用历史漂移和波动率模拟未来价格分布。',
				'Simulates future price distribution from historical drift and volatility.'
			]
		},
		bsm: {
			zh: 'BSM 期权',
			en: 'BSM options',
			tech: 'Black-Scholes-Merton',
			desc: [
				'用历史或输入波动率给欧式 call/put 定价并算 Greeks。',
				'Prices European calls/puts and Greeks with historical or input volatility.'
			]
		},
		markowitz: {
			zh: '均值-方差',
			en: 'Mean-variance',
			tech: 'Markowitz',
			desc: [
				'在长仓权重约束下搜索最大 Sharpe 和最小波动组合。',
				'Searches long-only max-Sharpe and min-vol portfolios under weight caps.'
			]
		},
		garch: {
			zh: 'GARCH 波动',
			en: 'GARCH volatility',
			tech: 'GARCH(1,1)',
			desc: [
				'估计条件波动率和短期波动预测。',
				'Estimates conditional volatility and near-term volatility forecasts.'
			]
		},
		cointegration: {
			zh: '协整套利',
			en: 'Cointegration',
			tech: 'Engle-Granger pair',
			desc: [
				'估计 hedge ratio、spread z-score 和均值回归半衰期。',
				'Estimates hedge ratio, spread z-score, and mean-reversion half-life.'
			]
		},
		hmm: {
			zh: 'HMM 状态',
			en: 'HMM regimes',
			tech: 'Gaussian HMM',
			desc: [
				'把收益率切成低/高波动 regime，输出当前状态概率。',
				'Splits returns into low/high-vol regimes and current state probabilities.'
			]
		},
		pca: {
			zh: 'PCA 因子',
			en: 'PCA factors',
			tech: 'Principal Components',
			desc: [
				'找出多资产收益率里的共同主因子和资产载荷。',
				'Finds common factors and asset loadings across return series.'
			]
		},
		kelly: {
			zh: 'Kelly 仓位',
			en: 'Kelly sizing',
			tech: 'Half-Kelly',
			desc: [
				'复用现有 Wilson 收缩 Half-Kelly 仓位模型。',
				'Reuses the existing Wilson-shrunk Half-Kelly sizing model.'
			]
		},
		copula: {
			zh: 'Copula 尾部',
			en: 'Copula tails',
			tech: 'Empirical tail dependence',
			desc: [
				'用 rank copula 估计上下尾联动风险。',
				'Estimates lower/upper tail co-movement with rank copulas.'
			]
		}
	};
	const MODEL_ENTRIES = Object.entries(MODEL_META) as [Model, ModelMeta][];

	const lang = $derived<Lang>($page.data.lang ?? 'zh');
	const en = $derived(lang === 'en');
	let model = $state<Model>('markowitz');
	const meta = $derived(MODEL_META[model]);

	let asset = $state('SPY');
	let universe = $state('SPY,QQQ,TLT,GLD,BIL');
	let lookbackDays = $state(756);
	let horizonDays = $state(30);
	let riskFreeRate = $state(0.04);
	let seed = $state(7);
	let paths = $state(1000);
	let strike = $state(0);
	let vol = $state(0);
	let daysToExpiry = $state(30);
	let maxWeight = $state(0.35);
	let samples = $state(8000);
	let states = $state(2);
	let components = $state(3);
	let tailQ = $state(0.05);
	let winRate = $state(0.55);
	let payoffRatio = $state(1.5);
	let nTrades = $state(1000);
	let cap = $state(0.05);

	let busy = $state(false);
	let err = $state('');
	let jobs = $state<BacktestJob[]>([]);
	let results = $state<Record<string, BacktestResult>>({});
	let openId = $state<string | null>(null);

	const needsAsset = $derived(['gbm', 'bsm', 'garch', 'hmm'].includes(model));
	const needsUniverse = $derived(['markowitz', 'pca', 'copula'].includes(model));
	const needsPair = $derived(model === 'cointegration');
	const needsPrices = $derived(model !== 'kelly');

	function tr(zh: string, enText: string): string {
		return en ? enText : zh;
	}

	function modelLabel(m: Model): string {
		const x = MODEL_META[m];
		return en ? x.en : x.zh;
	}

	function cleanUniverse(): string {
		return universe
			.split(',')
			.map((s) => s.trim().toUpperCase())
			.filter(Boolean)
			.join(',');
	}

	function validate(): string | null {
		const sym = /^[A-Z0-9]{1,8}$/;
		if (needsAsset && !sym.test(asset)) return tr('标的代码格式不对。', 'Invalid asset symbol.');
		if (
			(needsUniverse || needsPair) &&
			cleanUniverse()
				.split(',')
				.some((s) => !sym.test(s))
		) {
			return tr('资产列表只能包含逗号分隔的代码。', 'Universe must be comma-separated symbols.');
		}
		if (needsPair && cleanUniverse().split(',').length < 2)
			return tr('协整至少需要两个资产。', 'Cointegration needs two assets.');
		return null;
	}

	function payload(): Record<string, unknown> {
		const base: Record<string, unknown> = {
			model,
			lookback_days: lookbackDays,
			horizon_days: horizonDays,
			seed
		};
		if (model === 'kelly')
			return { model, win_rate: winRate, payoff_ratio: payoffRatio, n_trades: nTrades, cap };
		if (needsAsset) base.asset = asset.toUpperCase();
		if (needsUniverse || needsPair) base.universe = cleanUniverse();
		if (model === 'gbm') base.paths = paths;
		if (model === 'bsm') {
			base.risk_free_rate = riskFreeRate;
			base.days_to_expiry = daysToExpiry;
			if (strike > 0) base.strike = strike;
			if (vol > 0) base.vol = vol;
		}
		if (model === 'markowitz') {
			base.risk_free_rate = riskFreeRate;
			base.max_weight = maxWeight;
			base.samples = samples;
		}
		if (model === 'hmm') base.states = states;
		if (model === 'pca') base.components = components;
		if (model === 'copula') base.tail_q = tailQ;
		return base;
	}

	async function refresh() {
		if (!$user) return;
		try {
			jobs = await myJobs(fetch, 'quant_lab');
			for (const j of jobs) {
				if (j.status === 'done' && !results[j.id]) {
					const r = await jobResult(j.id);
					if (r) results = { ...results, [j.id]: r };
				}
			}
		} catch (e) {
			err = (e as Error).message;
		}
	}

	async function submit() {
		if (!$user?.sub) return;
		const v = validate();
		if (v) {
			err = v;
			return;
		}
		busy = true;
		err = '';
		try {
			await submitBacktest('quant_lab', payload(), $user.sub);
			track('backtest_submit');
			await refresh();
		} catch (e) {
			err = (e as Error).message;
		} finally {
			busy = false;
		}
	}

	function title(j: BacktestJob): string {
		const m = String(j.params.model ?? 'markowitz') as Model;
		const label = MODEL_META[m] ? modelLabel(m) : String(j.params.model ?? 'quant_lab');
		const assets = j.params.assets ?? j.params.universe ?? j.params.asset ?? '';
		return assets ? `${label} · ${assets}` : label;
	}

	function fmt(v: unknown): string {
		if (v == null) return '-';
		if (typeof v === 'number')
			return Number.isInteger(v) ? String(v) : String(Number(v.toFixed(6)));
		return String(v);
	}

	function cols(t: QuantLabTable): string[] {
		const keys: string[] = [];
		for (const r of t.rows ?? []) {
			for (const k of Object.keys(r)) {
				if (!keys.includes(k)) keys.push(k);
			}
		}
		return keys;
	}

	let timer: ReturnType<typeof setInterval>;
	onMount(() => {
		refresh();
		timer = setInterval(refresh, 4000);
	});
	onDestroy(() => clearInterval(timer));
</script>

<svelte:head>
	<title>{en ? 'Quant Lab' : '量化实验室'} · Crypto Quant</title>
	<meta
		name="description"
		content="Run quant model diagnostics: GBM, BSM, Markowitz, GARCH, cointegration, HMM, PCA, Kelly, and Copula."
	/>
</svelte:head>

<main class="mx-auto mt-10 max-w-5xl px-5 pb-16">
	<div class="flex flex-wrap items-end justify-between gap-4">
		<div>
			<h1 class="text-2xl font-semibold tracking-tight">{en ? 'Quant Lab' : '量化实验室'}</h1>
			<p class="mt-2 max-w-2xl text-sm text-muted-foreground">
				{tr(
					'把常用量化模型跑成可审计的诊断结果：分布、权重、状态、尾部联动和仓位。',
					'Run common quant models as auditable diagnostics: distributions, weights, regimes, tail links, and sizing.'
				)}
			</p>
		</div>
		<a href={resolve('/backtest')} class="text-sm font-medium text-primary hover:underline"
			>{tr('交易回测 →', 'Trading backtests →')}</a
		>
	</div>

	<div class="mt-6 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
		<section class="rounded-md border border-border p-4">
			<div class="grid gap-2 sm:grid-cols-3">
				{#each MODEL_ENTRIES as [key, item] (key)}
					<button
						type="button"
						onclick={() => (model = key)}
						class="rounded-md border p-3 text-left transition-colors {model === key
							? 'border-primary bg-primary/5'
							: 'border-border hover:border-primary/40 hover:bg-muted/30'}"
					>
						<div class="text-sm font-medium text-foreground">{en ? item.en : item.zh}</div>
						<div class="mt-0.5 font-mono text-[10px] text-muted-foreground">{item.tech}</div>
					</button>
				{/each}
			</div>

			<div class="mt-4 rounded bg-muted/30 p-3 text-sm">
				<div class="font-medium text-foreground">{en ? meta.en : meta.zh}</div>
				<p class="mt-1 text-xs text-muted-foreground">{en ? meta.desc[1] : meta.desc[0]}</p>
			</div>

			<div class="mt-4 grid gap-4 sm:grid-cols-3">
				{#if needsAsset}
					<label class="text-xs">
						<span class="text-muted-foreground">{tr('标的', 'Asset')}</span>
						<input
							bind:value={asset}
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
							maxlength="8"
						/>
					</label>
				{/if}
				{#if needsUniverse || needsPair}
					<label class="text-xs sm:col-span-2">
						<span class="text-muted-foreground"
							>{needsPair ? tr('配对资产', 'Pair') : tr('资产池', 'Universe')}</span
						>
						<input
							bind:value={universe}
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
						<p class="mt-1 text-[10px] text-muted-foreground">
							{tr('逗号分隔，最多 12 个。', 'Comma-separated, up to 12 symbols.')}
						</p>
					</label>
				{/if}

				{#if needsPrices}
					<label class="text-xs">
						<span class="text-muted-foreground">{tr('回看天数', 'Lookback days')}</span>
						<input
							type="number"
							bind:value={lookbackDays}
							min="252"
							max="4000"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
					</label>
				{/if}
				{#if ['gbm', 'bsm', 'garch'].includes(model)}
					<label class="text-xs">
						<span class="text-muted-foreground">{tr('预测天数', 'Horizon days')}</span>
						<input
							type="number"
							bind:value={horizonDays}
							min="1"
							max="365"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
					</label>
				{/if}
				{#if ['gbm', 'markowitz', 'hmm'].includes(model)}
					<label class="text-xs">
						<span class="text-muted-foreground">Seed</span>
						<input
							type="number"
							bind:value={seed}
							min="0"
							max="1000000"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
					</label>
				{/if}
				{#if model === 'gbm'}
					<label class="text-xs">
						<span class="text-muted-foreground">Paths</span>
						<input
							type="number"
							bind:value={paths}
							min="100"
							max="5000"
							step="100"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
					</label>
				{/if}
				{#if model === 'bsm'}
					<label class="text-xs">
						<span class="text-muted-foreground">Strike</span>
						<input
							type="number"
							bind:value={strike}
							min="0"
							step="0.01"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
						<p class="mt-1 text-[10px] text-muted-foreground">
							{tr('0 = 使用现价', '0 = use spot')}
						</p>
					</label>
					<label class="text-xs">
						<span class="text-muted-foreground">Vol</span>
						<input
							type="number"
							bind:value={vol}
							min="0"
							max="5"
							step="0.01"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
						<p class="mt-1 text-[10px] text-muted-foreground">
							{tr('0 = 使用历史波动率', '0 = use historical volatility')}
						</p>
					</label>
					<label class="text-xs">
						<span class="text-muted-foreground">{tr('到期天数', 'Days to expiry')}</span>
						<input
							type="number"
							bind:value={daysToExpiry}
							min="1"
							max="1095"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
					</label>
					<label class="text-xs">
						<span class="text-muted-foreground">{tr('无风险利率', 'Risk-free rate')}</span>
						<input
							type="number"
							bind:value={riskFreeRate}
							min="-0.05"
							max="0.25"
							step="0.005"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
					</label>
				{/if}
				{#if model === 'markowitz'}
					<label class="text-xs">
						<span class="text-muted-foreground">{tr('无风险利率', 'Risk-free rate')}</span>
						<input
							type="number"
							bind:value={riskFreeRate}
							min="-0.05"
							max="0.25"
							step="0.005"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
					</label>
					<label class="text-xs">
						<span class="text-muted-foreground">{tr('单资产上限', 'Max weight')}</span>
						<input
							type="number"
							bind:value={maxWeight}
							min="0.05"
							max="1"
							step="0.01"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
					</label>
					<label class="text-xs">
						<span class="text-muted-foreground">Samples</span>
						<input
							type="number"
							bind:value={samples}
							min="1000"
							max="50000"
							step="1000"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
					</label>
				{/if}
				{#if model === 'hmm'}
					<label class="text-xs">
						<span class="text-muted-foreground">States</span>
						<select
							bind:value={states}
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						>
							<option value={2}>2</option>
							<option value={3}>3</option>
						</select>
					</label>
				{/if}
				{#if model === 'pca'}
					<label class="text-xs">
						<span class="text-muted-foreground">Components</span>
						<input
							type="number"
							bind:value={components}
							min="1"
							max="6"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
					</label>
				{/if}
				{#if model === 'copula'}
					<label class="text-xs">
						<span class="text-muted-foreground">{tr('尾部分位', 'Tail quantile')}</span>
						<input
							type="number"
							bind:value={tailQ}
							min="0.01"
							max="0.2"
							step="0.01"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
					</label>
				{/if}
				{#if model === 'kelly'}
					<label class="text-xs">
						<span class="text-muted-foreground">{tr('胜率', 'Win rate')}</span>
						<input
							type="number"
							bind:value={winRate}
							min="0"
							max="1"
							step="0.01"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
					</label>
					<label class="text-xs">
						<span class="text-muted-foreground">{tr('盈亏比', 'Payoff ratio')}</span>
						<input
							type="number"
							bind:value={payoffRatio}
							min="0"
							max="20"
							step="0.1"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
					</label>
					<label class="text-xs">
						<span class="text-muted-foreground">{tr('交易样本', 'Trades')}</span>
						<input
							type="number"
							bind:value={nTrades}
							min="0"
							max="100000"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
					</label>
					<label class="text-xs">
						<span class="text-muted-foreground">Cap</span>
						<input
							type="number"
							bind:value={cap}
							min="0"
							max="1"
							step="0.01"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
					</label>
				{/if}
			</div>

			{#if $user}
				<button
					type="button"
					onclick={submit}
					disabled={busy}
					class="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
				>
					{busy ? tr('提交中...', 'Submitting...') : tr('运行模型', 'Run model')}
				</button>
			{:else}
				<a
					href={resolve('/login')}
					class="mt-4 inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
				>
					{tr('登录后运行', 'Sign in to run')}
				</a>
			{/if}
			{#if err}<p class="mt-3 text-xs text-red-600">{err}</p>{/if}
		</section>

		<aside class="rounded-md border border-border p-4">
			<h2 class="text-sm font-medium">{tr('模型清单', 'Model checklist')}</h2>
			<div class="mt-3 space-y-2">
				{#each MODEL_ENTRIES as [key, item] (key)}
					<div class="rounded border border-border/70 p-2">
						<div class="flex items-baseline justify-between gap-2">
							<span class="text-xs font-medium text-foreground">{en ? item.en : item.zh}</span>
							<span class="font-mono text-[10px] text-muted-foreground">{key.toUpperCase()}</span>
						</div>
						<p class="mt-1 text-[11px] text-muted-foreground">{en ? item.desc[1] : item.desc[0]}</p>
					</div>
				{/each}
			</div>
		</aside>
	</div>

	{#if $user}
		<section class="mt-8">
			<h2 class="text-sm font-medium">{tr('我的模型运行', 'My model runs')}</h2>
			{#if jobs.length === 0}
				<p class="mt-2 text-xs text-muted-foreground">
					{tr('还没有运行记录。', 'No model runs yet.')}
				</p>
			{:else}
				<div class="mt-2 divide-y divide-border rounded-md border border-border">
					{#each jobs as j (j.id)}
						{@const r = results[j.id]}
						{@const done = j.status === 'done' && r}
						<div>
							<button
								type="button"
								onclick={() => done && (openId = openId === j.id ? null : j.id)}
								class="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 text-left text-sm {done
									? 'hover:bg-muted/30'
									: ''}"
							>
								<span class="min-w-0 flex-1">
									<span class="block truncate text-xs font-medium text-foreground">{title(j)}</span>
									<span class="block truncate font-mono text-[10px] text-muted-foreground"
										>{JSON.stringify(j.params)}</span
									>
								</span>
								<span
									class="rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground"
									>{j.status}</span
								>
								{#if j.status === 'error'}<span class="text-xs text-red-600">{j.error}</span>{/if}
							</button>

							{#if done && openId === j.id}
								{@const m = r.metrics}
								<div class="border-t border-border bg-muted/20 px-3 py-4">
									<div class="grid gap-2 sm:grid-cols-4">
										{#each m.summary ?? [] as s (s.label)}
											<div>
												<div class="text-[10px] text-muted-foreground">{s.label}</div>
												<div class="font-mono text-sm text-foreground">
													{fmt(s.value)}{s.unit ? ` ${s.unit}` : ''}
												</div>
											</div>
										{/each}
									</div>

									{#each m.tables ?? [] as table (table.name)}
										{@const columns = cols(table)}
										<div class="mt-5">
											<div class="text-xs font-medium text-muted-foreground">{table.name}</div>
											<div class="mt-1 overflow-x-auto rounded border border-border/70">
												<table class="min-w-full text-left text-xs">
													<thead class="bg-muted/40 text-[10px] text-muted-foreground uppercase">
														<tr>
															{#each columns as c (c)}<th class="px-2 py-1 font-medium">{c}</th
																>{/each}
														</tr>
													</thead>
													<tbody class="divide-y divide-border/60">
														{#each table.rows as row, i (i)}
															<tr>
																{#each columns as c (c)}<td class="px-2 py-1 font-mono"
																		>{fmt(row[c])}</td
																	>{/each}
															</tr>
														{/each}
													</tbody>
												</table>
											</div>
										</div>
									{/each}

									{#if m.notes?.length}
										<ul class="mt-4 space-y-1 text-[11px] text-muted-foreground">
											{#each m.notes as note (note)}<li>{note}</li>{/each}
										</ul>
									{/if}
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		</section>
	{/if}
</main>
