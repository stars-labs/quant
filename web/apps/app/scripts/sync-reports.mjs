#!/usr/bin/env node
/**
 * Copy ../../../reports/* into static/reports/ so Cloudflare Pages serves
 * the plotly HTML backtest reports alongside the SvelteKit app.
 *
 * Also writes static/reports/index.json (manifest) for the reports listing page.
 */
import {
	copyFileSync,
	existsSync,
	mkdirSync,
	readdirSync,
	rmSync,
	writeFileSync,
	statSync
} from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = join(__dirname, '../../../..', 'reports');
const DST = join(__dirname, '..', 'static', 'reports');
const MAX_MB = 20; // Cloudflare Pages limit 25 MB — leave some headroom

if (!existsSync(SRC)) {
	console.log(`sync-reports: source ${SRC} does not exist; skipping`);
	process.exit(0);
}

// Fresh copy
rmSync(DST, { recursive: true, force: true });
mkdirSync(DST, { recursive: true });

let skipped = [];
function copyFilterHuge(src, dst) {
	for (const entry of readdirSync(src, { withFileTypes: true })) {
		const s = join(src, entry.name);
		const d = join(dst, entry.name);
		if (entry.isDirectory()) {
			mkdirSync(d, { recursive: true });
			copyFilterHuge(s, d);
		} else {
			const sz = statSync(s).size / (1024 * 1024);
			if (sz > MAX_MB) {
				skipped.push({ path: s.replace(SRC + '/', ''), mb: sz.toFixed(1) });
				continue;
			}
			copyFileSync(s, d);
		}
	}
}
copyFilterHuge(SRC, DST);

// Manifest
const folders = readdirSync(DST, { withFileTypes: true })
	.filter((d) => d.isDirectory())
	.map((d) => {
		const folder = d.name;
		const folderPath = join(DST, folder);
		const pages = readdirSync(folderPath)
			.filter((n) => n.endsWith('.html'))
			.sort();
		const mt = statSync(folderPath).mtime.toISOString();
		return { folder, pages, updated: mt };
	});

writeFileSync(join(DST, 'manifest.json'), JSON.stringify({ folders, skipped }, null, 2));
console.log(`sync-reports: copied ${folders.length} folders → ${DST}`);
for (const f of folders) console.log(`  ${f.folder}  (${f.pages.length} pages)`);
if (skipped.length) {
	console.log(`sync-reports: skipped ${skipped.length} files over ${MAX_MB} MB (CF Pages limit):`);
	for (const s of skipped) console.log(`  ${s.path} (${s.mb} MB)`);
}
