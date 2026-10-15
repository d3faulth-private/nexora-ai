from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .hvac import default_hvac_profile
from .models import Agent, Connector, KnowledgeEntry, Lead, User, Workspace, WorkspaceProfile
from .security import hash_password


AGENTS = [
    ("manager", "Nexora Manager", "Coordinates the AI workforce and business objectives"),
    ("receptionist", "Nexora Receptionist", "Captures and routes inbound inquiries"),
    ("sales", "Nexora Sales", "Qualifies leads and proposes appointments"),
    ("followup", "Nexora Follow-Up", "Re-engages open leads and estimates"),
    ("support", "Nexora Support", "Handles support requests and escalations"),
    ("operations", "Nexora Operations", "Summarizes activity, pipeline, and tasks"),
]

CONNECTORS = [
    ("google", "Google Gmail & Calendar"),
    ("hubspot", "HubSpot CRM"),
    ("webhook", "Outbound Webhook"),
]

DEMO_WORKSPACE_NAME = "Nexora HVAC"
LEGACY_DEMO_WORKSPACE_NAMES = {"Nexora HVAC Demo", "Northstar Heating & Air"}



def ensure_defaults(db: Session, workspace: Workspace, demo_mode: bool) -> None:
    profile = db.scalar(
        select(WorkspaceProfile).where(WorkspaceProfile.workspace_id == workspace.id)
    )
    if not profile:
        defaults = default_hvac_profile()
        db.add(
            WorkspaceProfile(
                workspace_id=workspace.id,
                services_json=json.dumps(defaults["services"] if demo_mode else []),
                service_area=defaults["service_area"] if demo_mode else "",
                business_hours=defaults["business_hours"] if demo_mode else "",
                emergency_policy=defaults["emergency_policy"] if demo_mode else "",
                booking_duration_minutes=defaults["booking_duration_minutes"],
                followup_after_minutes=defaults["followup_after_minutes"],
                followup_max_attempts=defaults["followup_max_attempts"],
                onboarding_completed=False,
            )
        )

    for slug, name in CONNECTORS:
        exists = db.scalar(
            select(Connector).where(
                Connector.workspace_id == workspace.id,
                Connector.slug == slug,
            )
        )
        if not exists:
            db.add(
                Connector(
                    workspace_id=workspace.id,
                    slug=slug,
                    name=name,
                    status="disconnected",
                    mode="mock" if demo_mode else "real",
                )
            )

    for slug, name, role in AGENTS:
        exists = db.scalar(
            select(Agent).where(
                Agent.workspace_id == workspace.id,
                Agent.slug == slug,
            )
        )
        if not exists:
            db.add(
                Agent(
                    workspace_id=workspace.id,
                    slug=slug,
                    name=name,
                    role=role,
                    enabled=True,
                    autonomy_level="guarded",
                )
            )
    db.commit()


def _find_demo_workspace(db: Session, settings) -> Workspace | None:
    demo_user = db.scalar(select(User).where(User.email == settings.demo_email))
    if demo_user:
        workspace = db.get(Workspace, demo_user.workspace_id)
        if workspace:
            return workspace
    return db.scalar(
        select(Workspace)
        .where(Workspace.name.in_([DEMO_WORKSPACE_NAME, *LEGACY_DEMO_WORKSPACE_NAMES]))
        .order_by(Workspace.id)
    )


