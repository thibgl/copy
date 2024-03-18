<!-- LoginForm.svelte -->
<script lang="ts">
	import { enhance } from '$app/forms';
	import { getModalStore } from '@skeletonlabs/skeleton';
	import { isAuthenticated } from '$lib/stores/auth';
	import { invalidateAll } from '$app/navigation';

	const modalStore = getModalStore();

	let username = '';
	let password = '';
	let creating = false;
	let reset = true;
</script>

<!-- {#if $modalStore[0]} -->
<form
	use:enhance={() => {
		creating = true;
		return async ({ update, result, action, formData, formElement }) => {
			// console.log(result, action, formData, formElement);
			await update({ reset: false });
			reset = false;
			if (result.status == 200) {
				modalStore.close();
				invalidateAll();
				// ! TO CHANGE
				reset = true;
			}
			creating = false;
		};
	}}
	action="/actions?/login"
	method="POST"
	class="form card p-4 w-modal shadow-xl space-y-4"
>
	<div class="form-group">
		<label for="username">Username</label>
		<input type="text" name="username" bind:value={username} class="input" />
	</div>

	<div class="form-group">
		<label for="password">Password</label>
		<input type="password" name="password" bind:value={password} class="input" />
	</div>

	<button type="submit" class="btn variant-filled-primary">Login</button>
</form>

<!-- {/if} -->

<style>
	.form-group {
		margin-bottom: 1rem;
	}

	.form-input {
		/* Tailwind classes for input */
		@apply p-2 border rounded;
	}

	.btn-primary {
		/* Tailwind classes for button */
		@apply bg-blue-500 text-white p-2 rounded;
	}
</style>
