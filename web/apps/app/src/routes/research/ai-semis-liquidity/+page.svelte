<script lang="ts">
	import { resolve } from '$app/paths';
	import {
		ArrowUpRight,
		Banknote,
		BatteryCharging,
		BookOpen,
		CircuitBoard,
		Cpu,
		Database,
		MemoryStick,
		Network,
		Shield,
		Zap
	} from 'lucide-svelte';
	import type { Lang } from '$lib/i18n';
	import type { ComponentType } from 'svelte';

	let { data }: { data: { lang?: Lang } } = $props();
	const lang = $derived<Lang>(data.lang ?? 'zh');
	const tr = (zh: string, en: string) => (lang === 'zh' ? zh : en);

	type Pair = { zh: string; en: string };
	type Gate = { title: Pair; text: Pair; signal: Pair; icon: ComponentType };

	const metrics: { label: Pair; value: string; note: Pair }[] = [
		{
			label: { zh: 'TurboQuant KV 压缩', en: 'TurboQuant KV compression' },
			value: '6x+',
			note: {
				zh: 'Google Research 称 KV cache 至少降 6 倍',
				en: 'Google Research reports at least 6x smaller KV cache'
			}
		},
		{
			label: { zh: 'Apple 端侧激活参数', en: 'Apple on-device active params' },
			value: '1-4B',
			note: {
				zh: '20B sparse 模型按 prompt 加载专家到 DRAM',
				en: '20B sparse model loads selected experts into DRAM per prompt'
			}
		},
		{
			label: { zh: '2025 半导体设备销售', en: '2025 semiconductor equipment sales' },
			value: '$135.1B',
			note: {
				zh: 'SEMI 数据，测试和封装设备弹性强',
				en: 'SEMI data with test and packaging equipment strength'
			}
		},
		{
			label: { zh: '离岸美元信用', en: 'Foreign-currency dollar credit' },
			value: '$14.3T',
			note: {
				zh: 'BIS end-2025，AI capex 对美元融资更敏感',
				en: 'BIS end-2025 data; AI capex is more funding-sensitive'
			}
		},
		{
			label: { zh: '2030 数据中心电耗', en: '2030 data-center electricity demand' },
			value: '945 TWh',
			note: {
				zh: 'IEA 基准情景，电力成为物理约束',
				en: 'IEA base case; power becomes a physical constraint'
			}
		},
		{
			label: { zh: 'AI baseboard 电容数', en: 'AI baseboard capacitors' },
			value: '15k-25k',
			note: {
				zh: 'Murata 上修 AI server baseboard 电容数量',
				en: 'Murata raised the AI server baseboard capacitor-count estimate'
			}
		}
	];

	const gates: Gate[] = [
		{
			title: { zh: 'HBM', en: 'HBM' },
			text: {
				zh: '高端 AI 加速器不是缺普通内存，而是缺高带宽、低功耗、可封装进 GPU/ASIC 旁边的 HBM。HBM 合约、良率和 wafer allocation 决定 2026 的真实供给。',
				en: 'Leading AI accelerators are gated by high-bandwidth memory that can sit beside the GPU or ASIC. Contracts, yield and wafer allocation define real supply in 2026.'
			},
			signal: {
				zh: '看 HBM3E/HBM4 价格是否继续强于普通 DRAM。',
				en: 'Watch whether HBM3E and HBM4 keep pricing power versus commodity DRAM.'
			},
			icon: MemoryStick
		},
		{
			title: { zh: '先进封装', en: 'Advanced packaging' },
			text: {
				zh: 'CoWoS、SoIC、2.5D/3D、panel-level fan-out 正在变成第二个晶圆厂。没有封装产能，先进 die 和 HBM 无法变成可出货的 AI 模组。',
				en: 'CoWoS, SoIC, 2.5D/3D and panel-level fan-out are becoming the second fab. Without package capacity, dies and HBM do not become shippable modules.'
			},
			signal: {
				zh: '看 CoWoS 交期、OSAT 订单和测试设备需求。',
				en: 'Watch CoWoS lead times, OSAT orders and test-equipment demand.'
			},
			icon: CircuitBoard
		},
		{
			title: { zh: '网络与光模块', en: 'Networking and optics' },
			text: {
				zh: '集群从数千颗 XPU 扩到数十万颗时，网络不是配件，而是算力利用率。1.6T/3.2T 光模块、AI Ethernet、CPO 和硅光会决定集群效率。',
				en: 'When clusters scale from thousands to hundreds of thousands of XPUs, networking is utilization. 1.6T/3.2T optics, AI Ethernet, CPO and silicon photonics matter.'
			},
			signal: {
				zh: '看 1.6T/3.2T 量产和大客户多年订单。',
				en: 'Watch 1.6T/3.2T production and multi-year hyperscaler orders.'
			},
			icon: Network
		},
		{
			title: { zh: '电力与并网', en: 'Power and grid access' },
			text: {
				zh: '真正的天花板可能不是买不到 GPU，而是数据中心无法按时拿到电力、土地、冷却和并网许可。能效会变成硬指标。',
				en: 'The real ceiling may be power, land, cooling and interconnection permits rather than GPU availability. Efficiency becomes a hard metric.'
			},
			signal: {
				zh: '看 PPA、天然气/核电项目和 grid queue。',
				en: 'Watch PPAs, gas or nuclear projects and grid queues.'
			},
			icon: Zap
		},
		{
			title: { zh: 'MLCC 与电源完整性', en: 'MLCC and power integrity' },
			text: {
				zh: 'AI 服务器的瞬态电流、PSU/IBC/VRM、xPU/HBM 去耦和板级空间约束，会把高端 MLCC 变成稳定交付的隐形瓶颈。',
				en: 'AI servers create transient-current, PSU/IBC/VRM, xPU/HBM decoupling and board-space constraints that make high-end MLCCs a hidden delivery bottleneck.'
			},
			signal: {
				zh: '看 AI server-grade MLCC lead time、Murata/TDK/Samsung 高端料号和 power module 认证。',
				en: 'Watch AI server-grade MLCC lead times, Murata/TDK/Samsung high-end parts and power-module qualifications.'
			},
			icon: BatteryCharging
		},
		{
			title: { zh: '美元信用', en: 'Dollar credit' },
			text: {
				zh: 'AI capex 已经大到不能只靠经营现金流覆盖。融资成本、信用利差和 private credit 风险，会决定边际项目是否继续。',
				en: 'AI capex is too large to rely only on operating cash flow. Funding cost, credit spreads and private-credit risk decide whether marginal projects continue.'
			},
			signal: {
				zh: '看利差、美元流动性和 hyperscaler 折旧压力。',
				en: 'Watch spreads, dollar liquidity and hyperscaler depreciation pressure.'
			},
			icon: Banknote
		}
	];

	const timeline: { year: string; title: Pair; text: Pair }[] = [
		{
			year: '2026',
			title: { zh: '供给紧张期', en: 'Supply squeeze' },
			text: {
				zh: 'HBM、先进封装、先进节点、网络、MLCC 和电力同步抢货。瓶颈资产最强。',
				en: 'HBM, packaging, nodes, networking, MLCCs and power are all being booked aggressively. Bottleneck assets lead.'
			}
		},
		{
			year: '2027',
			title: { zh: '产能释放期', en: 'Capacity release' },
			text: {
				zh: '扩产开始释放，市场从“有没有货”转向“新增产能能否被高利用率消化”。',
				en: 'New capacity arrives and the question moves from availability to utilization.'
			}
		},
		{
			year: '2028',
			title: { zh: 'ROI 分化期', en: 'ROI divergence' },
			text: {
				zh: '赢家不是买最多 GPU 的公司，而是能把算力、电力和软件转成高毛利收入的公司。',
				en: 'The winners are not the biggest GPU buyers but the firms that convert compute, power and software into high-margin revenue.'
			}
		}
	];

	const watchlist: { indicator: Pair; bullish: Pair; warning: Pair }[] = [
		{
			indicator: { zh: 'HBM 合约价', en: 'HBM contract pricing' },
			bullish: { zh: '强于普通 DRAM', en: 'Outperforms commodity DRAM' },
			warning: { zh: '新增供给压价', en: 'New supply compresses pricing' }
		},
		{
			indicator: { zh: '先进封装产能', en: 'Advanced packaging capacity' },
			bullish: { zh: '交期长、预付款强', en: 'Long lead times and strong prepayments' },
			warning: { zh: '扩产后利用率下降', en: 'Utilization falls after expansion' }
		},
		{
			indicator: { zh: '云厂商 capex', en: 'Hyperscaler capex' },
			bullish: { zh: '指引上调且 backlog 增长', en: 'Guidance rises with backlog' },
			warning: { zh: '收入不跟折旧', en: 'Revenue lags depreciation' }
		},
		{
			indicator: { zh: 'AI 网络订单', en: 'AI networking orders' },
			bullish: { zh: '1.6T/3.2T 放量', en: '1.6T and 3.2T ramp' },
			warning: { zh: '光模块库存累积', en: 'Optics inventory builds' }
		},
		{
			indicator: { zh: '高端 MLCC 交期', en: 'High-end MLCC lead times' },
			bullish: { zh: 'AI server-grade 分配制', en: 'AI server-grade parts move to allocation' },
			warning: { zh: '普通料号扩产压价', en: 'Commodity expansion pressures pricing' }
		},
		{
			indicator: { zh: '美元信用', en: 'Dollar credit' },
			bullish: { zh: '利差低、流动性扩张', en: 'Low spreads and expanding liquidity' },
			warning: { zh: 'private credit 风险暴露', en: 'Private-credit stress appears' }
		}
	];

	const sources = [
		{
			label: 'SIA',
			href: 'https://www.semiconductors.org/global-semiconductor-sales-increase-25-from-q4-2025-to-q1-2026/'
		},
		{
			label: 'Apple AFM 3',
			href: 'https://machinelearning.apple.com/research/introducing-third-generation-of-apple-foundation-models'
		},
		{
			label: 'Google TurboQuant',
			href: 'https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/'
		},
		{
			label: 'SEMI',
			href: 'https://www.semi.org/en/SEMI-Reports-Global-Semiconductor-Equipment-Billings-Reached-135-Billion-in-2025'
		},
		{
			label: 'Murata MLCC IR Day',
			href: 'https://corporate.murata.com/-/media/corporate/about/newsroom/news/irnews/irnews/2025/1201/2512-e-speach.ashx?cvid=20251204015903000000&la=en'
		},
		{
			label: 'TDK Data Center MLCC',
			href: 'https://product.tdk.com/en/techlibrary/applicationnote/mlcc-solution-for-data-center-psu.html'
		},
		{ label: 'BIS GLI', href: 'https://www.bis.org/statistics/gli2604.htm' },
		{
			label: 'IEA Energy and AI',
			href: 'https://www.iea.org/reports/energy-and-ai/energy-demand-from-ai'
		},
		{
			label: 'MLPerf Inference',
			href: 'https://mlcommons.org/2025/04/mlperf-inference-v5-0-results/'
		}
	];
