import type { PageServerLoad } from './$types'

// src/routes/protected/+page.js or +layout.js
export const load: PageServerLoad = async ({ fetch, parent }) => {
    // Access session data
    const data = await parent()
    const leaders = await fetch("http://localhost:8000/leaders/all").then((response) => response.json())
    // console.log(leaders)
    return {
        ...data,
        leaders: leaders.data
    }
}

export const actions = {
    // addTrader: async ({ cookies }) => {
    //     try {
    //         const response = await fetch('http://localhost:8000/api/logout', {
    //             method: 'GET', // or POST if that's how your endpoint is configured
    //             credentials: 'include' // Needed to include cookies in the request
    //         })

    //         if (!response.ok) {
    //             // Handle the error
    //             console.error('Logout failed')
    //         }

    //         // Assuming your Flask backend clears the session cookie,
    //         // you might not need to manually delete the cookie here
    //         cookies.delete("AuthorizationToken", { path: '/' })

    //         // throw redirect(302, "/user-auth")
    //     } catch (error) {
    //         console.error('An error occurred while logging out')
    //     }
    // },
    unfollow: async ({ cookies, url }) => {
        console.log('FORM ACTION REQUEST')
        const binanceId = url.searchParams.get("binanceId")
        console.log(binanceId)
        // try {
        //     const response = await fetch(`http://localhost:8000/leaders/unfollow/`, {
        //         method: 'GET', // or POST if that's how your endpoint is configured
        //         credentials: 'include' // Needed to include cookies in the request
        //     })

        //     if (!response.ok) {
        //         // Handle the error
        //         console.error('Logout failed')
        //     }

        //     // Assuming your Flask backend clears the session cookie,
        //     // you might not need to manually delete the cookie here
        //     // cookies.delete("AuthorizationToken", { path: '/' })

        //     // throw redirect(302, "/user-auth")
        // } catch (error) {
        //     console.error('An error occurred while logging out')
        // }
    },
}
