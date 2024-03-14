<!-- LoginForm.svelte -->
<script lang="ts">
	import { enhance } from '$app/forms';

	let username = '';
	let password = '';
	let creating = false;
	let reset = true;
</script>

<form
	use:enhance={() => {
		creating = true;
		return async ({ update, result, action, formData, formElement }) => {
			console.log(result, action, formData, formElement);
			await update({ reset: false });
			reset = false;
			if (result.data.status == 'success') {
				reset = true;
			}
			creating = false;
		};
	}}
	action="/login?/login"
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
