<script lang="ts">
	// User-defined signal management card — self-contained, drop anywhere.
	// Lists the user's own signals (pause/resume, delete-with-confirm), creates
	// new ones via an inline kind→dynamic-fields form (mirrors the backtest
	// page's dynamic-param pattern), and shows recent fires. Fires push to
	// Telegram via the existing alert-subscribe binding — if the user has
	// signals but no bound Telegram we nudge with <AlertSubscribe /> below.
	import { page } from '$app/stores';
	import { user } from '$lib/auth';
	import { type Lang } from '$lib/i18n';
	import {
		SIGNAL_KINDS,
		CRYPTO_ASSETS,
		EQUITY_ASSETS,
		COMMODITY_ASSETS,
		timeframesFor,
		mySignals,
		createSignal,
		setSignalStatus,
		deleteSignal,
		myFires,
		signalsVersion,
		type SignalKind,
		type UserSignal,
		type SignalFire
	} from '$lib/signals';
	import { getMyLink } from '$lib/alerts';
	import { track } from '$lib/track';
	import AlertSubscribe from './alert-subscribe.svelte';

	const lang = $derived<Lang>($page.data.lang ?? 'zh');
	const en = $derived(lang === 'en');

	// ── Dynamic per-kind form state (mirrors /backtest's strategy form) ──────
	type NumParam = { min: number; max: number; default: number; step?: number };
	type ChoiceParam = { choices: readonly string[]; default: string };
	type AnyParam = NumParam | ChoiceParam;
	const isChoice = (p: AnyParam): p is ChoiceParam => 'choices' in p;

	let kind = $state<SignalKind>('ema_cross');
	const kindCfg = $derived(SIGNAL_KINDS[kind]);

	let asset = $state<string>('BTC');
	let tf = $state<string>('1h');
	let params = $state<Record<string, number | string>>(seedParams('ema_cross'));
	const tfs = $derived(timeframesFor(kind, asset));

	function seedParams(k: SignalKind): Record<string, number | string> {
		const out: Record<string, number | string> = {};
		const ps = SIGNAL_KINDS[k].params as Record<string, AnyParam>;
		for (const [key, p] of Object.entries(ps)) out[key] = p.default;
		return out;
	}

	function onKindChange(k: SignalKind) {
		kind = k;
		params = seedParams(k);
		nameTouched = false;
		err = '';
	}

	// Keep tf valid when the asset flips between crypto (1h/1d) and equity (1d only).
	$effect(() => {
		if (!tfs.includes(tf)) tf = tfs[0];
	});

	// Friendly labels for param keys + enum values.
	const PARAM_LABELS: Record<string, [zh: string, en: string]> = {
		ema_fast: ['快线 EMA', 'EMA fast'],
		ema_slow: ['慢线 EMA', 'EMA slow'],
		direction: ['方向', 'Direction'],
		entry_lb: ['入场回看', 'Entry lookback'],
		exit_lb: ['离场回看', 'Exit lookback'],
		side: ['方向', 'Side'],
		below: ['FNG 低于', 'FNG below']
	};
	function paramLabel(k: string): string {
		const l = PARAM_LABELS[k];
		if (l) return en ? l[1] : l[0];
		return k.replace(/_/g, ' ');
	}
	const CHOICE_LABELS: Record<string, [zh: string, en: string]> = {
		golden: ['金叉', 'golden cross'],
		death: ['死叉', 'death cross'],
		both: ['金叉+死叉', 'both'],
		entry: ['入场突破', 'entry breakout'],
		exit: ['离场跌破', 'exit breakdown']
	};
	function choiceLabel(v: string): string {
		const l = CHOICE_LABELS[v];
		if (l) return en ? l[1] : l[0];
		return v;
	}
	function kindLabel(k: SignalKind): string {
		return en ? SIGNAL_KINDS[k].label[1] : SIGNAL_KINDS[k].label[0];
	}

	// ── Auto-suggested name ('BTC EMA20/50 金叉') — stops once the user edits ──
	let name = $state('');
	let nameTouched = $state(false);
	const suggested = $derived.by(() => {
		if (kind === 'fng_threshold') return `FNG<${params.below} ${en ? 'fear alert' : '恐慌提醒'}`;
		if (kind === 'vix_threshold')
			return `VIX>${params.above} ${en ? 'US fear alert' : '美股恐慌提醒'}`;
		if (kind === 'ema_cross') {
			const d = choiceLabel(String(params.direction));
			return `${asset} EMA${params.ema_fast}/${params.ema_slow} ${d}`;
		}
		return `${asset} ${en ? 'Donchian' : '唐奇安'} ${params.entry_lb}/${params.exit_lb} ${en ? 'breakout' : '突破'}`;
	});
	$effect(() => {
		if (!nameTouched) name = suggested;
	});

	// ── Data ──────────────────────────────────────────────────────────────────
	let signals = $state<UserSignal[]>([]);
	let fires = $state<SignalFire[]>([]);
	let tgBound = $state<boolean | null>(null);
	let loaded = $state(false);
	let busy = $state(false);
	let err = $state('');
	let formOpen = $state(false);
	const activeCount = $derived(signals.filter((s) => s.status === 'active').length);

	async function load() {
		try {
			const [s, f, l] = await Promise.all([mySignals(), myFires(), getMyLink()]);
			signals = s;
			fires = f;
			tgBound = l?.bound ?? false;
			err = '';
		} catch (e) {
			err = (e as Error).message;
		} finally {
			loaded = true;
		}
	}

	// Load whenever a user session appears or signalsVersion is bumped (a signal
	// was created elsewhere, e.g. from a backtest row); reset when it goes away.
	$effect(() => {
		void $signalsVersion;
		if ($user?.sub) {
			void load();
		} else {
			signals = [];
			fires = [];
			loaded = false;
		}
	});

	// ── Create ────────────────────────────────────────────────────────────────
	function validate(): string | null {
		if ((kind === 'ema_cross' || kind === 'donchian_breakout') && !/^[A-Z0-9]{1,6}$/.test(asset))
			return en
				? 'Asset must be 1-6 letters/digits, e.g. TSLA.'
				: '标的须为 1-6 位字母/数字，如 TSLA。';
		if (kind === 'ema_cross' && !((params.ema_fast as number) < (params.ema_slow as number)))
			return en ? 'Fast EMA must be < slow EMA.' : '快线 EMA 必须小于慢线。';
		if (
			kind === 'donchian_breakout' &&
			!((params.exit_lb as number) <= (params.entry_lb as number))
		)
			return en ? 'Exit lookback must be ≤ entry lookback.' : '离场回看必须 ≤ 入场回看。';
		return null;
	}

	async function submit() {
		const sub = $user?.sub;
		if (!sub || busy) return;
		const v = validate();
		if (v) {
			err = v;
			return;
		}
		busy = true;
		err = '';
		try {
			await createSignal({
				user_id: sub,
				name: name.trim() || suggested,
				kind,
				asset: kind === 'fng_threshold' || kind === 'vix_threshold' ? '*' : asset,
				timeframe: kind === 'fng_threshold' || kind === 'vix_threshold' ? '1d' : tf,
				params: { ...params }
			});
			track('signal_create');
			formOpen = false;
			nameTouched = false;
			await load();
		} catch (e) {
			err = (e as Error).message;
		} finally {
			busy = false;
		}
	}

	// ── Pause / resume (optimistic) ───────────────────────────────────────────
	async function toggleStatus(s: UserSignal) {
		const next = s.status === 'active' ? 'paused' : 'active';
		const prev = signals;
		signals = signals.map((x) => (x.id === s.id ? { ...x, status: next } : x));
		err = '';
		try {
			await setSignalStatus(s.id, next);
		} catch (e) {
			signals = prev; // revert
			err = (e as Error).message;
		}
	}

	// ── Delete with inline confirm (second click within 4s) ──────────────────
	let confirmId = $state<string | null>(null);
	let confirmTimer: ReturnType<typeof setTimeout> | null = null;
	function askDelete(id: string) {
		confirmId = id;
		if (confirmTimer) clearTimeout(confirmTimer);
		confirmTimer = setTimeout(() => (confirmId = null), 4000);
	}
	async function doDelete(id: string) {
		confirmId = null;
		err = '';
		try {
			await deleteSignal(id);
			signals = signals.filter((s) => s.id !== id);
		} catch (e) {
			err = (e as Error).message;
		}
	}

	// ── Display helpers ───────────────────────────────────────────────────────
	function paramsSummary(s: UserSignal): string {
		const p = s.params;
		if (s.kind === 'ema_cross')
			return `EMA ${p.ema_fast}/${p.ema_slow} · ${choiceLabel(String(p.direction))}`;
		if (s.kind === 'donchian_breakout')
			return `${p.entry_lb}/${p.exit_lb} · ${choiceLabel(String(p.side))}`;
		return `FNG < ${p.below}`;
	}
	function assetTf(s: UserSignal): string {
		return s.asset === '*'
			? `${en ? 'market' : '全市场'} · ${s.timeframe}`
			: `${s.asset} · ${s.timeframe}`;
	}
	function rel(ts: string | null): string {
		if (!ts) return en ? 'never fired' : '从未触发';
		const m = Math.floor((Date.now() - new Date(ts).getTime()) / 60_000);
		if (m < 1) return en ? 'just now' : '刚刚';
		if (m < 60) return en ? `${m}m ago` : `${m} 分钟前`;
		if (m < 1440) return en ? `${Math.floor(m / 60)}h ago` : `${Math.floor(m / 60)} 小时前`;
		return en ? `${Math.floor(m / 1440)}d ago` : `${Math.floor(m / 1440)} 天前`;
	}
