// Run: node --test src/lib/growth.test.ts   (from web/apps/app; Node >= 22.18 strips types)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
	HOUSE_COINS,
	hasCoin,
	liveSummary,
	refFromSearch,
	toggleCoin,
	LIVE_MIN_SAMPLE
} from './growth.ts';

test('refFromSearch keeps valid channel refs, lower-cased', () => {
	assert.equal(refFromSearch('?ref=tg_entry'), 'tg_entry');
	assert.equal(refFromSearch('?x=1&ref=TG_Scan'), 'tg_scan');
});

test('refFromSearch drops missing or malformed refs', () => {
	assert.equal(refFromSearch(''), null);
	assert.equal(refFromSearch('?ref='), null);
	assert.equal(refFromSearch('?ref=bad%20ref'), null);
	assert.equal(refFromSearch('?ref=' + 'a'.repeat(33)), null);
});

test('HOUSE_COINS mirrors strategy_record.ASSETS', () => {
	const py = readFileSync(
		new URL('../../../../../strategies/strategy_record.py', import.meta.url),
		'utf8'
	);
	const assets = [...py.match(/ASSETS = \(([^)]*)\)/s)![1].matchAll(/"([A-Z0-9]+)"/g)].map(
		(m) => m[1]
	);
	assert.deepEqual([...HOUSE_COINS], assets);
});

test('null coins means every coin', () => {
	assert.equal(hasCoin(null, 'PEPE'), true);
	assert.equal(hasCoin(['BTC'], 'PEPE'), false);
});

test('unticking one coin from "all" lists the other twelve', () => {
	const next = toggleCoin(null, 'PEPE');
	assert.deepEqual(
		next,
		HOUSE_COINS.filter((c) => c !== 'PEPE')
	);
});

test('ticking the last missing coin goes back to null (all, incl. future coins)', () => {
	const allButOne = HOUSE_COINS.filter((c) => c !== 'WLD');
	assert.equal(toggleCoin(allButOne, 'WLD'), null);
});

test('selection keeps universe order and can be empty', () => {
	assert.deepEqual(toggleCoin(['SOL'], 'BTC'), ['BTC', 'SOL']);
	assert.deepEqual(toggleCoin(['SOL'], 'SOL'), []);
});

test('liveSummary with no live signals yet', () => {
	const s = liveSummary(null);
	assert.deepEqual(
		[s.nSignals, s.nClosed, s.winRate, s.ret, s.smallSample],
		[0, 0, null, null, true]
	);
});

test('liveSummary win rate and small-sample flag', () => {
	const row = {
		n_signals: 25,
		n_closed: LIVE_MIN_SAMPLE,
		n_wins: 8,
		n_open: 5,
		closed_compound: 0.12,
		first_entry_ts: '2026-09-27T03:59:59.999Z'
	};
	const s = liveSummary(row);
	assert.deepEqual([s.winRate, s.ret, s.smallSample], [0.4, 0.12, false]);
	assert.equal(liveSummary({ ...row, n_closed: 19 }).smallSample, true);
});
