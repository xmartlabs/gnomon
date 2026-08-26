Use `Input` for any typed value. The visible `label` is required; a placeholder is only an example of the format.

```jsx
<Input label="Email" name="email" type="email" autoComplete="email"
       placeholder="ana@company.com" required
       error={errors.email} onChange={setEmail} />
```

Errors must say what to do, never "Invalid input". Mark required fields with the word `required`, not an asterisk.
