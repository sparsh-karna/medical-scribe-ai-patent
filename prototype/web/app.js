let currentPatientId = null;
let libraryCache = null;

async function api(url, opts = {}) {
  const res = await fetch(url, { credentials: "include", ...opts });
  if (res.status === 401) { location.href = "login.html"; throw new Error("redirecting"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Request failed.");
  return data;
}

async function init() {
  const me = await api("/api/auth/me");
  document.getElementById("doctor-name").textContent = me.name;
  loadLlmStatus();
  loadPipelineInfo();
  await loadPatients();
}

document.getElementById("logout-btn").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  location.href = "/";
});

async function loadPatients() {
  const patients = await api("/api/patients");
  const list = document.getElementById("patient-list");
  list.innerHTML = patients.map(p => `
    <div class="patient-item ${p.id === currentPatientId ? "active" : ""}" data-id="${p.id}" data-name="${escapeAttr(p.name)}">
      <span>${escapeHTML(p.name)}</span>
      <span class="count">${p.case_count}</span>
    </div>`).join("") || `<p class="muted" style="font-size:13px;">No patients yet.</p>`;

  list.querySelectorAll(".patient-item").forEach(el => {
    el.addEventListener("click", () => selectPatient(Number(el.dataset.id), el.dataset.name));
  });
}

function escapeHTML(str) { const d = document.createElement("div"); d.textContent = str ?? ""; return d.innerHTML; }
function escapeAttr(str) { return escapeHTML(str).replace(/"/g, "&quot;"); }

async function selectPatient(id, name) {
  currentPatientId = id;
  document.getElementById("no-patient").hidden = true;
  document.getElementById("patient-panel").hidden = false;
  document.getElementById("new-case-panel").hidden = true;
  document.getElementById("patient-name").textContent = name;
  await loadPatients();
  await loadCases();
}

async function loadCases() {
  const cases = await api(`/api/patients/${currentPatientId}/cases`);
  const list = document.getElementById("case-list");
  list.innerHTML = cases.map(c => `
    <a class="case-item" href="case.html?id=${c.id}">
      <div>
        <div class="case-title">${escapeHTML(c.title)}</div>
        <div class="case-meta">${new Date(c.created_at).toLocaleString()}</div>
      </div>
      <span class="source-tag">${c.source}</span>
    </a>`).join("") || `<p class="muted">No cases yet for this patient. Click "New case" to start one.</p>`;
}

// --- new patient ---
document.getElementById("new-patient-btn").addEventListener("click", () => {
  document.getElementById("new-patient-form").hidden = false;
  document.getElementById("new-patient-name").focus();
});
document.getElementById("cancel-patient-btn").addEventListener("click", () => {
  document.getElementById("new-patient-form").hidden = true;
});
document.getElementById("new-patient-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const nameInput = document.getElementById("new-patient-name");
  const patient = await api("/api/patients", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: nameInput.value.trim() }),
  });
  nameInput.value = "";
  document.getElementById("new-patient-form").hidden = true;
  await loadPatients();
  await selectPatient(patient.id, patient.name);
});

// --- new case ---
document.getElementById("new-case-btn").addEventListener("click", async () => {
  const panel = document.getElementById("new-case-panel");
  panel.hidden = !panel.hidden;
  if (!panel.hidden && !libraryCache) await loadLibrary();
});

document.querySelectorAll(".tab[data-source]").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab[data-source]").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    ["audio", "library", "paste", "upload"].forEach(s => {
      document.getElementById(`source-${s}`).hidden = s !== tab.dataset.source;
    });
  });
});

async function loadLibrary(query) {
  const url = query ? `/api/library?q=${encodeURIComponent(query)}` : "/api/library";
  const items = await api(url);
  if (!query) libraryCache = items;
  const el = document.getElementById("library-results");
  el.innerHTML = items.map(i => `
    <div class="library-item">
      <div>
        <div class="complaint">${escapeHTML(i.presenting_complaint)}</div>
        <div class="segcount">${i.visit_id} &middot; ${i.segment_count} utterances</div>
      </div>
      <button class="btn btn-secondary btn-sm" data-filename="${escapeAttr(i.filename)}" data-complaint="${escapeAttr(i.presenting_complaint)}">Use this case</button>
    </div>`).join("");
  el.querySelectorAll("button[data-filename]").forEach(btn => {
    btn.addEventListener("click", () => runFromLibrary(btn.dataset.filename, btn));
  });
}

