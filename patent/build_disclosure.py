"""
Builds the invention disclosure (Section A: Technical Detail Report) as a .docx,
following the numbered-table layout of the institute's patent form.

Text marked with flag(...) is rendered in red: it is a placeholder or a
third-party figure that the inventors must verify before submission.
"""
import os
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
OUT = Path(os.environ.get("DOCX_OUT", HERE / "Patent_Disclosure_Confidence_Gated_Clinical_Documentation.docx"))

HEADER_FILL = "DCE6F0"
RED = RGBColor(0xC0, 0x00, 0x00)
FONT = "Times New Roman"


class Flag(str):
    """A text fragment that must be verified/filled in by the inventors (rendered red)."""


def flag(text):
    return Flag(text)


# ---------------------------------------------------------------- helpers

def shade(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def set_cell_width(cell, cm):
    cell.width = Cm(cm)


def add_runs(par, parts, size=11, bold=False, italic=False):
    """parts: str | Flag | list of (str|Flag|('b', text)|('i', text)|('code', text))."""
    if isinstance(parts, (str, Flag)):
        parts = [parts]
    for part in parts:
        style = None
        if isinstance(part, tuple):
            style, part = part
        run = par.add_run(part)
        run.font.name = FONT
        run.font.size = Pt(size)
        run.bold = bold or style == "b"
        run.italic = italic or style == "i"
        if style == "code":
            run.font.name = "Consolas"
            run.font.size = Pt(size - 1)
        if isinstance(part, Flag):
            run.font.color.rgb = RED
    return par


def para(cell, parts, size=11, bold=False, italic=False, align=None, space_after=4, first=False):
    p = cell.paragraphs[0] if first and not cell.paragraphs[0].text else cell.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.space_before = Pt(0)
    if align:
        p.alignment = align
    return add_runs(p, parts, size, bold, italic)


def bullet(cell, parts, level=0):
    p = cell.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
    p.paragraph_format.space_after = Pt(2)
    return add_runs(p, parts)


def numbered(cell, n, parts):
    p = cell.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.6)
    p.paragraph_format.first_line_indent = Cm(-0.6)
    p.paragraph_format.space_after = Pt(3)
    return add_runs(p, [f"{n}.  "] + (parts if isinstance(parts, list) else [parts]))


def small_table(cell, header, rows, widths):
    t = cell.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]
        shade(c, "F2F2F2")
        add_runs(c.paragraphs[0], h, size=9.5, bold=True)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            add_runs(cells[i].paragraphs[0], v if isinstance(v, list) else [v], size=9.5)
    for row in t.rows:
        for i, w in enumerate(widths):
            set_cell_width(row.cells[i], w)
    cell.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


# ---------------------------------------------------------------- document

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
sec.left_margin = sec.right_margin = Cm(2.0)
sec.top_margin = sec.bottom_margin = Cm(2.0)
normal = doc.styles["Normal"]
normal.font.name = FONT
normal.font.size = Pt(11)
normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)

h = doc.add_paragraph()
h.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = h.add_run("SECTION A: TECHNICAL DETAIL REPORT")
r.bold, r.underline, r.font.size, r.font.name = True, True, Pt(14), FONT

legend = doc.add_paragraph()
legend.alignment = WD_ALIGN_PARAGRAPH.CENTER
add_runs(legend, [("i", "Text in "), flag("red"),
                  ("i", " is a placeholder or a third-party figure that must be completed or verified before submission.")],
         size=9)

table = doc.add_table(rows=0, cols=2)
table.style = "Table Grid"
table.alignment = WD_TABLE_ALIGNMENT.CENTER
NUM_W, BODY_W = 1.1, 15.9


def section(num, title, hint=None):
    """Header row (shaded) + body row; returns the body cell."""
    hdr = table.add_row().cells
    shade(hdr[0], HEADER_FILL)
    shade(hdr[1], HEADER_FILL)
    add_runs(hdr[0].paragraphs[0], f"{num}.", bold=True)
    add_runs(hdr[1].paragraphs[0], title, bold=True)
    if hint:
        para(hdr[1], hint, size=9, italic=True, space_after=2)
    body = table.add_row().cells
    set_cell_width(hdr[0], NUM_W); set_cell_width(hdr[1], BODY_W)
    set_cell_width(body[0], NUM_W); set_cell_width(body[1], BODY_W)
    return body[1]


def figure(cell, path, caption, width_cm=15.0):
    p = cell.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(path), width=Cm(width_cm))
    para(cell, caption, size=9.5, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=8)


# 1 ------------------------------------------------------------------------
c = section(1, "Title of the Invention (should not exceed 15 words)")
para(c, "Confidence-Gated Clinical Documentation Using Acoustic, Entailment and Plausibility Verification "
        "of AI-Drafted Facts", bold=True, first=True)
para(c, [("i", "(12 words)")], size=9)

# 2 ------------------------------------------------------------------------
c = section(2, "What is the Invention?",
            "(Should include Problem and Solution statement and general purpose in relation with your invention)")
para(c, [("b", "Problem: "),
         "AI \"ambient scribes\" record a doctor-patient consultation, transcribe it with automatic speech "
         "recognition (ASR) and use a large language model (LLM) to draft the clinical note. Three kinds of error "
         "reach the draft: (i) ASR misrecognition (in our own tests on real consultation audio, \"take some time off "
         "work\" was transcribed as \"take some type of work\", and \"stool\" as \"stall\"/\"stalk\"); (ii) LLM "
         "hallucination or mis-attribution (a dose, duration or symptom that was never said); and (iii) statements "
         "that are faithfully transcribed but clinically unsafe (e.g. an antibiotic prescribed to a patient with a "
         "documented allergy to that drug class). Commercial products (Nuance DAX, Abridge, AWS HealthScribe) link "
         "note sentences back to the transcript, but that link is only an optional convenience: every drafted "
         "statement still enters the note, and catching errors depends on a busy clinician choosing to check each "
         "one (automation bias)."], first=True)
para(c, [("b", "Solution: "),
         "Every clinical fact the system drafts must carry (a) the transcript segment(s) it relies on and (b) a "
         "verbatim quote from each. Before a fact may be auto-inserted into the structured note it must pass a "
         "multi-signal gate: citation integrity (each quote must actually occur in its cited segment); an acoustic "
         "signal (the ASR engine's own per-word confidence over exactly the quoted words); a semantic signal (a "
         "natural-language-inference model's probability that the cited evidence entails the statement, with outright "
         "rejection when the evidence contradicts it); and a clinical-plausibility cross-check against the rest of the "
         "encounter (allergy class, indication, contraindication, drug interaction, antibiotic stewardship). A fact "
         "that fails is hard-blocked from the record -- not merely flagged -- and routed to a review queue where the "
         "clinician sees the quoted evidence and can replay the exact audio span. Each approve/reject decision "
         "recalibrates that clinician's per-field auto-insert threshold, and every automatic and human decision is "
         "appended to an append-only audit log, so every line in the chart is traceable to either "
         "machine verification above threshold or a named clinician's sign-off."])
para(c, [("b", "General purpose: "),
         "To let healthcare providers use AI drafting to cut documentation time without allowing unverified, "
         "misheard, invented or unsafe statements to silently enter the medical record."])

# 3 ------------------------------------------------------------------------
c = section(3, "Search Terms",
            "(Please provide key words and common industry phrases on the basis of which this invention could be "
            "connected with the prior art)")
for t in ["Ambient clinical documentation, ambient AI scribe, digital scribe, ambient clinical intelligence (ACI)",
          "Automated clinical note generation from doctor-patient conversation; SOAP note generation",
          "Evidence linking / evidence mapping of note sentences to transcript segments",
          "Hallucination detection, factual consistency, faithfulness verification of generated summaries",
          "Natural language inference (NLI), textual entailment, entailment-based fact checking",
          "Speech recognition confidence score, word-level confidence, low-confidence word highlighting",
          "Confidence-gated / threshold-gated auto-population of EHR fields; human-in-the-loop review queue",
          "Adaptive threshold calibration from user feedback; active learning from clinician corrections",
          "Clinical decision support: drug-allergy check, drug-drug interaction, contraindication, antibiotic stewardship",
          "Audit trail, provenance, append-only log for AI-generated medical documentation"]:
    bullet(c, t)

# 4 ------------------------------------------------------------------------
c = section(4, "Background of the Invention (Present state of Art)")
para(c, [("b", "a. What are the present technologies that exist in the field of your invention")], first=True)
para(c, "Ambient AI scribes (Nuance/Microsoft DAX Copilot, Abridge, Suki, AWS HealthScribe, Augnito and others) "
        "combine medical ASR with LLM summarisation to draft notes from a recorded consultation. Several expose "
        "evidence links: AWS HealthScribe returns, for every summary sentence, the transcript segment ids it was "
        "derived from; Abridge \"Linked Evidence\" lets a clinician highlight note text, see the source transcript "
        "passage and replay the audio. Speech-recognition systems have long computed per-word confidence scores and "
        "displayed low-confidence words in a different colour. In research, NLI/entailment models (e.g. SummaC, "
        "FactCC) are used offline to score the factual consistency of generated summaries, and datasets such as "
        "ACI-BENCH and PriMock57 benchmark note generation from consultations. Separately, clinical decision-support "
        "systems perform drug-allergy and drug-interaction checks at order entry.")
