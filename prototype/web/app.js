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
    ["library", "paste", "upload"].forEach(s => {
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
    btn.addEventListener("click", () => runFromLibrary(btn.dataset.filename, btn.dataset.complaint));
  });
}

document.getElementById("library-search").addEventListener("input", (e) => loadLibrary(e.target.value.trim() || undefined));

async function runFromLibrary(filename, title) {
  clearCaseError();
  try {
    const form = new FormData();
    form.append("patient_id", currentPatientId);
    form.append("filename", filename);
    const result = await api("/api/cases/from-library", { method: "POST", body: form });
    location.href = `case.html?id=${result.case_id}`;
  } catch (err) { showCaseError(err.message); }
}

document.getElementById("paste-submit").addEventListener("click", async () => {
  clearCaseError();
  const title = document.getElementById("paste-title").value.trim();
  const text = document.getElementById("paste-text").value.trim();
  if (!title || !text) return showCaseError("Title and transcript text are both required.");
  try {
    const form = new FormData();
    form.append("patient_id", currentPatientId);
    form.append("title", title);
    form.append("text", text);
    const result = await api("/api/cases/from-text", { method: "POST", body: form });
    location.href = `case.html?id=${result.case_id}`;
  } catch (err) { showCaseError(err.message); }
});

document.getElementById("upload-submit").addEventListener("click", async () => {
  clearCaseError();
  const title = document.getElementById("upload-title").value.trim();
  const fileInput = document.getElementById("upload-file");
  if (!title || !fileInput.files.length) return showCaseError("Title and a file are both required.");
  try {
    const form = new FormData();
    form.append("patient_id", currentPatientId);
    form.append("title", title);
    form.append("file", fileInput.files[0]);
    const result = await api("/api/cases/from-upload", { method: "POST", body: form });
    location.href = `case.html?id=${result.case_id}`;
  } catch (err) { showCaseError(err.message); }
});

function showCaseError(msg) {
  const el = document.getElementById("new-case-error");
  el.textContent = msg; el.hidden = false;
}
function clearCaseError() {
  document.getElementById("new-case-error").hidden = true;
}

init();
