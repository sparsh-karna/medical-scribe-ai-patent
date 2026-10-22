"""
Demonstration + regression check of the three-signal gate on real data.

Every score printed here is computed by the real pipeline components --
the NLI entailment model, the ASR word probabilities recorded by
faster-whisper on real PriMock57 audio (sample_data/asr_output/), the
evidence-quote verifier, and the clinical-plausibility tables. Nothing is
hard-coded except the drafted facts themselves, which stand in for what
an extractor (rule-based or LLM) would hand to the gate.

Run with:  python tests/demo_scenarios.py
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.env import load_env
load_env()

from src.calibration import CalibrationStore
from src.extractor import Fact
from src.grounding import GroundingEngine
from src.pipeline import resolve_fact, run_pipeline

DEMO_DIR = os.path.join(os.path.dirname(__file__), "_demo_out")
ASR_FIXTURE = os.path.join(ROOT, "sample_data", "asr_output", "day1_consultation01_base.en.json")
UNSAFE_RX = os.path.join(ROOT, "sample_data", "gate_demo_unsafe_prescription.json")


def fact(field, value, evidence):
    return Fact(field, value, list(dict.fromkeys(e["segment_id"] for e in evidence)), "demo", evidence)


def show(title, f, r):
    acoustic = "n/a" if r.acoustic_score is None else f"{r.acoustic_score:.2f}"
    print(f"\n--- {title}\n    fact:      \"{f.value}\"\n"
          f"    signals:   entailment {r.nli.get('entailment', 0):.2f} / contradiction "
          f"{r.nli.get('contradiction', 0):.2f} / acoustic {acoustic} / combined {r.combined_confidence:.2f}\n"
          f"    decision:  {r.status} -- {r.reason}")


def main():
    os.makedirs(DEMO_DIR, exist_ok=True)
    audit_path = os.path.join(DEMO_DIR, "audit_log.jsonl")
    calibration_path = os.path.join(DEMO_DIR, "calibration_state.json")
    for p in (audit_path, calibration_path):
        if os.path.exists(p):
            os.remove(p)

    with open(ASR_FIXTURE, encoding="utf-8") as fh:
        segments = json.load(fh)["segments"]
    seg = {s["id"]: s for s in segments}
    print(f"Real ASR transcript: {len(segments)} segments, {ASR_FIXTURE}")
    print(f"  #6 PATIENT: {seg[6]['text']}")

    q6 = "I've just had some diarrhea for the last three days"
    q41 = "I vomited at the start of the symptoms, but now I've stopped vomiting."
    scenarios = [
        ("1. Faithful paraphrase of clearly recognised speech (should auto-insert)", "VERIFIED",
         fact("history_of_present_illness", "Vomited at symptom onset; vomiting has now stopped.",
              [{"segment_id": 41, "quote": q41}])),
        ("1b. Correct but uncertain key word: 'diarrhea' heard at 0.13 (weakest-word rule -> review)", "NEEDS_REVIEW",
         fact("chief_complaint", "Diarrhoea for three days.", [{"segment_id": 6, "quote": q6}])),
        ("1c. Real ASR error: 'stool' heard as 'stalk' at 0.28 (weakest-word rule -> review)", "NEEDS_REVIEW",
         fact("history_of_present_illness", "No blood in the stool; stools are watery and loose.",
              [{"segment_id": 14, "quote": "no blood, yeah, just watery and loose stalk."}])),
        ("2. Hallucinated detail: wrong duration (contradiction -> blocked)", "REJECTED",
         fact("chief_complaint", "Diarrhoea for three weeks.", [{"segment_id": 6, "quote": q6}])),
        ("3. Unsupported claim attached to a real citation (blocked)", "REJECTED",
         fact("history_of_present_illness", "The patient reports chest pain.", [{"segment_id": 6, "quote": q6}])),
        ("4. Invented evidence quote (citation integrity -> blocked)", "REJECTED",
         fact("medications", "Takes metformin 500 mg twice daily.",
              [{"segment_id": 6, "quote": "I take metformin 500 mg twice a day"}])),
        ("5. Real ASR error: 'time off work' heard as 'type of work' (borderline -> review)", "NEEDS_REVIEW",
         fact("plan", "Take two to three days off work to rest.", [
             {"segment_id": 153, "quote": "I would certainly advise you to take"},
             {"segment_id": 154, "quote": "some type of work."},
             {"segment_id": 155, "quote": "Actually, I know you're quite keen to work, I would say, in the next two to three days,"},
             {"segment_id": 157, "quote": "as an infection clears from your system, take some time off and rest."}])),
    ]

    calibration = CalibrationStore(calibration_path)
    results = GroundingEngine(segments, calibration).evaluate_many([f for _, _, f in scenarios])
    failures = []
    for (title, expected, f), r in zip(scenarios, results):
        show(title, f, r)
        if r.status != expected:
            failures.append(f"{title}: expected {expected}, got {r.status}")

    # --- adaptive calibration: clinician rejects the borderline fact ---
    k = next(i for i, (t, _, _) in enumerate(scenarios) if t.startswith("5."))
    borderline_fact, borderline = scenarios[k][2], results[k]
    case = {"segments": segments, "facts": [{
        "fact_id": "F001", "field": borderline_fact.field, "value": borderline_fact.value,
        "cited_segment_ids": borderline_fact.cited_segment_ids, "status": borderline.status,
        "combined_confidence": borderline.combined_confidence, "reason": borderline.reason, "resolution": None,
    }]}
    before = CalibrationStore(calibration_path).threshold_for("plan")
    if borderline.status == "NEEDS_REVIEW":
        resolve_fact(case, "F001", "reject", "Dr. Patel", audit_path=audit_path, calibration_path=calibration_path)
    after = CalibrationStore(calibration_path).threshold_for("plan")
    print(f"\n--- 6. Clinician rejects scenario 5 -> 'plan' auto-insert threshold {before:.2f} -> {after:.2f}")
    if not after > before:
        failures.append("6. calibration: threshold did not tighten after a reject")

    # --- clinical-plausibility gate, full pipeline on the unsafe-prescription transcript ---
    with open(UNSAFE_RX, encoding="utf-8") as fh:
        rx = json.load(fh)
    rx_case = run_pipeline(rx["segments"], use_llm=False, audit_path=audit_path,
                           calibration_path=os.path.join(DEMO_DIR, "rx_calibration.json"),
                           input_meta={"input_mode": "text", "origin": "gate demo"})
    print("\n--- 7. Faithfully-transcribed but unsafe prescription (plausibility gate)")
    flagged = [f for f in rx_case["facts"] if f.get("plausibility_flag")]
    for f in flagged:
        print(f"    {f['fact_id']} {f['status']}: \"{f['value']}\"")
        for c in f["plausibility"]:
            print(f"      [{c['check']}] {c['message']}")
    checks = {c["check"] for f in flagged for c in f["plausibility"]}
    if not {"allergy_conflict", "antibiotic_for_viral"} <= checks or any(f["status"] == "VERIFIED" for f in flagged):
        failures.append("7. plausibility: amoxicillin was not held for review with allergy + viral conflicts")

    print("\n=== Audit trail (append-only) ===")
    with open(audit_path, encoding="utf-8") as fh:
        for line in fh:
            e = json.loads(line)
            if e["event"] in ("clinician_resolution", "calibration_update", "clinical_plausibility_flag"):
                print(" ", line.strip()[:200])

    print("\n" + ("ALL SCENARIOS BEHAVED AS EXPECTED" if not failures else "FAILURES:\n  " + "\n  ".join(failures)))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
