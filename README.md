# Confidence-Gated Clinical Documentation

AI scribes record a doctor–patient consultation, transcribe it and let a language model draft the clinical note. Misheard words, invented details and clinically unsafe instructions reach that draft, and current products only *show* the clinician where each sentence came from.

This project **enforces** the evidence instead. Every drafted fact must cite transcript segments and quote them verbatim, and it is written into the note only if it passes these checks:

| Gate | Question | Signal |
|---|---|---|
| 0 | Does each quote really occur in the segment it cites? | Fuzzy alignment ≥ 90/100 (RapidFuzz) |
| 1 | Was the speech recogniser confident about exactly those words? | Mean Whisper word probability over the quoted span ≥ 0.50; weakest quoted content word ≥ 0.35 (else review) |
| 2 | Does the evidence entail the fact, and not contradict it? | Local DeBERTa-v3 NLI: P(contradiction) < 0.50, P(entailment) ≥ 0.30 |
| — | Is the evidence strong enough for this clinician and field? | S = 0.6·E + 0.4·A ≥ adaptive per-clinician, per-field threshold (starts at 0.75) |
| 3 | Is it clinically plausible with the rest of the encounter? | Allergy class, antibiotic-for-viral, indication, contraindication, interaction (negation-aware) |

Facts that fail are **withheld from the note** and queued for the clinician with the reason, the highlighted evidence and a button that replays exactly that audio span. Each approve/reject adjusts that clinician's threshold for the field. Every automatic and human decision is appended to an append-only audit log.

Text-only input has no audio, so the acoustic signal is reported as *unavailable*; it is never filled in with a made-up value.

## Repository layout

```
prototype/
  src/            pipeline: transcribe, medical_terms, speakers, extractor, llm,
                  grounding (Gates 0-2), entailment (NLI), clinical_plausibility (Gate 3),
                  calibration, audit, pipeline
  api/server.py   FastAPI backend: auth, patients, background pipeline jobs, audio streaming
  web/            browser UI: upload audio, live pipeline progress, note review, audio replay
  main.py         command-line interface
  eval/           PriMock57 evaluation: WER, confidence-vs-error analysis, gate outcomes, noise stress test
  tests/          demo_scenarios.py: regression scenarios on real ASR output
  sample_data/    PriMock57 transcripts (library), real Whisper output fixture, synthetic gate demo
  scripts/        download_primock57_audio.py
patent/           invention disclosure (.docx), figures, Review 1/2 presentation, their build scripts
```

## Setup

```bash
cd prototype
pip install -r requirements.txt
```

Optional, in `prototype/.env` (git-ignored; see `.env.example`):

```
GEMINI_API_KEY=...          # or ANTHROPIC_API_KEY=... — enables the LLM extractor
HF_HOME=E:/huggingface      # where the Whisper and NLI models are cached
WHISPER_MODEL=base.en       # small.en / medium.en are more accurate but need more RAM
PRIMOCK_AUDIO_DIR=E:/primock57_audio
```

The Whisper (`base.en`) and NLI (`DeBERTa-v3-base-mnli-fever-anli`) models download on first use and run locally on CPU. Tested on an 8-core laptop with 7.8 GB RAM and no GPU.

## Run

**Web app** (backend and frontend in one process):

```bash
cd prototype/api
python server.py          # http://127.0.0.1:8420
```

Sign up, add a patient, then **New case → Audio recording** and upload the doctor and patient recordings (e.g. from `scripts/download_primock57_audio.py day1_consultation01`). Tick *Draft with AI extractor* to use the LLM.

**Command line:**

```bash
python main.py run --doctor-audio doctor.wav --patient-audio patient.wav [--llm]
python main.py run --audio mixed.wav --llm          # single microphone; speaker roles from the LLM
python main.py run --transcript sample_data/primock57_library/day1_consultation01.json
python main.py resolve --case case_X.json --fact-id F004 --decision reject --reviewer "Dr. Patel"
```

**Regression scenarios** (real Whisper output, real NLI model):

```bash
python tests/demo_scenarios.py
```

**Evaluation on PriMock57** (resumable; downloads audio as needed):

```bash
python eval/run_eval.py --all            # WER, confidence-vs-error, gate outcomes -> eval_results/summary.md
python eval/noise_stress.py              # same consultation at clean / 20 / 10 / 5 / 0 dB SNR
```

## Data

[PriMock57](https://github.com/babylonhealth/primock57) (Babylon Health, CC BY 4.0; Papadopoulos Korfiatis et al., ACL 2022): 57 mock primary-care consultations with real clinicians, separate doctor/patient audio, human transcripts. No model is trained in this project; all models are used as released.

## Results (PriMock57 day1_consultation01, real audio)

Only this consultation's audio could be used so far: downloads of the rest from the dataset's Git LFS storage failed during this work. `eval/run_eval.py --all` is ready and resumable for when they succeed.

**Speech recognition** (faster-whisper `base.en`, CPU): 16.2 % WER against the human transcript.

**Does Whisper's confidence point at its own mistakes?** Yes. Correctly recognised words average probability 0.88, wrong words 0.61; AUROC 0.81 (0.5 = chance). Among content words, 38 % of those below 0.35 are errors versus 10.8 % overall, which is why a weak quoted word sends a fact to review (not to rejection).

**Vocabulary biasing A/B** (`eval/vocab_ab.py`):

| Mode | WER | Medical terms correct |
|---|---|---|
| none (default) | 16.2 % | 26 / 32 |
| initial_prompt | 19.4 % | 26 / 32 |
| hotwords | 27.9 % | 30 / 32 (but 134 inserted words) |

**Noise stress test** (`eval/noise_stress.py`, rule-based extractor):

| Speech SNR | WER | AUROC | Facts auto-verified |
|---|---|---|---|
| clean | 16.2 % | 0.81 | 12 / 13 |
| 20 dB | 27.9 % | 0.80 | 8 / 11 |
| 10 dB | 40.6 % | 0.78 | 5 / 9 |
| 5 dB | 58.0 % | 0.77 | 4 / 8 |
| 0 dB | 70.6 % | 0.72 | 2 / 5 |

The gate withholds proportionally more as recognition degrades. (The rule-based extractor's facts are verbatim, so this exercises the acoustic signal, not entailment.)

**Gate scenarios** (`tests/demo_scenarios.py`, 9/9 pass): a paraphrase of clear speech is verified; a wrong duration and an unsupported claim are rejected by NLI contradiction; an invented quote is rejected by the citation check; "no blood in the stool", built on the misheard "loose stalk" (0.28), is held for review although it scored entailment 0.89 and combined 0.83; the "time off work" → "type of work" error is held for review; a clinician rejection tightens the threshold 0.75 → 0.79; an amoxicillin prescription for a penicillin-allergic patient with a viral diagnosis is held by Gate 3.

Full tables: `prototype/eval_results/`. Invention disclosure and review deck: `patent/`.

## Limitations

- Gate thresholds and weights are set by design; tuning them needs facts labelled correct/incorrect, which have not been produced yet.
- Clinical-plausibility tables are a small curated set; a production system would use RxNorm / SNOMED-CT / openFDA.
- Speaker roles for a single mixed recording come from the LLM (content), not from acoustic diarization.
- Background pipeline jobs are held in memory; restarting the server loses runs in progress.
