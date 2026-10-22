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
const CHECK_LABELS = {
  allergy_conflict: "Allergy conflict",
  antibiotic_for_viral: "Antibiotic for viral illness",
  indication_mismatch: "Indication mismatch",
  contraindication: "Contraindication",
  drug_interaction: "Drug interaction",
};
const WEAK_WORD = 0.5;

const el = {
  caseTitle: document.getElementById("case-title"),
  caseMeta: document.getElementById("case-meta"),
  pipelineMeta: document.getElementById("pipeline-meta"),
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
  player: document.getElementById("player"),
};

let state = { case: null, calibration: {}, lastThresholds: {}, selected: null };

async function api(url, opts = {}) {
  const res = await fetch(url, { credentials: "include", ...opts });
  if (res.status === 401) { location.href = "login.html"; throw new Error("redirecting"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Request failed.");
  return data;
}

function escapeHTML(str) { const d = document.createElement("div"); d.textContent = str ?? ""; return d.innerHTML; }
const fmt = (x) => (x == null ? "n/a" : x.toFixed(2));
const clock = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

// --- transcript ---

function wordsHTML(seg, highlight) {
  // highlight: [[start, end], ...] character ranges of quoted evidence
  const inQuote = (w) => highlight.some(([a, b]) => w.char_end > a && w.char_start < b);
  if (!seg.words || !seg.words.length) {
    if (!highlight.length) return escapeHTML(seg.text);
    let out = "", pos = 0;
    for (const [a, b] of [...highlight].sort((x, y) => x[0] - y[0])) {
      if (a < pos) continue;
      out += escapeHTML(seg.text.slice(pos, a)) + `<mark>${escapeHTML(seg.text.slice(a, b))}</mark>`;
      pos = b;
    }
    return out + escapeHTML(seg.text.slice(pos));
  }
  let out = "", pos = 0;
  for (const w of seg.words) {
    out += escapeHTML(seg.text.slice(pos, w.char_start));
    const cls = [w.prob < WEAK_WORD ? "weak" : "", w.asr_text ? "corrected" : "", inQuote(w) ? "quoted" : ""].filter(Boolean).join(" ");
    const title = `ASR confidence ${w.prob.toFixed(2)}` + (w.asr_text ? ` · corrected from "${w.asr_text}"` : "");
    out += `<span class="w ${cls}" title="${escapeHTML(title)}">${escapeHTML(seg.text.slice(w.char_start, w.char_end))}</span>`;
    pos = w.char_end;
  }
  return out + escapeHTML(seg.text.slice(pos));
}

function segmentHTML(seg, highlight) {
  const cls = seg.speaker === "DOCTOR" ? "speaker-doctor" : seg.speaker === "PATIENT" ? "speaker-patient" : "speaker-other";
  const cited = highlight ? "cited" : "";
  const acoustic = seg.acoustic_confidence != null
    ? `<span class="seg-acoustic ${seg.acoustic_confidence < WEAK_WORD ? "low" : ""}" title="Mean ASR word confidence">${seg.acoustic_confidence.toFixed(2)}</span>` : "";
  const inferred = seg.speaker_source === "llm_attribution" ? `<span class="seg-inferred" title="Speaker role attributed by the LLM from content">inferred</span>` : "";
  const play = seg.audio_source
    ? `<button class="play" data-play="${seg.id}" title="Play ${clock(seg.start)}–${clock(seg.end)}" aria-label="Play segment ${seg.id}">▶</button>` : "";
  const time = seg.start != null && seg.audio_source ? `<span class="seg-time">${clock(seg.start)}</span>` : "";
  return `<div class="segment ${cls} ${cited}" id="seg-${seg.id}">
    <div class="seg-head">
      <span class="speaker">${seg.speaker}<span class="seg-id">#${seg.id}</span>${inferred}</span>
      <span class="seg-tools">${time}${acoustic}${play}</span>
    </div>
    <span class="seg-text">${wordsHTML(seg, highlight || [])}</span>
  </div>`;
}

function renderTranscript() {
  const c = state.case;
  const selected = c.facts.find(f => f.fact_id === state.selected);
  const ranges = {};
  if (selected) {
    for (const id of selected.cited_segment_ids) ranges[id] = ranges[id] || [];
    for (const chk of selected.evidence_checks || []) {
      if (chk.found) (ranges[chk.segment_id] = ranges[chk.segment_id] || []).push([chk.char_start, chk.char_end]);
    }
  }
  el.transcript.innerHTML = c.segments.map(s => segmentHTML(s, ranges[s.id])).join("");
}

// --- facts ---

function signalsHTML(fact) {
  const nli = fact.nli || {};
  const parts = [];
  if (nli.entailment != null) {
    parts.push(`<span class="sig" title="P(entailment) from the NLI model">entailment <b>${fmt(nli.entailment)}</b></span>`);
    if (nli.contradiction >= 0.2) parts.push(`<span class="sig sig-bad" title="P(contradiction)">contradiction <b>${fmt(nli.contradiction)}</b></span>`);
  }
  if (fact.status !== "REJECTED" || fact.acoustic_score != null) {
    parts.push(fact.acoustic_score == null
      ? `<span class="sig sig-na" title="Text input: no audio, so no acoustic signal">acoustic <b>n/a</b></span>`
      : `<span class="sig" title="Mean ASR word confidence over the quoted evidence">acoustic <b>${fmt(fact.acoustic_score)}</b></span>`);
  }
  if (fact.combined_confidence) parts.push(`<span class="sig">combined <b>${fmt(fact.combined_confidence)}</b></span>`);
  return parts.join("");
}

function evidenceHTML(fact) {
  const checks = fact.evidence_checks && fact.evidence_checks.length ? fact.evidence_checks
    : (fact.evidence || []).map(e => ({ ...e, found: null }));
  if (!checks.length) return "";
  return `<ul class="evidence">${checks.map(c => `<li class="${c.found === false ? "missing" : ""}">
      <span class="ev-seg">#${c.segment_id}</span>“${escapeHTML(c.quote)}”${c.found === false ? ` <span class="ev-miss">not in segment (${Math.round(c.match)}/100)</span>` : ""}
    </li>`).join("")}</ul>`;
}

function plausibilityHTML(fact) {
  if (!fact.plausibility || !fact.plausibility.length) return "";
  return `<ul class="plaus">${fact.plausibility.map(p =>
    `<li><span class="plaus-tag">${CHECK_LABELS[p.check] || p.check}</span>${escapeHTML(p.message)}</li>`).join("")}</ul>`;
}

function factCardHTML(fact, status) {
  const gateBlocked = fact.status === "REJECTED";
  const badgeClass = status === "verified" ? "badge-verified" : status === "pending" ? (gateBlocked ? "badge-rejected" : "badge-pending") : "badge-rejected";
  const badgeLabel = status === "verified" ? (fact.resolution === "approve" ? `Approved · ${escapeHTML(fact.resolved_by || "")}` : "Verified")
    : status === "pending" ? (gateBlocked ? "Blocked by gate" : "Needs review") : `Rejected · ${escapeHTML(fact.resolved_by || "")}`;
  const meta = `<div class="fact-meta">
      <span class="badge ${badgeClass}">${badgeLabel}</span>
      ${signalsHTML(fact)}
      <span class="fact-src">${fact.source === "llm" ? "LLM" : "rule-based"} · ${fact.fact_id}</span>
    </div>`;
  const reason = status !== "verified" || fact.resolution === "approve"
    ? `<div class="fact-reason">${escapeHTML(fact.reason)}</div>` : "";
  const actions = status === "pending"
    ? `<div class="fact-actions">
         <button class="btn btn-primary btn-sm" data-action="approve" data-fact="${fact.fact_id}">Approve</button>
         <button class="btn btn-danger-ghost btn-sm" data-action="reject" data-fact="${fact.fact_id}">Reject</button>
       </div>`
    : "";
  const selected = state.selected === fact.fact_id ? "selected" : "";
  return `<div class="fact-card status-${status} ${selected}" data-fact-id="${fact.fact_id}" tabindex="0" title="Show evidence in transcript">
      <div class="fact-value">${escapeHTML(fact.value)}</div>
      ${meta}${evidenceHTML(fact)}${plausibilityHTML(fact)}${reason}${actions}
    </div>`;
}

function render() {
  const c = state.case;
  if (!c) return;
  el.app.hidden = false;
  renderTranscript();

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
    const cal = state.calibration[field];
    if (!cal) return "";
    const prev = state.lastThresholds[field];
    const changed = prev && prev.threshold !== cal.threshold;
    const delta = changed ? ` <span class="delta">${cal.threshold > prev.threshold ? "▲" : "▼"} from ${prev.threshold.toFixed(2)}</span>` : "";
    const origin = cal.learned ? "learned" : "starting value";
    return `<tr><td>${FIELD_LABELS[field]}</td><td class="${changed ? "threshold-changed" : ""}">${cal.threshold.toFixed(2)}${delta}</td><td class="cal-origin ${cal.learned ? "learned" : ""}">${origin}</td></tr>`;
  }).join("");
}

