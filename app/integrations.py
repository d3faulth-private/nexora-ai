from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Connector, ConnectorSecret, ExternalEvent
from .vault import decrypt_json, encrypt_json


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]


@dataclass
class IntegrationResult:
    ok: bool
    provider: str
    action: str
    external_id: str | None = None
    detail: str = ""
    data: dict | None = None


def connector(db: Session, workspace_id: int, slug: str) -> Connector | None:
    return db.scalar(
        select(Connector).where(
            Connector.workspace_id == workspace_id,
            Connector.slug == slug,
        )
    )


def _secret_row(db: Session, workspace_id: int, slug: str) -> ConnectorSecret | None:
    return db.scalar(
        select(ConnectorSecret).where(
            ConnectorSecret.workspace_id == workspace_id,
            ConnectorSecret.connector_slug == slug,
        )
    )


def set_secret(db: Session, workspace_id: int, slug: str, value: dict) -> None:
    blob = encrypt_json(value)
    row = _secret_row(db, workspace_id, slug)
    if row:
        row.secret_blob = blob
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(
            ConnectorSecret(
                workspace_id=workspace_id,
                connector_slug=slug,
                secret_blob=blob,
            )
        )


def get_secret(db: Session, workspace_id: int, slug: str) -> dict:
    row = _secret_row(db, workspace_id, slug)
    if not row:
        return {}
    return decrypt_json(row.secret_blob)


def mark_connector(
    db: Session,
    workspace_id: int,
    slug: str,
    status: str,
    mode: str = "real",
    config: dict | None = None,
) -> Connector:
    item = connector(db, workspace_id, slug)
    if not item:
        item = Connector(
            workspace_id=workspace_id,
            slug=slug,
            name=slug.replace("_", " ").title(),
            status=status,
            mode=mode,
        )
        db.add(item)
        db.flush()
    else:
        item.status = status
        item.mode = mode

    if config is not None:
        item.config_json = json.dumps(config)
    item.last_sync_at = datetime.now(timezone.utc)
    return item


def google_authorization_url(state: str) -> str:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise RuntimeError("Google OAuth credentials are not configured.")

    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(GOOGLE_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
    )
    return GOOGLE_AUTH_URL + "?" + query


def exchange_google_code(code: str) -> dict:
    settings = get_settings()
    response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    expires_in = int(data.get("expires_in") or 3600)
    data["expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in - 60))
    ).isoformat()
    return data


def _google_token(db: Session, workspace_id: int) -> str:
    settings = get_settings()
    tokens = get_secret(db, workspace_id, "google")
    if not tokens:
        raise RuntimeError("Google is not connected.")

    expires_at_raw = tokens.get("expires_at")
    expires_at = datetime.fromisoformat(expires_at_raw) if expires_at_raw else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at and expires_at > datetime.now(timezone.utc):
        return str(tokens["access_token"])

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("Google access expired and no refresh token is available.")

    response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    response.raise_for_status()
    refreshed = response.json()
    tokens["access_token"] = refreshed["access_token"]
    expires_in = int(refreshed.get("expires_in") or 3600)
    tokens["expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in - 60))
    ).isoformat()
    set_secret(db, workspace_id, "google", tokens)
    db.commit()
    return str(tokens["access_token"])


def gmail_send(
    db: Session,
    workspace_id: int,
    to: str,
    subject: str,
    body: str,
) -> IntegrationResult:
    item = connector(db, workspace_id, "google")
    if item and item.mode == "mock" and item.status == "connected":
        return IntegrationResult(
            ok=True,
            provider="mock_google",
            action="gmail_send",
            external_id="mock-email",
            detail="Gmail send simulated.",
        )

    token = _google_token(db, workspace_id)
    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")
    response = httpx.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": "Bearer " + token},
        json={"raw": raw},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    return IntegrationResult(
        ok=True,
        provider="google",
        action="gmail_send",
        external_id=str(data.get("id") or ""),
        data=data,
    )


def _gmail_header(payload: dict, name: str) -> str:
    for header in payload.get("headers") or []:
        if str(header.get("name") or "").lower() == name.lower():
            return str(header.get("value") or "")
    return ""


def _gmail_text(payload: dict) -> str:
    body = payload.get("body") or {}
    data = body.get("data")
    if data:
        padded = str(data) + "=" * (-len(str(data)) % 4)
        try:
            return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
        except Exception:
            return ""

    for part in payload.get("parts") or []:
        mime = str(part.get("mimeType") or "")
        if mime == "text/plain":
            text = _gmail_text(part)
            if text:
                return text
    for part in payload.get("parts") or []:
        text = _gmail_text(part)
        if text:
            return text
    return ""


