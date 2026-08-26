Use `DonutChart` for share-of-total only — model mix, tier split. Never for change over time.

```jsx
<DonutChart data={[
  { label: 'Sonnet 4.5', value: 46 },
  { label: 'Opus 4.1', value: 31 },
  { label: 'GPT-5', value: 15 },
  { label: 'Other', value: 8 }
]} />
```

Cap it at 4-5 slices; roll the tail into "Other". The palette is an ordered green ramp, so slices must be sorted descending.
