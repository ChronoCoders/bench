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


def out_dir_for(path: Path) -> Path:
    """Beside what was chosen, never inside it.

    The mastering layer refuses to write into the folder its source is in. This is that
    rule turned into a place rather than an error: a folder gets one next to it with the
    same name, and a single file gets a Mastered folder beside the file.
    """
    if path.is_dir():
        return path.parent / (path.name + MASTERED_SUFFIX)
    return path.parent / MASTERED_FOLDER


JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _refusal(root: Path, what: str, target_name: str) -> str | None:
    if not what:
        return "nothing is chosen to master"
    if not target_name or target_name == NONE:
        return ("no target is chosen, and every correction here is derived from the "
                "distance to one")
    path = (root / what.rstrip("/")).resolve()
    if not str(path).startswith(str(root)):
        return "that path is outside the folder being served"
    if not path.exists():
        return f"{what} is not there any more"
    return None


def start_master(root: Path, what: str, target_name: str) -> str:
    """The id of the run to watch. One at a time: mastering uses the whole machine, and
    two at once would be writing into the same folder under the same names."""
    refused = _refusal(root, what, target_name)
    with JOBS_LOCK:
        if refused is None:
            already = next((k for k, v in JOBS.items() if v["running"]), None)
            if already is not None:
                return already
        job_id = str(len(JOBS) + 1)
        job = {"what": what, "target": target_name, "running": refused is None,
               "finished": 0, "total": 0, "at": None, "done": [], "failed": [],
               "failure": None, "refused": refused, "out_dir": ""}
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
            job["done"], job["failed"] = master.run_each(paths, chosen, out_dir, watching)
        except Exception:
            job["failure"] = traceback.format_exc()
        finally:
            job["at"], job["finished"] = None, job["total"]
            job["running"] = False

    threading.Thread(target=work, daemon=True).start()
    return job_id


def targets() -> list[str]:
    return sorted(p.stem for p in TARGETS.glob("*.json")) if TARGETS.is_dir() else []


def render(root: Path, what: str, target_name: str) -> str:
    head = page.controls(choices(root), targets(), what, target_name)
    if not what:
        return page.document("Bench", head + "<p>Choose a file or a folder, then measure.</p>")

    chosen = None
    if target_name and target_name != NONE:
        chosen = compare.load(TARGETS / f"{target_name}.json")

    path = (root / what.rstrip("/")).resolve()
    if not str(path).startswith(str(root)):
        return page.document("Bench", head + "<p>That path is outside the folder being served.</p>")

    if path.is_dir():
        sheet = folder.measure(path, chosen)
        return page.document(path.name or "Folder", head + page.folder_view(sheet))

    one = measurement.of_file(path)
    result = compare.against(one, chosen) if chosen else None
    return page.document(path.name, head + page.file_view(one, result, chosen))


def mastering(root: Path, job_id: str) -> tuple[str, int]:
    job = JOBS.get(job_id)
    if job is None:
        head = page.controls(choices(root), targets(), "", NONE)
        return page.document("Bench", head + "<h2>No such run</h2>"
                             "<p>Nothing here is mastering that.</p>"), 404
    head = page.controls(choices(root), targets(), job["what"], job["target"])
    again = page.WORKING_AGAIN_IN_S if job["running"] else None
    return page.document("Mastering" if job["running"] else "Mastered",
                         head + page.mastering_view(job), again), 200


def handler_for(root: Path):
    class Handler(BaseHTTPRequestHandler):
        def send_bytes(self, status: int, kind: str, body: bytes, cache: str | None = None):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            if cache:
                self.send_header("Cache-Control", cache)
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
            job_id = start_master(root, form.get("what", [""])[0],
                                  form.get("target", [NONE])[0])
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
                self.send_bytes(status, "text/html; charset=utf-8", body.encode("utf-8"))
                return
            try:
                body, status = render(root, what, target_name), 200
            except compare.BandSetMismatch as why:
                body = page.document("Refused", page.controls(choices(root), targets(), what,
                                                              target_name)
                                     + f"<h2>Refused</h2><p>{why}</p>")
                status = 409
            except Exception:
                body = page.document("Failed", page.controls(choices(root), targets(), what,
                                                             target_name)
                                     + "<h2>Failed</h2><pre>"
                                     + traceback.format_exc().replace("<", "&lt;") + "</pre>")
                status = 500
            self.send_bytes(status, "text/html; charset=utf-8", body.encode("utf-8"))

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
