// App navigation: one table for the sidebar entries AND the topbar page label, so every page
// name goes through i18n (each language rendering stays single-language — no English route
// slug in the zh UI).
import type { ComponentType } from 'svelte';
import {
	Home,
	Compass,
	Radio,
	Cpu,
	Boxes,
	Coins,
	Globe,
	LineChart,
	Layers,
	Archive,
	Wallet,
	CandlestickChart,
	Repeat2,
	Sparkles,
	Network,
	FileText,
	FlaskConical,
	Skull,
	Trophy
} from 'lucide-svelte';

export type NavItem = {
	href: string;
	labelKey: string;
	icon?: ComponentType;
	external?: boolean;
};

// `nav.live` deliberately has no icon — the sidebar draws its dot as a connection-status
// indicator, which would conflict with a static glyph.
export const PRIMARY_NAV: NavItem[] = [
	{ href: '/', labelKey: 'nav.home', icon: Home },
	{ href: '/start', labelKey: 'nav.start', icon: Compass },
	{ href: '/record', labelKey: 'nav.record', icon: Trophy },
	{ href: '/live', labelKey: 'nav.live' },
	{ href: '/nautilus', labelKey: 'nav.nautilus', icon: Cpu },
	{ href: '/signals', labelKey: 'nav.signals', icon: Radio },
	{ href: '/market', labelKey: 'nav.market', icon: LineChart },
	{ href: '/semis', labelKey: 'nav.semis', icon: Boxes },
	{ href: '/research/ai-semis-liquidity', labelKey: 'nav.aiSemisResearch', icon: FileText },
	{ href: '/commodities', labelKey: 'nav.commodities', icon: Coins },
	{ href: '/globe', labelKey: 'nav.globe', icon: Globe },
	{ href: '/strategies', labelKey: 'nav.strategies', icon: Layers },
	{ href: '/backtest', labelKey: 'nav.backtest', icon: FlaskConical },
	{ href: '/quant-lab', labelKey: 'nav.quantLab', icon: Sparkles },
	{ href: '/archive', labelKey: 'nav.archive', icon: Archive }
];

// The sidebar appends the Docs link (a static site with a per-language href).
export const SECONDARY_NAV: NavItem[] = [
	{ href: '/dca', labelKey: 'nav.dca', icon: Wallet },
	{ href: '/chart', labelKey: 'nav.chart', icon: CandlestickChart },
	{ href: '/wf', labelKey: 'nav.wf', icon: Repeat2 },
	{ href: '/hyperopt', labelKey: 'nav.hyperopt', icon: Sparkles },
	{ href: '/factors', labelKey: 'nav.factors', icon: Network },
	{ href: '/reports', labelKey: 'nav.reports', icon: FileText },
	{ href: '/graveyard', labelKey: 'nav.graveyard', icon: Skull }
];

export function isActive(href: string, pathname: string): boolean {
	if (href === '/') return pathname === '/';
	return pathname === href || pathname.startsWith(href + '/');
}

/** i18n key of the nav entry that owns `pathname` (e.g. /strategies/x → nav.strategies), or
 * null for pages outside the nav (login, auth callback). */
export function navLabelKey(pathname: string): string | null {
	return (
		[...PRIMARY_NAV, ...SECONDARY_NAV].find((n) => isActive(n.href, pathname))?.labelKey ?? null
	);
}
