<script lang="ts">
	const tableArr = [{ name: 'test', position: 3, symbol: 'XXX', weight: 32 }];
	const totalWeight = 42;
</script>

<div class="table-container">
	<!-- Native Table Element -->
	<table class="table table-hover">
		<thead>
			<tr>
				<th>Position</th>
				<th>Name</th>
				<th>Symbol</th>
				<th>Weight</th>
			</tr>
		</thead>
		<tbody>
			{#each tableArr as row, i}
				<tr>
					<td>{row.position}</td>
					<td>{row.name}</td>
					<td>{row.symbol}</td>
					<td>{row.weight}</td>
				</tr>
			{/each}
		</tbody>
		<tfoot>
			<tr>
				<th colspan="3">Calculated Total Weight</th>
				<td>{totalWeight}</td>
			</tr>
		</tfoot>
	</table>
</div>
