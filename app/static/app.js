let state = null;
let activeLead = null;
let activeLeadData = null;

const el = (selector) => document.querySelector(selector);
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

const timeText = (value) => new Date(value).toLocaleString();

async function api(url, options) {
  const config = options || {};
  const response = await fetch(url, Object.assign({
    headers: {"Content-Type": "application/json"}
  }, config));

  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("Authentication required");
  }

  if (!response.ok) {
    throw new Error(await response.text());
  }

  const type = response.headers.get("content-type") || "";
  return type.includes("application/json") ? response.json() : response.text();
}

function metric(label, value) {
  return '<div class="metric"><span>' + label + '</span><strong>' + value + '</strong></div>';
}

function renderMetrics() {
  const m = state.metrics;
  el("#metrics").innerHTML =
    metric("Leads", m.leads) +
    metric("Booked pipeline", money(m.booked_pipeline)) +
    metric("Completed revenue", money(m.completed_revenue)) +
    metric("Recovered revenue", money(m.recovered_revenue)) +
    metric("Open opportunity", money(m.open_opportunity)) +
    metric("Approvals", m.pending_approvals);
}

function renderOpportunities() {
  const items = state.opportunities || [];
  el("#opportunityList").innerHTML = items.length ? items.map(function(item) {
    return '<div class="opportunity-item">' +
      '<div><strong>#' + item.lead_id + ' ' + esc(item.name) + '</strong><br>' +
      '<span class="muted">' + esc(item.stage) + ' · idle ' + item.hours_idle + 'h</span></div>' +
      '<div class="opportunity-value">' + money(item.estimated_value) + '</div>' +
      '<div>' + esc(item.recommended_action) + '</div>' +
      '<button class="view" onclick="openLead(' + item.lead_id + ')">Work lead</button>' +
      '</div>';
  }).join("") : '<div class="activity-item"><div class="activity-agent">CLEAR</div><div>No open revenue opportunities.</div></div>';
}

function renderProfile() {
  const p = state.profile || {};
  const services = (p.services || []).slice(0, 6).join(", ");
  el("#profileCard").innerHTML =
    '<div><span class="profile-label">Status</span><strong>' + (p.onboarding_completed ? "Configured" : "Needs setup") + '</strong></div>' +
    '<div><span class="profile-label">Services</span><strong>' + esc(services || "Not configured") + '</strong></div>' +
    '<div><span class="profile-label">Service area</span><strong>' + esc(p.service_area || "Not configured") + '</strong></div>' +
    '<div><span class="profile-label">Follow-up</span><strong>' + (p.followup_after_minutes || 120) + ' min · ' + (p.followup_max_attempts || 3) + ' attempts</strong></div>';
}

function renderAgents() {
  el("#agentGrid").innerHTML = state.agents.map(function(agent) {
    const initial = agent.name.replace("Nexora ", "").slice(0, 1);
    const options = ["manual", "guarded", "autonomous"].map(function(level) {
      return '<option value="' + level + '"' +
        (agent.autonomy_level === level ? ' selected' : '') +
        '>' + level + '</option>';
    }).join("");

    return '<div class="agent-card">' +
      '<div class="agent-top">' +
      '<div class="agent-icon">' + initial + '</div>' +
      '<div class="agent-meta"><strong>' + esc(agent.name) + '</strong><p>' + esc(agent.role) + '</p></div>' +
      '</div>' +
      '<div class="agent-controls">' +
      '<button class="toggle ' + (agent.enabled ? 'on' : '') + '" onclick="toggleAgent(\'' + agent.slug + '\')">' +
      (agent.enabled ? 'ON' : 'OFF') +
      '</button>' +
      '<select onchange="setAutonomy(\'' + agent.slug + '\', this.value)">' + options + '</select>' +
      '</div></div>';
  }).join("");
}

