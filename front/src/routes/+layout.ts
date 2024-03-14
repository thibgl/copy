/** @type {import('./$types').LayoutLoad} */

export async function load({ params, fetch }) {
    const users = await fetch("http://localhost:5001/api/data").then((response) => response.json())

    // const topics = await fetch("/topics").then((response) => response.json())

    // return { services: services, websites: websites, topics: topics }
    return { users }
}
