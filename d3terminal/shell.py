from __future__ import annotations

import os
import shlex
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.seed import seed_demo

from . import diagnostics
from .branding import VERSION, banner, fail, info, ok, prompt, warn
from .runtime import ServerRuntime


HELP = """D3FAULTH // NEXORA COMMANDS

  status          system and runtime status
  doctor          dependency / service diagnostic
  revenue         commercial ROI snapshot
  opportunities   highest-value open opportunities
  leads           recent leads
  agents          AI workforce status
  jobs            automation queue
  connectors      integration status
  why [last]      explain the latest recorded problem
  serve           start local Nexora web server
  stop            stop server started by this console
  restart         restart local Nexora server
  open            open the dashboard in your browser
  history         session command history
  version         build information
  clear           clear terminal
  help            show commands
  exit | quit | q graceful shutdown

Natural shortcuts:
  what's wrong
  what needs my attention
  who should i call today
  show revenue
"""


@dataclass
class SessionStats:
    started_at: float = field(default_factory=time.time)
    commands: int = 0
    failures: int = 0
    warnings: int = 0
    history: list[str] = field(default_factory=list)


class OperatorShell:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.runtime = ServerRuntime()
        self.stats = SessionStats()
        self._closing = False

    def initialize(self) -> None:
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            seed_demo(db)

    def run(self) -> int:
        self.initialize()
        print(banner(self.settings.app_env))
        print(info("Type 'help' for commands. Ctrl+C cancels input; 'exit' performs graceful shutdown."))
        while not self._closing:
            try:
                raw = input(prompt(self.settings.app_env)).strip()
            except KeyboardInterrupt:
                print()
                self.stats.warnings += 1
                print(warn("Input cancelled. Use 'exit' for graceful shutdown."))
                continue
            except EOFError:
                print()
                return self.shutdown()

            if not raw:
                continue

            command = self._normalize(raw)
            self._record(raw)
            try:
                if self.execute(command):
                    return self.shutdown()
            except KeyboardInterrupt:
                self.stats.warnings += 1
                print()
                print(warn("Operation cancelled by operator."))
            except Exception as exc:
                self.stats.failures += 1
                print(fail(str(exc)))
                print(info("Run 'why last' or 'doctor' for diagnostics."))
        return self.shutdown()

    def _normalize(self, raw: str) -> str:
        lowered = " ".join(raw.lower().replace("’", "'").split())
        aliases = {
            "st": "status",
            "ag": "agents",
            "j": "jobs",
            "q": "exit",
            "what's wrong": "doctor",
            "whats wrong": "doctor",
            "what needs my attention": "opportunities",
            "who should i call today": "opportunities",
            "show revenue": "revenue",
        }
        return aliases.get(lowered, raw)

    def _record(self, raw: str) -> None:
        self.stats.commands += 1
        safe = raw
        lowered = raw.lower()
        if any(word in lowered for word in ("token", "secret", "password", "key=")):
            safe = "[REDACTED COMMAND]"
        self.stats.history.append(
            datetime.now(timezone.utc).strftime("%H:%M:%S") + "  " + safe
        )

    def execute(self, raw: str) -> bool:
        parts = shlex.split(raw)
        if not parts:
            return False
        command = parts[0].lower()

        if command in {"exit", "quit", "q"}:
            return True
        if command == "help":
            print(HELP)
        elif command == "clear":
            os.system("cls" if os.name == "nt" else "clear")
        elif command == "version":
            print("D3FAULTH // NEXORA AI " + VERSION)
        elif command == "status":
            self.show_status()
        elif command == "doctor":
            self.show_doctor()
        elif command == "revenue":
            self.show_revenue()
        elif command == "opportunities":
            self.show_opportunities()
        elif command == "leads":
            self.show_leads()
        elif command == "agents":
            self.show_agents()
        elif command == "jobs":
            self.show_jobs()
        elif command == "connectors":
            self.show_connectors()
        elif command == "why":
            print(info(diagnostics.explain_last_problem()))
        elif command == "history":
            print("\n".join(self.stats.history) or "No commands yet.")
        elif command == "serve":
            if self.runtime.start():
                print(ok("Nexora server started at http://127.0.0.1:8000"))
            else:
                print(warn("Nexora server is already running from this console."))
        elif command == "stop":
            if self.runtime.stop():
                print(ok("Nexora server stopped."))
            else:
                print(warn("No managed Nexora server is running."))
        elif command == "restart":
            self.runtime.restart()
            print(ok("Nexora server restarted."))
        elif command == "open":
            webbrowser.open("http://127.0.0.1:8000")
            print(ok("Dashboard open request sent to the browser."))
        else:
            self.stats.warnings += 1
            print(warn("Unknown command: " + command))
            print(info("Type 'help' for available commands."))
        return False

    def show_status(self) -> None:
        data = diagnostics.snapshot()
        print("D3FAULTH // NEXORA STATUS")
        print("  server........ " + ("RUNNING" if self.runtime.running else "NOT MANAGED"))
        print("  database...... " + str(data["database"]))
        print("  workspace..... " + str(data["workspace"] or "not initialized"))
        print("  agents........ " + str(data["agents_enabled"]) + "/" + str(data["agents_total"]) + " enabled")
        print("  pending jobs.. " + str(data["pending_jobs"]))
        print("  failed jobs... " + str(data["failed_jobs"]))

    def show_doctor(self) -> None:
        data = diagnostics.snapshot()
        print("D3FAULTH // SYSTEM DIAGNOSTIC")
        print("  Python........ " + data["python"])
        print("  Platform...... " + data["platform"])
        print("  Environment... " + data["environment"])
        print("  Database...... " + str(data["database"]))
        print("  AI provider... " + data["ai_provider"])
        print("  Agents........ " + str(data["agents_enabled"]) + "/" + str(data["agents_total"]) + " enabled")
        print("  Pending jobs.. " + str(data["pending_jobs"]))
        print("  Failed jobs... " + str(data["failed_jobs"]))
        problems = [
            item for item in data["connectors"] if item["status"] != "connected"
        ]
        if data["database"] != "ok" or data["failed_jobs"]:
            print(fail("Diagnostic requires attention."))
        elif problems:
            self.stats.warnings += 1
            print(warn(str(len(problems)) + " connector(s) are not connected."))
        else:
            print(ok("Core diagnostic is healthy."))

    def show_revenue(self) -> None:
        revenue = diagnostics.snapshot()["revenue"]
        if not revenue:
            print(warn("Revenue data is unavailable."))
            return
        print("NEXORA // COMMERCIAL SNAPSHOT")
        print("  pipeline........... $" + format(revenue["pipeline"], ",.0f"))
        print("  booked pipeline.... $" + format(revenue["booked_pipeline"], ",.0f"))
        print("  completed revenue.. $" + format(revenue["completed_revenue"], ",.0f"))
        print("  recovered revenue.. $" + format(revenue["recovered_revenue"], ",.0f"))
        print("  open opportunity... $" + format(revenue["open_opportunity"], ",.0f"))

    def show_opportunities(self) -> None:
        items = diagnostics.snapshot()["opportunities"]
        if not items:
            print(ok("No open revenue opportunities detected."))
            return
        total = sum(item["estimated_value"] for item in items)
        print("NEXORA // OPPORTUNITY ENGINE")
        print("  visible opportunity.. $" + format(total, ",.0f"))
        for item in items:
            print(
                "  #"
                + str(item["lead_id"])
                + " "
                + item["name"]
                + " | "
                + item["stage"]
                + " | $"
                + format(item["estimated_value"], ",.0f")
                + " | idle "
                + str(item["hours_idle"])
                + "h"
            )
            print("     -> " + item["recommended_action"])

    def show_leads(self) -> None:
        for item in diagnostics.leads():
            print(
                "#"
                + str(item["id"])
                + " "
                + item["name"]
                + " | "
                + item["stage"]
                + " | "
                + item["urgency"]
                + " | $"
                + format(item["value"], ",.0f")
            )

    def show_agents(self) -> None:
        for item in diagnostics.agents():
            print(
                item["name"]
                + " | "
                + ("ON" if item["enabled"] else "OFF")
                + " | "
                + item["autonomy"]
            )

    def show_jobs(self) -> None:
        items = diagnostics.jobs()
        if not items:
            print("No automation jobs.")
            return
        for item in items:
            print(
                "#"
                + str(item["id"])
                + " "
                + item["kind"]
                + " | "
                + item["status"]
                + " | attempts "
                + str(item["attempts"])
            )

    def show_connectors(self) -> None:
        items = diagnostics.snapshot()["connectors"]
        if not items:
            print("No connectors.")
            return
        for item in items:
            print(
                item["slug"]
                + " | "
                + item["status"]
                + " | "
                + item["mode"]
            )

    def shutdown(self) -> int:
        if self._closing:
            return 0
        self._closing = True
        print()
        print(info("Shutdown requested."))
        if self.runtime.running:
            print(info("Stopping managed Nexora server."))
            self.runtime.stop()
            print(ok("Server stopped."))
        elapsed = max(0, int(time.time() - self.stats.started_at))
        minutes, seconds = divmod(elapsed, 60)
        print(ok("Database sessions closed."))
        print(ok("Terminal state restored."))
        print()
        print("D3FAULTH // SESSION SUMMARY")
        print("  duration.... " + str(minutes).zfill(2) + ":" + str(seconds).zfill(2))
        print("  commands.... " + str(self.stats.commands))
        print("  warnings.... " + str(self.stats.warnings))
        print("  failures.... " + str(self.stats.failures))
        print()
        print("NEXORA OFFLINE")
        print("D3FAULTH // EXIT 0")
        return 0
