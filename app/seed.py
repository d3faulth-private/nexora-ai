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
    ("google", "Google Gmail & Calendar", "mock"),
    ("hubspot", "HubSpot CRM", "mock"),
    ("webhook", "Outbound Webhook", "mock"),
]


def ensure_v03_defaults(db: Session, workspace: Workspace) -> None:
    profile = db.scalar(
        select(WorkspaceProfile).where(WorkspaceProfile.workspace_id == workspace.id)
    )
    if not profile:
        defaults = default_hvac_profile()
        db.add(
            WorkspaceProfile(
                workspace_id=workspace.id,
                services_json=json.dumps(defaults["services"]),
                service_area=defaults["service_area"],
                business_hours=defaults["business_hours"],
                emergency_policy=defaults["emergency_policy"],
                booking_duration_minutes=defaults["booking_duration_minutes"],
                followup_after_minutes=defaults["followup_after_minutes"],
                followup_max_attempts=defaults["followup_max_attempts"],
                onboarding_completed=False,
            )
        )

    for slug, name, mode in CONNECTORS:
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
                    mode=mode,
                )
            )
    db.commit()


def seed_demo(db: Session) -> Workspace:
    settings = get_settings()
    workspace = db.scalar(select(Workspace).where(Workspace.name == "Nexora HVAC Demo"))
    if workspace:
        ensure_v03_defaults(db, workspace)
        return workspace

    workspace = Workspace(
        name="Nexora HVAC Demo",
        industry="HVAC",
        timezone=settings.default_timezone,
        phone="+1 555 010 1111",
        email="hello@nexora-demo.local",
        website="https://example.local",
        knowledge_summary=(
            "Demo HVAC company. Service area ZIPs 10001-10020. "
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

    for slug, name, role in AGENTS:
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
            content="The demo company serves ZIP codes 10001 through 10020.",
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
    ensure_v03_defaults(db, workspace)
    return workspace
