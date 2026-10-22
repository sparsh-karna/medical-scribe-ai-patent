// Builds the Review 1 + Review 2 presentation for the confidence-gated clinical documentation project.
// Run from E:/deckbuild (where pptxgenjs is installed):  node C:/Users/user/medical-scribe-ai-patent/patent/build_deck.js
// Every number on the slides comes from a real run of the prototype (see patent disclosure, section 15).
// Text in RED is a placeholder the team must fill in.

const path = require("path");
const pptxgen = require(require.resolve("pptxgenjs", { paths: ["E:/deckbuild/node_modules"] }));

const HERE = __dirname;
const FIG = path.join(HERE, "figures", "labeled");
const OUT = path.join(HERE, "Confidence_Gated_Clinical_Documentation_Review1_Review2.pptx");

// ---- palette: deep clinical slate + mint, with traffic-light gate colours ----
const C = {
  ink: "0F2A36",      // dominant dark (titles, dark slides)
  body: "27363D",
  muted: "5E6E75",
  mint: "E3F1EE",     // card tint
  mintDeep: "2A7F6F", // secondary
  line: "C9D8D5",
  verified: "1E8A4C",
  review: "C98311",
  blocked: "D1432B",  // sharp accent
  white: "FFFFFF",
  red: "C00000",      // placeholders
};
const HF = "Cambria";   // headers
const BF = "Calibri";   // body

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5 in
pres.title = "Confidence-Gated AI Clinical Documentation";
const W = 13.333;

let slideNo = 0;

function base(section, title, sources) {
  const s = pres.addSlide();
  slideNo += 1;
  s.background = { color: C.white };
  if (section) s.addText(section.toUpperCase(), { x: 0.6, y: 0.32, w: 9, h: 0.3, fontFace: BF, fontSize: 11, bold: true, color: C.mintDeep, charSpacing: 2, margin: 0, isTextBox: true });
  if (title) s.addText(title, { x: 0.6, y: 0.62, w: 12.1, h: 0.75, fontFace: HF, fontSize: 30, bold: true, color: C.ink, margin: 0, valign: "top", isTextBox: true });
  if (sources) s.addText("Sources: " + sources, { x: 0.6, y: 7.02, w: 11.2, h: 0.32, fontFace: BF, fontSize: 9, color: C.muted, margin: 0, valign: "middle", isTextBox: true });
  s.addText(String(slideNo), { x: 12.2, y: 7.02, w: 0.55, h: 0.32, fontFace: BF, fontSize: 9, color: C.muted, align: "right", margin: 0, isTextBox: true });
  return s;
}

function card(s, x, y, w, h, fill = C.mint) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { color: fill }, rectRadius: 0.08 });
}

function text(s, t, x, y, w, h, o = {}) {
  s.addText(t, Object.assign({ x, y, w, h, fontFace: BF, fontSize: 15, color: C.body, margin: 0, valign: "top", isTextBox: true }, o));
}

function bullets(s, items, x, y, w, h, size = 15) {
  const arr = items.map((it, i) => {
    const runs = Array.isArray(it) ? it : [{ text: it }];
    return runs.map((r, j) => Object.assign({}, r, {
      options: Object.assign({ fontFace: BF, fontSize: size, color: C.body },
        j === 0 ? { bullet: { indent: 16 }, paraSpaceAfter: 6 } : {},
        r.options || {},
        j === runs.length - 1 && i < items.length - 1 ? { breakLine: true } : {}),
    }));
  }).flat();
  s.addText(arr, { x, y, w, h, margin: 0, valign: "top", isTextBox: true });
}

const b = (t) => ({ text: t, options: { bold: true } });
const n = (t) => ({ text: t });
const red = (t) => ({ text: t, options: { color: C.red, bold: true } });

function circleNum(s, x, y, d, label, fill, color = C.white, size = 14) {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill } });
  s.addText(label, { x, y, w: d, h: d, align: "center", valign: "middle", fontFace: BF, fontSize: size, bold: true, color, margin: 0, isTextBox: true });
}

// "you are here" tracker shown on every pipeline-step slide (the deck's motif)
const STEPS = ["Audio + ASR", "Speakers", "Extract", "Gate 0", "Gate 1", "Gate 2", "Combine", "Gate 3", "Review", "Calibrate", "Audit"];
function tracker(s, active) {
  const x0 = 0.6, gap = (W - 1.2) / STEPS.length;
  STEPS.forEach((name, i) => {
    const on = i === active, done = i < active;
    const cx = x0 + i * gap;
    s.addShape(pres.shapes.OVAL, { x: cx + gap / 2 - 0.13, y: 6.36, w: 0.26, h: 0.26,
      fill: { color: on ? C.blocked : done ? C.mintDeep : C.white }, line: { color: on ? C.blocked : C.mintDeep, width: 1 } });
    s.addText(name, { x: cx, y: 6.64, w: gap, h: 0.26, align: "center", fontFace: BF, fontSize: 9.5, bold: on,
      color: on ? C.blocked : C.muted, margin: 0, isTextBox: true });
  });
}

function stepHeader(s, num, title, active) {
  circleNum(s, 0.6, 0.62, 0.62, String(num), C.blocked, C.white, 20);
  s.addText(title, { x: 1.4, y: 0.62, w: 11.3, h: 0.66, fontFace: HF, fontSize: 28, bold: true, color: C.ink, margin: 0, valign: "middle", isTextBox: true });
  tracker(s, active);
}

function stat(s, x, y, w, value, label, color = C.ink) {
  text(s, value, x, y, w, 0.8, { fontFace: HF, fontSize: 40, bold: true, color });
  text(s, label, x, y + 0.82, w, 0.6, { fontSize: 12.5, color: C.muted });
}

function table(s, rows, x, y, w, colW, opts = {}) {
  const fs = opts.fontSize || 12;
  const data = rows.map((r, i) => r.map((cell) => {
    const o = { fontFace: BF, fontSize: fs, color: C.body, valign: "middle", margin: [0.05, 0.08, 0.05, 0.08] };
    if (i === 0) Object.assign(o, { bold: true, color: C.white, fill: { color: C.ink } });
    else if (i % 2 === 0) Object.assign(o, { fill: { color: "F4F8F7" } });
    if (typeof cell === "object") return { text: cell.text, options: Object.assign(o, cell.options || {}) };
    return { text: cell, options: o };
  }));
  s.addTable(data, { x, y, w, colW, border: { type: "solid", pt: 0.5, color: C.line }, rowH: opts.rowH || 0.36, autoPage: false });
}

function darkSlide(kicker, title, sub) {
  const s = pres.addSlide();
  slideNo += 1;
  s.background = { color: C.ink };
  text(s, kicker.toUpperCase(), 0.8, 2.3, 11, 0.4, { fontSize: 14, bold: true, color: "8FD3C3", charSpacing: 3 });
  text(s, title, 0.8, 2.75, 11.5, 1.5, { fontFace: HF, fontSize: 40, bold: true, color: C.white });
  if (sub) text(s, sub, 0.8, 4.3, 11, 1.0, { fontSize: 18, color: "C8DAD6" });
  return s;
}

// ============================================================ REVIEW 1

// 1 Title
{
  const s = pres.addSlide();
  slideNo += 1;
  s.background = { color: C.ink };
  text(s, "REVIEW 1 & REVIEW 2", 0.8, 0.8, 8, 0.4, { fontSize: 13, bold: true, color: "8FD3C3", charSpacing: 3 });
  text(s, "Confidence-Gated AI Clinical Documentation", 0.8, 1.35, 11.5, 1.0, { fontFace: HF, fontSize: 40, bold: true, color: C.white });
  text(s, "Hard-blocking unverified AI-drafted facts from the medical record using acoustic, entailment and clinical-plausibility signals, with adaptive per-clinician thresholds and an append-only audit trail",
    0.8, 2.45, 11.2, 1.1, { fontSize: 18, color: "C8DAD6" });
  // three gate lights: the visual identity of the deck
  [["Verified", C.verified], ["Needs review", C.review], ["Blocked", C.blocked]].forEach(([l, col], i) => {
    s.addShape(pres.shapes.OVAL, { x: 0.8 + i * 2.1, y: 3.95, w: 0.34, h: 0.34, fill: { color: col }, line: { color: col } });
    text(s, l, 1.25 + i * 2.1, 3.97, 1.7, 0.32, { fontSize: 13, color: C.white });
  });
  s.addText([
    { text: "Team: ", options: { bold: true, color: C.white } },
    { text: "[Name, Reg. No.]  ·  [Name, Reg. No.]  ·  [Name, Reg. No.]", options: { color: "FF7B7B", bold: true } },
  ], { x: 0.8, y: 5.2, w: 11.5, h: 0.4, fontFace: BF, fontSize: 15, margin: 0, isTextBox: true });
  s.addText([
    { text: "Guide: ", options: { bold: true, color: C.white } },
    { text: "[Faculty name]", options: { color: "FF7B7B", bold: true } },
    { text: "     Course / School: ", options: { bold: true, color: C.white } },
    { text: "[Course code, School]", options: { color: "FF7B7B", bold: true } },
  ], { x: 0.8, y: 5.65, w: 11.5, h: 0.4, fontFace: BF, fontSize: 15, margin: 0, isTextBox: true });
  s.addNotes("Title slide. Red text = placeholders to fill in before presenting.");
}

