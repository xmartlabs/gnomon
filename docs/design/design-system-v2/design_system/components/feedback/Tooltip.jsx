import React from 'react';

export function Tooltip(props) {
  const [open, setOpen] = React.useState(false);
  const side = props.side || 'top';

  const pos = {
    top: { bottom: '100%', left: '50%', transform: 'translate(-50%, -6px)' },
    bottom: { top: '100%', left: '50%', transform: 'translate(-50%, 6px)' },
    right: { left: '100%', top: '50%', transform: 'translate(6px, -50%)' }
  }[side];

  return (
    <span
      style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}
      onMouseEnter={function () { setOpen(true); }}
      onMouseLeave={function () { setOpen(false); }}
      onFocus={function () { setOpen(true); }}
      onBlur={function () { setOpen(false); }}
    >
      {props.children ? props.children : (
        <span
          tabIndex={0}
          role="button"
          aria-label={props.label}
          aria-expanded={open}
          style={{
            minWidth: 24, minHeight: 24, flex: 'none',
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            background: 'none', border: 0, padding: 0, cursor: 'help'
          }}
        >
          <span aria-hidden="true" style={{
            width: 16, height: 16,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'var(--font-figure)', fontSize: 10, lineHeight: 1,
            color: 'var(--text-tertiary)',
            border: 'var(--rule-width) solid var(--rule-default)',
            borderRadius: 'var(--radius-full)'
          }}>i</span>
        </span>
      )}
      {open ? (
        <span role="tooltip" style={Object.assign({
          position: 'absolute', zIndex: 20,
          maxWidth: props.width || 260, width: 'max-content',
          padding: 'var(--space-4) var(--space-5)',
          background: 'var(--surface-inverse)', color: 'var(--text-inverse)',
          font: 'var(--type-body-sm)', textAlign: 'left',
          borderRadius: 'var(--radius-sm)', boxShadow: 'var(--shadow-overlay)',
          pointerEvents: 'none', textWrap: 'pretty'
        }, pos)}>
          {props.label}
        </span>
      ) : null}
    </span>
  );
}
