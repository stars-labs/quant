<script lang="ts">
	import { page } from '$app/stores';
	import { t, type Lang } from '$lib/i18n';
	import { AFFILIATE } from '$lib/config';

	const lang = $derived<Lang>($page.data.lang ?? 'zh');
</script>

<section class="mb-8 rounded-xl border bg-card p-5">
	<div class="flex flex-wrap items-start justify-between gap-4">
		<div class="max-w-2xl min-w-0">
			<h2 class="text-sm font-semibold tracking-wide text-muted-foreground uppercase">
				{t(lang, 'trust.heading')}
			</h2>
			<p class="mt-2 text-base text-foreground">{t(lang, 'trust.body')}</p>
		</div>
		<div class="flex flex-wrap gap-2 text-xs">
			<a
				href="/docs/architecture/"
				data-sveltekit-reload
				class="rounded-md border border-border bg-secondary px-3 py-2 text-secondary-foreground hover:bg-accent"
			>
				🧭 {t(lang, 'trust.architecture')}
			</a>
			<a
				href="/dca"
				class="rounded-md border border-border bg-secondary px-3 py-2 text-secondary-foreground hover:bg-accent"
			>
				💰 {t(lang, 'trust.dca')}
			</a>
			<a
				href={AFFILIATE.GITHUB_URL}
				target="_blank"
				rel="noopener"
				class="rounded-md border border-border bg-secondary px-3 py-2 text-secondary-foreground hover:bg-accent"
			>
				⚙️ GitHub ↗
			</a>
		</div>
	</div>
</section>
