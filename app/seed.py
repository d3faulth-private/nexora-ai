from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import get_settings
from .hvac import default_hvac_profile
from .models import (
    Activity,
    Agent,
    Appointment,
    Approval,
    AutomationJob,
    Connector,
    ConnectorSecret,
    Conversation,
    ConversationControl,
    ExternalEvent,
    KnowledgeEntry,
    Lead,
    Message,
    RevenueEvent,
    Task,
    UsageEvent,
    User,
    Workspace,
    WorkspaceProfile,
)
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
LEGACY_MINIMAL_LEADS = {"Avery Johnson", "Morgan Lee", "Jordan Smith"}


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


def _configure_operational_profile(db: Session, workspace: Workspace) -> None:
    ensure_defaults(db, workspace, True)
    profile = db.scalar(
        select(WorkspaceProfile).where(WorkspaceProfile.workspace_id == workspace.id)
    )
    if not profile:
        raise RuntimeError("Workspace profile could not be initialized.")

    defaults = default_hvac_profile()
    profile.services_json = json.dumps(defaults["services"])
    profile.service_area = "10001-10020"
    profile.business_hours = "Mon-Sat 8:00 AM-7:00 PM"
    profile.emergency_policy = (
        "Prioritize no-heat/no-cooling and safety-related requests. "
        "Escalate gas smells, smoke, burning smells, sparking, and electrical hazards to a human immediately."
    )
    profile.booking_duration_minutes = 90
    profile.followup_after_minutes = 120
    profile.followup_max_attempts = 3
    profile.onboarding_completed = True
    profile.updated_at = datetime.now(timezone.utc)

    workspace.name = DEMO_WORKSPACE_NAME
    workspace.industry = "HVAC"
    workspace.phone = "+1 212 555 0148"
    workspace.email = "office@nexora.local"
    workspace.website = ""
    workspace.knowledge_summary = (
        "Nexora HVAC serves ZIP codes 10001-10020. Hours Mon-Sat 8am-7pm. "
        "Emergency requests are prioritized. Never promise a fixed repair price before technician assessment. "
        "Financing may be available for qualifying replacement systems."
    )
    db.commit()


def _add_conversation(
    db: Session,
    workspace: Workspace,
    lead: Lead,
    *,
    agent: str,
    messages: list[tuple[str, str, str, int]],
    created_hours_ago: int,
) -> Conversation:
    now = datetime.now(timezone.utc)
    conversation = Conversation(
        workspace_id=workspace.id,
        lead_id=lead.id,
        channel="web",
        status="open",
        assigned_agent=agent,
        created_at=now - timedelta(hours=created_hours_ago),
    )
    db.add(conversation)
    db.flush()
    for direction, actor, body, minutes_ago in messages:
        db.add(
            Message(
                conversation_id=conversation.id,
                direction=direction,
                actor=actor,
                body=body,
                created_at=now - timedelta(minutes=minutes_ago),
            )
        )
    return conversation


