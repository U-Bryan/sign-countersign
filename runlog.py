"""Per-trial JSONL event log. Rule R4: if it isn't logged, it didn't happen."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


class RunLogger:
    def __init__(self, path: Path | str | None, run_id: str, clock=None):
        self.run_id = run_id
        self.clock = clock
        self.events: list[dict] = []
        self._seq = 0
        self._lock = threading.Lock()
        self._fh = None
        if path is not None:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(p, "w", encoding="utf-8", newline="\n")
        self.path = Path(path) if path is not None else None

    def log(self, event: str, **fields) -> dict:
        with self._lock:
            self._seq += 1
            rec = {
                "seq": self._seq,
                "event": event,
                "sim_time_ms": self.clock.now_ms() if self.clock is not None else None,
                "wall_time_iso": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "perf_ns": time.perf_counter_ns(),
                "run_id": self.run_id,
            }
            rec.update(fields)
            line = json.dumps(rec, ensure_ascii=False, default=str)
            self.events.append(json.loads(line))
            if self._fh is not None:
                self._fh.write(line + "\n")
                self._fh.flush()
            return rec

    def of(self, *event_types: str) -> list[dict]:
        return [e for e in self.events if e["event"] in event_types]

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                self._fh.close()
                self._fh = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def read_jsonl(path: Path | str) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