para(c, [("b", "b. What are the limitations of the same?")])
for t in ["Evidence links are advisory. Every drafted statement is inserted into the note regardless of how weakly it is "
          "supported; verification is left to the clinician, who under time pressure tends to accept drafts "
          "(automation bias).",
          "The existence of a citation is not checked for correctness: a fact can cite a real segment that does not "
          "actually support (or even contradicts) it, or quote text that is not in that segment.",
          "ASR confidence is shown at word level on the transcript but is not propagated to the specific note "
          "statements built from those words, and is not combined with a semantic check.",
          "Where a confidence model exists in prior art, it gates whole report sections on whether editing is "
          "cheaper than rewriting -- not each individual fact against its own cited evidence.",
          "Factual-consistency (NLI) scoring is used in research as an offline metric, not as an enforcing gate "
          "inside the documentation workflow.",
          "Drug-safety checks run at order entry, not on AI-drafted narrative text, so a faithfully transcribed but "
          "unsafe instruction (\"start amoxicillin\" for a penicillin-allergic patient) passes a transcript-fidelity check.",
          "Thresholds are static; they do not learn from each clinician's approve/reject behaviour, and there is no "
          "per-line record of why each sentence entered the chart."]:
    bullet(c, t)

# 5 ------------------------------------------------------------------------
c = section(5, "Prior Art",
            "(Please provide the details of the product or process by the help of which the problem solved by the "
            "invention was tackled before this invention. Please details of prior technologies, patents, or "
            "publications relevant to this invention)")
prior = [
    [("b", "US 11,222,716 B2"), " (Nuance Communications, now Microsoft Technology Licensing; filed 5 Mar 2019, granted "
     "11 Jan 2022) \"System and method for review of automated clinical documentation from recorded audio\" -- links "
     "audio, transcript and report layers for navigation; a confidence model exposes a draft report section only "
     "if editing it is judged faster than composing manually. Closest prior art to our gating concept, but it "
     "gates sections on editing effort, not individual facts on acoustic + entailment evidence."],
    [("b", "US 10,719,222 B2"), " (Google LLC; filed 24 May 2018, granted 21 Jul 2020) \"Method and system for "
     "generating transcripts of patient-healthcare provider conversations\" -- real-time transcript and auto-generated "
     "note, extracted phrases highlighted and linked to the transcript, confidence indicators for uncertain speech; "
     "verification is performed by the physician by inspection."],
    [("b", "US 11,227,688 B2"), " (Google LLC; filed 24 May 2018, granted 18 Jan 2022) \"Interface for "
     "patient-provider conversation and auto-generation of note or summary\" -- workstation showing transcript beside "
     "generated note, with extracted terms linked back to their audio."],
    [("b", "US 6,006,183 A"), " (IBM; filed 16 Dec 1997, granted 21 Dec 1999) \"Speech recognition confidence "
     "level display\" -- per-word confidence scores rendered with colour/font attributes above a user-set threshold."],
    [("b", "AWS HealthScribe"), " (Amazon, 2023) -- transcript with word-level timestamps and speaker roles; every "
     "summary sentence carries EvidenceLinks (segment ids) for the user to validate."],
    [("b", "Abridge Linked Evidence"), " (Abridge AI) -- each note section hyperlinked to the transcript passage and "
     "audio timestamp that produced it; clinician can replay audio to verify."],
    [("b", "Nuance / Microsoft DAX Copilot"), " -- ambient capture and LLM drafting of notes for clinician review "
     "and sign-off inside the EHR."],
    [("b", "Research: "), "Laban et al., \"SummaC: Re-visiting NLI-based models for inconsistency detection in "
     "summarization\", TACL 2022; Kryscinski et al., \"Evaluating the factual consistency of abstractive text "
     "summarization\" (FactCC), EMNLP 2020; Yim et al., \"ACI-BENCH\", Scientific Data 2023; Papadopoulos Korfiatis "
     "et al., \"PriMock57: A dataset of primary care mock consultations\", ACL 2022; Radford et al., \"Robust speech "
     "recognition via large-scale weak supervision\" (Whisper), ICML 2023."],
]
for p_ in prior:
    bullet(c, p_)

# 6 ------------------------------------------------------------------------
c = section(6, "Has the work filled a major gap in the prior art? If yes, a brief description of this gap.")
para(c, [("b", "Yes. "),
         "Prior systems either (a) link note text to its source so a human can check it, (b) show ASR confidence on "
         "transcript words, (c) score factual consistency offline, or (d) gate an entire draft section on predicted "
         "editing effort. None of them enforces, per drafted fact, that the fact's own cited evidence verbatim exists, "
         "was recognised with sufficient acoustic confidence at exactly the quoted words, and semantically entails "
         "(and does not contradict) the statement -- and then hard-blocks the fact from the record, cross-checks it for "
         "clinical plausibility against the rest of the encounter, learns the auto-insert threshold per clinician and "
         "per field from that clinician's decisions, and records the provenance of every note line. The invention "
         "turns evidence linking from an optional convenience into an enforced, auditable admission control for the "
         "medical record."], first=True)

# 7 ------------------------------------------------------------------------
c = section(7, "What are the components of the Invention?",
            "(Explain the external and internal parts/blocks/systems-subsystems/ composition/steps of process of your "
            "invention).")
para(c, [("b", "High-level components (reference numerals refer to FIG. 1; file names refer to the working prototype):")],
     first=True)
comps = [
    ("Audio capture (100)", "consultation audio, either separate doctor and patient channels or a single mixed recording."),
    ("Local ASR engine (110) with medical-vocabulary layer (115)", "an off-the-shelf speech recogniser (faster-whisper) "
     "run on-premise, producing per-word probabilities, timestamps and character offsets. Only words the recogniser "
     "itself scored below 0.70 are fuzzy-corrected to known drug/symptom terms, with the original word retained for "
     "audit. Prompt-based vocabulary biasing (initial prompt or hotwords) is available as an option but off by default, "
     "because it increased the word error rate in our A/B test (section 15) (transcribe.py, medical_terms.py)."),
    ("Speaker-role attribution (120)", "roles from the recording channel, or inferred by an LLM for mixed recordings "
     "and marked as inferred (speakers.py)."),
    ("Segmented transcript (130)", "utterances with id, speaker, text, and per-word probability and offsets."),
    ("Fact extractor (140)", "rule-based or LLM-based (Gemini / Claude); outputs, per fact, a field, a statement, "
     "cited segment ids and a verbatim quote from each cited segment, constrained to a JSON schema (extractor.py, llm.py)."),
    ("Gate 0 - citation integrity (150)", "fuzzy alignment of each quote inside its cited segment (score >= 90/100); "
     "an invented or mis-attributed quote rejects the fact (grounding.py)."),
    ("Gate 1 - acoustic signal (160)", "mean ASR word probability over exactly the words the aligned quote spans; "
     "reported as unavailable (never imputed) for text-only input."),
    ("Gate 2 - semantic signal (170)", "a locally run NLI cross-encoder (DeBERTa-v3 MNLI/FEVER/ANLI) returns "
     "P(entailment), P(neutral), P(contradiction) for (cited segments, statement) (entailment.py)."),
    ("Combiner and adaptive threshold (180)", "fixed safety floors, weighted combination, comparison with the "
     "clinician's per-field threshold."),
    ("Gate 3 - clinical plausibility (190)", "allergy-class conflict, antibiotic-for-viral, indication mismatch, "
     "contraindication and drug-drug interaction checks with negation handling (clinical_plausibility.py)."),
    ("Structured note (200) and review queue (210)", "only VERIFIED facts are auto-inserted; blocked facts are queued "
     "with their evidence, reasons and a per-segment audio replay control (web/case.js)."),
    ("Calibration store (220)", "per-clinician, per-field thresholds updated from approve/reject decisions (calibration.py)."),
    ("Append-only audit log (230)", "every input, gate decision, plausibility flag, clinician resolution and threshold "
     "change (audit.py)."),
    ("Application layer", "FastAPI backend with background pipeline jobs and live stage reporting; browser UI for "
     "upload, progress, note review and audio playback (api/server.py, web/)."),
]
for name, desc in comps:
    bullet(c, [("b", name + ": "), desc])

# 8 ------------------------------------------------------------------------
c = section(8, "How does the Invention work? Please describe the complete sequence of operation of the invention, "
               "including the inputs received, processing or operations performed, interaction between the relevant "
               "components, and the resulting output, action, or technical effect.",
            "(This portion of your invention disclosure deals with the working of your invention, the processes "
            "involved and the interactive actions taking place between the various components of your invention to "
            "give the desired output.)")
