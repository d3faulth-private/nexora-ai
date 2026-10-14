from __future__ import annotations

from email.utils import parseaddr

from sqlalchemy import select
from sqlalchemy.orm import Session

from .connectors.providers import gmail_mark_read, gmail_pull_unread
from .db import SessionLocal
from .models import Connector, ExternalEvent, Lead, Workspace
from .services import process_customer_message


def sync_workspace_gmail(
    db: Session,
    workspace: Workspace,
    max_results: int = 20,
) -> dict:
    messages = gmail_pull_unread(db, workspace.id, max_results=max_results)
    processed_lead_ids: list[int] = []

    for incoming in messages:
        sender_name, sender_email = parseaddr(
            incoming.get("reply_to") or incoming.get("from") or ""
        )
        sender_email = sender_email.strip().lower()

        lead = None
        if sender_email:
            lead = db.scalar(
                select(Lead).where(
                    Lead.workspace_id == workspace.id,
                    Lead.email == sender_email,
                    Lead.stage.notin_(("lost", "completed")),
                )
            )

        if not lead:
            lead = Lead(
                workspace_id=workspace.id,
                name=sender_name or sender_email or "Email Lead",
                email=sender_email or None,
                source="gmail",
                issue=incoming.get("subject") or "",
                estimated_value=0,
            )
            db.add(lead)
            db.flush()

        body = (
            (incoming.get("subject") or "")
            + "\n\n"
            + (incoming.get("body") or "")
        ).strip()

        if body:
            try:
                process_customer_message(
                    db,
                    workspace,
                    lead,
                    body,
                    "email",
                )
            except Exception:
                db.rollback()
                raise
            processed_lead_ids.append(lead.id)

        event = db.scalar(
            select(ExternalEvent).where(
                ExternalEvent.workspace_id == workspace.id,
                ExternalEvent.provider == "gmail",
                ExternalEvent.idempotency_key == str(incoming.get("id") or ""),
            )
        )
        if event:
            event.status = "processed"

        try:
            gmail_mark_read(db, workspace.id, str(incoming.get("id") or ""))
        except Exception:
            # Delivery/processing already succeeded. Leaving Gmail unread should
            # not duplicate the customer workflow because the event is processed.
            pass
        db.commit()

    return {
        "fetched": len(messages),
        "processed_lead_ids": processed_lead_ids,
    }


def sync_connected_gmail_once(max_results: int = 20) -> dict:
    with SessionLocal() as db:
        workspace_ids = list(
            db.scalars(
                select(Connector.workspace_id).where(
                    Connector.slug == "google",
                    Connector.status == "connected",
                )
            )
        )

    synced = 0
    failures = 0
    fetched = 0
    for workspace_id in sorted(set(workspace_ids)):
        with SessionLocal() as db:
            workspace = db.get(Workspace, workspace_id)
            if not workspace:
                continue
            try:
                result = sync_workspace_gmail(db, workspace, max_results=max_results)
                fetched += int(result["fetched"])
                synced += 1
            except Exception:
                db.rollback()
                failures += 1

    return {
        "workspaces": synced,
        "failures": failures,
        "fetched": fetched,
    }
