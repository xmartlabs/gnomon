Use `Tooltip` for every definition that would otherwise bloat a label — what AQ measures, what a pillar means, how a counter is derived.

```jsx
<SectionLabel size="lg" trailing={null}>
  Four pillars <Tooltip label="Breadth is how much machinery you move; Craft is how well; Efficiency is the return on each intervention; Savvy is judgment." />
</SectionLabel>
```

Definitions belong here, not beside the title. Never put an action inside a tooltip.
