import React from 'react';

export function Divider(props) {
  const weight = props.weight || 'default';
  const color = weight === 'strong' ? 'var(--rule-strong)' : weight === 'subtle' ? 'var(--rule-subtle)' : 'var(--rule-default)';
  const width = weight === 'strong' && props.thick ? 'var(--rule-width-strong)' : 'var(--rule-width)';

  if (props.orientation === 'vertical') {
    return <div aria-hidden="true" style={{ width: width, alignSelf: 'stretch', background: color, flex: 'none' }} />;
  }
  return (
    <hr style={{
      border: 0, borderTop: width + ' solid ' + color,
      margin: props.space ? 'var(--space-' + props.space + ') 0' : 'var(--space-11) 0'
    }} />
  );
}
