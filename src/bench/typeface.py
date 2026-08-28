"""The vendored faces and the style rules that name them.

Copied from the deck so the two tools read the same. Nothing is fetched: a page that
falls back to a substitute face changes every row height, and the columns are the point.

Chakra Petch and JetBrains Mono, latin and latin-ext only, both under the SIL Open
Font License. The subsets came from the Google Fonts css2 endpoint and are vendored
rather than linked, because a page that reaches out is a page that can fail to.
"""

from __future__ import annotations

from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent.parent.parent / "fonts"
FONT_URL = "/fonts"

LATIN_EXT = ("U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, "
             "U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, "
             "U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF")
LATIN = ("U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, "
         "U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, "
         "U+FEFF, U+FFFD")

FACES = (
    ("Chakra Petch", 400, "chakra-petch-400"),
    ("Chakra Petch", 600, "chakra-petch-600"),
    ("Chakra Petch", 700, "chakra-petch-700"),
    ("JetBrains Mono", 500, "jetbrains-mono"),
    ("JetBrains Mono", 700, "jetbrains-mono"),
)


def files() -> list[str]:
    out = []
    for _, _, stem in FACES:
        for subset in ("latin", "latin-ext"):
            name = f"{stem}-{subset}.woff2"
            if name not in out:
                out.append(name)
    return out


def css() -> str:
    blocks = []
    for family, weight, stem in FACES:
        for subset, ranges in (("latin-ext", LATIN_EXT), ("latin", LATIN)):
            blocks.append(
                "@font-face{"
                f"font-family:'{family}';font-style:normal;font-weight:{weight};"
                "font-display:block;"
                f"src:url('{FONT_URL}/{stem}-{subset}.woff2') format('woff2');"
                f"unicode-range:{ranges};"
                "}"
            )
    return "\n".join(blocks)


def missing() -> list[str]:
    return [name for name in files() if not (FONT_DIR / name).is_file()]
