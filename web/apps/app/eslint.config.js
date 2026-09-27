import prettier from 'eslint-config-prettier';
import path from 'node:path';
import { includeIgnoreFile } from '@eslint/compat';
import js from '@eslint/js';
import svelte from 'eslint-plugin-svelte';
import { defineConfig } from 'eslint/config';
import globals from 'globals';
import ts from 'typescript-eslint';
import svelteConfig from './svelte.config.js';

const gitignorePath = path.resolve(import.meta.dirname, '.gitignore');

export default defineConfig(
	includeIgnoreFile(gitignorePath),
	// Generated/vendored assets (Astro docs build, pagefind, plotly reports) — same as .prettierignore.
	{ ignores: ['static/'] },
	js.configs.recommended,
	ts.configs.recommended,
	svelte.configs.recommended,
	prettier,
	svelte.configs.prettier,
	{
		languageOptions: { globals: { ...globals.browser, ...globals.node } },
		rules: {
			// typescript-eslint strongly recommend that you do not use the no-undef lint rule on TypeScript projects.
			// see: https://typescript-eslint.io/troubleshooting/faqs/eslint/#i-get-errors-from-the-no-undef-rule-about-global-variables-not-being-defined-even-though-there-are-no-typescript-errors
			'no-undef': 'off'
		}
	},
	{
		files: ['**/*.svelte', '**/*.svelte.ts', '**/*.svelte.js'],
		languageOptions: {
			parserOptions: {
				projectService: true,
				extraFileExtensions: ['.svelte'],
				parser: ts.parser,
				svelteConfig
			}
		}
	},
	{
		rules: {
			// The pages build their chart data from throwaway Map/Set/Date locals inside
			// $derived.by / plain functions — rebuilt from scratch on every run, never mutated
			// reactively — so the svelte/reactivity wrappers would only add proxy overhead.
			'svelte/prefer-svelte-reactivity': 'off',
			// paths.base is '' and most hrefs are static assets (/docs/, /reports/) or external
			// URLs that resolve()'s typed route ids can't express; programmatic goto() stays checked.
			'svelte/no-navigation-without-resolve': ['error', { ignoreLinks: true }]
		}
	}
);
