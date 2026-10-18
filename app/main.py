from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .automation import start_scheduler, stop_scheduler
from .config import get_settings
from .db import Base, SessionLocal, engine, get_db
from .inbox import sync_connected_gmail_once
from .models import Agent, Approval, Appointment, AutomationJob, Connector, Conversation, KnowledgeEntry, Lead, Task, User
from .schemas import AppointmentCreate, ConnectorUpdate, KnowledgeCreate, LeadCreate, LeadUpdate, ManagerCommand, MessageCreate
from .revenue import record_booking_attribution
from .seed import seed_demo
from .security import csrf_token, csrf_valid, clear_login_failures, login_blocked, login_key, record_login_failure
from .api.routes import require_workspace_context, router as api_router
from .services import (
    activity,
    authenticate,
    dashboard,
    get_workspace,
    process_customer_message,
    request_action,
    run_manager,
)


BASE_DIR = Path(__file__).resolve().parent
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_runtime()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_demo(db)
    start_scheduler(sync_connected_gmail_once)
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title=settings.app_name, version="0.5.0", lifespan=lifespan)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_host_list,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_secret,
    same_site="lax",
    https_only=settings.app_env == "production",
    max_age=settings.session_max_age_seconds,
)

app.include_router(api_router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; script-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
    )
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"error": "request_failed", "message": "Nexora could not complete this request."},
            status_code=500,
        )
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={"app_name": settings.app_name},
        status_code=500,
    )


def session_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, int(user_id))
    if not user or not user.is_active:
        request.session.clear()
        return None
    return user


@app.get("/health")
def health():
    database = "ok"
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except Exception:
        database = "error"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "app": settings.app_name,
        "version": "0.5.0",
        "mode": "demo" if settings.demo_mode else "live",
        "database": database,
        "ai_provider": settings.ai_provider,
    }


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "app_name": settings.app_name,
            "demo_mode": settings.demo_mode,
            "demo_email": settings.demo_email,
            "demo_password": settings.demo_password if settings.demo_mode else "",
            "error": None,
        },
    )


@app.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    normalized_email = email.strip().lower()
    client_ip = request.client.host if request.client else "unknown"
    key = login_key(client_ip, normalized_email)
    if login_blocked(key):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "app_name": settings.app_name,
                "demo_mode": settings.demo_mode,
                "demo_email": settings.demo_email,
                "demo_password": settings.demo_password if settings.demo_mode else "",
                "error": "Too many sign-in attempts. Try again later.",
            },
            status_code=429,
        )

    user = authenticate(db, normalized_email, password)
    if not user:
        record_login_failure(key)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "app_name": settings.app_name,
                "demo_mode": settings.demo_mode,
                "demo_email": settings.demo_email,
                "demo_password": settings.demo_password if settings.demo_mode else "",
                "error": "Invalid email or password.",
            },
            status_code=401,
        )

    clear_login_failures(key)
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["workspace_id"] = user.workspace_id
    request.session["csrf_token"] = csrf_token()
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request, csrf: str = Form("")):
    if not csrf_valid(request.session.get("csrf_token"), csrf):
        raise HTTPException(403, "Invalid CSRF token")
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = session_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    workspace = get_workspace(db, user.workspace_id)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": settings.app_name,
            "user": user,
            "workspace": workspace,
            "csrf_token": request.session.get("csrf_token", ""),
            "demo_mode": settings.demo_mode,
            "app_env": settings.app_env,
        },
    )


@app.get("/api/me")
def api_me(request: Request, db: Session = Depends(get_db)):
    user, workspace = require_workspace_context(request, db)
    return {
        "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role},
        "workspace": {"id": workspace.id, "name": workspace.name, "industry": workspace.industry},
        "mode": "demo" if settings.demo_mode else "live",
        "csrf_token": request.session.get("csrf_token", ""),
    }


@app.get("/api/dashboard")
def api_dashboard(request: Request, db: Session = Depends(get_db)):
    _, workspace = require_workspace_context(request, db)
    return dashboard(db, workspace)


@app.post("/api/leads")
def create_lead(payload: LeadCreate, request: Request, db: Session = Depends(get_db)):
    _, workspace = require_workspace_context(request, db)
    lead = Lead(workspace_id=workspace.id, **payload.model_dump())
    db.add(lead)
    db.flush()
    activity(db, workspace.id, "receptionist", "lead_created", "Captured new lead: " + lead.name + ".", "lead", lead.id)
    db.commit()
    db.refresh(lead)
    return {"id": lead.id, "name": lead.name, "stage": lead.stage}


@app.patch("/api/leads/{lead_id}")
def update_lead(lead_id: int, payload: LeadUpdate, request: Request, db: Session = Depends(get_db)):
    _, workspace = require_workspace_context(request, db)
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace.id))
    if not lead:
        raise HTTPException(404, "Lead not found")
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(lead, key, value)

    if changes.get("stage") in {"booked", "completed", "lost"}:
        for job in db.scalars(
            select(AutomationJob).where(
                AutomationJob.workspace_id == workspace.id,
                AutomationJob.lead_id == lead.id,
                AutomationJob.status == "pending",
            )
        ):
            job.status = "cancelled"
            job.last_error = "Lead entered terminal follow-up state: " + lead.stage + "."

    activity(db, workspace.id, "operations", "lead_updated", "Updated lead: " + lead.name + ".", "lead", lead.id)
    db.commit()
    return {"id": lead.id, "stage": lead.stage, "urgency": lead.urgency}


