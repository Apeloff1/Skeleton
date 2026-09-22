from __future__ import annotations
from typing import Any, Dict, List, Optional

from gameforge.agents.jeeves_health_empathy import JeevesHealthEmpathy


class JeevesDiaryMixin:
    diaries = None
    personal_logs = None
    recording_ledger = None
    health = None
    calendar = None
    neuro = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    def bind_diaries(self, diary_service) -> None:
        self.diaries = diary_service

    def bind_personal_logs(self, log_service) -> None:
        self.personal_logs = log_service
        if self.health is None:
            self.health = JeevesHealthEmpathy()

    def bind_recording_ledger(self, ledger) -> None:
        self.recording_ledger = ledger

    def bind_calendar(self, calendar) -> None:
        self.calendar = calendar

    def bind_neuro(self, neuro) -> None:
        self.neuro = neuro

    async def diary_context_block(self, n: int = 4) -> str:
        if not self.diaries:
            return ""
        return self.diaries.export_all_context(n=n)

    async def logs_context_block(self, n_per_kind: int = 2) -> str:
        if not self.personal_logs:
            return ""
        return self.personal_logs.export_context(n_per_kind=n_per_kind)

    async def diary_mood_signals(self) -> Dict[str, Any]:
        if not self.diaries:
            return {}
        return self.diaries.mood_dashboard()

    async def wellness_signals(self) -> Dict[str, Any]:
        if not self.personal_logs:
            return {}
        return self.personal_logs.wellness_snapshot()

    async def build_proactive_diary_prompts(self) -> List[Dict[str, str]]:
        if not self.diaries:
            return []
        prompts: List[Dict[str, str]] = []
        mood = self.diaries.mood_dashboard()
        intro = mood.get("introspect") or {}
        retro = mood.get("retrospect") or {}
        outer = mood.get("outrospect") or {}
        mem = mood.get("memory") or {}

        if intro.get("count", 0) > 0 and intro.get("avg_mood") is not None:
            if intro["avg_mood"] < -0.25:
                prompts.append(
                    {
                        "type": "introspect_checkin",
                        "text": (
                            "You’ve logged some heavy inward notes recently. "
                            "Want a 2-minute reset: one tension, one need, one next kind step?"
                        ),
                    }
                )
        if (retro.get("count") or 0) == 0 and (mem.get("count") or 0) >= 3:
            prompts.append(
                {
                    "type": "retrospect_offer",
                    "text": (
                        "You’ve been active in the memory diary. "
                        "A short retrospect could lock the lesson: Keep / Change / One win?"
                    ),
                }
            )
        if outer.get("count", 0) > 0 and (outer.get("avg_mood") or 0) > 0.35:
            prompts.append(
                {
                    "type": "outrospect_reinforce",
                    "text": (
                        "Your outward notes skew positive. "
                        "Want to capture what in the environment helped, so we can repeat it?"
                    ),
                }
            )
        total = sum(
            (mood.get(k) or {}).get("count") or 0
            for k in ("memory", "introspect", "outrospect", "retrospect")
        )
        if total == 0:
            prompts.append(
                {
                    "type": "diary_empty",
                    "text": (
                        "Diaries are empty for this window. "
                        "One line is enough: inward (introspect), outward (outrospect), or a quick retrospect."
                    ),
                }
            )
        return prompts[:3]

    async def build_health_empathy_prompts(self) -> List[Dict[str, str]]:
        if not self.personal_logs:
            return []
        if self.health is None:
            self.health = JeevesHealthEmpathy()
        wellness = self.personal_logs.wellness_snapshot()
        return self.health.build_nudges(wellness)

    async def maybe_log_accomplishment_to_retrospect(
        self,
        title: str,
        body: str,
        *,
        period: str = "session",
        lesson: Optional[str] = None,
    ):
        if not self.diaries:
            return None
        return await self.diaries.retrospect.add_review(
            body,
            title=title,
            period=period,
            lesson=lesson,
            tags=["auto", "accomplishment"],
            mood=0.45,
            intensity=0.5,
        )

    async def compose_system_context(self) -> str:
        parts = []
        ctx = await self.diary_context_block(n=3)
        if ctx:
            parts.append(ctx)
        logs_ctx = await self.logs_context_block(n_per_kind=1)
        if logs_ctx:
            parts.append(logs_ctx)
        signals = await self.diary_mood_signals()
        if signals:
            parts.append(f"DIARY MOOD SIGNALS: {signals}")
        wellness = await self.wellness_signals()
        if wellness:
            parts.append(f"WELLNESS SNAPSHOT: {wellness}")
            if self.health is None:
                self.health = JeevesHealthEmpathy()
            health_block = self.health.compose_health_block(wellness)
            if health_block:
                parts.append(health_block)
        proactive = await self.build_proactive_diary_prompts()
        if proactive:
            parts.append(
                "OPTIONAL PROACTIVE DIARY PROMPTS:\n"
                + "\n".join(f"- ({p['type']}) {p['text']}" for p in proactive)
            )
        health_prompts = await self.build_health_empathy_prompts()
        if health_prompts:
            parts.append(
                "HEALTH EMPATHY NUDGES (supportive, non-medical):\n"
                + "\n".join(f"- ({p['type']}) {p['text']}" for p in health_prompts)
            )
        if self.recording_ledger is not None:
            parts.append(f"RECORDING LEDGER: {self.recording_ledger.status()}")
        if self.calendar is not None:
            try:
                parts.append(self.calendar.jeeves_context_block())
            except Exception:
                pass
        if self.neuro is not None:
            try:
                parts.append(self.neuro.jeeves_context_block())
            except Exception:
                pass
        return "\n\n".join(parts)
