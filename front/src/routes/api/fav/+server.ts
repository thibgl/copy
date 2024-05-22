import type { RequestHandler } from './$types'

export const GET: RequestHandler = async ({ cookies, url }) => {
	const binanceId = url.searchParams.get("binanceId")

	try {
		const response = await fetch(`http://localhost:8000/leaders/fav/${binanceId}`, {
			method: 'GET',
			credentials: 'include' // Needed to include cookies in the request
		})

		if (!response.ok) {
			return new Response(`Fav failed: ${await response.text()}`, { status: response.status })
		}

		return new Response('Faved Leader successfully', { status: 200 })
	} catch (err) {
		return new Response('An error occurred while Faving Leader', { status: 500 })
	}
}