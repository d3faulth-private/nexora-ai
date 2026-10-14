from __future__ import annotations

import subprocess
import sys
import time


class ServerRuntime:
    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, host: str = "127.0.0.1", port: int = 8000) -> bool:
        if self.running:
            return False
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
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.35)
        if self.process.poll() is not None:
            self.process = None
            raise RuntimeError("Nexora server exited during startup.")
        return True

    def stop(self, timeout: float = 5.0) -> bool:
        if not self.running:
            self.process = None
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
        return True

    def restart(self) -> None:
        self.stop()
        self.start()