// 2 Keywords + abstract
{
  const s = base("Review 1 · Title, keywords and abstract", "Keywords and abstract", null);
  card(s, 0.6, 1.55, 3.9, 5.1);
  text(s, "Keywords", 0.85, 1.75, 3.4, 0.4, { fontFace: HF, fontSize: 18, bold: true, color: C.ink });
  bullets(s, ["Ambient clinical documentation", "AI medical scribe", "Speech recognition confidence", "Natural language inference (NLI)",
    "Hallucination detection", "Evidence-grounded generation", "Clinical decision support", "Human-in-the-loop review", "Adaptive thresholds", "Audit trail / provenance"],
    0.85, 2.25, 3.5, 4.3, 13.5);
  text(s, "Abstract", 4.9, 1.6, 7.8, 0.4, { fontFace: HF, fontSize: 18, bold: true, color: C.ink });
  text(s, [
    n("AI scribes transcribe a consultation and let a language model draft the note, but misheard words, invented details and unsafe instructions reach the draft, and current products only "),
    b("show"), n(" the clinician where each sentence came from. We propose a gate that "), b("enforces"), n(" evidence: every drafted fact must cite transcript segments and quote them verbatim, and is auto-inserted only if (0) the quote really occurs in the cited segment, (1) the speech recogniser was confident about exactly those words, (2) an NLI model finds the evidence entails, and does not contradict, the fact, and (3) it does not conflict clinically with the rest of the encounter. Failing facts are hard-blocked to a review queue with one-click audio replay; clinician decisions adapt per-field thresholds; every decision is logged append-only. On real PriMock57 consultation audio the prototype auto-verified 23 of 26 drafted facts, held a fact corrupted by a real ASR error for review, and measured 17.5 % WER for the local recogniser."),
  ], 4.9, 2.1, 7.85, 4.6, { fontSize: 14.5, paraSpaceAfter: 4 });
  s.addNotes("Keywords map to the search terms in the patent disclosure. Numbers in the abstract are from our own runs on PriMock57 day1_consultation01.");
}

// 3 Introduction
{
  const s = base("Review 1 · Introduction", "Introduction: AI scribes are arriving fast", "[9] AWS HealthScribe docs; [10] Abridge Linked Evidence; [15] Astute Analytica; [16] Towards Healthcare");
  bullets(s, [
    [b("Ambient AI scribes "), n("record the doctor-patient conversation, transcribe it (ASR) and have a large language model draft the clinical note (chief complaint, history, medications, assessment, plan).")],
    [b("Deployed products: "), n("Nuance/Microsoft DAX Copilot, Abridge, Suki, AWS HealthScribe, Augnito.")],
    [b("Trust mechanism today = evidence linking. "), n("AWS HealthScribe attaches transcript segment ids to every summary sentence [9]; Abridge lets the clinician highlight note text and replay the source audio [10].")],
    [b("But the clinician must still verify every line. "), n("Linking helps a human check; it does not stop an unsupported sentence from entering the record.")],
  ], 0.6, 1.6, 7.3, 4.6, 15);
  card(s, 8.4, 1.6, 4.3, 4.6);
  text(s, "Market (analyst estimates)", 8.65, 1.8, 3.9, 0.4, { fontSize: 13, bold: true, color: C.mintDeep });
  stat(s, 8.65, 2.25, 3.9, "USD 1.2-1.4 bn", "AI scribe / clinical documentation market, 2025 [15][16]");
  stat(s, 8.65, 3.75, 3.9, "20-29 % CAGR", "projected to 2035; estimates vary by source [15][16]", C.mintDeep);
  text(s, "Figures are third-party projections, not our measurements.", 8.65, 5.35, 3.9, 0.6, { fontSize: 11, italic: true, color: C.muted });
  s.addNotes("Market figures: Astute Analytica USD 1.2bn (2025) to 15.1bn (2035), 28.8% CAGR; Towards Healthcare USD 1.39bn to 8.93bn, 20.48% CAGR.");
}

// 4 Problem statement
{
  const s = base("Review 1 · Problem statement", "Three kinds of error reach the AI-drafted note", "Examples 1 and 2 from our own run on PriMock57 day1_consultation01 audio [1]; example 3 from the synthetic gate-demo transcript");
  const cols = [
    ["1  Misheard", C.review, "Speech recognition error", "Doctor said \"take some time off work\"; the recogniser wrote \"take some type of work\". \"Stool\" became \"stall\" / \"stalk\"."],
    ["2  Invented", C.blocked, "LLM hallucination / mis-citation", "A duration, dose or symptom that was never said, e.g. \"diarrhoea for three weeks\" when the patient said three days."],
    ["3  Unsafe", C.ink, "Faithful but clinically wrong", "\"Start amoxicillin\" for a patient who just said they are allergic to penicillin: perfectly transcribed, still unsafe."],
  ];
  cols.forEach(([h, col, sub, body], i) => {
    const x = 0.6 + i * 4.1;
    card(s, x, 1.6, 3.8, 3.35);
    circleNum(s, x + 0.25, 1.8, 0.5, String(i + 1), col, C.white, 16);
    text(s, h.slice(3), x + 0.9, 1.84, 2.7, 0.45, { fontFace: HF, fontSize: 20, bold: true, color: C.ink });
    text(s, sub, x + 0.25, 2.45, 3.3, 0.35, { fontSize: 13, bold: true, color: col });
    text(s, body, x + 0.25, 2.85, 3.35, 2.0, { fontSize: 14 });
  });
  card(s, 0.6, 5.2, 12.1, 1.05, "FBEAE7");
  text(s, [b("Problem statement: "), n("existing AI scribes insert every drafted statement into the note and rely on a busy clinician to find these errors. There is no automatic, per-fact mechanism that verifies each statement against its own evidence and blocks it from the record when the evidence is weak, contradicts it, or it is clinically unsafe.")],
    0.85, 5.3, 11.6, 0.9, { fontSize: 14.5 });
  s.addNotes("Emphasise example 1 is a real ASR error from our own pipeline, not a hypothetical.");
}

// 5 Objectives and scope
{
  const s = base("Review 1 · Objectives and scope", "Objectives and scope of the work", null);
  text(s, "Objectives", 0.6, 1.55, 6, 0.4, { fontFace: HF, fontSize: 19, bold: true, color: C.ink });
  const objs = ["Draft structured clinical facts from consultation audio, each with cited, verbatim evidence.",
    "Verify every fact with independent signals: citation integrity, ASR confidence, NLI entailment, clinical plausibility.",
    "Hard-block failing facts from the note and route them to a clinician review queue with audio replay.",
    "Adapt the auto-insert threshold per clinician and per field from approve / reject decisions.",
    "Record every automatic and human decision in an append-only audit log.",
    "Validate on real, external consultation data (PriMock57)."];
  objs.forEach((o, i) => {
    circleNum(s, 0.6, 2.05 + i * 0.66, 0.4, String(i + 1), C.mintDeep, C.white, 12);
    text(s, o, 1.15, 2.07 + i * 0.66, 6.1, 0.6, { fontSize: 14 });
  });
  card(s, 7.7, 1.55, 5.0, 2.35);
  text(s, "In scope", 7.95, 1.7, 4.5, 0.35, { fontSize: 15, bold: true, color: C.verified });
  bullets(s, ["Outpatient consultations in English", "Local, on-premise ASR and verification", "Prototype web app for clinicians", "7 note fields: complaint, history, meds, allergies, vitals, assessment, plan"], 7.95, 2.1, 4.6, 1.8, 13);
  card(s, 7.7, 4.1, 5.0, 2.1, "F4F4F4");
  text(s, "Out of scope", 7.95, 4.25, 4.5, 0.35, { fontSize: 15, bold: true, color: C.blocked });
  bullets(s, ["Training or improving the speech recogniser", "A full clinical knowledge base (RxNorm / DrugBank)", "EHR integration, clinical deployment, user study"], 7.95, 4.65, 4.6, 1.5, 13);
}

