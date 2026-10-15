from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx


_SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)(api[_-]?key[=:]\s*)[^\s]+"),
    re.compile(r"(?i)(token[=:]\s*)[^\s]+"),
    re.compile(r"(?i)(secret[=:]\s*)[^\s]+"),
    re.compile(r"(?i)(password[=:]\s*)[^\s]+"),
]


class ServerRuntime:
    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.host = "127.0.0.1"
        self.port = 8000
        self.log_path: Path | None = None
        self._log_handle = None
        self.last_error: str = ""
        self.last_health: str = "NOT MANAGED"

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @property
    def pid(self) -> int | None:
        return self.process.pid if self.running and self.process else None

    @property
    def base_url(self) -> str:
        return "http://" + self.host + ":" + str(self.port)

    def _new_log_file(self) -> None:
        self._close_log_handle()
        fd, path = tempfile.mkstemp(prefix="nexora-server-", suffix=".log")
        os.close(fd)
        self.log_path = Path(path)
        self._log_handle = self.log_path.open("a", encoding="utf-8", buffering=1)

    def _close_log_handle(self) -> None:
        if self._log_handle is not None:
            try:
                self._log_handle.flush()
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None

    def _health_ok(self) -> bool:
        try:
            response = httpx.get(self.base_url + "/health", timeout=0.75)
            return response.status_code == 200
        except Exception:
            return False

    def start(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        health_timeout: float = 15.0,
    ) -> bool:
        if self.running:
            return False

        self.host = host
        self.port = port
        self.last_error = ""
        self.last_health = "STARTING"
        self._new_log_file()

        assert self._log_handle is not None
        project_root = Path(__file__).resolve().parents[1]
        child_env = os.environ.copy()
        child_env["PYTHONUNBUFFERED"] = "1"
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                host,
                "--port",
                str(port),
            ],
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(project_root),
            env=child_env,
        )

        deadline = time.monotonic() + health_timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                code = self.process.returncode
                self.last_health = "FAILED"
                self.last_error = (
                    "Nexora server exited during startup with code "
                    + str(code)
                    + ". "
                    + self.logs_tail(12)
                ).strip()
                self._close_log_handle()
                self.process = None
                raise RuntimeError(self.last_error)

            if self._health_ok():
                self.last_health = "HEALTHY"
                return True
            time.sleep(0.15)

        self.last_health = "FAILED"
        self.last_error = (
            "Nexora server did not become healthy within "
            + format(health_timeout, ".1f")
            + " seconds. "
            + self.logs_tail(12)
        ).strip()
        self.stop()
        raise RuntimeError(self.last_error)

    def health(self) -> str:
        if not self.running:
            return self.last_health if self.last_health == "FAILED" else "NOT MANAGED"
        self.last_health = "HEALTHY" if self._health_ok() else "DEGRADED"
        return self.last_health

    def stop(self, timeout: float = 5.0) -> bool:
        if not self.running:
            self.process = None
            self._close_log_handle()
            if self.last_health != "FAILED":
                self.last_health = "NOT MANAGED"
            return False

        assert self.process is not None
        self.process.terminate()
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)
        finally:
            self.process = None
            self._close_log_handle()
            if self.last_health != "FAILED":
                self.last_health = "STOPPED"
        return True

    def restart(self) -> None:
        self.stop()
        self.start(self.host, self.port)

    def logs_tail(self, limit: int = 50) -> str:
        if not self.log_path or not self.log_path.exists():
            return "No managed server logs are available."
        try:
            lines = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            return "Unable to read server logs: " + str(exc)
        selected = lines[-max(1, min(limit, 500)) :]
        return "\n".join(self._redact(line) for line in selected) or "Server log is empty."

    def debug_last(self) -> str:
        if self.last_error:
            return self._redact(self.last_error)
        return self.logs_tail(30)

    @staticmethod
    def _redact(text: str) -> str:
        output = text
        for pattern in _SECRET_PATTERNS:
            output = pattern.sub(lambda match: match.group(1) + "[REDACTED]", output)
        return output
