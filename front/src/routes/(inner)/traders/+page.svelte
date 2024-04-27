<script lang="ts">
	import { page } from '$app/stores';
	import type { PageData } from './$types';
	import { Avatar, ProgressRadial } from '@skeletonlabs/skeleton';
	import { writable } from 'svelte/store';
	import { Line } from 'svelte-chartjs';
	import { onMount } from 'svelte';

	import {
		Chart as ChartJS,
		// Title,
		Tooltip,
		//Legend,
		LineElement,
		LinearScale,
		PointElement,
		CategoryScale,
		Filler
	} from 'chart.js';

	ChartJS.register(
		// Title,
		Tooltip,
		//Legend,
		LineElement,
		LinearScale,
		PointElement,
		CategoryScale,
		Filler
	);

	let style: CSSStyleDeclaration | null;
	$: style = null;

	onMount(() => {
		style = getComputedStyle(document.body);
	});

	export let data: PageData;
	const userLeaders = data.userLeaders;
	const userFavorites = data.userFavorites;
	// $: console.log($userFavorites);
	// const test = writable({});
	// console.log(typeof test);

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
		const response = await fetch(`api/unfollow?binanceId=${leader.binanceId}`);
		if (response.ok) {
			$userFavorites.push(leader.binanceId);
			$userFavorites = $userFavorites;
		} else {
			console.error('Failed to unfollow leader');
		}
	}

	async function unfavLeader(leader) {
		const response = await fetch(`api/unfollow?binanceId=${leader.binanceId}`);
		if (response.ok) {
			const index = $userFavorites.indexOf(leader.binanceId);
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
		const response = await fetch(`api/unfollow?binanceId=${leader.binanceId}`);
		if (response.ok) {
			$userLeaders[leader.binanceId] = 1;
		} else {
			console.error('Failed to unfollow leader');
		}
	}

	async function unfollowLeader(leader) {
		const response = await fetch(`api/unfollow?binanceId=${leader.binanceId}`);
		if (response.ok) {
			delete $userLeaders[leader.binanceId];
			$userLeaders = $userLeaders;
		} else {
			console.error('Failed to unfollow leader');
		}
	}
</script>

<div class="flex flex-wrap gap-3 justify-center">
	<!-- <form action="/actions?/addTrader" method="POST" class="card w-96 aspect-video">
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
	</form> -->
	{#each $page.data.leaders as leader}
		<div class="card w-96 aspect-video space-y-3">
			<header class="card-header flex justify-between items-center">
				<a
					class="flex space-x-3 items-center"
					href={'https://www.binance.com/en/copy-trading/lead-details/' + leader.binanceId}
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
						<p
							class="text-primary-500 italic font-bold"
							class:text-warning-500={data.user.account.active_leaders.includes(leader.binanceId)}
						>
							{leader.detail.nicknameTranslate ?? leader.detail.nickname}
						</p>
						<p>{leader.binanceId}</p>
					</div>
				</a>

				<div class="flex space-x-3">
					{#if $userFavorites.includes(leader.binanceId)}
						<button on:click={() => unfavLeader(leader)}>
							<FavoriteEnabledIcon class="w-8 h-8 text-secondary-500" />
						</button>
					{:else}
						<button on:click={() => favLeader(leader)}>
							<FavoriteIcon class="w-8 h-8" />
						</button>
					{/if}
					{#if Object.keys($userLeaders).includes(leader.binanceId)}
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
			<section class="p-4 space-y-1 flex justify-between">
				<div class="flex flex-col items-start space-y-1">
					<span>
						<span class="badge variant-ghost-secondary">Copiers</span>
						<span class="">{leader.detail.currentCopyCount} / {leader.detail.maxCopyCount}</span>
					</span>
					<span class="flex">
						<span class="badge variant-ghost-secondary">AUM</span>
						<span class="flex space-x-1 items-center">
							<span>{Math.round(leader.detail.aumAmount)}</span>
							<span><USDTIcon /></span>
						</span>
					</span>
					<span class="flex">
						<span class="badge variant-ghost-secondary">Balance</span>
						<span class="flex space-x-1 items-center">
							<span>{Math.round(leader.detail.marginBalance)}</span>
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
				</div>
				<div class="flex flex-col items-end space-y-1">
					<span class="flex">
						<span class="flex space-x-1 items-center">
							<span>{Math.round(leader.performance.roi)} %</span>
						</span>
						<span class="badge variant-ghost-secondary">ROI</span>
					</span>
					<span class="flex">
						<span class="flex space-x-1 items-center">
							<span>{Math.round(leader.performance.pnl)}</span>
							<span><USDTIcon /></span>
						</span>
						<span class="badge variant-ghost-secondary">PNL</span>
					</span>
					<span>
						<span class="">
							<span>{Math.round(leader.performance.mdd * 100) / 100} %</span>
						</span>
						<span class="badge variant-ghost-secondary">MDD</span>
					</span>
					<span>
						<span class="">
							<span>{Math.round(leader.performance.winRate * 100) / 100} %</span>
						</span>
						<span class="badge variant-ghost-secondary">WinRate</span>
					</span>
					<span>
						<span class="">{Math.round(leader.performance.sharpRatio * 100) / 100}</span>
						<span class="badge variant-ghost-secondary">Sharpe</span>
					</span>
				</div>
			</section>
			<footer class="card-footer p-0">
				{#if style}
					<Line
						data={{
							labels: leader.chart.map((item) => new Date(item.dateTime)),
							datasets: [
								{
									// label: 'My First dataset',
									fill: true,
									backgroundColor: `rgb(${style.getPropertyValue('--color-surface-600')})`,
									lineTension: 0.5,
									borderColor: `rgb(${data.user.account.active_leaders.includes(leader.binanceId) ? style.getPropertyValue('--color-warning-500') : style.getPropertyValue('--color-primary-500')})`,
									borderCapStyle: 'butt',
									borderDash: [],
									borderDashOffset: 0.0,
									borderJoinStyle: 'miter',
									// pointBorderColor: 'rgb(205, 130,1 58)',
									// pointBackgroundColor: 'rgb(255, 255, 255)',
									// pointBorderWidth: 10,
									// pointHoverRadius: 5,
									pointHoverBackgroundColor: 'rgb(0, 0, 0)',
									pointHoverBorderColor: 'rgba(220, 220, 220,1)',
									pointHoverBorderWidth: 2,
									pointRadius: 0,
									pointHitRadius: 10,
									data: leader.chart.map((item) => item.value)
								}
							]
						}}
						options={{
							scales: {
								x: {
									display: false
								},
								y: {
									display: false
								}
							},
							maintainAspectRatio: false
						}}
					/>
				{/if}

				<!-- <ProgressRadial width="w-16" font={128} value={95}>95</ProgressRadial> -->
			</footer>
		</div>
	{/each}
</div>
