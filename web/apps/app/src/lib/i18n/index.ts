// Hand-rolled i18n: cookie-based, no library. The active `lang` is resolved
// server-side in hooks.server.ts from the `lang` cookie, then passed through
// the root layout's page data. The `t()` helper returns a string from the
// active bundle, falling back to the zh bundle if a key is missing (so new
// keys ship before translation is done, without crashing).

import zh from './zh';
import en from './en';

export type Lang = 'zh' | 'en';
export const LANGS: Lang[] = ['zh', 'en'];
export const LANG_LABELS: Record<Lang, string> = {
	zh: '简体中文',
	en: 'English'
};

const BUNDLES: Record<Lang, Record<string, string>> = { zh, en };

export function isLang(v: unknown): v is Lang {
	return v === 'zh' || v === 'en';
}

export function normalizeLang(v: string | null | undefined): Lang {
	if (v === 'en') return 'en';
	return 'zh';
}

/** Active bundle by lang. Always returns one of the maps, never null. */
export function bundle(lang: Lang): Record<string, string> {
	return BUNDLES[lang] ?? BUNDLES.zh;
}

/** Pick a string key. Missing keys render as `[key]` so mistakes are visible. */
export function t(lang: Lang, key: string): string {
	const v = BUNDLES[lang]?.[key] ?? BUNDLES.zh[key];
	return v ?? `[${key}]`;
}

/**
 * Pick a localized {zh, en} field. Useful for catalog data (e.g. strategies.ts
 * taglines) that we store inline rather than in message bundles. Falls back to
 * zh if the requested lang is missing.
 */
export function pick<T>(field: { zh: T; en?: T } | null | undefined, lang: Lang): T | null {
	if (!field) return null;
	if (lang === 'en' && field.en != null) return field.en;
	return field.zh;
}
