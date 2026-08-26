Use `DataTable` for the per-person and per-period detail that sits below the aggregate figures.

```jsx
<DataTable
  columns={[
    { key: 'name', header: 'Name' },
    { key: 'aq', header: 'AQ', figure: true },
    { key: 'tier', header: 'Tier', render: r => <Badge>{r.tier}</Badge> },
    { key: 'trend', header: 'Trend', render: r => <Trend delta={r.delta} /> },
    { key: 'upload', header: 'Last upload', muted: true }
  ]}
  rows={people}
  actionLabel="View profile"
  rowLabel={r => 'Open profile for ' + r.name}
  onRowClick={openProfile}
/>
```

Never add an outer border or alternating row backgrounds. Figures go in `figure` columns so they align down the column.
