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
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
a { color: var(--accent); text-decoration: none; border-bottom: 1px solid currentColor; }
a:hover { color: var(--accent-hover); }
:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
::selection { background: var(--accent-subtle); }
.gn-shell { max-width: 1180px; margin: 0 auto; padding: 0 32px 64px; }
.gn-masthead {
  display: flex; align-items: center; gap: 24px; min-height: 72px;
  border-bottom: 1px solid var(--rule-default);
}
.gn-brand { display: inline-flex; align-items: center; gap: 8px; border: 0; color: var(--text-primary); font-weight: 600; }
.gn-brand:hover { color: var(--accent); }
.gn-mark { width: 24px; height: 24px; display: block; }
.gn-masthead-label { color: var(--text-secondary); font-size: 13px; }
.gn-masthead-note { margin-left: auto; color: var(--text-tertiary); font-size: 13px; }
.gn-main { min-width: 0; }
.gn-section { min-width: 0; }
.gn-footer { margin-top: 64px; padding-top: 20px; border-top: 1px solid var(--rule-default); color: var(--text-secondary); font-size: 13px; }
.gn-footer p { margin: 4px 0; }
.gn-caption { max-width: 720px; }
.gn-fig-xl, .gn-fig-md, .gn-fig-sm, [data-figure] {
  font-family: var(--font-figure);
  font-variant-numeric: tabular-nums;
}
.gn-fig-xl { font-size: 120px; line-height: .88; }
.gn-fig-md { font-size: 40px; line-height: .95; }
.gn-fig-sm { font-size: 28px; line-height: 1.1; }
.gn-empty { color: var(--text-tertiary); }
@media (max-width: 680px) {
  .gn-shell { padding-left: 20px; padding-right: 20px; }
  .gn-masthead { gap: 12px; flex-wrap: wrap; padding: 16px 0; }
  .gn-masthead-note { width: 100%; margin-left: 32px; }
}
"""
