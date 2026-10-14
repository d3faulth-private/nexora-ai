let state = null;
let activeLead = null;
let activeLeadData = null;
let wizardStep = 0;

const el = (selector) => document.querySelector(selector);
const els = (selector) => Array.from(document.querySelectorAll(selector));
const csrf = () => el('meta[name="csrf-token"]').content;
const isDemo = document.body.dataset.mode === "demo";

const esc = (value) => String(value == null ? "" : value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const money = (value) => new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0
}).format(value || 0);

const timeText = (value) => value ? new Date(value).toLocaleString() : "—";

function toast(message, type) {
  const item = document.createElement("div");
  item.className = "toast " + (type || "ok");
  item.textContent = message;
  el("#toastRegion").appendChild(item);
  setTimeout(() => item.remove(), 4200);
}

async function api(url, options) {
  const config = Object.assign({}, options || {});
  config.headers = Object.assign(
    {"Content-Type": "application/json"},
    config.headers || {}
  );
  if (config.method && !["GET", "HEAD"].includes(config.method.toUpperCase())) {
    config.headers["X-Nexora-CSRF"] = csrf();
  }

  const response = await fetch(url, config);
  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("Authentication required");
  }

  if (!response.ok) {
    let detail = "Nexora could not complete this request.";
    try {
      const payload = await response.json();
      detail = payload.detail || payload.message || detail;
    } catch (_) {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }

  const type = response.headers.get("content-type") || "";
  return type.includes("application/json") ? response.json() : response.text();
}

async function run(task, successMessage) {
  try {
    const result = await task();
    if (successMessage) toast(successMessage, "ok");
    return result;
  } catch (error) {
    toast(error.message || "Nexora could not complete this action.", "error");
    throw error;
  }
}

function metric(label, value, note) {
  return '<div class="metric"><span>' + esc(label) + '</span><strong>' + esc(value) +
    '</strong>' + (note ? '<small>' + esc(note) + '</small>' : '') + '</div>';
}

function renderMetrics() {
  const m = state.metrics;
  el("#metrics").innerHTML =
    metric("Leads", m.leads) +
    metric("Booked pipeline", money(m.booked_pipeline), "Estimated booked value") +
    metric("Completed revenue", money(m.completed_revenue), "Confirmed") +
    metric("Recovered revenue", money(m.recovered_revenue), "Attributed to follow-up") +
    metric("Open opportunity", money(m.open_opportunity), "Potential") +
    metric("Approvals", m.pending_approvals);
}

function renderOpportunities() {
  const items = state.opportunities || [];
  el("#opportunityList").innerHTML = items.length ? items.map((item) =>
    '<div class="opportunity-item">' +
      '<div><strong>#' + item.lead_id + ' ' + esc(item.name) + '</strong><br>' +
      '<span class="muted">' + esc(item.stage.toUpperCase()) + ' · idle ' + item.hours_idle + 'h</span></div>' +
      '<div class="opportunity-value">' + money(item.estimated_value) + '</div>' +
      '<div>' + esc(item.recommended_action) + '</div>' +
      '<button class="view" data-action="open-lead" data-lead="' + item.lead_id + '">Work lead</button>' +
    '</div>'
  ).join("") : emptyState("CLEAR", "No open revenue opportunities.");
}

function renderProfile() {
  const p = state.profile || {};
  const services = (p.services || []).slice(0, 6).join(", ");
  el("#profileCard").innerHTML =
    '<div><span class="profile-label">Status</span><strong>' +
      (p.onboarding_completed ? "Configured" : "Needs setup") + '</strong></div>' +
    '<div><span class="profile-label">Services</span><strong>' +
      esc(services || "Not configured") + '</strong></div>' +
    '<div><span class="profile-label">Service area</span><strong>' +
      esc(p.service_area || "Not configured") + '</strong></div>' +
    '<div><span class="profile-label">Follow-up</span><strong>' +
      (p.followup_after_minutes || 120) + ' min · ' +
      (p.followup_max_attempts || 3) + ' attempts</strong></div>';

  el("#setupBanner").classList.toggle("hidden", !!p.onboarding_completed);
}

