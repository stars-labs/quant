#!/usr/bin/env node
/**
 * Copy selected markdown files from ../../../docs/*.md → src/content/docs/<category>/
 * with frontmatter added for Starlight.
 *
 * Bilingual: reads from ../../../docs/<stem>.md (zh, default locale) and
 * ../../../docs/en/<stem>.md (en) and writes to src/content/docs/<cat>/<slug>.md
 * and src/content/docs/en/<cat>/<slug>.md respectively. English files are
 * optional — if missing, we skip (Starlight falls back to root locale).
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = join(__dirname, '../../../..', 'docs');
const SRC_EN = join(SRC, 'en');
const DST_ROOT = join(__dirname, '..', 'src', 'content', 'docs');
const DST_EN_ROOT = join(DST_ROOT, 'en');

// [category, zh-title, en-title]
const MAPPING = {
	HONEST_TREND_REPORT: ['strategies', 'HonestTrend 完整验证报告', 'HonestTrend full validation report'],
	PHASE_B_FUTURES_SHORT: ['strategies', 'Phase B：期货对冲', 'Phase B: futures hedge'],
	FACTOR_DESIGN: ['strategies', '12 因子设计', '12-factor design'],
	STRATEGY_REPORT: ['strategies', 'Strategy Report v1', 'Strategy Report v1'],
	STRATEGY_REPORT_v2: ['strategies', 'Strategy Report v2', 'Strategy Report v2'],

	HYPEROPT_PYRAMID_TUNING: ['research', 'Hyperopt Pyramid 调优', 'Hyperopt Pyramid tuning'],
	EXPERIMENTS_DCA_AND_PYRAMID: ['research', 'DCA + Pyramid 激进实验', 'DCA + Pyramid aggressive experiments'],
	WALK_FORWARD_FULL_HISTORY: ['research', '8-Regime Walk-Forward', '8-regime Walk-Forward'],
	BACKTEST_RESULTS: ['research', '回测结果汇总', 'Backtest results summary'],
	OPTIMIZATION_PLAN: ['research', 'Phase 3 优化（归档）', 'Phase 3 optimization (archived)'],
	VISUALIZATION_GUIDE: ['research', '可视化指南', 'Visualization guide'],

	DRYRUN_HANDBOOK: ['ops', 'Dry-Run 操作手册', 'Dry-Run operations handbook'],
	GO_LIVE_CHECKLIST: ['ops', 'Go-Live 清单', 'Go-Live checklist'],
	IMPLEMENTATION_PLAN: ['ops', '架构演进（归档）', 'Implementation plan (archived)'],

	RETIRED_STRATEGIES: ['history', '退役策略记录', 'Retired strategies']
};

if (!existsSync(SRC)) {
	console.log('no docs source; skipping');
	process.exit(0);
}

function stripFrontmatter(body) {
	if (body.startsWith('---')) {
		const end = body.indexOf('\n---', 3);
		if (end !== -1) return body.slice(end + 4).replace(/^\n+/, '');
	}
	return body;
}

function writeMd(stem, category, title, body, root) {
	const slug = stem.toLowerCase().replace(/_/g, '-');
	const frontmatter = `---\ntitle: ${JSON.stringify(title)}\ndescription: ${JSON.stringify(stem)}\n---\n\n`;
	const outDir = join(root, category);
	mkdirSync(outDir, { recursive: true });
	writeFileSync(join(outDir, slug + '.md'), frontmatter + body);
}

let copied = 0;
for (const [stem, [category, titleZh, titleEn]] of Object.entries(MAPPING)) {
	// zh (root locale) — required
	const fromZh = join(SRC, stem + '.md');
	if (existsSync(fromZh)) {
		writeMd(stem, category, titleZh, stripFrontmatter(readFileSync(fromZh, 'utf8')), DST_ROOT);
		copied++;
	}
	// en (en locale) — optional; falls back to zh if missing
	const fromEn = join(SRC_EN, stem + '.md');
	if (existsSync(fromEn)) {
		writeMd(stem, category, titleEn, stripFrontmatter(readFileSync(fromEn, 'utf8')), DST_EN_ROOT);
		copied++;
	}
}

// Architecture page (custom, written inline)
const archZh = `---
title: 架构总览
description: 如何组合 Timescale / PostgREST / Supabase / Cloudflare Workers
---

## 数据层

\`\`\`
Local 机器 (bots + DCA + pipelines)
  ├─ feather 文件          — freqtrade 原生 OHLC
  ├─ SQLite                — bot 交易状态
  ├─ JSON 文件              — event_dca_state / walk_forward_history
  └─ sync 脚本每 5 分钟推 →  VPS TimescaleDB

VPS oracle-arm-002 (NixOS)
  ├─ PostgreSQL 18 + TimescaleDB + pg_cron
  ├─ PostgREST   → https://api.panda.qzz.io
  ├─ GoTrue      → https://auth.panda.qzz.io
  ├─ Realtime    → wss://*.realtime.panda.qzz.io
  └─ nginx + ACME (自动 SSL)

Supabase 云 (免费)
  └─ kol_events / dca_log / sentiment / deribit (应用事件)

Cloudflare Workers (免费)
  └─ quant.panda.qzz.io  统一 Worker (SvelteKit Dashboard + /docs Starlight)
\`\`\`

## 为什么这样切？

| 资源 | 用在哪 | 原因 |
|------|-------|------|
| VPS Timescale | OHLC (24M 行) + 回测 (万级 trade) | 重数据，Supabase 放不下 |
| Supabase | 小 JSONB 事件表 | 已在用，有 Realtime / Auth UI 等未来能力 |
| Cloudflare | 前端 + Worker | 全球 CDN + 0 egress |

## 认证

\`auth.panda.qzz.io\` 签发的 JWT 用共享 \`JWT_SECRET\` 直接过 PostgREST RLS —— 登录后访问 \`api.panda.qzz.io\` 时自带身份。未登录默认 \`anon\` 角色，看公开 view。
`;

const archEn = `---
title: Architecture overview
description: How Timescale / PostgREST / Supabase / Cloudflare Workers compose
---

## Data layer

\`\`\`
Local machine (bots + DCA + pipelines)
  ├─ feather files         — freqtrade-native OHLC
  ├─ SQLite                — bot trade state
  ├─ JSON files            — event_dca_state / walk_forward_history
  └─ sync script every 5 min →  VPS TimescaleDB

VPS oracle-arm-002 (NixOS)
  ├─ PostgreSQL 18 + TimescaleDB + pg_cron
  ├─ PostgREST   → https://api.panda.qzz.io
  ├─ GoTrue      → https://auth.panda.qzz.io
  ├─ Realtime    → wss://*.realtime.panda.qzz.io
  └─ nginx + ACME (auto SSL)

Supabase cloud (free tier)
  └─ kol_events / dca_log / sentiment / deribit (app events)

Cloudflare Workers (free tier)
  └─ quant.panda.qzz.io  unified worker (SvelteKit dashboard + /docs Starlight)
\`\`\`

## Why this split?

| Resource | Used for | Reason |
|------|-------|------|
| VPS Timescale | OHLC (24M rows) + backtests (10K+ trades) | Heavy data, Supabase can't hold it |
| Supabase | Small JSONB event tables | Already in use; gives us Realtime / Auth UI room to grow |
| Cloudflare | Frontend + Worker | Global CDN + 0 egress |

## Authentication

JWTs issued by \`auth.panda.qzz.io\` pass PostgREST RLS directly via the shared \`JWT_SECRET\` — once logged in, requests to \`api.panda.qzz.io\` carry identity automatically. Unauthenticated users hit the \`anon\` role and see public views only.
`;

writeFileSync(join(DST_ROOT, 'architecture.md'), archZh);
mkdirSync(DST_EN_ROOT, { recursive: true });
writeFileSync(join(DST_EN_ROOT, 'architecture.md'), archEn);
copied += 2;

console.log(`sync-docs: wrote ${copied} pages (zh + en)`);
