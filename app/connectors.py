from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class ConnectorResult:
    ok: bool
    provider: str
    action: str
    external_id: str | None = None
    detail: str = ""


class MockConnectorHub:
    """Safe local connector layer used by the MVP.

    Real provider adapters can implement the same methods without changing agent logic.
    """

    def send_email(self, to: str, subject: str, body: str) -> ConnectorResult:
        stamp = int(datetime.now(timezone.utc).timestamp())
        return ConnectorResult(
            ok=True,
            provider="mock_email",
            action="send_email",
            external_id="mock-email-" + str(stamp),
            detail="Email simulated; no external message was sent.",
        )

    def create_calendar_event(self, title: str, starts_at: str, attendee: str | None = None) -> ConnectorResult:
        stamp = int(datetime.now(timezone.utc).timestamp())
        return ConnectorResult(
            ok=True,
            provider="mock_calendar",
            action="create_event",
            external_id="mock-event-" + str(stamp),
            detail="Calendar event simulated.",
        )

    def upsert_crm_contact(self, payload: dict[str, Any]) -> ConnectorResult:
        stamp = int(datetime.now(timezone.utc).timestamp())
        return ConnectorResult(
            ok=True,
            provider="mock_crm",
            action="upsert_contact",
            external_id="mock-contact-" + str(stamp),
            detail="CRM sync simulated.",
        )

    def call_webhook(self, url: str, payload: dict[str, Any]) -> ConnectorResult:
        stamp = int(datetime.now(timezone.utc).timestamp())
        return ConnectorResult(
            ok=True,
            provider="mock_webhook",
            action="post",
            external_id="mock-hook-" + str(stamp),
            detail="Webhook simulated.",
        )


connector_hub = MockConnectorHub()
