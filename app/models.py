from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    industry: Mapped[str] = mapped_column(String(80), default="home_services")
    timezone: Mapped[str] = mapped_column(String(80), default="America/New_York")
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    knowledge_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    agents: Mapped[list["Agent"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    leads: Mapped[list["Lead"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("workspace_id", "email", name="uq_user_workspace_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    email: Mapped[str] = mapped_column(String(160))
    name: Mapped[str] = mapped_column(String(120), default="Admin")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default="owner")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workspace: Mapped["Workspace"] = relationship(back_populates="users")


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_agent_workspace_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    slug: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(180))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    autonomy_level: Mapped[str] = mapped_column(String(30), default="guarded")
    system_prompt: Mapped[str] = mapped_column(Text, default="")

    workspace: Mapped["Workspace"] = relationship(back_populates="agents")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str] = mapped_column(String(60), default="website")
    stage: Mapped[str] = mapped_column(String(40), default="new")
    urgency: Mapped[str] = mapped_column(String(40), default="normal")
    issue: Mapped[str] = mapped_column(Text, default="")
    estimated_value: Mapped[float] = mapped_column(Float, default=0)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workspace: Mapped["Workspace"] = relationship(back_populates="leads")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship(back_populates="lead", cascade="all, delete-orphan")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"))
    channel: Mapped[str] = mapped_column(String(30), default="web")
    status: Mapped[str] = mapped_column(String(30), default="open")
    assigned_agent: Mapped[str] = mapped_column(String(60), default="receptionist")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    lead: Mapped["Lead"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    direction: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="proposed")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    lead: Mapped["Lead"] = relationship(back_populates="appointments")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="open")
    assigned_agent: Mapped[str] = mapped_column(String(60), default="manager")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    lead: Mapped["Lead | None"] = relationship(back_populates="tasks")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    agent_slug: Mapped[str] = mapped_column(String(60))
    action_type: Mapped[str] = mapped_column(String(80))
    action_payload: Mapped[str] = mapped_column(Text, default="{}")
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    resolved_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    title: Mapped[str] = mapped_column(String(180))
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Connector(Base):
    __tablename__ = "connectors"
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_connector_workspace_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    slug: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="disconnected")
    mode: Mapped[str] = mapped_column(String(30), default="mock")
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    agent_slug: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    provider: Mapped[str] = mapped_column(String(60), default="local")
    model: Mapped[str] = mapped_column(String(100), default="local")
    agent_slug: Mapped[str] = mapped_column(String(60))
    units: Mapped[float] = mapped_column(Float, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)



class WorkspaceProfile(Base):
    __tablename__ = "workspace_profiles"
    __table_args__ = (UniqueConstraint("workspace_id", name="uq_workspace_profile"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    services_json: Mapped[str] = mapped_column(Text, default="[]")
    service_area: Mapped[str] = mapped_column(Text, default="")
    business_hours: Mapped[str] = mapped_column(Text, default="")
    emergency_policy: Mapped[str] = mapped_column(Text, default="")
    booking_duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    followup_after_minutes: Mapped[int] = mapped_column(Integer, default=120)
    followup_max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConversationControl(Base):
    __tablename__ = "conversation_controls"
    __table_args__ = (UniqueConstraint("conversation_id", name="uq_conversation_control"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    mode: Mapped[str] = mapped_column(String(20), default="ai")
    taken_over_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    taken_over_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AutomationJob(Base):
    __tablename__ = "automation_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), nullable=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(60))
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConnectorSecret(Base):
    __tablename__ = "connector_secrets"
    __table_args__ = (UniqueConstraint("workspace_id", "connector_slug", name="uq_connector_secret"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    connector_slug: Mapped[str] = mapped_column(String(60))
    secret_blob: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExternalEvent(Base):
    __tablename__ = "external_events"
    __table_args__ = (
        UniqueConstraint("workspace_id", "provider", "idempotency_key", name="uq_external_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    provider: Mapped[str] = mapped_column(String(60))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(80), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(30), default="received")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)



class RevenueEvent(Base):
    __tablename__ = "revenue_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40))
    amount: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    attribution: Mapped[str] = mapped_column(String(80), default="nexora")
    source: Mapped[str] = mapped_column(String(80), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