steps = [
    ("Capture and transcription.", "The recording is transcribed locally. Each Whisper segment is split into "
     "utterances at pauses of 0.8 s or more; each word keeps its probability, start/end time and character offsets. "
     "Channels are merged in time order."),
    ("Speaker roles.", "Taken from the channel, or attributed by an LLM for a mixed recording."),
    ("Fact drafting.", "The extractor returns facts, each with field (chief complaint, history, medications, "
     "allergies, vitals, assessment, plan), statement, and citations of the form {segment_id, verbatim quote}; "
     "questions are cited together with their answers (\"Do you smoke?\" / \"No\")."),
    ("Gate 0.", "A fact with no valid citation or no quote is REJECTED. Each quote is fuzzy-aligned inside its "
     "segment; if any quote aligns below 90/100 the fact is REJECTED as invented or mis-attributed evidence."),
    ("Gate 2.", "All surviving facts are scored in one batch by the NLI model with the premise formed from the cited "
     "segments in order (\"Doctor: ... Patient: ...\"). P(contradiction) >= 0.50 -> REJECTED; P(entailment) < 0.30 -> "
     "REJECTED."),
    ("Gate 1.", "The acoustic score is the mean probability of the ASR words overlapping the aligned quote spans "
     "(fallback: the cited segments' words). Below 0.50 -> REJECTED, with the weakest words reported. In addition, the "
     "least confidently recognised content word of the quotation (function words and fillers excluded) is recorded; if "
     "its probability is below 0.35 the fact cannot be auto-inserted even when its combined score clears the threshold "
     "-- it goes to review, because one misheard word can hide inside a high average. For text input the acoustic "
     "signal is recorded as unavailable and the decision is made on the semantic signal alone, which the reason text "
     "states explicitly."),
    ("Combination.", "combined = 0.6 x entailment + 0.4 x acoustic (or entailment alone without audio). If combined >= "
     "the clinician's threshold for that field (initially 0.75) and the weakest quoted content word is at least 0.35, the "
     "fact is VERIFIED; otherwise NEEDS_REVIEW."),
    ("Gate 3.", "Every non-rejected medication/plan fact is checked against the other non-rejected facts: allergy "
     "class, antibiotic prescribed against a viral assessment, \"<drug> for <condition>\" outside the drug's "
     "indications, contraindications in the documented history, and interacting drug pairs; negated mentions are "
     "ignored. Any conflict demotes a VERIFIED fact to NEEDS_REVIEW."),
    ("Enforcement and review.", "Only VERIFIED facts populate the note. Blocked facts appear in a review queue with "
     "their signals, quoted evidence (highlighted in the transcript), plausibility conflicts, and a control that "
     "replays exactly the cited audio span."),
    ("Adaptive calibration.", "When the named clinician resolves a NEEDS_REVIEW fact, that clinician's threshold for "
     "the field moves t <- t + 0.2 (target - t), target = the fact's combined score on approve or 0.95 on reject, "
     "clamped to [0.55, 0.95]. REJECTED facts never move thresholds, so the hard floors stay fixed. Thresholds "
     "persist across all of that clinician's cases."),
    ("Audit.", "input_received, auto_gate_decision (with every signal), clinical_plausibility_flag, "
     "clinician_resolution (name, decision) and calibration_update events are appended, never rewritten."),
]
for i, (h_, t) in enumerate(steps, 1):
    numbered(c, i, [("b", h_ + " "), t])
para(c, [("b", "Inputs: "), "consultation audio (two single-speaker channels, or one mixed recording) or a text "
         "transcript; the clinician's identity; the clinician's stored per-field thresholds."])
para(c, [("b", "Outputs: "), "(i) a structured note containing only VERIFIED facts; (ii) a review queue of withheld "
         "facts, each with its signals, reason, highlighted evidence and audio span; (iii) updated per-clinician "
         "thresholds; (iv) an append-only audit log."])
para(c, [("b", "Technical effect: "), "the system physically prevents unverified, contradicted, mis-cited, "
         "poorly-recognised or clinically conflicting machine-drafted statements from being written into the medical "
         "record, while letting evidence-backed statements through without human effort. Clinician attention is "
         "confined to the withheld facts, each presented with a specific machine-generated reason and its exact source "
         "audio, and every record line carries a machine-readable provenance entry."])

# 9 ------------------------------------------------------------------------
c = section(9, "Novelty of the Invention/Inventive Step of the Invention",
            "(Please state the unique/ novel aspect of your invention and how it is different and/or better than the "
            "existing technologies):")
for t in [
    [("b", "Enforcement instead of annotation: "), "evidence is used to admit or block each individual fact from "
     "the medical record, not merely displayed for optional inspection."],
    [("b", "Weakest-word safeguard: "), "a fact whose own evidence contains one poorly recognised content word is held "
     "for review even if its averages are high -- on real audio this caught \"no blood in the stool\" built on the "
     "misrecognised \"loose stalk\" (probability 0.28), which had passed entailment (0.89) and the combined threshold (0.83)."],
    [("b", "Per-fact, evidence-anchored dual signal: "), "the acoustic confidence is taken over exactly the words the "
     "fact quotes (not the whole transcript or segment) and combined with an entailment probability computed on "
     "that same cited evidence; contradiction by the evidence is an absolute rejection."],
    [("b", "Citation integrity as a precondition: "), "the extractor must supply verbatim quotes, and a quote not found "
     "in its cited segment rejects the fact before any scoring."],
    [("b", "Third, clinical-plausibility gate on drafted narrative: "), "catches statements that are faithful to the "
     "audio but unsafe, including indication mismatch and cross-fact conflicts within the same encounter."],
    [("b", "Adaptive, per-clinician, per-field thresholds "), "learned from that clinician's approve/reject decisions, "
     "bounded, while the safety floors stay non-adaptive."],
    [("b", "Honest handling of missing signals: "), "when a signal does not exist (text input) it is recorded as "
     "unavailable and the decision basis is logged, instead of imputing a value."],
    [("b", "Line-level provenance: "), "every note line is traceable in an append-only log to machine verification "
     "(with its signal values) or a named clinician's decision."],
]:
    bullet(c, t)

# 10 -----------------------------------------------------------------------
c = section(10, "What are the advantages and improvements over the existing methods/devices?",
            "(Please list advantages and improvements against closest patent and non-patent documents/products in "
            "pipeline explaining technical advancement of present invention over the existing technologies)")
for t in [
    [("b", "Patient safety: "), "misheard, invented, contradicted or clinically unsafe statements cannot silently enter "
     "the record (vs. evidence linking in AWS HealthScribe/Abridge, where every statement is inserted)."],
    [("b", "Targeted clinician effort: "), "the clinician reviews only blocked facts, each with its specific reason, "
     "quoted evidence and one-click audio replay, instead of re-reading the whole note."],
    [("b", "Finer granularity than US 11,222,716: "), "decisions are per fact and grounded in that fact's own evidence, "
     "not per report section on predicted editing effort."],
    [("b", "Uses signals the pipeline already produces: "), "ASR word probabilities and cited transcript text; the "
     "verifier runs locally (no transcript leaves the premises for verification)."],
    [("b", "Extractor-agnostic: "), "works identically with rule-based, Gemini or Claude extractors; a better LLM "
     "raises throughput without weakening the gate."],
    [("b", "Personalisation: "), "thresholds adapt to each clinician and field instead of one global setting."],
    [("b", "Auditability and medico-legal defensibility: "), "an append-only record of why each line is in the chart."],
]:
    bullet(c, t)

# 11 -----------------------------------------------------------------------
c = section(11, "Do you have in your mind as a researcher/inventor some ideas as to what are the various "
                "other/alternative forms in which your Invention can be depicted or utilized, in addition to one basic "
                "embodiment that has been described above?",
            "(This will lay the foundation, for making your patent as broad as possible. These are called preferred "
            "embodiments or variants.)")
para(c, [("i", "Items below are proposed embodiments; they are not implemented in the prototype unless stated.")],
     size=10, first=True)
for t in [
    [("b", "EHR integration: "), "writing only VERIFIED facts to EHR fields via HL7 FHIR, with blocked facts held in a "
     "pending state in the EHR inbox."],
    [("b", "Alternative semantic verifiers: "), "any entailment model, a second independent LLM acting as verifier, "
     "or an ensemble; domain-tuned clinical NLI models."],
    [("b", "Alternative acoustic signals: "), "lattice / N-best posteriors, token-level entropy, or confidence from any "
     "commercial ASR; weakest-word limits per field or per word class (e.g. stricter for drug names and negations)."],
    [("b", "Vocabulary biasing variants: "), "initial-prompt or hotword biasing (implemented, off by default), "
     "shallow-fusion language models, or recognisers fine-tuned on clinical speech."],
    [("b", "Clinical knowledge sources: "), "RxNorm / SNOMED-CT drug classes, openFDA or DrugBank interaction data "
     "replacing the prototype's curated tables."],
    [("b", "Acoustic speaker diarization "), "(speaker embeddings) instead of channel- or LLM-based roles for mixed recordings."],
    [("b", "Real-time streaming variant: "), "gating facts incrementally during the consultation."],
    [("b", "Calibration scopes: "), "per clinician (implemented), per department, per institution, or per fact type; "
     "alternative update rules (Bayesian, bandit)."],
    [("b", "Other regulated transcription domains: "), "legal depositions, court records, insurance claims calls, "
     "police interviews -- any setting where machine-drafted statements must be evidenced before entering a record."],
    [("b", "Deployment: "), "fully on-premise / on-device (implemented for ASR and NLI), or cloud with the same gate."],
]:
    bullet(c, t)

