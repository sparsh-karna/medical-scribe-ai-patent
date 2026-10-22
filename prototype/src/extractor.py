"""
Extraction backends: turn a list of transcript segments into a list of
candidate clinical facts, each citing the segment id(s) it was drawn from.

The grounding/gating layer (grounding.py) is backend-agnostic: it does not
care whether facts came from the rule-based extractor below or from an LLM.
That separation is intentional -- the novel contribution of this project is
the verification/gate layer, not the extraction method itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any

from .llm import LLMError, format_transcript, generate_json


@dataclass
class Fact:
    field: str                     # e.g. "chief_complaint", "medications"
    value: str                     # the drafted clinical statement
    cited_segment_ids: List[int] = field(default_factory=list)
    source: str = "rule_based"     # which extractor produced this
    # Verbatim evidence the extractor claims supports this fact:
    # [{"segment_id": int, "quote": str}]. The grounding gate checks each
    # quote really occurs in its segment before running entailment.
    evidence: List[Dict[str, Any]] = field(default_factory=list)


def _verbatim(field_name: str, seg: Dict[str, Any]) -> "Fact":
    """A rule-based fact is the segment's own text, so its evidence is the whole segment."""
    text = seg["text"].strip()
    return Fact(field_name, text, [seg["id"]], "rule_based",
                [{"segment_id": seg["id"], "quote": text}])


class RuleBasedExtractor:
    """
    Deterministic, dependency-free extractor. Not meant to be clinically
    sophisticated -- it exists so the pipeline is fully runnable and
    reproducible without any API key or model download, which matters for
    demonstrating the grounding/gating mechanism in isolation.
    """

    MED_KEYWORDS = [
        "metformin", "ibuprofen", "lisinopril", "amoxicillin", "albuterol",
        "penicillin", "atorvastatin", "aspirin", "insulin", "acetaminophen",
    ]

    def extract(self, segments: List[Dict[str, Any]]) -> List[Fact]:
        facts: List[Fact] = []
        patient_segments = [s for s in segments if s["speaker"] == "PATIENT"]
        doctor_segments = [s for s in segments if s["speaker"] == "DOCTOR"]

        # Chief complaint: first patient turn mentioning a symptom-ish cue.
        for s in patient_segments:
            if re.search(r"\b(here for|cough|pain|fever|feel|hurts|short of breath)\b", s["text"], re.I):
                facts.append(_verbatim("chief_complaint", s))
                break

        # History of present illness: any additional patient symptom detail.
        for s in patient_segments:
            if re.search(r"\b(fever|cough|breath|pain|days|weeks)\b", s["text"], re.I):
                facts.append(_verbatim("history_of_present_illness", s))

        # Medications.
        for s in patient_segments + doctor_segments:
            for med in self.MED_KEYWORDS:
                if med.lower() in s["text"].lower() and "allerg" not in s["text"].lower():
                    facts.append(_verbatim("medications", s))
                    break

        # Allergies.
        for s in patient_segments:
            if re.search(r"\ballerg", s["text"], re.I):
                facts.append(_verbatim("allergies", s))

        # Vitals (blood pressure / temperature / heart rate patterns).
        for s in doctor_segments:
            if re.search(r"\d{2,3}\s*(over|/)\s*\d{2,3}|\d{2,3}(\.\d)?\s*(f|fahrenheit)|\d{2,3}\s*bpm", s["text"], re.I):
                facts.append(_verbatim("vitals", s))

        # Assessment.
        for s in doctor_segments:
            if re.search(r"\b(looks like|likely|diagnosis|suspect|consistent with)\b", s["text"], re.I):
                facts.append(_verbatim("assessment", s))

        # Plan.
        for s in doctor_segments:
            if re.search(r"\b(follow up|start you on|prescri|recommend|rest|fluids)\b", s["text"], re.I):
                facts.append(_verbatim("plan", s))

        return facts


FACT_FIELDS = [
    "chief_complaint", "history_of_present_illness", "medications",
    "allergies", "vitals", "assessment", "plan",
]

LLM_SYSTEM_PROMPT = (
    "You are a clinical documentation assistant. You will be given a numbered "
    "doctor-patient transcript (lines look like `[id] SPEAKER: text`). Extract "
    "the clinically relevant facts for a structured note. For each fact give:\n"
    '- "field": one of ' + ", ".join(FACT_FIELDS) + "\n"
    '- "value": one concise clinical statement\n'
    '- "citations": every segment needed to support the statement, each as '
    '{"segment_id": <id>, "quote": <an exact, contiguous, verbatim excerpt of that '
    "segment's text>}. When a fact comes from an answer to a question (e.g. "
    '"Do you smoke?" / "No."), cite both the question and the answer.\n'
    "Quotes must be copied character-for-character from the transcript; never "
    "paraphrase inside a quote. Do not state anything the cited segments do not support."
)

# JSON schema for the fact array; constrains LLM output so the response is
# always parseable instead of relying on the prompt alone.
FACTS_JSON_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "field": {"type": "string", "enum": FACT_FIELDS},
            "value": {"type": "string"},
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "segment_id": {"type": "integer"},
                        "quote": {"type": "string"},
                    },
                    "required": ["segment_id", "quote"],
                },
            },
        },
        "required": ["field", "value", "citations"],
    },
}


def _facts_from_items(items: Any, segments: List[Dict[str, Any]]) -> List[Fact]:
    """
    Keep only well-formed items. Citations to non-existent segment ids are
    dropped here (the fact itself is kept), so an uncited fact still reaches
    the grounding gate and gets blocked there -- the gate, not this parser,
    decides what is trusted.
    """
    if not isinstance(items, list):
        raise LLMError("LLM returned JSON that is not an array of facts.")
    valid_ids = {s["id"] for s in segments}
    facts: List[Fact] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        field_name = item.get("field")
        value = item.get("value")
        if field_name not in FACT_FIELDS or not isinstance(value, str) or not value.strip():
            continue
        evidence = []
        for c in item.get("citations") or []:
            if not isinstance(c, dict):
                continue
            try:
                sid = int(c.get("segment_id"))
            except (TypeError, ValueError):
                continue
            quote = c.get("quote")
            if sid in valid_ids and isinstance(quote, str):
                evidence.append({"segment_id": sid, "quote": quote.strip()})
        cited_ids = list(dict.fromkeys(e["segment_id"] for e in evidence))
        facts.append(Fact(field_name, value.strip(), cited_ids, "llm", evidence))
    return facts


class LLMExtractor:
    """
    LLM-backed extractor (Gemini or Claude, see src/llm.py). The model must
    cite the segment(s) supporting every fact and quote the exact supporting
    text -- those citations and quotes are exactly what the grounding gate
    verifies, so a hallucinated or mis-cited fact is not trusted at face value.
    """

    def extract(self, segments: List[Dict[str, Any]]) -> List[Fact]:
        items = generate_json(LLM_SYSTEM_PROMPT, format_transcript(segments), FACTS_JSON_SCHEMA)
        return _facts_from_items(items, segments)


def get_extractor(use_llm: bool):
    return LLMExtractor() if use_llm else RuleBasedExtractor()
