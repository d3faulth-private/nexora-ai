from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..automation import run_due_jobs_once
from ..config import get_settings
from ..db import get_db
from ..inbox import sync_workspace_gmail
from ..connectors.providers import (
    connector,
    disconnect_connector,
    exchange_google_code,
    google_authorization_url,
    google_available_slots,
    google_calendar_create,
    hubspot_upsert_contact,
    mark_connector,
    set_secret,
    signed_webhook,
    test_connector,
)
from ..models import Appointment, AutomationJob, Conversation, Lead, User
from ..revenue import opportunity_list, record_booking_attribution, record_completed_revenue, revenue_summary
from ..security import csrf_valid
from ..schemas import (
    HubSpotConnect,
    HumanMessageCreate,
    IntakeEvent,
    OnboardingUpdate,
    WebhookConnect,
)
from ..services import (
    add_human_message,
    conversation_for_lead,
    get_profile,
    get_workspace,
    latest_conversation_for_lead,
    process_customer_message,
    profile_dict,
    set_handoff,
    upsert_profile,
)
from ..vault import VaultUnavailable


router = APIRouter()
settings = get_settings()


def context(request: Request, db: Session):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(401, "Authentication required")
    user = db.get(User, int(user_id))
    if not user or not user.is_active:
        request.session.clear()
        raise HTTPException(401, "Authentication required")
    workspace = get_workspace(db, user.workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if not csrf_valid(request.session.get("csrf_token"), request.headers.get("X-Nexora-CSRF")):
            raise HTTPException(403, "Invalid CSRF token")
    return user, workspace


def require_live_integrations() -> None:
    if settings.demo_mode:
        raise HTTPException(
            403,
            "Real integrations are disabled in Demo Mode. Activate a Live workspace to connect external accounts.",
        )


@router.get("/api/onboarding")
def onboarding_state(request: Request, db: Session = Depends(get_db)):
    _, workspace = context(request, db)
    profile = get_profile(db, workspace.id)
    return {
        "workspace": {
            "name": workspace.name,
            "industry": workspace.industry,
            "timezone": workspace.timezone,
            "phone": workspace.phone,
            "email": workspace.email,
            "website": workspace.website,
            "knowledge_summary": workspace.knowledge_summary,
        },
        "profile": profile_dict(profile),
    }


@router.post("/api/onboarding")
def save_onboarding(
    payload: OnboardingUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    _, workspace = context(request, db)
    profile = upsert_profile(db, workspace, payload.model_dump())
    return {
        "ok": True,
        "workspace": workspace.name,
        "profile": profile_dict(profile),
    }


@router.post("/api/leads/{lead_id}/takeover")
def takeover(lead_id: int, request: Request, db: Session = Depends(get_db)):
    user, workspace = context(request, db)
    lead = db.scalar(
        select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace.id)
    )
    if not lead:
        raise HTTPException(404, "Lead not found")
    conversation = latest_conversation_for_lead(db, workspace.id, lead.id)
    if not conversation:
        conversation = conversation_for_lead(db, workspace.id, lead.id, "web")
    control = set_handoff(db, workspace, conversation, user, "human")
    return {"lead_id": lead.id, "conversation_id": conversation.id, "mode": control.mode}


@router.post("/api/leads/{lead_id}/return-to-ai")
def return_to_ai(lead_id: int, request: Request, db: Session = Depends(get_db)):
    user, workspace = context(request, db)
    lead = db.scalar(
        select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace.id)
    )
    if not lead:
        raise HTTPException(404, "Lead not found")
    conversation = latest_conversation_for_lead(db, workspace.id, lead.id)
    if not conversation:
        conversation = conversation_for_lead(db, workspace.id, lead.id, "web")
    control = set_handoff(db, workspace, conversation, user, "ai")
    return {"lead_id": lead.id, "conversation_id": conversation.id, "mode": control.mode}


@router.post("/api/leads/{lead_id}/human-message")
def human_message(
    lead_id: int,
    payload: HumanMessageCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    user, workspace = context(request, db)
    lead = db.scalar(
        select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace.id)
    )
    if not lead:
        raise HTTPException(404, "Lead not found")
    try:
        conversation = add_human_message(
            db,
            workspace,
            user,
            lead,
            payload.body,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True, "conversation_id": conversation.id}


@router.get("/api/connectors/google/start")
def google_start(request: Request, db: Session = Depends(get_db)):
    _, workspace = context(request, db)
    require_live_integrations()
    state = secrets.token_urlsafe(32)
    request.session["google_oauth_state"] = state
    request.session["google_oauth_workspace_id"] = workspace.id
    try:
        url = google_authorization_url(state)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"authorization_url": url}


