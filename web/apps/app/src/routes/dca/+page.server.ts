import type { PageServerLoad } from './$types';
import { vps, supabase } from '$lib/api';
import type { DcaLogRow, OhlcRow } from '$lib/types';

export const load: PageServerLoad = async ({ fetch, cookies }) => {
	const jwt = cookies.get('qt_jwt');
	const auth = jwt ? `Bearer ${jwt}` : undefined;
	const isAuthed = Boolean(jwt);

	const ohlcFor = (pair: string) =>
		isAuthed
			? vps
					.ohlcDaily(fetch, pair, { from: '2017-01-01', limit: 4000, authHeader: auth })
					.catch(() => [] as OhlcRow[])
			: vps
					.publicOhlcDaily(fetch, pair, { from: '2017-01-01', limit: 4000 })
					.catch(() => [] as OhlcRow[]);

	const [logRaw, btcOhlc, ethOhlc, bnbOhlc, solOhlc] = await Promise.all([
		supabase.dcaLog(fetch, { limit: 200 }).catch(() => [] as DcaLogRow[]),
		ohlcFor('BTC/USDT'),
		ohlcFor('ETH/USDT'),
		ohlcFor('BNB/USDT'),
		ohlcFor('SOL/USDT')
	]);
	// Coerce to an array: a malformed 200 (Supabase returning a non-array body during a
	// transient hiccup) passes req()'s ok-check, so the post-processing below would otherwise
	// crash with a 500 and take the whole page down. Be resilient instead.
	const log = Array.isArray(logRaw) ? logRaw : [];
	const ohlcByCoin = { BTC: btcOhlc, ETH: ethOhlc, BNB: bnbOhlc, SOL: solOhlc };

	const sortedLog = [...log].sort((a, b) => (a.timestamp ?? '').localeCompare(b.timestamp ?? ''));
	let cum = 0;
	const cumulative = sortedLog.map((r) => {
		cum += r.amount_usdt ?? 0;
		return { ts: r.timestamp, amount: r.amount_usdt ?? 0, cum, mode: r.mode };
	});

	return {
		isAuthed,
		log,
		cumulative,
		ohlcByCoin,
		summary: {
			scheduled_count: log.length,
			scheduled_total_usdt: log.reduce((s, r) => s + (r.amount_usdt ?? 0), 0),
			last_scheduled: log[0]?.timestamp ?? null
		}
	};
};
