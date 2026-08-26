Use `Select` for a closed set of options. In a page header — the month picker — use `variant="inline"` so it reads as type, not as a control.

```jsx
<Select label="Month" variant="inline" value={month}
        options={['August 2026', 'July 2026', 'June 2026']} onChange={setMonth} />
```