// 6 Literature review
{
  const s = base("Review 1 · Literature review / related work", "Related work: products, patents and research", "[6] SummaC; [7] FactCC; [8] ACI-BENCH; [9] AWS HealthScribe; [10] Abridge; [11] US11222716B2; [12] US10719222B2; [13] US11227688B2; [14] US6006183A");
  table(s, [
    ["Work", "What it does", "Limitation for our problem"],
    ["AWS HealthScribe [9]", "Transcript + summary; every sentence carries EvidenceLinks to transcript segments", "Links are for human validation; nothing is blocked"],
    ["Abridge Linked Evidence [10]", "Highlight note text to see source transcript and replay audio", "Optional convenience; relies on clinician checking"],
    ["US 11,222,716 B2 - Nuance/Microsoft [11]", "Links audio, transcript, report; confidence model shows a section only if editing beats rewriting", "Gates whole sections on editing effort, not each fact on its evidence"],
    ["US 10,719,222 / 11,227,688 B2 - Google [12][13]", "Transcript beside generated note; extracted phrases linked to audio", "Verification by physician inspection"],
    ["US 6,006,183 A - IBM [14]", "Colour-codes low-confidence ASR words above a threshold", "Word level only; not tied to note statements"],
    ["SummaC [6], FactCC [7]", "NLI / classifier scoring of summary factual consistency", "Offline evaluation metric, not an enforcing gate"],
    ["ACI-BENCH [8]", "Benchmark for visit-note generation from conversations", "Measures quality; no verification mechanism"],
  ], 0.6, 1.55, 12.1, [3.3, 4.6, 4.2], { fontSize: 11.5, rowH: 0.56 });
}

// 7 Gap analysis
{
  const s = base("Review 1 · Gap analysis", "Gap analysis: nobody enforces the evidence", "[9]-[14] as on previous slide; capability marks from each source's documentation / claims");
  const cols = ["Capability", "HealthScribe / Abridge", "US 11,222,716", "Google patents", "SummaC / FactCC", "Ours"];
  const Y = "Yes", N = "No", P = "Partial";
  const rows = [
    ["Note statement linked to transcript", Y, Y, Y, N, Y],
    ["ASR confidence used", N, N, P, N, Y],
    ["Checks the citation is correct (quote in segment)", N, N, N, N, Y],
    ["Semantic entailment / contradiction check", N, N, N, Y, Y],
    ["Blocks content from the record", N, P, N, N, Y],
    ["Decision per individual fact", N, N, N, Y, Y],
    ["Clinical-plausibility check on drafted text", N, N, N, N, Y],
    ["Thresholds adapt per clinician", N, N, N, N, Y],
    ["Per-line provenance audit log", P, N, N, N, Y],
  ];
  const col = (v) => ({ text: v, options: { color: v === Y ? C.verified : v === N ? C.blocked : C.review, bold: true, align: "center" } });
  table(s, [cols, ...rows.map((r) => [r[0], ...r.slice(1).map(col)])], 0.6, 1.55, 12.1, [4.1, 1.75, 1.55, 1.55, 1.6, 1.55], { fontSize: 12, rowH: 0.43 });
  text(s, "Partial: US 11,222,716 hides whole sections when predicted editing effort is high; Google patents show confidence indicators on transcript words; AWS returns links, not a decision log.", 0.6, 6.0, 12.1, 0.5, { fontSize: 11, italic: true, color: C.muted });
}

// 8 Proposed solution
{
  const s = base("Review 1 · Proposed solution", "Proposed solution: an evidence gate in front of the record", null);
  const boxes = [["Draft", "Each fact + cited segments + verbatim quotes", C.ink],
    ["Gate 0", "Quote really occurs in cited segment?", C.mintDeep], ["Gate 1", "ASR confident about the quoted words?", C.mintDeep],
    ["Gate 2", "Evidence entails, not contradicts?", C.mintDeep], ["Gate 3", "Clinically plausible with rest of visit?", C.mintDeep]];
  boxes.forEach(([h, d, col], i) => {
    const x = 0.6 + i * 2.5;
    card(s, x, 1.7, 2.2, 1.9, i === 0 ? "E8ECEE" : C.mint);
    text(s, h, x + 0.2, 1.85, 1.8, 0.45, { fontFace: HF, fontSize: 19, bold: true, color: col });
    text(s, d, x + 0.2, 2.35, 1.85, 1.2, { fontSize: 13 });
    if (i < boxes.length - 1) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + 2.23, y: 2.5, w: 0.24, h: 0.3, fill: { color: C.muted }, line: { color: C.muted } });
  });
  const outs = [["Verified", "auto-inserted into the note", C.verified], ["Needs review", "blocked, queued with reason + audio replay", C.review], ["Blocked", "rejected with logged reason", C.blocked]];
  outs.forEach(([h, d, col], i) => {
    const x = 0.6 + i * 4.1;
    s.addShape(pres.shapes.OVAL, { x, y: 4.1, w: 0.42, h: 0.42, fill: { color: col }, line: { color: col } });
    text(s, h, x + 0.6, 4.08, 3.3, 0.4, { fontSize: 17, bold: true, color: col });
    text(s, d, x + 0.6, 4.5, 3.3, 0.6, { fontSize: 13.5 });
  });
  card(s, 0.6, 5.35, 12.1, 0.95, "E8ECEE");
  text(s, [b("Plus: "), n("clinician decisions tune per-field thresholds for that clinician; every decision (machine or human) is appended to an audit log, so every line in the chart is traceable.")], 0.85, 5.5, 11.6, 0.7, { fontSize: 14.5 });
}

// 9 Novelty
{
  const s = base("Review 1 · Novelty", "What is new", "Closest prior art: US 11,222,716 B2 [11]; evidence linking: AWS HealthScribe [9], Abridge [10]; NLI consistency: SummaC [6]");
  const items = [
    ["Enforce, don't annotate", "Evidence decides whether each fact may enter the record, instead of being displayed for optional checking [9][10]."],
    ["Per-fact dual signal on the same evidence", "ASR confidence over exactly the quoted words + NLI entailment on the cited segments; contradiction is an absolute block."],
    ["Citation integrity first", "The model must quote verbatim; a quote not found in its segment is rejected before any scoring."],
    ["Third gate for faithful-but-unsafe", "Allergy class, indication, contraindication, interaction and stewardship checks across the encounter's own facts."],
    ["Learns per clinician", "Per-field thresholds adapt to each clinician's approve / reject decisions; safety floors never move."],
    ["No imputed signals", "Text input has no audio, so the acoustic signal is logged as unavailable rather than faked."],
  ];
  items.forEach(([h, d], i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.6 + col * 6.15, y = 1.6 + row * 1.5;
    card(s, x, y, 5.95, 1.3);
    circleNum(s, x + 0.2, y + 0.22, 0.45, String(i + 1), C.blocked, C.white, 14);
    text(s, h, x + 0.8, y + 0.18, 4.95, 0.4, { fontSize: 16, bold: true, color: C.ink });
    text(s, d, x + 0.8, y + 0.55, 4.95, 0.75, { fontSize: 12.5 });
  });
  text(s, "vs. US 11,222,716: that patent gates whole report sections on predicted editing effort; ours gates each fact on its own evidence.", 0.6, 6.15, 12.1, 0.4, { fontSize: 12, italic: true, color: C.mintDeep, bold: true });
}

