Use `Button` for any action a person takes on a gnomon screen; `variant="link"` is the right call for in-flow navigation like "View profile".

```jsx
<Button variant="primary" onClick={save}>Link CLI</Button>
<Button variant="secondary" size="sm">Export month</Button>
<Button variant="link">View profile &rsaquo;</Button>
```

Rules: exactly one `primary` per view — gnomon screens are for reading, so most buttons are `secondary` or `link`. Labels name the outcome ("Link CLI"), never "Submit". Destructive actions are not in this system; if one is needed, ask before inventing a danger variant.
