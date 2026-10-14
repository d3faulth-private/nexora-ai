from fastapi.testclient import TestClient

from app.main import app


def login(client: TestClient):
    response = client.post(
        "/login",
        data={"email": "admin@nexora.local", "password": "nexora-demo"},
        follow_redirects=False,
    )
    assert response.status_code == 303


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
        assert health.json()["version"] == "0.4.0"

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
