let state = null;
let activeLead = null;

const el = (selector) => document.querySelector(selector);
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
    metric("Qualified", m.qualified) +
    metric("Appointments", m.appointments) +
    metric("Pipeline", money(m.pipeline)) +
    metric("Approvals", m.pending_approvals) +
    metric("Open tasks", m.open_tasks);
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
      '<div class="agent-meta"><strong>' + agent.name + '</strong><p>' + agent.role + '</p></div>' +
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
      '<td><strong>' + lead.name + '</strong><br><small>' + lead.source + '</small></td>' +
      '<td>' + (lead.issue || "—") + '</td>' +
      '<td><span class="stage">' + lead.stage + '</span></td>' +
      '<td class="' + (lead.urgency === "urgent" ? "urgent" : "") + '">' + lead.urgency + '</td>' +
      '<td>' + money(lead.estimated_value) + '</td>' +
      '<td><button class="view" onclick="openLead(' + lead.id + ')">Open</button></td>' +
      '</tr>';
  }).join("");
}

function renderApprovals() {
  el("#approvalList").innerHTML = state.approvals.length ? state.approvals.map(function(item) {
    return '<div class="approval-item">' +
      '<div class="approval-agent">' + item.agent_slug + '</div>' +
      '<div><strong>' + item.action_type + '</strong><br><span class="muted">' + item.reason + '</span></div>' +
      '<div class="approval-actions">' +
      '<button class="approve" onclick="resolveApproval(' + item.id + ', \'approved\')">Approve</button>' +
      '<button class="reject" onclick="resolveApproval(' + item.id + ', \'rejected\')">Reject</button>' +
      '</div></div>';
  }).join("") : '<div class="activity-item"><div class="activity-agent">CLEAR</div><div>No pending approvals.</div></div>';
}

function renderConnectors() {
  el("#connectorGrid").innerHTML = state.connectors.map(function(item) {
    return '<div class="connector-card">' +
      '<strong>' + item.name + '</strong>' +
      '<span>' + item.mode + ' mode</span>' +
      '<span class="connector-status">● ' + item.status + '</span>' +
      '</div>';
  }).join("");
}

function renderActivity() {
  el("#activityList").innerHTML = state.activities.length ? state.activities.map(function(item) {
    return '<div class="activity-item">' +
      '<div class="activity-agent">' + item.agent_slug + '</div>' +
      '<div>' + item.summary + '</div>' +
      '<div class="activity-time">' + timeText(item.created_at) + '</div>' +
      '</div>';
  }).join("") : '<div class="activity-item"><div></div><div>No activity yet.</div></div>';
}

function render() {
  el("#workspaceName").textContent = state.workspace.name;
  el("#workspaceMeta").textContent = state.workspace.industry + " · " + state.workspace.timezone;
  renderMetrics();
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
  const lead = await api("/api/leads/" + id);

  el("#dialogTitle").textContent = lead.name + " · " + lead.stage;
  el("#leadSummary").innerHTML =
    '<span>' + (lead.phone || "No phone") + '</span>' +
    '<span>' + (lead.email || "No email") + '</span>' +
    '<span>' + money(lead.estimated_value) + '</span>';

  el("#conversation").innerHTML = lead.messages.length ? lead.messages.map(function(message) {
    return '<div class="bubble ' + message.direction + '">' +
      '<small>' + message.actor + ' · ' + timeText(message.created_at) + '</small>' +
      message.body +
      '</div>';
  }).join("") : '<div class="hint">No messages yet. Send a customer message to test the workforce.</div>';

  el("#leadDialog").showModal();
};

el("#sendMessage").addEventListener("click", async function() {
  const body = el("#messageBody").value.trim();
  if (!body || !activeLead) return;

  const button = el("#sendMessage");
  button.disabled = true;
  try {
    await api("/api/leads/" + activeLead + "/message", {
      method: "POST",
      body: JSON.stringify({body: body, channel: "web"})
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
