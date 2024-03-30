<script lang="ts">
	import { page } from '$app/stores';
	import { Avatar, ProgressRadial } from '@skeletonlabs/skeleton';

	const tableArr = [{ name: 'test', position: 3, symbol: 'XXX', weight: 32 }];
	const totalWeight = 42;

	import TraderIcon from '~icons/ph/user-plus';
	import FavoriteIcon from '~icons/ph/star';
	import CopyIcon from '~icons/ph/lightning';
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
				<a class="flex space-x-3 items-center" href={leader.profileUrl} target="_blank">
					<!-- <Avatar src={lead.userPhotoUrl} fallback="src/lib/images/user.png" /> -->
					<img
						class="w-12 h-12 rounded-full bg-gray-500"
						src={leader.avatarUrl.length > 0 ? leader.avatarUrl : 'src/lib/images/user.png'}
						alt="user avatar"
					/>
					<p>{leader.nickname}</p>
				</a>

				<div class="flex space-x-3">
					<FavoriteIcon class="w-8 h-8" />
					<CopyIcon class="w-8 h-8" />
				</div>
			</header>
			<section class="p-4"></section>
			<footer class="card-footer">
				<ProgressRadial width="w-16" font={128} value={95}>95</ProgressRadial>
			</footer>
		</div>
	{/each}
</div>
