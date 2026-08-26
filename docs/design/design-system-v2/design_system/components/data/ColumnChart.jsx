import React from 'react';

export function ColumnChart(props) {
  const data = props.data || [];
  const height = props.height || 96;
  const max = props.max || Math.max.apply(null, data.map(function (d) { return d.value; })) * 1.12;

  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: props.gap || 'var(--space-5)', height: height }}
         role="img" aria-label={props.ariaLabel || data.map(function (d) { return d.label + ' ' + d.value; }).join(', ')}>
      {data.map(function (d, i) {
        const isLast = i === data.length - 1;
        const emphasised = d.emphasis !== undefined ? d.emphasis : isLast;
        return (
          <div key={d.label} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-3)' }}>
            {props.showValues === false ? null : (
              <span style={{
                fontFamily: 'var(--font-figure)', fontSize: 'var(--size-body-sm)',
                fontWeight: 'var(--weight-medium)', fontVariantNumeric: 'tabular-nums',
                color: emphasised ? 'var(--text-primary)' : 'var(--text-secondary)'
              }}>{d.value}</span>
            )}
            <div style={{
              width: '100%',
              height: Math.max(2, Math.round((d.value / max) * (height - 34))) + 'px',
              background: emphasised ? 'var(--chart-1)' : 'var(--chart-4)'
            }} />
            <span style={{
              fontFamily: 'var(--font-figure)', fontSize: 'var(--size-label)',
              letterSpacing: 'var(--tracking-label)', textTransform: 'uppercase',
              color: 'var(--text-tertiary)'
            }}>{d.label}</span>
          </div>
        );
      })}
    </div>
  );
}
