"""Embedded font faces used by the local profile."""

import base64
import os


_FONT_FILES = (
    ("Archivo", "Archivo-latin-wght.woff2", "400 600"),
    ("IBM Plex Mono", "IBMPlexMono-400-latin.woff2", "400"),
    ("IBM Plex Mono", "IBMPlexMono-500-latin.woff2", "500"),
)


def _font_face(family: str, filename: str, weight: str) -> str:
    font_path = os.path.join(os.path.dirname(__file__), "fonts", filename)
    with open(font_path, "rb") as font_file:
        encoded = base64.b64encode(font_file.read()).decode("ascii")
    return """@font-face {{
  font-family: "{family}";
  font-style: normal;
  font-weight: {weight};
  font-display: swap;
  src:url(data:font/woff2;base64,{encoded}) format("woff2");
}}
""".format(family=family, weight=weight, encoded=encoded)


def font_face_css() -> str:
    return "".join(_font_face(*font) for font in _FONT_FILES)
