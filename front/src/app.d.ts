/// <reference types="@sveltejs/kit" />

import type { User } from "$lib/types/auth" // Adjust the import path if your file structure is different

// See https://kit.svelte.dev/docs#typescript
// for information about these interfaces
declare global {
	declare namespace App {
		interface Locals {
			user?: User
			isAuthenticated: boolean = false
		}

		interface Platform { }

		interface Session { }

		interface Stuff { }
	}
}