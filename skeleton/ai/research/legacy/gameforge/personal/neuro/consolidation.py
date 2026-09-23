from __future__ import annotations
"""
Sleep & Consolidation Routine — end-of-day / midnight compression.
Strips filler, summarizes core lessons, writes distilled essence into long-term grid.
"""

import re
from dataclasses import dataclass, asdict, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pathlib import Path
import json
import os

from gameforge.personal.neuro.salience import SalienceNetwork


FILLER_WORDS = {
    "um", "uh", "like", "you know", "sort of", "kind of", "basically", "actually",
    "yeah", "yep", "okay", "ok", "right", "so", "well",
}


@dataclass
class ConsolidationResult:
    day: str
    input_chars: int
    kept_segments: int
    dropped_segments: int
    summary: str
    lessons: List[str]
    essence_path: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class SleepConsolidationRoutine:
    def __init__(self, user_id: str, salience: Optional[SalienceNetwork] = None):
        self.user_id = user_id
        self.salience = salience or SalienceNetwork(threshold=0.45)
        base = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        self.grid_root = base / "decade_essence" / user_id
        self.grid_root.mkdir(parents=True, exist_ok=True)

    def _strip_filler(self, text: str) -> str:
        t = text
        for w in FILLER_WORDS:
            t = re.sub(rf"\b{re.escape(w)}\b[,.]?", " ", t, flags=re.I)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def _segment(self, transcript_blob: str) -> List[str]:
        # split on newlines / sentence ends
        parts = re.split(r"[\n]+|(?<=[.!?])\s+", transcript_blob)
        return [p.strip() for p in parts if p and p.strip()]

    def consolidate(
        self,
        transcript_segments: List[str],
        *,
        day: Optional[date] = None,
        extra_notes: Optional[List[str]] = None,
    ) -> ConsolidationResult:
        day = day or date.today()
        segments = list(transcript_segments)
        if extra_notes:
            segments.extend(extra_notes)

        joined = "\n".join(segments)
        input_chars = len(joined)
        cleaned = [self._strip_filler(s) for s in segments]
        cleaned = [s for s in cleaned if s]

        kept_results, dropped = self.salience.filter_batch(cleaned)
        kept_texts = [r.text for r in kept_results]

        lessons = self._extract_lessons(kept_texts)
        summary = self._summarize(kept_texts, lessons)

        path = self.grid_root / f"{day.year}.jsonl"
        essence = {
            "day": day.isoformat(),
            "summary": summary,
            "lessons": lessons,
            "salient_count": len(kept_texts),
            "dropped_count": len(dropped),
            "categories": list({r.category for r in kept_results}),
            "created_at": datetime.utcnow().isoformat(),
        }
        with path.open("a") as f:
            f.write(json.dumps(essence) + "\n")

        return ConsolidationResult(
            day=day.isoformat(),
            input_chars=input_chars,
            kept_segments=len(kept_texts),
            dropped_segments=len(dropped),
            summary=summary,
            lessons=lessons,
            essence_path=str(path),
        )

    def _extract_lessons(self, texts: List[str]) -> List[str]:
        lessons = []
        for t in texts:
            low = t.lower()
            if any(k in low for k in ("learned", "lesson", "next time", "i will", "remember")):
                lessons.append(t[:240])
            elif any(k in low for k in ("deadline", "court", "milestone", "ship")):
                lessons.append(t[:240])
        # unique preserve order
        out = []
        seen = set()
        for L in lessons:
            if L not in seen:
                seen.add(L)
                out.append(L)
        return out[:12]

    def _summarize(self, texts: List[str], lessons: List[str]) -> str:
        if not texts and not lessons:
            return "Quiet day — little salient signal after consolidation."
        head = texts[:5]
        body = " | ".join(h[:120] for h in head)
        if lessons:
            return f"Essence: {body}. Core lessons: {'; '.join(lessons[:3])}"
        return f"Essence: {body}"

    def read_essence_year(self, year: int) -> List[dict]:
        path = self.grid_root / f"{year}.jsonl"
        if not path.exists():
            return []
        rows = []
        with path.open() as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
        return rows
