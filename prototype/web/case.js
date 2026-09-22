const caseId = new URLSearchParams(location.search).get("id");

const FIELD_ORDER = ["chief_complaint", "history_of_present_illness", "medications", "allergies", "vitals", "assessment", "plan"];
const FIELD_LABELS = {
  chief_complaint: "Chief complaint",
  history_of_present_illness: "History of present illness",
  medications: "Medications",
  allergies: "Allergies",
  vitals: "Vitals",
  assessment: "Assessment",
  plan: "Plan",
};

const el = {
  caseTitle: document.getElementById("case-title"),
  caseMeta: document.getElementById("case-meta"),
  app: document.getElementById("app"),
  transcript: document.getElementById("transcript"),
  noteFields: document.getElementById("note-fields"),
  pendingBlock: document.getElementById("pending-block"),
  pendingList: document.getElementById("pending-list"),
  rejectedBlock: document.getElementById("rejected-block"),
  rejectedList: document.getElementById("rejected-list"),
  calibrationBody: document.querySelector("#calibration-table tbody"),
  auditToggle: document.getElementById("audit-toggle"),
  auditLog: document.getElementById("audit-log"),
};

let state = { case: null, calibration: {}, lastThresholds: {} };

async function api(url, opts = {}) {
  const res = await fetch(url, { credentials: "include", ...opts });
  if (res.status === 401) { location.href = "login.html"; throw new Error("redirecting"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Request failed.");
  return data;
}

function escapeHTML(str) { const d = document.createElement("div"); d.textContent = str ?? ""; return d.innerHTML; }

function segmentHTML(seg) {
  const cls = seg.speaker === "DOCTOR" ? "speaker-doctor" : "speaker-patient";
  return `<div class="segment ${cls}">
    <span class="speaker">${seg.speaker}<span class="seg-id">#${seg.id}</span></span>
    <span class="seg-text">${escapeHTML(seg.text)}</span>
  </div>`;
}

function factCardHTML(fact, status) {
  const badgeClass = status === "verified" ? "badge-verified" : status === "pending" ? "badge-pending" : "badge-rejected";
  const badgeLabel = status === "verified" ? "Verified" : status === "pending" ? "Needs review" : "Rejected";
  const meta = `<div class="fact-meta">
      <span class="badge ${badgeClass}">${badgeLabel}</span>
      <span>segment ${JSON.stringify(fact.cited_segment_ids)}</span>
      <span>confidence ${fact.combined_confidence?.toFixed(2) ?? "-"}</span>
      <span>${fact.fact_id}</span>
    </div>`;
  const reason = status !== "verified" ? `<div class="fact-reason">${escapeHTML(fact.reason)}</div>` : "";
  const actions = status === "pending"
    ? `<div class="fact-actions">
         <button class="btn btn-primary btn-sm" data-action="approve" data-fact="${fact.fact_id}">Approve</button>
         <button class="btn btn-danger-ghost btn-sm" data-action="reject" data-fact="${fact.fact_id}">Reject</button>
       </div>`
    : "";
  return `<div class="fact-card status-${status}" data-fact-id="${fact.fact_id}">
      <div>${escapeHTML(fact.value)}</div>
      ${meta}${reason}${actions}
    </div>`;
}

function render() {
  const c = state.case;
  if (!c) return;
  el.app.hidden = false;

  el.transcript.innerHTML = c.segments.map(segmentHTML).join("");

  const verified = c.facts.filter(f => f.status === "VERIFIED" || f.resolution === "approve");
  const pending = c.facts.filter(f => f.status !== "VERIFIED" && !f.resolution);
  const rejected = c.facts.filter(f => f.resolution === "reject");

  el.noteFields.innerHTML = FIELD_ORDER.map(field => {
    const facts = verified.filter(f => f.field === field);
    if (!facts.length) return "";
    return `<div class="field-group">
        <h4>${FIELD_LABELS[field]}</h4>
        ${facts.map(f => factCardHTML(f, "verified")).join("")}
      </div>`;
  }).join("") || `<p class="muted">No fields cleared the confidence gate yet.</p>`;

  el.pendingBlock.hidden = pending.length === 0;
  el.pendingList.innerHTML = pending.map(f => factCardHTML(f, "pending")).join("");

  el.rejectedBlock.hidden = rejected.length === 0;
  el.rejectedList.innerHTML = rejected.map(f => factCardHTML(f, "rejected")).join("");

  el.calibrationBody.innerHTML = Object.keys(FIELD_LABELS).map(field => {
    const val = state.calibration[field] ?? 0.75;
    const changed = state.lastThresholds[field] !== undefined && state.lastThresholds[field] !== val;
    return `<tr><td>${FIELD_LABELS[field]}</td><td class="${changed ? "threshold-changed" : ""}">${val.toFixed(2)}</td></tr>`;
  }).join("");
}

async function load() {
  const me = await api("/api/auth/me");
  document.getElementById("doctor-name").textContent = me.name;

  const data = await api(`/api/cases/${caseId}`);
  state.case = data.case;
  state.calibration = data.calibration;
  el.caseTitle.textContent = data.title;
  el.caseMeta.textContent = `${data.case.segments.length} utterances · reviewing as ${me.name}`;
  render();
  await refreshAudit();
}

async function resolveFact(factId, decision) {
  try {
    const data = await api(`/api/cases/${caseId}/resolve`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fact_id: factId, decision }),
    });
    state.case = data.case;
    state.lastThresholds = state.calibration;
    state.calibration = data.calibration;
    render();
    await refreshAudit();
  } catch (err) {
    alert(`Resolve failed: ${err.message}`);
  }
}

async function refreshAudit() {
  const entries = await api(`/api/cases/${caseId}/audit`);
  el.auditLog.innerHTML = entries.slice().reverse().map(e =>
    `<div class="audit-entry">${escapeHTML(JSON.stringify(e))}</div>`
  ).join("") || `<p class="muted">No audit entries yet.</p>`;
}

el.auditToggle.addEventListener("click", () => {
  const hidden = el.auditLog.hidden;
  el.auditLog.hidden = !hidden;
  el.auditToggle.textContent = hidden ? "Hide audit trail" : "Show audit trail";
});
document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-action]");
  if (!btn) return;
  resolveFact(btn.dataset.fact, btn.dataset.action);
});
document.getElementById("logout-btn").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  location.href = "/";
});

if (!caseId) {
  el.caseTitle.textContent = "No case selected";
} else {
  load();
}
