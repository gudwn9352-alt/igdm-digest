"""처리 상태 저장: 이미 분석한 메시지 id 와 실행 이력."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


class State:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.seen: set[str] = set()
        self.runs: list[dict] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        self.seen = set(data.get("seen_message_ids", []))
        self.runs = list(data.get("runs", []))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"seen_message_ids": sorted(self.seen), "runs": self.runs[-200:]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def is_seen(self, message_id: str) -> bool:
        return message_id in self.seen

    def mark_seen(self, ids: Iterable[str]) -> None:
        self.seen.update(ids)

    def record_run(self, summary: dict) -> None:
        self.runs.append(summary)
