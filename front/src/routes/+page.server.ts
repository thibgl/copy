/** @type {import('./$types').LayoutLoad} */

// src/routes/protected/+page.js or +layout.js
export async function load({ fetch, cookies }) {
    // Access session data
    const authToken = cookies.get('AuthorizationToken')

    if (authToken) {
        // User is authenticated
        const users = await fetch("http://localhost:8000/api/data").then((response) => response.json())

        return { isAuthenticated: true, users }

        // return {
        //     props: {
        //         // You can pass session data as props
        //         user: session.user
        //     }
        // }
        // } else {
        //     // User is not authenticated, handle accordingly
        //     return {
        //         status: 302,
        //     }
    }

    return { isAuthenticated: false }
}
