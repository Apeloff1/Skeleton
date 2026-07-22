from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import uuid

from gameforge.rooms.room_assignments import coder_for_tier
from gameforge.agents.style_application import StyleApplicator


class AgentState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    WORKING = "working"
    ERROR = "error"


@dataclass
class WorkItem:
    work_id: str
    agent_id: str
    room_id: str
    prompt: str
    priority: int = 50
    status: str = "queued"
    result: Any = None
    error: Optional[str] = None
    parent_work_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None

    @staticmethod
    def create(agent_id: str, room_id: str, prompt: str, priority: int = 50, **meta) -> "WorkItem":
        return WorkItem(
            work_id=str(uuid.uuid4())[:12],
            agent_id=agent_id,
            room_id=room_id,
            prompt=prompt,
            priority=priority,
            metadata=meta,
        )


@dataclass
class AgentContext:
    agent_id: str
    traits: Dict[str, Any] = field(default_factory=dict)
    levels: Dict[str, Any] = field(default_factory=dict)
    jeeves: Any = None


class AgentRuntime:
    """Continuous agent loop: queue → style-aware execute → EXP hooks."""

    def __init__(
        self,
        ctx: AgentContext,
        generator=None,
        on_work_complete: Optional[Callable] = None,
        level_system=None,
    ):
        self.ctx = ctx
        self.generator = generator
        self.on_work_complete = on_work_complete
        self.level_system = level_system
        self.state = AgentState.IDLE
        self.queue: List[WorkItem] = []
        self.history: List[WorkItem] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._styles = StyleApplicator()

    def enqueue(self, work: WorkItem):
        self.queue.append(work)
        self.queue.sort(key=lambda w: -w.priority)

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass

    async def _loop(self):
        while self._running:
            if not self.queue:
                self.state = AgentState.IDLE
                await asyncio.sleep(0.05)
                continue
            work = self.queue.pop(0)
            try:
                self.state = AgentState.WORKING
                await self._execute_work(work)
            except Exception as e:
                work.status = "error"
                work.error = str(e)
                work.completed_at = datetime.utcnow().isoformat()
                self.state = AgentState.ERROR
                self.history.append(work)
                await asyncio.sleep(0.1)
                self.state = AgentState.IDLE

    def _active_tier_for_room(self, room_id: str) -> str:
        if not self.level_system:
            return "standard"
        progress = self.level_system.get_room(room_id)
        tiers = progress.unlocked_tiers or ["standard"]
        for t in ("tier_4", "tier_3", "tier_2", "standard"):
            if t in tiers:
                return t
        return "standard"

    def _active_coder_key(self, room_id: str) -> Optional[str]:
        style = (self.ctx.traits or {}).get("active_style") or {}
        if style.get("coder_key"):
            return style["coder_key"]
        tier = self._active_tier_for_room(room_id)
        return coder_for_tier(room_id, tier)

    async def _execute_work(self, work: WorkItem) -> Any:
        self.state = AgentState.THINKING
        coder_key = self._active_coder_key(work.room_id)
        tier = self._active_tier_for_room(work.room_id)
        framed = self._compose_prompt(work, coder_key=coder_key)
        text = None
        if self.generator is not None:
            text = await self.generator.generate(
                work.room_id,
                framed,
                coder_key=coder_key,
                tier=tier,
            )
        else:
            text = f"[mock:{work.room_id}] {work.prompt[:200]}"
        work.result = {
            "text": text,
            "room_id": work.room_id,
            "coder_key": coder_key,
            "tier": tier,
        }
        work.status = "completed"
        work.completed_at = datetime.utcnow().isoformat()
        self.history.append(work)
        if self.on_work_complete:
            try:
                await self.on_work_complete(work)
            except Exception:
                pass
        self.state = AgentState.IDLE
        return work.result

    def _compose_prompt(self, work: WorkItem, coder_key: Optional[str] = None) -> str:
        if coder_key:
            style_block = self._styles.build_style_prompt_section(coder_key)
        else:
            style_block = "ACTIVE STYLE: standard"
        return (
            f"ROOM: {work.room_id}\n"
            f"{style_block}\n"
            f"RULES: Be concrete. Prefer production-quality output.\n"
            f"USER REQUEST: {work.prompt}"
        )

    def status(self) -> Dict[str, Any]:
        return {
            "agent_id": self.ctx.agent_id,
            "state": self.state.value,
            "queued": len(self.queue),
            "history": len(self.history),
        }
