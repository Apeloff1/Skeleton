from __future__ import annotations
from typing import Optional, List
from gameforge.personal.diaries.base import DiaryBase, DiaryKind, DiaryEntry


class MemoryDiary(DiaryBase):
    kind = DiaryKind.MEMORY


class IntrospectDiary(DiaryBase):
    kind = DiaryKind.INTROSPECT

    async def add_self_observation(
        self,
        body: str,
        *,
        title: str = "Self observation",
        affect: Optional[str] = None,
        need: Optional[str] = None,
        mood: Optional[float] = None,
        intensity: Optional[float] = None,
        tags: Optional[List[str]] = None,
    ) -> DiaryEntry:
        meta = {"affect": affect, "need": need, "axis": "inward"}
        tags = list(tags or [])
        if affect:
            tags.append(f"affect:{affect}")
        if need:
            tags.append(f"need:{need}")
        tags.append("introspect")
        return await self.add(
            title=title,
            body=body,
            tags=tags,
            mood=mood,
            intensity=intensity,
            metadata=meta,
            source="user",
        )


class OutrospectDiary(DiaryBase):
    kind = DiaryKind.OUTROSPECT

    async def add_world_observation(
        self,
        body: str,
        *,
        title: str = "World observation",
        subject: Optional[str] = None,
        relation: Optional[str] = None,
        mood: Optional[float] = None,
        intensity: Optional[float] = None,
        tags: Optional[List[str]] = None,
    ) -> DiaryEntry:
        meta = {"subject": subject, "relation": relation, "axis": "outward"}
        tags = list(tags or [])
        if subject:
            tags.append(f"subject:{subject}")
        if relation:
            tags.append(f"relation:{relation}")
        tags.append("outrospect")
        return await self.add(
            title=title,
            body=body,
            tags=tags,
            mood=mood,
            intensity=intensity,
            metadata=meta,
            source="user",
        )


class RetrospectDiary(DiaryBase):
    kind = DiaryKind.RETROSPECT

    async def add_review(
        self,
        body: str,
        *,
        title: str = "Retrospective",
        period: Optional[str] = None,
        lesson: Optional[str] = None,
        keep: Optional[str] = None,
        change: Optional[str] = None,
        mood: Optional[float] = None,
        intensity: Optional[float] = None,
        tags: Optional[List[str]] = None,
    ) -> DiaryEntry:
        meta = {
            "period": period,
            "lesson": lesson,
            "keep": keep,
            "change": change,
            "axis": "backward",
        }
        tags = list(tags or [])
        if period:
            tags.append(f"period:{period}")
        tags.append("retrospect")
        chunks = [body]
        if lesson:
            chunks.append(f"Lesson: {lesson}")
        if keep:
            chunks.append(f"Keep: {keep}")
        if change:
            chunks.append(f"Change: {change}")
        return await self.add(
            title=title,
            body="\n".join(chunks),
            tags=tags,
            mood=mood,
            intensity=intensity,
            metadata=meta,
            source="user",
        )
