from fastapi.testclient import TestClient

from app.main import app


def login(client: TestClient):
    response = client.post(
        "/login",
        data={"email": "admin@nexora.local", "password": "nexora-demo"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_health_and_auth_boundary():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.json()["app"] == "Nexora AI"

        protected = client.get("/api/dashboard")
        assert protected.status_code == 401


def test_login_and_dashboard():
    with TestClient(app) as client:
        login(client)
        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert data["workspace"]["name"] == "Nexora HVAC Demo"
        assert data["metrics"]["leads"] >= 3
        assert len(data["agents"]) == 6
        assert len(data["connectors"]) == 4


def test_sales_agent_vertical_slice():
    with TestClient(app) as client:
        login(client)
        dashboard = client.get("/api/dashboard").json()
        lead_id = dashboard["leads"][0]["id"]

        response = client.post(
            "/api/leads/" + str(lead_id) + "/message",
            json={"body": "My AC stopped cooling and I need someone tomorrow.", "channel": "web"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["agent"] == "sales"
        assert data["stage"] == "qualified"
        assert data["appointment"] is not None


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


def test_manager_followup():
    with TestClient(app) as client:
        login(client)
        response = client.post(
            "/api/manager/run",
            json={"objective": "Follow up with everyone who hasn't booked."},
        )
        assert response.status_code == 200
        assert response.json()["intent"] == "followup_open"
