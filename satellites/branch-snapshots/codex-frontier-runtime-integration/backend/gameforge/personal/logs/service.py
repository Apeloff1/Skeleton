from __future__ import annotations
# Zaibatsu: writes should pass through guard_text via API middleware + appwide install

from typing import Any, Dict, List, Optional
from collections import defaultdict

from gameforge.personal.logs.kinds import (
    PersonalLogKind,
    PersonalLogEntry,
    LOG_FOCUS,
)
from gameforge.personal.logs.insights import InsightEngine


class PersonalLogService:
    """
    Ten specialized logs + client ledger.
    Shares diary-like buffers and feeds insight engine for Jeeves wellness.
    """

    def __init__(self, user_id: str, diary_service=None):
        self.user_id = user_id
        self.diary_service = diary_service  # optional bridge
        self._entries: Dict[PersonalLogKind, List[PersonalLogEntry]] = defaultdict(list)
        self.max_per_kind = 200
        self.insights = InsightEngine()

    async def add(
        self,
        kind: PersonalLogKind,
        title: str,
        body: str,
        *,
        tags: Optional[List[str]] = None,
        mood: Optional[float] = None,
        intensity: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        source: str = "user",
        mirror_to_diary: bool = False,
    ) -> PersonalLogEntry:
        hints = self.insights.extract_hints(kind, body, metadata or {})
        entry = PersonalLogEntry.create(
            kind=kind,
            user_id=self.user_id,
            title=title,
            body=body,
            tags=tags,
            mood=mood,
            intensity=intensity,
            metadata=metadata,
            insight_hints=hints,
            source=source,
        )
        bucket = self._entries[kind]
        bucket.append(entry)
        if len(bucket) > self.max_per_kind:
            self._entries[kind] = bucket[-self.max_per_kind :]

        if mirror_to_diary and self.diary_service is not None:
            # soft mirror important entries into memory diary
            try:
                from gameforge.personal.diaries.base import DiaryKind

                await self.diary_service.add(
                    DiaryKind.MEMORY,
                    title=f"[{kind.value}] {title}",
                    body=body,
                    tags=(tags or []) + [f"log:{kind.value}"],
                    mood=mood,
                    intensity=intensity,
                    metadata={"from_log": kind.value, **(metadata or {})},
                    source=source,
                )
            except Exception:
                pass
        return entry

    def recent(self, kind: PersonalLogKind, n: int = 10) -> List[PersonalLogEntry]:
        return list(reversed(self._entries[kind][-n:]))

    def all_recent(self, n_per_kind: int = 3) -> Dict[str, List[PersonalLogEntry]]:
        return {k.value: self.recent(k, n_per_kind) for k in PersonalLogKind}

    def export_context(self, n_per_kind: int = 2) -> str:
        lines = ["[PERSONAL LOGS]"]
        for kind in PersonalLogKind:
            rows = self.recent(kind, n_per_kind)
            if not rows:
                continue
            lines.append(f"## {kind.value} — {LOG_FOCUS[kind]}")
            for e in rows:
                mood = f" mood={e.mood:.2f}" if e.mood is not None else ""
                lines.append(f"- ({e.created_at.isoformat()}) {e.title}{mood}: {e.body[:200]}")
                if e.insight_hints:
                    lines.append(f"  hints: {', '.join(e.insight_hints[:4])}")
        return "\n".join(lines)

    def wellness_snapshot(self) -> Dict[str, Any]:
        return self.insights.summarize(self._entries)

    # --- specialized helpers ---
    async def prospect(self, body: str, **kw):
        return await self.add(PersonalLogKind.PROSPECT, kw.pop("title", "Prospect"), body, **kw)

    async def executive(self, body: str, steps: Optional[List[str]] = None, **kw):
        meta = kw.pop("metadata", {}) or {}
        if steps:
            meta["steps"] = steps
            body = body + "\nSteps:\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))
        return await self.add(
            PersonalLogKind.EXECUTIVE_FUNCTION,
            kw.pop("title", "Executive breakdown"),
            body,
            metadata=meta,
            **kw,
        )

    async def somatic(self, body: str, region: Optional[str] = None, energy: Optional[float] = None, **kw):
        meta = kw.pop("metadata", {}) or {}
        if region:
            meta["region"] = region
        if energy is not None:
            meta["energy"] = energy
        return await self.add(
            PersonalLogKind.INTEROCEPTION,
            kw.pop("title", "Somatic note"),
            body,
            metadata=meta,
            **kw,
        )

    async def environmental(self, body: str, noise: Optional[str] = None, light: Optional[str] = None, **kw):
        meta = kw.pop("metadata", {}) or {}
        if noise:
            meta["noise"] = noise
        if light:
            meta["light"] = light
        return await self.add(
            PersonalLogKind.ENVIRONMENTAL_TRIGGER,
            kw.pop("title", "Environment"),
            body,
            metadata=meta,
            **kw,
        )

    async def bias_catch(self, thought: str, reframe: Optional[str] = None, **kw):
        meta = kw.pop("metadata", {}) or {}
        if reframe:
            meta["reframe"] = reframe
        body = thought if not reframe else f"Thought: {thought}\nReframe: {reframe}"
        return await self.add(
            PersonalLogKind.COGNITIVE_BIAS,
            kw.pop("title", "Bias catch"),
            body,
            metadata=meta,
            **kw,
        )

    async def sandbox(self, body: str, **kw):
        return await self.add(
            PersonalLogKind.WORKING_MEMORY,
            kw.pop("title", "Scratchpad"),
            body,
            **kw,
        )

    async def social(self, body: str, boundary: Optional[str] = None, outcome: Optional[str] = None, **kw):
        meta = kw.pop("metadata", {}) or {}
        if boundary:
            meta["boundary"] = boundary
        if outcome:
            meta["outcome"] = outcome
        return await self.add(
            PersonalLogKind.SOCIAL_BOUNDARY,
            kw.pop("title", "Social / boundary"),
            body,
            metadata=meta,
            **kw,
        )

    async def skill(self, body: str, skill: Optional[str] = None, reps: Optional[int] = None, **kw):
        meta = kw.pop("metadata", {}) or {}
        if skill:
            meta["skill"] = skill
        if reps is not None:
            meta["reps"] = reps
        return await self.add(
            PersonalLogKind.SKILL_ACQUISITION,
            kw.pop("title", "Skill practice"),
            body,
            metadata=meta,
            **kw,
        )

    async def stimulus_response(self, trigger: str, response: str, **kw):
        body = f"Trigger: {trigger}\nResponse: {response}"
        return await self.add(
            PersonalLogKind.STIMULUS_RESPONSE,
            kw.pop("title", "Stimulus → response"),
            body,
            metadata={"trigger": trigger, "response": response, **(kw.pop("metadata", {}) or {})},
            **kw,
        )

    async def synthesize_week(self, body: str, **kw):
        return await self.add(
            PersonalLogKind.CENTRAL_SYNTHESIS,
            kw.pop("title", "Weekly synthesis"),
            body,
            mirror_to_diary=True,
            **kw,
        )

    async def ledger_from_transcript(self, transcript: str, *, title: str = "Transcript note", **kw):
        return await self.add(
            PersonalLogKind.CLIENT_LEDGER,
            title,
            transcript,
            source="transcript",
            mirror_to_diary=False,
            **kw,
        )