# 12 -----------------------------------------------------------------------
c = section(12, "Please provide final CAD images, line diagrams, and schematic images of the final prototype "
                "illustrating all the essential elements of the invention, and shortlist the major/primary drawings "
                "that need to be incorporated in the Complete Specification.",
            "(Please prepare images in two sets, one completely labeled to details and the second one without any "
            "description, legends/labeling or numbering. Include relevant Flow charts.)")
para(c, [("b", "Set 1 - labelled")], first=True)
figure(c, FIG / "labeled" / "fig1_system.png", "FIG. 1 - System architecture and data flow (labelled)")
figure(c, FIG / "labeled" / "fig2_gate_flow.png", "FIG. 2 - Per-fact gate decision flowchart (labelled)", 12.5)
figure(c, FIG / "labeled" / "fig3_calibration.png", "FIG. 3 - Clinician resolution, adaptive calibration and audit (labelled)")
para(c, [("b", "Set 2 - without labels, legends or numbering")])
figure(c, FIG / "unlabeled" / "fig1_system.png", "FIG. 1")
figure(c, FIG / "unlabeled" / "fig2_gate_flow.png", "FIG. 2", 12.5)
figure(c, FIG / "unlabeled" / "fig3_calibration.png", "FIG. 3")
para(c, [flag("Screenshots of the working prototype UI (upload/progress page, case page with blocked facts and audio "
              "replay) are not yet included; capture and attach them before submission.")])
para(c, [("b", "Shortlist for the Complete Specification: ")])
small_table(c, ["Drawing", "Priority", "Reason"], [
    ["FIG. 2 - per-fact gate decision flowchart", "Primary (recommended front-page figure)",
     "Shows the claimed method steps of claim 1 in order: citation check, contradiction, entailment, acoustic floor, "
     "combination, threshold, plausibility, outcome."],
    ["FIG. 1 - system architecture", "Primary", "Shows every component of the system claim (claim 10) and their interaction."],
    ["FIG. 3 - resolution, calibration and audit loop", "Supporting", "Supports dependent claim 3 (adaptive thresholds) "
     "and the audit-log step of claim 1."],
], [5.0, 3.6, 7.0])

# 13 -----------------------------------------------------------------------
c = section(13, "Brief description from the researcher/inventor in his own words explaining the images/ drawings.")
para(c, [("b", "FIG. 1 "), "shows the system. Audio (100) is transcribed by a local ASR engine (110), optionally "
         "assisted by the medical-vocabulary layer (115); speaker roles are attached (120) to give the segmented "
         "transcript (130). The extractor (140) drafts facts with citations and verbatim quotes. Gate 0 (150) checks "
         "each quote exists in its cited segment; Gate 1 (160) scores the ASR confidence of the quoted words; Gate 2 "
         "(170) scores entailment/contradiction; the combiner (180) applies floors and the clinician's per-field "
         "threshold; Gate 3 (190) checks clinical plausibility. Facts that pass enter the structured note (200); "
         "blocked facts go to the review queue (210), whose decisions update the calibration store (220). Gate records "
         "and resolutions are appended to the audit log (230)."], first=True)
para(c, [("b", "FIG. 2 "), "is the per-fact decision: citation/quote check (310), contradiction test (320), "
         "entailment floor (330), acoustic floor when audio exists (340), weighted combination (350), threshold test "
         "(360) and plausibility test (370), ending in REJECTED (380), NEEDS_REVIEW (390) or VERIFIED (400)."])
para(c, [("b", "FIG. 3 "), "is the feedback loop: a blocked fact (500) is resolved by a named clinician (510); for "
         "NEEDS_REVIEW facts the threshold update rule (520) adjusts that clinician's per-field threshold store (530), "
         "which the gate uses on the next case (540); all steps are written to the append-only log (550)."])

# 14 -----------------------------------------------------------------------
c = section(14, "Please provide a complete description of the invention, including its working methodology and "
               "working examples illustrating the inventive aspects of the corresponding invention.")
para(c, [("b", "Working example 1 - real consultation audio, end to end. "),
         "PriMock57 consultation day1_consultation01 (a patient with three days of diarrhoea; separate doctor and "
         "patient channels, 7 min 38 s each) was uploaded to the prototype. Local Whisper (base.en) produced 186 "
         "utterance segments with word-level probabilities; the Gemini extractor drafted 26 facts with citations and "
         "quotes; the gate auto-verified 23 and held 3 for review. Every score is computed, e.g. \"Diarrhoea for the "
         "last three days\" -> entailment 0.996, acoustic 0.896, combined 0.96 -> VERIFIED."], first=True)
para(c, [("b", "Working example 2 - an ASR error caught by the gate. "),
         "The doctor said \"take some time off work\"; the recogniser produced \"take some type of work\". The drafted "
         "plan \"Take two to three days off work to rest\" scored entailment 0.43, acoustic 0.85, combined 0.60 < 0.75 "
         "and was held for review instead of entering the note. When the clinician rejected it, their 'plan' "
         "threshold moved 0.75 -> 0.79 and both events were appended to the audit log."])
para(c, [("b", "Working example 3 - hallucination and mis-citation. "),
         "Against the real segment \"I've just had some diarrhea for the last three days\": \"Diarrhoea for three days\" "
         "-> entailment 1.00, VERIFIED; \"Diarrhoea for three weeks\" -> contradiction 1.00, REJECTED; \"The patient "
         "reports chest pain\" -> REJECTED; a fact quoting \"I take metformin 500 mg twice a day\" (not in the "
         "segment) -> quote alignment 46/100, REJECTED before scoring."])
para(c, [("b", "Working example 4 - faithful but unsafe. "),
         "Transcript: patient allergic to penicillin; assessment \"viral upper respiratory infection\"; doctor: \"I'll "
         "start you on amoxicillin 500 mg three times a day\". The prescription passes transcript fidelity but Gate 3 "
         "flags an allergy-class conflict and an antibiotic-for-viral conflict and holds it for review. \"Take "
         "aspirin for your diarrhoea\" is flagged as an indication mismatch; \"No known drug allergies\" and \"no "
         "history of stomach ulcers\" correctly raise nothing (negation handling)."])
para(c, [("b", "Methodology. "),
         "The prototype is implemented in Python (FastAPI backend, faster-whisper ASR, Hugging Face Transformers NLI, "
         "RapidFuzz alignment, Google Gemini or Anthropic Claude extractors) with a browser front-end (HTML/CSS/JS). "
         "The regression scenarios are reproducible with tests/demo_scenarios.py on the stored real ASR output."])

# 15 -----------------------------------------------------------------------
c = section(15, "Please provide details of experiments conducted and/or third-party validation data, if any, along "
               "with the mathematical equations, formulas, or calculations used in the invention, wherever the "
               "invention performs arithmetic calculations or mathematical operations.")
para(c, "All experiments used real, externally produced data: the PriMock57 dataset of primary-care mock "
        "consultations (Babylon Health, CC-BY 4.0), with its original doctor/patient audio and human transcripts. "
        "Runs were made on a CPU-only laptop (8 cores, 7.8 GB RAM) on 22-23 Sep and 22 Oct 2026.", first=True)
