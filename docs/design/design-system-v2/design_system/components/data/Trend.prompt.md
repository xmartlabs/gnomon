Use `Trend` next to any figure that moved. Pass `delta={null}` for a person with no upload this month — it renders "— no data" in neutral grey, never in red.

```jsx
<Trend delta={6} against="July" />
<Trend delta={-3} />
<Trend delta={null} />
```

Red means a real decline or an error. Never use it for something neutral.
