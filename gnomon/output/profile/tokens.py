"""Design-system v2 tokens and the profile's structural CSS."""

LIGHT_CSS = """:root {
  --grey-0: #FFFFFF;
  --grey-25: #FBFBFB;
  --grey-50: #F4F5F5;
  --grey-100: #E9EAEA;
  --grey-200: #D5D7D7;
  --grey-300: #B4B7B7;
  --grey-400: #8B8F8F;
  --grey-500: #6A6E6E;
  --grey-600: #4E5252;
  --grey-700: #383B3B;
  --grey-800: #232626;
  --grey-900: #141616;
  --grey-950: #0A0B0B;
  --blue-50: #EBF2FC;
  --blue-100: #CFE0F7;
  --blue-200: #9EC2EF;
  --blue-300: #6BA1E4;
  --blue-400: #4189DC;
  --blue-500: #2A78D6;
  --blue-600: #1F60B0;
  --blue-700: #17498A;
  --blue-800: #103361;
  --blue-900: #0A2242;
  --moss-100: #DCEDE3;
  --moss-500: #15734A;
  --moss-600: #0F5A39;
  --clay-100: #F6E3DF;
  --clay-500: #A23B2A;
  --clay-600: #85301F;
  --ochre-100: #F5EBD4;
  --ochre-500: #8A6516;
  --text-primary: var(--grey-900);
  --text-secondary: var(--grey-500);
  --text-tertiary: #6E7272;
  --text-decorative: var(--grey-400);
  --text-inverse: var(--grey-0);
  --text-accent: var(--blue-600);
  --surface-page: var(--grey-0);
  --surface-raised: var(--grey-0);
  --surface-sunken: var(--grey-50);
  --surface-hover: var(--grey-50);
  --surface-active: var(--grey-100);
  --surface-inverse: var(--grey-900);
  --surface-accent-subtle: var(--blue-50);
  --rule-strong: var(--grey-900);
  --rule-default: var(--grey-200);
  --rule-subtle: var(--grey-100);
  --accent: var(--blue-600);
  --accent-hover: var(--blue-700);
  --accent-pressed: var(--blue-800);
  --accent-on: var(--grey-0);
  --accent-subtle: var(--blue-50);
  --accent-mark: var(--blue-500);
  --accent-mark-shadow: var(--blue-200);
  --positive: var(--moss-500);
  --positive-subtle: var(--moss-100);
  --negative: var(--clay-500);
  --negative-subtle: var(--clay-100);
  --warning: var(--ochre-500);
  --warning-subtle: var(--ochre-100);
  --neutral: var(--grey-400);
  --chart-1: var(--blue-500);
  --chart-2: var(--blue-300);
  --chart-3: var(--blue-100);
  --chart-4: var(--grey-300);
  --chart-track: var(--grey-100);
  --chart-grid: var(--grey-200);
  --focus-ring: var(--blue-500);
  --font-sans: "Archivo", "Helvetica Neue", Helvetica, Arial, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
  --font-figure: var(--font-mono);
  --font-ui: var(--font-sans);
}
"""

BASE_CSS = """*, *::before, *::after { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--surface-page);
  color: var(--text-primary);
  font: 400 15px/1.5 var(--font-ui);
  font-variant-numeric: tabular-nums;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
a { color: var(--accent); text-decoration: none; }
a:hover { color: var(--accent-hover); }
[hidden] { display: none !important; }
:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
::selection { background: var(--accent-subtle); }
.gn-shell { max-width: 1244px; margin: 0 auto; padding: 0 32px 64px; }
.gn-masthead {
  display: flex; align-items: center; gap: 16px;
  padding: 20px 0 12px;
  border-bottom: 1px solid var(--rule-strong);
}
.gn-brand {
  display: inline-flex; align-items: center; gap: 8px;
  color: var(--text-primary);
  font-size: 22px; font-weight: 600; line-height: 1.2; letter-spacing: -.03em;
}
.gn-brand:hover { color: var(--text-primary); }
.gn-mark { width: 24px; height: 24px; display: block; flex: none; }
.gn-masthead-label {
  padding-left: 16px;
  border-left: 1px solid var(--rule-default);
  color: var(--text-tertiary);
  font: 500 11px/1.2 var(--font-figure); letter-spacing: .1em; text-transform: uppercase;
}
.gn-masthead-note {
  display: flex; align-items: center; gap: 8px; margin-left: auto;
  color: var(--text-secondary);
  font: 500 11px/1.2 var(--font-figure); letter-spacing: .1em; text-transform: uppercase;
}
.gn-lock { flex: none; }
.gn-theme-toggle {
  display: inline-flex; width: 32px; height: 32px; flex: none;
  align-items: center; justify-content: center; padding: 0;
  border: 1px solid var(--rule-default); border-radius: 2px;
  background: transparent; color: var(--text-primary); cursor: pointer;
}
.gn-theme-toggle:hover { background: var(--surface-hover); }
.gn-main { min-width: 0; padding-top: 56px; }
.gn-section { min-width: 0; }
#trend, #diagnosis, #aq-breakdown {
  margin-top: 48px; padding-top: 48px; border-top: 1px solid var(--rule-default);
}
#activity { margin-top: 56px; padding-top: 48px; border-top: 1px solid var(--rule-default); }
#portrait { margin-top: 72px; padding-top: 24px; border-top: 2px solid var(--rule-strong); }
.gn-footer {
  display: flex; align-items: baseline; gap: 24px;
  margin-top: 72px; padding-top: 20px;
  border-top: 1px solid var(--rule-default);
}
.gn-footer-brand {
  display: inline-flex; align-items: center; gap: 8px; flex: none;
  color: var(--text-secondary);
  font: 500 11px/1.2 var(--font-figure); letter-spacing: .1em; text-transform: uppercase;
}
.gn-footer-brand .gn-mark { width: 14px; height: 14px; align-self: center; }
.gn-footer-built {
  margin-left: auto; flex: none; display: inline-flex; align-items: center; gap: 8px;
  color: var(--text-secondary); font-size: 13px; text-decoration: none; border-bottom: 0;
}
.gn-footer-built:hover { color: var(--text-primary); }
.gn-xl-mark { width: 14px; height: 15px; flex: none; }
.gn-fig-xl, .gn-fig-md, .gn-fig-sm, [data-figure] {
  font-family: var(--font-figure);
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  letter-spacing: -.025em;
}
.gn-fig-xl { font-size: 88px; line-height: .88; }
.gn-fig-md { font-size: 40px; line-height: .88; }
.gn-fig-sm { font-size: 28px; line-height: 1.15; }
.gn-empty { color: var(--text-tertiary); }
@media (max-width: 680px) {
  .gn-shell { padding-left: 16px; padding-right: 16px; }
  .gn-masthead { gap: 12px; flex-wrap: wrap; }
  .gn-masthead-note { order: 3; width: 100%; margin-left: 0; }
  .gn-main { padding-top: 40px; }
  .gn-footer { flex-wrap: wrap; gap: 12px; }
  .gn-footer-repo { margin-left: 0; }
}
"""
