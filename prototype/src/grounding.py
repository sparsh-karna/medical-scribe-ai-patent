"""
Dual-signal confidence gate.

This module is the core novel mechanism of the project. Every drafted
clinical fact must clear these checks before it is allowed to
auto-populate the structured note:

  0. Citation integrity -- the fact cites real transcript segments, and
     every verbatim evidence quote the extractor supplied actually occurs
     in the segment it is attributed to (fuzzy-aligned, so punctuation /
     casing differences do not matter, but invented or mis-attributed
     evidence does).

  1. Acoustic confidence -- how confident the speech recognizer was about
     the exact words the evidence quotes. Computed from Whisper's
     per-word probabilities over the aligned quote span (falling back to
     the whole segment's word probabilities when a quote cannot be
     aligned to word timings). Text-only input has no acoustic signal;
     it is reported as unavailable rather than filled in, and the gate
     then decides on the semantic signal alone and says so.

  2. Semantic grounding -- whether the cited segments actually entail the
     drafted statement, scored by a local NLI model (src/entailment.py).
     A statement the evidence contradicts is rejected outright.

A fact is only auto-inserted if every available signal clears its floor
AND the combined score clears the field's (adaptive) threshold. Anything
else is blocked and routed to a clinician review queue -- it never
silently enters the chart. Every decision (auto-gate or human resolution)
is appended to an audit trail and is never overwritten.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from rapidfuzz import fuzz

from .calibration import CalibrationStore, DEFAULT_THRESHOLD
from .entailment import score_pairs

SEMANTIC_FLOOR = 0.30           # minimum P(entailment)
CONTRADICTION_CEILING = 0.50    # P(contradiction) at or above this -> reject
ACOUSTIC_FLOOR = 0.50           # minimum mean ASR word probability over the quoted span
QUOTE_MATCH_MIN = 90.0          # minimum fuzzy alignment score (0-100) for a quote
SEMANTIC_WEIGHT = 0.6
ACOUSTIC_WEIGHT = 0.4
LOW_CONFIDENCE_WORD = 0.5       # words below this are reported as weak
# An average can hide one badly recognised word ("no blood in the stalk" averaged 0.84).
# If the weakest *content* word of the quoted span is below this, the fact cannot be
# auto-inserted (it goes to review, it is not rejected: a weak word is not proof of error).
WEAKEST_CONTENT_WORD_FLOOR = 0.35
FUNCTION_WORDS = {
    "a", "an", "the", "and", "or", "but", "so", "if", "of", "to", "in", "on", "at", "for", "with", "by", "from",
    "is", "are", "was", "were", "be", "been", "am", "it", "its", "this", "that", "i", "you", "he", "she", "we",
    "they", "me", "my", "your", "our", "um", "uh", "erm", "hmm", "mm", "oh", "ok", "okay", "yeah", "yes", "well",
    "just", "like", "do", "does", "did", "have", "has", "had", "would", "could", "can", "will", "as", "then",
}


@dataclass
class GroundingResult:
    semantic_score: float                 # P(entailment)
    acoustic_score: Optional[float]       # None when the input has no audio
    combined_confidence: float
    status: str                           # "VERIFIED" | "NEEDS_REVIEW" | "REJECTED"
    reason: str
    nli: Dict[str, float] = field(default_factory=dict)
    evidence_checks: List[Dict[str, Any]] = field(default_factory=list)
    weak_words: List[Dict[str, Any]] = field(default_factory=list)
    weakest_content_word: Optional[Dict[str, Any]] = None


def _speaker_label(speaker: str) -> str:
    return {"DOCTOR": "Doctor", "PATIENT": "Patient"}.get(speaker, speaker.title())


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _align_quote(quote: str, seg_text: str):
    """Fuzzy-align a quote inside the segment text; returns (score, start, end) char span."""
    q, t = _norm(quote), seg_text.lower()
    if not q:
        return 0.0, 0, 0
    al = fuzz.partial_ratio_alignment(q, t)
    if al is None:
        return 0.0, 0, 0
    return round(al.score, 1), al.dest_start, al.dest_end


def _span_words(seg: Dict[str, Any], start: int, end: int) -> List[Dict[str, Any]]:
    """ASR words whose character range overlaps [start, end) of the segment text."""
    return [w for w in seg.get("words") or []
            if w["char_end"] > start and w["char_start"] < end]


class GroundingEngine:
    def __init__(self, segments: List[Dict[str, Any]], calibration: Optional[CalibrationStore] = None):
        self._segments_by_id = {s["id"]: s for s in segments}
        self._calibration = calibration

    def _premise(self, cited_ids: List[int]) -> str:
        segs = [self._segments_by_id[i] for i in sorted(set(cited_ids))]
        return " ".join(f"{_speaker_label(s['speaker'])}: {s['text']}" for s in segs)

    def _check_evidence(self, evidence: List[Dict[str, Any]]):
        """Verify each quote occurs in its segment; collect the ASR words it spans."""
        checks, words = [], []
        for ev in evidence:
            seg = self._segments_by_id.get(ev["segment_id"])
            if seg is None:
                continue
            score, start, end = _align_quote(ev["quote"], seg["text"])
            span = _span_words(seg, start, end) if score >= QUOTE_MATCH_MIN else []
            checks.append({"segment_id": ev["segment_id"], "quote": ev["quote"],
                           "match": score, "found": score >= QUOTE_MATCH_MIN,
                           "char_start": start, "char_end": end})
            words.extend(span)
        return checks, words

    def _acoustic(self, cited_ids: List[int], span_words: List[Dict[str, Any]]):
        """Mean word probability over the quoted span; whole cited segments as fallback.
        Returns (score or None, weak words, weakest content word or None)."""
        words = span_words
        if not words:
            words = [w for i in cited_ids for w in (self._segments_by_id[i].get("words") or [])]
        if not words:
            return None, [], None
        score = round(sum(w["prob"] for w in words) / len(words), 3)
        weak = [{"word": w["text"].strip(), "prob": w["prob"]} for w in words if w["prob"] < LOW_CONFIDENCE_WORD]
        content = [w for w in words if re.sub(r"[^a-z']", "", w["text"].lower()) not in FUNCTION_WORDS
                   and re.search(r"[a-z0-9]", w["text"].lower())]
        weakest = None
        if content:
            w = min(content, key=lambda w: w["prob"])
            weakest = {"word": w["text"].strip(), "prob": w["prob"]}
        return score, weak, weakest

    def evaluate_many(self, facts: List[Any]) -> List[GroundingResult]:
        """Gate a batch of facts (each with .field, .value, .cited_segment_ids, .evidence).
        NLI runs once, batched, over every fact that passes citation integrity."""
        results: List[Optional[GroundingResult]] = [None] * len(facts)
        pending = []  # (index, cited_ids, checks, span_words)

        for i, fact in enumerate(facts):
            cited = [sid for sid in fact.cited_segment_ids if sid in self._segments_by_id]
            if not cited:
                results[i] = GroundingResult(0.0, None, 0.0, "REJECTED", "No valid segment citation provided.")
                continue
            if not fact.evidence:
                results[i] = GroundingResult(0.0, None, 0.0, "REJECTED",
                                             "No verbatim evidence quoted for the cited segments.")
                continue
            checks, span_words = self._check_evidence(fact.evidence)
            missing = [c for c in checks if not c["found"]]
            if missing:
                c = missing[0]
                results[i] = GroundingResult(
                    0.0, None, 0.0, "REJECTED",
                    f"Quoted evidence \"{c['quote']}\" does not occur in segment #{c['segment_id']} "
                    f"(best alignment {c['match']:.0f}/100) -- citation is invented or mis-attributed.",
                    evidence_checks=checks)
                continue
            pending.append((i, cited, checks, span_words))

        nli = score_pairs([(self._premise(cited), facts[i].value) for i, cited, _, _ in pending])
        for (i, cited, checks, span_words), probs in zip(pending, nli):
            results[i] = self._decide(facts[i], cited, checks, span_words, probs)
        return results

    def _decide(self, fact, cited, checks, span_words, probs) -> GroundingResult:
        semantic = round(probs["entailment"], 3)
        acoustic, weak, weakest = self._acoustic(cited, span_words)

        def result(combined, status, reason):
            return GroundingResult(semantic, acoustic, combined, status, reason, probs, checks, weak, weakest)

        if probs["contradiction"] >= CONTRADICTION_CEILING:
            return result(0.0, "REJECTED",
                          f"Cited evidence contradicts the statement (P(contradiction) {probs['contradiction']:.2f}).")
        if semantic < SEMANTIC_FLOOR:
            return result(0.0, "REJECTED",
                          f"Cited evidence does not entail the statement (P(entailment) {semantic:.2f} "
                          f"below floor {SEMANTIC_FLOOR}).")
        if acoustic is not None and acoustic < ACOUSTIC_FLOOR:
            weak_txt = ", ".join(f"'{w['word']}' {w['prob']:.2f}" for w in weak[:5])
            return result(0.0, "REJECTED",
                          f"Acoustic confidence {acoustic:.2f} below floor {ACOUSTIC_FLOOR}"
                          + (f" (weak words: {weak_txt})." if weak_txt else "."))

        threshold = self._calibration.threshold_for(fact.field) if self._calibration else DEFAULT_THRESHOLD
        if acoustic is None:
            combined = semantic
            basis = "semantic signal only -- text input has no acoustic signal"
        else:
            combined = round(SEMANTIC_WEIGHT * semantic + ACOUSTIC_WEIGHT * acoustic, 3)
            basis = f"entailment {semantic:.2f}, acoustic {acoustic:.2f}"
        if combined >= threshold and weakest is not None and weakest["prob"] < WEAKEST_CONTENT_WORD_FLOOR:
            return result(combined, "NEEDS_REVIEW",
                          f"Combined confidence {combined:.2f} clears threshold {threshold:.2f}, but quoted word "
                          f"'{weakest['word']}' was recognised with probability {weakest['prob']:.2f} (below "
                          f"{WEAKEST_CONTENT_WORD_FLOOR}); check the audio before inserting.")
        if combined >= threshold:
            return result(combined, "VERIFIED",
                          f"Cleared threshold {threshold:.2f} for '{fact.field}' ({basis}); auto-inserted.")
        return result(combined, "NEEDS_REVIEW",
                      f"Combined confidence {combined:.2f} below auto-insert threshold {threshold:.2f} "
                      f"for '{fact.field}' ({basis}).")
