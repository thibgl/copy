<script lang="ts">
	import { page } from '$app/stores';
	import type { PageData } from './$types';
	import { Avatar, ProgressRadial } from '@skeletonlabs/skeleton';
	import { writable } from 'svelte/store';

	export let data: PageData;
	const userLeaders = data.userLeaders;
	const userFavorites = data.userFavorites;
	$: console.log($userFavorites);
	// const test = writable({});
	// console.log(typeof test);
	const tableArr = [{ name: 'test', position: 3, symbol: 'XXX', weight: 32 }];
	const totalWeight = 42;

	import TraderIcon from '~icons/ph/user-plus';
	import FavoriteIcon from '~icons/ph/star';
	import FavoriteEnabledIcon from '~icons/ph/star-fill';
	import CopyIcon from '~icons/ph/lightning';
	import CopyEnabledIcon from '~icons/ph/lightning-fill';
	import USDTIcon from '~icons/cryptocurrency-color/usdt';
	// console.log($page.data.leaders);

	// Assuming you get this initial data from somewhere, maybe load function
	// console.log($userLeaders);

	async function favLeader(leader) {
		const response = await fetch(`api/unfollow?binanceId=${leader.detail.leadPortfolioId}`);
		if (response.ok) {
			$userFavorites.push(leader._id);
			$userFavorites = $userFavorites;
		} else {
			console.error('Failed to unfollow leader');
		}
	}

	async function unfavLeader(leader) {
		const response = await fetch(`api/unfollow?binanceId=${leader.detail.leadPortfolioId}`);
		if (response.ok) {
			const index = $userFavorites.indexOf(leader._id);
			if (index > -1) {
				// only splice array when item is found
				$userFavorites.splice(index, 1); // 2nd parameter means remove one item only
			}
			$userFavorites = $userFavorites;
		} else {
			console.error('Failed to unfollow leader');
		}
	}

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
						<p class="text-primary-500 italic font-bold">
							{leader.detail.nicknameTranslate ?? leader.detail.nickname}
						</p>
						<p>{leader.detail.leadPortfolioId}</p>
					</div>
				</a>

				<div class="flex space-x-3">
					{#if $userFavorites.includes(leader._id)}
						<button on:click={() => unfavLeader(leader)}>
							<FavoriteEnabledIcon class="w-8 h-8 text-secondary-500" />
						</button>
					{:else}
						<button on:click={() => favLeader(leader)}>
							<FavoriteIcon class="w-8 h-8" />
						</button>
					{/if}
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
			<section class="p-4 space-y-1 flex flex-col items-start">
				<span>
					<span class="badge variant-ghost-secondary">Copiers</span>
					<span class="">{leader.detail.currentCopyCount}</span>
				</span>
				<span class="flex">
					<span class="badge variant-ghost-secondary">AUM</span>
					<span class="flex space-x-1 items-center">
						<span>{Math.round(+leader.detail.aumAmount)}</span>
						<span><USDTIcon /></span>
					</span>
				</span>
				<span class="flex">
					<span class="badge variant-ghost-secondary">Balance</span>
					<span class="flex space-x-1 items-center">
						<span>{Math.round(+leader.detail.marginBalance)}</span>
						<span><USDTIcon /></span>
					</span>
				</span>
				<span>
					<span class="badge variant-ghost-secondary">Levered</span>
					<span class="">
						<span>{Math.round(leader.account.levered_ratio * 100) / 100}</span>
					</span>
				</span>
				<span>
					<span class="badge variant-ghost-secondary">Unlevered</span>
					<span class="">
						<span>{Math.round(leader.account.unlevered_ratio * 100) / 100}</span>
					</span>
				</span>
			</section>
			<footer class="card-footer">
				<!-- <ProgressRadial width="w-16" font={128} value={95}>95</ProgressRadial> -->
			</footer>
		</div>
	{/each}
</div>