@app.get("/api/leads/{lead_id}")
def get_lead(lead_id: int, request: Request, db: Session = Depends(get_db)):
    _, workspace = require_workspace_context(request, db)
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace.id))
    if not lead:
        raise HTTPException(404, "Lead not found")

    conversations = list(
        db.scalars(
            select(Conversation)
            .where(Conversation.workspace_id == workspace.id, Conversation.lead_id == lead.id)
            .order_by(Conversation.id)
        )
    )
    messages = []
    for conversation in conversations:
        for message in sorted(conversation.messages, key=lambda item: item.created_at):
            messages.append(
                {
                    "id": message.id,
                    "conversation_id": conversation.id,
                    "direction": message.direction,
                    "actor": message.actor,
                    "body": message.body,
                    "created_at": message.created_at,
                }
            )

    return {
        "id": lead.id,
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "zip_code": lead.zip_code,
        "source": lead.source,
        "stage": lead.stage,
        "urgency": lead.urgency,
        "issue": lead.issue,
        "estimated_value": lead.estimated_value,
        "messages": messages,
        "appointments": [
            {
                "id": appointment.id,
                "starts_at": appointment.starts_at,
                "status": appointment.status,
                "notes": appointment.notes,
            }
            for appointment in lead.appointments
        ],
    }


@app.post("/api/leads/{lead_id}/message")
def lead_message(
    lead_id: int,
    payload: MessageCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    _, workspace = require_workspace_context(request, db)
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace.id))
    if not lead:
        raise HTTPException(404, "Lead not found")

    decision, appointment, conversation = process_customer_message(
        db,
        workspace,
        lead,
        payload.body,
        payload.channel,
    )
    return {
        "agent": decision.agent,
        "message": decision.reply,
        "actions": decision.actions or [],
        "stage": lead.stage,
        "urgency": lead.urgency,
        "conversation_id": conversation.id,
        "appointment": {
            "id": appointment.id,
            "starts_at": appointment.starts_at,
            "status": appointment.status,
        } if appointment else None,
    }


@app.post("/api/manager/run")
def manager_run(payload: ManagerCommand, request: Request, db: Session = Depends(get_db)):
    _, workspace = require_workspace_context(request, db)
    return run_manager(db, workspace, payload.objective)


@app.post("/api/agents/{slug}/toggle")
def toggle_agent(slug: str, request: Request, db: Session = Depends(get_db)):
    _, workspace = require_workspace_context(request, db)
    agent = db.scalar(select(Agent).where(Agent.workspace_id == workspace.id, Agent.slug == slug))
    if not agent:
        raise HTTPException(404, "Agent not found")
    agent.enabled = not agent.enabled
    activity(
        db,
        workspace.id,
        "manager",
        "agent_toggled",
        agent.name + (" enabled." if agent.enabled else " disabled."),
        "agent",
        agent.id,
    )
    db.commit()
    return {"slug": agent.slug, "enabled": agent.enabled}


@app.post("/api/agents/{slug}/autonomy/{level}")
def set_autonomy(slug: str, level: str, request: Request, db: Session = Depends(get_db)):
    _, workspace = require_workspace_context(request, db)
    if level not in {"manual", "guarded", "autonomous"}:
        raise HTTPException(400, "Invalid autonomy level")
    agent = db.scalar(select(Agent).where(Agent.workspace_id == workspace.id, Agent.slug == slug))
    if not agent:
        raise HTTPException(404, "Agent not found")
    agent.autonomy_level = level
    activity(
        db,
        workspace.id,
        "manager",
        "autonomy_changed",
        agent.name + " autonomy set to " + level + ".",
        "agent",
        agent.id,
    )
    db.commit()
    return {"slug": slug, "autonomy_level": level}


@app.post("/api/actions/request")
def request_sensitive_action(payload: dict, request: Request, db: Session = Depends(get_db)):
    _, workspace = require_workspace_context(request, db)
    action_type = str(payload.get("action_type") or "")
    agent_slug = str(payload.get("agent_slug") or "manager")
    if not action_type:
        raise HTTPException(400, "action_type is required")
    return request_action(
        db,
        workspace,
        agent_slug,
        action_type,
        payload.get("payload") or {},
        str(payload.get("reason") or ""),
    )


