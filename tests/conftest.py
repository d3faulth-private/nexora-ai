from __future__ import annotations

import atexit
import os
import tempfile
from pathlib import Path


_fd, _path = tempfile.mkstemp(prefix="nexora-pytest-", suffix=".db")
os.close(_fd)
Path(_path).unlink(missing_ok=True)

os.environ["DATABASE_URL"] = "sqlite:///" + _path
os.environ["AUTOMATION_ENABLED"] = "false"
os.environ["APP_ENV"] = "test"

TEST_DATABASE_PATH = Path(_path)


def _cleanup() -> None:
    try:
        from app.db import engine

        engine.dispose()
    except Exception:
        pass
    TEST_DATABASE_PATH.unlink(missing_ok=True)


atexit.register(_cleanup)


def pytest_sessionfinish(session, exitstatus):
    _cleanup()
