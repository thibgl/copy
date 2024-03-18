/** @type {import('./$types').Actions} */

import { fail } from '@sveltejs/kit'

export const actions = {
    login: async ({ cookies, request }) => {
        const formData = Object.fromEntries(await request.formData())

        // Directly use formData with URLSearchParams
        const formBody = new URLSearchParams(formData as any)


        try {
            const response = await fetch('http://localhost:8000/api/token', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: formBody,
            })

            if (!response.ok) {
                const { detail } = await response.json()
                return fail(401, { error: detail || 'Login failed' })
            }

            const { access_token } = await response.json()
            // Here you should decide how to store the access_token, e.g., in cookies or localStorage
            cookies.set('AuthorizationToken', `Bearer ${access_token}`, { path: '/' })

            return { success: true }

        } catch (error) {
            return fail(500, { error: 'An error occurred while logging in' })
        }
    },
    logout: async ({ cookies }) => {
        try {
            const response = await fetch('http://localhost:8000/api/logout', {
                method: 'GET', // or POST if that's how your endpoint is configured
                credentials: 'include' // Needed to include cookies in the request
            })

            if (!response.ok) {
                // Handle the error
                console.error('Logout failed')
            }

            // Assuming your Flask backend clears the session cookie,
            // you might not need to manually delete the cookie here
            cookies.delete("AuthorizationToken", { path: '/' })

            // throw redirect(302, "/user-auth")
        } catch (error) {
            console.error('An error occurred while logging out')
        }
    },
}
