import React from 'react';

export function Input(props) {
  const id = props.id || ('inp-' + (props.name || 'field'));
  const invalid = Boolean(props.error);
  const [focus, setFocus] = React.useState(false);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', width: props.fullWidth ? '100%' : undefined }}>
      <label htmlFor={id} style={{
        display: 'flex', alignItems: 'baseline', gap: 'var(--space-4)',
        font: 'var(--type-body-sm)', color: 'var(--text-secondary)'
      }}>
        <span>{props.label}</span>
        {props.required ? <span style={{ fontFamily: 'var(--font-figure)', fontSize: 11, color: 'var(--text-tertiary)' }}>required</span> : null}
      </label>
      <input
        id={id}
        name={props.name}
        type={props.type || 'text'}
        value={props.value}
        onChange={props.onChange}
        placeholder={props.placeholder}
        autoComplete={props.autoComplete}
        disabled={props.disabled}
        aria-invalid={invalid || undefined}
        aria-describedby={invalid ? id + '-err' : (props.hint ? id + '-hint' : undefined)}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        style={{
          height: 'var(--control-md)', padding: '0 var(--space-5)',
          font: 'var(--type-body)', fontFamily: props.mono ? 'var(--font-figure)' : 'var(--font-ui)',
          color: 'var(--text-primary)', background: 'var(--surface-raised)',
          border: 'var(--rule-width) solid ' + (invalid ? 'var(--negative)' : focus ? 'var(--accent)' : 'var(--rule-default)'),
          borderRadius: 'var(--radius-sm)', outline: 'none',
          transition: 'var(--transition-control)'
        }}
      />
      {invalid ? (
        <span id={id + '-err'} role="alert" style={{ font: 'var(--type-body-sm)', color: 'var(--negative)' }}>{props.error}</span>
      ) : props.hint ? (
        <span id={id + '-hint'} style={{ font: 'var(--type-body-sm)', color: 'var(--text-tertiary)' }}>{props.hint}</span>
      ) : null}
    </div>
  );
}
