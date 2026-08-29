"""Serve the bench on this machine. Nothing leaves it.

Run it: python tools/serve.py [root folder] [port]
"""

from __future__ import annotations

import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bench import compare, folder, master, measurement, page, typeface

TARGETS = Path(__file__).resolve().parent.parent / "targets"
DEFAULT_PORT = 8731
NONE = "none"

# The page is built from files that change under it, and a run in progress asks for
# itself again every few seconds. A browser holding any of that is showing yesterday.
# Cache-Control arrived with HTTP/1.1, and a cache reading an HTTP/1.0 reply is entitled
# to ignore it and guess a freshness lifetime instead, which is what a stale page here
# turned out to be. So the replies say 1.1, and Pragma is there for anything that only
# reads 1.0.
HTML = "text/html; charset=utf-8"
NO_CACHE = "no-store"

MASTERED_SUFFIX = " (Mastered)"
MASTERED_FOLDER = "Mastered"
BODY_LIMIT = 4096


DEPTH = 2


def audio_in(path: Path) -> list[Path]:
    try:
        return sorted(p for p in path.iterdir()
                      if p.is_file() and p.suffix.lower() in folder.AUDIO_SUFFIXES)
    except OSError:
        return []


def choices(root: Path, depth: int = DEPTH) -> list[str]:
    """Every folder that holds audio, then every file sitting loose at the top.

    A file inside a folder is not offered on its own. The folder is already one choice
    and listing both puts the same audio in the list twice. The walk stops at DEPTH
    because an unbounded one over a folder like Downloads reaches a node_modules.
    """
    out = ["./"] if audio_in(root) else []

    def folders(here: Path, left: int) -> None:
        if left <= 0:
            return
        try:
            entries = sorted(here.iterdir())
        except OSError:
            return
        for path in entries:
            if path.is_dir() and not path.name.startswith("."):
                if audio_in(path):
                    out.append(str(path.relative_to(root)) + "/")
                folders(path, left - 1)

    folders(root, depth)
    out.extend(str(p.relative_to(root)) for p in audio_in(root))
    return out


def inside(root: Path, path: Path) -> bool:
    """Whether a path really is under the folder being served.

    Comparing the front of one string against another says Downloads (Mastered) is
    inside Downloads, which is how the output folder for the root came to be offered
    at all: it sits beside what is being served, not in it.
    """
    return path == root or root in path.parents


def out_dir_for(path: Path) -> Path:
    """Beside what was chosen, never inside it.

    The mastering layer refuses to write into the folder its source is in. This is that
    rule turned into a place rather than an error: a folder gets one next to it with the
    same name, and a single file gets a Mastered folder beside the file.
    """
    if path.is_dir():
        return path.parent / (path.name + MASTERED_SUFFIX)
    return path.parent / MASTERED_FOLDER


# The last thing measured, so opening the page lands on something rather than on an
# empty card. It is one selection for the whole process, which is what a bench with one
# person in front of it has.
LAST: dict[str, str] = {}

# What was last typed into the bar, so a record does not have to be typed once per
# track. It is what the person in front of the bench last used, not a fact about any
# file, so it is remembered and never written down.
SAID: dict[str, str] = {}

# What has already been measured this run, so landing on it is instant. Keyed on what
# the files were when they were read, not on their names: a folder whose contents have
# changed is a different folder. It lives and dies with the process and nothing is
# written down, because a measurement that outlives the thing it measured is entry 2's
# fault in a new coat.
MEASURED: dict[tuple, object] = {}


