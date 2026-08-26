import React from 'react';

const SIZES = {
  xl: 'var(--type-metric-xl)',
  lg: 'var(--type-metric-lg)',
  md: 'var(--type-metric-md)',
  sm: 'var(--type-metric-sm)'
};

export function Metric(props) {
  const size = props.size || 'md';
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', alignItems: props.align === 'right' ? 'flex-end' : 'flex-start' }}>
      {props.label ? (
        <span style={{
          fontFamily: 'var(--font-figure)', fontSize: 'var(--size-label)',
          fontWeight: 'var(--weight-medium)', letterSpacing: 'var(--tracking-label)',
          textTransform: 'uppercase', color: 'var(--text-tertiary)'
        }}>{props.label}</span>
      ) : null}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-4)' }}>
        <span style={{
          font: SIZES[size], letterSpacing: 'var(--tracking-metric)',
          color: props.tone === 'accent' ? 'var(--accent)' : 'var(--text-primary)',
          fontVariantNumeric: 'tabular-nums'
        }}>{props.value}</span>
        {props.unit ? (
          <span style={{ font: 'var(--type-body-sm)', color: 'var(--text-secondary)', fontFamily: 'var(--font-figure)' }}>{props.unit}</span>
        ) : null}
        {props.trailing}
      </div>
      {props.caption ? (
        <span style={{ font: 'var(--type-body-sm)', color: 'var(--text-secondary)' }}>{props.caption}</span>
      ) : null}
    </div>
  );
}