def _seed_operational_dataset(db: Session, workspace: Workspace) -> None:
    _configure_operational_profile(db, workspace)
    now = datetime.now(timezone.utc)

    db.add_all(
        [
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
            KnowledgeEntry(
                workspace_id=workspace.id,
                title="Replacement financing",
                content="Financing may be available on qualifying system replacements after owner approval.",
                tags="financing,replacement",
            ),
            KnowledgeEntry(
                workspace_id=workspace.id,
                title="Safety escalation",
                content="Do not diagnose gas, smoke, burning, sparking, or electrical hazards remotely; escalate immediately.",
                tags="safety,escalation",
            ),
        ]
    )

    lead_specs = [
        ("Avery Johnson", "avery@example.com", "555-0101", "10011", "website", "new", "high", "AC is blowing warm air", 850, 5, None),
        ("Morgan Lee", "morgan@example.com", "555-0102", "10014", "referral", "contacted", "normal", "Needs furnace replacement estimate", 6400, 3, 2),
        ("Jordan Smith", "jordan@example.com", "555-0103", "10018", "google", "qualified", "normal", "Annual HVAC maintenance", 320, 2, 1),
        ("Daniel Carter", "daniel@example.com", "555-0104", "10008", "website", "booked", "normal", "Heat pump replacement", 5900, 4, 3),
        ("Sarah Wilson", "sarah@example.com", "555-0105", "10021", "phone", "booked", "urgent", "Emergency furnace repair — no heat", 3350, 1, 1),
        ("Michael Brooks", "michael@example.com", "555-0106", "10007", "referral", "completed", "normal", "AC compressor repair", 2800, 6, 4),
        ("Emily Davis", "emily@example.com", "555-0107", "10012", "website", "completed", "normal", "Full HVAC system replacement", 5000, 8, 5),
        ("Olivia Martinez", "olivia@example.com", "555-0108", "10016", "website", "contacted", "normal", "Weak airflow and uneven cooling", 1800, 1, 1),
        ("Ethan Reed", "ethan@example.com", "555-0109", "10019", "google", "qualified", "normal", "Mini-split service and diagnostics", 950, 2, 1),
        ("Sophia Turner", "sophia@example.com", "555-0110", "10003", "referral", "lost", "normal", "System replacement estimate", 4200, 10, 8),
        ("Noah Bennett", "noah@example.com", "555-0111", "10009", "website", "new", "normal", "Smart thermostat and wiring issue", 1100, 1, None),
        ("Grace Kim", "grace@example.com", "555-0112", "10017", "phone", "contacted", "high", "Furnace blower motor replacement", 3050, 2, 1),
    ]

    leads: dict[str, Lead] = {}
    for name, email, phone, zip_code, source, stage, urgency, issue, value, days_ago, contact_hours in lead_specs:
        lead = Lead(
            workspace_id=workspace.id,
            name=name,
            email=email,
            phone=phone,
            zip_code=zip_code,
            source=source,
            stage=stage,
            urgency=urgency,
            issue=issue,
            estimated_value=value,
            created_at=now - timedelta(days=days_ago),
            last_contacted_at=(now - timedelta(hours=contact_hours)) if contact_hours is not None else None,
        )
        db.add(lead)
        db.flush()
        leads[name] = lead

    conversations: dict[str, Conversation] = {}
    conversations["Avery Johnson"] = _add_conversation(
        db,
        workspace,
        leads["Avery Johnson"],
        agent="receptionist",
        created_hours_ago=2,
        messages=[
            ("inbound", "customer", "My AC is running but the air coming out is warm.", 105),
            ("outbound", "receptionist", "I can help with that. What ZIP code is the property in?", 103),
            ("inbound", "customer", "10011. It started this afternoon.", 98),
        ],
    )
    conversations["Morgan Lee"] = _add_conversation(
        db,
        workspace,
        leads["Morgan Lee"],
        agent="sales",
        created_hours_ago=26,
        messages=[
            ("inbound", "customer", "Our furnace is old and we need a replacement estimate.", 1500),
            ("outbound", "sales", "I can help coordinate an estimate. Is the current system still operating?", 1494),
            ("inbound", "customer", "Yes, but it has become unreliable.", 1470),
        ],
    )
    conversations["Jordan Smith"] = _add_conversation(
        db,
        workspace,
        leads["Jordan Smith"],
        agent="sales",
        created_hours_ago=6,
        messages=[
            ("inbound", "customer", "I want to schedule annual HVAC maintenance.", 340),
            ("outbound", "sales", "Absolutely. I have your request qualified and can move it toward scheduling.", 333),
        ],
    )
    conversations["Daniel Carter"] = _add_conversation(
        db,
        workspace,
        leads["Daniel Carter"],
        agent="sales",
        created_hours_ago=30,
        messages=[
            ("inbound", "customer", "We want to replace our heat pump before winter.", 1750),
            ("outbound", "sales", "Your replacement consultation is confirmed for the next available window.", 1725),
        ],
    )
    conversations["Sarah Wilson"] = _add_conversation(
        db,
        workspace,
        leads["Sarah Wilson"],
        agent="operations",
        created_hours_ago=3,
        messages=[
            ("inbound", "customer", "We have no heat and the house is getting cold.", 165),
            ("outbound", "receptionist", "I’m prioritizing this as an urgent no-heat request.", 162),
            ("outbound", "operations", "A technician window has been reserved pending dispatch confirmation.", 150),
        ],
    )
    conversations["Emily Davis"] = _add_conversation(
        db,
        workspace,
        leads["Emily Davis"],
        agent="followup",
        created_hours_ago=120,
        messages=[
            ("inbound", "customer", "I got the replacement estimate but needed time to decide.", 7200),
            ("outbound", "followup", "Checking in on the replacement estimate. I can help with next steps or scheduling.", 5760),
            ("inbound", "customer", "Yes, let’s move forward. What is the next appointment?", 5700),
            ("outbound", "sales", "Great — I’ll move this into scheduling.", 5685),
        ],
    )
    conversations["Olivia Martinez"] = _add_conversation(
        db,
        workspace,
        leads["Olivia Martinez"],
        agent="support",
        created_hours_ago=4,
        messages=[
            ("inbound", "customer", "Upstairs barely gets any airflow and the rooms stay warm.", 210),
            ("outbound", "support", "I’m reviewing the airflow history and service options.", 205),
            ("inbound", "customer", "Please have someone call me before scheduling.", 190),
        ],
    )
    conversations["Grace Kim"] = _add_conversation(
        db,
        workspace,
        leads["Grace Kim"],
        agent="followup",
        created_hours_ago=20,
        messages=[
            ("inbound", "customer", "The furnace blower is noisy and sometimes stops.", 1180),
            ("outbound", "sales", "That sounds like it needs technician assessment before final pricing.", 1170),
        ],
    )

    owner = db.scalar(
        select(User)
        .where(User.workspace_id == workspace.id)
        .order_by(User.id)
    )
    if owner:
        db.add(
            ConversationControl(
                workspace_id=workspace.id,
                conversation_id=conversations["Olivia Martinez"].id,
                mode="human",
                taken_over_by_user_id=owner.id,
                taken_over_at=now - timedelta(minutes=35),
            )
        )

    appointments = [
        Appointment(
            workspace_id=workspace.id,
            lead_id=leads["Jordan Smith"].id,
            starts_at=now + timedelta(days=2, hours=2),
            status="proposed",
            notes="Preventive maintenance window proposed by Nexora.",
            created_at=now - timedelta(hours=1),
        ),
        Appointment(
            workspace_id=workspace.id,
            lead_id=leads["Daniel Carter"].id,
            starts_at=now + timedelta(days=1, hours=1),
            status="confirmed",
            notes="Heat pump replacement consultation.",
            created_at=now - timedelta(hours=3),
        ),
        Appointment(
            workspace_id=workspace.id,
            lead_id=leads["Sarah Wilson"].id,
            starts_at=now + timedelta(hours=4),
            status="confirmed",
            notes="Priority no-heat service call.",
            created_at=now - timedelta(hours=1),
        ),
        Appointment(
            workspace_id=workspace.id,
            lead_id=leads["Michael Brooks"].id,
            starts_at=now - timedelta(days=1, hours=3),
            status="completed",
            notes="AC compressor repair completed.",
            created_at=now - timedelta(days=2),
        ),
    ]
    db.add_all(appointments)

    db.add_all(
        [
            RevenueEvent(
                workspace_id=workspace.id,
                lead_id=leads["Daniel Carter"].id,
                event_type="booked",
                amount=5900,
                attribution="nexora_assisted",
                source="seed",
                note="Replacement consultation booked.",
                created_at=now - timedelta(hours=3),
            ),
            RevenueEvent(
                workspace_id=workspace.id,
                lead_id=leads["Sarah Wilson"].id,
                event_type="booked",
                amount=3350,
                attribution="nexora_assisted",
                source="seed",
                note="Emergency service appointment booked.",
                created_at=now - timedelta(hours=1),
            ),
            RevenueEvent(
                workspace_id=workspace.id,
                lead_id=leads["Michael Brooks"].id,
                event_type="booked",
                amount=2800,
                attribution="nexora_assisted",
                source="seed",
                note="Repair appointment booked.",
                created_at=now - timedelta(days=2),
            ),
            RevenueEvent(
                workspace_id=workspace.id,
                lead_id=leads["Michael Brooks"].id,
                event_type="completed",
                amount=2800,
                attribution="nexora_assisted",
                source="seed",
                note="AC compressor repair completed and paid.",
                created_at=now - timedelta(days=1),
            ),
            RevenueEvent(
                workspace_id=workspace.id,
                lead_id=leads["Emily Davis"].id,
                event_type="booked",
                amount=5000,
                attribution="nexora_assisted",
                source="seed",
                note="Replacement booked after follow-up.",
                created_at=now - timedelta(days=4),
            ),
            RevenueEvent(
                workspace_id=workspace.id,
                lead_id=leads["Emily Davis"].id,
                event_type="recovered",
                amount=5000,
                attribution="followup",
                source="seed",
                note="Completed revenue recovered after Nexora follow-up activity.",
                created_at=now - timedelta(days=4),
            ),
            RevenueEvent(
                workspace_id=workspace.id,
                lead_id=leads["Emily Davis"].id,
                event_type="completed",
                amount=5000,
                attribution="nexora_assisted",
                source="seed",
                note="HVAC system replacement completed and paid.",
                created_at=now - timedelta(days=2),
            ),
        ]
    )

    db.add_all(
        [
            AutomationJob(
                workspace_id=workspace.id,
                lead_id=leads["Morgan Lee"].id,
                conversation_id=conversations["Morgan Lee"].id,
                kind="lead_followup",
                run_at=now + timedelta(minutes=45),
                status="pending",
                attempts=0,
                max_attempts=3,
                payload_json=json.dumps({"sequence_step": 1}),
                created_at=now - timedelta(hours=1),
            ),
            AutomationJob(
                workspace_id=workspace.id,
                lead_id=leads["Grace Kim"].id,
                conversation_id=conversations["Grace Kim"].id,
                kind="lead_followup",
                run_at=now + timedelta(hours=2),
                status="pending",
                attempts=0,
                max_attempts=3,
                payload_json=json.dumps({"sequence_step": 1}),
                created_at=now - timedelta(minutes=40),
            ),
        ]
    )

    db.add(
        Approval(
            workspace_id=workspace.id,
            agent_slug="operations",
            action_type="dispatch_technician",
            action_payload=json.dumps(
                {
                    "lead_id": leads["Sarah Wilson"].id,
                    "requested_window": "today",
                    "service_area_exception": True,
                }
            ),
            reason="Urgent no-heat request is just outside the standard service ZIP range.",
            status="pending",
            created_at=now - timedelta(minutes=50),
        )
    )

    db.add_all(
        [
            Task(
                workspace_id=workspace.id,
                lead_id=leads["Morgan Lee"].id,
                title="Review furnace replacement estimate",
                description="Confirm replacement options before next follow-up.",
                status="open",
                assigned_agent="sales",
                due_at=now + timedelta(hours=2),
                created_at=now - timedelta(hours=2),
            ),
            Task(
                workspace_id=workspace.id,
                lead_id=leads["Sarah Wilson"].id,
                title="Confirm emergency dispatch",
                description="Owner approval required for service-area exception.",
                status="open",
                assigned_agent="operations",
                due_at=now + timedelta(minutes=30),
                created_at=now - timedelta(minutes=50),
            ),
            Task(
                workspace_id=workspace.id,
                lead_id=leads["Grace Kim"].id,
                title="Prepare blower motor options",
                description="Keep technician assessment requirement in the estimate response.",
                status="open",
                assigned_agent="followup",
                due_at=now + timedelta(days=1),
                created_at=now - timedelta(hours=1),
            ),
        ]
    )

    activity_specs = [
        ("receptionist", "lead_captured", "Captured Avery Johnson from the website.", "lead", "Avery Johnson", 110),
        ("sales", "lead_qualified", "Qualified Jordan Smith for preventive maintenance.", "lead", "Jordan Smith", 100),
        ("sales", "appointment_proposed", "Proposed a maintenance window for Jordan Smith.", "lead", "Jordan Smith", 95),
        ("sales", "replacement_consultation", "Moved Daniel Carter to a heat pump replacement consultation.", "lead", "Daniel Carter", 90),
        ("operations", "appointment_confirmed", "Confirmed Daniel Carter’s replacement consultation.", "lead", "Daniel Carter", 86),
        ("receptionist", "urgent_intake", "Flagged Sarah Wilson as an urgent no-heat request.", "lead", "Sarah Wilson", 82),
        ("operations", "approval_requested", "Requested approval for Sarah Wilson service-area exception.", "lead", "Sarah Wilson", 78),
        ("operations", "appointment_confirmed", "Reserved priority service for Sarah Wilson.", "lead", "Sarah Wilson", 74),
        ("followup", "followup_sent", "Re-engaged Emily Davis on the replacement estimate.", "lead", "Emily Davis", 70),
        ("sales", "lead_recovered", "Emily Davis responded and resumed the replacement process.", "lead", "Emily Davis", 66),
        ("sales", "appointment_booked", "Booked Emily Davis after Nexora follow-up.", "lead", "Emily Davis", 62),
        ("operations", "job_completed", "Marked Emily Davis replacement job completed.", "lead", "Emily Davis", 58),
        ("operations", "revenue_recorded", "Recorded $5,000 completed revenue for Emily Davis.", "lead", "Emily Davis", 54),
        ("operations", "job_completed", "Marked Michael Brooks compressor repair completed.", "lead", "Michael Brooks", 50),
        ("operations", "revenue_recorded", "Recorded $2,800 completed revenue for Michael Brooks.", "lead", "Michael Brooks", 46),
        ("support", "conversation_review", "Reviewed Olivia Martinez airflow concern.", "lead", "Olivia Martinez", 42),
        ("manager", "human_takeover", "Nexora Admin took over Olivia Martinez’s conversation.", "lead", "Olivia Martinez", 36),
        ("followup", "followup_scheduled", "Scheduled the next follow-up for Morgan Lee.", "lead", "Morgan Lee", 32),
        ("followup", "followup_scheduled", "Scheduled the next follow-up for Grace Kim.", "lead", "Grace Kim", 28),
        ("manager", "daily_summary", "Reviewed pipeline, urgent work, approvals, and follow-up queue.", "workspace", None, 20),
    ]
    for agent_slug, action, summary, entity_type, lead_name, minutes_ago in activity_specs:
        entity_id = leads[lead_name].id if lead_name else workspace.id
        db.add(
            Activity(
                workspace_id=workspace.id,
                agent_slug=agent_slug,
                action=action,
                summary=summary,
                entity_type=entity_type,
                entity_id=entity_id,
                created_at=now - timedelta(minutes=minutes_ago),
            )
        )

    db.add_all(
        [
            UsageEvent(
                workspace_id=workspace.id,
                provider="local",
                model="local-model",
                agent_slug="sales",
                units=1820,
                estimated_cost=0,
                created_at=now - timedelta(hours=3),
            ),
            UsageEvent(
                workspace_id=workspace.id,
                provider="local",
                model="local-model",
                agent_slug="followup",
                units=920,
                estimated_cost=0,
                created_at=now - timedelta(hours=2),
            ),
        ]
    )

    db.commit()


