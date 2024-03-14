/** @type {import('./$types').Actions} */

export const actions = {
    create: async ({ request }) => {
        // event.preventDefault()
        // TODO log the user in
        const formData = await request.formData()

        console.log("FORM")
        console.log(formData)

        // try {
        //     const response = await fetch(
        //         "http://localhost:8000/scraper/topic?format=json",
        //         {
        //             body: formData,
        //             method: "POST",
        //         }
        //     ).then((response) => response.json())
        //     console.log("response")
        //     console.log(response)
        //     return response
        // } catch (error) {
        //     console.log(error)
        // }
    },
}
