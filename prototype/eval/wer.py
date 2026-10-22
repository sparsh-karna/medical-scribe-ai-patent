"""
Word error rate and word-level error labelling for evaluating the ASR stage
against PriMock57's human transcripts.

Normalisation (applied to both sides): lower-case, unify UK/US spellings of
a few frequent words, strip punctuation except apostrophes, drop fillers.

label_hypothesis_words() aligns the recognised words to the reference with
a word-level Levenshtein alignment and marks each recognised word as
correct or as an error (substituted or inserted). Each recognised word keeps
its ASR probability, which is what lets us test whether the acoustic signal
actually points at recognition errors.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

from rapidfuzz.distance import Levenshtein

FILLERS = {"um", "uh", "erm", "hmm", "mm", "mhm", "ah", "er", "uhm", "umm", "hm"}
SPELLING = {"diarrhoea": "diarrhea", "colour": "color", "paediatric": "pediatric", "oesophagus": "esophagus",
            "haemorrhoids": "hemorrhoids", "anaemia": "anemia", "behaviour": "behavior", "favour": "favor"}


def norm_tokens(text: str) -> List[str]:
    t = re.sub(r"[^a-z0-9' ]", " ", text.lower())
    out = []
    for w in t.split():
        w = w.strip("'")
        w = SPELLING.get(w, w)
        if w and w not in FILLERS:
            out.append(w)
    return out


def wer(ref: List[str], hyp: List[str]) -> Tuple[int, int]:
    """Returns (edit distance, reference length)."""
    return Levenshtein.distance(ref, hyp), len(ref)


def hyp_tokens_with_prob(segments: Iterable[Dict]) -> Tuple[List[str], List[float]]:
    """Normalised recognised tokens in order, each with its source word's ASR probability."""
    toks, probs = [], []
    for s in segments:
        for w in s.get("words") or []:
            for t in norm_tokens(w["text"]):
                toks.append(t)
                probs.append(w["prob"])
    return toks, probs


def label_hypothesis_words(ref: List[str], hyp: List[str]) -> List[bool]:
    """True for each hypothesis token that is a recognition error (substitution or insertion)."""
    is_err = [False] * len(hyp)
    for op in Levenshtein.opcodes(ref, hyp):
        if op.tag in ("replace", "insert"):
            for j in range(op.dest_start, op.dest_end):
                is_err[j] = True
    return is_err


def confidence_vs_errors(probs: List[float], is_err: List[bool], cut: float = 0.5) -> Dict[str, float]:
    """How well 'probability < cut' flags recognition errors."""
    err = [p for p, e in zip(probs, is_err) if e]
    ok = [p for p, e in zip(probs, is_err) if not e]
    flagged = [e for p, e in zip(probs, is_err) if p < cut]
    tp = sum(flagged)
    return {
        "words": len(probs), "error_words": len(err),
        "mean_prob_correct": round(sum(ok) / len(ok), 4) if ok else None,
        "mean_prob_error": round(sum(err) / len(err), 4) if err else None,
        f"flag_precision_at_{cut}": round(tp / len(flagged), 4) if flagged else None,
        f"flag_recall_at_{cut}": round(tp / len(err), 4) if err else None,
        "auroc": auroc(probs, is_err),
    }


def auroc(probs: List[float], is_err: List[bool]) -> float | None:
    """P(a random error word has lower probability than a random correct word); ties count half.
    0.5 = no better than chance, 1.0 = probability perfectly separates errors from correct words."""
    pairs = sorted(zip(probs, is_err))
    n_err = sum(is_err)
    n_ok = len(is_err) - n_err
    if not n_err or not n_ok:
        return None
    # rank-sum (Mann-Whitney U) with average ranks for ties
    ranks, i = [0.0] * len(pairs), 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        for k in range(i, j + 1):
            ranks[k] = (i + j) / 2 + 1
        i = j + 1
    rank_sum_ok = sum(r for r, (_, e) in zip(ranks, pairs) if not e)
    u_ok = rank_sum_ok - n_ok * (n_ok + 1) / 2   # pairs where a correct word outranks an error word
    return round(u_ok / (n_ok * n_err), 4)
