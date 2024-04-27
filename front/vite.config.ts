import { purgeCss } from 'vite-plugin-tailwind-purgecss'
import { sveltekit } from '@sveltejs/kit/vite'
import { defineConfig } from 'vite'
import Icons from 'unplugin-icons/vite'

export default defineConfig({
	server: {
		// Listen on all network interfaces
		host: '0.0.0.0',
		port: 5173, // Optional: specify a port number
		// Optional: Enable strict port checking
		strictPort: true
	},
	plugins: [
		sveltekit(),
		Icons({
			compiler: 'svelte',
		}),
		purgeCss()
	]
})