def _clear_operational_data(db: Session, workspace: Workspace) -> None:
    conversation_ids = select(Conversation.id).where(Conversation.workspace_id == workspace.id)

    db.execute(
        delete(ConversationControl).where(
            ConversationControl.workspace_id == workspace.id
        )
    )
    db.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
    db.execute(delete(AutomationJob).where(AutomationJob.workspace_id == workspace.id))
    db.execute(delete(RevenueEvent).where(RevenueEvent.workspace_id == workspace.id))
    db.execute(delete(Appointment).where(Appointment.workspace_id == workspace.id))
    db.execute(delete(Task).where(Task.workspace_id == workspace.id))
    db.execute(delete(Approval).where(Approval.workspace_id == workspace.id))
    db.execute(delete(Activity).where(Activity.workspace_id == workspace.id))
    db.execute(delete(UsageEvent).where(UsageEvent.workspace_id == workspace.id))
    db.execute(delete(ExternalEvent).where(ExternalEvent.workspace_id == workspace.id))
    db.execute(delete(ConnectorSecret).where(ConnectorSecret.workspace_id == workspace.id))
    db.execute(delete(Conversation).where(Conversation.workspace_id == workspace.id))
    db.execute(delete(Lead).where(Lead.workspace_id == workspace.id))
    db.execute(delete(KnowledgeEntry).where(KnowledgeEntry.workspace_id == workspace.id))

    for item in db.scalars(
        select(Connector).where(Connector.workspace_id == workspace.id)
    ):
        item.status = "disconnected"
        item.mode = "mock"
        item.config_json = "{}"
        item.last_sync_at = None

    db.commit()


