# Nexora AI Architecture Decisions

This log records significant product and engineering decisions. New decisions are appended; prior decisions are not silently rewritten.

## 2026-10-17 — Refactor the existing product, do not rewrite

**Decision:** Improve the current v0.5 codebase incrementally. Do not rebuild Nexora from scratch.

**Why:** The existing repository already has working lead, scheduling, integration, revenue, human-takeover, and operator-console behavior. A rewrite would spend the pre-revenue runway recreating behavior instead of reducing launch risk.

**Rejected:** Big-bang rewrite or framework migration.

## 2026-10-17 — First paid pilot is single-tenant operationally

**Decision:** Deploy one Nexora application/database environment for the first paying HVAC customer while retaining existing `workspace_id` scoping in the data model.

**Why:** A dedicated first-customer deployment minimizes authorization and isolation risk without discarding the path to later multi-tenancy.

**Rejected for now:** Shared multi-tenant production from customer #1.

## 2026-10-17 — One HVAC company before concurrent customer rollout

**Decision:** Optimize launch readiness for one first HVAC company, stabilize the pilot, then add the next customer.

**Why:** The solo-developer constraint makes operational learning more valuable than early infrastructure generality.

**Rejected for now:** Concurrent multi-customer launch.

## 2026-10-17 — LLM provider remains optional and swappable

**Decision:** Keep the LLM behind the existing provider interface. Do not hardcode a production vendor until privacy, latency, reliability, and cost are evaluated.

**Why:** Core workflows must remain useful when the LLM is unavailable. Customer data handling also changes materially with provider choice.

**Rejected for now:** Vendor-specific product architecture.

## 2026-10-17 — First pilot communication scope is email + web intake

**Decision:** Launch the first pilot around Gmail/email and web/intake workflows. SMS and voice are out of launch scope.

**Why:** Existing code already supports email workflows. Adding regulated channels before first revenue increases engineering and compliance risk.

**Rejected for now:** SMS, voice, WhatsApp before first paid pilot.

## 2026-10-17 — Proprietary/private product direction

**Decision:** Treat Nexora as proprietary software. Public source visibility is not an intentional open-source strategy.

**Current state:** The GitHub repository is still public. Repository visibility is a separate account/repository setting and is not changed in Phase 1.

**Rejected for now:** Open-source licensing strategy.

## 2026-10-17 — Deployment default is existing VPS/server when available

**Decision:** Prefer Docker Compose + PostgreSQL + Caddy on infrastructure the developer already has, if suitable.

**Why:** It matches the current single-process scheduler model, costs nothing additional when infrastructure already exists, and is operationally understandable.

**Status:** Exact deployment target remains pending confirmation of available infrastructure.

**Rejected for now:** Architecture optimized around hypothetical paid PaaS services.

## 2026-10-17 — Quality controls are introduced incrementally

**Decision:** Add Ruff, gradual strict mypy, pre-commit, and secret detection without mass reformatting or broad module rewrites.

**Why:** The goal is to prevent new debt while preserving working behavior and keeping changes reviewable.

**Rejected:** Repository-wide style rewrite mixed with logic changes.