@router.get("/api/connectors/google/callback")
def google_callback(
    request: Request,
    code: str,
    state: str,
    db: Session = Depends(get_db),
):
    _, workspace = context(request, db)
    require_live_integrations()
    expected = request.session.pop("google_oauth_state", None)
    expected_workspace = request.session.pop("google_oauth_workspace_id", None)

    if not expected or not secrets.compare_digest(str(expected), str(state)):
        raise HTTPException(400, "Invalid OAuth state.")
    if int(expected_workspace or 0) != workspace.id:
        raise HTTPException(400, "OAuth workspace mismatch.")

    try:
        tokens = exchange_google_code(code)
        set_secret(db, workspace.id, "google", tokens)
    except (RuntimeError, VaultUnavailable) as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "Google OAuth token exchange failed.") from exc

    mark_connector(
        db,
        workspace.id,
        "google",
        status="connected",
        mode="real",
        config={"gmail": True, "calendar": True},
    )
    db.commit()
    return RedirectResponse("/?connector=google-connected", status_code=303)


@router.post("/api/connectors/hubspot/connect")
def hubspot_connect(
    payload: HubSpotConnect,
    request: Request,
    db: Session = Depends(get_db),
):
    _, workspace = context(request, db)
    require_live_integrations()
    try:
        set_secret(
            db,
            workspace.id,
            "hubspot",
            {"private_app_token": payload.private_app_token},
        )
    except VaultUnavailable as exc:
        raise HTTPException(400, str(exc)) from exc

    mark_connector(
        db,
        workspace.id,
        "hubspot",
        status="disconnected",
        mode="real",
    )
    db.commit()

    try:
        test_connector(db, workspace.id, "hubspot")
    except Exception as exc:
        mark_connector(db, workspace.id, "hubspot", status="degraded", mode="real")
        db.commit()
        raise HTTPException(502, "HubSpot credential validation failed.") from exc

    mark_connector(db, workspace.id, "hubspot", status="connected", mode="real")
    db.commit()
    return {"ok": True, "slug": "hubspot", "status": "connected"}


@router.post("/api/connectors/webhook/connect")
def webhook_connect(
    payload: WebhookConnect,
    request: Request,
    db: Session = Depends(get_db),
):
    _, workspace = context(request, db)
    require_live_integrations()
    try:
        set_secret(
            db,
            workspace.id,
            "webhook",
            {"url": payload.url, "secret": payload.secret},
        )
    except VaultUnavailable as exc:
        raise HTTPException(400, str(exc)) from exc

    mark_connector(
        db,
        workspace.id,
        "webhook",
        status="connected",
        mode="real",
    )
    db.commit()
    return {"ok": True, "slug": "webhook", "status": "connected"}


@router.post("/api/connectors/{slug}/mock")
def connector_mock(slug: str, request: Request, db: Session = Depends(get_db)):
    _, workspace = context(request, db)
    if not settings.demo_mode:
        raise HTTPException(403, "Mock connectors are disabled in live mode.")
    item = mark_connector(
        db,
        workspace.id,
        slug,
        status="connected",
        mode="mock",
    )
    db.commit()
    return {"slug": item.slug, "status": item.status, "mode": item.mode}


@router.post("/api/connectors/gmail/sync")
def gmail_sync(request: Request, db: Session = Depends(get_db)):
    _, workspace = context(request, db)
    require_live_integrations()
    try:
        return sync_workspace_gmail(db, workspace, max_results=20)
    except Exception as exc:
        raise HTTPException(
            502,
            "Gmail sync failed; unprocessed messages remain retryable.",
        ) from exc


