<script lang="ts">
	// import Chart from '$lib/components/Chart.svelte';
	import { invalidateAll } from '$app/navigation';
	import { page } from '$app/stores';
	import '../app.postcss';
	import {
		AppShell,
		AppBar,
		Modal,
		initializeStores,
		AppRail,
		AppRailTile,
		AppRailAnchor,
		ProgressRadial,
		prefersReducedMotionStore,
		getModalStore
	} from '@skeletonlabs/skeleton';
	import type { ModalSettings, ModalComponent, ModalStore } from '@skeletonlabs/skeleton';
	// Floating UI for Popups
	import { computePosition, autoUpdate, flip, shift, offset, arrow } from '@floating-ui/dom';
	import { storePopup } from '@skeletonlabs/skeleton';
	storePopup.set({ computePosition, autoUpdate, flip, shift, offset, arrow });

	import LoginForm from '$lib/modals/login/LoginForm.svelte';
	initializeStores();

	const modalComponentRegistry: Record<string, ModalComponent> = {
		Login: { ref: LoginForm }
	};

	const modalStore = getModalStore();

	const loginModal: ModalSettings = {
		type: 'component',
		component: 'Login',
		title: 'Log-in',
		body: '',
		meta: {}
		// meta: { categories: data.categories, category: data.category.slug }
	};

	import StopIcon from '~icons/ph/stop';
	import PlayIcon from '~icons/ph/play';
	import HouseIcon from '~icons/ph/house-line';
	import TradersIcon from '~icons/ph/users';
	import TraderIcon from '~icons/ph/user';
	import LogIcon from '~icons/ph/clock-counter-clockwise';
	import LogoutIcon from '~icons/ph/eject';
	import SettingsIcon from '~icons/ph/gear';
	import BalanceIcon from '~icons/ph/piggy-bank';
	import FavoriteIcon from '~icons/ph/star';
	import CopyIcon from '~icons/ph/lightning';

	let currentTile: number = 0;
</script>

