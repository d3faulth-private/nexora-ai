from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .ai import AIResponse, get_ai_provider


@dataclass
class AgentDecision:
    agent: str
    reply: str
    stage: str | None = None
    urgency: str | None = None
    actions: list[str] | None = None
    proposal: dict | None = None
    ai: AIResponse | None = None


def _contains(text: str, values: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(value in lowered for value in values)


def route_message(body: str) -> str:
    if _contains(body, ("refund", "complaint", "unhappy", "cancel", "warranty", "bad service")):
        return "support"
    if _contains(body, ("quote", "estimate", "price", "cost", "appointment", "book", "ac", "furnace", "heat", "cooling", "repair")):
        return "sales"
    return "receptionist"


def next_service_slot() -> datetime:
    candidate = datetime.now(timezone.utc) + timedelta(days=1)
    return candidate.replace(hour=14, minute=0, second=0, microsecond=0)


def customer_decision(agent_slug: str, body: str, lead_name: str, knowledge: str = "") -> AgentDecision:
    ai = get_ai_provider()

    urgent = _contains(body, ("no heat", "no ac", "stopped", "not working", "emergency", "leak", "smoke", "burning"))
    soon = _contains(body, ("today", "tomorrow", "asap", "urgent", "immediately"))
    quote = _contains(body, ("quote", "estimate", "price", "cost"))

    if agent_slug == "support":
        fallback = (
            "Thanks, " + lead_name + ". I have logged this for support. "
            "Please share the service address and what happened. A team member can review the case."
        )
        result = ai.generate(
            "You are Nexora Support for a service business. Be concise. Do not invent policies, refunds, or prices. " + knowledge,
            body,
            fallback,
        )
        return AgentDecision(
            agent="support",
            reply=result.text,
            stage="support",
            urgency="urgent" if urgent else "normal",
            actions=["log_support_case"],
            ai=result,
        )

    if agent_slug == "sales":
        if urgent or soon:
            fallback = (
                "Thanks, " + lead_name + ". I marked this as priority. "
                "I can propose the next available service window. Please confirm the service ZIP code and best phone number."
            )
            result = ai.generate(
                "You are Nexora Sales for a service business. Be concise and helpful. Never promise a guaranteed arrival time or fixed price. " + knowledge,
                body,
                fallback,
            )
            return AgentDecision(
                agent="sales",
                reply=result.text,
                stage="qualified",
                urgency="urgent" if urgent else "high",
                actions=["qualify_lead", "propose_appointment"],
                proposal={"starts_at": next_service_slot().isoformat()},
                ai=result,
            )

        if quote:
            fallback = (
                "Absolutely, " + lead_name + ". I can prepare this for an estimate. "
                "What service is needed, what ZIP code is the property in, and when would you like the work completed?"
            )
            result = ai.generate(
                "You are Nexora Sales. Collect only the information needed to qualify a service lead. " + knowledge,
                body,
                fallback,
            )
            return AgentDecision(
                agent="sales",
                reply=result.text,
                stage="contacted",
                actions=["request_qualification_details"],
                ai=result,
            )

        fallback = (
            "Thanks for reaching out, " + lead_name + ". "
            "What service do you need, what ZIP code is the property in, and what day works best?"
        )
        result = ai.generate("You are Nexora Sales. " + knowledge, body, fallback)
        return AgentDecision(
            agent="sales",
            reply=result.text,
            stage="contacted",
            actions=["start_qualification"],
            ai=result,
        )

    fallback = (
        "Thanks, " + lead_name + ". I can route this to the right team. "
        "Please tell me what you need help with and the ZIP code for the property."
    )
    result = ai.generate("You are Nexora Receptionist. Be brief, friendly, and accurate. " + knowledge, body, fallback)
    return AgentDecision(
        agent="receptionist",
        reply=result.text,
        stage="contacted",
        actions=["capture_inquiry"],
        ai=result,
    )


def followup_message(lead_name: str, issue: str) -> str:
    topic = issue.strip() or "your recent service request"
    return (
        "Hi " + lead_name + ", just following up on " + topic + ". "
        "If you still need help, reply with a day that works and we can move the request forward."
    )


def manager_intent(objective: str) -> str:
    value = objective.lower()
    if "follow" in value and ("not booked" in value or "hasn't booked" in value or "open lead" in value):
        return "followup_open"
    if ("show" in value or "list" in value) and "lead" in value:
        return "show_leads"
    if "approval" in value:
        return "show_approvals"
    if "task" in value and ("create" in value or "add" in value):
        return "create_task"
    return "summary"
