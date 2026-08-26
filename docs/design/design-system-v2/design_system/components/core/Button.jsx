import React from 'react';

const SIZES = {
  sm: { height: 'var(--control-sm)', padding: '0 var(--space-5)', fontSize: 'var(--size-body-sm)' },
  md: { height: 'var(--control-md)', padding: '0 var(--space-6)', fontSize: 'var(--size-body)' },
  lg: { height: 'var(--control-lg)', padding: '0 var(--space-7)', fontSize: 'var(--size-body-lg)' }
};

const VARIANTS = {
  primary: {
    background: 'var(--accent)', color: 'var(--accent-on)',
    border: 'var(--rule-width) solid var(--accent)',
    hover: { background: 'var(--accent-hover)', borderColor: 'var(--accent-hover)' },
    active: { background: 'var(--accent-pressed)', borderColor: 'var(--accent-pressed)' }
  },
  secondary: {
    background: 'var(--surface-raised)', color: 'var(--text-primary)',
    border: 'var(--rule-width) solid var(--rule-strong)',
    hover: { background: 'var(--surface-hover)' },
    active: { background: 'var(--surface-active)' }
  },
  ghost: {
    background: 'transparent', color: 'var(--text-primary)',
    border: 'var(--rule-width) solid transparent',
    hover: { background: 'var(--surface-hover)' },
    active: { background: 'var(--surface-active)' }
  },
  link: {
    background: 'transparent', color: 'var(--accent)',
    border: 0, padding: 0, height: 'auto',
    borderBottom: 'var(--rule-width) solid currentColor',
    hover: { color: 'var(--accent-hover)' },
    active: { color: 'var(--accent-pressed)' }
  }
};

export function Button(props) {
  const variant = props.variant || 'primary';
  const size = props.size || 'md';
  const v = VARIANTS[variant] || VARIANTS.primary;
  const [hover, setHover] = React.useState(false);
  const [active, setActive] = React.useState(false);

  const base = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    gap: 'var(--space-4)',
    fontFamily: 'var(--font-ui)', fontWeight: 'var(--weight-medium)',
    letterSpacing: 0, borderRadius: 'var(--radius-sm)',
    cursor: props.disabled ? 'not-allowed' : 'pointer',
    opacity: props.disabled ? 0.4 : 1,
    transition: 'var(--transition-control)',
    width: props.fullWidth ? '100%' : undefined,
    whiteSpace: 'nowrap'
  };

  const style = Object.assign({}, base, SIZES[size], {
    background: v.background, color: v.color, border: v.border,
    borderBottom: v.borderBottom, padding: v.padding, height: v.height
  });
  if (!props.disabled && hover) Object.assign(style, v.hover);
  if (!props.disabled && active) Object.assign(style, v.active);

  return (
    <button
      type={props.type || 'button'}
      disabled={props.disabled}
      onClick={props.onClick}
      aria-label={props.ariaLabel}
      style={style}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => { setHover(false); setActive(false); }}
      onMouseDown={() => setActive(true)}
      onMouseUp={() => setActive(false)}
    >
      {props.iconLeft}
      {props.children}
      {props.iconRight}
    </button>
  );
}
