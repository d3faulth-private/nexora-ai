from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str | None = None
    phone: str | None = None
    zip_code: str | None = None
    source: str = "website"
    issue: str = ""
    estimated_value: float = 0


class LeadUpdate(BaseModel):
    stage: Literal["new", "contacted", "qualified", "booked", "completed", "lost", "support"] | None = None
    urgency: Literal["normal", "high", "urgent"] | None = None
    issue: str | None = None
    estimated_value: float | None = None


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    channel: str = "web"


class HumanMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ManagerCommand(BaseModel):
    objective: str = Field(min_length=1, max_length=1000)


class OnboardingUpdate(BaseModel):
    business_name: str = Field(min_length=1, max_length=160)
    industry: Literal["HVAC"] = "HVAC"
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


class ConnectorUpdate(BaseModel):
    status: str | None = None
    mode: str | None = None


class HubSpotConnect(BaseModel):
    private_app_token: str = Field(min_length=10)


class WebhookConnect(BaseModel):
    url: str = Field(min_length=8)
    secret: str = Field(min_length=16)


class IntakeEvent(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str | None = None
    phone: str | None = None
    zip_code: str | None = None
    issue: str = Field(min_length=1, max_length=4000)
    source: str = "webhook"
    external_id: str | None = None
    estimated_value: float = 0
