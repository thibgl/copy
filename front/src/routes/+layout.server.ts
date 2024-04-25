/** @type {import('./$types').LayoutServerLoad} */

// src/routes/protected/+page.js or +layout.js
export async function load({ fetch, cookies, locals }) {
    return { "user": locals.user }
    // Access session data
    // const authToken = cookies.get('AuthorizationToken')

    // if (authToken) {
    //     const user = await fetch("http://localhost:8000/auth/user").then((response) => response.json())
    // User is authenticated
    // const users = await fetch("http://localhost:8000/api/data").then((response) => response.json())
    // // const binance = await fetch("http://localhost:8000/api/binance/snapshot")
    // return { isAuthenticated: true, user }

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
    // } else {
    //     await fetch('http://localhost:8000/auth/user')
    // }

    // return { isAuthenticated: false }
}
