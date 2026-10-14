"""Smoke test a locally running Nexora demo instance."""

import http.cookiejar
import json
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


BASE = "http://127.0.0.1:8000"
jar = http.cookiejar.CookieJar()
client = build_opener(HTTPCookieProcessor(jar))
csrf = ""


def request(path, method="GET", data=None, content_type="application/json"):
    body = None
    headers = {}
    if data is not None:
        if content_type == "application/json":
            body = json.dumps(data).encode()
        else:
            body = urlencode(data).encode()
        headers["Content-Type"] = content_type
    if method not in {"GET", "HEAD"} and csrf:
        headers["X-Nexora-CSRF"] = csrf

    req = Request(BASE + path, data=body, method=method, headers=headers)
    with client.open(req) as response:
        payload = response.read().decode()
        if "application/json" in (response.headers.get("Content-Type") or ""):
            return json.loads(payload)
        return payload


request(
    "/login",
    "POST",
    {"email": "admin@nexora.local", "password": "nexora-demo"},
    "application/x-www-form-urlencoded",
)
me = request("/api/me")
csrf = me["csrf_token"]

dashboard = request("/api/dashboard")
print("Workspace:", dashboard["workspace"]["name"])
print("Mode:", dashboard["deployment"]["mode"])
print("Metrics:", dashboard["metrics"])

lead_id = dashboard["leads"][0]["id"]
reply = request(
    "/api/leads/" + str(lead_id) + "/message",
    "POST",
    {"body": "My AC stopped cooling and I need someone tomorrow.", "channel": "web"},
)
print("Agent:", reply["agent"])
print("Stage:", reply["stage"])
print("Appointment proposed:", bool(reply["appointment"]))

manager = request(
    "/api/manager/run",
    "POST",
    {"objective": "Follow up with everyone who hasn't booked."},
)
print("Manager:", manager["message"])
