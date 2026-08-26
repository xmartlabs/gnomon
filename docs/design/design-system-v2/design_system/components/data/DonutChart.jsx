import React from 'react';

const PALETTE = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)'];

export function DonutChart(props) {
  const data = props.data || [];
  const size = props.size || 176;
  const total = data.reduce(function (s, d) { return s + d.value; }, 0) || 1;
  const [active, setActive] = React.useState(-1);
  const r = 46;
  const inner = props.thickness ? 46 - props.thickness : 0;

  let acc = 0;
  const slices = data.map(function (d, i) {
    const a0 = (acc / total) * Math.PI * 2 - Math.PI / 2;
    acc += d.value;
    const a1 = (acc / total) * Math.PI * 2 - Math.PI / 2;
    const mid = (a0 + a1) / 2;
    const p = function (a, rad) { return [50 + rad * Math.cos(a), 50 + rad * Math.sin(a)]; };
    const o0 = p(a0, r), o1 = p(a1, r);
    const large = (d.value / total) > 0.5 ? 1 : 0;
    let path;
    if (inner > 0) {
      const i1 = p(a1, inner), i0 = p(a0, inner);
      path = 'M' + o0[0].toFixed(2) + ' ' + o0[1].toFixed(2) +
        ' A' + r + ' ' + r + ' 0 ' + large + ' 1 ' + o1[0].toFixed(2) + ' ' + o1[1].toFixed(2) +
        ' L' + i1[0].toFixed(2) + ' ' + i1[1].toFixed(2) +
        ' A' + inner + ' ' + inner + ' 0 ' + large + ' 0 ' + i0[0].toFixed(2) + ' ' + i0[1].toFixed(2) + ' Z';
    } else {
      path = 'M50 50 L' + o0[0].toFixed(2) + ' ' + o0[1].toFixed(2) +
        ' A' + r + ' ' + r + ' 0 ' + large + ' 1 ' + o1[0].toFixed(2) + ' ' + o1[1].toFixed(2) + ' Z';
    }
    const pct = Math.round((d.value / total) * 100);
    return {
      path: path, color: d.color || PALETTE[i % PALETTE.length],
      label: d.label, pct: pct,
      dx: Math.cos(mid) * 4, dy: Math.sin(mid) * 4
    };
  });

  const shown = active >= 0 ? slices[active] : null;

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 'var(--space-9)' }}>
      <div style={{ position: 'relative', width: size, height: size, flex: 'none' }}>
        <svg viewBox="0 0 100 100" style={{ width: '100%', height: '100%', overflow: 'visible' }}
             role="img" aria-label={props.ariaLabel || data.map(function (d) { return d.label + ' ' + Math.round((d.value / total) * 100) + '%'; }).join(', ')}>
          {slices.map(function (s, i) {
            return (
              <path key={s.label} d={s.path} fill={s.color}
                    stroke="var(--surface-page)" strokeWidth="0.8"
                    tabIndex={0} aria-label={s.label + ': ' + s.pct + '%'}
                    onMouseEnter={function () { setActive(i); }}
                    onMouseLeave={function () { setActive(-1); }}
                    onFocus={function () { setActive(i); }}
                    onBlur={function () { setActive(-1); }}
                    style={{
                      cursor: 'pointer',
                      transform: active === i ? 'translate(' + s.dx.toFixed(2) + 'px,' + s.dy.toFixed(2) + 'px)' : 'none',
                      transformOrigin: '50px 50px',
                      transition: 'transform var(--duration-fast) var(--ease-out)'
                    }} />
            );
          })}
        </svg>
        {shown ? (
          <div style={{
            position: 'absolute', left: '50%', top: '50%',
            transform: 'translate(-50%,-50%)', pointerEvents: 'none',
            background: 'var(--surface-raised)', border: 'var(--rule-width) solid var(--rule-strong)',
            padding: 'var(--space-2) var(--space-4)', whiteSpace: 'nowrap',
            boxShadow: 'var(--shadow-overlay)'
          }}>
            <span style={{ font: 'var(--type-body-sm)' }}>{shown.label}</span>{' '}
            <span style={{ fontFamily: 'var(--font-figure)', fontWeight: 'var(--weight-medium)' }}>{shown.pct}%</span>
          </div>
        ) : null}
      </div>
      {props.legend === false ? null : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)', flex: 'none' }}>
          {slices.map(function (s, i) {
            return (
              <div key={s.label}
                   onMouseEnter={function () { setActive(i); }}
                   onMouseLeave={function () { setActive(-1); }}
                   style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)', font: 'var(--type-body)' }}>
                <i style={{ width: 10, height: 10, background: s.color, flex: 'none' }} />
                <span>{s.label}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
