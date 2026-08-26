Use `IconButton` for secondary controls that sit in a dense header or toolbar where a text label would crowd the layout.

```jsx
<IconButton ariaLabel="Switch to dark theme" onClick={toggle}>
  <i data-lucide="moon" />
</IconButton>
```

Never use it for the main action on a screen. Minimum box is 32px; prefer 40px so it stays touch-safe.
