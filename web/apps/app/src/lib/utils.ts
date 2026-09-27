import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

export function fmtUSD(n: number | null | undefined): string {
	if (n == null) return '—';
	return '$' + Math.round(n).toLocaleString();
}
// Coin prices: >= $1 keeps cents (commas from $1,000); sub-dollar coins show 4 significant digits
// so PEPE (~$0.00001) never reads $0.00.
export function fmtPrice(v: number | null | undefined): string {
	if (v == null) return '—';
	return (
		'$' +
		(Math.abs(v) >= 1 || v === 0
			? v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
			: v.toLocaleString('en-US', { minimumSignificantDigits: 4, maximumSignificantDigits: 4 }))
	);
}
export function fmtPct(n: number | null | undefined, digits = 2): string {
	if (n == null) return '—';
	return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`;
}
export function fmtTime(iso: string | null | undefined): string {
	if (!iso) return '—';
	return iso.replace('T', ' ').slice(0, 16);
}
export function agoText(iso: string): string {
	if (!iso) return '';
	const diff = (Date.now() - new Date(iso).getTime()) / 60_000;
	if (diff < 60) return `${Math.floor(diff)}m ago`;
	if (diff < 1440) return `${Math.floor(diff / 60)}h ago`;
	return `${Math.floor(diff / 1440)}d ago`;
}
