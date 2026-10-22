"""
Lightweight domain-adaptation layer around the off-the-shelf ASR model.

We do not fine-tune or retrain Whisper -- that is out of scope and not a
realistic way to beat vendors who have already invested heavily in ASR
accuracy. Instead we (a) bias decoding toward medical vocabulary via
faster-whisper's hotwords prompt, which is prepended to every 30-second
decoding window (Whisper's initial_prompt only conditions the first window
when condition_on_previous_text is off), and (b) run a small fuzzy-correction
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
    "loperamide", "dioralyte", "salbutamol", "naproxen", "codeine", "ramipril",
    "cetirizine", "doxycycline", "clarithromycin", "trimethoprim", "nitrofurantoin",
    "amoxicillin-clavulanate", "azithromycin", "prednisone", "warfarin",
    "metoprolol", "sertraline",
]

COMMON_SYMPTOMS_ANATOMY = [
    "diarrhea", "diarrhoea", "fever", "cough", "dyspnea", "tachycardia", "abdomen",
    "epigastric", "lethargic", "vomiting", "nausea", "headache",
    "photophobia", "migraine", "gastroenteritis", "stool", "stools", "bowel",
    "abdominal", "dehydrated", "inhaler", "asthma", "antibiotics", "allergic",
    "hypertension", "diabetes", "rash", "phlegm", "wheezing",
]

MEDICAL_VOCABULARY = COMMON_DRUGS + COMMON_SYMPTOMS_ANATOMY


def build_vocabulary_prompt() -> str:
    """Prompt text that biases Whisper's decoder toward medical vocabulary.
    Passed as faster-whisper `hotwords`, so it conditions every decoding
    window. The library keeps at most ~223 prompt tokens; this list is
    well inside that."""
    return "Medical consultation. Terms that may appear: " + ", ".join(MEDICAL_VOCABULARY) + "."


# Only words the recognizer itself was unsure about are candidates for
# correction: a confidently-recognised ordinary word ("insulting") must
# never be "corrected" into a similar drug name ("insulin").
CORRECTION_MAX_ASR_PROB = 0.70


def correct_word(token: str, asr_prob: float, cutoff: float = 0.82) -> str:
    """Fuzzy-correct a near-miss ASR spelling of a known medical term
    (e.g. 'metformen' -> 'metformin'), preserving surrounding whitespace,
    punctuation and capitalisation. Returns the token unchanged when the
    recogniser was confident or no vocabulary term is close enough."""
    if asr_prob >= CORRECTION_MAX_ASR_PROB:
        return token
    m = re.match(r"^(\W*)([A-Za-z][A-Za-z\-]*)(\W*)$", token)
    if not m:
        return token
    lead, word, trail = m.groups()
    bare = word.lower()
    if len(bare) < 4 or bare in MEDICAL_VOCABULARY:
        return token
    match = difflib.get_close_matches(bare, MEDICAL_VOCABULARY, n=1, cutoff=cutoff)
    if not match:
        return token
    fixed = match[0].capitalize() if word[0].isupper() else match[0]
    return lead + fixed + trail