function renderLeads() {
  el("#leadRows").innerHTML = state.leads.map(function(lead) {
    return '<tr>' +
      '<td><strong>' + esc(lead.name) + '</strong><br><small>' + esc(lead.source) + '</small></td>' +
      '<td>' + esc(lead.issue || "—") + '</td>' +
      '<td><span class="stage">' + esc(lead.stage) + '</span></td>' +
      '<td><span class="control ' + (lead.human_control ? "human" : "ai") + '">' + (lead.human_control ? "HUMAN" : "AI") + '</span></td>' +
      '<td class="' + (lead.urgency === "urgent" ? "urgent" : "") + '">' + esc(lead.urgency) + '</td>' +
      '<td>' + money(lead.estimated_value) + '</td>' +
      '<td><button class="view" onclick="openLead(' + lead.id + ')">Open</button></td>' +
      '</tr>';
  }).join("");
}

function renderApprovals() {
  el("#approvalList").innerHTML = state.approvals.length ? state.approvals.map(function(item) {
    return '<div class="approval-item">' +
      '<div class="approval-agent">' + esc(item.agent_slug) + '</div>' +
      '<div><strong>' + esc(item.action_type) + '</strong><br><span class="muted">' + esc(item.reason) + '</span></div>' +
      '<div class="approval-actions">' +
      '<button class="approve" onclick="resolveApproval(' + item.id + ', \'approved\')">Approve</button>' +
      '<button class="reject" onclick="resolveApproval(' + item.id + ', \'rejected\')">Reject</button>' +
      '</div></div>';
  }).join("") : '<div class="activity-item"><div class="activity-agent">CLEAR</div><div>No pending approvals.</div></div>';
}

function connectorAction(item) {
  if (item.slug === "google") {
    return '<button class="view" onclick="connectGoogle()">Connect Google</button><button class="view" onclick="syncGmail()">Sync Gmail</button>';
  }
  if (item.slug === "hubspot") {
    return '<button class="view" onclick="openConnectorDialog(\'hubspotDialog\')">Connect HubSpot</button>';
  }
  if (item.slug === "webhook") {
    return '<button class="view" onclick="openConnectorDialog(\'webhookDialog\')">Connect webhook</button>';
  }
  return "";
}

function renderConnectors() {
  el("#connectorGrid").innerHTML = state.connectors
    .filter(function(item) { return ["google", "hubspot", "webhook"].includes(item.slug); })
    .map(function(item) {
      return '<div class="connector-card">' +
        '<strong>' + esc(item.name) + '</strong>' +
        '<span>' + esc(item.mode) + ' mode</span>' +
        '<span class="connector-status">● ' + esc(item.status) + '</span>' +
        '<div class="connector-actions">' + connectorAction(item) + '</div>' +
        '</div>';
    }).join("");
}

function renderActivity() {
  el("#activityList").innerHTML = state.activities.length ? state.activities.map(function(item) {
    return '<div class="activity-item">' +
      '<div class="activity-agent">' + esc(item.agent_slug) + '</div>' +
      '<div>' + esc(item.summary) + '</div>' +
      '<div class="activity-time">' + timeText(item.created_at) + '</div>' +
      '</div>';
  }).join("") : '<div class="activity-item"><div></div><div>No activity yet.</div></div>';
}

function render() {
  el("#workspaceName").textContent = state.workspace.name;
  el("#workspaceMeta").textContent = state.workspace.industry + " · " + state.workspace.timezone;
  renderMetrics();
  renderOpportunities();
  renderProfile();
  renderAgents();
  renderLeads();
  renderApprovals();
  renderConnectors();
  renderActivity();
}

async function refresh() {
  state = await api("/api/dashboard");
  render();
}

window.toggleAgent = async function(slug) {
  await api("/api/agents/" + slug + "/toggle", {method: "POST"});
  await refresh();
};

window.setAutonomy = async function(slug, level) {
  await api("/api/agents/" + slug + "/autonomy/" + level, {method: "POST"});
  await refresh();
};

window.resolveApproval = async function(id, decision) {
  await api("/api/approvals/" + id + "/resolve", {
    method: "POST",
    body: JSON.stringify({decision: decision})
  });
  await refresh();
};

