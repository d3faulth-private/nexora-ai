from fastapi.testclient import TestClient

from app.main import app


def login(client: TestClient):
    response = client.post(
        "/login",
        data={"email": "admin@nexora.local", "password": "nexora-demo"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    me = client.get("/api/me")
    assert me.status_code == 200
    client.headers.update({"X-Nexora-CSRF": me.json()["csrf_token"]})


def create_lead(client: TestClient, name: str):
    response = client.post(
        "/api/leads",
        json={
            "name": name,
            "email": name.lower().replace(" ", ".") + "@example.com",
            "phone": "555-0199",
            "zip_code": "10011",
            "source": "test",
            "issue": "",
            "estimated_value": 1200,
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_health_and_auth_boundary():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.json()["app"] == "Nexora AI"
        assert health.json()["version"] == "0.5.0"
        assert health.json()["mode"] == "demo"
        assert health.json()["database"] == "ok"

        protected = client.get("/api/dashboard")
        assert protected.status_code == 401


def test_login_dashboard_and_commercial_profile():
    with TestClient(app) as client:
        login(client)
        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert data["workspace"]["industry"] == "HVAC"
        assert data["metrics"]["leads"] >= 3
        assert len(data["agents"]) == 6
        slugs = {item["slug"] for item in data["connectors"]}
        assert {"google", "hubspot", "webhook"}.issubset(slugs)
        assert "pending_automations" in data["metrics"]
        assert "onboarding_completed" in data["profile"]


def test_hvac_onboarding():
    with TestClient(app) as client:
        login(client)
        response = client.post(
            "/api/onboarding",
            json={
                "business_name": "Nexora HVAC Demo",
                "industry": "HVAC",
                "timezone": "America/New_York",
                "phone": "555-0100",
                "email": "office@example.com",
                "website": "https://example.com",
                "services": ["AC repair", "Furnace repair", "Heat pumps"],
                "service_area": "10001-10020",
                "business_hours": "Mon-Sat 8am-7pm",
                "emergency_policy": "Escalate safety issues; do not diagnose gas hazards remotely.",
                "knowledge_summary": "Never quote a final repair price before technician assessment. Financing is available on replacements.",
                "booking_duration_minutes": 90,
                "followup_after_minutes": 60,
                "followup_max_attempts": 2,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["profile"]["onboarding_completed"] is True
        assert data["profile"]["booking_duration_minutes"] == 90
        assert "AC repair" in data["profile"]["services"]
        saved = client.get("/api/onboarding").json()
        assert "final repair price" in saved["workspace"]["knowledge_summary"]


def test_sales_agent_schedules_followup():
    with TestClient(app) as client:
        login(client)
        lead_id = create_lead(client, "Casey Automation")
        response = client.post(
            "/api/leads/" + str(lead_id) + "/message",
            json={
                "body": "My AC stopped cooling and I need someone tomorrow.",
                "channel": "web",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["agent"] == "sales"
        assert data["stage"] == "qualified"
        assert data["appointment"] is not None

        dashboard = client.get("/api/dashboard").json()
        assert dashboard["metrics"]["pending_automations"] >= 1


def test_human_takeover_pauses_agent_and_allows_human_reply():
    with TestClient(app) as client:
        login(client)
        lead_id = create_lead(client, "Taylor Handoff")

        takeover = client.post("/api/leads/" + str(lead_id) + "/takeover")
        assert takeover.status_code == 200
        assert takeover.json()["mode"] == "human"

        held = client.post(
            "/api/leads/" + str(lead_id) + "/message",
            json={"body": "Can someone call me?", "channel": "web"},
        )
        assert held.status_code == 200
        assert held.json()["agent"] == "human"
        assert held.json()["actions"] == ["held_for_human"]

        human = client.post(
            "/api/leads/" + str(lead_id) + "/human-message",
            json={"body": "Yes. I am taking over this conversation."},
        )
        assert human.status_code == 200

        returned = client.post("/api/leads/" + str(lead_id) + "/return-to-ai")
        assert returned.status_code == 200
        assert returned.json()["mode"] == "ai"


def test_human_approval_policy():
    with TestClient(app) as client:
        login(client)
        requested = client.post(
            "/api/actions/request",
            json={
                "agent_slug": "operations",
                "action_type": "dispatch_technician",
                "reason": "test",
                "payload": {"lead_id": 1},
            },
        )
        assert requested.status_code == 200
        data = requested.json()
        assert data["status"] == "pending_approval"

        approval_id = data["approval_id"]
        resolved = client.post(
            "/api/approvals/" + str(approval_id) + "/resolve",
            json={"decision": "approved"},
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "approved"


def test_mock_google_connector_can_be_explicitly_enabled():
    with TestClient(app) as client:
        login(client)
        result = client.post("/api/connectors/google/mock")
        assert result.status_code == 200
        assert result.json()["mode"] == "mock"
        assert result.json()["status"] == "connected"


def test_manager_followup():
    with TestClient(app) as client:
        login(client)
        response = client.post(
            "/api/manager/run",
            json={"objective": "Follow up with everyone who hasn't booked."},
        )
        assert response.status_code == 200
        assert response.json()["intent"] == "followup_open"



def test_revenue_attribution_and_completion():
    with TestClient(app) as client:
        login(client)
        lead_id = create_lead(client, "Revenue Proof")

        qualified = client.post(
            "/api/leads/" + str(lead_id) + "/message",
            json={
                "body": "My AC failed and I want to book service tomorrow.",
                "channel": "web",
            },
        )
        assert qualified.status_code == 200
        assert qualified.json()["appointment"] is not None

        booked = client.post("/api/leads/" + str(lead_id) + "/book")
        assert booked.status_code == 200

        revenue = client.get("/api/revenue/summary")
        assert revenue.status_code == 200
        assert revenue.json()["booked_pipeline"] >= 1200

        completed = client.post(
            "/api/leads/" + str(lead_id) + "/complete-job",
            json={"actual_amount": 1500},
        )
        assert completed.status_code == 200
        assert completed.json()["revenue"] == 1500

        revenue = client.get("/api/revenue/summary").json()
        assert revenue["completed_revenue"] >= 1500


def test_opportunity_engine_and_terminal_shortcuts():
    with TestClient(app) as client:
        login(client)
        create_lead(client, "Opportunity Proof")
        response = client.get("/api/opportunities")
        assert response.status_code == 200
        assert response.json()["count"] >= 1
        assert response.json()["estimated_value"] >= 1200

    from d3terminal.shell import OperatorShell

    shell = OperatorShell()
    assert shell._normalize("what needs my attention") == "opportunities"
    assert shell._normalize("what's wrong") == "doctor"



def test_html_routes_render_and_static_assets():
    with TestClient(app) as client:
        login_page = client.get("/login")
        assert login_page.status_code == 200
        assert "Nexora AI" in login_page.text

        login(client)
        dashboard_page = client.get("/")
        assert dashboard_page.status_code == 200
        assert "NEXORA AI" in dashboard_page.text
        assert "WHAT NEEDS ATTENTION" in dashboard_page.text

        javascript = client.get("/static/app.js")
        stylesheet = client.get("/static/styles.css")
        assert javascript.status_code == 200
        assert stylesheet.status_code == 200


def test_pytest_database_is_isolated():
    from app.db import engine

    database_path = str(engine.url.database or "")
    assert "nexora-pytest-" in database_path
    assert not database_path.endswith("/nexora.db")
    assert not database_path.endswith("\\nexora.db")


def test_connector_health_distinguishes_optional_configuration():
    from d3terminal import diagnostics

    data = diagnostics.snapshot()
    states = {item["slug"]: item["health"] for item in data["connectors"]}
    assert states["hubspot"] == "NOT CONFIGURED"
    assert states["webhook"] == "NOT CONFIGURED"
    assert data["overall_health"] == "HEALTHY"


def test_terminal_handles_multiline_command_input():
    from d3terminal.shell import OperatorShell

    shell = OperatorShell()
    raw = "what's wrong\nwhat needs my attention\nshow revenue"
    commands = [line.strip() for line in raw.splitlines() if line.strip()]
    assert [shell._normalize(item) for item in commands] == [
        "doctor",
        "opportunities",
        "revenue",
    ]



def test_native_prompt_theme_has_no_raw_ansi(monkeypatch):
    from d3terminal.theme import prompt_tokens

    monkeypatch.delenv("NO_COLOR", raising=False)
    dev = prompt_tokens("development")
    rendered = "".join(fragment for _, fragment in dev)
    assert rendered == "d3faulth@nexora [DEVE]:~$ "
    assert "\x1b[" not in rendered

    prod = prompt_tokens("production")
    assert any(style == "class:d3.env.prod" and fragment == "PROD" for style, fragment in prod)


def test_no_color_prompt_fallback(monkeypatch):
    from d3terminal.theme import prompt_tokens

    monkeypatch.setenv("NO_COLOR", "1")
    prompt_value = prompt_tokens("test")
    assert list(prompt_value) == [("", "d3faulth@nexora [TEST]:~$ ")]


def test_server_log_redaction(tmp_path):
    from d3terminal.runtime import ServerRuntime

    runtime = ServerRuntime()
    runtime.log_path = tmp_path / "server.log"
    runtime.log_path.write_text(
        "Authorization: Bearer super-secret-token\n"
        "password=hunter2\n"
        "normal log line\n",
        encoding="utf-8",
    )
    output = runtime.logs_tail(10)
    assert "super-secret-token" not in output
    assert "hunter2" not in output
    assert "[REDACTED]" in output
    assert "normal log line" in output


def test_server_runtime_health_start_with_fake_process(monkeypatch):
    from d3terminal.runtime import ServerRuntime

    class FakeProcess:
        pid = 4242
        returncode = None

        def poll(self):
            return None

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.returncode = -9

    runtime = ServerRuntime()
    monkeypatch.setattr("d3terminal.runtime.subprocess.Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(runtime, "_health_ok", lambda: True)

    assert runtime.start(port=8123, health_timeout=0.5) is True
    assert runtime.health() == "HEALTHY"
    assert runtime.pid == 4242
    assert runtime.stop() is True



def test_csrf_protects_authenticated_writes():
    with TestClient(app) as client:
        response = client.post(
            "/login",
            data={"email": "admin@nexora.local", "password": "nexora-demo"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        blocked = client.post(
            "/api/leads",
            json={"name": "CSRF Proof", "estimated_value": 100},
        )
        assert blocked.status_code == 403


def test_takeover_cancels_followup_and_return_can_resume():
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import AutomationJob

    with TestClient(app) as client:
        login(client)
        lead_id = create_lead(client, "Pause Followup")
        sent = client.post(
            "/api/leads/" + str(lead_id) + "/message",
            json={"body": "My AC stopped and I need someone tomorrow.", "channel": "web"},
        )
        assert sent.status_code == 200

        takeover = client.post("/api/leads/" + str(lead_id) + "/takeover")
        assert takeover.status_code == 200
        with SessionLocal() as db:
            pending = list(
                db.scalars(
                    select(AutomationJob).where(
                        AutomationJob.lead_id == lead_id,
                        AutomationJob.status == "pending",
                    )
                )
            )
            assert pending == []

        returned = client.post("/api/leads/" + str(lead_id) + "/return-to-ai")
        assert returned.status_code == 200
        with SessionLocal() as db:
            pending = list(
                db.scalars(
                    select(AutomationJob).where(
                        AutomationJob.lead_id == lead_id,
                        AutomationJob.status == "pending",
                    )
                )
            )
            assert len(pending) == 1


def test_mock_google_availability_and_disconnect():
    with TestClient(app) as client:
        login(client)
        enabled = client.post("/api/connectors/google/mock")
        assert enabled.status_code == 200

        availability = client.get("/api/availability")
        assert availability.status_code == 200
        data = availability.json()
        assert data["calendar_connected"] is True
        assert len(data["slots"]) == 3

        disconnected = client.post("/api/connectors/google/disconnect")
        assert disconnected.status_code == 200
        assert disconnected.json()["status"] == "disconnected"


def test_customer_history_matches_returning_customer():
    with TestClient(app) as client:
        login(client)
        first = client.post(
            "/api/leads",
            json={
                "name": "Returning Customer",
                "email": "returning@example.com",
                "issue": "Previous furnace visit",
                "estimated_value": 300,
            },
        )
        assert first.status_code == 200
        first_id = first.json()["id"]
        conversation = client.post(
            "/api/leads/" + str(first_id) + "/message",
            json={"body": "My furnace stopped and I need someone tomorrow.", "channel": "web"},
        )
        assert conversation.status_code == 200

        second = client.post(
            "/api/leads",
            json={
                "name": "Returning Customer",
                "email": "returning@example.com",
                "issue": "New AC request",
                "estimated_value": 900,
            },
        )
        assert second.status_code == 200
        history = client.get("/api/customers/" + str(second.json()["id"]) + "/history")
        assert history.status_code == 200
        payload = history.json()
        assert len(payload["previous_requests"]) >= 1
        assert any(item["lead_id"] == first_id for item in payload["conversations"])
        assert "appointments" in payload


def test_pilot_ui_has_no_inline_event_handlers_or_browser_prompts():
    from pathlib import Path

    html = Path("app/templates/index.html").read_text(encoding="utf-8")
    js = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "onclick=" not in html
    assert "onchange=" not in html
    assert "alert(" not in js
    assert "window.prompt(" not in js
    assert 'meta name="csrf-token"' in html


def test_live_seed_creates_clean_workspace(monkeypatch):
    from types import SimpleNamespace

    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    from app.db import Base
    from app.models import Lead, Connector
    import app.seed as seed_module

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    fake = SimpleNamespace(
        demo_mode=False,
        bootstrap_business_name="Pilot HVAC",
        bootstrap_admin_email="owner@pilot.test",
        bootstrap_admin_password="strong-password-123",
        default_timezone="America/New_York",
    )
    monkeypatch.setattr(seed_module, "get_settings", lambda: fake)

    with Session(engine) as db:
        workspace = seed_module.seed_workspace(db)
        assert workspace.name == "Pilot HVAC"
        assert int(db.scalar(select(func.count(Lead.id))) or 0) == 0
        modes = set(db.scalars(select(Connector.mode)))
        assert modes == {"real"}



def test_security_headers_and_login_throttle():
    with TestClient(app) as client:
        page = client.get("/login")
        assert page.headers["x-content-type-options"] == "nosniff"
        assert page.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in page.headers["content-security-policy"]

        for _ in range(5):
            failed = client.post(
                "/login",
                data={"email": "limit-test@example.com", "password": "wrong"},
                follow_redirects=False,
            )
            assert failed.status_code == 401
        blocked = client.post(
            "/login",
            data={"email": "limit-test@example.com", "password": "wrong"},
            follow_redirects=False,
        )
        assert blocked.status_code == 429


def test_workspace_object_isolation():
    from app.db import SessionLocal
    from app.models import Lead, Workspace

    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            other = Workspace(name="Other Tenant HVAC", industry="HVAC")
            db.add(other)
            db.flush()
            hidden = Lead(
                workspace_id=other.id,
                name="Other Tenant Lead",
                email="hidden@example.com",
                issue="Private tenant data",
                estimated_value=9999,
            )
            db.add(hidden)
            db.commit()
            hidden_id = hidden.id

        response = client.get("/api/leads/" + str(hidden_id))
        assert response.status_code == 404


def test_production_runtime_rejects_unsafe_defaults():
    import pytest

    from app.config import Settings

    unsafe = Settings(
        app_env="production",
        demo_mode=False,
        app_secret="change-this-before-production",
        connector_encryption_key="test-key",
        bootstrap_admin_email="owner@example.com",
        bootstrap_admin_password="strong-password-123",
    )
    with pytest.raises(RuntimeError):
        unsafe.validate_runtime()



def test_mark_lost_stops_pending_followup():
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import AutomationJob

    with TestClient(app) as client:
        login(client)
        lead_id = create_lead(client, "Lost Followup")
        sent = client.post(
            "/api/leads/" + str(lead_id) + "/message",
            json={"body": "My AC stopped and I need someone tomorrow.", "channel": "web"},
        )
        assert sent.status_code == 200

        lost = client.patch("/api/leads/" + str(lead_id), json={"stage": "lost"})
        assert lost.status_code == 200

        with SessionLocal() as db:
            pending = list(
                db.scalars(
                    select(AutomationJob).where(
                        AutomationJob.lead_id == lead_id,
                        AutomationJob.status == "pending",
                    )
                )
            )
            assert pending == []


def test_business_hours_parser():
    from app.connectors.providers import _business_hours_rule

    days, start, end = _business_hours_rule("Mon-Sat 8am-7pm")
    assert days == {0, 1, 2, 3, 4, 5}
    assert start == 8 * 60
    assert end == 19 * 60

    days, start, end = _business_hours_rule("Mon-Fri 9:30am-5:30pm")
    assert days == {0, 1, 2, 3, 4}
    assert start == 9 * 60 + 30
    assert end == 17 * 60 + 30


def test_gmail_send_preserves_thread_headers(monkeypatch):
    import base64
    from email import message_from_bytes
    from types import SimpleNamespace

    import app.connectors.providers as providers

    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "sent-message"}

    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        captured["json"] = json
        return Response()

    monkeypatch.setattr(providers, "connector", lambda *args, **kwargs: None)
    monkeypatch.setattr(providers, "_google_token", lambda *args, **kwargs: "token")
    monkeypatch.setattr(providers.httpx, "post", fake_post)

    result = providers.gmail_send(
        SimpleNamespace(),
        1,
        "customer@example.com",
        "Re: Service request",
        "Reply body",
        thread_id="thread-123",
        in_reply_to="<message-123@example.com>",
    )
    assert result.ok is True
    assert captured["json"]["threadId"] == "thread-123"

    raw = captured["json"]["raw"]
    raw += "=" * (-len(raw) % 4)
    message = message_from_bytes(base64.urlsafe_b64decode(raw))
    assert message["In-Reply-To"] == "<message-123@example.com>"
    assert message["References"] == "<message-123@example.com>"



def test_connected_gmail_poller_handles_mock_workspace():
    from app.inbox import sync_connected_gmail_once

    with TestClient(app) as client:
        login(client)
        enabled = client.post("/api/connectors/google/mock")
        assert enabled.status_code == 200

        result = sync_connected_gmail_once(max_results=5)
        assert result["failures"] == 0
        assert result["workspaces"] >= 1
        assert result["fetched"] == 0


def test_followup_does_not_claim_delivery_without_google():
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.automation import run_due_jobs_once
    from app.db import SessionLocal
    from app.models import AutomationJob, Message

    with TestClient(app) as client:
        login(client)
        client.post("/api/connectors/google/disconnect")

        lead_id = create_lead(client, "No Delivery Channel")
        response = client.post(
            "/api/leads/" + str(lead_id) + "/message",
            json={"body": "My AC stopped and I need help tomorrow.", "channel": "web"},
        )
        assert response.status_code == 200
        conversation_id = response.json()["conversation_id"]

        with SessionLocal() as db:
            job = db.scalar(
                select(AutomationJob).where(
                    AutomationJob.lead_id == lead_id,
                    AutomationJob.status == "pending",
                )
            )
            assert job is not None
            job.run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()

        run_due_jobs_once()

        with SessionLocal() as db:
            followup_messages = list(
                db.scalars(
                    select(Message).where(
                        Message.conversation_id == conversation_id,
                        Message.actor == "followup",
                    )
                )
            )
            assert followup_messages == []
            job = db.scalar(
                select(AutomationJob).where(AutomationJob.lead_id == lead_id)
                .order_by(AutomationJob.id.desc())
            )
            assert job.status == "completed"
            assert "Google email delivery is not connected" in (job.last_error or "")



def test_live_mode_refuses_demo_seeded_database(monkeypatch):
    import pytest
    from types import SimpleNamespace

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db import Base
    from app.models import User, Workspace
    from app.security import hash_password
    import app.seed as seed_module

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        workspace = Workspace(name="Nexora HVAC Demo", industry="HVAC")
        db.add(workspace)
        db.flush()
        db.add(
            User(
                workspace_id=workspace.id,
                email="admin@nexora.local",
                name="Demo Admin",
                password_hash=hash_password("demo-password"),
                role="owner",
            )
        )
        db.commit()

        fake = SimpleNamespace(
            demo_mode=False,
            demo_email="admin@nexora.local",
            bootstrap_business_name="Customer HVAC",
            bootstrap_admin_email="owner@customer.test",
            bootstrap_admin_password="strong-password-123",
            default_timezone="America/New_York",
        )
        monkeypatch.setattr(seed_module, "get_settings", lambda: fake)

        with pytest.raises(RuntimeError, match="cannot reuse a demo-seeded database"):
            seed_module.seed_workspace(db)



def test_onboarding_modal_is_viewport_safe_and_demo_ui_is_customer_facing():
    from pathlib import Path

    html = Path("app/templates/index.html").read_text(encoding="utf-8")
    login = Path("app/templates/login.html").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    js = Path("app/static/app.js").read_text(encoding="utf-8")

    assert 'class="onboarding-dialog"' in html
    assert 'class="onboarding-header"' in html
    assert 'class="onboarding-body"' in html
    assert 'class="wizard-actions onboarding-footer"' in html
    assert "Business details" in html
    assert "Services & coverage" in html
    assert "Operating rules" in html
    assert "Scheduling & follow-up" in html
    assert "Review & activate" in html

    assert "Demo Mode" in html
    assert "TRY NEXORA" in html
    assert "Activate Nexora" in html
    assert "Guided demo" in html
    assert "Demo Mode" in login
    assert "SANDBOX" not in html
    assert "SANDBOX" not in login
    assert "app_env|upper" not in html
    assert "DEVELOPMENT" not in html

    assert "max-height:calc(100vh - 28px)" in css
    assert "overflow-y:auto" in css
    assert "grid-template-rows:auto auto minmax(0,1fr) auto" in css
    assert 'el("#wizardStepLabel").textContent' in js
    assert "validateWizardStep()" in js
    assert "DEMO_STEPS" in js
    assert "Safe simulation · no external account connected" in js



def test_demo_seed_is_realistic_ready_and_simulated(monkeypatch):
    from types import SimpleNamespace

    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    from app.db import Base
    from app.models import Connector, Lead, WorkspaceProfile
    import app.seed as seed_module

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    fake = SimpleNamespace(
        demo_mode=True,
        demo_email="admin@nexora.local",
        demo_password="nexora-demo",
        default_timezone="America/New_York",
    )
    monkeypatch.setattr(seed_module, "get_settings", lambda: fake)

    with Session(engine) as db:
        workspace = seed_module.seed_workspace(db)
        assert workspace.name == "Northstar Heating & Air"
        assert workspace.email == "service@northstar.example"
        assert workspace.website == "https://northstar.example"

        profile = db.scalar(
            select(WorkspaceProfile).where(WorkspaceProfile.workspace_id == workspace.id)
        )
        assert profile is not None
        assert profile.onboarding_completed is True

        assert int(db.scalar(select(func.count(Lead.id))) or 0) == 3
        assert set(db.scalars(select(Connector.mode))) == {"mock"}


def test_demo_mode_blocks_real_connector_credentials():
    with TestClient(app) as client:
        login(client)

        google = client.get("/api/connectors/google/start")
        assert google.status_code == 403
        assert "Demo Mode" in google.json()["detail"]

        hubspot = client.post(
            "/api/connectors/hubspot/connect",
            json={"private_app_token": "demo-token-12345"},
        )
        assert hubspot.status_code == 403
        assert "Demo Mode" in hubspot.json()["detail"]

        webhook = client.post(
            "/api/connectors/webhook/connect",
            json={
                "url": "https://example.com/hook",
                "secret": "demo-secret-123456",
            },
        )
        assert webhook.status_code == 403
        assert "Demo Mode" in webhook.json()["detail"]

        patch = client.patch(
            "/api/connectors/google",
            json={"mode": "real", "status": "connected"},
        )
        assert patch.status_code == 403
        assert "simulated" in patch.json()["detail"].lower()



def test_final_modal_system_is_viewport_safe():
    from pathlib import Path

    html = Path("app/templates/index.html").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    js = Path("app/static/app.js").read_text(encoding="utf-8")

    assert 'id="leadDialog" class="lead-dialog"' in html
    assert 'class="lead-dialog-header"' in html
    assert 'class="lead-dialog-body"' in html
    assert 'class="conversation-panel"' in html

    assert ".hidden{display:none!important}" in css
    assert 'body[data-mode="demo"] .setup-banner{display:none!important}' in css
    assert "dialog:not(#onboardingDialog)" in css
    assert "max-height:calc(100dvh - 24px)" in css
    assert "#leadDialog" in css
    assert "width:min(1120px,calc(100vw - 24px))" in css
    assert "grid-template-rows:auto minmax(0,1fr)" in css
    assert "height:clamp(180px,32vh,320px)" in css

    assert 'const wasOpen = leadDialog.open;' in js
    assert 'leadDialog.querySelector(".lead-dialog-body")' in js


def test_managed_server_startup_is_patient_and_deterministic():
    import inspect

    from d3terminal.runtime import ServerRuntime

    signature = inspect.signature(ServerRuntime.start)
    assert signature.parameters["health_timeout"].default == 15.0

    source = inspect.getsource(ServerRuntime.start)
    assert 'Path(__file__).resolve().parents[1]' in source
    assert 'child_env["PYTHONUNBUFFERED"] = "1"' in source
    assert "cwd=str(project_root)" in source


def test_pasted_command_failures_stop_the_chain():
    from pathlib import Path

    shell_source = Path("d3terminal/shell.py").read_text(encoding="utf-8")
    assert "Remaining pasted commands were not executed because the previous command failed." in shell_source
    assert "if len(commands) > 1:" in shell_source