@router.post("/api/leads/{lead_id}/book")
def book_lead(lead_id: int, request: Request, db: Session = Depends(get_db)):
    _, workspace = context(request, db)
    lead = db.scalar(
        select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace.id)
    )
    if not lead:
        raise HTTPException(404, "Lead not found")

    appointment = db.scalar(
        select(Appointment)
        .where(
            Appointment.workspace_id == workspace.id,
            Appointment.lead_id == lead.id,
            Appointment.status == "proposed",
        )
        .order_by(Appointment.starts_at)
    )
    if not appointment:
        raise HTTPException(409, "No proposed appointment exists.")

    appointment.status = "confirmed"
    lead.stage = "booked"
    record_booking_attribution(db, workspace.id, lead, source="ai_booking")

    for job in db.scalars(
        select(AutomationJob).where(
            AutomationJob.workspace_id == workspace.id,
            AutomationJob.lead_id == lead.id,
            AutomationJob.status == "pending",
        )
    ):
        job.status = "cancelled"
        job.last_error = "Lead booked."

    profile = get_profile(db, workspace.id)
    duration = profile.booking_duration_minutes if profile else 60

    calendar_result = None
    try:
        calendar_result = google_calendar_create(
            db,
            workspace.id,
            "HVAC appointment - " + lead.name,
            appointment.starts_at,
            duration,
            lead.email,
        )
    except Exception:
        calendar_result = None

    try:
        hubspot_upsert_contact(
            db,
            workspace.id,
            {
                "name": lead.name,
                "email": lead.email,
                "phone": lead.phone,
                "zip_code": lead.zip_code,
                "stage": lead.stage,
            },
        )
    except Exception:
        pass
    try:
        signed_webhook(
            db,
            workspace.id,
            "lead.booked",
            {
                "lead_id": lead.id,
                "appointment_id": appointment.id,
                "starts_at": appointment.starts_at.isoformat(),
            },
        )
    except Exception:
        pass

    db.commit()
    return {
        "ok": True,
        "appointment_id": appointment.id,
        "starts_at": appointment.starts_at,
        "calendar_synced": bool(calendar_result and calendar_result.ok),
    }


@router.post("/api/automation/run-due")
def run_automation_now(request: Request, db: Session = Depends(get_db)):
    context(request, db)
    return {"processed": run_due_jobs_once()}


