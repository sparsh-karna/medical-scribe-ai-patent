"""
Dual-signal confidence gate.

This module is the core novel mechanism of the project. Every drafted
clinical fact must clear TWO independent checks before it is allowed to
auto-populate the structured note:

  1. Acoustic confidence  -- how confident the speech recognizer was about
     the words in the cited audio segment(s). For real audio this comes
     from the ASR engine's per-segment probability; for text-only demo
     input it falls back to a fixed high value (no acoustic signal exists).

  2. Semantic grounding    -- whether the drafted statement is actually
     supported by the text of the segment(s) it claims to cite. This is a
     lightweight lexical-overlap proxy for entailment (kept dependency-free
     for the prototype); a production system would substitute a real NLI/
     entailment model here without changing the gate logic below.

A fact is only auto-inserted into the note if BOTH signals individually
clear a floor AND their combination clears a higher bar. Anything else is
blocked and routed to a clinician review queue -- it never silently enters
the chart. Every decision (auto-gate or human resolution) is appended to
an audit trail and is never overwritten, only appended to.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Dict, List, Any, Optional

from .calibration import CalibrationStore, DEFAULT_THRESHOLD

SEMANTIC_FLOOR = 0.30
ACOUSTIC_FLOOR = 0.50
DEFAULT_TEXT_MODE_ACOUSTIC_CONFIDENCE = 0.95


@dataclass
class GroundingResult:
    semantic_score: float
    acoustic_score: float
    combined_confidence: float
    status: str          # "VERIFIED" | "NEEDS_REVIEW" | "REJECTED"
    reason: str


def _semantic_score(fact_value: str, cited_texts: List[str]) -> float:
    if not cited_texts:
        return 0.0
    combined_evidence = " ".join(cited_texts).lower()

    ratio = difflib.SequenceMatcher(None, fact_value.lower(), combined_evidence).ratio()

    fact_tokens = set(re.findall(r"[a-z0-9]+", fact_value.lower()))
    evidence_tokens = set(re.findall(r"[a-z0-9]+", combined_evidence))
    stopwords = {"a", "an", "the", "and", "or", "is", "am", "i", "to", "for", "of", "in", "on", "my"}
    fact_tokens -= stopwords
    overlap = len(fact_tokens & evidence_tokens) / max(len(fact_tokens), 1)

    return round(0.5 * ratio + 0.5 * overlap, 3)


class GroundingEngine:
    def __init__(self, segments: List[Dict[str, Any]], calibration: Optional[CalibrationStore] = None):
        self._segments_by_id = {s["id"]: s for s in segments}
        self._calibration = calibration

    def _acoustic_score(self, cited_segment_ids: List[int]) -> float:
        scores = []
        for sid in cited_segment_ids:
            seg = self._segments_by_id.get(sid)
            if seg is None:
                continue
            scores.append(seg.get("acoustic_confidence", DEFAULT_TEXT_MODE_ACOUSTIC_CONFIDENCE))
        if not scores:
            return 0.0
        return round(sum(scores) / len(scores), 3)

    def evaluate(self, fact_value: str, cited_segment_ids: List[int], field: str = "") -> GroundingResult:
        cited_texts = []
        for sid in cited_segment_ids:
            seg = self._segments_by_id.get(sid)
            if seg is not None:
                cited_texts.append(seg["text"])

        if not cited_segment_ids or not cited_texts:
            return GroundingResult(0.0, 0.0, 0.0, "REJECTED", "No valid segment citation provided.")

        semantic = _semantic_score(fact_value, cited_texts)
        acoustic = self._acoustic_score(cited_segment_ids)

        if semantic < SEMANTIC_FLOOR:
            return GroundingResult(semantic, acoustic, 0.0, "REJECTED",
                                    f"Semantic grounding {semantic:.2f} below floor {SEMANTIC_FLOOR}.")
        if acoustic < ACOUSTIC_FLOOR:
            return GroundingResult(semantic, acoustic, 0.0, "REJECTED",
                                    f"Acoustic confidence {acoustic:.2f} below floor {ACOUSTIC_FLOOR}.")

        threshold = self._calibration.threshold_for(field) if self._calibration else DEFAULT_THRESHOLD
        combined = round(0.6 * semantic + 0.4 * acoustic, 3)
        if combined >= threshold:
            return GroundingResult(semantic, acoustic, combined, "VERIFIED",
                                    f"Cleared dual-signal threshold ({threshold:.2f} for field '{field}'); auto-inserted.")
        return GroundingResult(semantic, acoustic, combined, "NEEDS_REVIEW",
                                f"Combined confidence {combined:.2f} below auto-insert threshold {threshold:.2f} for field '{field}'.")
