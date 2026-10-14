from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Appointment, Conversation, Lead, Message, RevenueEvent


ACTIVE_STAGES = ("new", "contacted", "qualified")
CLOSED_STAGES = ("lost", "completed")


def _existing_event(db: Session, workspace_id: int, lead_id: int, event_type: str) -> RevenueEvent | None:
    return db.scalar(
        select(RevenueEvent).where(
            RevenueEvent.workspace_id == workspace_id,
            RevenueEvent.lead_id == lead_id,
            RevenueEvent.event_type == event_type,
        )
    )


def lead_was_recovered(db: Session, workspace_id: int, lead_id: int) -> bool:
    followup = db.scalar(
        select(Message.id)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.workspace_id == workspace_id,
            Conversation.lead_id == lead_id,
            Message.actor == "followup",
        )
        .limit(1)
    )
    return followup is not None


def record_booking_attribution(db: Session, workspace_id: int, lead: Lead, source: str = "booking") -> None:
    amount = float(lead.estimated_value or 0)
    if not _existing_event(db, workspace_id, lead.id, "booked"):
        db.add(
            RevenueEvent(
                workspace_id=workspace_id,
                lead_id=lead.id,
                event_type="booked",
                amount=amount,
                attribution="nexora_assisted",
                source=source,
                note="Lead converted to a confirmed appointment.",
            )
        )

    if lead_was_recovered(db, workspace_id, lead.id) and not _existing_event(
        db, workspace_id, lead.id, "recovered"
    ):
        db.add(
            RevenueEvent(
                workspace_id=workspace_id,
                lead_id=lead.id,
                event_type="recovered",
                amount=amount,
                attribution="followup",
                source=source,
                note="Booked after Nexora follow-up activity.",
            )
        )


def record_completed_revenue(
    db: Session,
    workspace_id: int,
    lead: Lead,
    actual_amount: float | None = None,
    source: str = "operator",
) -> RevenueEvent:
    amount = float(actual_amount if actual_amount is not None else lead.estimated_value or 0)
    existing = _existing_event(db, workspace_id, lead.id, "completed")
    if existing:
        existing.amount = amount
        existing.source = source
        existing.note = "Completed revenue updated."
        return existing

    event = RevenueEvent(
        workspace_id=workspace_id,
        lead_id=lead.id,
        event_type="completed",
        amount=amount,
        attribution="nexora_assisted",
        source=source,
        note="Completed job revenue attributed to this lead.",
    )
    db.add(event)
    return event


def revenue_summary(db: Session, workspace_id: int) -> dict:
    pipeline = db.scalar(
        select(func.coalesce(func.sum(Lead.estimated_value), 0)).where(
            Lead.workspace_id == workspace_id,
            Lead.stage.notin_(CLOSED_STAGES),
        )
    )
    booked = db.scalar(
        select(func.coalesce(func.sum(RevenueEvent.amount), 0)).where(
            RevenueEvent.workspace_id == workspace_id,
            RevenueEvent.event_type == "booked",
        )
    )
    completed = db.scalar(
        select(func.coalesce(func.sum(RevenueEvent.amount), 0)).where(
            RevenueEvent.workspace_id == workspace_id,
            RevenueEvent.event_type == "completed",
        )
    )
    recovered = db.scalar(
        select(func.coalesce(func.sum(RevenueEvent.amount), 0)).where(
            RevenueEvent.workspace_id == workspace_id,
            RevenueEvent.event_type == "recovered",
        )
    )
    open_opportunity = db.scalar(
        select(func.coalesce(func.sum(Lead.estimated_value), 0)).where(
            Lead.workspace_id == workspace_id,
            Lead.stage.in_(ACTIVE_STAGES),
        )
    )

    return {
        "pipeline": float(pipeline or 0),
        "booked_pipeline": float(booked or 0),
        "completed_revenue": float(completed or 0),
        "recovered_revenue": float(recovered or 0),
        "open_opportunity": float(open_opportunity or 0),
    }


def opportunity_list(db: Session, workspace_id: int, limit: int = 10) -> list[dict]:
    leads = list(
        db.scalars(
            select(Lead)
            .where(
                Lead.workspace_id == workspace_id,
                Lead.stage.in_(ACTIVE_STAGES),
            )
            .order_by(Lead.estimated_value.desc(), Lead.created_at.asc())
            .limit(limit)
        )
    )

    results: list[dict] = []
    now = datetime.now(timezone.utc)
    for lead in leads:
        confirmed = db.scalar(
            select(Appointment.id).where(
                Appointment.lead_id == lead.id,
                Appointment.status.in_(("confirmed", "completed")),
            )
        )
        if confirmed:
            continue

        last = lead.last_contacted_at or lead.created_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        hours_idle = max(0, int((now - last).total_seconds() // 3600))

        if lead.stage == "qualified":
            action = "Prioritize follow-up and offer available appointment slots."
        elif hours_idle >= 24:
            action = "Re-engage this lead; no recent contact is recorded."
        else:
            action = "Continue qualification and move toward booking."

        results.append(
            {
                "lead_id": lead.id,
                "name": lead.name,
                "stage": lead.stage,
                "urgency": lead.urgency,
                "estimated_value": float(lead.estimated_value or 0),
                "hours_idle": hours_idle,
                "recommended_action": action,
            }
        )
    return results