small_table(c, ["Experiment", "Input", "Result"], [
    ["Semantic signal: word-overlap proxy vs. NLI (Gemini extractor)", "day1_consultation01 human transcript",
     "Word overlap: 0 of 21 facts auto-verified (paraphrases blocked). NLI: 17 of 19 auto-verified, 1 needs review, 1 rejected."],
    ["Full audio pipeline (CLI)", "day1_consultation01 audio, 2 channels, 7:38 each",
     "186 segments; 26 facts; 23 VERIFIED, 3 NEEDS_REVIEW; 7 min 44 s total on CPU."],
    ["Full audio pipeline (web app)", "same audio, uploaded through UI",
     "188 segments; 20 facts; 19 VERIFIED, 1 REJECTED; about 5.5 min (LLM output varies between runs)."],
    ["NLI discrimination check", "6 hand-written premise/statement pairs",
     "Paraphrases entailed (0.96-1.00); \"denies chest pain\" vs. reported chest pain: contradiction 0.99; wrong "
     "dose: contradiction 0.997; unsupported asthma history: neutral 0.999."],
    ["Gate regression suite (9 checks)", "real ASR output of day1_consultation01 + synthetic unsafe-prescription transcript",
     "9 of 9 behaved as expected, incl. the weakest-word rule holding \"no blood in the stool\" (built on misheard "
     "\"stalk\", 0.28) that otherwise scored entailment 0.89, combined 0.83."],
    ["Does ASR confidence mark recognition errors?", "day1_consultation01: recognised words aligned to the human "
     "transcript and labelled correct / wrong",
     "Correct words mean probability 0.88, wrong words 0.61; AUROC 0.81 (0.5 = chance). Among content words, 10.8 % are "
     "errors overall vs. 38 % of those below 0.35."],
    ["Vocabulary biasing A/B", "day1_consultation01 audio, three settings",
     "No biasing 16.2 % WER (26/32 medical terms right); initial prompt 19.4 % (26/32); hotwords 27.9 % (30/32, but "
     "134 inserted words). Biasing set to off by default."],
    ["Noise stress test (white noise, seeded)", "day1_consultation01 audio at clean / 20 / 10 / 5 / 0 dB speech SNR, "
     "rule-based extractor",
     "WER 16.2 / 27.9 / 40.6 / 58.0 / 70.6 %; AUROC 0.81 / 0.80 / 0.78 / 0.77 / 0.72; facts auto-verified 92 / 73 / 56 / "
     "50 / 40 % -- the gate withholds proportionally more as recognition degrades."],
    ["Plausibility gate", "5 synthetic fact sets incl. negations", "All conflicts detected; no false flags on negated mentions."],
    ["Adaptive calibration persistence (web)", "reject a NEEDS_REVIEW medications fact",
     "Threshold 0.75 -> 0.79, visible on a different case of the same clinician."],
    ["ASR word error rate", "day1_consultation01 Whisper output vs. PriMock57 human transcript",
     "17.5 % with the earlier initial-prompt setting (231 errors / 1,319 words); 16.2 % with the current default "
     "(no biasing). Mean word probability 0.853; 9.5 % of words below 0.5."],
], [4.3, 4.4, 6.9])
para(c, [("b", "Limitations of the validation so far: "),
         "only 1 of the 57 PriMock57 consultations has been run from audio (downloads of the remaining audio from "
         "the dataset's Git LFS storage failed during this work), so all audio results come from that consultation; "
         "the noise test uses the rule-based extractor, whose verbatim facts exercise the acoustic signal but not the "
         "entailment signal; gate precision/recall against labelled facts has not been measured; the "
         "0.75 / 0.30 / 0.50 / 0.6-0.4 parameters were chosen by design, "
         "not tuned; no clinician user study and no third-party validation have been done; the mixed-recording path "
         "completed transcription and speaker attribution but its extraction step was not completed because the "
         "Gemini API quota was exhausted."])

para(c, [("b", "Mathematical equations and calculations used by the invention")])
eqs = [
    ("E1  Quote alignment (Gate 0): ",
     "m = partial_ratio(q, s) in [0, 100], the best fuzzy similarity of quotation q against any substring of segment "
     "text s (RapidFuzz). The fact is rejected if m < 90 for any quotation."),
    ("E2  Acoustic score (Gate 1): ",
     "A = (1/|Q|) x sum over w in Q of p(w), where Q is the set of recognised words whose character span overlaps the "
     "aligned quotation span(s) and p(w) is the recogniser's probability for word w. Rejected if A < 0.50. "
     "A is undefined (not computed) when the input has no audio."),
    ("E3  Semantic probabilities (Gate 2): ",
     "(E, N, C) = softmax(z), where z are the NLI model's three output logits for (premise = cited segments, "
     "hypothesis = statement); E + N + C = 1. Rejected if C >= 0.50 or E < 0.30."),
    ("E4  Combined confidence: ", "S = 0.6 E + 0.4 A when audio exists; S = E otherwise."),
    ("E5  Admission rule: ", "VERIFIED if S >= t(c, f) and no plausibility conflict; otherwise NEEDS_REVIEW, where "
     "t(c, f) is clinician c's threshold for record field f (initially 0.75)."),
    ("E6  Threshold update: ", "t <- clip(t + 0.2 (tau - t), 0.55, 0.95), with tau = S of the resolved fact on approve "
     "and tau = 0.95 on reject; applied only to NEEDS_REVIEW facts."),
    ("E7  Word error rate (evaluation): ", "WER = (S_sub + D + I) / N, the word-level Levenshtein distance between "
     "the normalised recognised text and the normalised reference transcript, divided by the reference length N."),
    ("E8  Weakest-word rule (Gate 1): ", "W = min over content words w in Q of p(w); a fact with S >= t is still "
     "NEEDS_REVIEW if W < 0.35."),
    ("E9  AUROC (evaluation): ", "AUROC = P(p(w_err) < p(w_ok)) over all pairs of a wrongly and a correctly recognised "
     "word (ties count 1/2), computed with the Mann-Whitney rank sum; 0.5 means confidence carries no information "
     "about errors, 1.0 means it separates them perfectly."),
    ("E10  Noise at a target SNR: ", "noise variance = P_speech / 10^(SNR/10), where P_speech is the mean power of the "
     "loudest 30 % of 25 ms frames of the channel."),
]
for h_, t in eqs:
    para(c, [("b", h_), t], size=10.5)
para(c, [("b", "Worked calculations (real values from section 14): ")], size=10.5)
for t in [
    "Verified fact \"Diarrhea for the last three days\": E = 0.996, A = 0.896 -> S = 0.6 x 0.996 + 0.4 x 0.896 = "
    "0.598 + 0.358 = 0.956 >= 0.75 -> VERIFIED.",
    "ASR-error fact \"Take two to three days off work to rest\": E = 0.426, A = 0.853 -> S = 0.256 + 0.341 = 0.597 "
    "< 0.75 -> NEEDS_REVIEW.",
    "Clinician rejects it: t = 0.75 + 0.2 x (0.95 - 0.75) = 0.79 (plan threshold for that clinician).",
    "Had the clinician approved it instead: t = 0.75 + 0.2 x (0.597 - 0.75) = 0.719.",
    "Word error rate: 231 word errors / 1,319 reference words = 0.175 = 17.5 % (earlier setting); 213 / 1,319 = 16.2 % "
    "(current default).",
    "Weakest word: quotation \"no blood, yeah, just watery and loose stalk.\" -> content words no 0.93, blood 0.99, "
    "just 0.95, watery 0.86, loose 0.59, stalk 0.28 -> W = 0.28 < 0.35 -> NEEDS_REVIEW although S = 0.83 >= 0.75.",
]:
    bullet(c, t)

# 16 -----------------------------------------------------------------------
c = section(16, "Please provide a set of instructions or an exemplary set of code, including the code type, version, "
                "and any modifications or parameter tuning, where the invention primarily relies on software, code, "
                "or an algorithm.")
para(c, [("b", "Code type: "), "Python 3.13.1 (backend and pipeline); HTML / CSS / JavaScript (browser front-end). "
         "The invention is implemented entirely in software."], first=True)
small_table(c, ["Component", "Library / model", "Version"], [
    ["Speech recognition", "faster-whisper (CTranslate2 backend), model Whisper base.en, int8, CPU", "faster-whisper 1.2.1; ctranslate2 4.8.2"],
    ["Entailment (NLI)", "PyTorch + Hugging Face Transformers; MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli", "torch 2.8.0; transformers 5.17.0"],
    ["Quote alignment", "RapidFuzz partial_ratio_alignment", "rapidfuzz 3.13.0"],
    ["LLM extractor / speaker roles", "google-genai (Gemini 3.6 Flash, fallbacks 3.5 / 3.7 Flash); anthropic (Claude, optional)", "google-genai 1.38.0; anthropic 0.68.0"],
    ["Web backend", "FastAPI + Uvicorn; SQLite", "fastapi 0.141.1; uvicorn 0.52.4"],
], [3.6, 7.6, 4.4])
para(c, [("b", "Source layout (prototype/): "), "src/transcribe.py (ASR, utterance splitting), src/medical_terms.py "
         "(vocabulary biasing and confidence-gated correction), src/speakers.py (roles for mixed audio), src/extractor.py "
         "and src/llm.py (fact drafting), src/grounding.py (Gates 0-2 and combination), src/entailment.py (NLI), "
         "src/clinical_plausibility.py (Gate 3), src/calibration.py, src/audit.py, src/pipeline.py (orchestration), "
         "api/server.py (web API, background jobs, audio streaming), web/ (user interface), tests/demo_scenarios.py."])
para(c, [("b", "Instructions to run: ")])
for i, t in enumerate([
    "pip install -r prototype/requirements.txt",
    "Optional LLM: create prototype/.env containing GEMINI_API_KEY=<key> (or ANTHROPIC_API_KEY).",
    "Command line: python main.py run --doctor-audio doctor.wav --patient-audio patient.wav [--llm]",
    "Web application: python api/server.py, then open http://127.0.0.1:8420, sign up, add a patient, New case -> Audio recording.",
    "Regression check: python tests/demo_scenarios.py (9 checks on real ASR output; prints ALL SCENARIOS BEHAVED AS EXPECTED).",
    "Evaluation: python eval/run_eval.py <consultations> | --all ; python eval/noise_stress.py ; python eval/vocab_ab.py <consultations>",
], 1):
    numbered(c, i, [("code", t)])
