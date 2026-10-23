"""
Third gate signal: clinical-plausibility cross-check.

The dual-signal grounding gate (grounding.py) only answers "is this
statement supported by what was said?" It cannot catch a statement that
is faithfully transcribed AND clinically unsafe -- e.g. a genuinely-spoken
prescription that conflicts with an allergy stated in the same encounter,
or a drug given for a condition it does not treat ("aspirin for your
diarrhoea").

Every medication/plan fact that has not already been rejected is checked
against the other non-rejected facts of the same encounter:

  1. Allergy conflict     -- drug is in the same class as a documented allergy.
  2. Antibiotic for viral -- antibiotic prescribed while the assessment
                             documents a viral etiology (stewardship rule).
  3. Indication mismatch  -- "<drug> for <condition>" where the condition is
                             not among the drug's recognised indications.
  4. Contraindication     -- drug class contraindicated by a condition
                             documented in the history/assessment.
  5. Drug interaction     -- two drugs in the note form a known
                             clinically significant interacting pair.

Negated mentions ("no history of ulcers", "you don't need amoxicillin")
are ignored. Any conflict demotes a VERIFIED fact to NEEDS_REVIEW (never
silently auto-inserted) and is attached to NEEDS_REVIEW facts so the
reviewing clinician sees it.

The knowledge tables below are a small curated subset of standard drug
references (BNF / FDA labelling), sized for a prototype. A production
system would source them from RxNorm/SNOMED-CT and an interaction service
(e.g. openFDA, DrugBank) without changing the gate logic.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

# name/synonym -> canonical drug entry
DRUGS: Dict[str, Dict[str, Any]] = {}


def _drug(names: List[str], cls: str, indications: Optional[List[str]], antibiotic: bool = False):
    entry = {"name": names[0], "class": cls, "indications": set(indications) if indications else None,
             "antibiotic": antibiotic}
    for n in names:
        DRUGS[n] = entry


BACTERIAL = ["bacterial infection", "infection", "pneumonia", "tonsillitis", "otitis media",
             "sinusitis", "cellulitis", "urinary tract infection", "chest infection"]
_drug(["amoxicillin", "amoxil"], "penicillins", BACTERIAL, antibiotic=True)
_drug(["penicillin", "phenoxymethylpenicillin"], "penicillins", BACTERIAL, antibiotic=True)
_drug(["flucloxacillin"], "penicillins", BACTERIAL, antibiotic=True)
_drug(["co-amoxiclav", "amoxicillin-clavulanate", "augmentin"], "penicillins", BACTERIAL, antibiotic=True)
_drug(["cephalexin", "cefalexin", "cefuroxime", "ceftriaxone"], "cephalosporins", BACTERIAL, antibiotic=True)
_drug(["clarithromycin", "erythromycin", "azithromycin"], "macrolides", BACTERIAL, antibiotic=True)
_drug(["doxycycline"], "tetracyclines", BACTERIAL, antibiotic=True)
_drug(["ciprofloxacin"], "fluoroquinolones", BACTERIAL, antibiotic=True)
_drug(["trimethoprim"], "trimethoprim", BACTERIAL, antibiotic=True)
_drug(["nitrofurantoin"], "nitrofurans", BACTERIAL, antibiotic=True)
_drug(["co-trimoxazole", "sulfamethoxazole", "bactrim"], "sulfonamides", BACTERIAL, antibiotic=True)
_drug(["metronidazole"], "nitroimidazoles", BACTERIAL + ["bacterial vaginosis"], antibiotic=True)

ANALGESIC = ["pain", "fever", "headache", "migraine"]
NSAID_USES = ANALGESIC + ["inflammation", "arthritis", "period pain"]
_drug(["ibuprofen", "nurofen", "advil"], "nsaids", NSAID_USES)
_drug(["naproxen"], "nsaids", NSAID_USES)
_drug(["diclofenac"], "nsaids", NSAID_USES)
_drug(["aspirin"], "nsaids", NSAID_USES + ["cardiovascular prevention", "angina", "heart attack", "stroke"])
_drug(["paracetamol", "acetaminophen", "tylenol", "calpol"], "analgesics", ANALGESIC)
_drug(["codeine"], "opioids", ["pain", "cough"])

_drug(["metformin"], "biguanides", ["diabetes"])
_drug(["insulin"], "insulins", ["diabetes"])
_drug(["lisinopril", "ramipril", "enalapril", "perindopril"], "ace inhibitors",
      ["hypertension", "heart failure", "diabetes", "kidney disease"])
_drug(["losartan", "candesartan"], "arbs", ["hypertension", "heart failure", "kidney disease"])
_drug(["amlodipine"], "calcium channel blockers", ["hypertension", "angina"])
_drug(["atorvastatin", "simvastatin"], "statins", ["high cholesterol", "cardiovascular prevention"])
_drug(["levothyroxine"], "thyroid hormones", ["hypothyroidism"])
_drug(["omeprazole", "lansoprazole"], "proton pump inhibitors",
      ["reflux", "heartburn", "indigestion", "peptic ulcer", "gastritis"])
_drug(["salbutamol", "albuterol", "ventolin"], "beta2 agonists", ["asthma", "copd", "wheeze", "shortness of breath"])
_drug(["prednisolone", "prednisone"], "corticosteroids", None)  # too many indications to list
_drug(["warfarin"], "anticoagulants", ["atrial fibrillation", "deep vein thrombosis", "pulmonary embolism", "stroke"])
_drug(["metoprolol", "bisoprolol", "atenolol"], "cardioselective beta blockers",
      ["hypertension", "angina", "atrial fibrillation", "heart failure"])
_drug(["propranolol"], "non-selective beta blockers",
      ["hypertension", "angina", "anxiety", "migraine", "atrial fibrillation"])
_drug(["sertraline", "fluoxetine", "citalopram"], "ssris", ["depression", "anxiety", "panic disorder", "ocd"])
_drug(["methotrexate"], "antimetabolites", ["rheumatoid arthritis", "psoriasis"])
_drug(["loperamide", "imodium"], "antimotility agents", ["diarrhoea"])
_drug(["dioralyte", "oral rehydration"], "oral rehydration salts", ["diarrhoea", "dehydration", "vomiting"])
_drug(["cetirizine", "loratadine"], "antihistamines", ["allergy", "hay fever", "hives", "itching"])

# canonical condition -> surface forms
CONDITIONS: Dict[str, List[str]] = {
    "diarrhoea": ["diarrhoea", "diarrhea", "loose stools", "loose stool", "watery stools"],
    "vomiting": ["vomiting", "being sick"],
    "nausea": ["nausea", "feeling sick"],
    "constipation": ["constipation"],
    "cough": ["cough"],
    "common cold": ["common cold", "a cold"],
    "flu": ["flu", "influenza"],
    "sore throat": ["sore throat"],
    "headache": ["headache", "headaches"],
    "migraine": ["migraine", "migraines"],
    "fever": ["fever", "temperature"],
    "pain": ["pain", "ache", "aches"],
    "period pain": ["period pain", "dysmenorrhoea", "dysmenorrhea"],
    "inflammation": ["inflammation", "swelling"],
    "arthritis": ["arthritis", "osteoarthritis"],
    "rheumatoid arthritis": ["rheumatoid arthritis"],
    "asthma": ["asthma"],
    "copd": ["copd", "chronic obstructive"],
    "wheeze": ["wheeze", "wheezing"],
    "shortness of breath": ["shortness of breath", "breathless", "short of breath"],
    "hypertension": ["hypertension", "high blood pressure"],
    "diabetes": ["diabetes", "diabetic"],
    "high cholesterol": ["high cholesterol", "cholesterol"],
    "hypothyroidism": ["hypothyroidism", "underactive thyroid"],
    "reflux": ["reflux", "gerd", "gord"],
    "heartburn": ["heartburn"],
    "indigestion": ["indigestion", "dyspepsia"],
    "gastritis": ["gastritis"],
    "peptic ulcer": ["peptic ulcer", "stomach ulcer", "duodenal ulcer", "gastric ulcer"],
    "gi bleed": ["gi bleed", "gastrointestinal bleed", "bleeding from the stomach", "blood in vomit"],
    "kidney disease": ["kidney disease", "renal impairment", "renal disease", "ckd"],
    "kidney failure": ["kidney failure", "renal failure", "end-stage renal"],
    "pregnancy": ["pregnant", "pregnancy"],
    "depression": ["depression"],
    "anxiety": ["anxiety"],
    "insomnia": ["insomnia", "trouble sleeping"],
    "angina": ["angina"],
    "heart failure": ["heart failure"],
    "heart attack": ["heart attack", "myocardial infarction"],
    "stroke": ["stroke"],
    "atrial fibrillation": ["atrial fibrillation", "af"],
    "deep vein thrombosis": ["deep vein thrombosis", "dvt"],
    "pulmonary embolism": ["pulmonary embolism"],
    "urinary tract infection": ["urinary tract infection", "uti", "water infection"],
    "chest infection": ["chest infection"],
    "infection": ["infection"],
    "bacterial infection": ["bacterial infection"],
    "pneumonia": ["pneumonia"],
    "tonsillitis": ["tonsillitis"],
    "sinusitis": ["sinusitis"],
    "cellulitis": ["cellulitis"],
    "otitis media": ["otitis media", "ear infection"],
    "gastroenteritis": ["gastroenteritis", "stomach bug"],
    "dehydration": ["dehydration", "dehydrated"],
    "allergy": ["allergy", "allergies", "allergic reaction"],
    "hay fever": ["hay fever"],
    "rash": ["rash"],
    "eczema": ["eczema"],
}

VIRAL_MARKERS = ["viral", "virus", "common cold", "influenza", "flu"]

# drug class -> {condition: why it is contraindicated}
CONTRAINDICATIONS: Dict[str, Dict[str, str]] = {
    "nsaids": {
        "peptic ulcer": "NSAIDs are contraindicated with active/previous peptic ulceration",
        "gi bleed": "NSAIDs are contraindicated after gastrointestinal bleeding",
        "kidney disease": "NSAIDs can precipitate renal failure in kidney disease",
        "kidney failure": "NSAIDs are contraindicated in renal failure",
    },
    "non-selective beta blockers": {
        "asthma": "non-selective beta blockers can cause bronchospasm in asthma",
    },
    "ace inhibitors": {"pregnancy": "ACE inhibitors are contraindicated in pregnancy (fetotoxic)"},
    "arbs": {"pregnancy": "ARBs are contraindicated in pregnancy (fetotoxic)"},
    "biguanides": {"kidney failure": "metformin is contraindicated in renal failure (lactic acidosis)"},
}

# unordered class pairs -> interaction
INTERACTIONS: Dict[frozenset, str] = {
    frozenset({"anticoagulants", "nsaids"}): "warfarin with an NSAID markedly raises bleeding risk",
    frozenset({"anticoagulants", "nitroimidazoles"}): "metronidazole potentiates warfarin (INR rise)",
    frozenset({"anticoagulants", "macrolides"}): "macrolides potentiate warfarin (INR rise)",
    frozenset({"ssris", "nsaids"}): "SSRIs with NSAIDs increase gastrointestinal bleeding risk",
    frozenset({"antimetabolites", "trimethoprim"}): "trimethoprim with methotrexate risks bone-marrow toxicity",
    frozenset({"antimetabolites", "sulfonamides"}): "co-trimoxazole with methotrexate risks bone-marrow toxicity",
}

NEGATION_CUES = r"(?:no|not|don't|dont|doesn't|didn't|denies|denied|without|never|avoid|stop|stopped|instead of|nor|free of|negative for)"


def _mentions(text: str, term: str) -> List[int]:
    return [m.start() for m in re.finditer(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", text)]


def _negated(text: str, pos: int) -> bool:
    """NegEx-style: a negation cue within the preceding few words of the same clause."""
    window = re.split(r"[.;,:!?]| but ", text[max(0, pos - 60):pos])[-1]
    return re.search(r"(?<![a-z])" + NEGATION_CUES + r"(?![a-z])(?:\W+\w+){0,4}\W*$", window) is not None


def _affirmed(text: str, term: str) -> bool:
    return any(not _negated(text, p) for p in _mentions(text, term))


def drugs_in(text: str) -> List[Dict[str, Any]]:
    t = text.lower()
    found, seen = [], set()
    for name, entry in DRUGS.items():
        if entry["name"] not in seen and _affirmed(t, name):
            seen.add(entry["name"])
            found.append(entry)
    return found


def conditions_in(text: str) -> Set[str]:
    t = text.lower()
    return {canon for canon, forms in CONDITIONS.items() if any(_affirmed(t, f) for f in forms)}


def _indication_targets(text: str, drug_name: str) -> Set[str]:
    """Conditions named in a '<drug> ... for <condition>' phrase."""
    t = text.lower()
    targets: Set[str] = set()
    for pos in _mentions(t, drug_name):
        m = re.match(r"[^.;]*?\bfor\s+(?:the\s+|your\s+|his\s+|her\s+|my\s+|their\s+)?([^.;]+)", t[pos:])
        if m:
            phrase = re.split(r"\b(?:and then|then|until|so that|because)\b", m.group(1))[0]
            targets |= conditions_in(phrase)
    return targets


def _fact_conflicts(fact, allergy_classes, viral_assessment, history_conditions, other_drug_facts):
    conflicts = []
    text = fact["value"]
    for drug in drugs_in(text):
        for allergy_fact_id, classes in allergy_classes:
            if drug["class"] in classes:
                conflicts.append({
                    "check": "allergy_conflict", "related": [allergy_fact_id],
                    "message": f"{drug['name']} is a {drug['class'][:-1] if drug['class'].endswith('s') else drug['class']}; "
                               f"the patient has a documented {drug['class']} allergy ({allergy_fact_id})."})
        if drug["antibiotic"] and viral_assessment:
            fid, avalue = viral_assessment
            conflicts.append({
                "check": "antibiotic_for_viral", "related": [fid],
                "message": f"{drug['name']} (antibiotic) prescribed while the assessment ({fid}) documents a "
                           f"viral etiology: \"{avalue}\". Antibiotics are not indicated for viral illness."})
        if drug["indications"] is not None:
            # an antibiotic for a viral illness is already reported by the stewardship check
            unindicated = sorted(c for c in _indication_targets(text, drug["name"])
                                 if c not in drug["indications"] and c not in ("infection",))
            if unindicated:
                conflicts.append({
                    "check": "indication_mismatch", "related": [],
                    "message": f"{drug['name']} is given for {', '.join(unindicated)}, which is not among its "
                               f"indications ({', '.join(sorted(drug['indications']))})."})
        for condition, why in CONTRAINDICATIONS.get(drug["class"], {}).items():
            if condition in history_conditions:
                conflicts.append({
                    "check": "contraindication", "related": history_conditions[condition],
                    "message": f"{drug['name']}: {why}; {condition} is documented "
                               f"({', '.join(history_conditions[condition])})."})
        for other_id, other_drug in other_drug_facts:
            if other_id == fact["fact_id"] or other_drug["name"] == drug["name"]:
                continue
            why = INTERACTIONS.get(frozenset({drug["class"], other_drug["class"]}))
            if why:
                conflicts.append({
                    "check": "drug_interaction", "related": [other_id],
                    "message": f"{drug['name']} + {other_drug['name']} ({other_id}): {why}."})
    return conflicts


def apply_plausibility_checks(case_facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    live = [f for f in case_facts if f["status"] != "REJECTED"]

    allergy_classes = []
    for f in live:
        if f["field"] == "allergies":
            classes = {d["class"] for d in drugs_in(f["value"])}
            if classes:
                allergy_classes.append((f["fact_id"], classes))

    viral_assessment = None
    for f in live:
        if f["field"] == "assessment":
            t = f["value"].lower()
            if any(_affirmed(t, v) for v in VIRAL_MARKERS):
                viral_assessment = (f["fact_id"], f["value"])
                break

    history_conditions: Dict[str, List[str]] = {}
    for f in live:
        if f["field"] in ("chief_complaint", "history_of_present_illness", "assessment", "medications"):
            for c in conditions_in(f["value"]):
                history_conditions.setdefault(c, []).append(f["fact_id"])

    drug_facts = [(f["fact_id"], d) for f in live if f["field"] in ("medications", "plan")
                  for d in drugs_in(f["value"])]

    for fact in live:
        if fact["field"] not in ("medications", "plan"):
            continue
        # a fact's own condition mentions ("aspirin for diarrhoea") are its
        # indication, not a documented history -> exclude it from history
        history = {c: [i for i in ids if i != fact["fact_id"]] for c, ids in history_conditions.items()}
        history = {c: ids for c, ids in history.items() if ids}
        conflicts = _fact_conflicts(fact, allergy_classes, viral_assessment, history, drug_facts)
        if not conflicts:
            continue
        fact["plausibility"] = conflicts
        fact["plausibility_flag"] = True
        summary = " ".join(c["message"] for c in conflicts)
        if fact["status"] == "VERIFIED":
            fact["status"] = "NEEDS_REVIEW"
            fact["held_for"] = "plausibility"   # held only for a safety conflict
            fact["reason"] = f"[clinical-plausibility gate] {summary}"
        else:
            fact["reason"] = f"{fact['reason']} [clinical-plausibility gate] {summary}"
    return case_facts