@router.post("/api/intake/{workspace_id}")
def external_intake(
    workspace_id: int,
    payload: IntakeEvent,
    x_nexora_intake_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not settings.intake_api_key:
        raise HTTPException(503, "External intake is not enabled.")
    if not x_nexora_intake_key or not secrets.compare_digest(
        x_nexora_intake_key,
        settings.intake_api_key,
    ):
        raise HTTPException(401, "Invalid intake key.")

    workspace = get_workspace(db, workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")

    if payload.external_id:
        existing = db.scalar(
            select(Lead).where(
                Lead.workspace_id == workspace.id,
                Lead.source == payload.source,
                Lead.email == payload.email,
                Lead.issue == payload.issue,
            )
        )
        if existing:
            return {"lead_id": existing.id, "deduplicated": True}

    lead = Lead(
        workspace_id=workspace.id,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        zip_code=payload.zip_code,
        source=payload.source,
        issue=payload.issue,
        estimated_value=payload.estimated_value,
    )
    db.add(lead)
    db.flush()

    decision, appointment, _ = process_customer_message(
        db,
        workspace,
        lead,
        payload.issue,
        "webhook",
    )
    return {
        "lead_id": lead.id,
        "agent": decision.agent,
        "stage": lead.stage,
        "appointment_proposed": appointment is not None,
    }



@router.get("/api/revenue/summary")
def revenue_report(request: Request, db: Session = Depends(get_db)):
    _, workspace = context(request, db)
    return revenue_summary(db, workspace.id)


@router.get("/api/opportunities")
def opportunities(request: Request, db: Session = Depends(get_db)):
    _, workspace = context(request, db)
    items = opportunity_list(db, workspace.id, limit=20)
    return {
        "count": len(items),
        "estimated_value": sum(item["estimated_value"] for item in items),
        "items": items,
    }


@router.post("/api/leads/{lead_id}/complete-job")
def complete_job(
    lead_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
):
    _, workspace = context(request, db)
    lead = db.scalar(
        select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace.id)
    )
    if not lead:
        raise HTTPException(404, "Lead not found")

    amount_raw = payload.get("actual_amount")
    actual_amount = float(amount_raw) if amount_raw is not None else None
    lead.stage = "completed"

    for job in db.scalars(
        select(AutomationJob).where(
            AutomationJob.workspace_id == workspace.id,
            AutomationJob.lead_id == lead.id,
            AutomationJob.status == "pending",
        )
    ):
        job.status = "cancelled"
        job.last_error = "Job completed."

    appointment = db.scalar(
        select(Appointment)
        .where(
            Appointment.workspace_id == workspace.id,
            Appointment.lead_id == lead.id,
            Appointment.status == "confirmed",
        )
        .order_by(Appointment.starts_at.desc())
    )
    if appointment:
        appointment.status = "completed"

    event = record_completed_revenue(
        db,
        workspace.id,
        lead,
        actual_amount=actual_amount,
        source="operator",
    )
    try:
        hubspot_upsert_contact(
            db,
            workspace.id,
            {
                "name": lead.name,
                "email": lead.email,
                "phone": lead.phone,
                "zip_code": lead.zip_code,
                "stage": lead.stage,
            },
        )
    except Exception:
        pass
    try:
        signed_webhook(
            db,
            workspace.id,
            "lead.completed",
            {"lead_id": lead.id, "revenue": event.amount},
        )
    except Exception:
        pass

    db.commit()
    db.refresh(event)
    return {
        "ok": True,
        "lead_id": lead.id,
        "stage": lead.stage,
        "revenue": event.amount,
    }



@router.get("/api/availability")
def availability(
    request: Request,
    start: str | None = None,
    count: int = 3,
    db: Session = Depends(get_db),
):
    _, workspace = context(request, db)
    profile = get_profile(db, workspace.id)
    duration = profile.booking_duration_minutes if profile else 60

    if start:
        desired = datetime.fromisoformat(start.replace("Z", "+00:00"))
    else:
        desired = datetime.now(timezone.utc) + timedelta(hours=2)

    try:
        slots = google_available_slots(
            db,
            workspace.id,
            desired,
            duration_minutes=duration,
            count=max(1, min(count, 8)),
            timezone_name=workspace.timezone,
            business_hours=profile.business_hours if profile else "",
        )
    except Exception as exc:
        raise HTTPException(502, "Calendar availability check failed.") from exc

    google = connector(db, workspace.id, "google")
    return {
        "calendar_connected": bool(google and google.status == "connected"),
        "duration_minutes": duration,
        "slots": [item.isoformat() for item in slots],
    }


@router.post("/api/connectors/{slug}/test")
def connector_test(slug: str, request: Request, db: Session = Depends(get_db)):
    _, workspace = context(request, db)
    try:
        result = test_connector(db, workspace.id, slug)
        item = mark_connector(db, workspace.id, slug, status="connected", mode=(connector(db, workspace.id, slug).mode if connector(db, workspace.id, slug) else "real"))
        db.commit()
        return {"ok": result.ok, "slug": slug, "detail": result.detail, "status": item.status}
    except Exception as exc:
        item = mark_connector(db, workspace.id, slug, status="degraded", mode=(connector(db, workspace.id, slug).mode if connector(db, workspace.id, slug) else "real"))
        db.commit()
        raise HTTPException(502, "Connector health check failed.") from exc


@router.post("/api/connectors/{slug}/disconnect")
def connector_disconnect(slug: str, request: Request, db: Session = Depends(get_db)):
    _, workspace = context(request, db)
    if slug not in {"google", "hubspot", "webhook"}:
        raise HTTPException(404, "Unknown connector.")
    disconnect_connector(db, workspace.id, slug)
    return {"ok": True, "slug": slug, "status": "disconnected"}


@router.get("/api/customers/{lead_id}/history")
def customer_history(lead_id: int, request: Request, db: Session = Depends(get_db)):
    _, workspace = context(request, db)
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace.id))
    if not lead:
        raise HTTPException(404, "Lead not found")

    candidates = list(
        db.scalars(
            select(Lead)
            .where(Lead.workspace_id == workspace.id)
            .order_by(Lead.created_at.desc())
        )
    )
    related = [
        item for item in candidates
        if item.id != lead.id
        and (
            (lead.email and item.email and item.email.lower() == lead.email.lower())
            or (lead.phone and item.phone and item.phone == lead.phone)
        )
    ]

    history_leads = [lead] + related
    history_ids = [item.id for item in history_leads]
    names = {item.id: item.name for item in history_leads}

    appointments = list(
        db.scalars(
            select(Appointment)
            .where(
                Appointment.workspace_id == workspace.id,
                Appointment.lead_id.in_(history_ids),
            )
            .order_by(Appointment.starts_at.desc())
            .limit(20)
        )
    )
    conversations = list(
        db.scalars(
            select(Conversation)
            .where(
                Conversation.workspace_id == workspace.id,
                Conversation.lead_id.in_(history_ids),
            )
            .order_by(Conversation.created_at.desc())
            .limit(20)
        )
    )

    return {
        "customer": {
            "name": lead.name,
            "email": lead.email,
            "phone": lead.phone,
        },
        "previous_requests": [
            {
                "id": item.id,
                "stage": item.stage,
                "issue": item.issue,
                "estimated_value": item.estimated_value,
                "created_at": item.created_at,
            }
            for item in related[:10]
        ],
        "appointments": [
            {
                "lead_id": item.lead_id,
                "lead_name": names.get(item.lead_id, "Customer"),
                "status": item.status,
                "starts_at": item.starts_at,
            }
            for item in appointments
        ],
        "conversations": [
            {
                "lead_id": item.lead_id,
                "channel": item.channel,
                "status": item.status,
                "message_count": len(item.messages),
                "created_at": item.created_at,
            }
            for item in conversations
        ],
    }