para(c, [("b", "Exemplary code - the per-fact gate decision (abridged from src/grounding.py): ")])
code = [
    "def decide(fact, cited, span_words, nli):",
    "    E = nli['entailment']                      # Gate 2",
    "    if nli['contradiction'] >= 0.50: return REJECTED('evidence contradicts')",
    "    if E < 0.30:                     return REJECTED('not entailed')",
    "    A = mean(w.prob for w in span_words) if span_words else None   # Gate 1",
    "    if A is not None and A < 0.50:   return REJECTED('low acoustic confidence')",
    "    W = min(w.prob for w in content_words(span_words)) if span_words else None",
    "    S = E if A is None else 0.6 * E + 0.4 * A",
    "    t = calibration.threshold_for(clinician, fact.field)          # starts at 0.75",
    "    if S >= t and W is not None and W < 0.35: return NEEDS_REVIEW('weak key word')",
    "    return VERIFIED if S >= t else NEEDS_REVIEW",
    "# Gate 0 runs before this (every quote must align >= 90/100 inside its segment);",
    "# Gate 3 (clinical_plausibility.apply_plausibility_checks) runs after it.",
]
for line in code:
    p_ = c.add_paragraph()
    p_.paragraph_format.space_after = Pt(0)
    add_runs(p_, [("code", line)], size=9.5)
c.add_paragraph().paragraph_format.space_after = Pt(2)
para(c, [("b", "Modifications and parameter tuning: ")])
for t in [
    "Pretrained models are used unmodified (no fine-tuning or retraining).",
    "ASR run with word_timestamps=True, vad_filter=True, condition_on_previous_text=False (prevents repetition "
    "loops on long audio); vocabulary biasing selectable via ASR_VOCAB_MODE = none (default) | initial_prompt | "
    "hotwords, chosen from the A/B test in section 15; utterances re-split at pauses >= 0.8 s.",
    "NLI inputs truncated to 512 tokens (premise truncated first), batch size 8.",
    "LLM output constrained to a JSON schema; max 16,000 output tokens; 3 attempts with exponential back-off "
    "(2-15 s) on HTTP 429/5xx, then fallback models.",
    "All gate thresholds and weights (section 23) were set by design and have not yet been tuned on data.",
]:
    bullet(c, t)

# 17 -----------------------------------------------------------------------
c = section(17, "Please provide details of the training data, including its source, type, and relevant characteristics, "
                "where the invention relates to a machine learning (ML) model. Also, specify the ML model used and "
                "explain how the ML model is trained, implemented, and utilized in the invention.")
para(c, [("b", "No model is trained by the inventors. "), "The invention is a verification-and-enforcement method that "
         "uses the outputs of pretrained models; all models are used exactly as released by their authors. The "
         "training data below is that of the original authors, as stated in their publications / model cards."],
     first=True)
small_table(c, ["Model", "Type and size", "Training data (by its authors)", "How it is used in the invention"], [
    ["Whisper base.en (OpenAI), via faster-whisper",
     "Transformer encoder-decoder speech recogniser, about 74 M parameters",
     "About 680,000 hours of weakly supervised multilingual audio-transcript pairs collected from the web "
     "(Radford et al., ICML 2023); the .en model is English-only.",
     "Transcribes the consultation locally; its per-word probabilities form the acoustic signal (Gate 1)."],
    ["DeBERTa-v3-base-mnli-fever-anli (M. Laurer)",
     "DeBERTa-v3 cross-encoder classifier, about 184 M parameters, 3 classes",
     "DeBERTa-v3 pre-trained by Microsoft (He et al., ICLR 2023), then fine-tuned on the MultiNLI, FEVER-NLI and "
     "Adversarial NLI datasets of premise-hypothesis pairs (model card).",
     "Scores P(entailment / neutral / contradiction) of each drafted fact against its cited segments (Gate 2)."],
    ["Gemini 3.6 Flash (Google), optional",
     "Hosted large language model (size not published)",
     "Not disclosed by the provider.",
     "Drafts facts with citations and verbatim quotes; labels speakers for mixed recordings. Its output is never "
     "trusted without Gates 0-3."],
], [3.3, 3.2, 4.8, 4.3])
para(c, [("b", "Data used by the inventors (evaluation, not training): "),
         "PriMock57 (Babylon Health, CC BY 4.0; Papadopoulos Korfiatis et al., ACL 2022): 57 mock primary-care "
         "consultations with real clinicians and actor patients; separate doctor and patient audio channels (16 kHz "
         "mono WAV); human transcripts; reference notes. Statistics computed by us: 8.6 h of conversation, 6,727 "
         "transcribed utterances, 85,914 words, mean 9.1 min per consultation (3.8-14.3 min). Used to run the pipeline "
         "and to measure word error rate; a development/test split of the 57 consultations is planned for tuning the "
         "parameters of section 23."])
para(c, [("b", "What is implemented rather than learned: "),
         "Gate 0 (fuzzy alignment), the acoustic averaging, the combination rule, the clinical-plausibility tables and "
         "the adaptive threshold update are deterministic algorithms written by the inventors (section 15, E1-E6). "
         "The threshold update is the only component that changes with use, and it adapts from clinician decisions, "
         "not from a training set."])


# 18 -----------------------------------------------------------------------
c = section(18, "Please provide details of any public disclosure done/ any publication made.")
para(c, [("b", "Public source-code repository: "),
         "the prototype was pushed to a public GitHub repository, github.com/sparsh-karna/medical-scribe-ai-patent, "
         "first commit 22 Sep 2026. ",
         flag("This is a public disclosure of the invention before filing and may be treated as prior art against it. "
              "Recommended: make the repository private immediately and consult the IP cell about filing a provisional "
              "application at once.")], first=True)
para(c, "No journal or conference publication, product launch or public demonstration has been made.")

# 19 -----------------------------------------------------------------------
c = section(19, "What is the stage/level of development of the Invention?")
para(c, [("b", "a. At a basic conceptualization stage? "), "No."], first=True)
para(c, [("b", "b. Completed and results validated? "),
         "Partially. A working prototype of the complete pipeline (audio upload -> local transcription -> extraction "
         "-> three-signal gate -> review queue -> calibration -> audit) is implemented and validated in the laboratory "
         "on real consultation data (section 15). Large-scale validation (all 57 consultations, gate precision/recall, "
         "clinician study) and EHR integration are pending."])

# 20 -----------------------------------------------------------------------
c = section(20, "What are the aspects of your disclosure that you want to claim/monopolize? (Proposed Claims)")
claims = [
    ("Claim 1 (Independent - method): ",
     "A computer-implemented method for generating a clinical record from a recorded patient encounter, comprising: "
     "(a) transcribing audio of the encounter with a speech recogniser into transcript segments, each word of which "
     "carries a recognition confidence value; (b) generating, by an extraction module, a plurality of candidate "
     "clinical facts, each candidate fact comprising a record field, a statement, and at least one citation "
     "identifying a transcript segment together with a verbatim quotation from that segment; (c) for each candidate "
     "fact, verifying that each quotation occurs in its cited segment, and rejecting the fact if it does not; "
     "(d) computing an acoustic score from the recognition confidence values of the words spanned by the verified "
     "quotation(s); (e) computing, with a natural-language-inference model, an entailment probability and a "
     "contradiction probability that the cited segment(s) support the statement; (f) rejecting the fact when the "
     "contradiction probability exceeds a contradiction limit or either score is below a respective floor, and "
     "otherwise combining the scores into a combined confidence; (g) automatically inserting the fact into the "
     "clinical record only when the combined confidence meets a threshold associated with its record field, and "
     "otherwise withholding the fact from the record and placing it in a review queue; and (h) appending a record of "
     "each determination to an append-only audit log."),
    ("Claim 2 (Dependent): ", "The method of claim 1, wherein, when the encounter is provided as text without audio, "
     "the acoustic score is recorded as unavailable and the determination of step (g) is made on the entailment "
     "probability alone, the basis of the determination being recorded in the audit log."),
    ("Claim 3 (Dependent): ", "The method of claim 1, further comprising, upon a named clinician approving or rejecting "
     "a fact from the review queue, updating the threshold for that record field and that clinician toward the fact's "
     "combined confidence on approval and toward an upper bound on rejection, the threshold being clamped to a "
     "predetermined range, wherein the floors of step (f) are not updated."),
    ("Claim 4 (Dependent): ", "The method of claim 1, further comprising a clinical-plausibility step in which a "
     "medication or plan fact otherwise eligible for insertion is withheld when it conflicts with another fact of the "
     "same encounter by at least one of: a drug-class allergy, an antibiotic prescribed against a viral assessment, a "
     "stated condition outside the drug's indications, a contraindicating condition, or an interacting drug, negated "
     "mentions being disregarded."),
    ("Claim 5 (Dependent): ", "The method of claim 1, wherein the acoustic score is the mean of the recognition "
     "confidence values of the words whose character positions overlap the aligned quotation, and the words below a "
     "weakness limit are reported with the determination."),
    ("Claim 6 (Dependent): ", "The method of claim 1, wherein step (a) comprises correcting a recognised word to a term "
     "of a medical vocabulary only when that word's recognition confidence is below a correction limit, the originally "
     "recognised word being retained for audit."),
    ("Claim 7 (Dependent): ", "The method of claim 1, wherein speaker roles are assigned from separate recording "
     "channels or, for a single mixed recording, inferred by a language model and marked as inferred."),
    ("Claim 8 (Dependent): ", "The method of claim 1, wherein the review queue presents, for each withheld fact, the "
     "reason for withholding, the verified quotations highlighted within the transcript, and a control that plays back "
     "only the audio interval of the cited segment."),
    ("Claim 9 (Dependent): ", "The method of claim 5, further comprising determining the lowest recognition confidence "
     "among the content words of the quotation, and withholding the fact from automatic insertion when that lowest "
     "confidence is below a weakest-word limit, even when the combined confidence meets the threshold."),
    ("Claim 10 (Independent - system): ", "A system comprising one or more processors and memory storing instructions "
     "that, when executed, perform the method of any of claims 1 to 9."),
    ("Claim 11 (Independent - medium): ", "A non-transitory computer-readable medium storing instructions that, when "
     "executed by a processor, cause the processor to perform the method of any of claims 1 to 9."),
]
first = True
for head, text in claims:
    para(c, [("b", head), text], first=first, space_after=6)
    first = False
