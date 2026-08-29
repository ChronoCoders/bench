"""Take a picture of a page, so a design can be looked at rather than asserted about.

Every claim about this page until now was a string match in a test. A string match
cannot tell you a panel is the wrong height. Run it against a file or a URL:

    python tools/shot.py <file or url> <out.png> [width] [height]
"""

from __future__ import annotations

import subprocess
import sys
import time
import tempfile
from pathlib import Path

CHROME = Path(r"C:/Program Files/Google/Chrome/Application/chrome.exe")
WIDTH, HEIGHT = 2000, 1400
WAIT_STEPS = 40


def shoot(where: str, out: Path, width: int = WIDTH, height: int = HEIGHT) -> Path:
    if not CHROME.is_file():
        raise FileNotFoundError(f"no browser to render with at {CHROME}")
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    with tempfile.TemporaryDirectory(prefix="bench-shot-") as profile:
        run = subprocess.run(
            [str(CHROME), "--headless=new", "--disable-gpu", "--hide-scrollbars",
             f"--user-data-dir={profile}", f"--window-size={width},{height}",
             "--screenshot=" + str(out), "--virtual-time-budget=4000",
             "--force-device-scale-factor=1", where],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120,
        )
    # The new headless mode leaves a child behind that writes the file after the
    # parent has already exited, so waiting on the process is not waiting on the
    # picture.
    for _ in range(WAIT_STEPS):
        if out.is_file() and out.stat().st_size:
            return out
        time.sleep(0.5)
    raise RuntimeError(f"no picture came out: {run.stderr.strip()[:400]}")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    where = sys.argv[1]
    if not where.startswith(("http://", "https://", "file://")):
        where = Path(where).resolve().as_uri()
    size = [int(a) for a in sys.argv[3:5]] or [WIDTH, HEIGHT]
    out = shoot(where, Path(sys.argv[2]), *size)
    print(f"{out}  {out.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