// 10 References (Review 1)
function references(title) {
  const s = base(title, "References", null);
  const refs = [
    "[1] Papadopoulos Korfiatis A., Moramarco F., Sarac R., Savkov A. PriMock57: A Dataset of Primary Care Mock Consultations. ACL 2022. github.com/babylonhealth/primock57 (CC BY 4.0)",
    "[2] Radford A. et al. Robust Speech Recognition via Large-Scale Weak Supervision (Whisper). ICML 2023.",
    "[3] SYSTRAN. faster-whisper (CTranslate2 Whisper implementation). github.com/SYSTRAN/faster-whisper",
    "[4] He P., Gao J., Chen W. DeBERTaV3: Improving DeBERTa using ELECTRA-Style Pre-Training with Gradient-Disentangled Embedding Sharing. ICLR 2023.",
    "[5] Laurer M. DeBERTa-v3-base-mnli-fever-anli (model card). huggingface.co/MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli",
    "[6] Laban P., Schnabel T., Bennett P. N., Hearst M. A. SummaC: Re-Visiting NLI-based Models for Inconsistency Detection in Summarization. TACL 2022.",
    "[7] Kryscinski W., McCann B., Xiong C., Socher R. Evaluating the Factual Consistency of Abstractive Text Summarization. EMNLP 2020.",
    "[8] Yim W. et al. ACI-BENCH: a Novel Ambient Clinical Intelligence Dataset for Benchmarking Automatic Visit Note Generation. Scientific Data 2023.",
    "[9] AWS HealthScribe - Clinical documentation insights. docs.aws.amazon.com/transcribe/latest/dg/health-scribe-insights.html",
    "[10] Abridge - Verify a Note With Linked Evidence. support.abridge.com/hc/en-us/articles/30235128433811",
    "[11] US 11,222,716 B2. System and method for review of automated clinical documentation from recorded audio. Nuance / Microsoft, 2022.",
    "[12] US 10,719,222 B2. Method and system for generating transcripts of patient-healthcare provider conversations. Google, 2020.",
    "[13] US 11,227,688 B2. Interface for patient-provider conversation and auto-generation of note or summary. Google, 2022.",
    "[14] US 6,006,183 A. Speech recognition confidence level display. IBM, 1999.",
    "[15] Astute Analytica. AI Clinical Documentation (Ambient Scribe) Market report. astuteanalytica.com",
    "[16] Towards Healthcare. AI in Medical Scribing Market sizing. towardshealthcare.com",
    "[17] Google. Gemini API documentation (structured JSON output). ai.google.dev",
    "[18] RapidFuzz - fuzzy string matching library. github.com/rapidfuzz/RapidFuzz",
    "[19] British National Formulary (drug indications, contraindications, interactions). bnf.nice.org.uk",
  ];
  const half = Math.ceil(refs.length / 2);
  [refs.slice(0, half), refs.slice(half)].forEach((col, i) => {
    s.addText(col.map((r, j) => ({ text: r, options: { breakLine: j < col.length - 1, paraSpaceAfter: 5 } })),
      { x: 0.6 + i * 6.15, y: 1.5, w: 5.95, h: 5.4, fontFace: BF, fontSize: 10.5, color: C.body, margin: 0, valign: "top", isTextBox: true });
  });
  return s;
}
references("Review 1 · References");

// ============================================================ REVIEW 2
darkSlide("Review 2", "Methodology and system development", "Architecture · data · models · the pipeline step by step · algorithm · validation · preliminary results");

// Architecture
{
  const s = base("Review 2 · Proposed architecture", "Proposed architecture", "Figure generated from the prototype's module structure (prototype/src); ASR [2][3]; NLI [4][5]; LLM [17]");
  s.addImage({ path: path.join(FIG, "fig1_system.png"), x: 0.6, y: 1.45, w: 7.35, h: 5.3, sizing: { type: "contain", w: 7.35, h: 5.3 } });
  bullets(s, [
    [b("Capture + ASR (100-130): "), n("local Whisper, per-word probability, speaker roles")],
    [b("Extractor (140): "), n("rule-based or LLM; facts with citations + quotes")],
    [b("Gates 0-2 (150-180): "), n("quote check, acoustic, entailment, per-field threshold")],
    [b("Gate 3 (190): "), n("clinical plausibility")],
    [b("Outputs (200-230): "), n("note, review queue, calibration store, audit log")],
  ], 8.25, 1.6, 4.5, 4.9, 13.5);
}

// Environment setup
{
  const s = base("Review 2 · Environment setup", "Environment setup", "[2][3] Whisper / faster-whisper; [4][5] DeBERTa NLI; [17] Gemini API; [18] RapidFuzz");
  table(s, [
    ["Layer", "Technology", "Why"],
    ["Language / backend", "Python 3.13, FastAPI, Uvicorn", "async API, background pipeline jobs"],
    ["Speech recognition", "faster-whisper (Whisper base.en, int8, CPU) [2][3]", "local: audio never leaves the machine; word-level probabilities"],
    ["Entailment", "PyTorch 2.8 + Transformers; DeBERTa-v3 NLI [4][5]", "local P(entail / neutral / contradict)"],
    ["Quote alignment", "RapidFuzz partial-ratio alignment [18]", "fuzzy match quote inside segment"],
    ["Fact extraction", "Rule-based, or Gemini 3.6 Flash with JSON schema [17]; Claude optional", "structured, cited output"],
    ["Storage", "SQLite (users, patients, cases); JSON case files; JSONL audit log", "simple, inspectable"],
    ["Front end", "HTML / CSS / JavaScript", "upload, live progress, review, audio replay"],
  ], 0.6, 1.55, 8.1, [1.9, 3.4, 2.8], { fontSize: 11.5, rowH: 0.5 });
  card(s, 9.0, 1.55, 3.7, 4.55);
  text(s, "Test machine", 9.25, 1.72, 3.2, 0.4, { fontSize: 15, bold: true, color: C.mintDeep });
  stat(s, 9.25, 2.15, 3.2, "8-core CPU", "no GPU");
  stat(s, 9.25, 3.55, 3.2, "7.8 GB RAM", "Windows 11; models cached locally");
  text(s, "Everything runs on a student laptop.", 9.25, 5.25, 3.2, 0.6, { fontSize: 12.5, italic: true, color: C.muted });
}

// Dataset
{
  const s = base("Review 2 · Dataset collection", "Dataset: PriMock57 (real audio, real transcripts)", "[1] Papadopoulos Korfiatis et al., ACL 2022 - Babylon Health, CC BY 4.0; statistics computed by us from the released transcripts");
  text(s, "57 mock primary-care consultations recorded by Babylon Health: real clinicians, actors as patients, separate doctor and patient audio channels, human transcripts and reference clinical notes. We use it because it is real speech with ground truth, and freely licensed [1].",
    0.6, 1.55, 12.1, 0.9, { fontSize: 15 });
  const st = [["57", "consultations"], ["8.6 h", "total conversation time"], ["6,727", "human-transcribed utterances"], ["85,914", "words"], ["9.1 min", "mean length (3.8 - 14.3)"]];
  st.forEach(([v, l], i) => {
    const x = 0.6 + i * 2.45;
    card(s, x, 2.7, 2.25, 1.8);
    stat(s, x + 0.2, 2.85, 1.95, v, l, i === 0 ? C.blocked : C.ink);
  });
  table(s, [
    ["Per consultation we use", "Format", "Used for"],
    ["Doctor + patient audio", "16 kHz mono WAV, one speaker per channel", "ASR input, acoustic signal, speaker roles"],
    ["Human transcript", "TextGrid (converted to JSON segments)", "text-input pipeline; WER reference"],
    ["Reference clinical note", "text", "future: fact-level accuracy of drafts"],
  ], 0.6, 4.75, 12.1, [3.2, 4.4, 4.5], { fontSize: 12, rowH: 0.38 });
}