para(c, [("i", "Note: draft claims for discussion. Scope, wording and novelty must be reviewed by a registered patent "
               "agent against the prior art in sections 5 and 21 (particularly US 11,222,716 B2) before filing.")], size=10)

# 21 -----------------------------------------------------------------------
c = section(21, "Have you conducted novelty/inventiveness search for your invention? If yes, what are the databases "
                "/references used by you? What are the search results?")
para(c, "Yes -- a preliminary search of Google Patents, product documentation (AWS, Abridge) and the research "
        "literature (ACL Anthology, arXiv). It is not a professional freedom-to-operate or patentability search.",
     first=True)
small_table(c, ["Sno", "Reference", "Existing Idea", "Our Invention"], [
    ["1", "US 11,222,716 B2 (Nuance / Microsoft)", "Links audio, transcript and report; a confidence model exposes a "
     "draft section only if editing is judged faster than rewriting.",
     "Admits or blocks each individual fact using that fact's own cited evidence (quote check, acoustic score over "
     "quoted words, NLI entailment/contradiction), plus plausibility gate and per-clinician adaptive thresholds."],
    ["2", "US 10,719,222 B2 / US 11,227,688 B2 (Google)", "Transcript + generated note; extracted phrases linked to "
     "transcript/audio; physician verifies by inspection.", "Verification is automatic and enforcing; the clinician "
     "only sees facts the gate blocked, each with a stated reason."],
    ["3", "US 6,006,183 A (IBM)", "Per-word ASR confidence displayed by colour above a user threshold.",
     "Word confidence is propagated to the specific note statement that quotes those words and used to gate it."],
    ["4", "AWS HealthScribe; Abridge Linked Evidence", "Every summary sentence carries links to source segments / audio "
     "for optional human validation.", "Links are verified by machine and used to hard-block unsupported facts; "
     "provenance of every line recorded in an append-only log."],
    ["5", "SummaC (TACL 2022); FactCC (EMNLP 2020)", "NLI-based scoring of summary factual consistency as an offline "
     "evaluation metric.", "NLI used online, per fact, on the fact's own cited evidence, as an enforcing gate in the "
     "documentation workflow, combined with an acoustic signal."],
], [1.0, 3.6, 5.3, 5.7])

# 22 -----------------------------------------------------------------------
c = section(22, "Do you feel that a person of \"average\" skill (not-extraordinary skill) in your area of technology "
                "would have arrived at your invention with existing knowledge in public domain? If no, what could be "
                "the reasons for the same?")
para(c, [("b", "No. "), "Reasons:"], first=True)
for t in [
    "The field's established direction is transparency for the human (evidence links, highlighting); moving to "
    "machine enforcement that withholds content from the record is a different design choice the products and "
    "patents above did not take.",
    "Combining a signal from speech recognition (word probabilities) with a signal from text reasoning (entailment) "
    "requires aligning the fact's quoted evidence back to individual recognised words by character offset -- the "
    "two signals live in different subsystems in existing pipelines.",
    "Requiring verbatim quotations and verifying them before scoring converts a free-form LLM output into a "
    "checkable claim; the prior art trusts the model's own citation.",
    "The prior-art confidence gate (US 11,222,716) optimises editing effort, which teaches away from per-fact "
    "safety gating.",
    "Adaptive per-clinician thresholds with fixed, non-adaptive safety floors, and explicit handling of an absent "
    "signal rather than imputation, are not suggested by the references.",
]:
    bullet(c, t)

# 23 -----------------------------------------------------------------------
c = section(23, "Kindly provide broad workable ranges for all parameters involved in the invention, including the "
               "working parameters and ranges applicable to each component utilized in the system.")
small_table(c, ["Parameter", "Prototype value", "Workable range"], [
    ["Quote alignment minimum (fuzzy score)", "90 / 100", "80 - 100"],
    ["Contradiction limit P(contradiction)", "0.50", "0.30 - 0.80"],
    ["Entailment floor P(entailment)", "0.30", "0.10 - 0.60"],
    ["Acoustic floor (mean word probability)", "0.50", "0.30 - 0.80"],
    ["Weights semantic : acoustic", "0.6 : 0.4", "0.5 : 0.5 to 0.9 : 0.1"],
    ["Initial auto-insert threshold per field", "0.75", "0.55 - 0.95"],
    ["Threshold bounds", "[0.55, 0.95]", "lower 0.40 - 0.70; upper 0.85 - 0.99"],
    ["Calibration learning rate", "0.2", "0.05 - 0.5"],
    ["Weak-word marker", "0.50", "0.30 - 0.70"],
    ["Weakest quoted content word (review trigger)", "0.35", "0.20 - 0.50"],
    ["Medical-term correction only below ASR probability", "0.70", "0.50 - 0.90"],
    ["Utterance split at pause", "0.8 s", "0.4 - 2.0 s"],
    ["ASR model", "faster-whisper base.en (int8, CPU)", "any ASR giving word-level confidence"],
    ["NLI model", "DeBERTa-v3-base MNLI/FEVER/ANLI", "any entailment model or LLM verifier"],
    ["Extractor", "rule-based; Gemini 3.6 Flash; Claude", "any"],
], [6.2, 4.4, 5.0])
para(c, [("b", "Working parameters per component")])
small_table(c, ["Component", "Parameter", "Prototype value", "Workable range"], [
    ["Audio input", "Sample rate / channels", "16 kHz mono PCM WAV (MP3, M4A, FLAC, OGG, WebM accepted)", "8-48 kHz; any codec the decoder reads"],
    ["Audio input", "Recording length", "7.6 min tested", "about 1-60 min"],
    ["Audio input", "Maximum upload size", "300 MB", "50 MB - 2 GB"],
    ["ASR", "Model size", "base.en (about 74 M parameters)", "tiny.en to large-v3 (39 M - 1.5 B)"],
    ["ASR", "Compute type / device", "int8 on CPU", "int8 / float16 / float32; CPU or GPU"],
    ["ASR", "Voice-activity detection", "on (Silero VAD, library default)", "on / off"],
    ["ASR", "Decoding window", "30 s (Whisper fixed)", "fixed by model"],
    ["Medical vocabulary", "Terms in vocabulary", "about 65 drug / symptom terms", "10 - 200 (prompt limit about 224 tokens)"],
    ["Medical vocabulary", "Biasing mode", "none (default)", "none / initial prompt / hotwords"],
    ["Medical vocabulary", "Fuzzy-correction similarity cutoff", "0.82", "0.75 - 0.95"],
    ["Extractor (LLM)", "Maximum output tokens", "16,000", "4,000 - 64,000"],
    ["Extractor (LLM)", "Retries / back-off", "3 attempts, 2-15 s", "1 - 5 attempts"],
    ["NLI", "Maximum input length", "512 tokens", "256 - 1,024"],
    ["NLI", "Batch size", "8", "1 - 64"],
    ["Plausibility gate", "Negation look-back window", "60 characters, up to 4 words", "30 - 120 characters"],
    ["Web server", "Concurrent pipeline runs", "1 (models share CPU / RAM)", "1 - N (hardware dependent)"],
    ["Hardware", "Minimum tested", "8-core CPU, 7.8 GB RAM, no GPU", "4+ cores, 8+ GB RAM; GPU optional"],
], [3.0, 3.8, 4.6, 4.2])
para(c, [("i", "The prototype values were set by design and have not yet been optimised on data.")], size=10)

