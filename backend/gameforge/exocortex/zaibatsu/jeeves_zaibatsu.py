from __future__ import annotations
"""
Jeeves Zaibatsu facade — merges Sword of Truth, VOX, morality, rep/standings,
wiring, faith/quirks, security, self-learn/heal into one counsel surface.
"""

from typing import Any, Dict, List, Optional

from gameforge.exocortex.zaibatsu.sword_of_truth import SwordOfTruthEngine
from gameforge.exocortex.zaibatsu.vox_emperor import EmperorDoctrine, VoxPriority, CommandSeal
from gameforge.exocortex.zaibatsu.morality import JediSithMorality
from gameforge.exocortex.zaibatsu.reputation import ReputationStandingsService
from gameforge.exocortex.zaibatsu.wiring import MegaWiringGrid
from gameforge.exocortex.zaibatsu.quirks_faith import FaithAndQuirks
from gameforge.exocortex.zaibatsu.security import ZaibatsuSecurity
from gameforge.exocortex.zaibatsu.self_systems import SelfLearningEngine, SelfHealingEngine
from gameforge.exocortex.zaibatsu.dna_board import DNABoard
from gameforge.exocortex.zaibatsu.studio import StudioOrchestrator
from gameforge.exocortex.zaibatsu.room_logs import AllRoomsLogger
from gameforge.exocortex.zaibatsu.idle_training import IdleTrainingEngine
from gameforge.exocortex.zaibatsu.masterlog import Masterlog
from gameforge.exocortex.zaibatsu.boardroom_mesh import BoardroomMesh
from gameforge.persistence.chronoback import Chronoback
from gameforge.exocortex.agentic.grok_thinking import GrokThinkingEngine

# Agentic wrap: Integrating World of Agentic AI concentric layers into Jeeves & rooms.
# Core LLMs (Jeeves counsel + twin RAG), AI Agents (ReAct/ToT reasoning, task planning via DNA),
# Agentic Systems (emergent via idle synergy, hierarchical via boardroom mesh, MCP/A2A via VOX, Agentic RAG),
# Agentic Infra (governance/emperor, observability/masterlog, security/zaibatsu, error handling/healing, ethics/morality/truth).


