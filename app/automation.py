from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from .agents import followup_message
from .config import get_settings
from .db import SessionLocal
from .integrations import gmail_send, hubspot_upsert_contact, signed_webhook
from .models import (
    Appointment,
    AutomationJob,
    Conversation,
    ConversationControl,
    Lead,
    Message,
    WorkspaceProfile,
)


_scheduler: BackgroundScheduler | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def schedule_job(
    db,
    workspace_id: int,
    kind: str,
    run_at: datetime,
    lead_id: int | None = None,
    conversation_id: int | None = None,
    payload: dict | None = None,
    max_attempts: int = 3,
) -> AutomationJob:
    job = AutomationJob(
        workspace_id=workspace_id,
        lead_id=lead_id,
        conversation_id=conversation_id,
        kind=kind,
        run_at=run_at,
        status="pending",
        payload_json=json.dumps(payload or {}),
        max_attempts=max_attempts,
    )
    db.add(job)
    db.flush()
    return job


def schedule_followup_for_lead(db, workspace_id: int, lead_id: int, conversation_id: int) -> AutomationJob:
    profile = db.scalar(
        select(WorkspaceProfile).where(WorkspaceProfile.workspace_id == workspace_id)
    )
    delay = profile.followup_after_minutes if profile else 120
    max_attempts = profile.followup_max_attempts if profile else 3
    return schedule_job(
        db,
        workspace_id=workspace_id,
        kind="lead_followup",
        run_at=utcnow() + timedelta(minutes=delay),
        lead_id=lead_id,
        conversation_id=conversation_id,
        max_attempts=max_attempts,
    )


def _human_has_control(db, conversation_id: int | None) -> bool:
    if not conversation_id:
        return False
    control = db.scalar(
        select(ConversationControl).where(
            ConversationControl.conversation_id == conversation_id
        )
    )
    return bool(control and control.mode == "human")


def _run_followup(db, job: AutomationJob) -> str:
    if not job.lead_id or not job.conversation_id:
        return "missing lead/conversation"

    lead = db.get(Lead, job.lead_id)
    conversation = db.get(Conversation, job.conversation_id)
    if not lead or not conversation:
        return "lead/conversation removed"

    if _human_has_control(db, conversation.id):
        return "human takeover active"

    confirmed = db.scalar(
        select(Appointment).where(
            Appointment.lead_id == lead.id,
            Appointment.status.in_(("confirmed", "completed")),
        )
    )
    if confirmed or lead.stage in {"booked", "completed", "lost"}:
        return "lead no longer needs follow-up"

    body = followup_message(lead.name, lead.issue)
    db.add(
        Message(
            conversation_id=conversation.id,
            direction="outbound",
            actor="followup",
            body=body,
        )
    )
    lead.last_contacted_at = utcnow()
    if lead.stage == "new":
        lead.stage = "contacted"

    if lead.email:
        try:
            gmail_send(
                db,
                job.workspace_id,
                lead.email,
                "Following up on your service request",
                body,
            )
        except Exception:
            pass

    try:
        hubspot_upsert_contact(
            db,
            job.workspace_id,
            {
                "name": lead.name,
                "email": lead.email,
                "phone": lead.phone,
                "zip_code": lead.zip_code,
            },
        )
    except Exception:
        pass

    try:
        signed_webhook(
            db,
            job.workspace_id,
            "lead.followup",
            {
                "lead_id": lead.id,
                "name": lead.name,
                "stage": lead.stage,
            },
        )
    except Exception:
        pass

    return "follow-up sent"


def run_due_jobs_once() -> int:
    processed = 0
    with SessionLocal() as db:
        jobs = list(
            db.scalars(
                select(AutomationJob)
                .where(
                    AutomationJob.status == "pending",
                    AutomationJob.run_at <= utcnow(),
                )
                .order_by(AutomationJob.run_at)
                .limit(50)
            )
        )

        for job in jobs:
            job.status = "running"
            job.attempts += 1
            db.commit()

            try:
                if job.kind == "lead_followup":
                    detail = _run_followup(db, job)
                else:
                    detail = "unknown job kind"

                job.status = "completed"
                job.completed_at = utcnow()
                job.last_error = detail
                db.commit()
                processed += 1
            except Exception as exc:
                job.last_error = str(exc)[:1000]
                if job.attempts >= job.max_attempts:
                    job.status = "failed"
                else:
                    job.status = "pending"
                    job.run_at = utcnow() + timedelta(minutes=5 * job.attempts)
                db.commit()

    return processed


def start_scheduler() -> None:
    global _scheduler
    settings = get_settings()
    if not settings.automation_enabled or _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        run_due_jobs_once,
        "interval",
        seconds=max(5, settings.automation_poll_seconds),
        id="nexora_due_jobs",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
