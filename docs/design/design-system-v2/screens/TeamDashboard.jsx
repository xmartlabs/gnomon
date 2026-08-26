function TierSplit() {
  return (
    <div>
      {TEAM.tiers.map(function (t, i) {
        return (
          <div key={t.name} style={{
            display: 'flex', alignItems: 'baseline', gap: 'var(--space-5)',
            padding: 'var(--space-5) 0',
            borderBottom: i < TEAM.tiers.length - 1 ? 'var(--rule-width) solid var(--rule-subtle)' : 0
          }}>
            <span style={{ font: 'var(--type-title-sm)' }}>{t.name}</span>
            <span style={{
              fontFamily: 'var(--font-figure)', fontSize: 'var(--size-label)',
              letterSpacing: 'var(--tracking-label)', color: 'var(--text-tertiary)'
            }}>{t.range}</span>
            <span style={{
              marginLeft: 'auto', fontFamily: 'var(--font-figure)',
              fontSize: 'var(--size-metric-sm)', fontWeight: 'var(--weight-medium)'
            }}>{t.count}</span>
          </div>
        );
      })}
      <p style={{ margin: 'var(--space-5) 0 0', font: 'var(--type-body-sm)', color: 'var(--text-secondary)' }}>
        Tier medio: Operator &middot; {TEAM.uploaded} personas subieron este mes
      </p>
    </div>
  );
}

function Coaching() {
  return (
    <div>
      <h3 style={{
        margin: 0, font: 'var(--type-title-md)', letterSpacing: 'var(--tracking-title)',
        textWrap: 'pretty'
      }}>Breadth es el pilar más flojo del equipo.</h3>
      <p style={{ margin: 'var(--space-4) 0 var(--space-8)', font: 'var(--type-body)', color: 'var(--text-secondary)', textWrap: 'pretty' }}>
        Solo 2 de 6 personas orquestan subagentes. Impacto estimado:{' '}
        <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-figure)', fontWeight: 'var(--weight-medium)' }}>+5 AQ</span> de equipo.
      </p>
      <Divider weight="subtle" space={0} />
      <h4 style={{ margin: 'var(--space-6) 0 var(--space-2)', font: 'var(--type-title-sm)', textWrap: 'pretty' }}>
        4 perfiles con sesiones largas sin checkpoints.
      </h4>
      <p style={{ margin: 0, font: 'var(--type-body-sm)', color: 'var(--text-secondary)' }}>
        Baja Efficiency sin bajar el volumen de trabajo.
      </p>
    </div>
  );
}

function TeamDashboard(props) {
  const heading = (
      <h1 style={{
        margin: '0 0 var(--space-8)', font: 'var(--type-title-lg)',
        letterSpacing: 'var(--tracking-title)'
      }}>
        Equipo · <span style={{ fontFamily: 'var(--font-figure)', fontWeight: 'var(--weight-medium)' }}>{props.month}</span>
      </h1>
  );

  if (props.month === 'Junio 2026') {
    return (
      <div>
        {heading}
        <EmptyState
        title="Nadie subió sesiones en Junio 2026."
        body={<span>Los datos aparecen cuando alguien corre <code style={{ fontFamily: 'var(--font-figure)', fontSize: 14 }}>gnomon push</code> apuntando a este servidor.</span>}
        action={<Button variant="link" onClick={props.onReset}>&larr; Ver Agosto 2026</Button>}
        />
      </div>
    );
  }

  const aq = props.month === 'Julio 2026' ? 68 : TEAM.aq;
  const delta = props.month === 'Julio 2026' ? 1 : TEAM.delta;

  return (
    <div>
      {heading}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 'var(--space-10)' }}>
        <Metric
          label="AQ del equipo" value={aq} unit="/100" size="xl"
          trailing={<Trend delta={delta} against={props.month === 'Julio 2026' ? 'junio' : 'julio'} size="lg" />}
        />
        <div style={{ width: 210, flex: 'none' }}>
          <ColumnChart height={96} data={TEAM.history} ariaLabel="Evolución del AQ del equipo, últimos 3 meses" />
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 'var(--space-9)' }}>
          <Metric label="Tokens" value={TEAM.tokens} size="md" align="right" />
          <Metric label="Costo" value={TEAM.cost} size="md" align="right"
                  trailing={<Trend delta={TEAM.costDelta} />} />
        </div>
      </div>

      <Divider weight="default" space={11} />

      <div style={{ display: 'grid', gridTemplateColumns: '1.15fr auto 1fr', gap: 'var(--layout-column-gap)', alignItems: 'start' }}>
        <section>
          <SectionLabel as="h2" size="lg" hint="Promedio del pilar entre quienes subieron datos este mes. Breadth = cuánta maquinaria movés · Craft = qué tan bien · Efficiency = cuánto rinde cada intervención · Savvy = criterio">
            Cuatro pilares
          </SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-7)' }}>
            {TEAM.pillars.map(function (p) {
              return <PillarBar key={p.name} name={p.name} weight={p.weight} value={p.value} />;
            })}
          </div>
        </section>
        <Divider orientation="vertical" />
        <section>
          <SectionLabel as="h2" size="lg">Qué mejorar este mes</SectionLabel>
          <Coaching />
        </section>
      </div>

      <Divider weight="default" space={11} />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 'var(--layout-column-gap)', alignItems: 'start' }}>
        <section>
          <SectionLabel as="h2" size="lg" hint="Distribución de tokens por modelo en el mes. Pasá el mouse por una porción para ver su porcentaje.">
            Modelos más usados
          </SectionLabel>
          <DonutChart data={TEAM.models} size={176} />
        </section>
        <Divider orientation="vertical" />
        <section>
          <SectionLabel as="h2" size="lg">Cómo se reparte el equipo</SectionLabel>
          <TierSplit />
        </section>
      </div>

      <h2 style={{
        font: 'var(--type-title-lg)', letterSpacing: 'var(--tracking-title)',
        margin: 'var(--space-13) 0 var(--space-7)'
      }}>Personas</h2>
      <DataTable
        columns={[
          { key: 'name', header: 'Nombre' },
          { key: 'aq', header: 'AQ', figure: true },
          { key: 'tier', header: 'Tier', render: function (r) { return <Badge tone={r.tier === 'Architect' ? 'accent' : 'neutral'}>{r.tier}</Badge>; } },
          { key: 'trend', header: 'Trend', render: function (r) { return <Trend delta={r.delta} />; } },
          { key: 'top', header: 'Top pilar' },
          { key: 'upload', header: 'Último upload', muted: true }
        ]}
        rows={PEOPLE}
        actionLabel="Ver perfil"
        rowLabel={function (r) { return 'Abrir perfil de ' + r.name; }}
        onRowClick={function (r) { props.onOpenPerson(r.id); }}
      />
    </div>
  );
}
