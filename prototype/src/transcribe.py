"""
Audio -> transcript stage, using faster-whisper locally so raw patient
audio never has to leave the device.

The ASR model is used as-is (not fine-tuned). Around it sits a light
domain-adaptation layer (src/medical_terms.py): decoding is biased toward
medical vocabulary via faster-whisper hotwords (every window), and low-confidence words
that are near-misses of known medical terms are corrected (the original
ASR word is kept alongside for the audit trail).

Every transcript segment carries its per-word ASR probabilities and
character offsets, which is what the grounding gate's acoustic signal is
computed from.

Speaker roles:
  - separate doctor / patient recordings (one speaker per channel, as in
    PriMock57): each channel is transcribed on its own and labelled with
    its role, then the two are merged in time order;
  - a single mixed recording: segments are transcribed unlabelled and
    roles are attributed afterwards (src/speakers.py).

Model size: WHISPER_MODEL (default "base.en").
"""
from __future__ import annotations

import os
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from .medical_terms import build_vocabulary_prompt, correct_word

PAUSE_SPLIT_SECONDS = 0.8   # a silence this long inside a Whisper segment starts a new utterance
UNATTRIBUTED = "UNATTRIBUTED"

ProgressFn = Optional[Callable[[float], None]]

_model_lock = threading.Lock()
_models: Dict[str, Any] = {}


def whisper_model_name() -> str:
    return os.environ.get("WHISPER_MODEL", "base.en")


VOCAB_MODES = ("initial_prompt", "hotwords", "none")


def vocabulary_mode() -> str:
    """How the medical vocabulary biases decoding (ASR_VOCAB_MODE).

    Default "none": in eval/vocab_ab.py on PriMock57 day1_consultation01 (base.en),
    no biasing gave 16.2 % WER, initial_prompt 19.4 % (same medical-term recall,
    26/32) and hotwords 27.9 % (30/32 medical terms but 134 inserted words). Prompt
    biasing therefore stays an option, not the default, until more audio is tested."""
    mode = os.environ.get("ASR_VOCAB_MODE", "none").strip().lower()
    return mode if mode in VOCAB_MODES else "none"


def _get_model():
    name = whisper_model_name()
    with _model_lock:
        if name not in _models:
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise RuntimeError("faster-whisper is not installed (pip install faster-whisper).") from e
            _models.clear()  # keep at most one ASR model in memory
            _models[name] = WhisperModel(name, device="cpu", compute_type="int8")
    return _models[name]


def _utterance(words: List[Any], speaker: str, source: str) -> Dict[str, Any]:
    text, out = "", []
    for w in words:
        fixed = correct_word(w.word, w.probability)
        start = len(text) + (len(fixed) - len(fixed.lstrip()))
        text += fixed
        entry = {"text": fixed.strip(), "start": round(w.start, 2), "end": round(w.end, 2),
                 "prob": round(w.probability, 3), "char_start": start, "char_end": len(text)}
        if fixed != w.word:
            entry["asr_text"] = w.word.strip()
        out.append(entry)
    lead = len(text) - len(text.lstrip())
    for entry in out:
        entry["char_start"] -= lead
        entry["char_end"] -= lead
    return {
        "start": out[0]["start"], "end": out[-1]["end"], "speaker": speaker,
        "text": text.strip(), "words": out, "audio_source": source,
        "acoustic_confidence": round(sum(e["prob"] for e in out) / len(out), 3),
    }


def transcribe_channel(path: str, speaker: str, source: str, progress: ProgressFn = None
                       ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Transcribe one recording into utterance segments (not yet numbered)."""
    model = _get_model()
    english_only = whisper_model_name().endswith(".en")
    mode = vocabulary_mode()
    biasing = {}
    if mode == "hotwords":
        biasing["hotwords"] = build_vocabulary_prompt()        # prepended to every 30 s window
    elif mode == "initial_prompt":
        biasing["initial_prompt"] = build_vocabulary_prompt()  # conditions the first window only
    raw, info = model.transcribe(
        path,
        word_timestamps=True,
        vad_filter=True,                    # skip the silence while the other party speaks
        condition_on_previous_text=False,   # avoids Whisper's repetition loops on long audio
        language="en" if english_only else None,
        **biasing,
    )
    segments: List[Dict[str, Any]] = []
    for seg in raw:
        words = [w for w in (seg.words or []) if w.word.strip()]
        group: List[Any] = []
        for w in words:
            if group and w.start - group[-1].end >= PAUSE_SPLIT_SECONDS:
                segments.append(_utterance(group, speaker, source))
                group = []
            group.append(w)
        if group:
            segments.append(_utterance(group, speaker, source))
        if progress and info.duration:
            progress(min(seg.end / info.duration, 1.0))
    meta = {"source": source, "duration": round(info.duration, 1), "language": info.language}
    return segments, meta


def transcribe_consultation(channels: List[Tuple[str, str, str]], progress: ProgressFn = None
                            ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    channels: [(path, speaker, source_label)] -- e.g.
      [("doc.wav", "DOCTOR", "doctor"), ("pat.wav", "PATIENT", "patient")]  separate channels
      [("visit.wav", UNATTRIBUTED, "mixed")]                                 one mixed recording
    Returns time-ordered segments numbered from 1, plus ASR metadata.
    """
    all_segments: List[Dict[str, Any]] = []
    channel_meta = []
    n = len(channels)
    for i, (path, speaker, source) in enumerate(channels):
        def channel_progress(f, i=i):
            if progress:
                progress((i + f) / n)
        segs, meta = transcribe_channel(path, speaker, source, channel_progress)
        all_segments.extend(segs)
        channel_meta.append(meta)
    all_segments.sort(key=lambda s: (s["start"], s["end"]))
    for i, seg in enumerate(all_segments, start=1):
        seg["id"] = i
    corrected = sum(1 for s in all_segments for w in s["words"] if "asr_text" in w)
    meta = {
        "asr_model": f"faster-whisper {whisper_model_name()}",
        "channels": channel_meta,
        "duration": max((m["duration"] for m in channel_meta), default=0.0),
        "segments": len(all_segments),
        "medical_term_corrections": corrected,
        "vocabulary_biasing": vocabulary_mode(),
    }
    return all_segments, meta
