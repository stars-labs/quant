import { test } from 'node:test';
import assert from 'node:assert/strict';
import { homeOverview } from './home-overview.ts';
const now = Date.parse('2026-10-06T00:00:00Z');
const row = {
	strategy: 'donchian_1h',
	asset: 'BTC',
	start_ts: '2026-01-01T00:00:00Z',
	last_ts: '2026-10-05T23:00:00Z',
	sleeve_ret: 0.2,
	hold_ret: 0.1,
	n_closed: 5,
	open_entry_ts: null
};
test('uses equal-weight rule returns and the oldest asset close', () => {
	const result = homeOverview(
		[
			row,
			{
				...row,
				asset: 'ETH',
				sleeve_ret: -0.1,
				n_closed: 2,
				last_ts: '2026-10-05T22:00:00Z',
				open_entry_ts: row.start_ts
			}
		],
		now
	)!;
	assert.equal(result.modelReturn, 0.05);
	assert.equal(result.closed, 7);
	assert.equal(result.open, 1);
	assert.equal(result.asOf, '2026-10-05T22:00:00.000Z');
	assert.equal(result.stale, false);
});
test('missing or malformed data cannot masquerade as zero return', () => {
	for (const input of [
		null,
		[],
		{},
		[row, row],
		[{ ...row, asset: '' }],
		[{ ...row, start_ts: 1 }],
		[{ ...row, last_ts: 1 }],
		[{ ...row, start_ts: '2027-01-01T00:00:00Z' }],
		[{ ...row, sleeve_ret: null }],
		[{ ...row, hold_ret: NaN }],
		[{ ...row, n_closed: -1 }],
		[{ ...row, last_ts: 'bad' }],
		[{ ...row, last_ts: '2026-10-06T01:00:00Z' }]
	])
		assert.equal(homeOverview(input, now), null);
});
test('one stale asset makes the whole snapshot delayed', () => {
	assert.equal(
		homeOverview([row, { ...row, asset: 'ETH', last_ts: '2026-10-05T20:00:00Z' }], now)!.stale,
		true
	);
});