function renderAgents() {
  el("#agentGrid").innerHTML = state.agents.map((agent) => {
    const initial = agent.name.replace("Nexora ", "").slice(0, 1);
    const options = ["manual", "guarded", "autonomous"].map((level) =>
      '<option value="' + level + '"' +
      (agent.autonomy_level === level ? ' selected' : '') + '>' + level + '</option>'
    ).join("");

    return '<div class="agent-card">' +
      '<div class="agent-top"><div class="agent-icon">' + esc(initial) + '</div>' +
      '<div class="agent-meta"><strong>' + esc(agent.name) + '</strong><p>' + esc(agent.role) + '</p></div></div>' +
      '<div class="agent-controls">' +
      '<button class="toggle ' + (agent.enabled ? 'on' : '') + '" data-action="toggle-agent" data-agent="' +
      esc(agent.slug) + '">' + (agent.enabled ? 'ON' : 'OFF') + '</button>' +
      '<select data-action="autonomy" data-agent="' + esc(agent.slug) + '">' + options + '</select>' +
      '</div></div>';
  }).join("");
}

function renderLeads() {
  const rows = state.leads || [];
  el("#leadRows").innerHTML = rows.length ? rows.map((lead) =>
    '<tr>' +
      '<td><strong>' + esc(lead.name) + '</strong><br><small>' + esc(lead.source) + '</small></td>' +
      '<td>' + esc(lead.issue || "—") + '</td>' +
      '<td><span class="stage">' + esc(lead.stage.toUpperCase()) + '</span></td>' +
      '<td><span class="control ' + (lead.human_control ? "human" : "ai") + '">' +
        (lead.human_control ? "HUMAN" : "NEXORA") + '</span></td>' +
      '<td class="' + (lead.urgency === "urgent" ? "urgent" : "") + '">' + esc(lead.urgency) + '</td>' +
      '<td>' + money(lead.estimated_value) + '</td>' +
      '<td><button class="view" data-action="open-lead" data-lead="' + lead.id + '">Open</button></td>' +
    '</tr>'
  ).join("") : '<tr><td colspan="7" class="empty-cell">No leads yet.</td></tr>';
}

function renderConversations() {
  const items = state.conversations || [];
  el("#conversationList").innerHTML = items.length ? items.map((item) =>
    '<div class="conversation-row">' +
      '<div><strong>' + esc(item.name) + '</strong><br><span class="muted">' +
      esc(item.stage.toUpperCase()) + '</span></div>' +
      '<div><span class="control ' + (item.human_control ? "human" : "ai") + '">' +
      (item.human_control ? "HUMAN" : "NEXORA") + '</span></div>' +
      '<div class="muted">' + timeText(item.last_contacted_at) + '</div>' +
      '<button class="view" data-action="open-lead" data-lead="' + item.lead_id + '">Open</button>' +
    '</div>'
  ).join("") : emptyState("CLEAR", "No conversations yet.");
}

function renderAppointments() {
  const items = state.appointments || [];
  el("#appointmentList").innerHTML = items.length ? items.map((item) =>
    '<div class="appointment-row">' +
      '<div><strong>' + esc(item.lead_name) + '</strong><br><span class="muted">#' + item.lead_id + '</span></div>' +
      '<div>' + timeText(item.starts_at) + '</div>' +
      '<div><span class="stage">' + esc(item.status.toUpperCase()) + '</span></div>' +
      '<button class="view" data-action="open-lead" data-lead="' + item.lead_id + '">Open lead</button>' +
    '</div>'
  ).join("") : emptyState("CLEAR", "No appointments yet.");
}

function renderApprovals() {
  el("#approvalList").innerHTML = state.approvals.length ? state.approvals.map((item) =>
    '<div class="approval-item">' +
      '<div class="approval-agent">' + esc(item.agent_slug) + '</div>' +
      '<div><strong>' + esc(item.action_type) + '</strong><br><span class="muted">' + esc(item.reason) + '</span></div>' +
      '<div class="approval-actions">' +
        '<button class="approve" data-action="approval" data-id="' + item.id + '" data-decision="approved">Approve</button>' +
        '<button class="reject" data-action="approval" data-id="' + item.id + '" data-decision="rejected">Reject</button>' +
      '</div></div>'
  ).join("") : emptyState("CLEAR", "No pending approvals.");
}

function connectorLabel(item) {
  if (item.status === "connected") return "CONNECTED";
  if (item.status === "degraded") return "DEGRADED";
  return item.mode === "mock" && isDemo ? "NOT ENABLED" : "NOT CONFIGURED";
}