document.getElementById("library-search").addEventListener("input", (e) => loadLibrary(e.target.value.trim() || undefined));

async function runFromLibrary(filename, button) {
  const form = new FormData();
  form.append("patient_id", currentPatientId);
  form.append("filename", filename);
  await runCase("/api/cases/from-library", form, button);
}

document.getElementById("paste-submit").addEventListener("click", async () => {
  clearCaseError();
  const title = document.getElementById("paste-title").value.trim();
  const text = document.getElementById("paste-text").value.trim();
  if (!title || !text) return showCaseError("Title and transcript text are both required.");
  const form = new FormData();
  form.append("patient_id", currentPatientId);
  form.append("title", title);
  form.append("text", text);
  await runCase("/api/cases/from-text", form, document.getElementById("paste-submit"));
});

document.getElementById("upload-submit").addEventListener("click", async () => {
  clearCaseError();
  const title = document.getElementById("upload-title").value.trim();
  const fileInput = document.getElementById("upload-file");
  if (!title || !fileInput.files.length) return showCaseError("Title and a file are both required.");
  const form = new FormData();
  form.append("patient_id", currentPatientId);
  form.append("title", title);
  form.append("file", fileInput.files[0]);
  await runCase("/api/cases/from-upload", form, document.getElementById("upload-submit"));
});

const LLM_NAMES = { gemini: "Gemini", claude: "Claude" };

async function loadLlmStatus() {
  try {
    const { provider } = await api("/api/llm-status");
    if (!provider) return;
    document.getElementById("llm-provider-name").textContent = LLM_NAMES[provider] || provider;
    document.getElementById("llm-toggle").hidden = false;
  } catch (_) { /* toggle stays hidden */ }
}

function useLlm() {
  const box = document.getElementById("use-llm");
  return !document.getElementById("llm-toggle").hidden && box.checked ? "true" : "false";
}

// --- pipeline jobs ---
// Every new case runs server-side as a job; we poll it and show each stage live.
let pipelineInfo = null;

const STAGE_INFO = {
  transcribing: { label: "Transcribe audio", detail: () => `${pipelineInfo?.asr_model ?? "Whisper"} · word-level confidence, medical-term biasing` },
  attributing_speakers: { label: "Attribute speakers", detail: () => `${LLM_NAMES[pipelineInfo?.llm_provider] ?? "LLM"} labels doctor / patient turns` },
  extracting: { label: "Extract clinical facts", detail: (job) => job.use_llm ? `${LLM_NAMES[pipelineInfo?.llm_provider] ?? "LLM"} (${pipelineInfo?.llm_model ?? ""}) · cited, quoted evidence` : "Rule-based extractor · verbatim segments" },
  grounding: { label: "Gates 1–2: acoustic + entailment", detail: () => `Quote check · ASR word confidence · NLI (${(pipelineInfo?.nli_model ?? "").split("/").pop()})` },
  plausibility: { label: "Gate 3: clinical plausibility", detail: () => "Allergy · indication · contraindication · interaction · stewardship" },
  done: { label: "Structured note ready", detail: () => "Opening case…" },
};

async function loadPipelineInfo() {
  try {
    pipelineInfo = await api("/api/pipeline-info");
    document.getElementById("asr-hint").textContent =
      `Transcribed locally with ${pipelineInfo.asr_model}; audio never leaves this machine. Long recordings take a few minutes on CPU.`;
  } catch (_) { /* hint keeps its default text */ }
}

