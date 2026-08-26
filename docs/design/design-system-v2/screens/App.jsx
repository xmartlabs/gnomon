function App() {
  const [view, setView] = React.useState('team');
  const [personId, setPersonId] = React.useState('ana');
  const [month, setMonth] = React.useState('Agosto 2026');
  const [dark, setDark] = React.useState(false);

  React.useEffect(function () {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  }, [dark]);

  return (
    <div style={{ maxWidth: 'var(--layout-max)', margin: '0 auto', padding: 'var(--space-8) var(--layout-gutter) var(--space-14)' }}>
      <AppHeader
        month={month} dark={dark}
        onMonth={function (e) { setMonth(e.target.value); setView('team'); }}
        onTheme={function () { setDark(!dark); }}
        onHome={function () { setView('team'); }}
      />
      {view === 'team' ? (
        <TeamDashboard
          month={month}
          onReset={function () { setMonth('Agosto 2026'); }}
          onOpenPerson={function (id) { setPersonId(id); setView('person'); }}
        />
      ) : (
        <PersonProfile personId={personId} onBack={function () { setView('team'); }} />
      )}
    </div>
  );
}
