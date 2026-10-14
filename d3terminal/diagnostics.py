from __future__ import annotations

import platform

from sqlalchemy import func, select, text

from app.config import get_settings
from app.db import SessionLocal, engine
from app.models import Agent, AutomationJob, Connector, Lead, Workspace
from app.revenue import opportunity_list, revenue_summary


HEALTHY = "HEALTHY"
NOT_CONFIGURED = "NOT CONFIGURED"
DISCONNECTED = "DISCONNECTED"
DEGRADED = "DEGRADED"
FAILED = "FAILED"


def _workspace(db):
    return db.scalar(select(Workspace).order_by(Workspace.id))


def connector_health(item: Connector) -> str:
    settings = get_settings()
    configured = item.mode == "real" or (item.config_json or "{}") not in {"", "{}"}
    if item.slug == "google":
        configured = configured or bool(settings.google_client_id and settings.google_client_secret)
    elif item.slug == "hubspot":
        configured = configured or bool(settings.hubspot_private_app_token)
    elif item.slug == "webhook":
        configured = configured or bool(settings.outbound_webhook_url)

    raw = (item.status or "").lower()
    if raw == "connected":
        return HEALTHY
    if raw in {"failed", "error"}:
        return FAILED
    if raw == "degraded":
        return DEGRADED
    if configured:
        return DISCONNECTED
    return NOT_CONFIGURED


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
        "overall_health": HEALTHY,
    }

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        data["database"] = "ok"
    except Exception as exc:
        data["database"] = "error: " + str(exc)[:160]
        data["overall_health"] = FAILED
        return data

    with SessionLocal() as db:
        workspace = _workspace(db)
        if not workspace:
            data["overall_health"] = DEGRADED
            return data

        data["workspace"] = workspace.name
        agents = list(db.scalars(select(Agent).where(Agent.workspace_id == workspace.id)))
        data["agents_total"] = len(agents)
        data["agents_enabled"] = sum(1 for item in agents if item.enabled)
        data["pending_jobs"] = int(
            db.scalar(select(func.count(AutomationJob.id)).where(
                AutomationJob.workspace_id == workspace.id,
                AutomationJob.status == "pending",
            )) or 0
        )
        data["failed_jobs"] = int(
            db.scalar(select(func.count(AutomationJob.id)).where(
                AutomationJob.workspace_id == workspace.id,
                AutomationJob.status == "failed",
            )) or 0
        )

        connector_rows = list(db.scalars(
            select(Connector).where(Connector.workspace_id == workspace.id).order_by(Connector.slug)
        ))
        data["connectors"] = [
            {
                "slug": item.slug,
                "name": item.name,
                "status": item.status,
                "mode": item.mode,
                "health": connector_health(item),
                "last_sync_at": item.last_sync_at,
            }
            for item in connector_rows
        ]
        data["revenue"] = revenue_summary(db, workspace.id)
        data["opportunities"] = opportunity_list(db, workspace.id, limit=8)

    if data["failed_jobs"] or any(x["health"] == FAILED for x in data["connectors"]):
        data["overall_health"] = DEGRADED
    elif any(x["health"] in {DISCONNECTED, DEGRADED} for x in data["connectors"]):
        data["overall_health"] = DEGRADED
    else:
        data["overall_health"] = HEALTHY
    return data


def leads(limit: int = 20) -> list[dict]:
    with SessionLocal() as db:
        workspace = _workspace(db)
        if not workspace:
            return []
        return [
            {"id": item.id, "name": item.name, "stage": item.stage, "urgency": item.urgency, "value": float(item.estimated_value or 0)}
            for item in db.scalars(
                select(Lead).where(Lead.workspace_id == workspace.id).order_by(Lead.created_at.desc()).limit(limit)
            )
        ]


def agents() -> list[dict]:
    with SessionLocal() as db:
        workspace = _workspace(db)
        if not workspace:
            return []
        return [
            {"slug": item.slug, "name": item.name, "enabled": item.enabled, "autonomy": item.autonomy_level}
            for item in db.scalars(select(Agent).where(Agent.workspace_id == workspace.id).order_by(Agent.id))
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
                select(AutomationJob).where(AutomationJob.workspace_id == workspace.id).order_by(AutomationJob.created_at.desc()).limit(limit)
            )
        ]


def explain_last_problem() -> str:
    data = snapshot()
    if data["database"] != "ok":
        return "Database health is FAILED: " + str(data["database"])

    with SessionLocal() as db:
        workspace = _workspace(db)
        if not workspace:
            return "No workspace has been initialized."
        failed = db.scalar(
            select(AutomationJob)
            .where(AutomationJob.workspace_id == workspace.id, AutomationJob.status == "failed")
            .order_by(AutomationJob.completed_at.desc(), AutomationJob.id.desc())
        )
        if failed:
            return "Latest failed automation #" + str(failed.id) + " " + failed.kind + ": " + (failed.last_error or "No detail recorded.")

    actionable = [
        item for item in data["connectors"]
        if item["health"] in {DISCONNECTED, DEGRADED, FAILED}
    ]
    if actionable:
        item = actionable[0]
        return item["name"] + " is " + item["health"] + ". Check its credentials, provider state, and reconnect flow."

    optional = [item for item in data["connectors"] if item["health"] == NOT_CONFIGURED]
    if optional:
        return "Core system is healthy. " + str(len(optional)) + " optional connector(s) are NOT CONFIGURED."

    return "No failed automation or connector problem is currently recorded."
