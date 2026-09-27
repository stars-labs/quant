import type { PageServerLoad } from './$types';
// Inline the manifest at build time. SSR `fetch('/reports/manifest.json')` on
// Cloudflare doesn't route through the static-asset binding — the worker's own
// code handles the request and returns 404, so the load silently fell back to
// []. Importing the JSON bakes it into the worker bundle (a few KB, fine).
import manifestJson from '../../../static/reports/manifest.json';

interface Manifest {
	folder: string;
	pages: string[];
	updated: string;
}

const DESCRIPTIONS: Record<string, { title: string; body: string }> = {
	hyperopted_full_history: {
		title: '📈 Hyperopt 后全历史',
		body: '4 参数 hyperopt (Optuna CmaEs) 后的生产参数，在 2017-2026 全历史上跑的结果。'
	},
	full_history_btceth: {
		title: '📊 BTC+ETH 全历史（旧 baseline）',
		body: 'Phase A 采纳前的默认配置。保留做对比基准。'
	},
	full_history_btceth_pyramid: {
		title: '🏛️ BTC+ETH + Pyramid Winners',
		body: '开启加仓机制后的版本，+41% 额外利润，Max DD 不涨。'
	},
	pyramid: {
		title: '🧩 Pyramid 专题',
		body: '加仓逻辑本身的独立回测，验证"只加赢家，不 Martingale"的稳定性。'
	},
	dca_backtest: {
		title: '💰 Smart DCA 对比',
		body: 'flat / current / aggressive / fng-only 4 种乘数规则的累积 BTC 对比。'
	},
	walk_forward: {
		title: '🧭 Walk-Forward 对比',
		body: '3 策略 × 8 个 regime 窗口的稳定性分析。'
	}
};

type ManifestShape = {
	folders?: Manifest[];
	skipped?: Array<{ path: string; mb: string }>;
};

export const load: PageServerLoad = async () => {
	const manifest = manifestJson as ManifestShape;
	const enriched = (manifest.folders ?? []).map((m) => ({
		...m,
		...(DESCRIPTIONS[m.folder] ?? { title: m.folder, body: '' })
	}));
	return { reports: enriched, skipped: manifest.skipped ?? [] };
};
