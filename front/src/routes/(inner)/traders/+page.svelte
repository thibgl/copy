<script lang="ts">
	import { page } from '$app/stores';
	import type { PageData } from './$types';
	import { Avatar, ProgressRadial } from '@skeletonlabs/skeleton';
	import { writable } from 'svelte/store';

	export let data: PageData;
	const userLeaders = data.userLeaders;
	$: console.log($userLeaders);
	// const test = writable({});
	// console.log(typeof test);
	const tableArr = [{ name: 'test', position: 3, symbol: 'XXX', weight: 32 }];
	const totalWeight = 42;

	import TraderIcon from '~icons/ph/user-plus';
	import FavoriteIcon from '~icons/ph/star';
	import CopyIcon from '~icons/ph/lightning';
	import CopyEnabledIcon from '~icons/ph/lightning-fill';

	// console.log($page.data.leaders);

	// Assuming you get this initial data from somewhere, maybe load function
	// console.log($userLeaders);

	async function followLeader(leader) {
		const response = await fetch(`api/unfollow?binanceId=${leader.detail.leadPortfolioId}`);
		if (response.ok) {
			$userLeaders[leader._id] = 1;
		} else {
			console.error('Failed to unfollow leader');
		}
	}

	async function unfollowLeader(leader) {
		const response = await fetch(`api/unfollow?binanceId=${leader.detail.leadPortfolioId}`);
		if (response.ok) {
			delete $userLeaders[leader._id];
			$userLeaders = $userLeaders;
		} else {
			console.error('Failed to unfollow leader');
		}
	}
</script>

<div class="flex flex-wrap gap-3 justify-center">
	<form action="/actions?/addTrader" method="POST" class="card w-96 aspect-video">
		<header class="card-header flex justify-between items-center">
			<h2>Add a Trader</h2>
		</header>
		<section class="p-4 flex flex-col h-full justify-center items-center space-y-3">
			<TraderIcon class="w-16 h-16" />
			<input type="text" placeholder="Portfolio id" class="input" />
		</section>
		<footer class="card-footer">
			<btn class="btn variant-outline-primary">Submit</btn>
		</footer>
	</form>
	{#each $page.data.leaders as leader}
		<div class="card w-96 aspect-video">
			<header class="card-header flex justify-between items-center">
				<a
					class="flex space-x-3 items-center"
					href={'https://www.binance.com/en/copy-trading/lead-details/' +
						leader.detail.leadPortfolioId}
					target="_blank"
				>
					<!-- <Avatar src={lead.userPhotoUrl} fallback="src/lib/images/user.png" /> -->
					<img
						class="w-12 h-12 rounded-full bg-gray-500"
						src={leader.detail.avatarUrl.length > 0
							? leader.detail.avatarUrl
							: 'src/lib/images/user.png'}
						alt="user avatar"
					/>
					<div class="flex flex-col items-start">
						<p>{leader.detail.nickname}</p>
						<p>{leader.detail.leadPortfolioId}</p>
					</div>
				</a>

				<div class="flex space-x-3">
					<FavoriteIcon class="w-8 h-8" />
					{#if Object.keys($userLeaders).includes(leader._id)}
						<button on:click={() => unfollowLeader(leader)}>
							<CopyEnabledIcon class="w-8 h-8 text-warning-500" />
						</button>
					{:else}
						<button on:click={() => followLeader(leader)}>
							<CopyIcon class="w-8 h-8" />
						</button>
					{/if}
				</div>
			</header>
			<section class="p-4"></section>
			<footer class="card-footer">
				<ProgressRadial width="w-16" font={128} value={95}>95</ProgressRadial>
			</footer>
		</div>
	{/each}
</div>
