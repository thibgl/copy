import type { Handle } from '@sveltejs/kit'
import { parse } from 'cookie'

export const handle: Handle = async ({ event, resolve }) => {
    const cookies = parse(event.request.headers.get('cookie') || '')
    const authToken = cookies['AuthorizationToken']
    // Check for the existence of the JWT in the cookies
    if (authToken) {
        try {
            // Attempt to fetch user data using the JWT
            const response = await fetch('http://localhost:8000/api/user', {
                method: 'GET',
                headers: {
                    'Authorization': authToken,
                },
                credentials: 'include', // Ensures cookies are included with the request
            })

            if (response.ok) {
                // If the request is successful, set the user data in locals for use in endpoints/load functions
                const userData = await response.json()
                event.locals.user = userData
            } else {
                console.error('Failed to verify user')
                // Handle failure (e.g., by clearing invalid tokens or redirecting to a login page)
            }
        } catch (error) {
            console.error('Error fetching user data:', error)
            // Handle error (e.g., logging, cleaning up, etc.)
        }
    }

    // Continue with the request handling
    return await resolve(event)
}