// Preprocessing
{
  const s = base("Review 2 · Preprocessing", "Preprocessing", "[1] PriMock57 format; [2][3] Whisper / faster-whisper VAD and word timestamps; medical-term list: prototype/src/medical_terms.py");
  const steps = [
    ["Transcripts", "PriMock57 TextGrid files converted to JSON segments {id, start, end, speaker, text}; 57 cases indexed by presenting complaint."],
    ["Audio decoding", "16 kHz mono PCM; voice-activity detection skips silence while the other party speaks."],
    ["Utterance segmentation", "Whisper segments re-split at pauses >= 0.8 s using word timestamps, so doctor/patient turns interleave correctly."],
    ["Word features", "each word keeps probability, start/end time and character offsets in the segment text (needed to score quoted spans)."],
    ["Medical vocabulary", "decoding biased with a drug/symptom prompt; only words with ASR probability < 0.70 are fuzzy-corrected, original word kept."],
    ["WER normalisation", "lower-case, strip punctuation, drop fillers (um, uh, erm), unify UK/US spelling before comparing."],
  ];
  steps.forEach(([h, d], i) => {
    const y = 1.55 + i * 0.83;
    circleNum(s, 0.6, y + 0.05, 0.45, String(i + 1), C.mintDeep, C.white, 13);
    text(s, h, 1.25, y + 0.02, 2.6, 0.5, { fontSize: 15, bold: true, color: C.ink });
    text(s, d, 3.9, y + 0.02, 8.8, 0.75, { fontSize: 13.5 });
  });
}

// Data division and augmentation
{
  const s = base("Review 2 · Data division and augmentation", "Data division and augmentation", "[1] PriMock57; [2][4][5] pretrained models used as released");
  card(s, 0.6, 1.55, 5.9, 4.6);
  text(s, "No model is trained", 0.85, 1.72, 5.4, 0.45, { fontFace: HF, fontSize: 19, bold: true, color: C.ink });
  text(s, "Whisper, the DeBERTa NLI model and Gemini are used exactly as released [2][4][5][17]. The contribution is the verification method, so there is no training set and no train / test split for model weights.",
    0.85, 2.2, 5.4, 1.6, { fontSize: 14 });
  text(s, "What the data is used for today", 0.85, 3.8, 5.4, 0.4, { fontSize: 14, bold: true, color: C.mintDeep });
  bullets(s, ["1 consultation end to end from audio (both channels)", "57 human transcripts for text-input runs", "Synthetic transcripts only for unsafe-prescription tests"], 0.85, 4.2, 5.4, 1.8, 13.5);
  card(s, 6.8, 1.55, 5.9, 4.6, "F4F4F4");
  s.addText([{ text: "PLANNED, not yet done", options: { color: C.red, bold: true } }], { x: 7.05, y: 1.72, w: 5.4, h: 0.4, fontFace: BF, fontSize: 13, margin: 0, isTextBox: true });
  text(s, "Division for tuning the gate", 7.05, 2.1, 5.4, 0.45, { fontFace: HF, fontSize: 19, bold: true, color: C.ink });
  bullets(s, ["Split the 57 consultations by consultation (not by utterance) into a development set for tuning thresholds / weights and a held-out test set.",
    "Label each drafted fact correct / incorrect against the transcript and reference note to measure the gate."], 7.05, 2.6, 5.4, 1.8, 13.5);
  text(s, "Augmentation (stress tests)", 7.05, 4.4, 5.4, 0.4, { fontSize: 14, bold: true, color: C.mintDeep });
  bullets(s, ["Add background noise / change speed to the audio to test that the acoustic gate reacts to degraded speech."], 7.05, 4.8, 5.4, 1.2, 13.5);
}

// Models
{
  const s = base("Review 2 · Machine learning / deep learning models", "Models used (all pretrained, none fine-tuned)", "[2] Whisper; [3] faster-whisper; [4] DeBERTaV3; [5] NLI model card; [17] Gemini API; parameter counts from the model papers / cards");
  const m = [
    ["Whisper base.en", "Speech recognition", "Transformer encoder-decoder, ~74 M parameters, trained on 680k h of weakly supervised audio [2]; run int8 on CPU via faster-whisper [3].", "per-word probability = acoustic signal"],
    ["DeBERTa-v3-base NLI", "Entailment", "DeBERTaV3 encoder [4] fine-tuned by its authors on MNLI, FEVER-NLI, ANLI [5]; ~184 M parameters. Cross-encodes (evidence, statement).", "P(entailment), P(contradiction) = semantic signal"],
    ["Gemini 3.6 Flash", "Fact extraction; speaker roles for mixed audio", "Hosted LLM, prompted to return facts with citations and verbatim quotes under a JSON schema [17]. Optional; a rule-based extractor also works.", "drafts; never trusted without the gate"],
  ];
  m.forEach(([name, role, d, out], i) => {
    const x = 0.6 + i * 4.1;
    card(s, x, 1.55, 3.8, 4.7);
    text(s, name, x + 0.25, 1.72, 3.3, 0.45, { fontFace: HF, fontSize: 19, bold: true, color: C.ink });
    text(s, role, x + 0.25, 2.2, 3.3, 0.4, { fontSize: 13, bold: true, color: C.mintDeep });
    text(s, d, x + 0.25, 2.65, 3.3, 2.3, { fontSize: 13 });
    text(s, [b("Output: "), n(out)], x + 0.25, 5.05, 3.3, 1.0, { fontSize: 12.5 });
  });
}