function renderPipelineMeta(c) {
  const input = c.input || {};
  const rows = [];
  if (input.input_mode === "audio") {
    rows.push(["Input", `Audio · ${clock(input.duration || 0)} · ${input.speaker_roles === "channel" ? "separate doctor/patient channels" : "mixed recording, roles attributed by LLM"}`]);
    rows.push(["Speech recognition", `${input.asr_model} · ${input.segments} segments · ${input.medical_term_corrections} medical-term correction(s)`]);
  } else {
    rows.push(["Input", `Text transcript${input.origin ? ` · ${input.origin}` : ""} · no acoustic signal`]);
  }
  rows.push(["Extraction", c.extractor ? (c.extractor === "rule_based" ? "Rule-based" : c.extractor.replace(/^llm:/, "LLM · ").replace(/:/g, " · ")) : "Rule-based"]);
  if (c.models && c.models.nli) rows.push(["Entailment model", c.models.nli]);
  el.pipelineMeta.innerHTML = rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${escapeHTML(v)}</dd></div>`).join("");
}

async function load() {
  const me = await api("/api/auth/me");
  document.getElementById("doctor-name").textContent = me.name;

  const data = await api(`/api/cases/${caseId}`);
  state.case = data.case;
  state.calibration = data.calibration;
  el.caseTitle.textContent = data.title;
  const counts = { v: 0, r: 0, b: 0 };
  for (const f of data.case.facts) f.status === "VERIFIED" ? counts.v++ : f.status === "REJECTED" ? counts.b++ : counts.r++;
  el.caseMeta.textContent = `${data.case.segments.length} utterances · ${data.case.facts.length} facts drafted: ${counts.v} auto-verified, ${counts.r} need review, ${counts.b} blocked · reviewing as ${me.name}`;
  renderPipelineMeta(data.case);
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

// --- audio playback of a single segment ---
let stopAt = null;
function playSegment(segId) {
  const seg = state.case.segments.find(s => s.id === segId);
  if (!seg || !seg.audio_source) return;
  const src = `/api/cases/${caseId}/audio/${seg.audio_source}`;
  const start = () => {
    el.player.currentTime = Math.max(0, seg.start - 0.15);
    stopAt = seg.end + 0.25;
    setPlaying(segId);
    el.player.play().catch(err => { setPlaying(null); alert(`Could not play audio: ${err.message}`); });
  };
  if (!el.player.src.endsWith(src)) {
    el.player.src = src;
    el.player.addEventListener("loadedmetadata", start, { once: true });
    el.player.load();  // preload="none": nothing is fetched until load() is called
  } else if (el.player.readyState >= 1) {
    start();
  } else {
    el.player.addEventListener("loadedmetadata", start, { once: true });
  }
}

function setPlaying(segId) {
  document.querySelectorAll(".play.playing").forEach(b => { b.classList.remove("playing"); b.textContent = "▶"; });
  if (segId != null) {
    const btn = document.querySelector(`[data-play="${segId}"]`);
    if (btn) { btn.classList.add("playing"); btn.textContent = "■"; }
  }
}
el.player.addEventListener("pause", () => setPlaying(null));
el.player.addEventListener("error", () => {
  setPlaying(null);
  if (el.player.src) alert("Could not load this case's audio recording.");
});
el.player.addEventListener("timeupdate", () => {
  if (stopAt != null && el.player.currentTime >= stopAt) { el.player.pause(); stopAt = null; }
});

function selectFact(factId) {
  state.selected = state.selected === factId ? null : factId;
  render();
  const fact = state.case.facts.find(f => f.fact_id === state.selected);
  if (fact && fact.cited_segment_ids.length) {
    document.getElementById(`seg-${fact.cited_segment_ids[0]}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

el.auditToggle.addEventListener("click", () => {
  const hidden = el.auditLog.hidden;
  el.auditLog.hidden = !hidden;
  el.auditToggle.textContent = hidden ? "Hide audit trail" : "Show audit trail";
});
document.addEventListener("click", (e) => {
  const action = e.target.closest("[data-action]");
  if (action) { resolveFact(action.dataset.fact, action.dataset.action); return; }
  const play = e.target.closest("[data-play]");
  if (play) {
    if (play.classList.contains("playing")) { el.player.pause(); stopAt = null; return; }
    playSegment(Number(play.dataset.play));
    return;
  }
  const card = e.target.closest(".fact-card");
  if (card) selectFact(card.dataset.factId);
});
document.addEventListener("keydown", (e) => {
  const card = e.target.closest?.(".fact-card");
  if (card && (e.key === "Enter" || e.key === " ") && !e.target.closest("button")) { e.preventDefault(); selectFact(card.dataset.factId); }
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