function renderPipeline(job, startedAt) {
  const steps = job.stages;
  const current = steps.indexOf(job.stage);
  document.getElementById("pipeline-steps").innerHTML = steps.map((s, i) => {
    const info = STAGE_INFO[s] || { label: s, detail: () => "" };
    const state = job.status === "done" || i < current ? "done"
      : i === current ? (job.status === "error" ? "failed" : "active") : "waiting";
    const pct = state === "active" && job.progress != null ? ` · ${Math.round(job.progress * 100)}%` : "";
    const bar = state === "active" && job.progress != null
      ? `<div class="step-bar"><div style="width:${(job.progress * 100).toFixed(1)}%"></div></div>` : "";
    return `<li class="step step-${state}">
        <span class="step-dot"></span>
        <div><div class="step-label">${info.label}${pct}</div>
        <div class="step-detail">${escapeHTML(info.detail(job))}</div>${bar}</div>
      </li>`;
  }).join("");
  const secs = Math.round((Date.now() - startedAt) / 1000);
  document.getElementById("pipeline-elapsed").textContent = `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")} elapsed`;
}

async function runCase(url, form, button) {
  clearCaseError();
  const llm = useLlm();
  form.append("use_llm", llm);
  const label = button ? button.textContent : null;
  const reset = () => { if (button) { button.disabled = false; button.textContent = label; } };
  if (button) { button.disabled = true; button.textContent = "Starting…"; }

  let jobId;
  try {
    ({ job_id: jobId } = await api(url, { method: "POST", body: form }));
  } catch (err) { showCaseError(err.message); reset(); return; }

  const panel = document.getElementById("pipeline-panel");
  const errEl = document.getElementById("pipeline-error");
  document.getElementById("new-case-panel").hidden = true;
  document.getElementById("pipeline-title").textContent = "Running pipeline";
  errEl.hidden = true;
  panel.hidden = false;
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  const startedAt = Date.now();

  while (true) {
    let job;
    try { job = await api(`/api/jobs/${jobId}`); }
    catch (err) { errEl.textContent = err.message; errEl.hidden = false; reset(); return; }
    job.use_llm = llm === "true";
    renderPipeline(job, startedAt);
    if (job.status === "done") { location.href = `case.html?id=${job.case_id}`; return; }
    if (job.status === "error") {
      document.getElementById("pipeline-title").textContent = "Pipeline stopped";
      errEl.textContent = job.error; errEl.hidden = false;
      document.getElementById("new-case-panel").hidden = false;
      reset();
      return;
    }
    await new Promise(r => setTimeout(r, 1000));
  }
}

// --- audio source ---
document.querySelectorAll('input[name="audio-mode"]').forEach(r => r.addEventListener("change", () => {
  const mixed = document.querySelector('input[name="audio-mode"]:checked').value === "mixed";
  document.getElementById("audio-separate-inputs").hidden = mixed;
  document.getElementById("audio-mixed-inputs").hidden = !mixed;
}));

document.getElementById("audio-submit").addEventListener("click", async () => {
  clearCaseError();
  const title = document.getElementById("audio-title").value.trim();
  const mode = document.querySelector('input[name="audio-mode"]:checked').value;
  if (!title) return showCaseError("A case title is required.");
  const form = new FormData();
  form.append("patient_id", currentPatientId);
  form.append("title", title);
  form.append("mode", mode);
  if (mode === "separate") {
    const d = document.getElementById("doctor-audio").files[0];
    const p = document.getElementById("patient-audio").files[0];
    if (!d || !p) return showCaseError("Choose both the doctor and the patient recording.");
    form.append("doctor_audio", d);
    form.append("patient_audio", p);
  } else {
    const m = document.getElementById("mixed-audio").files[0];
    if (!m) return showCaseError("Choose the consultation recording.");
    if (!pipelineInfo?.llm_provider) return showCaseError("A mixed recording needs an LLM for speaker attribution; none is configured.");
    form.append("mixed_audio", m);
  }
  await runCase("/api/cases/from-audio", form, document.getElementById("audio-submit"));
});

function showCaseError(msg) {
  const el = document.getElementById("new-case-error");
  el.textContent = msg; el.hidden = false;
}
function clearCaseError() {
  document.getElementById("new-case-error").hidden = true;
}

init();