def _looks_like_legacy_minimal_seed(db: Session, workspace: Workspace) -> bool:
    leads = list(
        db.scalars(
            select(Lead).where(Lead.workspace_id == workspace.id)
        )
    )
    return len(leads) == 3 and {lead.name for lead in leads} == LEGACY_MINIMAL_LEADS


def reset_operational_workspace(db: Session) -> Workspace:
    settings = get_settings()
    if settings.app_env == "production" or not settings.demo_mode:
        raise RuntimeError(
            "Workspace reset is available only in local development/test mode."
        )

    workspace = _find_demo_workspace(db, settings)
    if not workspace:
        workspace = Workspace(
            name=DEMO_WORKSPACE_NAME,
            industry="HVAC",
            timezone=settings.default_timezone,
            phone="+1 212 555 0148",
            email="office@nexora.local",
            website="",
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
        db.commit()
        db.refresh(workspace)

    ensure_defaults(db, workspace, True)
    _clear_operational_data(db, workspace)
    _seed_operational_dataset(db, workspace)
    db.refresh(workspace)
    return workspace


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
            db.commit()

        ensure_defaults(db, workspace, True)
        if _looks_like_legacy_minimal_seed(db, workspace):
            _clear_operational_data(db, workspace)
            _seed_operational_dataset(db, workspace)
        db.refresh(workspace)
        return workspace

    workspace = Workspace(
        name=DEMO_WORKSPACE_NAME,
        industry="HVAC",
        timezone=settings.default_timezone,
        phone="+1 212 555 0148",
        email="office@nexora.local",
        website="",
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
    db.commit()
    db.refresh(workspace)
    ensure_defaults(db, workspace, True)
    _seed_operational_dataset(db, workspace)
    db.refresh(workspace)
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
            "Live mode requires BOOTSTRAP_ADMIN_EMAIL and a 12+ character BOOTSTRAP_ADMIN_PASSWORD for the initial owner account."
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
