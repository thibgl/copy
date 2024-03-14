<script lang="ts">
	import '../app.postcss';
	import {
		AppShell,
		AppBar,
		Modal,
		initializeStores,
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
	export let data;
	console.log(data);
</script>

<!-- App Shell -->
<AppShell>
	<svelte:fragment slot="header">
		<!-- App Bar -->
		<AppBar>
			<svelte:fragment slot="lead">
				<strong class="text-xl uppercase">Skeleton</strong>
			</svelte:fragment>
			<svelte:fragment slot="trail">
				<button
					on:click={() => modalStore.trigger(loginModal)}
					type="button"
					class="btn variant-filled">Log-in</button
				>
			</svelte:fragment>
		</AppBar>
	</svelte:fragment>
	<!-- Page Route Content -->
	<slot />
</AppShell>

<!-- Modals -->
<Modal components={modalComponentRegistry} />
