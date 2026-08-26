function Scorecard(props) {
  const s = props.scorecard;
  const items = [
    { k: 'Execution', v: s.execution, d: 'cuánto shippea y qué tan rápido' },
    { k: 'Planning', v: s.planning, d: 'pensar antes de construir' },
    { k: 'Engineering', v: s.engineering, d: 'qué tan limpio es el trabajo' }
  ];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 'var(--space-8)' }}>
      {items.map(function (it) {
        return (
          <div key={it.k}>
            <div style={{ font: 'var(--type-metric-md)', letterSpacing: 'var(--tracking-metric)' }}>{it.v}</div>
            <div style={{ font: 'var(--type-body)', marginTop: 'var(--space-1)' }}>{it.k}</div>
            <div style={{ font: 'var(--type-body-sm)', color: 'var(--text-secondary)', textWrap: 'pretty' }}>{it.d}</div>
          </div>
        );
      })}
    </div>
  );
}

function PersonProfile(props) {
  const p = PEOPLE.filter(function (x) { return x.id === props.personId; })[0] || PEOPLE[0];
  const order = ['Breadth', 'Craft', 'Efficiency', 'Savvy'];

  const history = ['mar', 'abr', 'may', 'jun', 'jul', 'ago'].map(function (l, i) {
    const base = p.aq - (p.delta === null ? 0 : p.delta);
    const offsets = [-11, -8, -6, -4, 0];
    return { label: l, value: i === 5 ? p.aq : Math.max(0, base + offsets[i]) };
  });

  return (
    <div>
      <nav aria-label="breadcrumb" style={{ marginBottom: 'var(--space-9)' }}>
        <Button variant="link" onClick={props.onBack}>&larr; Equipo</Button>
      </nav>

      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 'var(--space-10)', flexWrap: 'wrap' }}>
        <div style={{ maxWidth: 460 }}>
          <h1 style={{ margin: 0, font: 'var(--type-title-lg)', fontSize: 40, letterSpacing: 'var(--tracking-title)' }}>{p.name}</h1>
          <div style={{
            fontFamily: 'var(--font-figure)', fontSize: 'var(--size-label-lg)',
            letterSpacing: 'var(--tracking-label)', color: 'var(--text-tertiary)',
            margin: 'var(--space-3) 0 var(--space-5)'
          }}>{p.email}</div>
          <p style={{ margin: 0, font: 'var(--type-title-sm)', fontStyle: 'italic', color: 'var(--text-secondary)', textWrap: 'pretty' }}>
            &ldquo;{p.quote}&rdquo;
          </p>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'baseline', gap: 'var(--space-6)' }}>
          <span style={{ font: 'var(--type-metric-lg)', fontSize: 96, letterSpacing: 'var(--tracking-metric)', fontVariantNumeric: 'tabular-nums' }}>{p.aq}</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            <span style={{ font: 'var(--type-body)', fontFamily: 'var(--font-figure)', color: 'var(--text-secondary)' }}>/100</span>
            <Badge tone={p.tier === 'Architect' ? 'accent' : 'neutral'}>{p.tier}</Badge>
          </div>
        </div>
      </div>

      <Divider weight="default" space={10} />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1.25fr', gap: 'var(--layout-column-gap)', alignItems: 'start' }}>
        <section>
          <SectionLabel as="h2" size="lg" hint="Cada sugerencia sale de un eje concreto de la rúbrica.">Sugerencias</SectionLabel>
          {p.suggestions.map(function (s, i) {
            return (
              <p key={i} style={{
                margin: 0, paddingBottom: 'var(--space-6)', marginBottom: 'var(--space-6)',
                borderBottom: i === 0 ? 'var(--rule-width) solid var(--rule-subtle)' : 0,
                font: 'var(--type-title-sm)', textWrap: 'pretty'
              }}>{s}</p>
            );
          })}
        </section>
        <Divider orientation="vertical" />
        <section>
          <SectionLabel as="h2" size="lg" hint="El scorecard gstack juzga cómo construís; el AQ juzga cómo operás la máquina.">Scorecard</SectionLabel>
          <Scorecard scorecard={p.scorecard} />
          <Divider weight="subtle" space={8} />
          <SectionLabel as="h3">Nivel en el tiempo &middot; 6 meses</SectionLabel>
          <ColumnChart height={110} data={history} ariaLabel={'AQ de ' + p.name + ', últimos 6 meses'} />
        </section>
      </div>

      <Divider weight="default" space={11} />

      <SectionLabel as="h2" size="lg">Cómo opera agentes &middot; cuatro pilares</SectionLabel>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 'var(--space-10)' }}>
        {order.map(function (name) {
          const meta = PILLAR_META[name];
          const pct = p.pillars[name];
          const offs = [0.5, -0.1, -0.6];
          return (
            <div key={name} style={{ borderTop: 'var(--rule-width-strong) solid var(--rule-strong)', paddingTop: 'var(--space-5)' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-4)', marginBottom: 'var(--space-6)' }}>
                <span style={{ font: 'var(--type-title-sm)' }}>{name}</span>
                <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-figure)', fontSize: 'var(--size-metric-sm)', fontWeight: 'var(--weight-medium)' }}>
                  {Math.round(pct * meta.max / 100)}
                </span>
                <span style={{ fontFamily: 'var(--font-figure)', fontSize: 'var(--size-label)', color: 'var(--text-tertiary)' }}>/{meta.max}</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
                {meta.axes.map(function (ax, i) {
                  const v = Math.max(0, Math.min(10, pct / 10 + offs[i]));
                  return <PillarBar key={ax} name={ax} value={Number(v.toFixed(1))} max={10} size="sm" />;
                })}
              </div>
            </div>
          );
        })}
      </div>

      <Divider weight="default" space={11} />

      <div style={{ display: 'grid', gridTemplateColumns: '1.35fr auto 1fr', gap: 'var(--layout-column-gap)', alignItems: 'start' }}>
        <section>
          <SectionLabel as="h2" size="lg" hint="Contadores deterministas: no opinan, solo cuentan.">Explore</SectionLabel>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 'var(--space-8) var(--space-9)' }}>
            {COUNTERS.map(function (c) {
              return (
                <div key={c.k}>
                  <div style={{ font: 'var(--type-metric-sm)', fontVariantNumeric: 'tabular-nums' }}>{c.v}</div>
                  <div style={{ font: 'var(--type-body-sm)', color: 'var(--text-secondary)', textWrap: 'pretty' }}>{c.k}</div>
                </div>
              );
            })}
          </div>
        </section>
        <Divider orientation="vertical" />
        <section>
          <SectionLabel as="h2" size="lg">Uso del mes</SectionLabel>
          <div style={{ display: 'flex', gap: 'var(--space-9)', marginBottom: 'var(--space-8)' }}>
            <Metric value="153" caption="sesiones" size="sm" />
            <Metric value="1.062" caption="prompts" size="sm" />
            <Metric value="14" caption="acciones/prompt" size="sm" />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
            {PERSON_MODELS.map(function (m) {
              return <PillarBar key={m.label} name={m.label} value={m.value} size="sm" tone={m.value < 30 ? 'muted' : 'default'} />;
            })}
          </div>
        </section>
      </div>
    </div>
  );
}
