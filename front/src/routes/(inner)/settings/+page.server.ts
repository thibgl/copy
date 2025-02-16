/** @type {import('./$types').PageServerLoad} */

// src/routes/protected/+page.js or +layout.js
export async function load({ fetch, cookies }) {
    // Access session data
    const settings = fetch("http://localhost:8000/api/settings").then((response) => response.json())

    return { settings }
}
