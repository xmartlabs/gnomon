Use `SectionLabel` above every block of content. It is what replaces card headers in this system.

```jsx
<SectionLabel as="h2" size="lg" hint="Average of the pillar across people who uploaded this month.">
  Four pillars
</SectionLabel>

<SectionLabel>Tokens &middot; cost</SectionLabel>
```

Pass `as="h2"` (or `h3`) whenever the label titles a real section — this component is the only
thing carrying the document outline, so skipping it leaves a screen with no headings. Leave the
default `div` for decorative eyebrows that merely name a nearby figure.

Keep the label to 1-3 words. Anything explanatory goes in `hint` — long labels beside a title are
a known gnomon anti-pattern.
