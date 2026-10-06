// Read-only browser regression check. Requires the agent-browser CLI.
import { execFileSync } from 'node:child_process';
import assert from 'node:assert/strict';

const base = new URL(process.argv[2] ?? 'http://127.0.0.1:5173');
const session = `language-check-${process.pid}`;
function browser(...args) {
	return execFileSync('agent-browser', ['--session', session, ...args], {
		encoding: 'utf8',
		timeout: 45000
	}).trim();
}
function state() {
	return JSON.parse(
		browser(
			'eval',
			`({language:document.documentElement.lang,title:document.querySelector('h1').textContent,selected:document.querySelector('button[aria-pressed=true]').textContent})`
		)
	);
}
try {
	browser('open', base.href);
	browser('wait', '--load', 'networkidle');
	assert.equal(state().language, 'en', 'New visitors default to English');
	browser('click', 'button[aria-pressed="false"]');
	browser('wait', '--text', '先理解策略规则。');
	assert.equal(state().language, 'zh-CN');
	assert.equal(state().selected, '中');
	browser('reload');
	browser('wait', '--text', '先理解策略规则。');
	assert.equal(state().language, 'zh-CN', 'Preference survives reload');
	for (const [path, title] of [
		['/start', '从策略研究到自己的账户'],
		['/execution', '我的账户']
	]) {
		browser('open', new URL(path, base).href);
		browser('wait', '--load', 'networkidle');
		browser('wait', '--text', title);
		assert.equal(state().language, 'zh-CN');
		assert.equal(state().title, title);
	}
	browser('click', 'button[aria-pressed="false"]');
	browser('wait', '--text', 'Your machine. Your keys.');
	assert.equal(state().language, 'en');
	assert.equal(state().selected, 'EN');
	console.log('PASS: EN → 中文 → reload → guide → account → EN');
} finally {
	browser('close');
}
