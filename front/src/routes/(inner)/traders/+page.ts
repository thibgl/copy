import type { PageLoad } from './$types'
import { writable } from 'svelte/store'
// src/routes/protected/+page.js or +layout.js

export const load: PageLoad = async ({ data }) => {
    // console.log(data.user.leaders.WEIGHT)
    // await parent().then((data) => console.log(data.user.leaders))
    return {
        ...data,
        userLeaders: writable(data.user.leaders.WEIGHT),
        userFavorites: writable(data.user.account.fav_leaders)
    }
}