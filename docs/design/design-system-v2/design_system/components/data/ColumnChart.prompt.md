Use `ColumnChart` for 3-6 periods of the same measure. Keep the current period emphasised and the rest grey.

```jsx
<ColumnChart data={[
  { label: 'Mar', value: 58 }, { label: 'Apr', value: 61 }, { label: 'May', value: 65 },
  { label: 'Jun', value: 67 }, { label: 'Jul', value: 68 }, { label: 'Aug', value: 72 }
]} />
```

Compute bar heights in px, never in %: a percentage height inside an auto-height flex column collapses to zero.
