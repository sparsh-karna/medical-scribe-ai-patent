#!/usr/bin/env python3
"""
CLI demo for the dual-signal confidence-gated clinical documentation
pipeline.

  Draft a note from a transcript, with low-confidence facts blocked:
    python main.py run --transcript sample_data/sample_visit_transcript.json

  Draft a note from audio (separate doctor/patient channels, as in PriMock57):
    python main.py run --doctor-audio doctor.wav --patient-audio patient.wav

  ...or from a single mixed recording (speaker roles attributed by the LLM):
    python main.py run --audio visit.wav

  Resolve a fact that got blocked pending clinician review:
    python main.py resolve --case case_SYNTH-0001.json --fact-id F004 \\
        --decision approve --reviewer "Dr. Patel"
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from src.env import load_env
from src.llm import LLMError
from src.pipeline import run_pipeline, resolve_fact, render_note, save_case, load_case


def cmd_run(args: argparse.Namespace) -> None:
    try:
        if args.transcript:
            with open(args.transcript, "r", encoding="utf-8") as f:
                data = json.load(f)
            segments = data["segments"]
            visit_id = data.get("visit_id", "CASE")
            input_meta = {"input_mode": "text", "file": args.transcript}
        elif args.audio or args.doctor_audio:
            segments, input_meta, visit_id = _transcribe(args)
        else:
            print("Provide --transcript, --audio, or --doctor-audio/--patient-audio.", file=sys.stderr)
            sys.exit(1)

        case = run_pipeline(segments, use_llm=args.llm, audit_path=args.audit,
                            calibration_path=args.calibration, input_meta=input_meta,
                            progress=lambda stage: print(f"[{stage}]", file=sys.stderr))
    except LLMError as e:
        print(f"LLM stage failed: {e}", file=sys.stderr)
        sys.exit(1)
    case["visit_id"] = visit_id

    case_path = args.case or f"case_{visit_id}.json"
    save_case(case, case_path)

    print(render_note(case))
    print(f"\n(case saved to {case_path}; audit trail at {args.audit}; "
          f"calibration state at {args.calibration})")


def _transcribe(args: argparse.Namespace):
    from src.transcribe import UNATTRIBUTED, transcribe_consultation

    def progress(f):
        print(f"\r[transcribing] {f * 100:5.1f}%", end="", file=sys.stderr, flush=True)

    if args.doctor_audio:
        if not args.patient_audio:
            print("--doctor-audio needs --patient-audio too.", file=sys.stderr)
            sys.exit(1)
        channels = [(args.doctor_audio, "DOCTOR", "doctor"), (args.patient_audio, "PATIENT", "patient")]
    else:
        channels = [(args.audio, UNATTRIBUTED, "mixed")]
    segments, asr_meta = transcribe_consultation(channels, progress)
    print(file=sys.stderr)
    if not args.doctor_audio:
        from src.speakers import attribute_speakers
        print("[attributing speakers]", file=sys.stderr)
        segments = attribute_speakers(segments)
    visit_id = os.path.splitext(os.path.basename(args.doctor_audio or args.audio))[0]
    return segments, {"input_mode": "audio", **asr_meta}, visit_id


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
    p_run.add_argument("--audio", help="Single mixed recording (speaker roles attributed by the LLM)")
    p_run.add_argument("--doctor-audio", help="Doctor-channel recording (use with --patient-audio)")
    p_run.add_argument("--patient-audio", help="Patient-channel recording (use with --doctor-audio)")
    p_run.add_argument("--llm", action="store_true", help="Use the LLM extractor (Gemini or Claude, per prototype/.env) instead of rule-based")
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
    load_env()
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
