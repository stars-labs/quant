// See https://svelte.dev/docs/kit/types#app.d.ts for these interfaces.
import type { Lang } from '$lib/i18n';

declare global {
	namespace App {
		// interface Error {}
		interface Locals {
			/** Active UI language, resolved from the `lang` cookie by hooks.server.ts. */
			lang: Lang;
		}
		interface PageData {
			lang: Lang;
		}
		// interface PageState {}
	}
}

export {};
