#!/usr/bin/env python3
"""
Evaluate the pipeline on PriMock57 consultations, from real audio.

For each consultation:
  1. download the doctor + patient audio if missing (CC BY 4.0, Babylon Health)
  2. transcribe both channels with the project's ASR stage (cached)
  3. word error rate per channel against the human transcript
  4. does ASR word confidence point at recognition errors? (mean probability of
     correct vs wrong words, AUROC, precision/recall of the < 0.5 flag)
  5. run the full gate (extraction -> Gates 0-3) and count outcomes and reasons

Resumable: finished consultations are skipped on re-run. Results go to
<out>/results.jsonl (one line per consultation) and <out>/summary.{json,md}.

  python eval/run_eval.py --all --audio-dir E:/primock57_audio
  python eval/run_eval.py day1_consultation01 day2_consultation05 --llm
  python eval/run_eval.py --summary-only
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.env import load_env  # noqa: E402
load_env()

from eval.wer import confidence_vs_errors, hyp_tokens_with_prob, label_hypothesis_words, norm_tokens, wer  # noqa: E402

LIBRARY = ROOT / "sample_data" / "primock57_library"
AUDIO_URL = "https://github.com/babylonhealth/primock57/raw/main/audio/{name}_{role}.wav"


def all_names():
    return sorted(p.stem for p in LIBRARY.glob("day*_consultation*.json"))


def ensure_audio(name, audio_dir: Path):
    paths = {}
    for role in ("doctor", "patient"):
        dest = audio_dir / f"{name}_{role}.wav"
        if not dest.exists():
            audio_dir.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".part")
            with urllib.request.urlopen(AUDIO_URL.format(name=name, role=role)) as r, open(tmp, "wb") as f:
                f.write(r.read())
            tmp.replace(dest)
        paths[role] = dest
    return paths


def transcribe_cached(name, paths, out: Path):
    from src.transcribe import transcribe_consultation, whisper_model_name
    cache = out / "asr" / f"{name}_{whisper_model_name()}.json"
    if cache.exists():
        d = json.loads(cache.read_text(encoding="utf-8"))
        return d["segments"], d["input"], 0.0
    t = time.time()
    segments, meta = transcribe_consultation(
        [(str(paths["doctor"]), "DOCTOR", "doctor"), (str(paths["patient"]), "PATIENT", "patient")])
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"visit_id": name, "input": {"input_mode": "audio", **meta}, "segments": segments}),
                     encoding="utf-8")
    return segments, {"input_mode": "audio", **meta}, round(time.time() - t, 1)


def asr_scores(name, segments):
    ref = json.loads((LIBRARY / f"{name}.json").read_text(encoding="utf-8"))["segments"]
    res, all_p, all_e, E, N = {}, [], [], 0, 0
    for spk in ("DOCTOR", "PATIENT"):
        r = [t for s in ref if s["speaker"] == spk for t in norm_tokens(s["text"])]
        h, p = hyp_tokens_with_prob([s for s in segments if s["speaker"] == spk])
        e, n = wer(r, h)
        res[f"wer_{spk.lower()}"] = round(e / n, 4) if n else None
        E, N = E + e, N + n
        all_p += p
        all_e += label_hypothesis_words(r, h)
    res.update({"word_errors": E, "ref_words": N, "wer": round(E / N, 4) if N else None})
    res["confidence"] = confidence_vs_errors(all_p, all_e)
    return res, all_p, all_e


def reason_kind(f):
    r = f["reason"]
    if f.get("plausibility_flag"):
        return "plausibility"
    if f["status"] == "REJECTED":
        for key, kind in (("Quoted evidence", "quote_not_found"), ("No valid segment", "no_citation"),
                          ("No verbatim evidence", "no_quote"), ("contradicts", "contradiction"),
                          ("does not entail", "not_entailed"), ("Acoustic confidence", "acoustic_floor")):
            if key in r:
                return kind
        return "rejected_other"
    if f["status"] == "NEEDS_REVIEW":
        return "weakest_word" if "was recognised with probability" in r else "below_threshold"
    return "verified"


def gate(name, segments, meta, use_llm, out: Path):
    from src.pipeline import run_pipeline
    run_dir = out / "runs" / f"{name}_{'llm' if use_llm else 'rule'}"
    run_dir.mkdir(parents=True, exist_ok=True)
    for f in ("audit_log.jsonl", "calibration.json"):
        (run_dir / f).unlink(missing_ok=True)  # every consultation starts from the default thresholds
    t = time.time()
    case = run_pipeline(segments, use_llm=use_llm, audit_path=str(run_dir / "audit_log.jsonl"),
                        calibration_path=str(run_dir / "calibration.json"), input_meta=meta)
    (run_dir / "case.json").write_text(json.dumps(case), encoding="utf-8")
    counts, kinds = {}, {}
    for f in case["facts"]:
        counts[f["status"]] = counts.get(f["status"], 0) + 1
        k = reason_kind(f)
        kinds[k] = kinds.get(k, 0) + 1
    return {"extractor": case["extractor"], "facts": len(case["facts"]), "status": counts, "reasons": kinds,
            "gate_seconds": round(time.time() - t, 1)}


def done_keys(results: Path):
    if not results.exists():
        return set()
    return {(r["name"], r["gate"]["extractor"].split(":")[0]) for r in map(json.loads, results.read_text(encoding="utf-8").splitlines()) if r.get("gate")}


def summarise(out: Path):
    results = out / "results.jsonl"
    rows = [json.loads(l) for l in results.read_text(encoding="utf-8").splitlines()] if results.exists() else []
    if not rows:
        print("no results yet")
        return
    asr_rows = {r["name"]: r for r in rows}.values()
    # pooled word-level confidence analysis, recomputed from the ASR caches
    P, ERR = [], []
    for r in asr_rows:
        cache = next((out / "asr").glob(f"{r['name']}_*.json"))
        _, p, e = asr_scores(r["name"], json.loads(cache.read_text(encoding="utf-8"))["segments"])
        P += p
        ERR += e
    wers = [r["asr"]["wer"] for r in asr_rows]
    E = sum(r["asr"]["word_errors"] for r in asr_rows)
    N = sum(r["asr"]["ref_words"] for r in asr_rows)
    by_ext = {}
    for r in rows:
        ext = r["gate"]["extractor"]
        agg = by_ext.setdefault(ext, {"consultations": 0, "facts": 0, "status": {}, "reasons": {}})
        agg["consultations"] += 1
        agg["facts"] += r["gate"]["facts"]
        for k, v in r["gate"]["status"].items():
            agg["status"][k] = agg["status"].get(k, 0) + v
        for k, v in r["gate"]["reasons"].items():
            agg["reasons"][k] = agg["reasons"].get(k, 0) + v
    summary = {
        "consultations": len(list(asr_rows)),
        "asr_model": rows[0]["asr_model"],
        "wer_pooled": round(E / N, 4), "word_errors": E, "ref_words": N,
        "wer_per_consultation": {"mean": round(st.mean(wers), 4), "median": round(st.median(wers), 4),
                                 "min": round(min(wers), 4), "max": round(max(wers), 4)},
        "confidence_vs_errors_pooled": confidence_vs_errors(P, ERR),
        "gate": by_ext,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    c = summary["confidence_vs_errors_pooled"]
    md = [f"# PriMock57 evaluation ({summary['consultations']} consultations, {summary['asr_model']})", "",
          "## Speech recognition", "",
          f"- Pooled WER: **{100 * summary['wer_pooled']:.1f} %** ({E:,} errors / {N:,} reference words)",
          f"- Per consultation: mean {100 * summary['wer_per_consultation']['mean']:.1f} %, median "
          f"{100 * summary['wer_per_consultation']['median']:.1f} %, range {100 * summary['wer_per_consultation']['min']:.1f}"
          f"-{100 * summary['wer_per_consultation']['max']:.1f} %", "",
          "## Does ASR word confidence point at recognition errors?", "",
          f"- Recognised words: {c['words']:,}, of which errors (substituted/inserted): {c['error_words']:,}",
          f"- Mean probability: correct words **{c['mean_prob_correct']}**, wrong words **{c['mean_prob_error']}**",
          f"- AUROC (probability ranks wrong words below correct ones): **{c['auroc']}** (0.5 = chance)",
          f"- Flag 'probability < 0.5': precision {c['flag_precision_at_0.5']}, recall {c['flag_recall_at_0.5']}", "",
          "## Gate outcomes", ""]
    for ext, g in by_ext.items():
        md.append(f"### Extractor: {ext} ({g['consultations']} consultations, {g['facts']} facts)")
        md.append("")
        md += [f"- {k}: {v} ({100 * v / g['facts']:.1f} %)" for k, v in sorted(g["status"].items())]
        md.append("- Reasons: " + ", ".join(f"{k} {v}" for k, v in sorted(g["reasons"].items(), key=lambda x: -x[1])))
        md.append("")
    (out / "summary.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--audio-dir", default=os.environ.get("PRIMOCK_AUDIO_DIR", str(ROOT / "sample_data" / "primock57_audio")))
    ap.add_argument("--out", default=str(ROOT / "eval_results"))
    ap.add_argument("--llm", action="store_true", help="gate LLM-extracted facts instead of rule-based ones")
    ap.add_argument("--summary-only", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.summary_only:
        return summarise(out)

    from src.transcribe import whisper_model_name
    names = all_names() if a.all else a.names
    if not names:
        ap.error("name consultations or pass --all")
    results = out / "results.jsonl"
    done = done_keys(results)
    ext_key = "llm" if a.llm else "rule_based"
    for i, name in enumerate(names, 1):
        if (name, ext_key) in done:
            print(f"[{i}/{len(names)}] {name}: done, skipping", flush=True)
            continue
        try:
            t = time.time()
            paths = ensure_audio(name, Path(a.audio_dir))
            segments, meta, asr_s = transcribe_cached(name, paths, out)
            asr, _, _ = asr_scores(name, segments)
            g = gate(name, segments, meta, a.llm, out)
            row = {"name": name, "asr_model": f"faster-whisper {whisper_model_name()}", "duration_s": meta.get("duration"),
                   "segments": len(segments), "asr_seconds": asr_s, "asr": asr, "gate": g,
                   "total_seconds": round(time.time() - t, 1)}
            with open(results, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            print(f"[{i}/{len(names)}] {name}: WER {100 * asr['wer']:.1f} %, AUROC {asr['confidence']['auroc']}, "
                  f"facts {g['facts']} {g['status']}, {row['total_seconds']} s", flush=True)
        except Exception as e:  # keep going; the failed one is retried on the next run
            print(f"[{i}/{len(names)}] {name}: FAILED {type(e).__name__}: {e}", flush=True)
    summarise(out)


if __name__ == "__main__":
    main()
