// src/lib/store.js
import { writable } from 'svelte/store'

export const isAuthenticated = writable(false)
