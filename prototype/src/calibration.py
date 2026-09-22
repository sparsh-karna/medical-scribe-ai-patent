"""
Adaptive per-field threshold calibration.

The dual-signal floors (SEMANTIC_FLOOR, ACOUSTIC_FLOOR in grounding.py) are
fixed safety minimums and are never adjusted -- no amount of clinician
approval history can push the system below them. What IS adaptive is the
combined-score bar a field must clear to auto-insert (AUTO_INSERT_THRESHOLD
by default). Each time a clinician resolves a blocked fact, this module
nudges that field's threshold toward the clinician's judgment:

  - approve a borderline fact -> threshold eases down for that field
    (future similar-confidence facts in that field need less friction)
  - reject a borderline fact  -> threshold tightens up for that field
    (future similar-confidence facts need more scrutiny)

This turns the gate from a static rule into one that learns, per clinical
field, how much scrutiny that field's clinicians actually want -- while
the hard safety floors underneath it stay fixed.
"""
from __future__ import annotations

import json
import os
from typing import Dict

DEFAULT_THRESHOLD = 0.75
MIN_THRESHOLD = 0.55
MAX_THRESHOLD = 0.95
LEARNING_RATE = 0.2


class CalibrationStore:
    def __init__(self, path: str):
        self.path = path
        self._thresholds: Dict[str, float] = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self._thresholds = json.load(f)

    def threshold_for(self, field: str) -> float:
        return self._thresholds.get(field, DEFAULT_THRESHOLD)

    def update_from_resolution(self, field: str, confidence: float, decision: str) -> float:
        current = self.threshold_for(field)
        if decision == "approve":
            target = confidence
        elif decision == "reject":
            target = MAX_THRESHOLD
        else:
            raise ValueError(f"Unknown decision: {decision}")

        new_value = current + LEARNING_RATE * (target - current)
        new_value = max(MIN_THRESHOLD, min(MAX_THRESHOLD, new_value))
        self._thresholds[field] = round(new_value, 3)
        self._save()
        return self._thresholds[field]

    def _save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._thresholds, f, indent=2)

    def as_dict(self) -> Dict[str, float]:
        return dict(self._thresholds)
