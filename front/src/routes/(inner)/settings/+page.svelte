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
	class="form p-4 space-y-4"
>
	<h2 class="h2">Binance</h2>
	<div class="form-group">
		<label for="username">API Key</label>
		<input type="text" name="APILey" bind:value={username} class="input" />
	</div>

	<div class="form-group">
		<label for="password">Secret Key</label>
		<input type="password" name="secretKey" bind:value={password} class="input" />
	</div>

	<h2 class="h2">Telegram</h2>
	<div class="form-group">
		<label for="username">API Key</label>
		<input type="text" name="APILey" bind:value={username} class="input" />
	</div>

	<div class="form-group">
		<label for="password">Secret Key</label>
		<input type="password" name="secretKey" bind:value={password} class="input" />
	</div>
	<button type="submit" class="btn variant-filled-primary">Save</button>
</form>
