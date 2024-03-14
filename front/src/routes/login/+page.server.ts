/** @type {import('./$types').Actions} */


export const actions = {
    login: async ({ request }) => {
        // event.preventDefault()
        // TODO log the user in
        const formData = await request.formData()

        console.log("Login - Login")
        console.log(formData)

        try {
            const response = await fetch(
                "http://localhost:5001/login",
                {
                    body: formData,
                    method: "POST",
                }
            )

            if (response.status === 200) {
            }

            return await response.json()
        } catch (error) {
            console.log(error)
        }
    },
    // logout: async ({ request }) => {
    //     // event.preventDefault()
    //     // TODO log the user in
    //     const formData = await request.formData()

    //     console.log("Forms - New Topic")
    //     console.log(formData)

    //     try {
    //         const response = await fetch(
    //             "http://localhost:8000/websites/topics/create/?format=json",
    //             {
    //                 body: formData,
    //                 method: "POST",
    //             }
    //         ).then((response) => response.json())
    //         console.log("response")
    //         console.log(response)
    //         return response
    //     } catch (error) {
    //         console.log(error)
    //     }
    // },
}
