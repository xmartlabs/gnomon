import React from 'react';
import { Tooltip } from '../feedback/Tooltip.jsx';

export function SectionLabel(props) {
  const Tag = props.as || 'div';
  const isHeading = Tag !== 'div';

  return (
    <Tag style={{
      display: 'flex', alignItems: 'center', gap: 'var(--space-4)',
      margin: 0,
      marginBottom: props.tight ? 'var(--space-4)' : 'var(--space-6)',
      font: 'inherit', fontWeight: 'inherit'
    }}>
      <span style={{
        fontFamily: 'var(--font-figure)',
        fontSize: props.size === 'lg' ? 'var(--size-label-lg)' : 'var(--size-label)',
        fontWeight: 'var(--weight-medium)',
        letterSpacing: 'var(--tracking-label)',
        textTransform: 'uppercase',
        color: props.size === 'lg' ? 'var(--text-secondary)' : 'var(--text-tertiary)'
      }}>
        {props.children}
      </span>
      {props.hint ? <Tooltip label={props.hint} /> : null}
      {props.trailing ? <span style={{ marginLeft: 'auto' }}>{props.trailing}</span> : null}
    </Tag>
  );
}
