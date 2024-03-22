/** @type {import('./$types').PageServerLoad} */

// src/routes/protected/+page.js or +layout.js
export async function load({ fetch, cookies }) {
    // Access session data
    const leads = await fetch("http://localhost:8000/api/leads").then((response) => response.json())
    console.log(leads)
    return { leads }
}
