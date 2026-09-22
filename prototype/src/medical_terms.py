"""
Lightweight domain-adaptation layer around the off-the-shelf ASR model.

We do not fine-tune or retrain Whisper -- that is out of scope and not a
realistic way to beat vendors who have already invested heavily in ASR
accuracy. Instead we (a) bias decoding toward medical vocabulary via
Whisper's initial_prompt mechanism, and (b) run a small fuzzy-correction
pass after transcription to fix near-miss spellings of known medical
terms. Both are proof-of-concept sized: a real deployment would source
this vocabulary from RxNorm/SNOMED rather than a hardcoded list.
"""
from __future__ import annotations

import difflib
import re
from typing import List

COMMON_DRUGS = [
    "metformin", "ibuprofen", "lisinopril", "amoxicillin", "albuterol",
    "penicillin", "atorvastatin", "aspirin", "insulin", "acetaminophen",
    "paracetamol", "losartan", "amlodipine", "levothyroxine", "omeprazole",
    "amoxicillin-clavulanate", "azithromycin", "prednisone", "warfarin",
    "metoprolol", "sertraline",
]

COMMON_SYMPTOMS_ANATOMY = [
    "diarrhea", "fever", "cough", "dyspnea", "tachycardia", "abdomen",
    "epigastric", "lethargic", "vomiting", "nausea", "headache",
    "photophobia", "migraine", "gastroenteritis",
]

MEDICAL_VOCABULARY = COMMON_DRUGS + COMMON_SYMPTOMS_ANATOMY


def build_initial_prompt() -> str:
    """A short prompt string passed to Whisper to bias decoding toward
    medical vocabulary. This is the standard Whisper technique for
    domain adaptation without any retraining."""
    return "Medical consultation. Terms that may appear: " + ", ".join(MEDICAL_VOCABULARY) + "."


def normalize_medical_terms(text: str, cutoff: float = 0.82) -> str:
    """Fuzzy-correct near-miss ASR spellings of known medical terms.
    E.g. 'metformen' -> 'metformin'. Conservative cutoff to avoid
    over-correcting unrelated words."""
    words = text.split()
    corrected = []
    for w in words:
        bare = re.sub(r"[^A-Za-z\-]", "", w).lower()
        if len(bare) < 4:
            corrected.append(w)
            continue
        match = difflib.get_close_matches(bare, MEDICAL_VOCABULARY, n=1, cutoff=cutoff)
        if match and match[0] != bare:
            corrected.append(w.replace(bare, match[0]) if bare in w.lower() else match[0])
        else:
            corrected.append(w)
    return " ".join(corrected)
