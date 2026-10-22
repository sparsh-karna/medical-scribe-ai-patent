"""
Speaker-role attribution for a single mixed recording.

When doctor and patient are captured on separate channels (as in
PriMock57) the role of every segment is known from its channel and this
module is not used. For one mixed recording the ASR output has no speaker
labels, so an LLM assigns each segment a role from the conversational
content (who asks history questions / examines / prescribes versus who
reports symptoms). The attribution source is recorded on every segment so
the note's provenance shows roles were inferred, not measured.

Limitation: a Whisper segment that spans a turn change gets a single role.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .llm import LLMError, format_transcript, generate_json, llm_provider

ROLES = ["DOCTOR", "PATIENT", "OTHER"]

SYSTEM_PROMPT = (
    "You label speakers in a transcript of a medical consultation recorded on a "
    "single microphone. Each line is `[id] UNATTRIBUTED: text`. For every id, decide "
    "whether the clinician (DOCTOR), the patient or their companion answering for "
    "them (PATIENT), or someone else (OTHER) spoke it, using the conversational "
    "content: the clinician asks history questions, explains, examines and "
    "prescribes; the patient describes symptoms and answers. Return one entry per "
    "id, in order."
)

SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "segment_id": {"type": "integer"},
            "speaker": {"type": "string", "enum": ROLES},
        },
        "required": ["segment_id", "speaker"],
    },
}


def attribute_speakers(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if llm_provider() is None:
        raise LLMError("A single mixed recording needs an LLM to attribute speaker roles. "
                       "Configure GEMINI_API_KEY / ANTHROPIC_API_KEY, or upload the doctor "
                       "and patient channels as separate files.")
    items = generate_json(SYSTEM_PROMPT, format_transcript(segments), SCHEMA)
    roles = {}
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and item.get("speaker") in ROLES:
            try:
                roles[int(item["segment_id"])] = item["speaker"]
            except (TypeError, ValueError, KeyError):
                continue
    unlabelled = [s["id"] for s in segments if s["id"] not in roles]
    if unlabelled:
        raise LLMError(f"Speaker attribution left {len(unlabelled)} segment(s) unlabelled "
                       f"(e.g. #{unlabelled[0]}); retry the run.")
    for s in segments:
        s["speaker"] = roles[s["id"]]
        s["speaker_source"] = "llm_attribution"
    return segments
