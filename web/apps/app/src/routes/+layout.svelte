<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';
	import { ModeWatcher } from 'mode-watcher';
	import { browser } from '$app/environment';
	import { page } from '$app/stores';
	import { afterNavigate } from '$app/navigation';
	import Topbar from '$lib/components/topbar.svelte';
	import Sidebar from '$lib/components/sidebar.svelte';
	import { track } from '$lib/track';

	let { children } = $props();
	let sidebarOpen = $state(false);
	$effect(() => {
		document.documentElement.lang = $page.data.lang === 'zh' ? 'zh-CN' : 'en';
	});

	// Desktop sidebar collapse (icon rail), persisted per browser.
	const COLLAPSE_KEY = 'bdv:sidebar-collapsed';
	let sidebarCollapsed = $state(browser && localStorage.getItem(COLLAPSE_KEY) === '1');

	function toggleSidebar() {
		// One topbar button, two behaviors: drawer on mobile, collapse on desktop.
		if (window.matchMedia('(min-width: 48rem)').matches) {
			sidebarCollapsed = !sidebarCollapsed;
			localStorage.setItem(COLLAPSE_KEY, sidebarCollapsed ? '1' : '0');
		} else {
			sidebarOpen = !sidebarOpen;
		}
	}

	// First-party analytics: one page_view per navigation (de-duped in track()).
	afterNavigate((nav) => track('page_view', nav.to?.url.pathname));
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>
<ModeWatcher defaultMode="dark" />
<div
	class="bdv-app-bg min-h-screen text-foreground transition-[grid-template-columns] duration-200 md:grid {sidebarCollapsed
		? 'md:grid-cols-[64px_1fr]'
		: 'md:grid-cols-[240px_1fr]'}"
>
	<Sidebar
		bind:open={sidebarOpen}
		collapsed={sidebarCollapsed}
		onclose={() => (sidebarOpen = false)}
	/>
	<div class="flex min-w-0 flex-col">
		<Topbar onmenuToggle={toggleSidebar} />
		{@render children()}
	</div>
</div>