</script>

<section class="rounded-xl border border-border bg-card p-5">
	{#if !$user}
		<p class="text-sm text-muted-foreground">
			📡
			{en
				? 'Sign in to set your own rule-based signal alerts.'
				: '登录后可设置你自己的规则信号提醒。'}
			<a
				href={`/login?next=${encodeURIComponent($page.url.pathname)}`}
				class="font-medium text-primary hover:underline">{en ? 'Sign in →' : '登录 →'}</a
			>
		</p>
	{:else if !loaded}
		<p class="text-sm text-muted-foreground">{en ? 'Loading…' : '加载中…'}</p>
	{:else}
		<div class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
			<span class="text-sm font-medium text-foreground">{en ? 'My signals' : '我的信号'}</span>
			<span class="text-xs text-muted-foreground">{activeCount}/10 {en ? 'active' : '启用中'}</span>
			<button
				type="button"
				onclick={() => (formOpen = !formOpen)}
				class="ml-auto rounded-md border border-border px-3 py-1.5 text-xs text-foreground hover:bg-muted/30"
			>
				{formOpen ? (en ? 'Close' : '收起') : `➕ ${en ? 'New signal' : '新建信号'}`}
			</button>
		</div>

		<!-- Inline create form: kind → dynamic fields (same pattern as /backtest) -->
		{#if formOpen}
			<div class="mt-3 rounded-md border border-border p-4">
				<div class="grid grid-cols-2 gap-4 sm:grid-cols-4">
					<label class="text-xs">
						<span class="text-muted-foreground">{en ? 'Kind' : '类型'}</span>
						<select
							value={kind}
							onchange={(e) =>
								onKindChange((e.currentTarget as HTMLSelectElement).value as SignalKind)}
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						>
							{#each Object.keys(SIGNAL_KINDS) as k (k)}
								<option value={k}>{kindLabel(k as SignalKind)}</option>
							{/each}
						</select>
					</label>
					{#if kind !== 'fng_threshold' && kind !== 'vix_threshold'}
						<label class="text-xs">
							<span class="text-muted-foreground">{en ? 'Asset' : '标的'}</span>
							<!-- Combo: free text (any US ticker, uppercase-normalized) + suggestions. -->
							<input
								type="text"
								list="signal-assets"
								value={asset}
								oninput={(e) =>
									(asset = (e.currentTarget as HTMLInputElement).value.toUpperCase().trim())}
								placeholder={en ? 'BTC / NVDA / any US ticker' : 'BTC / NVDA / 任意美股代码'}
								maxlength="6"
								autocomplete="off"
								spellcheck="false"
								class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
							/>
							<datalist id="signal-assets">
								{#each CRYPTO_ASSETS as a (a)}<option value={a}>{a}</option>{/each}
								{#each EQUITY_ASSETS as a (a)}<option value={a}>{a}</option>{/each}
								{#each COMMODITY_ASSETS as c (c.sym)}<option value={c.sym}
										>{c.sym} — {en ? c.en : c.zh}</option
									>{/each}
							</datalist>
							<p class="mt-1 text-[11px] text-muted-foreground">
								{en
									? 'US: any ticker (daily); crypto: 8 majors; commodities (gold/oil etc.): daily. Invalid symbols never fire.'
									: '美股支持任意代码（日线）；加密限 8 大币种；商品（黄金/原油等）仅日线；无效代码不会触发。'}
							</p>
						</label>
						<label class="text-xs">
							<span class="text-muted-foreground">{en ? 'Timeframe' : '周期'}</span>
							<select
								bind:value={tf}
								class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
							>
								{#each tfs as f (f)}<option value={f}>{f}</option>{/each}
							</select>
						</label>
					{/if}
					{#each Object.entries(kindCfg.params as Record<string, AnyParam>) as [k, p] (k)}
						<label class="text-xs">
							<span class="text-muted-foreground">{paramLabel(k)}</span>
							{#if isChoice(p)}
								<select
									bind:value={params[k]}
									class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
								>
									{#each p.choices as c (c)}<option value={c}>{choiceLabel(c)}</option>{/each}
								</select>
							{:else}
								<input
									type="number"
									bind:value={params[k]}
									min={p.min}
									max={p.max}
									step={p.step ?? 1}
									class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
								/>
							{/if}
						</label>
					{/each}
					<label class="col-span-2 text-xs">
						<span class="text-muted-foreground">{en ? 'Name' : '名称'}</span>
						<input
							type="text"
							value={name}
							oninput={(e) => {
								name = (e.currentTarget as HTMLInputElement).value;
								nameTouched = true;
							}}
							maxlength="60"
							class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
						/>
					</label>
				</div>
				<button
					type="button"
					onclick={submit}
					disabled={busy}
					class="mt-3 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
				>
					{busy ? (en ? 'Creating…' : '创建中…') : en ? 'Create signal' : '创建信号'}
				</button>
			</div>
		{/if}

		<!-- Signal list -->
		{#if signals.length === 0}
			<p class="mt-3 text-xs text-muted-foreground">
				{en
					? 'No signals yet — create one above, or turn a backtest config into one.'
					: '还没有信号 —— 在上面新建一个，或把回测配置一键变成信号。'}
			</p>
		{:else}
			<div class="mt-3 divide-y divide-border rounded-md border border-border">
				{#each signals as s (s.id)}
					<div class="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
						<span class="font-medium text-foreground">{s.name}</span>
						<span class="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
							>{kindLabel(s.kind)}</span
						>
						<span class="font-mono text-xs text-muted-foreground">{assetTf(s)}</span>
						<span class="font-mono text-xs text-muted-foreground">{paramsSummary(s)}</span>
						<span class="text-xs text-muted-foreground" title={s.last_fired_at ?? ''}
							>{rel(s.last_fired_at)}</span
						>
						<span class="ml-auto flex items-center gap-2">
							<span
								class="rounded border px-1.5 py-0.5 text-[10px] {s.status === 'active'
									? 'border-emerald-500/50 text-emerald-600'
									: 'border-muted-foreground/40 text-muted-foreground'}">{s.status}</span
							>
							<button
								type="button"
								onclick={() => toggleStatus(s)}
								class="rounded-md border border-border px-2 py-1 text-xs text-foreground hover:bg-muted/30"
							>
								{s.status === 'active' ? (en ? 'Pause' : '暂停') : en ? 'Resume' : '启用'}
							</button>
							{#if confirmId === s.id}
								<button
									type="button"
									onclick={() => doDelete(s.id)}
									class="rounded-md border border-red-500/50 px-2 py-1 text-xs text-red-600 hover:bg-red-500/10"
								>
									{en ? 'Confirm delete?' : '确认删除？'}
								</button>
							{:else}
								<button
									type="button"
									onclick={() => askDelete(s.id)}
									class="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-muted/30"
								>
									{en ? 'Delete' : '删除'}
								</button>
							{/if}
						</span>
					</div>
				{/each}
			</div>
		{/if}

		<!-- Recent fires -->
		{#if fires.length > 0}
			<h3 class="mt-5 text-xs font-medium text-muted-foreground">
				{en ? 'Recent fires' : '最近触发'}
			</h3>
			<div class="mt-1 divide-y divide-border rounded-md border border-border">
				{#each fires.slice(0, 20) as f (f.id)}
					<div class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-3 py-1.5 text-xs">
						<span class="font-medium text-foreground">{f.signal_name ?? '—'}</span>
						<span class="text-muted-foreground">{f.details?.message ?? ''}</span>
						<span class="ml-auto text-muted-foreground" title={f.fired_at}>{rel(f.fired_at)}</span>
					</div>
				{/each}
			</div>
		{/if}

		<!-- Telegram nudge: they have signals but no bound chat to push to. -->
		{#if signals.length > 0 && tgBound === false}
			<div class="mt-5">
				<p class="mb-2 text-xs text-muted-foreground">
					{en
						? 'Bind Telegram to get a push when your signals fire; unbound, fires still show up here.'
						: '绑定后信号触发会推送到 Telegram;未绑定也能在这里看到记录'}
				</p>
				<AlertSubscribe />
			</div>
		{/if}

		<p class="mt-4 text-xs text-muted-foreground">
			{en
				? 'Signals are reminders for rules you set yourself — not investment advice.'
				: '信号是你自己设定的规则提醒,不构成投资建议。'}
		</p>
	{/if}
	{#if err}<p class="mt-2 text-xs text-red-500">{err}</p>{/if}
</section>
