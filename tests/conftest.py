import sys
import threading
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))

import serve


@pytest.fixture
def serving(tmp_path):
    """The bench on a port of its own, over an empty folder. A test puts into tmp_path
    whatever it wants the server to find, before or after this starts: the folder is
    read once per request."""
    httpd = serve.server_on(tmp_path, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)
