#!/usr/bin/env python3
"""
Acoustic stress test: add white Gaussian noise to a consultation's real audio
at decreasing signal-to-noise ratios and measure how speech recognition, ASR
word confidence and the gate's decisions respond.

The SNR is set against the power of the *speech* frames of each channel (the
loudest 30 % of 25 ms frames), not the whole file -- each PriMock57 channel is
mostly silence while the other speaker talks, which would otherwise make the
nominal SNR far milder than intended. Noise is seeded, so runs are repeatable.

  python eval/noise_stress.py                       # day1_consultation01, clean/20/10/5/0 dB
  python eval/noise_stress.py day2_consultation05 --snr 15 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.env import load_env  # noqa: E402
load_env()

from eval.run_eval import asr_scores, ensure_audio, gate, reason_kind  # noqa: E402,F401

SR = 16000


def speech_power(x: np.ndarray) -> float:
    frame = int(0.025 * SR)
    n = len(x) // frame
    p = (x[: n * frame].reshape(n, frame) ** 2).mean(axis=1)
    top = np.sort(p)[int(0.7 * n):]
    return float(top.mean())


def add_noise(x: np.ndarray, snr_db: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise_power = speech_power(x) / (10 ** (snr_db / 10))
    y = x + rng.normal(0.0, np.sqrt(noise_power), size=x.shape).astype(np.float32)
    return np.clip(y, -1.0, 1.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", nargs="?", default="day1_consultation01")
    ap.add_argument("--snr", nargs="*", type=float, default=[20, 10, 5, 0])
    ap.add_argument("--audio-dir", default=os.environ.get("PRIMOCK_AUDIO_DIR", str(ROOT / "sample_data" / "primock57_audio")))
    ap.add_argument("--out", default=str(ROOT / "eval_results" / "noise"))
    a = ap.parse_args()

    from faster_whisper import decode_audio
    from scipy.io import wavfile
    from src.transcribe import transcribe_consultation, whisper_model_name

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    clean = ensure_audio(a.name, Path(a.audio_dir))
    signals = {role: decode_audio(str(p), sampling_rate=SR) for role, p in clean.items()}

    rows = []
    for snr in [None] + a.snr:
        tag = "clean" if snr is None else f"snr{int(snr)}"
        paths = {}
        for k, (role, x) in enumerate(signals.items()):
            if snr is None:
                paths[role] = clean[role]
                continue
            y = add_noise(x, snr, seed=1000 + k)
            paths[role] = out / f"{a.name}_{role}_{tag}.wav"
            wavfile.write(paths[role], SR, (y * 32767).astype(np.int16))
        t = time.time()
        segments, meta = transcribe_consultation(
            [(str(paths["doctor"]), "DOCTOR", "doctor"), (str(paths["patient"]), "PATIENT", "patient")])
        meta = {"input_mode": "audio", **meta, "noise": tag}
        asr, _, _ = asr_scores(a.name, segments)
        g = gate(f"{a.name}_{tag}", segments, meta, False, out)
        case = json.loads((out / "runs" / f"{a.name}_{tag}_rule" / "case.json").read_text(encoding="utf-8"))
        ac = [f["acoustic_score"] for f in case["facts"] if f.get("acoustic_score") is not None]
        row = {"condition": tag, "snr_db": snr, "segments": len(segments), "wer": asr["wer"],
               "mean_prob_correct": asr["confidence"]["mean_prob_correct"],
               "mean_prob_error": asr["confidence"]["mean_prob_error"], "auroc": asr["confidence"]["auroc"],
               "facts": g["facts"], "status": g["status"], "reasons": g["reasons"],
               "mean_fact_acoustic": round(sum(ac) / len(ac), 3) if ac else None,
               "seconds": round(time.time() - t, 1)}
        rows.append(row)
        print(json.dumps(row), flush=True)

    (out / f"{a.name}_noise_results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    md = [f"# Noise stress test: {a.name} (faster-whisper {whisper_model_name()}, rule-based extractor)", "",
          "| Condition | WER | Mean word prob (correct / wrong) | AUROC | Facts | Verified | Needs review | Rejected | Mean fact acoustic |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        s = r["status"]
        md.append(f"| {r['condition']} | {100 * r['wer']:.1f} % | {r['mean_prob_correct']} / {r['mean_prob_error']} | "
                  f"{r['auroc']} | {r['facts']} | {s.get('VERIFIED', 0)} | {s.get('NEEDS_REVIEW', 0)} | "
                  f"{s.get('REJECTED', 0)} | {r['mean_fact_acoustic']} |")
    (out / f"{a.name}_noise_results.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
