"""
Turns whatever a clinician actually has (a JSON file in our schema, or
plain pasted/uploaded dialogue text) into the segment list the pipeline
expects. Real clinicians will not have our exact JSON schema lying
around, so the plain-text path matters as much as the JSON path.
"""
from __future__ import annotations

import json
import re
from typing import List, Dict, Any

SPEAKER_PREFIXES = {
    "doctor": "DOCTOR", "dr": "DOCTOR", "physician": "DOCTOR", "clinician": "DOCTOR", "gp": "DOCTOR",
    "patient": "PATIENT", "pt": "PATIENT",
}

LINE_RE = re.compile(r"^\s*([A-Za-z]+)\s*:\s*(.+)$")


def parse_plain_text(text: str) -> List[Dict[str, Any]]:
    segments = []
    current_speaker = "PATIENT"
    idx = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = LINE_RE.match(line)
        if match and match.group(1).lower() in SPEAKER_PREFIXES:
            current_speaker = SPEAKER_PREFIXES[match.group(1).lower()]
            content = match.group(2).strip()
        else:
            content = line
        if not content:
            continue
        idx += 1
        segments.append({
            "id": idx,
            "start": float(idx - 1),
            "end": float(idx),
            "speaker": current_speaker,
            "text": content,
        })
    if not segments:
        raise ValueError("No utterances found. Use lines like 'Doctor: ...' / 'Patient: ...'.")
    return segments


def parse_json_transcript(raw: str) -> List[Dict[str, Any]]:
    data = json.loads(raw)
    segments = data.get("segments") if isinstance(data, dict) else data
    if not isinstance(segments, list) or not segments:
        raise ValueError("JSON transcript must contain a non-empty 'segments' list.")
    normalized = []
    for i, seg in enumerate(segments, start=1):
        if "text" not in seg or "speaker" not in seg:
            raise ValueError(f"Segment {i} is missing 'speaker' or 'text'.")
        normalized.append({
            "id": seg.get("id", i),
            "start": float(seg.get("start", i - 1)),
            "end": float(seg.get("end", i)),
            "speaker": str(seg["speaker"]).upper(),
            "text": str(seg["text"]),
        })
    return normalized


def parse_upload(filename: str, raw_bytes: bytes) -> List[Dict[str, Any]]:
    text = raw_bytes.decode("utf-8", errors="replace")
    if filename.lower().endswith(".json"):
        return parse_json_transcript(text)
    return parse_plain_text(text)
