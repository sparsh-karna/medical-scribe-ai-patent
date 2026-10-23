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
            _model = AutoModelForSequenceClassification.from_pretrained(name).eval().to(_device())
            _labels = {int(i): label.lower() for i, label in _model.config.id2label.items()}
            missing = {"entailment", "neutral", "contradiction"} - set(_labels.values())
            if missing:
                raise RuntimeError(f"NLI model {name} lacks labels {missing}; not an NLI model?")
    return _model, _tokenizer


_cache: Dict[Tuple[str, str], Dict[str, float]] = {}
_CACHE_MAX = 50_000


def _device() -> str:
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


def score_pairs(pairs: List[Tuple[str, str]], batch_size: int = 0) -> List[Dict[str, float]]:
    """Return {entailment, neutral, contradiction} probabilities per (premise, hypothesis).
    Results are memoised: the model is deterministic, so a repeated pair gives the same
    probabilities (the ablation study scores each pair under several gate configurations)."""
    if not pairs:
        return []
    todo = list(dict.fromkeys(p for p in pairs if p not in _cache))
    if todo:
        import torch

        if len(_cache) + len(todo) > _CACHE_MAX:
            _cache.clear()  # before scoring, so every pair of this call stays available

        model, tokenizer = _load()
        batch_size = batch_size or (64 if _device() == "cuda" else 8)
        with torch.no_grad():
            for i in range(0, len(todo), batch_size):
                chunk = todo[i:i + batch_size]
                enc = tokenizer([p for p, _ in chunk], [h for _, h in chunk], return_tensors="pt",
                                padding=True, truncation="only_first", max_length=512).to(_device())
                probs = model(**enc).logits.softmax(-1).cpu()
                for pair, row in zip(chunk, probs):
                    _cache[pair] = {_labels[j]: round(float(v), 4) for j, v in enumerate(row)}
    return [dict(_cache[p]) for p in pairs]
