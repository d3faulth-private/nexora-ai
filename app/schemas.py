from datetime import datetime
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str | None = None
    phone: str | None = None
    zip_code: str | None = None
    source: str = "website"
    issue: str = ""
    estimated_value: float = 0


class LeadUpdate(BaseModel):
    stage: str | None = None
    urgency: str | None = None
    issue: str | None = None
    estimated_value: float | None = None


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    channel: str = "web"


class HumanMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ManagerCommand(BaseModel):
    objective: str = Field(min_length=1, max_length=1000)


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    industry: str | None = None
    timezone: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    knowledge_summary: str | None = None


class OnboardingUpdate(BaseModel):
    business_name: str = Field(min_length=1, max_length=160)
    industry: str = "HVAC"
    timezone: str = "America/New_York"
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    services: list[str] = Field(default_factory=list, min_length=1)
    service_area: str = Field(min_length=1)
    business_hours: str = Field(min_length=1)
    emergency_policy: str = Field(min_length=1)
    knowledge_summary: str = ""
    booking_duration_minutes: int = Field(default=60, ge=15, le=480)
    followup_after_minutes: int = Field(default=120, ge=15, le=10080)
    followup_max_attempts: int = Field(default=3, ge=0, le=10)


class AppointmentCreate(BaseModel):
    lead_id: int
    starts_at: datetime
    notes: str = ""


class KnowledgeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    content: str = Field(min_length=1)
    tags: str = ""


class ApprovalResolve(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")


class ConnectorUpdate(BaseModel):
    status: str | None = None
    mode: str | None = None


class HubSpotConnect(BaseModel):
    private_app_token: str = Field(min_length=10)


class WebhookConnect(BaseModel):
    url: str = Field(min_length=8)
    secret: str = ""


class IntakeEvent(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str | None = None
    phone: str | None = None
    zip_code: str | None = None
    issue: str = Field(min_length=1, max_length=4000)
    source: str = "webhook"
    external_id: str | None = None
    estimated_value: float = 0
