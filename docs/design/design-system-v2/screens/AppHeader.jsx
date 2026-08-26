function Wordmark() {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-4)' }}>
      <i aria-hidden="true" style={{
        width: 0, height: 0,
        borderLeft: '7px solid transparent', borderRight: '7px solid transparent',
        borderBottom: '16px solid var(--accent-mark)'
      }} />
      <span style={{
        fontFamily: 'var(--font-ui)', fontWeight: 'var(--weight-semibold)',
        fontSize: 22, letterSpacing: '-0.03em', color: 'var(--text-primary)'
      }}>gnomon</span>
    </span>
  );
}

function AppHeader(props) {
  return (
    <header style={{
      display: 'flex', alignItems: 'center', gap: 'var(--space-8)',
      paddingBottom: 'var(--space-5)',
      borderBottom: 'var(--rule-width) solid var(--rule-strong)',
      marginBottom: 'var(--space-11)'
    }}>
      <button type="button" onClick={props.onHome} aria-label="gnomon — volver al tablero"
              style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer' }}>
        <Wordmark />
      </button>
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 'var(--space-6)' }}>
        <Select label="Mes" variant="inline" value={props.month} options={MONTHS} onChange={props.onMonth} />
        <IconButton ariaLabel={props.dark ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro'}
                    bordered onClick={props.onTheme}>
          {props.dark ? (
            <svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="currentColor"
                 strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
              <circle cx="10" cy="10" r="3.6" />
              <path d="M10 1.8v1.9M10 16.3v1.9M3.8 3.8l1.35 1.35M14.85 14.85l1.35 1.35M1.8 10h1.9M16.3 10h1.9M3.8 16.2l1.35-1.35M14.85 5.15L16.2 3.8" />
            </svg>
          ) : (
            <svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="currentColor"
                 strokeWidth="1.5" strokeLinejoin="round" aria-hidden="true">
              <path d="M16.3 12.4A7 7 0 0 1 7.6 3.7a7 7 0 1 0 8.7 8.7z" />
            </svg>
          )}
        </IconButton>
      </div>
    </header>
  );
}
