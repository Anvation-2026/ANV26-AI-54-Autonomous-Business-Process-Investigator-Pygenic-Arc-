"""Small durable checkpoint store used by the graph runner."""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any


class JsonCheckpointStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def save(self, state: dict[str, Any], node: str) -> str:
        checkpoint_id = uuid.uuid4().hex
        record = {"id": checkpoint_id, "node": node, "state": state}
        with self._lock:
            records = []
            if self.path.exists():
                try:
                    records = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    records = []
            records.append(record)
            self.path.write_text(json.dumps(records[-100:], indent=2), encoding="utf-8")
        return checkpoint_id
