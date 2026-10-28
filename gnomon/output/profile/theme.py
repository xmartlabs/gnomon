"""Theme initialization and controls for the local profile."""


# This runs before the profile stylesheet is parsed, avoiding a light-theme
# flash when a saved preference or the operating system requests dark mode.
HEAD_SCRIPT = """<script>
(function () {
  var theme;
  try {
    var saved = localStorage.getItem("gn-theme");
    if (saved === "light" || saved === "dark") {
      theme = saved;
    }
  } catch (e) {}
  if (!theme) {
    theme = window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }
  document.documentElement.dataset.theme = theme;
})();
</script>"""


# The dark semantic tokens are copied from the v2 design-system colors.css
# block so the standalone profile follows the dashboard's palette exactly.
DARK_CSS = """[data-theme="dark"] {
  --text-primary: var(--grey-50);
  --text-secondary: var(--grey-400);
  --text-tertiary: #9AA0A0;
  --text-decorative: var(--grey-500);
  --text-inverse: var(--grey-950);
  --text-accent: var(--blue-200);

  --surface-page: var(--grey-950);
  --surface-raised: var(--grey-900);
  --surface-sunken: var(--grey-900);
  --surface-hover: var(--grey-800);
  --surface-active: var(--grey-700);
  --surface-inverse: var(--grey-50);
  --surface-accent-subtle: var(--blue-900);

  --rule-strong: var(--grey-300);
  --rule-default: var(--grey-700);
  --rule-subtle: var(--grey-800);

  --accent: var(--blue-300);
  --accent-hover: var(--blue-200);
  --accent-pressed: var(--blue-100);
  --accent-on: var(--grey-950);
  --accent-subtle: var(--blue-900);
  --accent-mark: var(--blue-300);
  --accent-mark-shadow: var(--blue-700);

  --positive: #7FC79E;
  --positive-subtle: #0E2E1E;
  --negative: #D98A78;
  --negative-subtle: #3A1C15;
  --warning: #D6AC5C;
  --warning-subtle: #33280F;
  --neutral: var(--grey-500);

  --chart-1: var(--blue-300);
  --chart-2: var(--blue-500);
  --chart-3: var(--blue-800);
  --chart-4: var(--grey-600);
  --chart-track: var(--grey-800);
  --chart-grid: var(--grey-700);

  --focus-ring: var(--blue-300);
}"""


def render_toggle() -> str:
    """Return the masthead theme toggle and its small inline controller."""
    return """<button id="gn-theme-toggle" class="gn-theme-toggle" type="button"
  aria-label="Switch to dark theme">
  <svg data-theme-icon="sun" width="17" height="17" viewBox="0 0 20 20"
    fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"
    aria-hidden="true" hidden>
    <circle cx="10" cy="10" r="3.6"></circle>
    <path d="M10 1.5v2M10 16.5v2M1.5 10h2M16.5 10h2M4 4l1.4 1.4M14.6 14.6L16 16M4 16l1.4-1.4M14.6 5.4L16 4"></path>
  </svg>
  <svg data-theme-icon="moon" width="17" height="17" viewBox="0 0 20 20"
    fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"
    aria-hidden="true">
    <path d="M16.3 12.4A7 7 0 0 1 7.6 3.7a7 7 0 1 0 8.7 8.7z"></path>
  </svg>
</button>
<script>
(function () {
  var button = document.getElementById("gn-theme-toggle");
  if (!button) return;
  var sun = button.querySelector('[data-theme-icon="sun"]');
  var moon = button.querySelector('[data-theme-icon="moon"]');

  // SVG elements have no ``hidden`` IDL property, so set the attribute itself.
  function show(icon, visible) {
    if (icon.toggleAttribute) icon.toggleAttribute("hidden", !visible);
    icon.hidden = !visible;
  }

  function sync() {
    var dark = document.documentElement.dataset.theme === "dark";
    button.setAttribute("aria-label", dark
      ? "Switch to light theme"
      : "Switch to dark theme");
    show(sun, dark);
    show(moon, !dark);
  }

  button.addEventListener("click", function () {
    var next = document.documentElement.dataset.theme === "dark"
      ? "light"
      : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("gn-theme", next);
    } catch (e) {}
    sync();
  });
  sync();
})();
</script>"""
