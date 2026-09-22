from __future__ import annotations

import json
from typing import List, Dict, Any

from .extractor import get_extractor, Fact
from .grounding import GroundingEngine
from .audit import AuditLog
from .calibration import CalibrationStore
from .clinical_plausibility import apply_plausibility_checks

FIELD_ORDER = [
    "chief_complaint", "history_of_present_illness", "medications",
    "allergies", "vitals", "assessment", "plan",
]
FIELD_LABELS = {
    "chief_complaint": "Chief Complaint",
    "history_of_present_illness": "History of Present Illness",
    "medications": "Medications",
    "allergies": "Allergies",
    "vitals": "Vitals",
    "assessment": "Assessment",
    "plan": "Plan",
}


def run_pipeline(segments: List[Dict[str, Any]], use_llm: bool, audit_path: str,
                  calibration_path: str) -> Dict[str, Any]:
    extractor = get_extractor(use_llm)
    facts: List[Fact] = extractor.extract(segments)

    calibration = CalibrationStore(calibration_path)
    grounder = GroundingEngine(segments, calibration)
    audit = AuditLog(audit_path)

    case_facts = []
    for idx, fact in enumerate(facts, start=1):
        fact_id = f"F{idx:03d}"
        result = grounder.evaluate(fact.value, fact.cited_segment_ids, fact.field)

        record = {
            "fact_id": fact_id,
            "field": fact.field,
            "value": fact.value,
            "cited_segment_ids": fact.cited_segment_ids,
            "source": fact.source,
            "semantic_score": result.semantic_score,
            "acoustic_score": result.acoustic_score,
            "combined_confidence": result.combined_confidence,
            "status": result.status,          # VERIFIED | NEEDS_REVIEW | REJECTED
            "reason": result.reason,
            "resolution": None,                # filled in later if a clinician resolves it
        }
        case_facts.append(record)

        audit.append({
            "event": "auto_gate_decision",
            "fact_id": fact_id,
            "field": fact.field,
            "value": fact.value,
            "cited_segment_ids": fact.cited_segment_ids,
            "semantic_score": result.semantic_score,
            "acoustic_score": result.acoustic_score,
            "combined_confidence": result.combined_confidence,
            "status": result.status,
            "reason": result.reason,
        })

    case_facts = apply_plausibility_checks(case_facts)
    for fact in case_facts:
        if fact.get("plausibility_flag"):
            audit.append({
                "event": "clinical_plausibility_override",
                "fact_id": fact["fact_id"],
                "field": fact["field"],
                "value": fact["value"],
                "reason": fact["reason"],
            })

    return {"segments": segments, "facts": case_facts}


def resolve_fact(case: Dict[str, Any], fact_id: str, decision: str, reviewer: str,
                  audit_path: str, calibration_path: str) -> Dict[str, Any]:
    if decision not in ("approve", "reject"):
        raise ValueError("decision must be 'approve' or 'reject'")

    target = next((f for f in case["facts"] if f["fact_id"] == fact_id), None)
    if target is None:
        raise ValueError(f"No fact with id {fact_id} in this case.")
    if target["status"] == "VERIFIED":
        raise ValueError(f"{fact_id} was already auto-verified; nothing to resolve.")
    if target.get("resolution") is not None:
        raise ValueError(f"{fact_id} was already resolved ({target['resolution']}).")

    target["resolution"] = decision
    target["resolved_by"] = reviewer

    audit = AuditLog(audit_path)
    audit.append({
        "event": "clinician_resolution",
        "fact_id": fact_id,
        "field": target["field"],
        "value": target["value"],
        "prior_status": target["status"],
        "combined_confidence": target["combined_confidence"],
        "decision": decision,
        "reviewer": reviewer,
    })

    # Only NEEDS_REVIEW facts (borderline, not below the hard safety floors)
    # feed the adaptive calibration loop. REJECTED facts failed an absolute
    # floor -- that floor is not adaptive, by design.
    if target["status"] == "NEEDS_REVIEW":
        calibration = CalibrationStore(calibration_path)
        new_threshold = calibration.update_from_resolution(
            target["field"], target["combined_confidence"], decision
        )
        audit.append({
            "event": "calibration_update",
            "field": target["field"],
            "new_threshold": new_threshold,
            "triggered_by_fact_id": fact_id,
        })

    return case


def render_note(case: Dict[str, Any]) -> str:
    facts = case["facts"]
    verified = [f for f in facts if f["status"] == "VERIFIED" or f.get("resolution") == "approve"]
    pending = [f for f in facts if f["status"] != "VERIFIED" and f.get("resolution") is None]
    rejected_final = [f for f in facts if f.get("resolution") == "reject"]

    lines = ["# Structured Clinical Note (auto-generated draft)\n"]
    for fkey in FIELD_ORDER:
        field_facts = [f for f in verified if f["field"] == fkey]
        if not field_facts:
            continue
        lines.append(f"## {FIELD_LABELS[fkey]}")
        for f in field_facts:
            lines.append(f"- {f['value']}  _(source: segment {f['cited_segment_ids']}, "
                         f"confidence {f['combined_confidence']:.2f}, fact {f['fact_id']})_")
        lines.append("")

    if pending:
        lines.append("## ⚠ Pending Clinician Review (blocked from auto-insertion)")
        for f in pending:
            lines.append(f"- [{f['fact_id']}] ({FIELD_LABELS.get(f['field'], f['field'])}) "
                         f"\"{f['value']}\" — {f['reason']}")
        lines.append("")

    if rejected_final:
        lines.append("## ✗ Reviewed and Rejected")
        for f in rejected_final:
            lines.append(f"- [{f['fact_id']}] \"{f['value']}\" — rejected by clinician")
        lines.append("")

    return "\n".join(lines)


def save_case(case: Dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(case, f, indent=2)


def load_case(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