function connectorActions(item) {
  const actions = [];
  if (item.slug === "google") {
    actions.push('<button class="view" data-action="connect-google">' +
      (item.status === "connected" ? "Reconnect" : "Connect Google") + '</button>');
    if (item.status === "connected") {
      actions.push('<button class="view" data-action="sync-gmail">Sync Gmail</button>');
    }
  } else if (item.slug === "hubspot") {
    actions.push('<button class="view" data-action="connector-dialog" data-dialog="hubspotDialog">' +
      (item.status === "connected" ? "Reconnect" : "Connect HubSpot") + '</button>');
  } else if (item.slug === "webhook") {
    actions.push('<button class="view" data-action="connector-dialog" data-dialog="webhookDialog">' +
      (item.status === "connected" ? "Reconnect" : "Connect webhook") + '</button>');
  }

  if (item.status === "connected" || item.status === "degraded") {
    actions.push('<button class="view" data-action="test-connector" data-slug="' + esc(item.slug) + '">Test</button>');
    actions.push('<button class="view danger-lite" data-action="disconnect-connector" data-slug="' +
      esc(item.slug) + '">Disconnect</button>');
  } else if (isDemo) {
    actions.push('<button class="view" data-action="mock-connector" data-slug="' + esc(item.slug) + '">Enable mock</button>');
  }
  return actions.join("");
}

function renderConnectors() {
  el("#connectorGrid").innerHTML = (state.connectors || []).map((item) =>
    '<div class="connector-card">' +
      '<div class="connector-heading"><strong>' + esc(item.name) + '</strong>' +
      '<span class="connector-badge ' + esc(item.status) + '">' + connectorLabel(item) + '</span></div>' +
      '<span>' + esc(item.mode.toUpperCase()) + ' mode</span>' +
      '<span class="connector-last">Last check: ' + timeText(item.last_sync_at) + '</span>' +
      '<div class="connector-actions">' + connectorActions(item) + '</div>' +
    '</div>'
  ).join("");
}

function renderActivity() {
  el("#activityList").innerHTML = state.activities.length ? state.activities.map((item) =>
    '<div class="activity-item">' +
      '<div class="activity-agent">' + esc(item.agent_slug) + '</div>' +
      '<div>' + esc(item.summary) + '</div>' +
      '<div class="activity-time">' + timeText(item.created_at) + '</div>' +
    '</div>'
  ).join("") : emptyState("", "No activity yet.");
}

function emptyState(label, message) {
  return '<div class="empty-state"><span>' + esc(label) + '</span><div>' + esc(message) + '</div></div>';
}

function render() {
  el("#workspaceName").textContent = state.workspace.name;
  el("#workspaceMeta").textContent = state.workspace.industry + " · " + state.workspace.timezone;
  renderMetrics();
  renderOpportunities();
  renderProfile();
  renderAgents();
  renderLeads();
  renderConversations();
  renderAppointments();
  renderApprovals();
  renderConnectors();
  renderActivity();
}

async function refresh() {
  try {
    state = await api("/api/dashboard");
    render();
  } catch (error) {
    toast("Dashboard refresh failed: " + error.message, "error");
  }
}

async function confirmAction(title, message, confirmText) {
  const dialog = el("#confirmDialog");
  el("#confirmTitle").textContent = title;
  el("#confirmMessage").textContent = message;
  el("#confirmAction").textContent = confirmText || "Confirm";
  dialog.showModal();
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), {once: true});
  });
}

