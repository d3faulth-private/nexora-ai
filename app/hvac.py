from __future__ import annotations

DEFAULT_HVAC_SERVICES = [
    "AC repair",
    "AC installation",
    "furnace repair",
    "furnace replacement",
    "heat pump service",
    "preventive maintenance",
    "indoor air quality",
    "thermostat service",
]

HVAC_QUALIFICATION_QUESTIONS = [
    "What type of HVAC service do you need?",
    "What ZIP code is the property in?",
    "Is the system completely down or partially working?",
    "When would you like service?",
    "What is the best phone number for appointment confirmation?",
]

HVAC_EMERGENCY_SIGNALS = (
    "gas smell",
    "carbon monoxide",
    "smoke",
    "burning smell",
    "sparking",
    "no heat",
    "no ac",
    "water leak",
)


def default_hvac_profile() -> dict:
    return {
        "services": DEFAULT_HVAC_SERVICES,
        "service_area": "",
        "business_hours": "Mon-Sat 8:00 AM-7:00 PM",
        "emergency_policy": (
            "Prioritize loss of heating/cooling during extreme conditions and safety-related issues. "
            "Never diagnose gas or electrical hazards remotely; advise appropriate emergency action."
        ),
        "booking_duration_minutes": 60,
        "followup_after_minutes": 120,
        "followup_max_attempts": 3,
    }


def hvac_knowledge_text(profile: dict) -> str:
    services = ", ".join(profile.get("services") or [])
    return (
        "HVAC services: " + services + ". "
        "Service area: " + (profile.get("service_area") or "not configured") + ". "
        "Business hours: " + (profile.get("business_hours") or "not configured") + ". "
        "Emergency policy: " + (profile.get("emergency_policy") or "not configured") + "."
    )