// ---- pipeline steps ----
{
  const s = base(null, null, "[2][3] Whisper / faster-whisper; WER computed by us against the PriMock57 human transcript [1]");
  stepHeader(s, 1, "Audio capture and speech recognition", 0);
  bullets(s, ["Upload doctor + patient recordings (or one mixed recording).", "Local faster-whisper transcribes each channel with voice-activity detection and word timestamps [3].",
    "Decoding is biased with a medical vocabulary prompt.", "Words scored < 0.70 that are near a known drug / symptom are corrected; original kept for audit.",
    "Output: utterances with per-word probability and character offsets."], 0.6, 1.6, 6.6, 4.5, 14.5);
  card(s, 7.6, 1.6, 5.1, 4.45);
  text(s, "Real run: day1_consultation01", 7.85, 1.75, 4.6, 0.4, { fontSize: 13.5, bold: true, color: C.mintDeep });
  stat(s, 7.85, 2.15, 2.2, "186", "utterances (2 x 7:38)");
  stat(s, 10.2, 2.15, 2.3, "17.5 %", "word error rate vs human transcript", C.blocked);
  stat(s, 7.85, 3.65, 2.2, "0.853", "mean word probability");
  stat(s, 10.2, 3.65, 2.3, "9.5 %", "words below 0.5 probability", C.review);
  text(s, "WER: 231 errors / 1,319 words (doctor 17.5 %, patient 17.6 %), fillers removed.", 7.85, 5.15, 4.6, 0.7, { fontSize: 11.5, italic: true, color: C.muted });
}
{
  const s = base(null, null, "[1] PriMock57 separate channels; [17] Gemini API for mixed recordings");
  stepHeader(s, 2, "Speaker roles", 1);
  card(s, 0.6, 1.6, 5.9, 4.4);
  text(s, "Separate channels (default)", 0.85, 1.78, 5.4, 0.45, { fontFace: HF, fontSize: 18, bold: true, color: C.ink });
  text(s, "Each recording holds one speaker, so every utterance from the doctor channel is DOCTOR and from the patient channel is PATIENT. Channels are merged in time order. This is exact, as in PriMock57 [1].", 0.85, 2.3, 5.4, 2.0, { fontSize: 14 });
  text(s, "Real run: 106 doctor + 82 patient utterances.", 0.85, 4.8, 5.4, 0.5, { fontSize: 13.5, bold: true, color: C.mintDeep });
  card(s, 6.8, 1.6, 5.9, 4.4, "F4F4F4");
  text(s, "Single mixed recording", 7.05, 1.78, 5.4, 0.45, { fontFace: HF, fontSize: 18, bold: true, color: C.ink });
  text(s, "No channel information, so an LLM labels each utterance DOCTOR / PATIENT / OTHER from what is said (questions vs. symptoms) [17]. Roles are marked \"inferred\" in the note's provenance.", 7.05, 2.3, 5.4, 1.8, { fontSize: 14 });
  text(s, "Tested up to attribution; extraction step not completed (API quota). Limitation: an utterance spanning a turn change gets one role.", 7.05, 4.5, 5.4, 1.2, { fontSize: 12.5, italic: true, color: C.blocked });
}
{
  const s = base(null, null, "[17] Gemini structured output; fact from our real run on PriMock57 audio [1], citations abridged (4 in the original)");
  stepHeader(s, 3, "Fact extraction with citations and verbatim quotes", 2);
  bullets(s, ["Extractor drafts facts in 7 fields: complaint, history, medications, allergies, vitals, assessment, plan.",
    "Each fact must cite the segment(s) it relies on and quote them character-for-character.",
    "Questions are cited with their answers (\"Do you smoke?\" + \"No\").",
    "Output is forced into a JSON schema [17], so it always parses.",
    "The extractor is untrusted: its citations and quotes are exactly what the gates check next."], 0.6, 1.6, 5.9, 4.6, 14.5);
  card(s, 6.8, 1.6, 5.9, 4.4, "1B2B33");
  s.addText([
    { text: "{", options: { breakLine: true } },
    { text: '  "field": "plan",', options: { breakLine: true } },
    { text: '  "value": "Take two to three days off', options: { breakLine: true } },
    { text: '            work to rest.",', options: { breakLine: true } },
    { text: '  "citations": [', options: { breakLine: true } },
    { text: '    {"segment_id": 154,', options: { breakLine: true } },
    { text: '     "quote": "some type of work."},', options: { breakLine: true } },
    { text: '    {"segment_id": 157,', options: { breakLine: true } },
    { text: '     "quote": "take some time off and rest."}', options: { breakLine: true } },
    { text: "  ]", options: { breakLine: true } },
    { text: "}" },
  ], { x: 7.05, y: 1.8, w: 5.4, h: 4.0, fontFace: "Courier New", fontSize: 13, color: "D7F0EA", margin: 0, valign: "top", isTextBox: true });
}
{
  const s = base(null, null, "[18] RapidFuzz partial-ratio alignment; example from our gate regression suite on real ASR output [1]");
  stepHeader(s, 4, "Gate 0: citation integrity", 3);
  text(s, "Before any scoring, every quote must actually occur in the segment it cites.", 0.6, 1.55, 12.1, 0.5, { fontSize: 16, bold: true, color: C.ink });
  bullets(s, ["Fuzzy-align the quote inside the segment text (RapidFuzz partial ratio [18]).", "Score >= 90 / 100 required for every quote.",
    "Otherwise: REJECTED as invented or mis-attributed evidence.", "The aligned character span is kept: it tells Gate 1 which words to score."], 0.6, 2.2, 5.9, 3.5, 14.5);
  card(s, 6.8, 2.2, 5.9, 3.8);
  text(s, "Segment #6 (patient, real ASR)", 7.05, 2.35, 5.4, 0.35, { fontSize: 12.5, bold: true, color: C.mintDeep });
  text(s, "\"I've just had some diarrhea for the last three days, and it's been affecting me...\"", 7.05, 2.7, 5.4, 0.8, { fontSize: 13, italic: true });
  text(s, [b("Quote: "), n("\"I've just had some diarrhea for the last three days\"")], 7.05, 3.55, 5.4, 0.6, { fontSize: 13 });
  text(s, "alignment 100 / 100  ->  continue", 7.05, 4.1, 5.4, 0.35, { fontSize: 13, bold: true, color: C.verified });
  text(s, [b("Quote: "), n("\"I take metformin 500 mg twice a day\"")], 7.05, 4.6, 5.4, 0.6, { fontSize: 13 });
  text(s, "alignment 46 / 100  ->  REJECTED", 7.05, 5.15, 5.4, 0.35, { fontSize: 13, bold: true, color: C.blocked });
}
{
  const s = base(null, null, "Word probabilities from faster-whisper [3]; example from our real run on PriMock57 day1_consultation01 [1]");
  stepHeader(s, 5, "Gate 1: acoustic confidence of the quoted words", 4);
  card(s, 0.6, 1.6, 5.9, 1.55, "E8ECEE");
  s.addText([
    { text: "A = (1 / |Q|)  Σ", options: { fontSize: 22 } }, { text: "w ∈ Q", options: { fontSize: 13, subscript: true } }, { text: "  p(w)", options: { fontSize: 22 } },
  ], { x: 0.85, y: 1.75, w: 5.4, h: 0.6, fontFace: "Cambria Math", color: C.ink, margin: 0, isTextBox: true });
  text(s, "Q = ASR words whose character span overlaps the aligned quotes; p(w) = Whisper's word probability.", 0.85, 2.4, 5.4, 0.7, { fontSize: 12.5, color: C.muted });
  bullets(s, ["A < 0.50 -> REJECTED, weakest words listed.", "Only the words the fact relies on count, not the whole transcript.",
    "Text input (no audio): A is recorded as unavailable, never invented."], 0.6, 3.4, 5.9, 2.6, 14);
  card(s, 6.8, 1.6, 5.9, 4.4);
  text(s, "Real Whisper word probabilities, segments #153-154", 7.05, 1.72, 5.4, 0.35, { fontSize: 12.5, bold: true, color: C.mintDeep });
  text(s, "Said: \"take some time off work\"   Heard: \"take some type of work\"", 7.05, 2.05, 5.4, 0.4, { fontSize: 12.5, italic: true });
  s.addChart(pres.charts.BAR, [{ name: "p(word)", labels: ["take", "some", "type", "of", "work."], values: [0.994, 0.994, 0.405, 0.997, 0.946] }], {
    x: 7.0, y: 2.45, w: 5.5, h: 2.5, barDir: "col", chartColors: [C.mintDeep], showValue: true, dataLabelPosition: "outEnd",
    dataLabelFontSize: 11, dataLabelFormatCode: "0.00", valAxisMinVal: 0, valAxisMaxVal: 1, valAxisLabelFontSize: 9, catAxisLabelFontSize: 12,
    catAxisLabelColor: C.body, valAxisLabelColor: C.muted, valGridLine: { color: "E3E8E7", size: 0.5 }, catGridLine: { style: "none" }, showLegend: false });
  text(s, "The misheard word is the least confident one. The fact's quoted span averaged A = 0.85, and its entailment fell to 0.43 (Gate 2), so it was held for review.", 7.05, 5.05, 5.4, 0.9, { fontSize: 12.5 });
}
{
  const s = base(null, null, "[4] DeBERTaV3; [5] NLI model card; [6] SummaC (NLI for consistency); probabilities measured by us with the model");
  stepHeader(s, 6, "Gate 2: semantic entailment (NLI)", 5);
  text(s, "Premise = cited segments (\"Doctor: ... Patient: ...\"); hypothesis = drafted fact. The NLI model [4][5] returns three probabilities.", 0.6, 1.55, 12.1, 0.6, { fontSize: 15 });
  table(s, [
    ["Premise (cited evidence)", "Drafted fact", "P(entail)", "P(contra)", "Decision"],
    ["Patient: I've just had some diarrhea for the last three days.", "Patient reports diarrhea for 3 days.", "0.997", "0.000", { text: "pass", options: { color: C.verified, bold: true } }],
    ["Doctor: Do you smoke? Patient: No, I don't.", "Denies smoking.", "0.994", "0.001", { text: "pass", options: { color: C.verified, bold: true } }],
    ["Patient: I have really bad chest pain.", "Denies chest pain.", "0.006", "0.990", { text: "REJECT", options: { color: C.blocked, bold: true } }],
    ["Doctor: I'll start you on metformin 500 mg twice a day.", "Metformin 1000 mg three times a day.", "0.000", "0.997", { text: "REJECT", options: { color: C.blocked, bold: true } }],
    ["Patient: I've been coughing for a week.", "Patient has a history of asthma.", "0.000", "0.001", { text: "REJECT", options: { color: C.blocked, bold: true } }],
  ], 0.6, 2.25, 12.1, [4.6, 3.6, 1.2, 1.2, 1.5], { fontSize: 12, rowH: 0.48 });
  text(s, "Rules: P(contradiction) >= 0.50 -> REJECTED;  P(entailment) < 0.30 -> REJECTED.  Replaced a word-overlap proxy that blocked correct paraphrases (0 of 21 passed).", 0.6, 5.35, 12.1, 0.7, { fontSize: 13, bold: true, color: C.ink });
}
{
  const s = base(null, null, "Parameters set by design (not yet tuned on data); values from prototype/src/grounding.py and calibration.py");
  stepHeader(s, 7, "Combining the signals against a per-field threshold", 6);
  card(s, 0.6, 1.6, 6.3, 1.5, "E8ECEE");
  s.addText([{ text: "S = 0.6 · E + 0.4 · A", options: { breakLine: true } }, { text: "S = E   (text input, no audio)", options: { fontSize: 16 } }],
    { x: 0.85, y: 1.72, w: 5.9, h: 1.3, fontFace: "Cambria Math", fontSize: 24, color: C.ink, margin: 0, isTextBox: true });
  bullets(s, ["E = P(entailment), A = acoustic score.", "S >= t(clinician, field) -> VERIFIED (auto-insert).", "S < t -> NEEDS_REVIEW (blocked, queued).", "t starts at 0.75 per field; floors (0.30, 0.50) and contradiction limit never adapt."], 0.6, 3.35, 6.3, 2.7, 14);
  table(s, [
    ["Real fact (audio run, wording abridged)", "E", "A", "S", "Result"],
    ["Diarrhea for the last three days.", "0.996", "0.896", "0.96", { text: "VERIFIED", options: { color: C.verified, bold: true } }],
    ["Fever at onset, none now.", "0.631", "0.967", "0.77", { text: "VERIFIED", options: { color: C.verified, bold: true } }],
    ["Take 2-3 days off work to rest.", "0.426", "0.853", "0.60", { text: "REVIEW", options: { color: C.review, bold: true } }],
    ["History of asthma, well controlled.", "0.384", "0.784", "0.54", { text: "REVIEW", options: { color: C.review, bold: true } }],
  ], 7.2, 1.6, 5.5, [2.6, 0.7, 0.7, 0.6, 0.9], { fontSize: 11.5, rowH: 0.55 });
}
{
  const s = base(null, null, "[19] BNF for indications / contraindications / interactions (curated subset, not exhaustive); examples from our plausibility tests");
  stepHeader(s, 8, "Gate 3: clinical plausibility", 7);
  text(s, "Catches statements that are faithful to the audio but clinically unsafe. Runs on every non-rejected medication / plan fact, against the encounter's other facts.", 0.6, 1.55, 12.1, 0.6, { fontSize: 15 });
  const checks = [["Allergy conflict", "amoxicillin + documented penicillin allergy"], ["Antibiotic for viral", "antibiotic while assessment says viral"],
    ["Indication mismatch", "\"aspirin for your diarrhoea\""], ["Contraindication", "naproxen + history of peptic ulcer"], ["Drug interaction", "warfarin + NSAID"]];
  checks.forEach(([h, e], i) => {
    const x = 0.6 + i * 2.45;
    card(s, x, 2.35, 2.25, 2.0);
    text(s, h, x + 0.18, 2.5, 1.95, 0.6, { fontSize: 14.5, bold: true, color: C.blocked });
    text(s, e, x + 0.18, 3.15, 1.95, 1.1, { fontSize: 12.5 });
  });
  bullets(s, [[b("Negation-aware: "), n("\"No known drug allergies\", \"no history of stomach ulcers\" and \"you don't need amoxicillin\" raise nothing.")],
    [b("Effect: "), n("a conflict demotes VERIFIED -> NEEDS_REVIEW and attaches the reason for the clinician.")],
    [b("Knowledge: "), n("curated drug classes / indications / interactions [19]; production would use RxNorm / openFDA.")]], 0.6, 4.6, 12.1, 1.6, 13.5);
}
{
  const s = base(null, null, "Prototype web app (prototype/web/case.js); speaker-level provenance idea related to evidence linking in [9][10], here attached to blocked facts only");
  stepHeader(s, 9, "Clinician review queue with audio replay", 8);
  bullets(s, ["Only blocked facts need attention; verified facts are already in the note.",
    "Each card shows: badge (needs review / blocked), entailment, acoustic, combined score, the quoted evidence, and any plausibility conflict.",
    "Clicking a fact highlights the exact quoted words in the transcript.", "▶ on a segment plays only that audio span from the original recording.",
    "Approve or Reject: recorded under the clinician's name."], 0.6, 1.6, 6.3, 4.6, 14.5);
  card(s, 7.2, 1.6, 5.5, 4.4);
  text(s, "NEEDS REVIEW", 7.45, 1.8, 2.2, 0.35, { fontSize: 11, bold: true, color: C.review });
  text(s, "Take two to three days off work to rest.", 7.45, 2.15, 5.0, 0.5, { fontSize: 15, bold: true, color: C.ink });
  text(s, "entailment 0.43 · acoustic 0.85 · combined 0.60", 7.45, 2.65, 5.0, 0.35, { fontSize: 12, color: C.muted });
  text(s, "#154 \"some type of work.\"   #157 \"take some time off and rest.\"", 7.45, 3.05, 5.0, 0.6, { fontSize: 12, italic: true });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.45, y: 3.85, w: 1.3, h: 0.45, fill: { color: C.mintDeep }, line: { color: C.mintDeep }, rectRadius: 0.06 });
  text(s, "Approve", 7.45, 3.85, 1.3, 0.45, { fontSize: 13, bold: true, color: C.white, align: "center", valign: "middle" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.95, y: 3.85, w: 1.3, h: 0.45, fill: { color: C.white }, line: { color: C.blocked }, rectRadius: 0.06 });
  text(s, "Reject", 8.95, 3.85, 1.3, 0.45, { fontSize: 13, bold: true, color: C.blocked, align: "center", valign: "middle" });
  s.addText([{ text: "Schematic of the review card with real values. Add a screenshot of the running app here.", options: { color: C.red, bold: true } }],
    { x: 7.45, y: 4.6, w: 5.0, h: 1.2, fontFace: BF, fontSize: 11.5, margin: 0, isTextBox: true });
}
{
  const s = base(null, null, "Update rule from prototype/src/calibration.py; result from our web-app test");
  stepHeader(s, 10, "Adaptive calibration per clinician", 9);
  card(s, 0.6, 1.6, 6.3, 1.8, "E8ECEE");
  s.addText([{ text: "t ← clip( t + 0.2 · (τ − t), 0.55, 0.95 )", options: { breakLine: true } },
    { text: "τ = S of the fact (approve)   ·   τ = 0.95 (reject)", options: { fontSize: 15 } }],
    { x: 0.85, y: 1.75, w: 5.9, h: 1.5, fontFace: "Cambria Math", fontSize: 22, color: C.ink, margin: 0, isTextBox: true });
  bullets(s, ["Stored per clinician and per field, reused on all of that clinician's future cases.", "Only NEEDS_REVIEW decisions move t; REJECTED facts failed a fixed floor.",
    "Approvals relax the bar toward the level the clinician trusts; rejections tighten it."], 0.6, 3.65, 6.3, 2.5, 14);
  s.addImage({ path: path.join(FIG, "fig3_calibration.png"), x: 7.2, y: 1.6, w: 5.5, h: 3.0, sizing: { type: "contain", w: 5.5, h: 3.0 } });
  card(s, 7.2, 4.8, 5.5, 1.3);
  text(s, [b("Real test: "), n("rejecting the borderline \"days off work\" fact moved this clinician's plan threshold 0.75 -> 0.79; a medications rejection in the web app showed 0.79 on a different case too.")], 7.45, 4.92, 5.0, 1.1, { fontSize: 12.5 });
}
{
  const s = base(null, null, "prototype/src/audit.py; entry copied from a real audit log produced by our web-app run");
  stepHeader(s, 11, "Append-only audit trail", 10);
  bullets(s, ["Every event is appended, never edited: input_received, auto_gate_decision, clinical_plausibility_flag, clinician_resolution, calibration_update.",
    "Each gate record stores the fact, citations, extractor, entailment / contradiction, acoustic, combined score, status and reason.",
    "So every line in the chart is traceable to machine verification (with its scores) or a named clinician's decision."], 0.6, 1.6, 5.6, 4.5, 14.5);
  card(s, 6.5, 1.6, 6.2, 4.4, "1B2B33");
  s.addText([
    { text: "{\"event\": \"auto_gate_decision\",", options: { breakLine: true } },
    { text: " \"fact_id\": \"F012\", \"field\": \"plan\",", options: { breakLine: true } },
    { text: " \"value\": \"as an infection clears from your", options: { breakLine: true } },
    { text: "   system, take some time off and rest.\",", options: { breakLine: true } },
    { text: " \"cited_segment_ids\": [157],", options: { breakLine: true } },
    { text: " \"extractor\": \"rule_based\",", options: { breakLine: true } },
    { text: " \"nli\": {\"entailment\": 0.9893,", options: { breakLine: true } },
    { text: "         \"contradiction\": 0.001},", options: { breakLine: true } },
    { text: " \"acoustic_score\": 0.801,", options: { breakLine: true } },
    { text: " \"combined_confidence\": 0.914,", options: { breakLine: true } },
    { text: " \"status\": \"VERIFIED\"}" },
  ], { x: 6.75, y: 1.8, w: 5.8, h: 4.0, fontFace: "Courier New", fontSize: 12.5, color: "D7F0EA", margin: 0, valign: "top", isTextBox: true });
}