async function openLead(id) {
  activeLead = Number(id);
  const results = await Promise.all([
    api("/api/leads/" + activeLead),
    api("/api/customers/" + activeLead + "/history")
  ]);
  activeLeadData = results[0];
  const history = results[1];
  const lead = activeLeadData;
  const row = state.leads.find((item) => item.id === activeLead);
  const human = !!(row && row.human_control);

  el("#dialogTitle").textContent = lead.name;
  el("#leadSummary").innerHTML =
    '<span>' + esc(lead.phone || "No phone") + '</span>' +
    '<span>' + esc(lead.email || "No email") + '</span>' +
    '<span>' + money(lead.estimated_value) + '</span>';
  el("#leadStageLine").innerHTML =
    '<span class="stage">' + esc(lead.stage.toUpperCase()) + '</span>' +
    '<span class="urgency-label">' + esc(lead.urgency.toUpperCase()) + '</span>' +
    '<span>' + esc(lead.issue || "No issue recorded") + '</span>';

  el("#conversation").innerHTML = lead.messages.length ? lead.messages.map((message) =>
    '<div class="bubble ' + esc(message.direction) + '">' +
      '<small>' + esc(message.actor) + ' · ' + timeText(message.created_at) + '</small>' +
      esc(message.body) + '</div>'
  ).join("") : '<div class="hint">No messages yet.</div>';

  el("#customerHistory").innerHTML = history.previous_requests.length ?
    history.previous_requests.map((item) =>
      '<div class="history-item"><strong>' + esc(item.stage.toUpperCase()) + '</strong>' +
      '<span>' + esc(item.issue || "No issue") + '</span><small>' + timeText(item.created_at) + '</small></div>'
    ).join("") : '<div class="hint">No previous requests found for this customer.</div>';

  el("#leadAppointments").innerHTML = lead.appointments.length ?
    lead.appointments.map((item) =>
      '<div class="history-item"><strong>' + esc(item.status.toUpperCase()) + '</strong>' +
      '<span>' + timeText(item.starts_at) + '</span><small>' + esc(item.notes || "") + '</small></div>'
    ).join("") : '<div class="hint">No appointments yet.</div>';

  el("#takeoverBtn").textContent = human ? "Return to Nexora" : "Take over";
  el("#conversationModeNote").textContent = human ?
    "Human control is active. Nexora messaging and automated follow-up are paused." :
    "Nexora controls this conversation. Take over at any time.";

  const proposed = lead.appointments.find((item) => item.status === "proposed");
  el("#bookBtn").classList.toggle("hidden", !proposed);
  el("#completeJobBtn").classList.toggle("hidden", lead.stage !== "booked");
  el("#markLostBtn").classList.toggle("hidden", ["lost", "completed"].includes(lead.stage));
  el("#leadDialog").showModal();
}

function setWizardStep(step) {
  wizardStep = Math.max(0, Math.min(4, step));
  els(".wizard-step").forEach((node, index) => node.classList.toggle("active", index === wizardStep));
  els(".wizard-progress span").forEach((node, index) => node.classList.toggle("active", index <= wizardStep));
  el("#wizardBack").disabled = wizardStep === 0;
  el("#wizardNext").classList.toggle("hidden", wizardStep === 4);
  el("#wizardSave").classList.toggle("hidden", wizardStep !== 4);

  if (wizardStep === 4) {
    const data = Object.fromEntries(new FormData(el("#onboardingForm")).entries());
    el("#onboardingReview").innerHTML =
      '<strong>' + esc(data.business_name || "Business") + '</strong>' +
      '<p>' + esc(data.services || "No services entered").replaceAll("\n", ", ") + '</p>' +
      '<p>' + esc(data.service_area || "No service area entered") + '</p>' +
      '<p>' + esc(data.business_hours || "No business hours entered") + '</p>' +
      '<p>' + esc(data.knowledge_summary || "No additional policies or FAQs entered") + '</p>';
  }
}

async function openOnboarding() {
  const data = await api("/api/onboarding");
  const form = el("#onboardingForm");
  const w = data.workspace || {};
  const p = data.profile || {};
  form.elements.business_name.value = w.name || "";
  form.elements.industry.value = "HVAC";
  form.elements.timezone.value = w.timezone || "America/New_York";
  form.elements.phone.value = w.phone || "";
  form.elements.email.value = w.email || "";
  form.elements.website.value = w.website || "";
  form.elements.services.value = (p.services || []).join("\n");
  form.elements.service_area.value = p.service_area || "";
  form.elements.business_hours.value = p.business_hours || "";
  form.elements.emergency_policy.value = p.emergency_policy || "";
  form.elements.knowledge_summary.value = w.knowledge_summary || "";
  form.elements.booking_duration_minutes.value = p.booking_duration_minutes || 60;
  form.elements.followup_after_minutes.value = p.followup_after_minutes || 120;
  form.elements.followup_max_attempts.value = p.followup_max_attempts || 3;
  setWizardStep(0);
  el("#onboardingDialog").showModal();
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const action = button.dataset.action;

  try {
    if (action === "open-lead") {
      await openLead(button.dataset.lead);
    } else if (action === "toggle-agent") {
      await run(() => api("/api/agents/" + button.dataset.agent + "/toggle", {method: "POST"}));
      await refresh();
    } else if (action === "approval") {
      await run(() => api("/api/approvals/" + button.dataset.id + "/resolve", {
        method: "POST", body: JSON.stringify({decision: button.dataset.decision})
      }), "Approval updated.");
      await refresh();
    } else if (action === "connect-google") {
      const data = await run(() => api("/api/connectors/google/start"));
      window.location.href = data.authorization_url;
    } else if (action === "sync-gmail") {
      const data = await run(() => api("/api/connectors/gmail/sync", {method: "POST"}));
      toast("Processed " + data.fetched + " unread Gmail message(s).", "ok");
      await refresh();
    } else if (action === "connector-dialog") {
      document.getElementById(button.dataset.dialog).showModal();
    } else if (action === "test-connector") {
      const data = await run(() => api("/api/connectors/" + button.dataset.slug + "/test", {method: "POST"}));
      toast(data.detail || "Connector healthy.", "ok");
      await refresh();
    } else if (action === "disconnect-connector") {
      const slug = button.dataset.slug;
      if (await confirmAction("Disconnect " + slug + "?", "Stored connector credentials will be removed.", "Disconnect")) {
        await run(() => api("/api/connectors/" + slug + "/disconnect", {method: "POST"}), "Connector disconnected.");
        await refresh();
      }
    } else if (action === "mock-connector") {
      await run(() => api("/api/connectors/" + button.dataset.slug + "/mock", {method: "POST"}), "Mock connector enabled.");
      await refresh();
    }
  } catch (_) {
    // Errors are already surfaced by run()/toast.
  }
});

