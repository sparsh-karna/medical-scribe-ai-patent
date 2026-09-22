"""
Third gate signal: clinical-plausibility cross-check.

The dual-signal grounding gate (grounding.py) only answers "does this
match what was said in the audio?" It cannot catch a statement that is
faithfully transcribed AND clinically unsafe -- e.g. a genuinely-spoken
instruction that contradicts a fact stated elsewhere in the same
encounter (a documented allergy), or a generated plan that violates a
well-established, uncontroversial clinical stewardship rule.

This module is deliberately NOT a diagnostic reasoning engine and does
not attempt general diagnosis-treatment appropriateness judgment -- that
would overstate what a lookup table can responsibly claim to do. It
checks exactly two narrow, objectively-checkable things:

  1. Drug-class allergy contradiction: a drafted medication/plan fact
     names a drug in the same class as a drug the patient is recorded
     (in this same note) as being allergic to.
  2. Antibiotic-for-viral-diagnosis: a drafted plan/medication fact
     prescribes an antibiotic while the drafted assessment documents a
     viral etiology -- one of the most well-established antibiotic
     stewardship rules taught in clinical training, not a judgment call.

A production system would replace these small hardcoded tables with a
real clinical knowledge base (e.g. RxNorm drug-class data, an
interaction/allergy-checking API such as openFDA). These tables are a
proof-of-concept stand-in, sized for a course project, not a claim to
have built a clinical decision-support system.
"""
from __future__ import annotations

from typing import List, Dict, Any

DRUG_CLASSES = {
    "penicillins": ["penicillin", "amoxicillin", "ampicillin", "amoxicillin-clavulanate", "augmentin"],
    "sulfonamides": ["sulfamethoxazole", "bactrim", "sulfa"],
    "nsaids": ["ibuprofen", "naproxen", "aspirin", "diclofenac"],
    "cephalosporins": ["cephalexin", "ceftriaxone", "cefuroxime"],
}

ANTIBIOTIC_KEYWORDS = [
    "amoxicillin", "penicillin", "azithromycin", "ciprofloxacin",
    "cephalexin", "doxycycline", "amoxicillin-clavulanate", "augmentin",
    "ceftriaxone", "cefuroxime", "bactrim", "sulfamethoxazole",
]

VIRAL_KEYWORDS = ["viral", "common cold", "upper respiratory infection, likely viral", "flu", "influenza"]


def _drug_class_of(text: str):
    text_l = text.lower()
    return [cls for cls, members in DRUG_CLASSES.items() if any(m in text_l for m in members)]


def check_allergy_contradiction(allergy_facts: List[Dict[str, Any]], med_fact: Dict[str, Any]):
    med_classes = _drug_class_of(med_fact["value"])
    if not med_classes:
        return None
    for allergy in allergy_facts:
        allergy_classes = _drug_class_of(allergy["value"])
        overlap = set(med_classes) & set(allergy_classes)
        if overlap:
            return (f"Drafted medication/plan cites a drug in class {sorted(overlap)}, which "
                    f"conflicts with a documented allergy in fact {allergy['fact_id']}: "
                    f"\"{allergy['value']}\".")
    return None


def check_antibiotic_for_viral(assessment_facts: List[Dict[str, Any]], med_fact: Dict[str, Any]):
    med_text_l = med_fact["value"].lower()
    if not any(abx in med_text_l for abx in ANTIBIOTIC_KEYWORDS):
        return None
    for assessment in assessment_facts:
        if any(v in assessment["value"].lower() for v in VIRAL_KEYWORDS):
            return (f"Drafted plan/medication appears to prescribe an antibiotic while the "
                    f"documented assessment ({assessment['fact_id']}) states a viral etiology: "
                    f"\"{assessment['value']}\". Antibiotics are not indicated for viral illness.")
    return None


def apply_plausibility_checks(case_facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Re-examines VERIFIED medication/plan facts against other VERIFIED
    facts in the same note. Any conflict downgrades the fact from
    VERIFIED to NEEDS_REVIEW -- it does not get silently auto-inserted
    just because it was faithfully transcribed."""
    allergy_facts = [f for f in case_facts if f["field"] == "allergies" and f["status"] == "VERIFIED"]
    assessment_facts = [f for f in case_facts if f["field"] == "assessment" and f["status"] == "VERIFIED"]

    for fact in case_facts:
        if fact["field"] not in ("medications", "plan") or fact["status"] != "VERIFIED":
            continue

        conflict = check_allergy_contradiction(allergy_facts, fact) or \
            check_antibiotic_for_viral(assessment_facts, fact)

        if conflict:
            fact["status"] = "NEEDS_REVIEW"
            fact["reason"] = f"[clinical-plausibility gate] {conflict}"
            fact["plausibility_flag"] = True

    return case_facts
