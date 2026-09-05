import sys
import threading
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))

import reach
import serve

REACHABILITY = "test_every_control_reaches_the_method_it_stands_behind"


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef, request):
    reach.start()
    try:
        yield
    finally:
        reach.credit_fixture(fixturedef.argname, reach.stop())


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    reach.start()
    try:
        yield
    finally:
        reach.credit_test(getattr(item, "originalname", None) or item.name,
                          reach.stop(), getattr(item, "fixturenames", ()))


def pytest_collection_modifyitems(items):
    """The reachability check reads what the session ran, so it runs after the session.
    Collection order is alphabetical and test_methods.py sits in the middle of it, where
    the check would pass on the two thirds of the suite that had run by then."""
    last = [i for i in items if i.name == REACHABILITY]
    if last:
        items[:] = [i for i in items if i.name != REACHABILITY] + last


@pytest.fixture(autouse=True)
def forget():
    """The server remembers the last thing measured and what it read, for the life of
    the process. Tests share one process, so one test landing on another's folder is a
    pass that means nothing."""
    def wipe():
        for held in (serve.LAST, serve.MEASURED, serve.SAID, serve.JOBS):
            held.clear()
        serve.NEXT_JOB[0] = 1

    wipe()
    yield
    wipe()


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
