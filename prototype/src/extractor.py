"""
Extraction backends: turn a list of transcript segments into a list of
candidate clinical facts, each citing the segment id(s) it was drawn from.

The grounding/gating layer (grounding.py) is backend-agnostic: it does not
care whether facts came from the rule-based extractor below or from an LLM.
That separation is intentional -- the novel contribution of this project is
the verification/gate layer, not the extraction method itself.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class Fact:
    field: str                     # e.g. "chief_complaint", "medications"
    value: str                     # the drafted clinical statement
    cited_segment_ids: List[int] = field(default_factory=list)
    source: str = "rule_based"     # which extractor produced this


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
                facts.append(Fact("chief_complaint", s["text"].strip(), [s["id"]], "rule_based"))
                break

        # History of present illness: any additional patient symptom detail.
        for s in patient_segments:
            if re.search(r"\b(fever|cough|breath|pain|days|weeks)\b", s["text"], re.I):
                facts.append(Fact("history_of_present_illness", s["text"].strip(), [s["id"]], "rule_based"))

        # Medications.
        for s in patient_segments + doctor_segments:
            for med in self.MED_KEYWORDS:
                if med.lower() in s["text"].lower() and "allerg" not in s["text"].lower():
                    facts.append(Fact("medications", s["text"].strip(), [s["id"]], "rule_based"))
                    break

        # Allergies.
        for s in patient_segments:
            if re.search(r"\ballerg", s["text"], re.I):
                facts.append(Fact("allergies", s["text"].strip(), [s["id"]], "rule_based"))

        # Vitals (blood pressure / temperature / heart rate patterns).
        for s in doctor_segments:
            if re.search(r"\d{2,3}\s*(over|/)\s*\d{2,3}|\d{2,3}(\.\d)?\s*(f|fahrenheit)|\d{2,3}\s*bpm", s["text"], re.I):
                facts.append(Fact("vitals", s["text"].strip(), [s["id"]], "rule_based"))

        # Assessment.
        for s in doctor_segments:
            if re.search(r"\b(looks like|likely|diagnosis|suspect|consistent with)\b", s["text"], re.I):
                facts.append(Fact("assessment", s["text"].strip(), [s["id"]], "rule_based"))

        # Plan.
        for s in doctor_segments:
            if re.search(r"\b(follow up|start you on|prescri|recommend|rest|fluids)\b", s["text"], re.I):
                facts.append(Fact("plan", s["text"].strip(), [s["id"]], "rule_based"))

        return facts


class ClaudeExtractor:
    """
    Optional LLM-backed extractor. Requires `anthropic` package and
    ANTHROPIC_API_KEY. Instructs the model to cite the transcript segment
    id(s) supporting every fact it drafts -- those citations are exactly
    what the grounding layer later verifies, so a hallucinated or
    mis-cited fact is not simply trusted at face value.
    """

    SYSTEM_PROMPT = (
        "You are a clinical documentation assistant. You will be given a "
        "numbered doctor-patient transcript. Extract structured clinical "
        "facts as a JSON array. Each item must have: "
        '"field" (one of chief_complaint, history_of_present_illness, '
        "medications, allergies, vitals, assessment, plan), "
        '"value" (a concise clinical statement), and '
        '"cited_segment_ids" (list of integer segment ids that directly '
        "support the statement). Only cite segments that literally "
        "contain the supporting evidence. Output JSON only, no prose."
    )

    def __init__(self, model: str = "claude-sonnet-5"):
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic  # local import: optional dependency
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY not set; cannot use ClaudeExtractor.")
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def extract(self, segments: List[Dict[str, Any]]) -> List[Fact]:
        import json

        client = self._get_client()
        transcript_text = "\n".join(f"[{s['id']}] {s['speaker']}: {s['text']}" for s in segments)
        resp = client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": transcript_text}],
        )
        raw = "".join(block.text for block in resp.content if hasattr(block, "text"))
        items = json.loads(raw)
        return [
            Fact(
                field=item["field"],
                value=item["value"],
                cited_segment_ids=list(item.get("cited_segment_ids", [])),
                source="llm",
            )
            for item in items
        ]


def get_extractor(use_llm: bool):
    if use_llm:
        return ClaudeExtractor()
    return RuleBasedExtractor()
