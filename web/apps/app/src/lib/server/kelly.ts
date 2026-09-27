// Server-side helper that reads the Kelly status JSON snapshot generated
// by `python strategies/telegram_alerts.py --write-kelly-status`. The file
// is written into `static/data/kelly_status.json` so it ships as a static
// asset; we fetch it via SvelteKit's same-origin fetch so the loader path
// works identically in dev, preview, and the Cloudflare Worker.

import type { KellyStatusEntry, KellyStatusFile } from '$lib/types';

const ASSET_PATH = '/kelly_status.json';

let cached: KellyStatusFile | null = null;
let cachedAt = 0;
const CACHE_TTL_MS = 60_000; // freshness ceiling — the file only updates once/day

export async function loadKellyStatus(fetchFn: typeof fetch): Promise<KellyStatusFile | null> {
	const now = Date.now();
	if (cached && now - cachedAt < CACHE_TTL_MS) return cached;
	try {
		const res = await fetchFn(ASSET_PATH);
		if (!res.ok) {
			// Drain the body so the Cloudflare runtime can release the slot.
			await res.body?.cancel().catch(() => {});
			return null;
		}
		const data = (await res.json()) as KellyStatusFile;
		cached = data;
		cachedAt = now;
		return data;
	} catch {
		return null;
	}
}

/**
 * Build a name → entry map for quick per-strategy lookup from a page loader.
 * Returns an empty Map (not null) so the consumer can always `.get(name)`.
 */
export function indexKellyStatus(file: KellyStatusFile | null): Map<string, KellyStatusEntry> {
	const m = new Map<string, KellyStatusEntry>();
	if (!file) return m;
	for (const e of file.strategies) m.set(e.name, e);
	return m;
}