// Algorithm / mathematical formulation
{
  const s = base("Review 2 · Algorithm and mathematical formulation", "Algorithm: gating one drafted fact", "prototype/src/grounding.py, clinical_plausibility.py; FIG. 2 of the patent disclosure");
  s.addText([
    "Input: fact f = (field, statement h, citations {(s_i, q_i)}), segments, threshold t",
    "1  if no valid citation or any align(q_i, s_i) < 90: return REJECTED",
    "2  premise P = concat(speaker_i : text(s_i))",
    "3  (E, N, C) = NLI(P, h)",
    "4  if C >= 0.50 or E < 0.30: return REJECTED",
    "5  Q = ASR words overlapping aligned quotes",
    "6  A = mean_{w in Q} p(w)   (None if no audio)",
    "7  if A is not None and A < 0.50: return REJECTED",
    "8  S = 0.6 E + 0.4 A   (S = E if A is None)",
    "9  status = VERIFIED if S >= t[clinician, field] else NEEDS_REVIEW",
    "10 if status == VERIFIED and plausibility_conflict(f, other facts):",
    "       status = NEEDS_REVIEW",
    "11 append(audit, f, E, C, A, S, status, reason);  return status",
  ].map((l, i, a) => ({ text: l, options: { breakLine: i < a.length - 1 } })),
    { x: 0.6, y: 1.55, w: 7.3, h: 4.9, fontFace: "Courier New", fontSize: 12.5, color: C.body, margin: 0, valign: "top", isTextBox: true });
  s.addImage({ path: path.join(FIG, "fig2_gate_flow.png"), x: 8.2, y: 1.45, w: 4.5, h: 5.35, sizing: { type: "contain", w: 4.5, h: 5.35 } });
}

