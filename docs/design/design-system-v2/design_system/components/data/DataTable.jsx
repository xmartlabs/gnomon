import React from 'react';

export function DataTable(props) {
  const cols = props.columns || [];
  const rows = props.rows || [];
  const clickable = Boolean(props.onRowClick);
  const [hover, setHover] = React.useState(-1);

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr>
          {cols.map(function (c) {
            return (
              <th key={c.key} scope="col" style={{
                textAlign: c.align === 'right' ? 'right' : 'left',
                padding: '0 var(--space-5) var(--space-4) 0',
                borderBottom: 'var(--rule-width) solid var(--rule-strong)',
                fontFamily: 'var(--font-figure)', fontSize: 'var(--size-label)',
                fontWeight: 'var(--weight-medium)', letterSpacing: 'var(--tracking-label)',
                textTransform: 'uppercase', color: 'var(--text-tertiary)', whiteSpace: 'nowrap'
              }}>{c.header}</th>
            );
          })}
          {clickable ? <th aria-hidden="true" style={{ borderBottom: 'var(--rule-width) solid var(--rule-strong)' }} /> : null}
        </tr>
      </thead>
      <tbody>
        {rows.map(function (r, i) {
          return (
            <tr
              key={r.id || i}
              tabIndex={clickable ? 0 : undefined}
              role={clickable ? 'button' : undefined}
              aria-label={clickable ? (props.rowLabel ? props.rowLabel(r) : undefined) : undefined}
              onClick={clickable ? function () { props.onRowClick(r); } : undefined}
              onKeyDown={clickable ? function (e) {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); props.onRowClick(r); }
              } : undefined}
              onMouseEnter={function () { setHover(i); }}
              onMouseLeave={function () { setHover(-1); }}
              style={{
                cursor: clickable ? 'pointer' : 'default',
                background: clickable && hover === i ? 'var(--surface-hover)' : 'transparent',
                transition: 'background var(--duration-fast) var(--ease-out)'
              }}
            >
              {cols.map(function (c) {
                return (
                  <td key={c.key} style={{
                    textAlign: c.align === 'right' ? 'right' : 'left',
                    padding: 'var(--space-5) var(--space-5) var(--space-5) 0',
                    borderBottom: 'var(--rule-width) solid var(--rule-subtle)',
                    font: c.figure ? undefined : 'var(--type-body)',
                    fontFamily: c.figure ? 'var(--font-figure)' : 'var(--font-ui)',
                    fontSize: c.figure ? 'var(--size-metric-xs)' : (c.muted ? 'var(--size-body-sm)' : 'var(--size-body)'),
                    fontWeight: c.figure ? 'var(--weight-medium)' : 'var(--weight-regular)',
                    fontVariantNumeric: c.figure ? 'tabular-nums' : undefined,
                    color: c.muted ? 'var(--text-secondary)' : 'var(--text-primary)',
                    whiteSpace: c.wrap ? 'normal' : 'nowrap'
                  }}>
                    {c.render ? c.render(r) : r[c.key]}
                  </td>
                );
              })}
              {clickable ? (
                <td style={{
                  padding: 'var(--space-5) 0', textAlign: 'right',
                  borderBottom: 'var(--rule-width) solid var(--rule-subtle)'
                }}>
                  <span style={{
                    font: 'var(--type-body-sm)', color: 'var(--accent)',
                    borderBottom: 'var(--rule-width) solid currentColor', whiteSpace: 'nowrap'
                  }}>{props.actionLabel || 'Open'} &rsaquo;</span>
                </td>
              ) : null}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