# 24 -----------------------------------------------------------------------
c = section(24, "Commercialization Data (at least a minimum of 2 companies must be provided and preferably up to 5)")
para(c, [("b", "a. Names and addresses of companies which might be interested in this technology:")], first=True)
companies = [
    ("Augnito India Private Limited", "Meher House, 1st Floor, 15 Cawasji Patel Road, Fort, Mumbai, Maharashtra 400001, India",
     "Indian medical speech-recognition and ambient-documentation vendor."),
    ("Eka Care (Orbi Health Private Limited)", "Villa No. 28, Plot No. 331/A, Road No. 5, EPIP, Whitefield, Bengaluru, "
     "Karnataka 560066, India", "Indian digital-health platform with AI documentation for doctors."),
    ("Abridge AI, Inc.", "500 Grant Street, Suite 2900, Pittsburgh, PA 15219, USA",
     "Ambient AI documentation; offers Linked Evidence (would gain enforcement)."),
    ("Nuance Communications, Inc. (a Microsoft company)", "1 Wayside Road, Burlington, MA 01803, USA",
     "DAX Copilot ambient clinical documentation."),
    ("Suki AI, Inc.", "1823 El Camino Real, Redwood City, CA 94063, USA", "AI voice assistant and ambient documentation."),
]
for i, (name, addr, why) in enumerate(companies, 1):
    numbered(c, i, [("b", name), " -- ", flag(addr), f". {why}"])
para(c, [flag("Addresses were taken from public company directories (Tofler/ZaubaCorp, Craft.co, SalesTools, "
              "Yahoo Local, SEC filings) and must be confirmed on each company's official website before submission.")],
     size=10)
para(c, [("b", "b. Short marketing profile")])
para(c, "Ambient AI scribes are being adopted rapidly, but health systems' main barrier is trust: an AI-drafted note "
        "that is mostly correct still has to be re-read line by line to find the few errors that matter. This "
        "technology is a verification layer that sits between any scribe and the EHR. It lets only evidence-backed "
        "facts into the record automatically, withholds the rest with a specific reason and a one-click audio replay, "
        "adapts to each clinician, and leaves a per-line audit trail for compliance and medico-legal defence. Unlike "
        "evidence linking (AWS HealthScribe, Abridge), it enforces rather than suggests; unlike section-level "
        "confidence gating (US 11,222,716), it decides per fact on that fact's own evidence. It can be licensed to "
        "scribe vendors as an SDK or offered to hospitals as an on-premise gateway; ASR and verification run locally, "
        "which suits data-residency requirements such as India's DPDP Act, 2023.")

# 25 -----------------------------------------------------------------------
c = section(25, "Provide available data or information on market potential/size, adoption trends, industry analysis, "
                "and projected growth.")
small_table(c, ["Year", "Estimated Market Size", "Growth Drivers", "Notable Existing Devices"], [
    ["2025", [flag("USD 1.2 - 1.4 billion")], "Clinician burnout and documentation burden; maturing LLMs; EHR vendor "
     "integrations", "Nuance/Microsoft DAX Copilot, Abridge, Suki, AWS HealthScribe"],
    ["2034-2035", [flag("USD 8.9 - 15.1 billion")], "Health-system-wide rollouts; ambient AI in outpatient and "
     "emergency care; demand for auditability and safety of AI output", "As above, plus Augnito, Nabla, Eka Care"],
    ["CAGR", [flag("about 20 - 29 % per year")], "Estimates vary widely between analysts", "--"],
], [2.0, 3.6, 5.3, 4.7])
para(c, [flag("Figures are third-party market-research estimates and differ by source: Astute Analytica (USD 1.2 bn in "
              "2025 to USD 15.1 bn by 2035, 28.8 % CAGR) and Towards Healthcare (USD 1.39 bn in 2025 to USD 8.93 bn "
              "by 2035, 20.48 % CAGR). Verify before citing; other reports range from 19 % to 48 % CAGR.")], size=10)

# 26 -----------------------------------------------------------------------
c = section(26, "Please provide the names of the inventors involved in the Invention")
for _ in range(3):
    bullet(c, [flag("[Inventor name]  [Registration number]")])
para(c, [flag("To be completed by the inventors.")], size=10)

# 27 -----------------------------------------------------------------------
c = section(27, "User Information")
para(c, [("b", "a. Who all are the potential users of the technology? ")], first=True)
para(c, "Doctors and other clinicians who document consultations (general practice, outpatient specialties, "
        "emergency care, telemedicine); hospitals and clinic chains; vendors of AI scribes and EHR systems; clinical "
        "documentation-integrity and compliance teams; medical-legal auditors.")
para(c, [("b", "b. Age group of the user? ")])
para(c, "Adult healthcare professionals (typically 22-70). Patients of any age benefit indirectly through safer records.")
para(c, [("b", "c. Expected benefits to the user? ")])
para(c, "Less time re-reading AI drafts (only blocked facts need attention); fewer transcription and hallucination "
        "errors in the record; clinically unsafe instructions caught before sign-off; one-click evidence and audio "
        "for each questioned fact; thresholds that fit the individual clinician; an audit trail for compliance.")
para(c, [("b", "d. Cost advantage when compared to available solutions ")])
para(c, "The gate uses open models run locally on commodity CPUs (demonstrated on a 7.8 GB RAM laptop), so "
        "verification adds no per-use API cost and no cloud data transfer; it can be added to an existing scribe "
        "rather than replacing it. Avoided cost of documentation errors (claim denials, adverse events, litigation) "
        "is the main economic benefit.")

# 28 -----------------------------------------------------------------------
c = section(28, "What is Technology readiness level of your invention? (Tick the appropriate TRL)")
trl = [("TRL 1", "Basic principles observed"), ("TRL 2", "Technology concept formulated"),
       ("TRL 3", "Experimental proof of concept"), ("TRL 4", "Technology validated in a lab"),
       ("TRL 5", "Technology validated in a relevant environment"), ("TRL 6", "Technology demonstrated in a relevant environment"),
       ("TRL 7", "System prototype demonstration in an operational environment"), ("TRL 8", "System complete and qualified"),
       ("TRL 9", "Actual system proven in an operational environment")]
t = c.add_table(rows=2, cols=9)
t.style = "Table Grid"
for i, (k, v) in enumerate(trl):
    add_runs(t.rows[0].cells[i].paragraphs[0], ("☑ " if k == "TRL 4" else "☐ ") + k, size=9, bold=True)
    add_runs(t.rows[1].cells[i].paragraphs[0], v, size=8)
    if k == "TRL 4":
        shade(t.rows[0].cells[i], "E2EFDA"); shade(t.rows[1].cells[i], "E2EFDA")
para(c, [("b", "Selected: TRL 4 "), "-- the complete pipeline works and has been validated in the laboratory on real "
         "consultation audio and transcripts; it has not been tested in a clinical environment."])

# 29 -----------------------------------------------------------------------
c = section(29, "Any additional notes or remarks.")
for t in [
    [flag("Public disclosure: the GitHub repository is public (see section 18). Make it private and consult the IP cell "
          "about filing a provisional application immediately.")],
    "The prototype uses off-the-shelf models (Whisper, DeBERTa NLI, Gemini/Claude) without training; the claimed "
    "invention is the verification-and-enforcement method, not any model.",
    "Clinical-plausibility knowledge tables are a small curated subset intended as a stand-in for RxNorm / "
    "SNOMED-CT / openFDA in production (section 11).",
    "Vocabulary biasing: Whisper's initial prompt only conditions the first 30-second window when "
    "condition_on_previous_text is off; hotwords condition every window but, in our A/B test, inserted many words and "
    "raised WER from 16.2 % to 27.9 %. Biasing is therefore off by default; the confidence-gated correction stays on.",
    "The weakest-word rule trades automation for safety: on day1_consultation01 about one in three content words "
    "below 0.35 is a real recognition error (3.5 x the base rate), so roughly two in three such reviews are false alarms.",
    "Planned next steps: run all 57 PriMock57 consultations from audio once the dataset's audio downloads succeed "
    "(eval/run_eval.py is ready and resumable); label drafted facts correct / incorrect to measure gate precision and "
    "recall; tune the parameters in section 23 on a development split; clinician usability study.",
]:
    bullet(c, t if isinstance(t, list) else [t])

for row in table.rows:
    set_cell_width(row.cells[0], NUM_W)
    set_cell_width(row.cells[1], BODY_W)
    # drop the empty paragraph a new cell starts with when content was appended after it
    body = row.cells[1]._tc
    first = body.find(qn("w:p"))
    if first is not None and len(body.findall(qn("w:p")) + body.findall(qn("w:tbl"))) > 1             and not "".join(t.text or "" for t in first.iter(qn("w:t"))) and first.find(".//" + qn("w:drawing")) is None:
        body.remove(first)

doc.save(OUT)
print("saved", OUT)
