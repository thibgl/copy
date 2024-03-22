<script lang="ts">
	import { page } from '$app/stores';
	import { Avatar, ProgressRadial } from '@skeletonlabs/skeleton';

	const tableArr = [{ name: 'test', position: 3, symbol: 'XXX', weight: 32 }];
	const totalWeight = 42;

	import TraderIcon from '~icons/ph/user';
	import FavoriteIcon from '~icons/ph/star';
	import CopyIcon from '~icons/ph/lightning';
</script>

<div class="flex flex-wrap gap-3 justify-center">
	{#each $page.data.leads as lead}
		<div class="card w-96">
			<header class="card-header flex justify-between items-center">
				<a class="flex space-x-3 items-center" href={lead.leaderboardUrl} target="_blank">
					<!-- <Avatar src={lead.userPhotoUrl} fallback="src/lib/images/user.png" /> -->
					<img
						class="w-12 h-12 rounded-full bg-gray-500"
						src={lead.userPhotoUrl.length > 0 ? lead.userPhotoUrl : 'src/lib/images/user.png'}
						alt="user avatar"
					/>
					<p>{lead.nickName}</p>
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
