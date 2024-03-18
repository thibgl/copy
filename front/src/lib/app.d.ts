// src/lib/app.d.ts or src/app.d.ts
/// <reference types="@sveltejs/kit" />

declare namespace App {
    interface Locals {
        session: import('$lib/types').SessionData // Use your SessionData type here
    }
}
