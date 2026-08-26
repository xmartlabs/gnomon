import React from 'react';

export function Trend(props) {
  const d = props.delta;
  const noData = d === null || d === undefined;
  const dir = noData ? 'none' : d > 0 ? 'up' : d < 0 ? 'down' : 'flat';

  const map = {
    up: { glyph: '\u25B2', color: 'var(--positive)', text: '+' + d },
    down: { glyph: '\u25BC', color: 'var(--negative)', text: '\u2212' + Math.abs(d) },
    flat: { glyph: '=', color: 'var(--neutral)', text: '0' },
    none: { glyph: '\u2014', color: 'var(--neutral)', text: 'no data' }
  };
  const m = map[dir];

  return (
    <span style={{
      display: 'inline-flex', alignItems: 'baseline', gap: 'var(--space-2)',
      fontFamily: 'var(--font-figure)',
      fontSize: props.size === 'lg' ? 'var(--size-body-lg)' : 'var(--size-body-sm)',
      fontWeight: 'var(--weight-medium)', color: m.color, whiteSpace: 'nowrap'
    }}>
      <span aria-hidden="true">{m.glyph}</span>
      <span>{m.text}</span>
      {props.against ? (
        <span style={{ color: 'var(--text-tertiary)', fontWeight: 'var(--weight-regular)' }}>vs {props.against}</span>
      ) : null}
    </span>
  );
}
