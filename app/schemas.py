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