window.openLead = async function(id) {
  activeLead = id;
  activeLeadData = await api("/api/leads/" + id);
  const lead = activeLeadData;
  const row = state.leads.find(function(item) { return item.id === id; });
  const human = !!(row && row.human_control);

  el("#dialogTitle").textContent = lead.name + " · " + lead.stage;
  el("#leadSummary").innerHTML =
    '<span>' + esc(lead.phone || "No phone") + '</span>' +
    '<span>' + esc(lead.email || "No email") + '</span>' +
    '<span>' + money(lead.estimated_value) + '</span>';

  el("#conversation").innerHTML = lead.messages.length ? lead.messages.map(function(message) {
    return '<div class="bubble ' + message.direction + '">' +
      '<small>' + esc(message.actor) + ' · ' + timeText(message.created_at) + '</small>' +
      esc(message.body) +
      '</div>';
  }).join("") : '<div class="hint">No messages yet. Send a customer message to test the workforce.</div>';

  el("#takeoverBtn").textContent = human ? "Return to Nexora" : "Take over";
  el("#conversationModeNote").textContent = human ?
    "Human control is active. AI automation is paused for this conversation." :
    "Nexora has control of this conversation.";

  const proposed = lead.appointments.find(function(item) { return item.status === "proposed"; });
  el("#bookBtn").classList.toggle("hidden", !proposed);
  el("#completeJobBtn").classList.toggle("hidden", lead.stage !== "booked");
  el("#leadDialog").showModal();
};

el("#sendMessage").addEventListener("click", async function() {
  const body = el("#messageBody").value.trim();
  if (!body || !activeLead) return;

  const button = el("#sendMessage");
  button.disabled = true;
  try {
    const row = state.leads.find(function(item) { return item.id === activeLead; });
    const human = !!(row && row.human_control);
    const endpoint = human ? "/api/leads/" + activeLead + "/human-message" : "/api/leads/" + activeLead + "/message";
    const payload = human ? {body: body} : {body: body, channel: "web"};
    await api(endpoint, {
      method: "POST",
      body: JSON.stringify(payload)
    });
    el("#messageBody").value = "";
    await refresh();
    await window.openLead(activeLead);
  } finally {
    button.disabled = false;
  }
});

el("#managerForm").addEventListener("submit", async function(event) {
  event.preventDefault();
  const objective = el("#managerInput").value.trim();
  if (!objective) return;

  const result = await api("/api/manager/run", {
    method: "POST",
    body: JSON.stringify({objective: objective})
  });

  const box = el("#managerResult");
  box.classList.remove("hidden");
  box.innerHTML =
    '<strong>' + result.message + '</strong>' +
    (result.actions.length ? '<br>' + result.actions.join('<br>') : '');

  await refresh();
});

el("#newLeadBtn").addEventListener("click", function() {
  el("#newLeadDialog").showModal();
});

el("#newLeadForm").addEventListener("submit", async function(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  payload.estimated_value = Number(payload.estimated_value || 0);

  await api("/api/leads", {
    method: "POST",
    body: JSON.stringify(payload)
  });

  el("#newLeadDialog").close();
  event.currentTarget.reset();
  await refresh();
});


window.openConnectorDialog = function(id) {
  document.getElementById(id).showModal();
};

window.connectGoogle = async function() {
  try {
    const data = await api("/api/connectors/google/start");
    window.location.href = data.authorization_url;
  } catch (error) {
    alert("Google OAuth is not configured in .env yet.");
  }
};

window.syncGmail = async function() {
  try {
    const data = await api("/api/connectors/gmail/sync", {method: "POST"});
    alert("Fetched " + data.fetched + " unread Gmail message(s).");
    await refresh();
  } catch (error) {
    alert("Connect Google in real mode before syncing Gmail.");
  }
};

el("#takeoverBtn").addEventListener("click", async function() {
  if (!activeLead) return;
  const row = state.leads.find(function(item) { return item.id === activeLead; });
  const human = !!(row && row.human_control);
  await api("/api/leads/" + activeLead + (human ? "/return-to-ai" : "/takeover"), {method: "POST"});
  await refresh();
  await window.openLead(activeLead);
});

