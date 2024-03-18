import type { RequestHandler } from './$types'

export const GET: RequestHandler = async ({ cookies }) => {
	try {
		const response = await fetch('http://localhost:8000/api/logout', {
			method: 'GET', // or POST if that's how your endpoint is configured
			credentials: 'include' // Needed to include cookies in the request
		})

		if (!response.ok) {
			// Handle the error
			console.error('Logout failed')
			return new Response(`Logout failed: ${await response.text()}`, { status: response.status })
		}

		// Assuming your Flask backend clears the session cookie,
		// you might not need to manually delete the cookie here
		cookies.delete("AuthorizationToken", { path: '/' })

		// Return a 200 response
		return new Response('Logged out successfully', { status: 200 })
	} catch (err) {
		console.error('An error occurred while logging out', err)
		return new Response('An error occurred while logging out', { status: 500 })
	}
}
