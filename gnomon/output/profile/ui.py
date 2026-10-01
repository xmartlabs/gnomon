"""Small v2 controls shared by the profile sections."""

import html


# Definitions live in a keyboard-reachable control, not the native ``title`` attribute
# (design-system v2). The tooltip text is the button's accessible name, shown on hover
# and on keyboard focus by ``CSS`` below.
CSS = """
.gn-info {
  position: relative;
  display: inline-flex;
  width: 24px;
  height: 24px;
  flex: none;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  background: none;
  cursor: help;
}
.gn-info-glyph {
  display: inline-flex;
  width: 16px;
  height: 16px;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--rule-default);
  border-radius: 999px;
  color: var(--text-tertiary);
  font: 400 10px/1 var(--font-figure);
  letter-spacing: 0;
  text-transform: none;
}
.gn-info:hover::after,
.gn-info:focus-visible::after {
  content: attr(aria-label);
  position: absolute;
  z-index: 10;
  top: calc(100% + 4px);
  left: 0;
  width: max-content;
  max-width: 280px;
  padding: 8px 10px;
  border: 1px solid var(--rule-default);
  border-radius: 2px;
  background: var(--surface-raised);
  box-shadow: 0 1px 2px rgba(10, 11, 11, 0.06), 0 8px 24px rgba(10, 11, 11, 0.10);
  color: var(--text-primary);
  font: 400 13px/1.5 var(--font-ui);
  letter-spacing: 0;
  text-align: left;
  text-transform: none;
  white-space: normal;
}
.gn-label {
  margin: 0;
  color: var(--text-tertiary);
  font: 500 11px/1.2 var(--font-figure);
  letter-spacing: .1em;
  text-transform: uppercase;
}
.gn-section-head {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  margin-bottom: 4px;
}
.gn-section-head h2,
.gn-section-title {
  margin: 0;
  color: var(--text-secondary);
  font: 500 12px/1.2 var(--font-figure);
  letter-spacing: .1em;
  text-transform: uppercase;
}
.gn-section-hint {
  margin: 0 0 20px;
  color: var(--text-tertiary);
  font-size: 13px;
  line-height: 1.5;
}
.gn-vrule {
  width: 1px;
  align-self: stretch;
  background: var(--rule-default);
}
"""


def info_button(label: str) -> str:
    """Return the small circled-i definition control."""
    return ('<button type="button" class="gn-info" aria-label="{}">'
            '<span class="gn-info-glyph" aria-hidden="true">i</span></button>').format(
                html.escape(label, quote=True))