document.addEventListener("change", async (event) => {
  const node = event.target.closest('[data-action="autonomy"]');
  if (!node) return;
  try {
    await run(() => api("/api/agents/" + node.dataset.agent + "/autonomy/" + node.value, {method: "POST"}));
    await refresh();
  } catch (_) {}
});

el("#sendMessage").addEventListener("click", async () => {
  const body = el("#messageBody").value.trim();
  if (!body || !activeLead) return;
  const button = el("#sendMessage");
  button.disabled = true;
  try {
    const row = state.leads.find((item) => item.id === activeLead);
    const human = !!(row && row.human_control);
    const endpoint = human ? "/api/leads/" + activeLead + "/human-message" : "/api/leads/" + activeLead + "/message";
    const payload = human ? {body} : {body, channel: "web"};
    await run(() => api(endpoint, {method: "POST", body: JSON.stringify(payload)}));
    el("#messageBody").value = "";
    await refresh();
    await openLead(activeLead);
  } finally {
    button.disabled = false;
  }
});

el("#managerForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const objective = el("#managerInput").value.trim();
  if (!objective) return;
  try {
    const result = await run(() => api("/api/manager/run", {
      method: "POST", body: JSON.stringify({objective})
    }));
    const box = el("#managerResult");
    box.classList.remove("hidden");
    box.textContent = result.message + (result.actions.length ? "\n" + result.actions.join("\n") : "");
    await refresh();
  } catch (_) {}
});

el("#newLeadBtn").addEventListener("click", () => el("#newLeadDialog").showModal());

el("#newLeadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  payload.estimated_value = Number(payload.estimated_value || 0);
  try {
    await run(() => api("/api/leads", {method: "POST", body: JSON.stringify(payload)}), "Lead created.");
    el("#newLeadDialog").close();
    event.currentTarget.reset();
    await refresh();
  } catch (_) {}
});

el("#takeoverBtn").addEventListener("click", async () => {
  if (!activeLead) return;
  const row = state.leads.find((item) => item.id === activeLead);
  const human = !!(row && row.human_control);
  const nextMode = human ? "Return control to Nexora?" : "Take human control?";
  const detail = human ?
    "Nexora may resume scheduled follow-up for this open lead." :
    "Automated follow-up will pause immediately while you control the conversation.";
  if (!await confirmAction(nextMode, detail, human ? "Return to Nexora" : "Take over")) return;
  try {
    await run(() => api("/api/leads/" + activeLead + (human ? "/return-to-ai" : "/takeover"), {method: "POST"}));
    await refresh();
    await openLead(activeLead);
  } catch (_) {}
});

el("#bookBtn").addEventListener("click", async () => {
  if (!activeLead) return;
  if (!await confirmAction("Confirm appointment?", "This will mark the lead booked, stop follow-up and sync Google Calendar when connected.", "Confirm booking")) return;
  try {
    const result = await run(() => api("/api/leads/" + activeLead + "/book", {method: "POST"}));
    toast(result.calendar_synced ? "Booked and synced to Google Calendar." : "Booked. Google Calendar sync was unavailable.", result.calendar_synced ? "ok" : "warn");
    await refresh();
    await openLead(activeLead);
  } catch (_) {}
});

el("#completeJobBtn").addEventListener("click", () => {
  if (!activeLead || !activeLeadData) return;
  el("#actualRevenue").value = String(activeLeadData.estimated_value || 0);
  el("#revenueDialog").showModal();
});

