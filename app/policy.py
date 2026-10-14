from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    requires_approval: bool
    reason: str = ""


SENSITIVE_ACTIONS = {
    "send_bulk_outreach",
    "issue_refund",
    "modify_billing",
    "delete_customer_data",
    "dispatch_technician",
    "change_account_permissions",
}


def evaluate_action(action_type: str, autonomy_level: str = "guarded") -> PolicyDecision:
    if action_type in SENSITIVE_ACTIONS:
        return PolicyDecision(
            allowed=True,
            requires_approval=True,
            reason="Sensitive external or irreversible action requires human approval.",
        )

    if autonomy_level == "manual":
        return PolicyDecision(
            allowed=True,
            requires_approval=True,
            reason="Agent is configured for manual approval.",
        )

    return PolicyDecision(allowed=True, requires_approval=False)
