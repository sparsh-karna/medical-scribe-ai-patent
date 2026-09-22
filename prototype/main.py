#!/usr/bin/env python3
"""
CLI demo for the dual-signal confidence-gated clinical documentation
pipeline.

  Draft a note from a transcript, with low-confidence facts blocked:
    python main.py run --transcript sample_data/sample_visit_transcript.json

  Draft a note from raw audio instead (requires faster-whisper installed):
    python main.py run --audio path/to/visit.wav

  Resolve a fact that got blocked pending clinician review:
    python main.py resolve --case case_SYNTH-0001.json --fact-id F004 \\
        --decision approve --reviewer "Dr. Patel"
"""
from __future__ import annotations

import argparse
import json
import sys

from src.pipeline import run_pipeline, resolve_fact, render_note, save_case, load_case


def cmd_run(args: argparse.Namespace) -> None:
    if args.transcript:
        with open(args.transcript, "r", encoding="utf-8") as f:
            data = json.load(f)
        segments = data["segments"]
        visit_id = data.get("visit_id", "CASE")
    elif args.audio:
        from src.transcribe import transcribe_audio
        segments = transcribe_audio(args.audio)
        visit_id = "AUDIO-CASE"
    else:
        print("Provide either --transcript or --audio.", file=sys.stderr)
        sys.exit(1)

    case = run_pipeline(segments, use_llm=args.llm, audit_path=args.audit,
                         calibration_path=args.calibration)
    case["visit_id"] = visit_id

    case_path = args.case or f"case_{visit_id}.json"
    save_case(case, case_path)

    print(render_note(case))
    print(f"\n(case saved to {case_path}; audit trail at {args.audit}; "
          f"calibration state at {args.calibration})")


def cmd_resolve(args: argparse.Namespace) -> None:
    case = load_case(args.case)
    case = resolve_fact(case, args.fact_id, args.decision, args.reviewer,
                         audit_path=args.audit, calibration_path=args.calibration)
    save_case(case, args.case)

    print(render_note(case))
    print(f"\n(resolution recorded in {args.audit}; case updated at {args.case})")


def cmd_audit(args: argparse.Namespace) -> None:
    from src.audit import AuditLog
    for entry in AuditLog(args.audit).read_all():
        print(json.dumps(entry))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Confidence-gated clinical documentation demo")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Draft a structured note from a transcript or audio file")
    p_run.add_argument("--transcript", help="Path to a transcript JSON (see sample_data/)")
    p_run.add_argument("--audio", help="Path to a raw audio file (requires faster-whisper)")
    p_run.add_argument("--llm", action="store_true", help="Use Claude-backed extractor instead of rule-based")
    p_run.add_argument("--case", help="Path to save the case file (default: case_<visit_id>.json)")
    p_run.add_argument("--audit", default="audit_log.jsonl", help="Path to the append-only audit log")
    p_run.add_argument("--calibration", default="calibration_state.json", help="Path to adaptive threshold state")
    p_run.set_defaults(func=cmd_run)

    p_resolve = sub.add_parser("resolve", help="Clinician resolves a blocked fact (approve/reject)")
    p_resolve.add_argument("--case", required=True, help="Path to the case file to update")
    p_resolve.add_argument("--fact-id", required=True, help="Fact id to resolve, e.g. F004")
    p_resolve.add_argument("--decision", required=True, choices=["approve", "reject"])
    p_resolve.add_argument("--reviewer", required=True, help="Reviewing clinician's name")
    p_resolve.add_argument("--audit", default="audit_log.jsonl")
    p_resolve.add_argument("--calibration", default="calibration_state.json")
    p_resolve.set_defaults(func=cmd_resolve)

    p_audit = sub.add_parser("audit", help="Print the append-only audit trail")
    p_audit.add_argument("--audit", default="audit_log.jsonl")
    p_audit.set_defaults(func=cmd_audit)

    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
