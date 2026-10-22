"""
Semantic-grounding signal: natural-language-inference (NLI) entailment.

Given the text of the transcript segments a fact cites (the premise) and
the drafted clinical statement (the hypothesis), a pretrained NLI
cross-encoder returns P(entailment), P(neutral), P(contradiction). This is
what lets the gate distinguish:

  - a faithful paraphrase  ("No, I don't smoke" -> "Denies smoking")     entailment
  - an unsupported claim   (cited text never mentions asthma)            neutral
  - a contradicted claim   ("I have chest pain" -> "Denies chest pain")  contradiction

The model runs locally (no transcript text leaves the machine) and is
used as-is; nothing is fine-tuned. Override with NLI_MODEL.
"""
from __future__ import annotations

import os
import threading
from typing import Dict, List, Tuple

DEFAULT_NLI_MODEL = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"

_lock = threading.Lock()
_model = None
_tokenizer = None
_labels: Dict[int, str] = {}


def nli_model_name() -> str:
    return os.environ.get("NLI_MODEL", DEFAULT_NLI_MODEL)


def _load():
    global _model, _tokenizer, _labels
    with _lock:
        if _model is None:
            try:
                import torch  # noqa: F401
                from transformers import AutoModelForSequenceClassification, AutoTokenizer
            except ImportError as e:
                raise RuntimeError(
                    "Semantic grounding needs `torch` and `transformers` "
                    "(pip install torch transformers sentencepiece)."
                ) from e
            name = nli_model_name()
            _tokenizer = AutoTokenizer.from_pretrained(name)
            _model = AutoModelForSequenceClassification.from_pretrained(name).eval()
            _labels = {int(i): label.lower() for i, label in _model.config.id2label.items()}
            missing = {"entailment", "neutral", "contradiction"} - set(_labels.values())
            if missing:
                raise RuntimeError(f"NLI model {name} lacks labels {missing}; not an NLI model?")
    return _model, _tokenizer


def score_pairs(pairs: List[Tuple[str, str]], batch_size: int = 8) -> List[Dict[str, float]]:
    """Return {entailment, neutral, contradiction} probabilities per (premise, hypothesis)."""
    if not pairs:
        return []
    import torch

    model, tokenizer = _load()
    out: List[Dict[str, float]] = []
    with torch.no_grad():
        for i in range(0, len(pairs), batch_size):
            chunk = pairs[i:i + batch_size]
            enc = tokenizer([p for p, _ in chunk], [h for _, h in chunk], return_tensors="pt",
                            padding=True, truncation="only_first", max_length=512)
            probs = model(**enc).logits.softmax(-1)
            for row in probs:
                out.append({_labels[j]: round(float(v), 4) for j, v in enumerate(row)})
    return out