def stamp(path: Path) -> tuple:
    if path.is_dir():
        return (str(path),) + tuple(
            (p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in audio_in(path))
    found = path.stat()
    return (str(path), found.st_mtime_ns, found.st_size)


def remember(path: Path, target_name: str, make):
    key = (stamp(path), target_name)
    if key not in MEASURED:
        MEASURED[key] = make()
    return MEASURED[key]

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _refusal(root: Path, what: str, target_name: str) -> str | None:
    if not what:
        return "nothing is chosen to master"
    if not target_name or target_name == NONE:
        return ("no target is chosen, and every correction here is derived from the "
                "distance to one")
    path = (root / what.rstrip("/")).resolve()
    if not inside(root, path):
        return "that path is outside the folder being served"
    if not path.exists():
        return f"{what} is not there any more"
    # The output folder sits beside what was chosen. Beside the served root is outside
    # it, and writing outside the folder being served is worse than not offering to.
    out = out_dir_for(path)
    if not inside(root, out):
        return (f"mastering {what} would write to {out}, which is outside the folder "
                "being served. Choose something inside it")
    return None


def typed(form: dict) -> dict:
    """The three fields nothing here can derive, taken from the form or from the last
    time they were filled in."""
    said = {}
    for name in page.TYPED:
        value = form.get(name, [""])[0].strip()
        said[name] = value if value else SAID.get(name, "")
    return said


def start_master(root: Path, what: str, target_name: str, said: dict | None = None) -> str:
    """The id of the run to watch. One at a time: mastering uses the whole machine, and
    two at once would be writing into the same folder under the same names."""
    refused = _refusal(root, what, target_name)
    with JOBS_LOCK:
        if refused is None:
            already = next((k for k, v in JOBS.items() if v["running"]), None)
            if already is not None:
                return already
        job_id = str(len(JOBS) + 1)
        job = {"what": what, "target": target_name, "said": dict(said or {}),
               "running": refused is None, "finished": 0, "total": 0, "at": None,
               "done": [], "failed": [], "failure": None, "refused": refused,
               "out_dir": ""}
        JOBS[job_id] = job
    if refused is not None:
        return job_id

    path = (root / what.rstrip("/")).resolve()
    out_dir = out_dir_for(path)
    paths = audio_in(path) if path.is_dir() else [path]
    job["out_dir"], job["total"] = str(out_dir), len(paths)

    def watching(name, finished, total):
        job["at"], job["finished"], job["total"] = name, finished, total

    def work():
        try:
            chosen = compare.load(TARGETS / f"{target_name}.json")
            job["done"], job["failed"] = master.run_each(paths, chosen, out_dir, watching,
                                                         said)
        except Exception:
            job["failure"] = traceback.format_exc()
        finally:
            job["at"], job["finished"] = None, job["total"]
            job["running"] = False

    threading.Thread(target=work, daemon=True).start()
    return job_id


def targets() -> list[str]:
    return sorted(p.stem for p in TARGETS.glob("*.json")) if TARGETS.is_dir() else []


def writes_into(root: Path, what: str) -> str:
    """Where Master would put it, shown before the button is pressed rather than after,
    and written the way the picker writes things: from the folder being served."""
    if not what:
        return ""
    path = (root / what.rstrip("/")).resolve()
    if not inside(root, path) or not path.exists():
        return ""
    out = out_dir_for(path)
    if not inside(root, out):
        return ""
    return str(out.relative_to(root)) + "/"


def opening(root: Path, what: str, target_name: str) -> tuple[str, str, bool]:
    """What to show when nothing was asked for, and whether it is ready to show.

    The last thing measured, which is held in memory and comes back at once. Not the
    first thing in the picker: measuring is minutes of work on a real record, and a
    page load that starts it leaves the browser waiting on a spinner with nothing to
    say for itself. That is what pressing Measure is for.
    """
    if what:
        return what, target_name, True
    offered, named = choices(root), targets()
    # Only if it is still there. A remembered choice is a path, and a path that has
    # been moved or renamed would otherwise be measured on every bare visit.
    remembered = LAST.get("what")
    ready = remembered in offered
    what = remembered if ready else (offered[0] if offered else "")
    if not target_name or target_name == NONE:
        held = LAST.get("target")
        target_name = held if held in named else (named[0] if named else NONE)
    return what, target_name, ready


def render(root: Path, what: str, target_name: str) -> str:
    what, target_name, ready = opening(root, what, target_name)
    head = page.controls(choices(root), targets(), what, target_name,
                         writes_into(root, what), SAID)
    if not what:
        return page.document("Bench", head + page.said(
            "Nothing to measure", "This folder holds no audio the bench can read."))
    if not ready:
        return page.document("Bench", head + page.said(
            "Ready", f"{what} is chosen. Press Measure to read it.",
            "nothing measured yet this run"))

    chosen = None
    if target_name and target_name != NONE:
        chosen = compare.load(TARGETS / f"{target_name}.json")

    path = (root / what.rstrip("/")).resolve()
    if not inside(root, path):
        return page.document("Bench", head + page.said(
            "Refused", "That path is outside the folder being served."))

    LAST["what"], LAST["target"] = what, target_name
    if path.is_dir():
        sheet = remember(path, target_name, lambda: folder.measure(path, chosen))
        return page.document(path.name or "Folder", head + page.folder_view(sheet))

    one = remember(path, "", lambda: measurement.of_file(path))
    result = compare.against(one, chosen) if chosen else None
    return page.document(path.name, head + page.file_view(one, result, chosen))


def mastering(root: Path, job_id: str) -> tuple[str, int]:
    job = JOBS.get(job_id)
    if job is None:
        head = page.controls(choices(root), targets(), "", NONE, "", SAID)
        return page.document("Bench", head + page.said(
            "No such run", "Nothing here is mastering that.")), 404
    head = page.controls(choices(root), targets(), job["what"], job["target"],
                         job["out_dir"], job.get("said"))
    again = page.WORKING_AGAIN_IN_S if job["running"] else None
    return page.document("Mastering" if job["running"] else "Mastered",
                         head + page.mastering_view(job), again), 200


def handler_for(root: Path):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def send_bytes(self, status: int, kind: str, body: bytes, cache: str | None = None):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            if cache:
                self.send_header("Cache-Control", cache)
            if cache == NO_CACHE:
                self.send_header("Pragma", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def send_font(self, name: str) -> None:
            if name not in typeface.files():
                self.send_error(404)
                return
            path = typeface.FONT_DIR / name
            if not path.is_file():
                self.send_error(404)
                return
            self.send_bytes(200, "font/woff2", path.read_bytes(), "max-age=86400")

        def do_POST(self):
            """Mastering writes files, so it is not a GET. The redirect afterwards is
            what stops a reload of the result page starting the run a second time."""
            if urlparse(self.path).path != page.MASTER_URL:
                self.send_error(404)
                return
            length = min(int(self.headers.get("Content-Length") or 0), BODY_LIMIT)
            form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
            said = typed(form)
            SAID.update(said)
            job_id = start_master(root, form.get("what", [""])[0],
                                  form.get("target", [NONE])[0], said)
            self.send_response(303)
            self.send_header("Location", f"{page.MASTER_URL}?job={job_id}")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            route = urlparse(self.path).path
            if route.startswith(typeface.FONT_URL + "/"):
                self.send_font(route[len(typeface.FONT_URL) + 1:])
                return
            query = parse_qs(urlparse(self.path).query)
            what = query.get("what", [""])[0]
            target_name = query.get("target", [NONE])[0]
            if route == page.MASTER_URL:
                body, status = mastering(root, query.get("job", [""])[0])
                self.send_bytes(status, HTML, body.encode("utf-8"), NO_CACHE)
                return
            try:
                body, status = render(root, what, target_name), 200
            except compare.BandSetMismatch as why:
                body = page.document("Refused", page.controls(
                    choices(root), targets(), what, target_name, "", SAID)
                    + page.said("Refused", str(why)))
                status = 409
            except Exception:
                body = page.document("Failed", page.controls(
                    choices(root), targets(), what, target_name, "", SAID)
                    + page.card("Failed", "<div class=\"inset\"><pre>"
                                + traceback.format_exc().replace("<", "&lt;") + "</pre></div>"))
                status = 500
            self.send_bytes(status, HTML, body.encode("utf-8"), NO_CACHE)

        def log_message(self, fmt, *args):
            sys.stderr.write(f"{self.address_string()} {fmt % args}\n")

    return Handler


def server_on(root: Path, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), handler_for(root))


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT
    missing = typeface.missing()
    if missing:
        print("missing font files, the page would fall back to a substitute face:")
        for name in missing:
            print(f"  {name}")
        return 2
    server = server_on(root, port)
    print(f"serving {root} on http://127.0.0.1:{port}")
    print(f"targets: {', '.join(targets()) or 'none'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