el("#completeJobBtn").addEventListener("click", async function() {
  if (!activeLead || !activeLeadData) return;
  const entered = window.prompt("Actual completed job revenue", String(activeLeadData.estimated_value || 0));
  if (entered === null) return;
  const actual = Number(entered);
  if (!Number.isFinite(actual) || actual < 0) {
    alert("Enter a valid revenue amount.");
    return;
  }
  await api("/api/leads/" + activeLead + "/complete-job", {
    method: "POST",
    body: JSON.stringify({actual_amount: actual})
  });
  await refresh();
  await window.openLead(activeLead);
});

el("#bookBtn").addEventListener("click", async function() {
  if (!activeLead) return;
  const result = await api("/api/leads/" + activeLead + "/book", {method: "POST"});
  alert(result.calendar_synced ? "Appointment confirmed and synced to Google Calendar." : "Appointment confirmed. Calendar sync was unavailable.");
  await refresh();
  await window.openLead(activeLead);
});

el("#configureBusiness").addEventListener("click", async function() {
  const data = await api("/api/onboarding");
  const form = el("#onboardingForm");
  const w = data.workspace || {};
  const p = data.profile || {};
  form.elements.business_name.value = w.name || "";
  form.elements.industry.value = w.industry || "HVAC";
  form.elements.timezone.value = w.timezone || "America/New_York";
  form.elements.phone.value = w.phone || "";
  form.elements.email.value = w.email || "";
  form.elements.website.value = w.website || "";
  form.elements.services.value = (p.services || []).join("\n");
  form.elements.service_area.value = p.service_area || "";
  form.elements.business_hours.value = p.business_hours || "";
  form.elements.emergency_policy.value = p.emergency_policy || "";
  form.elements.booking_duration_minutes.value = p.booking_duration_minutes || 60;
  form.elements.followup_after_minutes.value = p.followup_after_minutes || 120;
  form.elements.followup_max_attempts.value = p.followup_max_attempts || 3;
  el("#onboardingDialog").showModal();
});

el("#onboardingForm").addEventListener("submit", async function(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget).entries());
  data.services = String(data.services || "").split("\n").map(function(v) { return v.trim(); }).filter(Boolean);
  data.booking_duration_minutes = Number(data.booking_duration_minutes || 60);
  data.followup_after_minutes = Number(data.followup_after_minutes || 120);
  data.followup_max_attempts = Number(data.followup_max_attempts || 3);
  await api("/api/onboarding", {method: "POST", body: JSON.stringify(data)});
  el("#onboardingDialog").close();
  await refresh();
});

el("#hubspotForm").addEventListener("submit", async function(event) {
  event.preventDefault();
  const token = new FormData(event.currentTarget).get("token");
  await api("/api/connectors/hubspot/connect", {method: "POST", body: JSON.stringify({private_app_token: token})});
  event.currentTarget.reset();
  el("#hubspotDialog").close();
  await refresh();
});

el("#webhookForm").addEventListener("submit", async function(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  await api("/api/connectors/webhook/connect", {
    method: "POST",
    body: JSON.stringify({url: form.get("url"), secret: form.get("secret") || ""})
  });
  event.currentTarget.reset();
  el("#webhookDialog").close();
  await refresh();
});

el("#runAutomations").addEventListener("click", async function() {
  const result = await api("/api/automation/run-due", {method: "POST"});
  alert("Processed " + result.processed + " due automation job(s).");
  await refresh();
});

el("#simulateApproval").addEventListener("click", async function() {
  await api("/api/actions/request", {
    method: "POST",
    body: JSON.stringify({
      agent_slug: "operations",
      action_type: "dispatch_technician",
      reason: "Demo sensitive action requiring owner approval.",
      payload: {lead_id: state.leads.length ? state.leads[0].id : null}
    })
  });
  await refresh();
});

document.querySelectorAll("[data-close]").forEach(function(button) {
  button.addEventListener("click", function() {
    document.getElementById(button.dataset.close).close();
  });
});

document.querySelectorAll("[data-scroll]").forEach(function(button) {
  button.addEventListener("click", function() {
    document.getElementById(button.dataset.scroll).scrollIntoView({behavior: "smooth"});
  });
});

refresh();
