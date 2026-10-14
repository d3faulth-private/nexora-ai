from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .agents import AgentDecision, customer_decision, followup_message, manager_intent, route_message
from .automation import schedule_followup_for_lead
from .hvac import hvac_knowledge_text
from .connectors.providers import hubspot_upsert_contact, signed_webhook
from .models import (
    Activity,
    Agent,
    Approval,
    Appointment,
    AutomationJob,
    Connector,
    Conversation,
    ConversationControl,
    KnowledgeEntry,
    Lead,
    Message,
    Task,
    UsageEvent,
    User,
    Workspace,
    WorkspaceProfile,
)
from .policy import evaluate_action
from .revenue import opportunity_list, revenue_summary
from .security import verify_password


def activity(
    db: Session,
    workspace_id: int,
    agent_slug: str,
    action: str,
    summary: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
):
    item = Activity(
        workspace_id=workspace_id,
        agent_slug=agent_slug,
        action=action,
        summary=summary,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(item)
    return item


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_workspace(db: Session, workspace_id: int) -> Workspace | None:
    return db.get(Workspace, workspace_id)


def get_agent(db: Session, workspace_id: int, slug: str) -> Agent | None:
    return db.scalar(
        select(Agent).where(Agent.workspace_id == workspace_id, Agent.slug == slug)
    )


def get_profile(db: Session, workspace_id: int) -> WorkspaceProfile | None:
    return db.scalar(
        select(WorkspaceProfile).where(WorkspaceProfile.workspace_id == workspace_id)
    )


def profile_dict(profile: WorkspaceProfile | None) -> dict:
    if not profile:
        return {}
    try:
        services = json.loads(profile.services_json or "[]")
    except json.JSONDecodeError:
        services = []
    return {
        "services": services,
        "service_area": profile.service_area,
        "business_hours": profile.business_hours,
        "emergency_policy": profile.emergency_policy,
        "booking_duration_minutes": profile.booking_duration_minutes,
        "followup_after_minutes": profile.followup_after_minutes,
        "followup_max_attempts": profile.followup_max_attempts,
        "onboarding_completed": profile.onboarding_completed,
    }


def upsert_profile(db: Session, workspace: Workspace, payload: dict) -> WorkspaceProfile:
    workspace.name = payload["business_name"]
    workspace.industry = payload.get("industry") or "HVAC"
    workspace.timezone = payload.get("timezone") or workspace.timezone
    workspace.phone = payload.get("phone")
    workspace.email = payload.get("email")
    workspace.website = payload.get("website")

    profile = get_profile(db, workspace.id)
    if not profile:
        profile = WorkspaceProfile(workspace_id=workspace.id)
        db.add(profile)
        db.flush()

    profile.services_json = json.dumps(payload.get("services") or [])
    profile.service_area = payload.get("service_area") or ""
    profile.business_hours = payload.get("business_hours") or ""
    profile.emergency_policy = payload.get("emergency_policy") or ""
    profile.booking_duration_minutes = int(payload.get("booking_duration_minutes") or 60)
    profile.followup_after_minutes = int(payload.get("followup_after_minutes") or 120)
    profile.followup_max_attempts = int(payload.get("followup_max_attempts") or 3)
    profile.onboarding_completed = True
    profile.updated_at = datetime.now(timezone.utc)

    activity(
        db,
        workspace.id,
        "operations",
        "onboarding_updated",
        "Business onboarding profile updated.",
        "workspace",
        workspace.id,
    )
    db.commit()
    db.refresh(profile)
    return profile


def knowledge_context(db: Session, workspace: Workspace) -> str:
    entries = list(
        db.scalars(
            select(KnowledgeEntry)
            .where(
                KnowledgeEntry.workspace_id == workspace.id,
                KnowledgeEntry.is_active.is_(True),
            )
            .order_by(KnowledgeEntry.id)
            .limit(20)
        )
    )
    parts = [workspace.knowledge_summary]
    profile = get_profile(db, workspace.id)
    if profile:
        parts.append(hvac_knowledge_text(profile_dict(profile)))
    parts.extend(entry.title + ": " + entry.content for entry in entries)
    return " ".join(part for part in parts if part)


def conversation_for_lead(
    db: Session,
    workspace_id: int,
    lead_id: int,
    channel: str = "web",
) -> Conversation:
    conversation = db.scalar(
        select(Conversation)
        .where(
            Conversation.workspace_id == workspace_id,
            Conversation.lead_id == lead_id,
            Conversation.status == "open",
        )
        .order_by(Conversation.id.desc())
    )
    if conversation:
        return conversation

    conversation = Conversation(
        workspace_id=workspace_id,
        lead_id=lead_id,
        channel=channel,
        status="open",
    )
    db.add(conversation)
    db.flush()
    return conversation


def conversation_control(
    db: Session,
    workspace_id: int,
    conversation_id: int,
) -> ConversationControl:
    control = db.scalar(
        select(ConversationControl).where(
            ConversationControl.workspace_id == workspace_id,
            ConversationControl.conversation_id == conversation_id,
        )
    )
    if control:
        return control

    control = ConversationControl(
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        mode="ai",
    )
    db.add(control)
    db.flush()
    return control


def set_handoff(
    db: Session,
    workspace: Workspace,
    conversation: Conversation,
    user: User,
    mode: str,
) -> ConversationControl:
    control = conversation_control(db, workspace.id, conversation.id)
    now = datetime.now(timezone.utc)

    if mode == "human":
        control.mode = "human"
        control.taken_over_by_user_id = user.id
        control.taken_over_at = now
        activity(
            db,
            workspace.id,
            "manager",
            "human_takeover",
            user.name + " took over conversation " + str(conversation.id) + ".",
            "conversation",
            conversation.id,
        )
    elif mode == "ai":
        control.mode = "ai"
        control.returned_at = now
        activity(
            db,
            workspace.id,
            "manager",
            "returned_to_ai",
            "Conversation " + str(conversation.id) + " returned to Nexora.",
            "conversation",
            conversation.id,
        )
    else:
        raise ValueError("Unsupported handoff mode")

    db.commit()
    db.refresh(control)
    return control


def record_usage(db: Session, workspace_id: int, agent_slug: str, ai_response):
    if not ai_response:
        return
    db.add(
        UsageEvent(
            workspace_id=workspace_id,
            provider=ai_response.provider,
            model=ai_response.model,
            agent_slug=agent_slug,
            units=ai_response.units,
            estimated_cost=ai_response.estimated_cost,
        )
    )


def _ensure_followup_job(
    db: Session,
    workspace: Workspace,
    lead: Lead,
    conversation: Conversation,
) -> None:
    if lead.stage not in {"new", "contacted", "qualified"}:
        return

    exists = db.scalar(
        select(AutomationJob).where(
            AutomationJob.workspace_id == workspace.id,
            AutomationJob.lead_id == lead.id,
            AutomationJob.kind == "lead_followup",
            AutomationJob.status == "pending",
        )
    )
    if not exists:
        schedule_followup_for_lead(db, workspace.id, lead.id, conversation.id)


def _sync_external_best_effort(db: Session, workspace: Workspace, lead: Lead) -> None:
    contact = {
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "zip_code": lead.zip_code,
    }
    try:
        hubspot_upsert_contact(db, workspace.id, contact)
        activity(
            db,
            workspace.id,
            "operations",
            "crm_synced",
            "Synced " + lead.name + " to CRM.",
            "lead",
            lead.id,
        )
    except Exception:
        pass

    try:
        signed_webhook(
            db,
            workspace.id,
            "lead.updated",
            {
                "lead_id": lead.id,
                "name": lead.name,
                "stage": lead.stage,
                "urgency": lead.urgency,
            },
        )
    except Exception:
        pass


def process_customer_message(
    db: Session,
    workspace: Workspace,
    lead: Lead,
    body: str,
    channel: str = "web",
):
    conversation = conversation_for_lead(db, workspace.id, lead.id, channel)
    control = conversation_control(db, workspace.id, conversation.id)

    db.add(
        Message(
            conversation_id=conversation.id,
            direction="inbound",
            actor="customer",
            body=body,
        )
    )

    if control.mode == "human":
        activity(
            db,
            workspace.id,
            "manager",
            "inbound_held_for_human",
            "Customer message held for human owner on " + lead.name + ".",
            "lead",
            lead.id,
        )
        db.commit()
        return (
            AgentDecision(
                agent="human",
                reply="",
                actions=["held_for_human"],
            ),
            None,
            conversation,
        )

    target = route_message(body)
    agent = get_agent(db, workspace.id, target)
    if not agent or not agent.enabled:
        target = "receptionist"
        agent = get_agent(db, workspace.id, target)

    decision = customer_decision(
        target,
        body,
        lead.name,
        knowledge_context(db, workspace),
    )
    conversation.assigned_agent = decision.agent

    if decision.stage:
        lead.stage = decision.stage
    if decision.urgency:
        lead.urgency = decision.urgency
    if not lead.issue:
        lead.issue = body
    lead.last_contacted_at = datetime.now(timezone.utc)

    appointment = None
    if decision.proposal and decision.proposal.get("starts_at"):
        appointment = Appointment(
            workspace_id=workspace.id,
            lead_id=lead.id,
            starts_at=datetime.fromisoformat(decision.proposal["starts_at"]),
            status="proposed",
            notes="Proposed by Nexora Sales. Confirmation remains under business control.",
        )
        db.add(appointment)

    if decision.reply:
        db.add(
            Message(
                conversation_id=conversation.id,
                direction="outbound",
                actor=decision.agent,
                body=decision.reply,
            )
        )

    activity(
        db,
        workspace.id,
        decision.agent,
        "message_processed",
        decision.agent.title() + " handled a customer message from " + lead.name + ".",
        "lead",
        lead.id,
    )
    for action_name in decision.actions or []:
        activity(
            db,
            workspace.id,
            decision.agent,
            action_name,
            action_name.replace("_", " ").title() + " for " + lead.name + ".",
            "lead",
            lead.id,
        )

    record_usage(db, workspace.id, decision.agent, decision.ai)
    _ensure_followup_job(db, workspace, lead, conversation)
    _sync_external_best_effort(db, workspace, lead)
    db.commit()

    if appointment:
        db.refresh(appointment)
    db.refresh(lead)
    return decision, appointment, conversation


def add_human_message(
    db: Session,
    workspace: Workspace,
    user: User,
    lead: Lead,
    body: str,
):
    conversation = conversation_for_lead(db, workspace.id, lead.id, "web")
    control = conversation_control(db, workspace.id, conversation.id)
    if control.mode != "human":
        raise ValueError("Human takeover is not active.")

    db.add(
        Message(
            conversation_id=conversation.id,
            direction="outbound",
            actor="human:" + user.name,
            body=body,
        )
    )
    lead.last_contacted_at = datetime.now(timezone.utc)
    activity(
        db,
        workspace.id,
        "manager",
        "human_message",
        user.name + " replied to " + lead.name + ".",
        "lead",
        lead.id,
    )
    db.commit()
    return conversation


def request_action(
    db: Session,
    workspace: Workspace,
    agent_slug: str,
    action_type: str,
    payload: dict,
    reason: str = "",
):
    agent = get_agent(db, workspace.id, agent_slug)
    autonomy = agent.autonomy_level if agent else "guarded"
    policy = evaluate_action(action_type, autonomy)

    if not policy.allowed:
        return {"status": "blocked", "reason": policy.reason}

    if policy.requires_approval:
        approval = Approval(
            workspace_id=workspace.id,
            agent_slug=agent_slug,
            action_type=action_type,
            action_payload=json.dumps(payload),
            reason=reason or policy.reason,
            status="pending",
        )
        db.add(approval)
        activity(
            db,
            workspace.id,
            agent_slug,
            "approval_requested",
            "Approval requested for " + action_type + ".",
            "approval",
            None,
        )
        db.commit()
        db.refresh(approval)
        return {"status": "pending_approval", "approval_id": approval.id}

    return {"status": "allowed"}


def run_manager(db: Session, workspace: Workspace, objective: str) -> dict:
    manager = get_agent(db, workspace.id, "manager")
    if manager and not manager.enabled:
        return {"intent": "blocked", "message": "Nexora Manager is disabled.", "actions": []}

    intent = manager_intent(objective)

    if intent == "followup_open":
        followup_agent = get_agent(db, workspace.id, "followup")
        if not followup_agent or not followup_agent.enabled:
            return {"intent": intent, "message": "Nexora Follow-Up is disabled.", "actions": []}

        leads = list(
            db.scalars(
                select(Lead).where(
                    Lead.workspace_id == workspace.id,
                    Lead.stage.in_(("new", "contacted", "qualified")),
                )
            )
        )
        actions = []
        for lead in leads:
            confirmed = db.scalar(
                select(func.count(Appointment.id)).where(
                    Appointment.lead_id == lead.id,
                    Appointment.status.in_(("confirmed", "completed")),
                )
            )
            if confirmed:
                continue

            conversation = conversation_for_lead(db, workspace.id, lead.id, "web")
            control = conversation_control(db, workspace.id, conversation.id)
            if control.mode == "human":
                continue

            db.add(
                Message(
                    conversation_id=conversation.id,
                    direction="outbound",
                    actor="followup",
                    body=followup_message(lead.name, lead.issue),
                )
            )
            lead.last_contacted_at = datetime.now(timezone.utc)
            if lead.stage == "new":
                lead.stage = "contacted"
            actions.append("Prepared follow-up for " + lead.name)
            activity(
                db,
                workspace.id,
                "followup",
                "followup_prepared",
                actions[-1],
                "lead",
                lead.id,
            )

        activity(
            db,
            workspace.id,
            "manager",
            "objective_completed",
            "Executed objective: " + objective,
        )
        db.commit()
        return {
            "intent": intent,
            "message": "Prepared follow-up for " + str(len(actions)) + " open leads.",
            "actions": actions,
        }

    if intent == "show_leads":
        leads = list(db.scalars(select(Lead).where(Lead.workspace_id == workspace.id)))
        return {
            "intent": intent,
            "message": str(len(leads)) + " leads in the workspace.",
            "actions": [
                lead.name
                + ": "
                + lead.stage
                + " (USD "
                + format(lead.estimated_value, ",.0f")
                + ")"
                for lead in leads
            ],
        }

    if intent == "show_approvals":
        count = db.scalar(
            select(func.count(Approval.id)).where(
                Approval.workspace_id == workspace.id,
                Approval.status == "pending",
            )
        )
        return {
            "intent": intent,
            "message": str(count) + " pending approvals.",
            "actions": [],
        }

    leads = list(db.scalars(select(Lead).where(Lead.workspace_id == workspace.id)))
    pipeline = sum(
        lead.estimated_value
        for lead in leads
        if lead.stage not in ("lost", "completed")
    )
    pending = db.scalar(
        select(func.count(Approval.id)).where(
            Approval.workspace_id == workspace.id,
            Approval.status == "pending",
        )
    )
    message = (
        "Pipeline USD "
        + format(pipeline, ",.0f")
        + ". "
        + str(len(leads))
        + " leads. "
        + str(pending)
        + " approvals waiting."
    )
    activity(db, workspace.id, "operations", "summary_generated", message)
    db.commit()
    return {"intent": "summary", "message": message, "actions": []}


def dashboard(db: Session, workspace: Workspace) -> dict:
    leads = list(
        db.scalars(
            select(Lead)
            .where(Lead.workspace_id == workspace.id)
            .order_by(Lead.created_at.desc())
        )
    )
    agents = list(
        db.scalars(
            select(Agent)
            .where(Agent.workspace_id == workspace.id)
            .order_by(Agent.id)
        )
    )
    activities = list(
        db.scalars(
            select(Activity)
            .where(Activity.workspace_id == workspace.id)
            .order_by(Activity.created_at.desc())
            .limit(30)
        )
    )
    approvals = list(
        db.scalars(
            select(Approval)
            .where(
                Approval.workspace_id == workspace.id,
                Approval.status == "pending",
            )
            .order_by(Approval.created_at.desc())
        )
    )
    appointments = list(
        db.scalars(
            select(Appointment)
            .where(Appointment.workspace_id == workspace.id)
            .order_by(Appointment.starts_at.desc())
        )
    )
    connectors = list(
        db.scalars(
            select(Connector)
            .where(Connector.workspace_id == workspace.id)
            .order_by(Connector.id)
        )
    )
    tasks = list(
        db.scalars(
            select(Task)
            .where(
                Task.workspace_id == workspace.id,
                Task.status != "completed",
            )
            .order_by(Task.created_at.desc())
            .limit(20)
        )
    )
    pending_jobs = db.scalar(
        select(func.count(AutomationJob.id)).where(
            AutomationJob.workspace_id == workspace.id,
            AutomationJob.status == "pending",
        )
    )
    usage_cost = db.scalar(
        select(func.coalesce(func.sum(UsageEvent.estimated_cost), 0)).where(
            UsageEvent.workspace_id == workspace.id
        )
    )
    revenue = revenue_summary(db, workspace.id)
    opportunities = opportunity_list(db, workspace.id, limit=8)
    pipeline = revenue["pipeline"]
    profile = get_profile(db, workspace.id)

    lead_rows = []
    for lead in leads:
        conversation = db.scalar(
            select(Conversation)
            .where(
                Conversation.workspace_id == workspace.id,
                Conversation.lead_id == lead.id,
                Conversation.status == "open",
            )
            .order_by(Conversation.id.desc())
        )
        human_control = False
        if conversation:
            control = db.scalar(
                select(ConversationControl).where(
                    ConversationControl.conversation_id == conversation.id
                )
            )
            human_control = bool(control and control.mode == "human")

        lead_rows.append(
            {
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
                "human_control": human_control,
                "created_at": lead.created_at,
            }
        )

    return {
        "workspace": {
            "id": workspace.id,
            "name": workspace.name,
            "industry": workspace.industry,
            "timezone": workspace.timezone,
        },
        "profile": profile_dict(profile),
        "metrics": {
            "leads": len(leads),
            "qualified": sum(1 for lead in leads if lead.stage == "qualified"),
            "appointments": len(appointments),
            "pipeline": pipeline,
            "pending_approvals": len(approvals),
            "open_tasks": len(tasks),
            "pending_automations": int(pending_jobs or 0),
            "estimated_ai_cost": float(usage_cost or 0),
            "booked_pipeline": revenue["booked_pipeline"],
            "completed_revenue": revenue["completed_revenue"],
            "recovered_revenue": revenue["recovered_revenue"],
            "open_opportunity": revenue["open_opportunity"],
        },
        "agents": [
            {
                "id": agent.id,
                "slug": agent.slug,
                "name": agent.name,
                "role": agent.role,
                "enabled": agent.enabled,
                "autonomy_level": agent.autonomy_level,
            }
            for agent in agents
        ],
        "leads": lead_rows,
        "opportunities": opportunities,
        "approvals": [
            {
                "id": item.id,
                "agent_slug": item.agent_slug,
                "action_type": item.action_type,
                "reason": item.reason,
                "created_at": item.created_at,
            }
            for item in approvals
        ],
        "connectors": [
            {
                "id": item.id,
                "slug": item.slug,
                "name": item.name,
                "status": item.status,
                "mode": item.mode,
            }
            for item in connectors
        ],
        "activities": [
            {
                "id": item.id,
                "agent_slug": item.agent_slug,
                "action": item.action,
                "summary": item.summary,
                "created_at": item.created_at,
            }
            for item in activities
        ],
    }
