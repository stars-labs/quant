import { spawnSync } from 'node:child_process';
import assert from 'node:assert/strict';

const session = 'account-display-harness';
const origin = process.argv[2] ?? 'https://quant.starslab.qzz.io';
function browser(...args) {
	const result = spawnSync('agent-browser', ['--session', session, ...args], {
		encoding: 'utf8',
		timeout: 60000
	});
	if (result.status !== 0) throw new Error(result.stderr || result.stdout);
	return result.stdout;
}
const now = new Date().toISOString();
const report = {
	version: 1,
	sequence: 1,
	observed_at: now,
	status: 'healthy',
	venue: 'htx',
	environment: 'live',
	cash_usdt: 100,
	equity_usdt: 198,
	funded_usdt: 200,
	trend_available_usdt: 0,
	dca_available_usdt: 100,
	fees_usdt: 0.2,
	positions: [],
	fills: [],
	decisions: [{ strategy: 'trend', asset: 'BTC', reason: 'confirmed_budget_unavailable' }],
	return_summary: {
		method: 'modified_dietz',
		estimated: true,
		start_at: new Date(Date.now() - 3600000).toISOString(),
		end_at: now,
		return_pct: 1,
		unavailable_reason: null
	},
	funding_history: [
		{
			reference: 'fund:2026-10-01',
			month: '2026-10-01',
			kind: 'deposit',
			confirmed_at: null,
			trend_delta_usdt: 100,
			dca_delta_usdt: 100,
			cash_delta_usdt: 200
		}
	],
	attribution: [
		{
			strategy: 'trend',
			asset: 'BTC',
			realized_pnl_usdt: 0,
			unrealized_pnl_usdt: -2,
			net_pnl_usdt: -2,
			fees_usdt: 0.2
		}
	],
	history: [
		{
			observed_at: now,
			price_as_of: now,
			equity_usdt: 198,
			cash_usdt: 100,
			net_contributions_usdt: 200,
			fees_usdt: 0.2,
			net_pnl_usdt: -2
		}
	]
};
const fixture = [
	{
		id: 'fixture-only',
		label: 'Fixture HTX',
		venue: 'htx',
		environment: 'live',
		created_at: now,
		revoked_at: null,
		received_at: now,
		sequence: 1,
		report
	}
];
try {
	browser('open', origin + '/execution');
	browser('wait', '--load', 'networkidle');
	browser('network', 'route', '**/rpc/**', '--abort');
	browser('network', 'route', '**/runner_connections**', '--body', JSON.stringify(fixture));
	browser(
		'eval',
		`localStorage.setItem('qt_session_v1',JSON.stringify({access_token:'fixture-only',expires_at:Date.now()+600000,user:{sub:'fixture-only'}})); document.cookie='qt_jwt=fixture-only; path=/'; const originalFetch=window.fetch.bind(window); window.fetch=(input,options)=>String(input).includes('/telegram_links') ? Promise.resolve(new Response(JSON.stringify([{link_token:'fixture-only',bound:true,topics:[],coins:null}]),{status:200,headers:{'Content-Type':'application/json'}})) : String(input).includes('/runner_connections') ? Promise.resolve(new Response(${JSON.stringify(JSON.stringify(fixture))},{status:200,headers:{'Content-Type':'application/json'}})) : originalFetch(input,options);`
	);
	browser('wait', '31000');
	const loaded = browser('get', 'text', 'body');
	assert.ok(loaded.includes('Fixture HTX'), 'Fixture was not loaded: ' + loaded.slice(-800));
	for (const [lang, width, height] of [
		['en', 1440, 1000],
		['zh', 390, 844]
	]) {
		browser('set', 'viewport', String(width), String(height));
		if (lang === 'zh') {
			browser('click', 'button[aria-pressed="false"]');
			browser('wait', '--load', 'networkidle');
		}
		const text = browser('get', 'text', 'body');
		assert.ok(text.includes(lang === 'en' ? 'Account history' : '账户历史'));
		assert.ok(
			text.includes(lang === 'en' ? 'No confirmed budget is available' : '没有可用的已确认预算')
		);
		assert.ok(text.includes(lang === 'en' ? 'Net contributions' : '净投入'));
		assert.ok(text.includes(lang === 'en' ? 'Private Telegram alerts' : '私有 Telegram 提醒'));
		assert.ok(text.includes(lang === 'en' ? 'Live PnL attribution' : '实盘收益归因'));
		assert.ok(text.includes(lang === 'en' ? 'Funding and allocation history' : '资金与预算流水'));
		assert.ok(text.includes(lang === 'en' ? 'Confirmation time unrecorded' : '确认时间未记录'));
		assert.ok(
			text.includes(
				lang === 'en'
					? 'Observed return (estimated, cash-flow adjusted)'
					: '观测期收益率（资金调整估算）'
			)
		);
		assert.ok(text.includes(lang === 'en' ? 'Telegram connected' : 'Telegram 已绑定'));
		const metrics = JSON.parse(
			browser('eval', '({viewport:innerWidth,width:document.documentElement.scrollWidth})')
		);
		assert.ok(metrics.width <= metrics.viewport, 'Account page overflows the viewport');
		browser('screenshot', `/tmp/account-display-${lang}.png`, '--full');
		console.log(`${lang}: history, decisions, contributions and viewport passed`);
	}
} finally {
	browser('close');
}
