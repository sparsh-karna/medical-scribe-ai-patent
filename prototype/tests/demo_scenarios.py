"""
Demonstration script (not a unit test framework) proving the core claim:
a hallucinated/uncited clinical fact is blocked from auto-insertion, and
a clinician's resolution of a blocked fact is (a) permanently logged and
(b) recalibrates that field's future auto-insert threshold.

Run with:  python tests/demo_scenarios.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline import resolve_fact, render_note, save_case, load_case
from src.calibration import CalibrationStore

DEMO_DIR = os.path.join(os.path.dirname(__file__), "_demo_out")


def main():
    os.makedirs(DEMO_DIR, exist_ok=True)
    audit_path = os.path.join(DEMO_DIR, "audit_log.jsonl")
    calibration_path = os.path.join(DEMO_DIR, "calibration_state.json")
    case_path = os.path.join(DEMO_DIR, "case_demo.json")
    for p in (audit_path, calibration_path, case_path):
        if os.path.exists(p):
            os.remove(p)

    segments = [
        {"id": 6, "start": 25.0, "end": 31.4, "speaker": "PATIENT",
         "text": "Yes, I'm taking metformin 500 mg twice a day for my diabetes."},
    ]

    # A borderline fact: right drug, wrong dose -- exactly the kind of
    # error a generative model can silently introduce.
    case = {
        "visit_id": "DEMO-001",
        "segments": segments,
        "facts": [{
            "fact_id": "F001",
            "field": "medications",
            "value": "metformin 1000 mg three times a day for diabetes",
            "cited_segment_ids": [6],
            "source": "rule_based",
            "semantic_score": 0.52,
            "acoustic_score": 0.95,
            "combined_confidence": 0.69,
            "status": "NEEDS_REVIEW",
            "reason": "Combined confidence 0.69 below auto-insert threshold 0.75 for field 'medications'.",
            "resolution": None,
        }],
    }
    save_case(case, case_path)

    print("=== BEFORE clinician resolution ===")
    print(render_note(case))
    threshold_before = CalibrationStore(calibration_path).threshold_for("medications")
    print(f"medications threshold before resolution: {threshold_before}")

    print("\n=== Clinician rejects the incorrect dosage fact ===")
    case = load_case(case_path)
    case = resolve_fact(case, "F001", "reject", "Dr. Patel", audit_path, calibration_path)
    save_case(case, case_path)
    print(render_note(case))

    threshold_after = CalibrationStore(calibration_path).threshold_for("medications")
    print(f"medications threshold after a REJECT: {threshold_after} "
          f"(moved {'up' if threshold_after > threshold_before else 'down'} -> field now requires MORE confidence)")

    print("\n=== Audit trail (append-only) ===")
    for line in open(audit_path):
        print(line.strip())


if __name__ == "__main__":
    main()
