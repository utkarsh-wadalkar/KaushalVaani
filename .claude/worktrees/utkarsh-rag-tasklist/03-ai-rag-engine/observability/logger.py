"""Dependency-free structured request logging."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Callable


class StructuredLogger:
    def __init__(self, sink: Callable[[str], None] | None = None):
        self.sink = sink or (lambda line: print(line, file=sys.stderr))

    def event(self, request_id: str, event: str, **fields: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "event": event,
            **fields,
        }
        self.sink(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return payload

    def stage(self, request_id: str, stage: str, **fields: Any) -> dict[str, Any]:
        return self.event(request_id, "stage", stage=stage, **fields)


__all__ = ["StructuredLogger"]
