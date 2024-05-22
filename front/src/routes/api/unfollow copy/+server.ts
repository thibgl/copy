import type { RequestHandler } from './$types'

export const GET: RequestHandler = async ({ cookies, url }) => {
	const binanceId = url.searchParams.get("binanceId")

	try {
		const response = await fetch(`http://localhost:8000/leaders/unfav/${binanceId}`, {
			method: 'GET', // or POST if that's how your endpoint is configured
			credentials: 'include' // Needed to include cookies in the request
		})

		if (!response.ok) {
			// Handle the error
			return new Response(`Unfav failed: ${await response.text()}`, { status: response.status })
		}

		// 	// Assuming your Flask backend clears the session cookie,
		// 	// you might not need to manually delete the cookie here
		// 	cookies.delete("AuthorizationToken", { path: '/' })

		// 	// Return a 200 response
		return new Response('Unfaved Leader successfully', { status: 200 })
	} catch (err) {
		// console.error('An error occurred while Unfollowing Leader', err)
		return new Response('An error occurred while Unfaving Leader', { status: 500 })
	}
}