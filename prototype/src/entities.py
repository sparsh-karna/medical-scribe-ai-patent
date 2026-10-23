"""
Clinical entity check (part of Gate 2).

The entailment model judges whole sentences. A drafted fact can still differ
from its evidence in one small, safety-critical detail -- a dose, a unit, a
frequency, a drug name, or whether a symptom was present or denied -- and
that detail can be easy to miss inside a long spoken sentence. This module
extracts those entities from the fact and from the cited evidence and
requires every entity the fact states to be present, with the same value,
in the evidence:

  numbers    every number in the fact appears in the evidence; if the fact
             attaches a unit to it, the evidence does not attach a different
             unit to that number (3 days vs 3 weeks); durations are compared
             in days (a week == 7 days)
  frequency  every dosing frequency in the fact (twice a day, every 4 hours,
             as needed, ...) appears in the evidence, compared in canonical
             form (bd == twice daily == two times a day)
  drugs      every drug named in the fact is named in the evidence
             (synonyms such as paracetamol / acetaminophen are equal)
  negation   a clinical term the fact affirms is not only denied in the
             evidence, and vice versa; mentions inside questions are ignored
             (the answer, not the question, carries the polarity)

Spoken numbers are normalised first ("five hundred milligrams" -> 500 mg).
The check is deterministic and every mismatch is reported in words.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from .clinical_plausibility import CONDITIONS, DRUGS

# ---------------------------------------------------------------- numbers

UNITS_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
TENS_WORDS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
              "eighty": 80, "ninety": 90}
SCALE_WORDS = {"hundred": 100, "thousand": 1000}
NUMBER_WORDS = set(UNITS_WORDS) | set(TENS_WORDS) | set(SCALE_WORDS)


def words_to_digits(text: str) -> str:
    """'five hundred and twenty' -> '520', 'two tablets' -> '2 tablets'."""
    tokens = re.findall(r"[A-Za-z]+(?:-[A-Za-z]+)?|\d+(?:\.\d+)?|[^A-Za-z\d]+", text)
    out: List[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        parts = tok.lower().split("-")
        if all(p in NUMBER_WORDS for p in parts):
            total, current, j = 0, 0, i
            consumed_end = i
            while j < len(tokens):
                t = tokens[j].lower()
                ps = t.split("-")
                if all(p in NUMBER_WORDS for p in ps):
                    for p in ps:
                        if p in UNITS_WORDS:
                            current += UNITS_WORDS[p]
                        elif p in TENS_WORDS:
                            current += TENS_WORDS[p]
                        else:
                            current = max(current, 1) * SCALE_WORDS[p]
                            if SCALE_WORDS[p] >= 1000:
                                total, current = total + current, 0
                    consumed_end = j
                    j += 1
                elif t.strip() == "" and j + 1 < len(tokens):
                    j += 1  # whitespace between number words
                elif (t == "and" and j + 2 < len(tokens) and _prev_word(tokens, j) in SCALE_WORDS
                      and all(p in NUMBER_WORDS for p in tokens[j + 2].lower().split("-"))):
                    j += 1  # "five hundred and twenty"
                else:
                    break
            out.append(str(total + current))
            i = consumed_end + 1
            continue
        out.append(tok)
        i += 1
    return "".join(out)


def _prev_word(tokens: List[str], j: int) -> str:
    k = j - 1
    while k >= 0 and not tokens[k].strip():
        k -= 1
    return tokens[k].lower() if k >= 0 else ""


# Denial cues for the polarity check. Deliberately excludes "stop"/"stopped": "now I've
# stopped vomiting" says the vomiting ended, not that it was denied.
DENIAL = re.compile(r"(?<![a-z])(?:no|not|none|never|without|denies|denied|deny|nor|"
                    r"don't|doesn't|didn't|haven't|hasn't|hadn't|isn't|aren't|wasn't|weren't|can't|"
                    r"free of|negative for)(?![a-z])(?:\W+\w+){0,4}\W*$")


def _denied(clause: str, pos: int) -> bool:
    window = re.split(r"[.;,:!?]| but ", clause[max(0, pos - 60):pos])[-1]
    return DENIAL.search(window) is not None


UNIT_FORMS = {
    "mg": ["mg", "milligram", "milligrams", "milligramme", "milligrammes"],
    "mcg": ["mcg", "microgram", "micrograms", "ug"],
    "g": ["g", "gram", "grams", "gramme", "grammes"],
    "ml": ["ml", "millilitre", "millilitres", "milliliter", "milliliters", "mls"],
    "unit": ["unit", "units", "iu"],
    "tablet": ["tablet", "tablets", "tab", "tabs", "pill", "pills", "capsule", "capsules"],
    "puff": ["puff", "puffs"],
    "drop": ["drop", "drops"],
    "percent": ["%", "percent", "per cent"],
    "bpm": ["bpm", "beats per minute"],
    "mmhg": ["mmhg"],
    "degree": ["degree", "degrees", "°c", "°f", "celsius", "fahrenheit"],
    "kg": ["kg", "kilo", "kilos", "kilogram", "kilograms"],
    "minute": ["minute", "minutes", "min", "mins"],
    "hour": ["hour", "hours", "hr", "hrs"],
    "day": ["day", "days"],
    "week": ["week", "weeks"],
    "month": ["month", "months"],
    "year": ["year", "years", "yr", "yrs"],
}
UNIT_OF = {form: unit for unit, forms in UNIT_FORMS.items() for form in forms}
DURATION_DAYS = {"minute": 1 / 1440, "hour": 1 / 24, "day": 1, "week": 7, "month": 30, "year": 365}
_unit_alt = "|".join(sorted((re.escape(f) for f in UNIT_OF), key=len, reverse=True))
NUM_UNIT = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(" + _unit_alt + r")(?![a-z])")
NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])")
ARTICLE_DURATION = re.compile(r"(?<![a-z])(?:a|an|one)\s+(minute|hour|day|week|month|year)(?![a-z])")

# ---------------------------------------------------------------- frequency

FREQ_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(?<![a-z])(?:as|when) (?:needed|required)(?![a-z])|(?<![a-z])prn(?![a-z])"), "prn"),
    (re.compile(r"(?<![a-z])(?:once|1 times?) (?:a|per|each|every) day(?![a-z])|(?<![a-z])once daily|(?<![a-z])od(?![a-z])"), "1/day"),
    (re.compile(r"(?<![a-z])(?:twice|2 times) (?:a|per|each|every) day(?![a-z])|(?<![a-z])(?:twice|2 times) daily|(?<![a-z])bd(?![a-z])|(?<![a-z])bid(?![a-z])"), "2/day"),
    (re.compile(r"(?<![a-z])(?:thrice|3 times) (?:a|per|each|every) day(?![a-z])|(?<![a-z])(?:thrice|3 times) daily|(?<![a-z])tds(?![a-z])|(?<![a-z])tid(?![a-z])"), "3/day"),
    (re.compile(r"(?<![a-z])4 times (?:a|per|each|every) day(?![a-z])|(?<![a-z])4 times daily|(?<![a-z])qds(?![a-z])|(?<![a-z])qid(?![a-z])"), "4/day"),
    (re.compile(r"(?<![\w.])(\d+) times (?:a|per|each|every) day(?![a-z])|(?<![\w.])(\d+) times daily"), "{n}/day"),
    (re.compile(r"(?<![\w.])(\d+) times (?:a|per|each|every) week(?![a-z])|(?<![\w.])(\d+) times weekly"), "{n}/week"),
    (re.compile(r"(?<![a-z])(?:once|1 times?) (?:a|per|each|every) week(?![a-z])|(?<![a-z])weekly(?![a-z])"), "1/week"),
    (re.compile(r"(?<![a-z])every (\d+) hours?(?![a-z])|(?<![a-z])(\d+) hourly(?![a-z])"), "every {n} h"),
    (re.compile(r"(?<![a-z])(?:every|each) (?:night|evening)(?![a-z])|(?<![a-z])at night(?![a-z])|(?<![a-z])nightly(?![a-z])"), "nightly"),
    (re.compile(r"(?<![a-z])(?:every|each) morning(?![a-z])|(?<![a-z])in the morning(?![a-z])"), "morning"),
    (re.compile(r"(?<![a-z])daily(?![a-z])|(?<![a-z])(?:every|each|a|per) day(?![a-z])"), "daily"),
]

# ---------------------------------------------------------------- negation terms

EXTRA_TERMS = {
    "blood": ["blood", "bleeding"], "smoking": ["smoke", "smokes", "smoking", "smoker"],
    "alcohol": ["alcohol", "drink", "drinks", "drinking"], "chest pain": ["chest pain"],
    "weight loss": ["weight loss", "lost weight"], "allergies": ["allergies", "allergic"],
    "dizziness": ["dizzy", "dizziness"], "palpitations": ["palpitations"], "itching": ["itching", "itchy"],
}
POLARITY_TERMS: Dict[str, List[str]] = {**CONDITIONS, **EXTRA_TERMS}
POLARITY_TERMS.pop("pain", None)        # too generic: "no pain now" vs "pain at onset" are both common
POLARITY_TERMS.pop("allergy", None)     # covered by "allergies"


def normalise(text: str) -> str:
    t = text.lower().replace("’", "'")
    t = re.sub(r"(\d),(\d{3})", r"\1\2", t)         # 1,000 -> 1000
    t = words_to_digits(t)
    t = re.sub(r"(\d+)\s*(?:-|to|or)\s*(\d+)", r"\1 to \2", t)  # 2-3 / 2 or 3 -> "2 to 3"
    return t


def _numbers(t: str) -> Tuple[Dict[float, Set[str]], Set[float], Set[float]]:
    """{value: units attached}, set of all values, set of durations in days."""
    attached: Dict[float, Set[str]] = {}
    durations: Set[float] = set()
    for m in NUM_UNIT.finditer(t):
        v, unit = float(m.group(1)), UNIT_OF[m.group(2)]
        attached.setdefault(v, set()).add(unit)
        if unit in DURATION_DAYS:
            durations.add(round(v * DURATION_DAYS[unit], 4))
    # "2 to 3 days": the first number of a range takes the unit of the second
    for m in re.finditer(r"(\d+(?:\.\d+)?) to (\d+(?:\.\d+)?)\s*(" + _unit_alt + r")(?![a-z])", t):
        v, unit = float(m.group(1)), UNIT_OF[m.group(3)]
        attached.setdefault(v, set()).add(unit)
        if unit in DURATION_DAYS:
            durations.add(round(v * DURATION_DAYS[unit], 4))
    for m in ARTICLE_DURATION.finditer(t):
        durations.add(round(DURATION_DAYS[m.group(1)], 4))
    values = {float(x) for x in NUM.findall(t)}
    return attached, values, durations


def _frequencies(t: str) -> Tuple[Set[str], str]:
    """Canonical frequencies, and the text with the frequency phrases blanked out
    (so their numbers are not checked again as doses)."""
    found: Set[str] = set()
    for pat, label in FREQ_PATTERNS:
        def sub(m):
            n = next((g for g in m.groups() if g), None) if m.groups() else None
            found.add(label.format(n=int(float(n))) if n is not None and "{n}" in label else label)
            return " " * len(m.group(0))
        t = pat.sub(sub, t)
    return found, t


def _drugs(t: str) -> Set[str]:
    return {entry["name"] for name, entry in DRUGS.items()
            if re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", t)}


def _clauses(text: str) -> List[Tuple[str, bool]]:
    """Split into clauses, flagging those that are questions."""
    parts = re.split(r"(?<=[.?!])\s+|\n+", text)
    return [(p, p.rstrip().endswith("?")) for p in parts if p.strip()]


def _polarities(text: str, skip_questions: bool) -> Dict[str, Set[bool]]:
    """{canonical term: {True if affirmed, False if negated}} over non-question clauses."""
    out: Dict[str, Set[bool]] = {}
    for clause, is_q in _clauses(text.lower()):
        if skip_questions and is_q:
            continue
        for canon, forms in POLARITY_TERMS.items():
            for form in forms:
                for m in re.finditer(r"(?<![a-z])" + re.escape(form) + r"(?![a-z])", clause):
                    out.setdefault(canon, set()).add(not _denied(clause, m.start()))
    return out


def entity_mismatches(fact: str, evidence: str) -> List[Dict[str, str]]:
    """Entities stated in the fact that the evidence does not support. Empty list = consistent."""
    f, e = normalise(fact), normalise(evidence)
    problems: List[Dict[str, str]] = []

    f_freq, f_rest = _frequencies(f)
    e_freq, e_rest = _frequencies(e)
    for fr in sorted(f_freq - e_freq):
        # bare "daily" / "every day" only says "some number of times per day"
        if fr == "daily" and any(x.endswith("/day") for x in e_freq):
            continue
        if fr == "1/day" and "daily" in e_freq:
            continue
        problems.append({"kind": "frequency", "detail": f"frequency '{fr}' is not in the evidence"
                         + (f" (evidence: {', '.join(sorted(e_freq))})" if e_freq else "")})

    f_att, f_vals, f_dur = _numbers(f_rest)
    e_att, e_vals, e_dur = _numbers(e_rest)
    e_all_vals = e_vals | {float(re.sub(r'\D', '', x)) for x in re.findall(r"\d+/(?:day|week)|every \d+ h", " ".join(e_freq))}
    for v in sorted(f_vals):
        units = f_att.get(v, set())
        dur_units = {u for u in units if u in DURATION_DAYS}
        if dur_units:
            days = {round(v * DURATION_DAYS[u], 4) for u in dur_units}
            if days & e_dur:
                continue
            if v in e_vals and not (e_att.get(v, set()) & set(DURATION_DAYS)):
                continue  # evidence states the number without a unit: unit not contradicted
            problems.append({"kind": "duration", "detail": f"'{_fmt(v)} {'/'.join(sorted(dur_units))}' is not in the "
                             "evidence" + (f" (evidence durations: {', '.join(_days_txt(d) for d in sorted(e_dur))})" if e_dur else "")})
            continue
        if v not in e_all_vals:
            problems.append({"kind": "number", "detail": f"'{_fmt(v)}{(' ' + '/'.join(sorted(units))) if units else ''}' "
                             "is not in the evidence" + (f" (evidence numbers: {', '.join(_fmt(x) for x in sorted(e_vals))})" if e_vals else "")})
            continue
        e_units = e_att.get(v, set())
        if units and e_units and not (units & e_units):
            problems.append({"kind": "unit", "detail": f"'{_fmt(v)} {'/'.join(sorted(units))}' but the evidence says "
                             f"'{_fmt(v)} {'/'.join(sorted(e_units))}'"})

    for d in sorted(_drugs(f) - _drugs(e)):
        problems.append({"kind": "drug", "detail": f"drug '{d}' is not named in the evidence"
                         + (f" (evidence names: {', '.join(sorted(_drugs(e)))})" if _drugs(e) else "")})

    f_pol = _polarities(fact, skip_questions=False)
    e_pol = _polarities(evidence, skip_questions=True)
    for term, pols in f_pol.items():
        if len(pols) != 1 or term not in e_pol:
            continue
        fp = next(iter(pols))
        if fp not in e_pol[term]:
            problems.append({"kind": "negation", "detail": f"the fact {'affirms' if fp else 'denies'} '{term}' but the "
                             f"evidence only {'denies' if fp else 'affirms'} it"})
    return problems


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else str(v)


def _days_txt(d: float) -> str:
    return f"{_fmt(round(d, 2))} d"


def describe(problems: List[Dict[str, str]]) -> Optional[str]:
    if not problems:
        return None
    return "; ".join(f"{p['kind']}: {p['detail']}" for p in problems)