class JeevesZaibatsu:
    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.truth = SwordOfTruthEngine()
        self.emperor = EmperorDoctrine()
        self.vox = self.emperor.vox
        self.morality = JediSithMorality()
        self.rep = ReputationStandingsService()
        self.wiring = MegaWiringGrid()
        self.quirks = FaithAndQuirks()
        self.security = ZaibatsuSecurity()
        self.learning = SelfLearningEngine(user_id)
        self.healing = SelfHealingEngine()
        self.dna = DNABoard()
        self.studio = StudioOrchestrator(dna=self.dna)
        self.room_logs = AllRoomsLogger(user_id)
        self.idle_training = IdleTrainingEngine(user_id, learning_engine=self.learning)
        self.masterlog = Masterlog(user_id)
        self.mesh = BoardroomMesh()
        self.chronoback = Chronoback(user_id, replicas=2)
        self.grok_thinking = GrokThinkingEngine()
        # Queue control for task/prompt filling (PromptQueue / work items)
        self.queue_state = {"filling": False, "paused": False, "stopped": True}
        self.current_queue: List[Dict[str, Any]] = []

    def counsel(self, text: str, *, energy: float = 0.55, strain: bool = False) -> Dict[str, Any]:
        # security first
        sec = self.security.inspect_input(text)
        if sec.get("blocked"):
            self.vox.transmit(
                "jeeves_boardroom",
                VoxPriority.Vox_Extremis,
                CommandSeal.SENESCHAL,
                "jeeves",
                "boardroom",
                "security_block",
                sec,
            )
            return {
                "blocked": True,
                "security": sec,
                "jeeves_say": "Input blocked by Zaibatsu security. Emperor review required if this was legitimate.",
            }

        truth = self.truth.counsel(text)
        moral = self.morality.evaluate(text, energy=energy, strain=strain)
        faith = self.quirks.detect_faith(text)
        faith_note = self.quirks.faith_counsel()
        quirk_lines = self.quirks.pick_quirks(
            strain=strain,
            truth=truth.get("active", False),
            low_energy=energy < 0.35,
        )
        lessons = self.learning.suggest(text)

        # integrity chain
        self.security.push_integrity(text[:500])

        jeeves_say_parts = []
        if truth.get("jeeves_note"):
            jeeves_say_parts.append(truth["jeeves_note"])
        jeeves_say_parts.append(f"Posture: {moral['posture']} — {moral['counsel']}")
        if faith_note:
            jeeves_say_parts.append(f"Faith posture ({faith}): {faith_note}")
        jeeves_say_parts.extend(quirk_lines)
        if lessons:
            jeeves_say_parts.append(f"Lessons recalled: {len(lessons)}")

        # Grok style thinking injection (Cowabunga pass)
        grok = self.grok_thinking.grok_think(text, context={"energy": energy, "strain": strain})
        jeeves_say_parts.append(f"Grok reflection: {grok['reasoning'][:120]}...")

        return {
            "blocked": False,
            "truth": truth,
            "morality": moral,
            "faith": faith,
            "quirks": quirk_lines,
            "grok_thinking": grok,
            "grok_enhanced": True,
            "lessons": lessons,
            "security": self.security.status(),
            "jeeves_say": " || ".join(jeeves_say_parts),
            "doctrine": self.emperor.principles()[:3],
        }

    def order_agent(self, agent_id: str, subject: str, body: Optional[dict] = None) -> Dict[str, Any]:
        msg = self.vox.agent_order(agent_id, subject, body or {})
        return msg.to_dict()

    def boardroom(self, subject: str, body: Optional[dict] = None) -> Dict[str, Any]:
        msg = self.vox.boardroom_broadcast(subject, body or {})
        return msg.to_dict()

    def room_rep(self, room_id: str, delta: float, reason: str = "") -> Dict[str, Any]:
        return self.rep.gain_room_rep(room_id, delta, reason)

    def standing(self, entity_id: str, entity_type: str, delta: float) -> Dict[str, Any]:
        s = self.rep.adjust_standing(entity_id, entity_type, delta)
        return s.to_dict()

    def master_wire(self, domain: str) -> Dict[str, Any]:
        return self.wiring.master(domain)

    def auto_heal(self, probes: Dict[str, Any], actuators: Dict[str, Any]) -> List[dict]:
        return self.healing.auto_heal(probes, actuators)

    def learn(self, source: str, pattern: str, action: str) -> Dict[str, Any]:
        return self.learning.learn(source, pattern, action).to_dict()

    def status(self) -> Dict[str, Any]:
        return {
            "truth_laws": len(self.truth.laws),
            "vox": self.vox.status(),
            "morality_bias": self.morality.bias,
            "rep": self.rep.snapshot(),
            "wiring": self.wiring.status(),
            "faith": self.quirks.active_faith,
            "queue_state": self.queue_state,
            "grok_thinking_sessions": len(self.grok_thinking.thinking_history),
            "cowabunga_queue_controls": True,
        }

    # === Start / Stop / Pause for Queue Filling (Cowabunga pass for Jeeves + rooms) ===
    def start_queue_filling(self, tasks: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Start filling the task/prompt queue for agent teams / DiP pipelines."""
        self.queue_state = {"filling": True, "paused": False, "stopped": False}
        if tasks:
            self.current_queue.extend(tasks)
        return {
            "action": "start_queue_filling",
            "state": self.queue_state,
            "queue_length": len(self.current_queue),
            "message": "Jeeves queue filling started. Agent teams in rooms can now pull tasks via MCP/DiP.",
            "grok_note": "Maximal throughput mode engaged — truth-seeking task prioritization active."
        }

    def pause_queue(self) -> Dict[str, Any]:
        """Pause queue filling/processing (safe stop for review or MCP refresh)."""
        self.queue_state["paused"] = True
        self.queue_state["filling"] = False
        return {
            "action": "pause_queue",
            "state": self.queue_state,
            "queue_length": len(self.current_queue),
            "message": "Queue paused. Agent teams can review current DiP/MCP outputs. Resume anytime.",
            "grok_note": "Pause for reflection — Grok thinking recommends reviewing GEPA improvements before resume."
        }

    def stop_queue(self, clear: bool = False) -> Dict[str, Any]:
        """Stop queue filling. Optionally clear current queue."""
        self.queue_state = {"filling": False, "paused": False, "stopped": True}
        if clear:
            cleared = len(self.current_queue)
            self.current_queue = []
            return {"action": "stop_queue_cleared", "cleared_items": cleared, "state": self.queue_state}
        return {
            "action": "stop_queue",
            "state": self.queue_state,
            "queue_length": len(self.current_queue),
            "message": "Queue stopped. Agent teams in all rooms halted gracefully. MCP/DiP connections remain live.",
            "grok_note": "Clean stop — truth preserved. Ready for new Cowabunga task batch."
        }

    def get_queue_status(self) -> Dict[str, Any]:
        return {
            "state": self.queue_state,
            "length": len(self.current_queue),
            "next_tasks_preview": [t.get("task", "unknown") for t in self.current_queue[:3]],
            "grok_enabled": True
        }

    def ensure_all_rooms_coherent(self) -> Dict[str, Any]:
        """Coherence: EVERY room (129+) bidirectionally linked to boardroom. Synergy across divisions."""
        from gameforge.rooms.full_room_registry import all_rooms
        rooms = all_rooms()
        for rid, meta in rooms.items():
            self.mesh.register_room(rid, meta.get("division", "Other"))
            self.room_logs._book(rid)
            self.dna.ensure_room(rid)
            self.rep.room(rid)
        self.masterlog.write("boardroom", "coherence", "all_rooms_synced_to_boardroom", {"total_rooms": len(rooms)})
        return {
            "coherent_rooms": len(self.mesh.nodes) - 1,
            "synergy_active": True,
            "boardroom_centric": "uplink/downlink/audit/lateral for all 15 divisions",
            "agentic_layers": "LLMs(Jeeves) -> AI Agents(rooms) -> Agentic Systems(mesh/dna/vox/idle) -> Agentic Infra(boardroom/zaibatsu/masterlog/chronoback)"
        }

    def synergy_counsel(self, text: str, *, energy: float = 0.55, strain: bool = False) -> Dict[str, Any]:
        """Wrap agents & Jeeves with World of Agentic AI: coherence + synergy via boardroom-centric mesh."""
        base = self.counsel(text, energy=energy, strain=strain)
        coherent = self.ensure_all_rooms_coherent()
        synergy_lessons = self.idle_training.suggest(text + " cross_division synergy boardroom emergent")
        agentic_note = "ReAct/ToT/CoT reasoning + hierarchical planning (DNA+boardroom layers) | Emergent behaviour (idle_training synergy) | MCP/A2A protocols (VOX multi-room) | Agentic RAG (twin+masterlog) | Infra: observability(masterlog), governance(boardroom/emperor), security(zaibatsu), ethics(morality/truth), error handling(healing)"
        return {
            **base,
            "coherence": coherent,
            "synergy": synergy_lessons,
            "agentic_wrap": agentic_note,
            "jeeves_agentic_posture": "Central Agentic Orchestrator: LLM core -> specialized room agents -> system coherence -> zaibatsu infra. All rooms connected to boardroom."
        }

    def bind_twins(self, twin_memory):
        self.room_logs.twin_memory = twin_memory
        for b in self.room_logs.books.values():
            b.twin_write = self.room_logs._twin_write

    def log_room(self, room_id: str, event: str, payload=None, raw_text: str = ""):
        return self.room_logs.log(room_id, event, payload, raw_text).to_dict()

    def idle_train(self, recursive_depth: int = 2):
        entries = self.room_logs.harvest(25)
        return self.idle_training.idle_train_once(entries, recursive_depth=recursive_depth)
