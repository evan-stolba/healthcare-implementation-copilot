"""Append-only log of every question clients ask. This is what feeds the success dashboard."""

import json
from datetime import datetime, timezone
from pathlib import Path

from copilot.answer import Answer

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "data" / "question_log.jsonl"
OUT_OF_SCOPE = "Out of scope"


def topic_for(answer: Answer) -> str:
    """Label a question with the topic of its best-matching source, or flag it as out of scope."""
    if not answer.answered or not answer.retrieved:
        return OUT_OF_SCOPE
    return (answer.sources or answer.retrieved)[0]["topic"]


def record(answer: Answer, client: str, timestamp: datetime | None = None, demo: bool = False,
           path: Path = LOG_PATH) -> dict:
    entry = {
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "client": client,
        "question": answer.question,
        "topic": topic_for(answer),
        "answered": answer.answered,
        "mode": answer.mode,
        "top_score": answer.retrieved[0]["score"] if answer.retrieved else 0.0,
        "cited_sources": [s["source_id"] for s in answer.sources],
        "demo": demo,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load(path: Path = LOG_PATH) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
