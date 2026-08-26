Use `PillarBar` for any 0-N score that reads as part of a set: the four pillars, a rubric's axes, a model mix.

```jsx
<PillarBar name="Breadth" weight="30%" value={64} reference={71} />
<PillarBar name="Verification" value={9.1} max={10} size="sm" />
```

The track is `--chart-track` and the fill `--chart-1`; never colour bars per-series in a set that shares a scale.