@app.post("/api/approvals/{approval_id}/resolve")
def resolve_approval(approval_id: int, payload: dict, request: Request, db: Session = Depends(get_db)):
    user, workspace = require_workspace_context(request, db)
    decision = str(payload.get("decision") or "")
    if decision not in {"approved", "rejected"}:
        raise HTTPException(400, "Decision must be approved or rejected")

    approval = db.scalar(
        select(Approval).where(Approval.id == approval_id, Approval.workspace_id == workspace.id)
    )
    if not approval:
        raise HTTPException(404, "Approval not found")
    if approval.status != "pending":
        raise HTTPException(409, "Approval already resolved")

    approval.status = decision
    approval.resolved_by_user_id = user.id
    approval.resolved_at = datetime.now(timezone.utc)
    activity(
        db,
        workspace.id,
        "manager",
        "approval_resolved",
        "Approval " + str(approval.id) + " " + decision + " for " + approval.action_type + ".",
        "approval",
        approval.id,
    )
    db.commit()
    return {"id": approval.id, "status": approval.status}


@app.post("/api/appointments")
def create_appointment(payload: AppointmentCreate, request: Request, db: Session = Depends(get_db)):
    _, workspace = require_workspace_context(request, db)
    lead = db.scalar(select(Lead).where(Lead.id == payload.lead_id, Lead.workspace_id == workspace.id))
    if not lead:
        raise HTTPException(404, "Lead not found")

    appointment = Appointment(
        workspace_id=workspace.id,
        lead_id=lead.id,
        starts_at=payload.starts_at,
        status="confirmed",
        notes=payload.notes,
    )
    lead.stage = "booked"
    db.add(appointment)
    db.flush()
    record_booking_attribution(db, workspace.id, lead, source="manual_appointment")
    activity(
        db,
        workspace.id,
        "sales",
        "appointment_confirmed",
        "Appointment confirmed for " + lead.name + ".",
        "lead",
        lead.id,
    )
    db.commit()
    db.refresh(appointment)
    return {
        "id": appointment.id,
        "lead_id": lead.id,
        "starts_at": appointment.starts_at,
        "status": appointment.status,
    }


@app.get("/api/knowledge")
def list_knowledge(request: Request, db: Session = Depends(get_db)):
    _, workspace = require_workspace_context(request, db)
    entries = list(
        db.scalars(
            select(KnowledgeEntry)
            .where(KnowledgeEntry.workspace_id == workspace.id)
            .order_by(KnowledgeEntry.created_at.desc())
        )
    )
    return [
        {
            "id": entry.id,
            "title": entry.title,
            "content": entry.content,
            "tags": entry.tags,
            "is_active": entry.is_active,
        }
        for entry in entries
    ]


@app.post("/api/knowledge")
def create_knowledge(payload: KnowledgeCreate, request: Request, db: Session = Depends(get_db)):
    _, workspace = require_workspace_context(request, db)
    entry = KnowledgeEntry(workspace_id=workspace.id, **payload.model_dump())
    db.add(entry)
    db.flush()
    activity(db, workspace.id, "operations", "knowledge_added", "Knowledge added: " + entry.title, "knowledge", entry.id)
    db.commit()
    db.refresh(entry)
    return {"id": entry.id, "title": entry.title}


@app.get("/api/connectors")
def list_connectors(request: Request, db: Session = Depends(get_db)):
    _, workspace = require_workspace_context(request, db)
    items = list(db.scalars(select(Connector).where(Connector.workspace_id == workspace.id).order_by(Connector.id)))
    return [
        {"id": item.id, "slug": item.slug, "name": item.name, "status": item.status, "mode": item.mode}
        for item in items
    ]


@app.patch("/api/connectors/{slug}")
def update_connector(
    slug: str,
    payload: ConnectorUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    _, workspace = require_workspace_context(request, db)
    item = db.scalar(select(Connector).where(Connector.workspace_id == workspace.id, Connector.slug == slug))
    if not item:
        raise HTTPException(404, "Connector not found")
    updates = payload.model_dump(exclude_none=True)
    if settings.demo_mode and updates.get("mode") not in {None, "mock"}:
        raise HTTPException(403, "Local connectors cannot switch to external mode.")
    for key, value in updates.items():
        setattr(item, key, value)
    item.last_sync_at = datetime.now(timezone.utc)
    activity(db, workspace.id, "operations", "connector_updated", item.name + " connector updated.", "connector", item.id)
    db.commit()
    return {"slug": item.slug, "status": item.status, "mode": item.mode}


@app.post("/api/tasks")
def create_task(payload: dict, request: Request, db: Session = Depends(get_db)):
    _, workspace = require_workspace_context(request, db)
    title = str(payload.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "Task title is required")

    task = Task(
        workspace_id=workspace.id,
        lead_id=payload.get("lead_id"),
        title=title,
        description=str(payload.get("description") or ""),
        assigned_agent=str(payload.get("assigned_agent") or "manager"),
        status="open",
    )
    db.add(task)
    db.flush()
    activity(db, workspace.id, "manager", "task_created", "Created task: " + task.title, "task", task.id)
    db.commit()
    db.refresh(task)
    return {"id": task.id, "title": task.title, "status": task.status}


@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    _, workspace = require_workspace_context(request, db)
    task = db.scalar(select(Task).where(Task.id == task_id, Task.workspace_id == workspace.id))
    if not task:
        raise HTTPException(404, "Task not found")
    task.status = "completed"
    activity(db, workspace.id, "operations", "task_completed", "Completed task: " + task.title, "task", task.id)
    db.commit()
    return {"id": task.id, "status": task.status}