<!-- App Shell -->
<AppShell>
	<svelte:fragment slot="header">
		<!-- App Bar -->
		<AppBar>
			<svelte:fragment slot="lead">
				<h1 class="text-3xl">
					<strong
						class="bg-gradient-to-br from-primary-500 to-secondary-500 bg-clip-text text-transparent box-decoration-clone"
						>CopyTrader</strong
					>
				</h1>
			</svelte:fragment>
			<svelte:fragment slot="trail">
				{#if $page.data.isAuthenticated}
					<button class="btn variant-filled-secondary"><BalanceIcon /><span>1000 USDT</span></button
					>
					<button class="btn variant-ghost-primary"><StopIcon /></button>
				{:else}
					<button
						on:click={() => modalStore.trigger(loginModal)}
						type="button"
						class="btn bg-gradient-to-br variant-gradient-primary-secondary">Log-in</button
					>
				{/if}
			</svelte:fragment>
		</AppBar>
	</svelte:fragment>
	<svelte:fragment slot="sidebarLeft">
		{#if $page.data.isAuthenticated}
			<AppRail width="w-full">
				<!-- --- -->
				<AppRailTile bind:group={currentTile} name="tile-1" value={0} title="tile-1">
					<svelte:fragment slot="lead"><HouseIcon class="w-full h-8" /></svelte:fragment>
					<span>Home</span>
				</AppRailTile>
				<AppRailTile bind:group={currentTile} name="tile-2" value={1} title="tile-2">
					<svelte:fragment slot="lead"><TradersIcon class="w-full h-8" /></svelte:fragment>
					<span>Traders</span>
				</AppRailTile>
				<AppRailTile bind:group={currentTile} name="tile-3" value={2} title="tile-3">
					<svelte:fragment slot="lead"><LogIcon class="w-full h-8" /></svelte:fragment>
					<span>Logs</span>
				</AppRailTile>
				<!-- --- -->
				<svelte:fragment slot="trail">
					<AppRailTile bind:group={currentTile} name="tile-4" value={3} title="tile-4">
						<svelte:fragment slot="lead"><SettingsIcon class="w-full h-8" /></svelte:fragment>
						<span>Settings</span>
					</AppRailTile>

					<button
						type="button"
						class="btn !bg-transparent aspect-square flex flex-col items-center space-x-0"
						on:click={async () => {
							await fetch('/api/logout');
							invalidateAll();
						}}
						><LogoutIcon class="w-full h-8" /><span class="text-xs font-bold">Sign-out</span
						></button
					>
				</svelte:fragment>
			</AppRail>
		{/if}
	</svelte:fragment>

	<!-- Page Route Content -->
	<div class="container h-full mx-auto flex justify-center items-center">
		<div class="space-y-10 text-center flex flex-col items-center">
			<!-- Animated Logo -->
			{#if $page.data.isAuthenticated}
				{#if currentTile === 0}
					<!-- <Chart /> -->
					Tile 1
				{/if}
				{#if currentTile === 1}
					<div class="card">
						<header class="card-header flex">
							<TraderIcon class="w-8 h-8" />
							<FavoriteIcon class="w-8 h-8" />
							<CopyIcon class="w-8 h-8" />
						</header>
						<section class="p-4">(content)</section>
						<footer class="card-footer">
							<ProgressRadial width="w-16" font={128} value={95}>95</ProgressRadial>
						</footer>
					</div>
				{/if}
				{#if currentTile === 2}
					Tile 3
				{/if}
				{#if currentTile === 3}
					Settings
				{/if}
			{:else}
				<figure>
					<section class="img-bg" />
					<svg
						class="fill-token -scale-x-[100%]"
						xmlns="http://www.w3.org/2000/svg"
						viewBox="0 0 200 200"
					>
						<path
							fill-rule="evenodd"
							d="M98.77 50.95c25.1 0 46.54 8.7 61.86 23a41.34 41.34 0 0 0 5.19-1.93c4.35-2.02 10.06-6.17 17.13-12.43-1.15 10.91-2.38 18.93-3.7 24.04-.7 2.75-1.8 6.08-3.3 10a80.04 80.04 0 0 1 8.42 23.33c6.04 30.3-4.3 43.7-28.33 51.18.18.9.32 1.87.42 2.9.86 8.87-3.62 23.19-9 23.19-3.54 0-5.84-4.93-8.3-12.13-.78 8.34-4.58 17.9-8.98 17.9-4.73 0-7.25-8.84-10.93-20.13a214 214 0 0 1-.64 2.93l-.16.71-.16.71-.17.71c-1.84 7.58-4.46 15.07-8.5 15.07-5.06 0-2.29-15.9-10.8-22.63-43.14 2.36-79.43-13.6-79.43-59.62 0-8.48 2-16.76 5.69-24.45a93.72 93.72 0 0 1-1.77-3.68c-2.87-6.32-6.3-15.88-10.31-28.7 10.26 7.66 18.12 12.22 23.6 13.68.5.14 1.02.26 1.57.36 14.36-14.44 35.88-24.01 60.6-24.01Zm-9.99 62.3c-14.57 0-26.39 11.45-26.39 25.58 0 14.14 11.82 25.6 26.39 25.6s26.39-11.46 26.39-25.6c0-13.99-11.58-25.35-25.95-25.58Zm37.45 31.95c-4.4 0-6.73 9.4-6.73 13.62 0 3.3 1.1 5.12 2.9 5.45 4.39.4 3.05-5.97 5.23-5.97 1.06 0 2.2 1.35 3.34 2.73l.34.42c1.25 1.52 2.5 2.93 3.64 2.49 2.7-1.61 1.67-5.12.74-7.88-3.3-6.96-5.05-10.86-9.46-10.86Zm-36.85-28.45c12.57 0 22.76 9.78 22.76 21.85 0 12.07-10.2 21.85-22.76 21.85-.77 0-1.53-.04-2.29-.11 11.5-1.1 20.46-10.42 20.46-21.74 0-11.32-8.97-20.63-20.46-21.74.76-.07 1.52-.1 2.3-.1Zm65.54-5c-10.04 0-18.18 10.06-18.18 22.47 0 12.4 8.14 22.47 18.18 22.47s18.18-10.06 18.18-22.47c0-12.41-8.14-22.48-18.18-22.48Zm.6 3.62c8.38 0 15.16 8.4 15.16 18.74 0 10.35-6.78 18.74-15.16 18.74-.77 0-1.54-.07-2.28-.21 7.3-1.36 12.89-9.14 12.89-18.53 0-9.4-5.6-17.17-12.89-18.53.74-.14 1.5-.2 2.28-.2Zm3.34-72.27.12.07c.58.38.75 1.16.37 1.74l-2.99 4.6c-.35.55-1.05.73-1.61.44l-.12-.07a1.26 1.26 0 0 1-.37-1.74l2.98-4.6a1.26 1.26 0 0 1 1.62-.44ZM39.66 42l.08.1 2.76 3.93a1.26 1.26 0 0 1-2.06 1.45l-2.76-3.94A1.26 1.26 0 0 1 39.66 42Zm63.28-42 2.85 24.13 10.62-11.94.28 29.72-2.1-.47a77.8 77.8 0 0 0-16.72-2.04c-4.96 0-9.61.67-13.96 2l-2.34.73L83.5 4.96l9.72 18.37L102.94 0Zm-1.87 13.39-7.5 17.96-7.3-13.8-1.03 19.93.22-.06a51.56 51.56 0 0 1 12.1-1.45h.31c4.58 0 9.58.54 15 1.61l.35.07-.15-16.54-9.79 11-2.21-18.72Zm38.86 19.23c.67.2 1.05.89.86 1.56l-.38 1.32c-.17.62-.8 1-1.42.89l-.13-.03a1.26 1.26 0 0 1-.86-1.56l.38-1.32c.19-.66.88-1.05 1.55-.86ZM63.95 31.1l.05.12.7 2.17a1.26 1.26 0 0 1-2.34.9l-.04-.12-.71-2.17a1.26 1.26 0 0 1 2.34-.9Z"
						/>
					</svg>
				</figure>
			{/if}
			<!-- / -->
		</div>
	</div>
</AppShell>

<!-- Modals -->
<Modal components={modalComponentRegistry} />

<style lang="postcss">
	figure {
		@apply flex relative flex-col;
	}
	figure svg,
	.img-bg {
		@apply w-64 h-64 md:w-80 md:h-80;
	}
	.img-bg {
		@apply absolute z-[-1] rounded-full blur-[50px] transition-all;
		animation:
			pulse 5s cubic-bezier(0, 0, 0, 0.5) infinite,
			glow 5s linear infinite;
	}
	@keyframes glow {
		0% {
			@apply bg-primary-400/50;
		}
		33% {
			@apply bg-secondary-400/50;
		}
		66% {
			@apply bg-tertiary-400/50;
		}
		100% {
			@apply bg-primary-400/50;
		}
	}
	@keyframes pulse {
		50% {
			transform: scale(1.5);
		}
	}
</style>
