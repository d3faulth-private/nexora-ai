from __future__ import annotations

import os
import shlex
import time
import webbrowser
from dataclasses import dataclass, field

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from datetime import datetime, timezone

from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.seed import reset_operational_workspace, seed_demo

from . import diagnostics
from .branding import VERSION, banner, fail, info, ok, prompt, warn
from .runtime import ServerRuntime
from .theme import D3_STYLE, message_tokens


HELP = """D3FAULTH // NEXORA COMMANDS

  status          system and runtime status
  doctor          dependency / service diagnostic
  revenue         commercial ROI snapshot
  opportunities   highest-value open opportunities
  leads           recent leads
  agents          AI workforce status
  jobs            automation queue
  connectors      integration status
  workspace reset restore local HVAC operating dataset (confirmation required)
  why [last]      explain the latest recorded problem
  logs [--tail N] show managed server logs
  debug last      show the latest managed server failure/log tail
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
        self._history = InMemoryHistory()
        self._completer = WordCompleter(
            [
                "status", "doctor", "revenue", "opportunities", "leads", "agents",
                "jobs", "connectors", "workspace", "workspace reset", "workspace reset --confirm",
                "why", "logs", "debug", "serve", "stop", "restart", "open",
                "history", "version", "clear", "help", "exit", "quit", "q",
            ],
            ignore_case=True,
            sentence=True,
        )
        self._session = PromptSession(
            history=self._history,
            completer=self._completer,
            style=D3_STYLE,
            complete_while_typing=False,
        )

    def _emit(self, level: str, message: str) -> None:
        print_formatted_text(message_tokens(level, message), style=D3_STYLE)

    def initialize(self) -> None:
        self.settings.validate_runtime()
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            seed_demo(db)

    def run(self) -> int:
        self.initialize()
        print(banner(self.settings.app_env))
        self._emit("info", "Type 'help' for commands. Ctrl+C cancels input; 'exit' performs graceful shutdown.")
        while not self._closing:
            try:
                raw = self._session.prompt(prompt(self.settings.app_env)).strip()
            except KeyboardInterrupt:
                print()
                self.stats.warnings += 1
                self._emit("warn", "Input cancelled. Use 'exit' for graceful shutdown.")
                continue
            except EOFError:
                print()
                return self.shutdown()

            if not raw:
                continue

            commands = [line.strip() for line in raw.splitlines() if line.strip()]
            if len(commands) > 1:
                self._emit("info", str(len(commands)) + " pasted commands detected; executing sequentially.")

            for raw_command in commands:
                command = self._normalize(raw_command)
                self._record(raw_command)
                try:
                    if self.execute(command):
                        return self.shutdown()
                except KeyboardInterrupt:
                    self.stats.warnings += 1
                    print()
                    self._emit("warn", "Operation cancelled by operator.")
                    break
                except Exception as exc:
                    self.stats.failures += 1
                    self._emit("fail", str(exc))
                    self._emit("info", "Run 'why last' or 'doctor' for diagnostics.")
                    if len(commands) > 1:
                        self._emit("warn", "Remaining pasted commands were not executed because the previous command failed.")
                    break
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
        elif command == "workspace":
            if len(parts) < 2 or parts[1].lower() != "reset":
                raise ValueError("Usage: workspace reset [--confirm]")
            self.reset_workspace("--confirm" in parts[2:])
        elif command == "why":
            self._emit("info", diagnostics.explain_last_problem())
        elif command == "logs":
            limit = 50
            if "--tail" in parts:
                index = parts.index("--tail")
                if index + 1 >= len(parts):
                    raise ValueError("Usage: logs --tail <number>")
                limit = int(parts[index + 1])
            print(self.runtime.logs_tail(limit))
        elif command == "debug":
            if len(parts) > 1 and parts[1].lower() != "last":
                raise ValueError("Usage: debug last")
            print(self.runtime.debug_last())
        elif command == "history":
            print("\n".join(self.stats.history) or "No commands yet.")
        elif command == "serve":
            self._emit("info", "Starting Nexora and waiting for /health...")
            if self.runtime.start():
                self._emit("ok", "Nexora server started: " + self.runtime.base_url)
                self._emit("ok", "Health check: " + self.runtime.health())
                if self.runtime.pid:
                    self._emit("info", "Managed PID: " + str(self.runtime.pid))
            else:
                self._emit("warn", "Nexora server is already running from this console.")
        elif command == "stop":
            if self.runtime.stop():
                self._emit("ok", "Nexora server stopped.")
            else:
                self._emit("warn", "No managed Nexora server is running.")
        elif command == "restart":
            self._emit("info", "Restarting Nexora and waiting for /health...")
            self.runtime.restart()
            self._emit("ok", "Nexora server restarted: " + self.runtime.health())
        elif command == "open":
            webbrowser.open("http://127.0.0.1:8000")
            self._emit("ok", "Dashboard open request sent to the browser.")
        else:
            self.stats.warnings += 1
            self._emit("warn", "Unknown command: " + command)
            self._emit("info", "Type 'help' for available commands.")
        return False

    def show_status(self) -> None:
        data = diagnostics.snapshot()
        print("D3FAULTH // NEXORA STATUS")
        runtime_health = self.runtime.health()
        print("  server........ " + ("RUNNING" if self.runtime.running else "NOT MANAGED"))
        print("  server health. " + runtime_health)
        print("  managed pid... " + (str(self.runtime.pid) if self.runtime.pid else "—"))
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
        print("  System health. " + data["overall_health"])
        print("  Integrations")
        for item in data["connectors"]:
            suffix = " (" + item["mode"] + ")" if item["health"] == "HEALTHY" else ""
            print("    " + item["slug"].ljust(12) + item["health"] + suffix)

        actionable = [
            item for item in data["connectors"]
            if item["health"] in {"DISCONNECTED", "DEGRADED", "FAILED"}
        ]
        optional = [
            item for item in data["connectors"]
            if item["health"] == "NOT CONFIGURED"
        ]

        if data["overall_health"] == "FAILED":
            self._emit("fail", "Core diagnostic failed.")
        elif actionable:
            self.stats.warnings += 1
            self._emit("warn", str(len(actionable)) + " configured integration(s) require attention.")
        elif optional:
            self._emit("ok", "Core system healthy. " + str(len(optional)) + " optional integration(s) are not configured.")
        else:
            self._emit("ok", "Core diagnostic is healthy.")

    def show_revenue(self) -> None:
        revenue = diagnostics.snapshot()["revenue"]
        if not revenue:
            self._emit("warn", "Revenue data is unavailable.")
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
            self._emit("ok", "No open revenue opportunities detected.")
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

    def reset_workspace(self, confirmed: bool = False) -> None:
        if self.settings.app_env == "production" or not self.settings.demo_mode:
            raise RuntimeError("Workspace reset is available only in local development/test mode.")
        if self.runtime.running:
            raise RuntimeError("Stop the managed Nexora server before resetting the local workspace.")
        if not confirmed:
            self._emit("warn", "This replaces local leads, conversations, appointments, revenue, tasks, approvals, and activity.")
            self._emit("info", "Run 'workspace reset --confirm' to restore the standard HVAC operating dataset.")
            return

        with SessionLocal() as db:
            workspace = reset_operational_workspace(db)
        self._emit("ok", "Operational HVAC workspace restored: " + workspace.name)
        self._emit("info", "12 leads · 4 appointments · 2 completed jobs · 2 pending follow-ups · 1 approval")

    def show_connectors(self) -> None:
        items = diagnostics.snapshot()["connectors"]
        if not items:
            print("No connectors.")
            return
        for item in items:
            print(
                item["slug"]
                + " | "
                + item["health"]
                + " | "
                + item["mode"]
            )

    def shutdown(self) -> int:
        if self._closing:
            return 0
        self._closing = True
        print()
        self._emit("info", "Shutdown requested.")
        if self.runtime.running:
            self._emit("info", "Stopping managed Nexora server.")
            self.runtime.stop()
            self._emit("ok", "Server stopped.")
        elapsed = max(0, int(time.time() - self.stats.started_at))
        minutes, seconds = divmod(elapsed, 60)
        self._emit("ok", "Database sessions closed.")
        self._emit("ok", "Terminal state restored.")
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
