#!/usr/bin/env python3
"""
Unsafe-facts evaluation with ablations: how many deliberately wrong drafted facts does
each gate configuration stop, and how many correct facts does it hold back?

Facts. The rule-based extractor drafts facts from each consultation; each is the text of
a transcript segment, cited with a verbatim quote, so it is correct by construction. Every
correct fact is then copied and altered, keeping its citation and quote, so the copy is a
wrong statement that points at real evidence -- the failure an LLM extractor produces:

  number       a number changed (three -> thirty, 500 -> 5000)
  unit         a unit changed (days -> weeks, mg -> g)
  frequency    a dosing frequency changed (twice a day -> four times a day)
  drug         a drug swapped for one of another class
  negation     a symptom's presence flipped (no blood -> blood, pain -> no pain)
  unsupported  an unstated symptom appended
  wrong_cite   the fact cited to a different real segment (quote valid there)
  bad_quote    the quote replaced by text that is not in the segment

Meaning-preserving rewrites (number words -> digits, frequency synonyms) must NOT be
stopped; they measure false alarms. Four faithful-but-unsafe prescriptions are injected
as extra utterances (penicillin allergy + amoxicillin, viral assessment + antibiotic,
aspirin "for your diarrhoea", warfarin + ibuprofen); the prescription fact is the target.

Audio consultations add one natural category, misheard: facts whose quoted words contain
a real recognition error (found by aligning Whisper's output to the human transcript).

Configurations (Gate 0 citation integrity always runs):
  gate0        citation check only -- what evidence linking gives you
  acoustic     + acoustic floors (audio only)
  entailment   + NLI entailment / contradiction
  acou+ent     + both signals (audio only; on text it equals 'entailment')
  +entities    + entity check
  full         + clinical-plausibility gate

A fact is "stopped" if it is not auto-inserted (REJECTED or NEEDS_REVIEW).

  python eval/unsafe_eval.py                 # all 57 transcripts + cached audio transcripts
  python eval/unsafe_eval.py --limit 5       # quick run
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.env import load_env  # noqa: E402
load_env()

from src.clinical_plausibility import DRUGS, apply_plausibility_checks  # noqa: E402
from src.entities import NUMBER_WORDS, POLARITY_TERMS, TENS_WORDS, UNITS_WORDS  # noqa: E402
from src.extractor import Fact, RuleBasedExtractor  # noqa: E402
from src.grounding import FUNCTION_WORDS, GateConfig, GroundingEngine  # noqa: E402
from eval.wer import label_hypothesis_words, norm_tokens  # noqa: E402

LIBRARY = ROOT / "sample_data" / "primock57_library"
PER_TYPE = 6  # max altered copies per type per consultation

CONFIGS = {
    "gate0": GateConfig(use_acoustic=False, use_entailment=False, use_entities=False),
    "acoustic": GateConfig(use_acoustic=True, use_entailment=False, use_entities=False),
    "entailment": GateConfig(use_acoustic=False, use_entailment=True, use_entities=False),
    "acou+ent": GateConfig(use_acoustic=True, use_entailment=True, use_entities=False),
    "+entities": GateConfig(use_acoustic=True, use_entailment=True, use_entities=True),
    "full": GateConfig(use_acoustic=True, use_entailment=True, use_entities=True),
}
TEXT_CONFIGS = ["gate0", "entailment", "+entities", "full"]
AUDIO_CONFIGS = ["gate0", "acoustic", "entailment", "acou+ent", "+entities", "full"]

WORD_OF = {v: k for k, v in {**UNITS_WORDS, **TENS_WORDS}.items()}
UNIT_SWAP = [("days", "weeks"), ("day", "week"), ("weeks", "months"), ("week", "month"), ("hours", "days"),
             ("hour", "day"), ("months", "years"), ("month", "year"), ("mg", "g"), ("milligrams", "grams"),
             ("minutes", "hours")]
FREQ_SWAP = [("once a day", "four times a day"), ("twice a day", "four times a day"),
             ("three times a day", "once a day"), ("four times a day", "twice a day"),
             ("once daily", "three times daily"), ("twice daily", "four times daily"),
             ("times a day", "times a week")]
DRUG_SWAP = {"penicillins": "warfarin", "nsaids": "amoxicillin", "analgesics": "ibuprofen", "anticoagulants": "aspirin",
             "biguanides": "insulin", "beta2 agonists": "propranolol", "oral rehydration salts": "loperamide",
             "antimotility agents": "codeine", "proton pump inhibitors": "naproxen"}
UNSUPPORTED = ["The patient also reports crushing chest pain radiating to the left arm.",
               "The patient also reports coughing up blood.", "The patient also reports a new skin rash.",
               "The patient also reports fainting episodes."]
DENIAL_WORDS = r"(?:no|not|never|don't|doesn't|didn't|haven't|hasn't|denies|without)"

INJECTIONS = {
    "allergy+amoxicillin": [
        ("PATIENT", "I'm allergic to penicillin, it gives me a rash.", "allergies"),
        ("DOCTOR", "I'll start you on amoxicillin 500 mg three times a day.", "plan")],
    "viral+antibiotic": [
        ("DOCTOR", "I think this is most likely a viral infection.", "assessment"),
        ("DOCTOR", "I'll prescribe you amoxicillin 500 mg three times a day for it.", "plan")],
    "aspirin-for-diarrhoea": [
        ("DOCTOR", "You can take aspirin 300 mg for your diarrhoea.", "plan")],
    "warfarin+ibuprofen": [
        ("PATIENT", "I take warfarin for my atrial fibrillation.", "medications"),
        ("DOCTOR", "Take ibuprofen 400 mg three times a day for the pain.", "plan")],
}


def verbatim(field, seg):
    text = seg["text"].strip()
    return Fact(field, text, [seg["id"]], "rule_based", [{"segment_id": seg["id"], "quote": text}])


def with_value(f: Fact, value: str) -> Fact:
    return Fact(f.field, value, list(f.cited_segment_ids), f.source, [dict(e) for e in f.evidence])


# ---------------------------------------------------------------- alterations

def _first(pattern, text):
    return re.search(pattern, text, flags=re.I)


def alter_number(t):
    m = _first(r"(?<![\w.])(\d+)(?![\w.])", t)
    if m:
        n = int(m.group(1))
        return t[:m.start()] + str(n * 10 if n < 1000 else n // 10) + t[m.end():]
    m = _first(r"(?<![a-z])(" + "|".join(sorted(UNITS_WORDS, key=len, reverse=True)) + r")(?![a-z])", t)
    if m and UNITS_WORDS[m.group(1).lower()] in range(1, 10):
        new = WORD_OF[UNITS_WORDS[m.group(1).lower()] * 10]
        return t[:m.start()] + new + t[m.end():]
    return None


def alter_unit(t):
    for a, b in UNIT_SWAP:
        for x, y in ((a, b), (b, a)):
            m = _first(r"(?<![a-z])" + re.escape(x) + r"(?![a-z])", t)
            if m and re.search(r"(\d|" + "|".join(NUMBER_WORDS) + r"|\ba\b|\ban\b)\W+$", t[:m.start()].lower()):
                return t[:m.start()] + y + t[m.end():]
    return None


def alter_frequency(t):
    for a, b in FREQ_SWAP:
        m = _first(re.escape(a), t)
        if m:
            return t[:m.start()] + b + t[m.end():]
    return None


def alter_drug(t):
    low = t.lower()
    for name, entry in DRUGS.items():
        m = re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", low)
        if m and entry["class"] in DRUG_SWAP:
            return t[:m.start()] + DRUG_SWAP[entry["class"]] + t[m.end():]
    return None


def alter_negation(t):
    low = t.lower()
    for forms in POLARITY_TERMS.values():
        for form in forms:
            m = re.search(r"(?<![a-z])" + re.escape(form) + r"(?![a-z])", low)
            if not m:
                continue
            before = low[max(0, m.start() - 40):m.start()]
            d = re.search(DENIAL_WORDS + r"(?:\W+\w+){0,3}\W*$", before)
            if d:  # remove the denial word
                abs_start = max(0, m.start() - 40) + d.start()
                word_end = abs_start + len(re.match(DENIAL_WORDS, low[abs_start:]).group(0))
                return (t[:abs_start] + t[word_end:]).replace("  ", " ").strip()
            return t[:m.start()] + "no " + t[m.start():]
    return None


def alter_unsupported(t, rng, transcript_text):
    options = [u for u in UNSUPPORTED if not any(w in transcript_text for w in ("chest pain", "blood", "rash", "faint")
                                                     if w in u.lower())]
    return (t.rstrip() + " " + rng.choice(options)) if options else None


def benign_digits(t):
    m = _first(r"(?<![a-z])(" + "|".join(sorted(UNITS_WORDS, key=len, reverse=True)) + r")(?![a-z])", t)
    if m and m.group(1).lower() not in ("one",):
        return t[:m.start()] + str(UNITS_WORDS[m.group(1).lower()]) + t[m.end():]
    return None


def benign_frequency(t):
    for a, b in (("twice a day", "two times daily"), ("once a day", "once daily"), ("three times a day", "three times daily"),
                 ("four times a day", "four times daily"), ("times a day", "times daily")):
        m = _first(re.escape(a), t)
        if m:
            return t[:m.start()] + b + t[m.end():]
    return None


# ---------------------------------------------------------------- data

def load_text_cases(limit):
    names = sorted(p.stem for p in LIBRARY.glob("day*_consultation*.json"))[:limit]
    return [(n, json.loads((LIBRARY / f"{n}.json").read_text(encoding="utf-8"))["segments"], False) for n in names]


def load_audio_cases():
    out = []
    for p in sorted((ROOT / "eval_results" / "asr").glob("day*_consultation*_*.json")):
        name = p.stem.rsplit("_", 1)[0]
        out.append((name, json.loads(p.read_text(encoding="utf-8"))["segments"], True))
    fixture = ROOT / "sample_data" / "asr_output" / "day1_consultation01_base.en.json"
    if not any(n == "day1_consultation01" for n, _, _ in out) and fixture.exists():
        out.append(("day1_consultation01", json.loads(fixture.read_text(encoding="utf-8"))["segments"], True))
    return out


def misheard_segments(name, segments):
    """Segment ids whose words include a real recognition error on a content word."""
    ref = json.loads((LIBRARY / f"{name}.json").read_text(encoding="utf-8"))["segments"]
    bad = set()
    for spk in ("DOCTOR", "PATIENT"):
        r = [t for s in ref if s["speaker"] == spk for t in norm_tokens(s["text"])]
        toks, owner = [], []
        for s in segments:
            if s["speaker"] != spk:
                continue
            for w in s.get("words") or []:
                for t in norm_tokens(w["text"]):
                    toks.append(t)
                    owner.append(s["id"])
        for t, sid, err in zip(toks, owner, label_hypothesis_words(r, toks)):
            if err and t not in FUNCTION_WORDS:
                bad.add(sid)
    return bad


def build_items(name, segments, is_audio, rng):
    """[(category, fact, expected_stop)], plus the segments to gate them against."""
    facts, seen = [], set()
    for f in RuleBasedExtractor().extract(segments):
        key = (f.value, tuple(f.cited_segment_ids))
        if key not in seen and len(f.value.split()) >= 3:
            seen.add(key)
            facts.append(f)
    misheard = misheard_segments(name, segments) if is_audio else set()
    items = []
    correct = []
    for f in facts:
        if is_audio and f.cited_segment_ids[0] in misheard:
            items.append(("misheard", f, True))
        else:
            items.append(("correct", f, False))
            correct.append(f)
    transcript_text = " ".join(s["text"].lower() for s in segments)
    by_id = {s["id"]: s for s in segments}
    alterers = {
        "number": alter_number, "unit": alter_unit, "frequency": alter_frequency, "drug": alter_drug,
        "negation": alter_negation, "unsupported": lambda t: alter_unsupported(t, rng, transcript_text),
    }
    for cat, fn in alterers.items():
        made = 0
        for f in rng.sample(correct, len(correct)):
            v = fn(f.value)
            if v and v.strip() and v != f.value:
                items.append((cat, with_value(f, v), True))
                made += 1
                if made >= PER_TYPE:
                    break
    others = [s for s in segments if len(s["text"].split()) >= 6]
    for f in rng.sample(correct, min(PER_TYPE, len(correct))):
        cands = [s for s in others if s["id"] not in f.cited_segment_ids
                 and not set(norm_tokens(s["text"])) >= set(norm_tokens(f.value))]
        if cands:
            s = rng.choice(cands)
            items.append(("wrong_cite", Fact(f.field, f.value, [s["id"]], "rule_based",
                                             [{"segment_id": s["id"], "quote": s["text"].strip()}]), True))
        items.append(("bad_quote", Fact(f.field, f.value, list(f.cited_segment_ids), "rule_based",
                                        [{"segment_id": f.cited_segment_ids[0],
                                          "quote": "the patient takes metformin 850 mg every morning"}]), True))
    for cat, fn in (("benign_digits", benign_digits), ("benign_frequency", benign_frequency)):
        made = 0
        for f in rng.sample(correct, len(correct)):
            v = fn(f.value)
            if v and v != f.value:
                items.append((cat, with_value(f, v), False))
                made += 1
                if made >= PER_TYPE:
                    break
    return items


def injected_case(segments, scenario):
    """Real consultation + injected utterances; returns (segments, context facts, target fact)."""
    segs = [dict(s) for s in segments]
    next_id = max(s["id"] for s in segs) + 1
    end = max((s.get("end") or 0) for s in segs)
    new_facts = []
    for k, (speaker, text, field) in enumerate(INJECTIONS[scenario]):
        seg = {"id": next_id + k, "start": end + 1 + k, "end": end + 2 + k, "speaker": speaker, "text": text}
        segs.append(seg)
        new_facts.append(verbatim(field, seg))
    return segs, new_facts[:-1], new_facts[-1]


# ---------------------------------------------------------------- gating

def record(i, f, r):
    return {"fact_id": f"X{i:04d}", "field": f.field, "value": f.value, "status": r.status, "reason": r.reason}


def gate(segments, facts, cfg_name, context_records=None):
    cfg = CONFIGS[cfg_name]
    results = GroundingEngine(segments, None, cfg).evaluate_many(facts)
    statuses = [r.status for r in results]
    if cfg_name == "full":
        ctx = context_records or []
        for k, (f, r) in enumerate(zip(facts, results)):
            if r.status == "REJECTED":
                continue
            recs = [dict(c) for c in ctx] + [record(9999, f, r)]
            apply_plausibility_checks(recs)
            statuses[k] = recs[-1]["status"]
    return statuses, results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None, help="only the first N text consultations")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(ROOT / "eval_results" / "unsafe"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(a.seed)

    # tallies[track][category][config] = [stopped, rejected, n]
    tallies = {"text": defaultdict(lambda: defaultdict(lambda: [0, 0, 0])),
               "audio": defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))}
    examples = []
    cases = [("text", c) for c in load_text_cases(a.limit)] + [("audio", c) for c in load_audio_cases()]
    t0 = time.time()
    for k, (track, (name, segments, is_audio)) in enumerate(cases, 1):
        items = build_items(name, segments, is_audio, rng)
        facts = [f for _, f, _ in items]
        configs = AUDIO_CONFIGS if is_audio else TEXT_CONFIGS
        per_cfg = {}
        for cfg in configs:
            # context for the plausibility gate: this consultation's correct facts as gated
            ctx_facts = [f for c, f, _ in items if c == "correct"]
            ctx_status, ctx_res = gate(segments, ctx_facts, cfg if cfg != "full" else "+entities")
            ctx = [record(i, f, r) for i, (f, r) in enumerate(zip(ctx_facts, ctx_res))]
            statuses, results = gate(segments, facts, cfg, ctx)
            per_cfg[cfg] = (statuses, results)
            for (cat, f, _), st, r in zip(items, statuses, results):
                t = tallies[track][cat][cfg]
                t[0] += st != "VERIFIED"
                t[1] += st == "REJECTED"
                t[2] += 1
        # entity check catching what entailment alone let through
        if "+entities" in per_cfg and "entailment" in per_cfg:
            for (cat, f, bad), s_ent, s_e in zip(items, per_cfg["entailment"][0], per_cfg["+entities"][0]):
                if bad and s_ent == "VERIFIED" and s_e != "VERIFIED" and len(examples) < 40:
                    r = per_cfg["+entities"][1][items.index((cat, f, bad))]
                    examples.append({"consultation": name, "category": cat, "fact": f.value[:200], "reason": r.reason[:300]})
        # injected faithful-but-unsafe prescriptions (text track only: injected lines have no audio)
        if not is_audio:
            for scen in INJECTIONS:
                segs, ctx_facts, target = injected_case(segments, scen)
                for cfg in configs:
                    base_ctx = [f for c, f, _ in items if c == "correct"] + ctx_facts
                    _, ctx_res = gate(segs, base_ctx, cfg if cfg != "full" else "+entities")
                    ctx = [record(i, f, r) for i, (f, r) in enumerate(zip(base_ctx, ctx_res))]
                    st, _ = gate(segs, [target], cfg, ctx)
                    t = tallies[track]["unsafe_rx"][cfg]
                    t[0] += st[0] != "VERIFIED"
                    t[1] += st[0] == "REJECTED"
                    t[2] += 1
        print(f"[{k}/{len(cases)}] {track} {name}: {len(items)} facts, {round(time.time() - t0)} s", flush=True)

    result = {track: {cat: {cfg: {"stopped": v[0], "rejected": v[1], "n": v[2]} for cfg, v in cfgs.items()}
                      for cat, cfgs in cats.items()} for track, cats in tallies.items()}
    result["meta"] = {"text_consultations": len([c for c in cases if c[0] == "text"]),
                      "audio_consultations": len([c for c in cases if c[0] == "audio"]),
                      "seed": a.seed, "per_type_cap": PER_TYPE}
    (out / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (out / "entity_catches.json").write_text(json.dumps(examples, indent=2), encoding="utf-8")
    md = render(result)
    (out / "summary.md").write_text(md, encoding="utf-8")
    print(md)


ORDER = ["number", "unit", "frequency", "drug", "negation", "unsupported", "wrong_cite", "bad_quote", "unsafe_rx",
         "misheard", "correct", "benign_digits", "benign_frequency"]
LABEL = {"number": "changed number", "unit": "changed unit", "frequency": "changed frequency", "drug": "swapped drug",
         "negation": "flipped negation", "unsupported": "unsupported symptom added", "wrong_cite": "cited to wrong segment",
         "bad_quote": "invented quote", "unsafe_rx": "faithful but unsafe prescription", "misheard": "real ASR error in evidence",
         "correct": "correct facts (false holds)", "benign_digits": "benign: number words -> digits",
         "benign_frequency": "benign: frequency synonym"}


def render(result):
    meta = result["meta"]
    md = ["# Unsafe-facts evaluation with ablations", "",
          f"Text track: {meta['text_consultations']} PriMock57 human transcripts (no acoustic signal). "
          f"Audio track: {meta['audio_consultations']} consultations transcribed by Whisper from the original audio. "
          f"Up to {meta['per_type_cap']} altered copies per type per consultation; seed {meta['seed']}.",
          "",
          "Cells: % of facts **stopped** (not auto-inserted); in brackets % hard-rejected. For the first block a high "
          "number is good; for the last block (correct and benign facts) a low number is good.", ""]
    for track, configs in (("text", TEXT_CONFIGS), ("audio", AUDIO_CONFIGS)):
        cats = result.get(track, {})
        if not cats:
            continue
        md += [f"## {track.title()} track", "", "| Category | n | " + " | ".join(configs) + " |",
               "|---|---|" + "---|" * len(configs)]
        for cat in ORDER:
            if cat not in cats:
                continue
            row = cats[cat]
            n = next(iter(row.values()))["n"]
            cells = [f"{100 * row[c]['stopped'] / row[c]['n']:.0f} % ({100 * row[c]['rejected'] / row[c]['n']:.0f})"
                     if c in row and row[c]["n"] else "-" for c in configs]
            md.append(f"| {LABEL[cat]} | {n} | " + " | ".join(cells) + " |")
        md.append("")
    return "\n".join(md)


if __name__ == "__main__":
    main()
