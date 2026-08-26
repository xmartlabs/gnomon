Use `Divider` wherever another system would reach for a card. Horizontal between sections, vertical between grid columns.

```jsx
<Divider weight="default" space={11} />
<div style={{ display: 'grid', gridTemplateColumns: '1.15fr auto 1fr', gap: 'var(--layout-column-gap)' }}>
  <PillarList /> <Divider orientation="vertical" /> <Coaching />
</div>
```
