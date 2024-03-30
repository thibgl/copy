/** @type {import('./$types').PageServerLoad} */

// src/routes/protected/+page.js or +layout.js
export async function load({ fetch, cookies }) {
    // Access session data
    const leaders = await fetch("http://localhost:8000/leaders/all").then((response) => response.json())
    // console.log(leaders)
    return { leaders: leaders.data }
}