def _seed_demo(db: Session) -> Workspace:
    settings = get_settings()
    workspace = _find_demo_workspace(db, settings)
    if workspace:
        if workspace.name in LEGACY_DEMO_WORKSPACE_NAMES:
            workspace.name = DEMO_WORKSPACE_NAME
            if workspace.email in {"hello@nexora-demo.local", "service@northstar.example"}:
                workspace.email = "office@nexora.local"
            if workspace.website in {"https://example.local", "https://northstar.example"}:
                workspace.website = ""
            if (workspace.knowledge_summary or "").startswith(("Demo HVAC company.", "Northstar Heating & Air")):
                workspace.knowledge_summary = (
                    "Nexora HVAC serves ZIP codes 10001-10020. "
                    "Hours Mon-Sat 8am-7pm. Emergency requests are prioritized. "
                    "Never promise a fixed repair price before technician assessment."
                )
            db.commit()
        ensure_defaults(db, workspace, True)
        db.refresh(workspace)
        return workspace

    workspace = Workspace(
        name=DEMO_WORKSPACE_NAME,
        industry="HVAC",
        timezone=settings.default_timezone,
        phone="+1 212 555 0148",
        email="office@nexora.local",
        website="",
        knowledge_summary=(
            "Nexora HVAC serves ZIP codes 10001-10020. "
            "Hours Mon-Sat 8am-7pm. Emergency requests are prioritized. "
            "Never promise a fixed repair price before technician assessment."
        ),
    )
    db.add(workspace)
    db.flush()

    db.add(
        User(
            workspace_id=workspace.id,
            email=settings.demo_email,
            name="Nexora Admin",
            password_hash=hash_password(settings.demo_password),
            role="owner",
        )
    )

    db.add_all([
        KnowledgeEntry(
            workspace_id=workspace.id,
            title="Service policy",
            content="Emergency requests receive priority. Technicians confirm final pricing after assessment.",
            tags="service,pricing,emergency",
        ),
        KnowledgeEntry(
            workspace_id=workspace.id,
            title="Coverage area",
            content="Nexora HVAC serves ZIP codes 10001 through 10020.",
            tags="coverage,zip",
        ),
    ])

    db.add_all([
        Lead(
            workspace_id=workspace.id,
            name="Avery Johnson",
            email="avery@example.com",
            phone="555-0101",
            zip_code="10011",
            source="website",
            stage="new",
            issue="AC is blowing warm air",
            estimated_value=850,
        ),
        Lead(
            workspace_id=workspace.id,
            name="Morgan Lee",
            email="morgan@example.com",
            phone="555-0102",
            zip_code="10014",
            source="referral",
            stage="contacted",
            issue="Needs furnace replacement estimate",
            estimated_value=6400,
        ),
        Lead(
            workspace_id=workspace.id,
            name="Jordan Smith",
            email="jordan@example.com",
            phone="555-0103",
            zip_code="10018",
            source="google",
            stage="qualified",
            issue="Annual HVAC maintenance",
            estimated_value=320,
        ),
    ])

    db.commit()
    db.refresh(workspace)
    ensure_defaults(db, workspace, True)
    return workspace


def _seed_live(db: Session) -> Workspace:
    settings = get_settings()
    workspace = db.scalar(select(Workspace).order_by(Workspace.id))
    if workspace:
        demo_user = db.scalar(
            select(User).where(
                User.workspace_id == workspace.id,
                User.email == settings.demo_email,
            )
        )
        if workspace.name in LEGACY_DEMO_WORKSPACE_NAMES or demo_user:
            raise RuntimeError(
                "LIVE mode cannot reuse a demo-seeded database. "
                "Configure a clean DATABASE_URL or migrate real business data explicitly."
            )
        ensure_defaults(db, workspace, False)
        return workspace

    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        raise RuntimeError(
            "Live mode requires BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD for the initial owner account."
        )

    workspace = Workspace(
        name=settings.bootstrap_business_name,
        industry="HVAC",
        timezone=settings.default_timezone,
        knowledge_summary="",
    )
    db.add(workspace)
    db.flush()
    db.add(
        User(
            workspace_id=workspace.id,
            email=settings.bootstrap_admin_email.strip().lower(),
            name="Owner",
            password_hash=hash_password(settings.bootstrap_admin_password),
            role="owner",
        )
    )
    db.commit()
    db.refresh(workspace)
    ensure_defaults(db, workspace, False)
    return workspace


def seed_workspace(db: Session) -> Workspace:
    return _seed_demo(db) if get_settings().demo_mode else _seed_live(db)


def seed_demo(db: Session) -> Workspace:
    # Backward-compatible alias for older scripts/terminal imports.
    return seed_workspace(db)
