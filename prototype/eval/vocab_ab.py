#!/usr/bin/env python3
"""
A/B test of how the medical vocabulary is given to Whisper:
  none            no biasing
  initial_prompt  vocabulary as Whisper's initial prompt (conditions the first 30 s window only,
                  because condition_on_previous_text is off)
  hotwords        vocabulary as faster-whisper hotwords (prepended to every window)

For each consultation and mode: word error rate, deletions/insertions, number of
utterance segments, and medical-term recall (of the vocabulary words spoken in the
human transcript, how many the recogniser got right at the aligned position).

  python eval/vocab_ab.py day1_consultation01 day1_consultation02 day2_consultation01
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.env import load_env  # noqa: E402
load_env()

from rapidfuzz.distance import Levenshtein  # noqa: E402

from eval.run_eval import LIBRARY, ensure_audio  # noqa: E402
from eval.wer import norm_tokens  # noqa: E402
from src.medical_terms import MEDICAL_VOCABULARY  # noqa: E402

VOCAB = {t for term in MEDICAL_VOCABULARY for t in norm_tokens(term)}


def score(name, segments):
    ref = json.loads((LIBRARY / f"{name}.json").read_text(encoding="utf-8"))["segments"]
    ops, med_total, med_hit = Counter(), 0, 0
    n_ref = dist = 0
    for spk in ("DOCTOR", "PATIENT"):
        r = [t for s in ref if s["speaker"] == spk for t in norm_tokens(s["text"])]
        h = [t for s in segments if s["speaker"] == spk for t in norm_tokens(s["text"])]
        n_ref += len(r)
        dist += Levenshtein.distance(r, h)
        med_total += sum(t in VOCAB for t in r)
        for o in Levenshtein.opcodes(r, h):
            if o.tag == "equal":
                med_hit += sum(t in VOCAB for t in r[o.src_start:o.src_end])
            else:
                ops[o.tag] += max(o.src_end - o.src_start, o.dest_end - o.dest_start) if o.tag == "replace" \
                    else (o.src_end - o.src_start if o.tag == "delete" else o.dest_end - o.dest_start)
    return {"wer": round(dist / n_ref, 4), "word_errors": dist, "ref_words": n_ref, "substitutions": ops["replace"],
            "deletions": ops["delete"], "insertions": ops["insert"], "segments": len(segments),
            "medical_terms": med_total, "medical_terms_correct": med_hit}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="+")
    ap.add_argument("--modes", nargs="*", default=["none", "initial_prompt", "hotwords"])
    ap.add_argument("--audio-dir", default=os.environ.get("PRIMOCK_AUDIO_DIR", str(ROOT / "sample_data" / "primock57_audio")))
    ap.add_argument("--out", default=str(ROOT / "eval_results" / "vocab_ab"))
    a = ap.parse_args()
    from src.transcribe import transcribe_consultation, whisper_model_name

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res_file = out / "results.jsonl"
    done = {(r["name"], r["mode"]) for r in map(json.loads, res_file.read_text(encoding="utf-8").splitlines())} \
        if res_file.exists() else set()
    for name in a.names:
        paths = ensure_audio(name, Path(a.audio_dir))
        for mode in a.modes:
            if (name, mode) in done:
                continue
            os.environ["ASR_VOCAB_MODE"] = mode
            t = time.time()
            segments, _ = transcribe_consultation(
                [(str(paths["doctor"]), "DOCTOR", "doctor"), (str(paths["patient"]), "PATIENT", "patient")])
            row = {"name": name, "mode": mode, "asr_model": whisper_model_name(), **score(name, segments),
                   "seconds": round(time.time() - t, 1)}
            with open(res_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            print(json.dumps(row), flush=True)

    rows = [json.loads(l) for l in res_file.read_text(encoding="utf-8").splitlines()]
    md = ["# Vocabulary biasing A/B (faster-whisper " + rows[0]["asr_model"] + ")", "",
          "| Consultation | Mode | WER | Subs | Del | Ins | Segments | Medical terms correct |",
          "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["name"], a.modes.index(r["mode"]) if r["mode"] in a.modes else 9)):
        md.append(f"| {r['name']} | {r['mode']} | {100 * r['wer']:.1f} % | {r['substitutions']} | {r['deletions']} | "
                  f"{r['insertions']} | {r['segments']} | {r['medical_terms_correct']} / {r['medical_terms']} |")
    md += ["", "| Mode (pooled) | WER | Deletions | Medical terms correct |", "|---|---|---|---|"]
    for mode in a.modes:
        rs = [r for r in rows if r["mode"] == mode]
        if not rs:
            continue
        err = sum(r["word_errors"] for r in rs)
        n = sum(r["ref_words"] for r in rs)
        mt, mh = sum(r["medical_terms"] for r in rs), sum(r["medical_terms_correct"] for r in rs)
        md.append(f"| {mode} | {100 * err / n:.1f} % | {sum(r['deletions'] for r in rs)} | {mh} / {mt} "
                  f"({100 * mh / mt:.0f} %) |" if mt else f"| {mode} | {100 * err / n:.1f} % | - | - |")
    (out / "summary.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
