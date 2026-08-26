Use `EmptyState` whenever a period or a person has no data. It replaces the whole content region — never show empty figures beside it.

```jsx
<EmptyState
  title="Nobody uploaded sessions in June 2026."
  body={<>Data appears once someone runs <code>gnomon push</code> pointed at this server.</>}
  action={<Button variant="link" onClick={backToCurrent}>&larr; View August 2026</Button>}
/>
```

Always give a way out. An empty state without an action is a dead end.

Keep the screen's `h1` rendered above the empty state so the outline holds in every data state —
or pass `titleAs="h1"` when the empty state is the entire screen.
