<script lang="ts">
	import { page } from '$app/stores';

	const tableArr = [{ name: 'test', position: 3, symbol: 'XXX', weight: 32 }];
	const totalWeight = 42;
</script>

<div class="table-container">
	<!-- Native Table Element -->
	<table class="table table-hover">
		<thead>
			<tr>
				<th>Symbol</th>
				<th>Amount</th>
				<th>Free</th>
				<th>Locked</th>
				<th>Borrowed</th>
				<th>Interest</th>
			</tr>
		</thead>
		<tbody>
			{#each Object.keys($page.data.user.positions.symbol) as symbol, i}
				<tr>
					<td>{$page.data.user.positions.symbol[symbol]}</td>
					<td>{$page.data.user.positions.netAsset[symbol]}</td>
					<td>{$page.data.user.positions.free[symbol]}</td>
					<td>{$page.data.user.positions.locked[symbol]}</td>
					<td>{$page.data.user.positions.borrowed[symbol]}</td>
					<td>{$page.data.user.positions.interest[symbol]}</td>
				</tr>
			{/each}
		</tbody>
		<!-- <tfoot>
			<tr>
				<th colspan="3">Calculated Total Weight</th>
				<td>{totalWeight}</td>
			</tr>
		</tfoot> -->
	</table>
</div>
