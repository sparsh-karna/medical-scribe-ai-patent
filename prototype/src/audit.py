"""
Append-only audit trail.

Every gate decision (automatic) and every clinician resolution (manual) is
appended as one JSON line. Lines are never edited or deleted -- that is
what makes the trail usable as evidence that a given clinical statement
was either machine-verified above threshold, or explicitly signed off by
a named clinician, before it entered the record.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, Any


class AuditLog:
    def __init__(self, path: str):
        self.path = path

    def append(self, entry: Dict[str, Any]) -> None:
        entry = dict(entry)
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def read_all(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
