import React from 'react';

export function EmptyState(props) {
  const Title = props.titleAs || 'h2';
  return (
    <div style={{
      maxWidth: props.width || 520,
      padding: 'var(--space-14) 0',
      display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
      gap: 'var(--space-5)'
    }}>
      {props.label ? (
        <span style={{
          fontFamily: 'var(--font-figure)', fontSize: 'var(--size-label)',
          fontWeight: 'var(--weight-medium)', letterSpacing: 'var(--tracking-label)',
          textTransform: 'uppercase', color: 'var(--text-tertiary)'
        }}>{props.label}</span>
      ) : null}
      <Title style={{
        margin: 0, font: 'var(--type-title-lg)',
        letterSpacing: 'var(--tracking-title)', textWrap: 'pretty'
      }}>{props.title}</Title>
      {props.body ? (
        <p style={{ margin: 0, font: 'var(--type-body-lg)', color: 'var(--text-secondary)', textWrap: 'pretty' }}>
          {props.body}
        </p>
      ) : null}
      {props.action ? <div style={{ marginTop: 'var(--space-3)' }}>{props.action}</div> : null}
    </div>
  );
}
