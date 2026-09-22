"""
Optional audio-to-transcript embodiment using faster-whisper, run locally
so raw patient audio never has to leave the device (supports the
on-premise/privacy-preserving embodiment described in the patent doc).

Not required to run the demo: `main.py run --transcript ...` uses a
pre-built transcript JSON and skips this module entirely. This file is
provided so the "detailed description" of the audio-input embodiment is
backed by real, runnable code, not just prose.
"""
from __future__ import annotations

import math
from typing import List, Dict, Any

from .medical_terms import build_initial_prompt, normalize_medical_terms


def transcribe_audio(audio_path: str, model_size: str = "base",
                      medical_prompt: bool = True, normalize: bool = True) -> List[Dict[str, Any]]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "faster-whisper is not installed. Install it with "
            "`pip install faster-whisper` to transcribe raw audio, or use "
            "`--transcript` with a pre-built transcript JSON instead."
        ) from e

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    prompt = build_initial_prompt() if medical_prompt else None
    raw_segments, _info = model.transcribe(audio_path, word_timestamps=False, initial_prompt=prompt)

    segments: List[Dict[str, Any]] = []
    for i, seg in enumerate(raw_segments, start=1):
        acoustic_confidence = 1.0 / (1.0 + math.exp(-seg.avg_logprob))  # logprob -> (0,1)
        text = seg.text.strip()
        if normalize:
            text = normalize_medical_terms(text)
        segments.append({
            "id": i,
            "start": seg.start,
            "end": seg.end,
            "speaker": "UNKNOWN",  # speaker-role diarization is a separate embodiment (see patent doc)
            "text": text,
            "acoustic_confidence": round(acoustic_confidence, 3),
        })
    return segments
