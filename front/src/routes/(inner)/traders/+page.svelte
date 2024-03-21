<script lang="ts">
	import { ProgressRadial } from '@skeletonlabs/skeleton';

	const tableArr = [{ name: 'test', position: 3, symbol: 'XXX', weight: 32 }];
	const totalWeight = 42;

	import TraderIcon from '~icons/ph/user';
	import FavoriteIcon from '~icons/ph/star';
	import CopyIcon from '~icons/ph/lightning';
</script>

<div class="card">
	<header class="card-header flex">
		<TraderIcon class="w-8 h-8" />
		<FavoriteIcon class="w-8 h-8" />
		<CopyIcon class="w-8 h-8" />
	</header>
	<section class="p-4">(content)</section>
	<footer class="card-footer">
		<ProgressRadial width="w-16" font={128} value={95}>95</ProgressRadial>
	</footer>
</div>
