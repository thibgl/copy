/** @type {import('./$types').LayoutLoad} */

// export async function load({ params, fetch }) {
// const users = await fetch("http://localhost:8000/api/data").then((response) => response.json())

// const topics = await fetch("/topics").then((response) => response.json())

// return { services: services, websites: websites, topics: topics }
// return { users }
// }


// src/routes/protected/+page.js or +layout.js
// export async function load({ locals }) {
//     // Access session data
//     if (locals.session.user) {
//         // User is authenticated
//         const users = await fetch("http://localhost:8000/api/data").then((response) => response.json())

//         // const topics = await fetch("/topics").then((response) => response.json())

//         // return { services: services, websites: websites, topics: topics }
//         return { users }

//         // return {
//         //     props: {
//         //         // You can pass session data as props
//         //         user: session.user
//         //     }
//         // }
//     } else {
//         // User is not authenticated, handle accordingly
//         return {
//             status: 302,
//         }
//     }
// }