</script>

<svelte:head>
	<title>{tr('AI 半导体与全球流动性研究', 'AI Semis and Global Liquidity Research')}</title>
	<meta
		name="description"
		content={tr(
			'面向读者的 AI 半导体、全球流动性、产业链瓶颈和三年驱动分析。',
			'Reader-facing analysis of AI semiconductors, global liquidity, supply-chain bottlenecks and three-year drivers.'
		)}
	/>
</svelte:head>

<main class="mx-auto w-full max-w-[1280px] px-4 py-8 sm:px-6 lg:py-10">
	<section class="mb-8 border-b border-border pb-8">
		<div class="bdv-eyebrow mb-3 text-[var(--gold-500)]">BearDawnVerse · Research</div>
		<div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-end">
			<div>
				<h1 class="bdv-display text-[34px] leading-[1.08] font-bold tracking-tight sm:text-[48px]">
					{tr('AI 半导体与全球流动性', 'AI Semiconductors and Global Liquidity')}
				</h1>
				<p class="mt-4 max-w-3xl text-[15px] leading-7 text-muted-foreground">
					{tr(
						'未来三年，真正的问题不是谁卖 GPU，而是 AI 架构能不能突破内存墙。我们把论文和产业拆成 token 需求、KV cache、HBM、先进封装、网络、电力、政策和美元信用八个层面。',
						'Over the next three years, the question is not simply who sells GPUs. It is whether AI architecture can break the memory wall across tokens, KV cache, HBM, packaging, networking, power, policy and dollar credit.'
					)}
				</p>
				<div class="mt-5 flex flex-wrap gap-3">
					<a
						href={resolve('/semis')}
						class="inline-flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm font-medium hover:bg-accent"
					>
						<Cpu size={16} />
						{tr('半导体图谱', 'Semis map')}
					</a>
					<a
						href={resolve('/globe')}
						class="inline-flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm font-medium hover:bg-accent"
					>
						<Database size={16} />
						{tr('全球新闻', 'Global news')}
					</a>
				</div>
			</div>
			<div class="rounded-md border border-border bg-card p-4">
				<div class="flex items-center gap-2 text-sm font-semibold">
					<BookOpen size={16} />
					{tr('一句话结论', 'One-line thesis')}
				</div>
				<p class="mt-3 text-sm leading-6 text-muted-foreground">
					{tr(
						'AI 不会停止吃内存，但会越来越聪明地吃内存；同时更高 rack power 会把 MLCC/电源完整性推成隐形瓶颈。估值锚正在从“容量”推向“带宽、封装、层级、调度和板级可靠性”。',
						'AI will not stop consuming memory, but it will consume memory more intelligently; higher rack power also turns MLCCs and power integrity into hidden bottlenecks. The valuation anchor is shifting from capacity to bandwidth, packaging, hierarchy, scheduling and board-level reliability.'
					)}
				</p>
			</div>
		</div>
	</section>

	<section class="mb-10 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
		{#each metrics as m (m.label.en)}
			<div class="rounded-md border border-border bg-card p-4">
				<div class="text-xs tracking-wide text-muted-foreground uppercase">
					{tr(m.label.zh, m.label.en)}
				</div>
				<div class="bdv-display mt-2 text-[30px] font-bold">{m.value}</div>
				<p class="mt-2 text-sm leading-6 text-muted-foreground">{tr(m.note.zh, m.note.en)}</p>
			</div>
		{/each}
	</section>

	<section class="mb-10">
		<div class="mb-4 flex items-center gap-2">
			<Shield size={18} />
			<h2 class="bdv-display text-2xl font-bold">
				{tr('六个真正的收费站', 'Six Real Toll Gates')}
			</h2>
		</div>
		<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
			{#each gates as gate (gate.title.en)}
				{@const Icon = gate.icon}
				<article class="rounded-md border border-border bg-card p-4">
					<div
						class="mb-3 grid h-9 w-9 place-items-center rounded-md border border-border bg-background"
					>
						<Icon size={18} />
					</div>
					<h3 class="text-base font-semibold">{tr(gate.title.zh, gate.title.en)}</h3>
					<p class="mt-3 text-sm leading-6 text-muted-foreground">
						{tr(gate.text.zh, gate.text.en)}
					</p>
					<p class="mt-3 border-t border-border pt-3 text-xs leading-5 text-[var(--gold-500)]">
						{tr(gate.signal.zh, gate.signal.en)}
					</p>
				</article>
			{/each}
		</div>
	</section>

	<section class="mb-10 grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
		<div class="rounded-md border border-border bg-card p-5">
			<h2 class="bdv-display text-2xl font-bold">{tr('2026-2028 节奏', '2026-2028 Cadence')}</h2>
			<p class="mt-3 text-sm leading-6 text-muted-foreground">
				{tr(
					'分析 AI 半导体不能只看本季度订单。更重要的是判断周期从供给短缺、产能释放，到 ROI 分化的切换点。',
					'AI semis should not be judged only by this quarter’s orders. The key is the transition from shortage, to capacity release, to ROI divergence.'
				)}
			</p>
		</div>
		<div class="grid gap-3 md:grid-cols-3">
			{#each timeline as item (item.year)}
				<div class="rounded-md border border-border bg-card p-4">
					<div class="bdv-display text-[28px] font-bold text-[var(--gold-500)]">{item.year}</div>
					<h3 class="mt-2 font-semibold">{tr(item.title.zh, item.title.en)}</h3>
					<p class="mt-2 text-sm leading-6 text-muted-foreground">
						{tr(item.text.zh, item.text.en)}
					</p>
				</div>
			{/each}
		</div>
	</section>

	<section class="mb-10 overflow-hidden rounded-md border border-border bg-card">
		<div class="border-b border-border p-4">
			<h2 class="bdv-display text-2xl font-bold">{tr('读者跟踪表', 'Reader Watchlist')}</h2>
			<p class="mt-2 text-sm text-muted-foreground">
				{tr(
					'只要其中两层同时转弱，就要降低 AI 半导体周期假设。',
					'If two layers weaken at the same time, cut the AI semi-cycle assumption.'
				)}
			</p>
		</div>
		<div class="overflow-x-auto">
			<table class="min-w-full text-left text-sm">
				<thead class="border-b border-border text-xs text-muted-foreground uppercase">
					<tr>
						<th class="px-4 py-3 font-medium">{tr('指标', 'Indicator')}</th>
						<th class="px-4 py-3 font-medium">{tr('多头信号', 'Bullish signal')}</th>
						<th class="px-4 py-3 font-medium">{tr('风险信号', 'Warning sign')}</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-border">
					{#each watchlist as row (row.indicator.en)}
						<tr>
							<td class="px-4 py-3 font-medium">{tr(row.indicator.zh, row.indicator.en)}</td>
							<td class="px-4 py-3 text-muted-foreground">{tr(row.bullish.zh, row.bullish.en)}</td>
							<td class="px-4 py-3 text-muted-foreground">{tr(row.warning.zh, row.warning.en)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</section>

	<section class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
		<div class="rounded-md border border-border bg-card p-5">
			<h2 class="bdv-display text-2xl font-bold">{tr('非共识判断', 'Non-consensus View')}</h2>
			<div class="mt-4 grid gap-4 text-sm leading-7 text-muted-foreground md:grid-cols-2">
				<p>
					{tr(
						'内存效率提升不会简单杀死内存需求。TurboQuant、KIVI、PagedAttention、MLA 和 linear attention 会降低单位 token 的 HBM 占用，但也可能释放更长上下文、更高并发和更多 agent 工作流。',
						'Memory efficiency gains do not simply destroy memory demand. TurboQuant, KIVI, PagedAttention, MLA and linear attention reduce HBM per token, but can unlock longer contexts, higher concurrency and more agent workflows.'
					)}
				</p>
				<p>
					{tr(
						'内存股真正的风险不是 AI 结束，而是 HBM 估值锚改变。如果 2027 年 KV 压缩和混合架构成为默认路径，市场会从“买所有容量”切到“买带宽、良率、custom HBM 和先进封装”。',
						'The real risk for memory stocks is not the end of AI; it is a changing HBM valuation anchor. If KV compression and hybrid architectures become default by 2027, the market shifts from buying all capacity to buying bandwidth, yield, custom HBM and advanced packaging.'
					)}
				</p>
			</div>
		</div>
		<div class="rounded-md border border-border bg-card p-5">
			<h2 class="bdv-display text-xl font-bold">{tr('核心来源', 'Core Sources')}</h2>
			<div class="mt-4 flex flex-col gap-2">
				{#each sources as source (source.label)}
					<a
						href={source.href}
						target="_blank"
						rel="noreferrer"
						class="inline-flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm hover:bg-accent"
					>
						<span>{source.label}</span>
						<ArrowUpRight size={15} />
					</a>
				{/each}
				<!-- eslint-enable svelte/no-navigation-without-resolve -->
			</div>
		</div>
	</section>
</main>
