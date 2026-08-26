import React from 'react';

export function PillarBar(props) {
  const max = props.max || 100;
  const pct = Math.max(0, Math.min(100, (props.value / max) * 100));
  const height = props.size === 'sm' ? 6 : props.size === 'lg' ? 10 : 8;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-4)' }}>
        <span style={{ font: props.size === 'sm' ? 'var(--type-body-sm)' : 'var(--type-title-sm)' }}>{props.name}</span>
        {props.weight ? (
          <span style={{ fontFamily: 'var(--font-figure)', fontSize: 'var(--size-label)', letterSpacing: 'var(--tracking-label)', color: 'var(--text-tertiary)' }}>{props.weight}</span>
        ) : null}
        <span style={{
          marginLeft: 'auto', fontFamily: 'var(--font-figure)',
          fontSize: props.size === 'sm' ? 'var(--size-body)' : 'var(--size-metric-sm)',
          fontWeight: 'var(--weight-medium)', fontVariantNumeric: 'tabular-nums'
        }}>{props.value}</span>
        {props.max ? (
          <span style={{ fontFamily: 'var(--font-figure)', fontSize: 'var(--size-label)', color: 'var(--text-tertiary)' }}>/{max}</span>
        ) : null}
      </div>
      <div
        role="img"
        aria-label={props.name + ': ' + props.value + ' of ' + max}
        style={{ height: height, background: 'var(--chart-track)', position: 'relative' }}
      >
        <span style={{
          position: 'absolute', inset: '0 auto 0 0', width: pct + '%',
          background: props.tone === 'muted' ? 'var(--chart-3)' : 'var(--chart-1)'
        }} />
        {props.reference !== undefined && props.reference !== null ? (
          <span
            aria-hidden="true"
            title={'Team average: ' + props.reference}
            style={{
              position: 'absolute', top: -2, bottom: -2,
              left: Math.max(0, Math.min(100, (props.reference / max) * 100)) + '%',
              width: 'var(--rule-width-strong)', background: 'var(--rule-strong)'
            }}
          />
        ) : null}
      </div>
    </div>
  );
}