// Validation process and metrics
{
  const s = base("Review 2 · Validation process and performance metrics", "Validation process and metrics", "[1] PriMock57; WER = (S + D + I) / N over words after normalisation");
  table(s, [
    ["What is validated", "Metric", "Status"],
    ["Speech recognition quality", "Word error rate vs. human transcript; mean word probability", { text: "Measured: 1 consultation", options: { color: C.verified, bold: true } }],
    ["Gate behaviour on known cases", "Expected decision for 7 scripted scenarios (true fact, wrong duration, unsupported, invented quote, ASR error, calibration, unsafe Rx)", { text: "Measured: 7 / 7", options: { color: C.verified, bold: true } }],
    ["NLI discrimination", "P(entail) / P(contradict) on paraphrase, negation, wrong dose, unsupported pairs", { text: "Measured: 6 pairs", options: { color: C.verified, bold: true } }],
    ["End-to-end throughput", "facts verified / held / blocked per consultation; runtime on CPU", { text: "Measured: 3 runs", options: { color: C.verified, bold: true } }],
    ["Gate accuracy", "precision / recall of blocking against facts labelled correct / incorrect", { text: "Planned", options: { color: C.red, bold: true } }],
    ["Across the dataset", "all 57 consultations from audio; WER distribution", { text: "Planned", options: { color: C.red, bold: true } }],
    ["Clinician usefulness", "review time, acceptance rate (user study)", { text: "Planned", options: { color: C.red, bold: true } }],
  ], 0.6, 1.55, 12.1, [3.2, 6.5, 2.4], { fontSize: 12, rowH: 0.56 });
}

// Preliminary results (chart)
{
  const s = base("Review 2 · Preliminary results", "Preliminary results", "Our runs on PriMock57 day1_consultation01 [1], 22-23 Sep 2026; LLM output varies between runs");
  s.addChart(pres.charts.BAR, [
    { name: "Auto-verified", labels: ["Word-overlap gate\n(text, Gemini)", "NLI gate\n(text, Gemini)", "NLI gate\n(audio, CLI)", "NLI gate\n(audio, web)"], values: [0, 17, 23, 19] },
    { name: "Held for review", labels: ["Word-overlap gate\n(text, Gemini)", "NLI gate\n(text, Gemini)", "NLI gate\n(audio, CLI)", "NLI gate\n(audio, web)"], values: [11, 1, 3, 0] },
    { name: "Blocked", labels: ["Word-overlap gate\n(text, Gemini)", "NLI gate\n(text, Gemini)", "NLI gate\n(audio, CLI)", "NLI gate\n(audio, web)"], values: [10, 1, 0, 1] },
  ], { x: 0.6, y: 1.5, w: 7.6, h: 4.9, barDir: "col", barGrouping: "stacked", chartColors: [C.verified, C.review, C.blocked],
    showValue: true, dataLabelPosition: "ctr", dataLabelColor: C.white, dataLabelFontSize: 11, dataLabelFormatCode: "0;-0;;",
    showLegend: true, legendPos: "b", legendFontSize: 11, catAxisLabelFontSize: 10.5, valAxisLabelFontSize: 10,
    catAxisLabelColor: C.muted, valAxisLabelColor: C.muted, valGridLine: { color: "E3E8E7", size: 0.5 }, catGridLine: { style: "none" },
    showTitle: true, title: "Drafted facts by gate decision", titleFontSize: 13, titleColor: C.ink });
  card(s, 8.6, 1.5, 4.1, 4.9);
  stat(s, 8.85, 1.7, 3.6, "0 → 17", "of the same consultation's Gemini facts auto-verified after replacing word overlap with NLI", C.verified);
  stat(s, 8.85, 3.2, 3.6, "23 / 26", "facts auto-verified from real audio; 3 held (one caused by a real ASR error)");
  stat(s, 8.85, 4.7, 3.6, "17.5 %", "WER of local Whisper base.en", C.blocked);
  s.addNotes("Word-overlap run: 21 facts, 11 needs review, 10 rejected (0 verified). NLI text run: 19 facts. Audio CLI: 26 facts. Audio web: 20 facts.");
}

// Analysis and discussion
{
  const s = base("Review 2 · Analysis and discussion", "Analysis and discussion", null);
  card(s, 0.6, 1.55, 5.9, 4.6);
  text(s, "What the results show", 0.85, 1.72, 5.4, 0.45, { fontFace: HF, fontSize: 18, bold: true, color: C.verified });
  bullets(s, ["A real entailment model is essential: word overlap blocked every correct paraphrase.",
    "The gate catches a real ASR error (\"type of work\") that a transcript-faithful check would have let through.",
    "Contradiction is decisive (0.99-1.0) for wrong durations, doses and negations.",
    "Faithful-but-unsafe prescriptions are held by Gate 3, which fidelity checks cannot do.",
    "Runs fully on a CPU laptop; audio never leaves the machine."], 0.85, 2.25, 5.45, 3.9, 13.5);
  card(s, 6.8, 1.55, 5.9, 4.6, "F4F4F4");
  text(s, "Limitations and next steps", 7.05, 1.72, 5.4, 0.45, { fontFace: HF, fontSize: 18, bold: true, color: C.blocked });
  bullets(s, ["Only 1 of 57 consultations run from audio so far: run all 57.",
    "Mean acoustic score can hide one badly heard word (\"blood in the stalk\" passed at 0.84): add a weakest-word floor.",
    "Thresholds / weights set by design: tune on a development split, report on a held-out split.",
    "Plausibility tables are a small curated set: move to RxNorm / openFDA.",
    "No clinician study yet."], 7.05, 2.25, 5.45, 3.9, 13.5);
}

references("Review 2 · References");

// Closing
{
  const s = darkSlide("Thank you", "Evidence first, then the record.", "Questions?");
  s.addText([{ text: "Code: prototype/ (FastAPI + local Whisper + DeBERTa NLI).  Note: the GitHub repository is public; see patent disclosure section 18.", options: { color: "C8DAD6" } }],
    { x: 0.8, y: 5.6, w: 11.5, h: 0.5, fontFace: BF, fontSize: 12, margin: 0, isTextBox: true });
}

pres.writeFile({ fileName: OUT }).then((f) => console.log("saved", f));
