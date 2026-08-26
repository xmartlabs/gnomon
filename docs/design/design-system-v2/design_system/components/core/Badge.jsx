import React from 'react';

const TONES = {
  neutral: { color: 'var(--text-secondary)', border: 'var(--rule-default)', background: 'transparent' },
  accent: { color: 'var(--accent)', border: 'var(--accent)', background: 'transparent' },
  solid: { color: 'var(--accent-on)', border: 'var(--accent)', background: 'var(--accent)' },
  positive: { color: 'var(--positive)', border: 'var(--positive)', background: 'transparent' },
  negative: { color: 'var(--negative)', border: 'var(--negative)', background: 'transparent' },
  warning: { color: 'var(--warning)', border: 'var(--warning)', background: 'transparent' }
};

export function Badge(props) {
  const t = TONES[props.tone || 'neutral'] || TONES.neutral;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 'var(--space-2)',
      height: 22, padding: '0 var(--space-4)',
      fontFamily: 'var(--font-figure)', fontSize: 'var(--size-label-lg)',
      fontWeight: 'var(--weight-medium)',
      letterSpacing: props.uppercase ? 'var(--tracking-label)' : 0,
      textTransform: props.uppercase ? 'uppercase' : 'none',
      color: t.color, background: t.background,
      border: 'var(--rule-width) solid ' + t.border,
      borderRadius: 'var(--radius-sm)', whiteSpace: 'nowrap'
    }}>
      {props.children}
    </span>
  );
}