el("#revenueForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!activeLead) return;
  const actual = Number(el("#actualRevenue").value);
  if (!Number.isFinite(actual) || actual < 0) {
    toast("Enter a valid revenue amount.", "error");
    return;
  }
  try {
    await run(() => api("/api/leads/" + activeLead + "/complete-job", {
      method: "POST", body: JSON.stringify({actual_amount: actual})
    }), "Completed revenue recorded.");
    el("#revenueDialog").close();
    await refresh();
    await openLead(activeLead);
  } catch (_) {}
});

el("#markLostBtn").addEventListener("click", async () => {
  if (!activeLead) return;
  if (!await confirmAction("Mark lead lost?", "Nexora will stop automated follow-up for this lead.", "Mark lost")) return;
  try {
    await run(() => api("/api/leads/" + activeLead, {
      method: "PATCH", body: JSON.stringify({stage: "lost"})
    }), "Lead marked lost.");
    el("#leadDialog").close();
    await refresh();
  } catch (_) {}
});

el("#configureBusiness").addEventListener("click", openOnboarding);
el("#setupBannerBtn").addEventListener("click", openOnboarding);
el("#wizardBack").addEventListener("click", () => setWizardStep(wizardStep - 1));
el("#wizardNext").addEventListener("click", () => setWizardStep(wizardStep + 1));

el("#onboardingForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget).entries());
  data.services = String(data.services || "").split("\n").map((v) => v.trim()).filter(Boolean);
  data.booking_duration_minutes = Number(data.booking_duration_minutes || 60);
  data.followup_after_minutes = Number(data.followup_after_minutes || 120);
  data.followup_max_attempts = Number(data.followup_max_attempts || 3);
  try {
    await run(() => api("/api/onboarding", {method: "POST", body: JSON.stringify(data)}), "Business profile saved.");
    el("#onboardingDialog").close();
    await refresh();
  } catch (_) {}
});

el("#hubspotForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = new FormData(event.currentTarget).get("token");
  try {
    await run(() => api("/api/connectors/hubspot/connect", {
      method: "POST", body: JSON.stringify({private_app_token: token})
    }), "HubSpot connected.");
    event.currentTarget.reset();
    el("#hubspotDialog").close();
    await refresh();
  } catch (_) {}
});

el("#webhookForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    await run(() => api("/api/connectors/webhook/connect", {
      method: "POST",
      body: JSON.stringify({url: form.get("url"), secret: form.get("secret") || ""})
    }), "Webhook connected.");
    event.currentTarget.reset();
    el("#webhookDialog").close();
    await refresh();
  } catch (_) {}
});

el("#runAutomations").addEventListener("click", async () => {
  try {
    const result = await run(() => api("/api/automation/run-due", {method: "POST"}));
    toast("Processed " + result.processed + " due automation job(s).", "ok");
    await refresh();
  } catch (_) {}
});

el("#simulateApproval").addEventListener("click", async () => {
  try {
    await run(() => api("/api/actions/request", {
      method: "POST",
      body: JSON.stringify({
        agent_slug: "operations",
        action_type: "dispatch_technician",
        reason: "Demo sensitive action requiring owner approval.",
        payload: {lead_id: state.leads.length ? state.leads[0].id : null}
      })
    }), "Demo approval created.");
    await refresh();
  } catch (_) {}
});

el("#checkAvailabilityBtn").addEventListener("click", async () => {
  try {
    const data = await run(() => api("/api/availability"));
    el("#availabilityList").innerHTML = data.calendar_connected ?
      (data.slots.length ? data.slots.map((slot) =>
        '<div class="history-item"><strong>AVAILABLE</strong><span>' + timeText(slot) +
        '</span><small>' + data.duration_minutes + ' minute service window</small></div>'
      ).join("") : '<div class="hint">Google is connected, but no open windows were found in the search window.</div>') :
      '<div class="hint">Connect Google Calendar to check real availability.</div>';
    el("#availabilityDialog").showModal();
  } catch (_) {}
});

els("[data-close]").forEach((button) => {
  button.addEventListener("click", () => document.getElementById(button.dataset.close).close());
});

els("[data-scroll]").forEach((button) => {
  button.addEventListener("click", () => {
    document.getElementById(button.dataset.scroll).scrollIntoView({behavior: "smooth"});
    els(".nav").forEach((node) => node.classList.remove("active"));
    button.classList.add("active");
  });
});

if (!isDemo) {
  els(".demo-only").forEach((node) => node.classList.add("hidden"));
}

refresh();
