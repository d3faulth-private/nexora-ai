from __future__ import annotations

import platform
import sys
from datetime import datetime, timezone

from sqlalchemy import func, select, text

from app.config import get_settings
from app.db import SessionLocal, engine
from app.models import Agent, AutomationJob, Connector, Lead, Workspace
from app.revenue import opportunity_list, revenue_summary


def _workspace(db):
    return db.scalar(select(Workspace).order_by(Workspace.id))


def snapshot() -> dict:
    settings = get_settings()
    data = {
        "python": platform.python_version(),
        "platform": platform.system() + " " + platform.release(),
        "environment": settings.app_env,
        "ai_provider": settings.ai_provider,
        "database": "unknown",
        "workspace": None,
        "agents_enabled": 0,
        "agents_total": 0,
        "pending_jobs": 0,
        "failed_jobs": 0,
        "connectors": [],
        "revenue": {},
        "opportunities": [],
    }

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        data["database"] = "ok"
    except Exception as exc:
        data["database"] = "error: " + str(exc)[:160]
        return data

    with SessionLocal() as db:
        workspace = _workspace(db)
        if not workspace:
            return data

        data["workspace"] = workspace.name
        agents = list(db.scalars(select(Agent).where(Agent.workspace_id == workspace.id)))
        data["agents_total"] = len(agents)
        data["agents_enabled"] = sum(1 for item in agents if item.enabled)
        data["pending_jobs"] = int(
            db.scalar(
                select(func.count(AutomationJob.id)).where(
                    AutomationJob.workspace_id == workspace.id,
                    AutomationJob.status == "pending",
                )
            )
            or 0
        )
        data["failed_jobs"] = int(
            db.scalar(
                select(func.count(AutomationJob.id)).where(
                    AutomationJob.workspace_id == workspace.id,
                    AutomationJob.status == "failed",
                )
            )
            or 0
        )
        data["connectors"] = [
            {
                "slug": item.slug,
                "status": item.status,
                "mode": item.mode,
                "last_sync_at": item.last_sync_at,
            }
            for item in db.scalars(
                select(Connector)
                .where(Connector.workspace_id == workspace.id)
                .order_by(Connector.slug)
            )
        ]
        data["revenue"] = revenue_summary(db, workspace.id)
        data["opportunities"] = opportunity_list(db, workspace.id, limit=8)
    return data


def leads(limit: int = 20) -> list[dict]:
    with SessionLocal() as db:
        workspace = _workspace(db)
        if not workspace:
            return []
        return [
            {
                "id": item.id,
                "name": item.name,
                "stage": item.stage,
                "urgency": item.urgency,
                "value": float(item.estimated_value or 0),
            }
            for item in db.scalars(
                select(Lead)
                .where(Lead.workspace_id == workspace.id)
                .order_by(Lead.created_at.desc())
                .limit(limit)
            )
        ]


def agents() -> list[dict]:
    with SessionLocal() as db:
        workspace = _workspace(db)
        if not workspace:
            return []
        return [
            {
                "slug": item.slug,
                "name": item.name,
                "enabled": item.enabled,
                "autonomy": item.autonomy_level,
            }
            for item in db.scalars(
                select(Agent)
                .where(Agent.workspace_id == workspace.id)
                .order_by(Agent.id)
            )
        ]


def jobs(limit: int = 20) -> list[dict]:
    with SessionLocal() as db:
        workspace = _workspace(db)
        if not workspace:
            return []
        return [
            {
                "id": item.id,
                "kind": item.kind,
                "status": item.status,
                "attempts": item.attempts,
                "run_at": item.run_at,
                "last_error": item.last_error,
            }
            for item in db.scalars(
                select(AutomationJob)
                .where(AutomationJob.workspace_id == workspace.id)
                .order_by(AutomationJob.created_at.desc())
                .limit(limit)
            )
        ]


def explain_last_problem() -> str:
    with SessionLocal() as db:
        workspace = _workspace(db)
        if not workspace:
            return "No workspace has been initialized."

        failed = db.scalar(
            select(AutomationJob)
            .where(
                AutomationJob.workspace_id == workspace.id,
                AutomationJob.status == "failed",
            )
            .order_by(AutomationJob.completed_at.desc(), AutomationJob.id.desc())
        )
        if failed:
            reason = failed.last_error or "No detailed error was recorded."
            return (
                "Latest failed automation: #"
                + str(failed.id)
                + " "
                + failed.kind
                + ". Reason: "
                + reason
            )

        disconnected = db.scalar(
            select(Connector)
            .where(
                Connector.workspace_id == workspace.id,
                Connector.status != "connected",
            )
            .order_by(Connector.id)
        )
        if disconnected:
            return (
                disconnected.name
                + " is "
                + disconnected.status
                + ". Connect it only if this business needs that integration."
            )

        return "No failed automation or connector problem is currently recorded."
