import React from 'react';

export function IconButton(props) {
  const size = props.size || 'md';
  const box = size === 'sm' ? 32 : size === 'lg' ? 48 : 40;
  const [hover, setHover] = React.useState(false);

  return (
    <button
      type="button"
      onClick={props.onClick}
      disabled={props.disabled}
      aria-label={props.ariaLabel}
      title={props.ariaLabel}
      aria-pressed={props.pressed}
      style={{
        width: box, height: box, flex: 'none',
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        background: props.pressed ? 'var(--surface-active)' : (hover ? 'var(--surface-hover)' : 'transparent'),
        color: props.disabled ? 'var(--text-tertiary)' : 'var(--text-secondary)',
        border: props.bordered ? 'var(--rule-width) solid var(--rule-default)' : 'var(--rule-width) solid transparent',
        borderRadius: 'var(--radius-sm)',
        cursor: props.disabled ? 'not-allowed' : 'pointer',
        opacity: props.disabled ? 0.4 : 1,
        transition: 'var(--transition-control)'
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      {props.children}
    </button>
  );
}