def gmail_pull_unread(
    db: Session,
    workspace_id: int,
    max_results: int = 10,
) -> list[dict]:
    token = _google_token(db, workspace_id)
    headers = {"Authorization": "Bearer " + token}

    listing = httpx.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
        headers=headers,
        params={"q": "is:unread newer_than:2d", "maxResults": max_results},
        timeout=20,
    )
    listing.raise_for_status()

    output: list[dict] = []
    for item in listing.json().get("messages") or []:
        message_id = str(item["id"])
        exists = db.scalar(
            select(ExternalEvent).where(
                ExternalEvent.workspace_id == workspace_id,
                ExternalEvent.provider == "gmail",
                ExternalEvent.idempotency_key == message_id,
            )
        )
        if exists:
            continue

        detail = httpx.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/" + message_id,
            headers=headers,
            params={"format": "full"},
            timeout=20,
        )
        detail.raise_for_status()
        data = detail.json()
        payload = data.get("payload") or {}

        parsed = {
            "id": message_id,
            "thread_id": data.get("threadId"),
            "from": _gmail_header(payload, "From"),
            "reply_to": _gmail_header(payload, "Reply-To"),
            "subject": _gmail_header(payload, "Subject"),
            "body": _gmail_text(payload).strip(),
        }
        output.append(parsed)

        db.add(
            ExternalEvent(
                workspace_id=workspace_id,
                provider="gmail",
                idempotency_key=message_id,
                event_type="inbound_email",
                payload_json=json.dumps(parsed),
                status="received",
            )
        )

    if output:
        db.commit()
    return output


def google_calendar_create(
    db: Session,
    workspace_id: int,
    title: str,
    starts_at: datetime,
    duration_minutes: int,
    attendee_email: str | None = None,
) -> IntegrationResult:
    item = connector(db, workspace_id, "google")
    if item and item.mode == "mock" and item.status == "connected":
        return IntegrationResult(
            ok=True,
            provider="mock_google",
            action="calendar_create",
            external_id="mock-calendar-event",
            detail="Calendar event simulated.",
        )

    token = _google_token(db, workspace_id)
    end_at = starts_at + timedelta(minutes=duration_minutes)
    body = {
        "summary": title,
        "start": {"dateTime": starts_at.isoformat()},
        "end": {"dateTime": end_at.isoformat()},
    }
    if attendee_email:
        body["attendees"] = [{"email": attendee_email}]

    response = httpx.post(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers={"Authorization": "Bearer " + token},
        params={"sendUpdates": "all" if attendee_email else "none"},
        json=body,
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    return IntegrationResult(
        ok=True,
        provider="google",
        action="calendar_create",
        external_id=str(data.get("id") or ""),
        data=data,
    )


def hubspot_upsert_contact(
    db: Session,
    workspace_id: int,
    contact: dict,
) -> IntegrationResult:
    item = connector(db, workspace_id, "hubspot")
    if item and item.mode == "mock" and item.status == "connected":
        return IntegrationResult(
            ok=True,
            provider="mock_hubspot",
            action="contact_upsert",
            external_id="mock-contact",
            detail="HubSpot sync simulated.",
        )

    secret = get_secret(db, workspace_id, "hubspot")
    token = secret.get("private_app_token") or get_settings().hubspot_private_app_token
    if not token:
        raise RuntimeError("HubSpot is not connected.")

    email = str(contact.get("email") or "").strip()
    properties = {
        key: value
        for key, value in {
            "email": email or None,
            "firstname": contact.get("name"),
            "phone": contact.get("phone"),
            "zip": contact.get("zip_code"),
        }.items()
        if value
    }
    headers = {
        "Authorization": "Bearer " + str(token),
        "Content-Type": "application/json",
    }

    contact_id = None
    if email:
        search = httpx.post(
            "https://api.hubapi.com/crm/v3/objects/contacts/search",
            headers=headers,
            json={
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": "email",
                                "operator": "EQ",
                                "value": email,
                            }
                        ]
                    }
                ],
                "properties": ["email", "firstname", "phone", "zip"],
                "limit": 1,
            },
            timeout=20,
        )
        search.raise_for_status()
        results = search.json().get("results") or []
        if results:
            contact_id = str(results[0]["id"])

    if contact_id:
        response = httpx.patch(
            "https://api.hubapi.com/crm/v3/objects/contacts/" + contact_id,
            headers=headers,
            json={"properties": properties},
            timeout=20,
        )
    else:
        response = httpx.post(
            "https://api.hubapi.com/crm/v3/objects/contacts",
            headers=headers,
            json={"properties": properties},
            timeout=20,
        )

    response.raise_for_status()
    data = response.json()
    return IntegrationResult(
        ok=True,
        provider="hubspot",
        action="contact_upsert",
        external_id=str(data.get("id") or contact_id or ""),
        data=data,
    )


def signed_webhook(
    db: Session,
    workspace_id: int,
    event_type: str,
    payload: dict,
) -> IntegrationResult:
    item = connector(db, workspace_id, "webhook")
    if item and item.mode == "mock" and item.status == "connected":
        return IntegrationResult(
            ok=True,
            provider="mock_webhook",
            action=event_type,
            external_id="mock-webhook",
            detail="Webhook simulated.",
        )

    secret = get_secret(db, workspace_id, "webhook")
    url = secret.get("url") or get_settings().outbound_webhook_url
    signing_secret = secret.get("secret") or get_settings().outbound_webhook_secret
    if not url:
        raise RuntimeError("Outbound webhook is not configured.")

    envelope = {
        "event": event_type,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    raw = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(
        str(signing_secret).encode("utf-8"),
        raw,
        hashlib.sha256,
    ).hexdigest()

    response = httpx.post(
        str(url),
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Nexora-Signature": "sha256=" + signature,
        },
        timeout=20,
    )
    response.raise_for_status()
    return IntegrationResult(
        ok=True,
        provider="webhook",
        action=event_type,
        external_id=response.headers.get("X-Request-Id"),
        detail="Webhook delivered.",
    )
