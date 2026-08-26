Use `Metric` for every headline number. One `xl` per screen at most — that is the screen's subject.

```jsx
<Metric label="Team AQ" value={72} unit="/100" size="xl"
        trailing={<Trend delta={4} against="July" />} />
```

Never wrap a Metric in a bordered box to "group" it; use a `SectionLabel` and whitespace.
