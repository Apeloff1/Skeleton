"""Jeeves core: system laws, session orchestration, co-coding mode.

Jeeves is the tutor persona that fronts the platform. The core owns session
lifecycle, enforces the system laws (pedagogy-first, honesty, safety), and
switches into co-coding mode when the learner wants to build rather than be
taught. LLM access is injected; without a backend, Jeeves answers from its
local scaffolding responder.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from skeleton.kernel.errors import SessionError
from skeleton.kernel.events import EventBus
from skeleton.kernel.ids import SessionId, UserId

SYSTEM_LAWS: tuple[str, ...] = (
    "Teach, don't just answer: every response must advance understanding.",
    "Never fabricate: say 'I don't know' rather than invent.",
    "Adapt to the learner: pace, depth, and register follow the learner model.",
    "In co-coding mode, the learner drives; Jeeves reviews and explains.",
    "Safety first: refuse harmful content and redirect constructively.",
)


class SessionMode(str, Enum):
    TUTORING = "tutoring"
    CO_CODING = "co_coding"
    TACTICAL = "tactical"
    BUILDER = "builder"
    CORTEX = "cortex"
    CREATIVE = "creative"
    ANALYTICAL = "analytical"
    DEBUG = "debug"


@dataclass
class Turn:
    role: str  # "learner" | "jeeves"
    content: str
    at: float = field(default_factory=time.time)


@dataclass
class Session:
    session_id: str
    user_id: str
    mode: SessionMode = SessionMode.TUTORING
    turns: list[Turn] = field(default_factory=list)
    opened_at: float = field(default_factory=time.time)
    closed_at: float | None = None

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    def add_turn(self, role: str, content: str) -> Turn:
        if not self.is_open:
            raise SessionError("cannot add a turn to a closed session",
                               context={"session_id": self.session_id})
        turn = Turn(role=role, content=content)
        self.turns.append(turn)
        return turn


ResponderFn = Callable[[str, list[Turn], dict[str, Any]], str]


def _cortex_can_think(cortex: Any) -> bool:
    """True when cortex is the GameForge neocortex (has think), not observability stub."""
    return cortex is not None and callable(getattr(cortex, "think", None))


def _local_responder(message: str, history: list[Turn], context: dict[str, Any]) -> str:
    """Fallback responder: Socratic scaffolding without an LLM backend."""
    topic = message.strip().rstrip("?")[:80]
    hints = context.get("hints") or []
    prefix = "Let's work through this together. " if history else "Good question. "
    scaffold = f"On '{topic}': start by stating what you already know about it."
    if hints:
        scaffold += f" Hint: {hints[0]}."
    scaffold += " Then tell me where your understanding gets shaky, and we'll build from there."
    return prefix + scaffold


class Jeeves:
    """The tutor brain: sessions, laws, co-coding."""

    def __init__(self, bus: EventBus | None = None,
                 responder: ResponderFn | None = None,
                 *, max_turns: int = 200,
                 max_sessions: int = 1000,
                 max_message_chars: int = 32_000) -> None:
        if type(max_turns) is not int or max_turns < 2:
            raise ValueError("max_turns must be an integer >= 2")
        if type(max_sessions) is not int or max_sessions < 1:
            raise ValueError("max_sessions must be an integer >= 1")
        if type(max_message_chars) is not int or max_message_chars < 1:
            raise ValueError("max_message_chars must be an integer >= 1")
        if responder is not None and not callable(responder):
            raise TypeError("responder must be callable")
        self._bus = bus or EventBus()
        self._responder = responder or _local_responder
        self._max_turns = max_turns
        self._max_sessions = max_sessions
        self._max_message_chars = max_message_chars
        self._sessions: dict[str, Session] = {}
        self._brain = None  # lazy TacticalBrain
        self._cortex = None  # lazy JeevesCortex — the model in training
        self._game_engines = None  # lazy executable historical engine lab
        self._game_projects = None  # lazy composite runtime + asset project lab
        self.era = "extraction_now"
        self.last_plan = None
        self.last_walk = None

    @property
    def laws(self) -> tuple[str, ...]:
        return SYSTEM_LAWS

    @staticmethod
    def _require_mode(mode: SessionMode) -> SessionMode:
        if not isinstance(mode, SessionMode):
            raise SessionError("invalid session mode", context={"mode": str(mode)[:64]})
        return mode

    def _reclaim_closed_session(self) -> bool:
        closed = [s for s in self._sessions.values() if not s.is_open]
        if not closed:
            return False
        victim = min(closed, key=lambda s: s.closed_at or s.opened_at)
        self._sessions.pop(victim.session_id, None)
        self._bus.emit("jeeves.session.evicted", {
            "session_id": victim.session_id,
            "turns": len(victim.turns),
        })
        return True

    def _ensure_turn_capacity(self, session: Session, needed: int) -> None:
        if len(session.turns) + needed > self._max_turns:
            raise SessionError("session turn limit reached",
                               context={"session_id": session.session_id,
                                        "max_turns": self._max_turns})

    def open_session(self, user_id: str | UserId, *, mode: SessionMode = SessionMode.TUTORING) -> Session:
        mode = self._require_mode(mode)
        if len(self._sessions) >= self._max_sessions and not self._reclaim_closed_session():
            raise SessionError("session capacity reached",
                               context={"max_sessions": self._max_sessions})
        session = Session(session_id=str(SessionId.new()), user_id=str(user_id), mode=mode)
        self._sessions[session.session_id] = session
        self._bus.emit("jeeves.session.opened",
                       {"session_id": session.session_id, "mode": mode.value})
        return session

    def close_session(self, session_id: str) -> Session:
        session = self._get(session_id)
        if session.is_open:
            session.closed_at = time.time()
            self._bus.emit("jeeves.session.closed",
                           {"session_id": session_id, "turns": len(session.turns)})
        return session

    def set_mode(self, session_id: str, mode: SessionMode) -> Session:
        session = self._get(session_id)
        mode = self._require_mode(mode)
        if not session.is_open:
            raise SessionError("session is closed", context={"session_id": session_id})
        session.mode = mode
        self._bus.emit("jeeves.session.mode_changed",
                       {"session_id": session_id, "mode": mode.value})
        return session

    def ask(self, session_id: str, message: str, *, context: dict[str, Any] | None = None) -> str:
        """Take a learner turn and commit it only when a valid reply exists."""
        if not isinstance(message, str) or not message.strip():
            raise SessionError("message must be a non-empty string")
        if len(message) > self._max_message_chars:
            raise SessionError("message exceeds size limit",
                               context={"max_message_chars": self._max_message_chars})
        if context is not None and not isinstance(context, dict):
            raise SessionError("context must be an object")

        session = self._get(session_id)
        self._ensure_turn_capacity(session, 2)
        prior_history = [Turn(role=t.role, content=t.content, at=t.at) for t in session.turns]
        start_turns = len(session.turns)
        session.add_turn("learner", message)
        ctx = dict(context or {})
        ctx["mode"] = session.mode.value

        try:
            if session.mode in (SessionMode.TACTICAL, SessionMode.BUILDER):
                tel = ctx.get("telemetry") or {}
                reply = self._brain_get().recommend_next(tel).text
            elif session.mode is SessionMode.CORTEX:
                reply = self.think(message, context=ctx).amalgam.text
            else:
                reply = self._responder(message, prior_history, ctx)
            if not isinstance(reply, str) or not reply.strip():
                raise SessionError("responder returned an invalid reply",
                                   context={"session_id": session_id})
            session.add_turn("jeeves", reply)
        except BaseException:
            del session.turns[start_turns:]
            self._bus.emit("jeeves.turn.failed", {"session_id": session_id})
            raise

        self._bus.emit("jeeves.turn.completed",
                       {"session_id": session_id, "turns": len(session.turns)})
        return reply

    def review_code(self, session_id: str, code: str) -> dict[str, Any]:
        """Co-coding mode: lightweight static review of learner code."""
        session = self._get(session_id)
        if session.mode is not SessionMode.CO_CODING:
            raise SessionError("review_code requires co_coding mode",
                               context={"session_id": session_id})
        findings: list[dict[str, Any]] = []
        for i, line in enumerate(code.splitlines(), start=1):
            if "eval(" in line or "exec(" in line:
                findings.append({"line": i, "severity": "error",
                                 "message": "avoid eval/exec — unsafe dynamic execution"})
            elif len(line) > 120:
                findings.append({"line": i, "severity": "style",
                                 "message": "line over 120 characters"})
        summary = "Looks clean." if not findings else f"{len(findings)} finding(s)."
        self._bus.emit("jeeves.review.completed",
                       {"session_id": session_id, "findings": len(findings)})
        return {"findings": findings, "summary": summary}

    def get_session(self, session_id: str) -> Session:
        return self._get(session_id)

    @property
    def game_engines(self):
        """Lazy Pong-to-next executable engine laboratory."""
        if self._game_engines is None:
            from skeleton.jeeves.game_engine_runtime import ExecutableGameEngineLab
            self._game_engines = ExecutableGameEngineLab()
        return self._game_engines

    def build_game_engine(self, era, *, gameplay_dialect: str | None = None):
        """Create an isolated executable era sandbox owned by Jeeves."""
        sandbox = self.game_engines.create(era, gameplay_dialect)
        self._bus.emit(
            "jeeves.game_engine.created",
            {
                "era": sandbox.era.value,
                "family": sandbox.family.value,
                "tree_digest": sandbox.tree.digest,
            },
        )
        return sandbox

    @property
    def game_projects(self):
        """Lazy complete project lab over all deterministic engine evidence planes."""
        if self._game_projects is None:
            from skeleton.jeeves.game_engine_project import ExecutableGameProjectLab

            self._game_projects = ExecutableGameProjectLab(
                self.game_engines
            )
        return self._game_projects

    def compile_game_navigation(
        self,
        sandbox,
        source,
    ):
        """Compile one bounded historical navigation graph into a sandbox."""
        from skeleton.jeeves.game_engine_navigation import (
            attach_navigation_build,
            compile_navigation_build,
        )

        build = compile_navigation_build(
            sandbox.era,
            source,
        )
        compiled = attach_navigation_build(
            sandbox,
            source,
        )
        self._bus.emit(
            "jeeves.game_engine.navigation_compiled",
            {
                "era": sandbox.era.value,
                "family": sandbox.family.value,
                "source_digest": build.source_digest,
                "policy_digest": build.policy_digest,
                "manifest_digest": build.manifest_digest,
                "node_count": len(source.nodes),
                "edge_count": len(source.edges),
                "tree_digest": compiled.tree.digest,
            },
        )
        return compiled

    def evaluate_game_navigation(
        self,
        sandbox,
        source,
    ):
        """Attest compiled navigation, path optimality, hierarchy, and steering."""
        from skeleton.jeeves.game_engine_navigation import NavigationAdversary

        report = NavigationAdversary().evaluate(
            sandbox,
            source,
        )
        self._bus.emit(
            "jeeves.game_engine.navigation_evaluated",
            {
                "era": sandbox.era.value,
                "score": report.score,
                "passed": report.passed,
                "failed": list(report.failed),
            },
        )
        return report

    def game_navigation(
        self,
        era,
        source=None,
    ):
        """Create a deterministic historical navigation runtime."""
        from skeleton.jeeves.game_engine_navigation import build_navigation_runtime

        runtime = build_navigation_runtime(
            era,
            source,
        )
        self._bus.emit(
            "jeeves.game_engine.navigation_created",
            {
                "era": runtime.era.value,
                "mode": runtime.policy.mode.value,
                "nodes": len(runtime.source.nodes),
                "edges": len(runtime.source.edges),
                "dynamic_obstacles": runtime.policy.dynamic_obstacles,
                "hierarchical": runtime.policy.hierarchical,
                "crowd_steering": runtime.policy.crowd_steering,
            },
        )
        return runtime

    def query_game_navigation(
        self,
        runtime,
        query,
    ):
        """Execute one deterministic navigation query."""
        result = runtime.path(
            query
        )
        self._bus.emit(
            "jeeves.game_engine.navigation_queried",
            {
                "era": result.era.value,
                "mode": result.mode.value,
                "start": result.start,
                "goal": result.goal,
                "found": result.found,
                "path_nodes": len(result.path),
                "cost": result.total_cost,
                "expanded_nodes": result.expanded_nodes,
                "digest": result.digest,
            },
        )
        return result

    def game_loop(
        self,
        sandbox,
    ):
        """Bind one engine sandbox to deterministic timing, input, and replay."""
        from skeleton.jeeves.game_engine_session import (
            build_game_loop,
        )

        loop = build_game_loop(
            sandbox
        )
        self._bus.emit(
            "jeeves.game_engine.loop_created",
            {
                "era": loop.era.value,
                "family": sandbox.family.value,
                "tree_digest": sandbox.tree.digest,
                "machine_digest": loop.machine.fingerprint(),
                "clock_digest": loop.clock.fingerprint(),
                "chain_digest": loop.chain_digest,
            },
        )
        return loop

    def advance_game_loop(
        self,
        loop,
        delta_ns: int,
        samples=(),
    ):
        """Advance one presentation interval through clock, input, and machine."""
        result = loop.advance(
            delta_ns,
            samples,
        )
        self._bus.emit(
            "jeeves.game_engine.loop_advanced",
            {
                "era": result.era.value,
                "presentation_index": result.presentation_index,
                "simulation_steps": result.timing.simulation_steps,
                "dropped_simulation_steps":
                    result.timing.dropped_simulation_steps,
                "simulation_tick": result.timing.simulation_tick,
                "input_records": sum(
                    len(
                        item.input_digests
                    )
                    for item
                    in result.simulation
                ),
                "machine_digest": result.machine_digest,
                "clock_digest": result.clock_digest,
                "chain_digest": result.chain_digest,
                "digest": result.digest,
            },
        )
        return result

    def verify_game_loop_replay(
        self,
        loop,
    ):
        """Replay a loop from fresh sandbox state and compare all authority."""
        verification = (
            loop.verify_replay()
        )
        self._bus.emit(
            "jeeves.game_engine.loop_replay_verified",
            {
                "era": loop.era.value,
                "passed": verification.passed,
                "advances": verification.advances,
                "failure_index": verification.failure_index,
                "chain_digest": verification.chain_digest,
                "machine_digest": verification.machine_digest,
                "clock_digest": verification.clock_digest,
                "detail": verification.detail,
            },
        )
        return verification
    def export_game_loop_replay(
        self,
        loop,
    ) -> bytes:
        """Serialize one verified deterministic game-loop replay tape."""
        from skeleton.jeeves.game_engine_session import (
            build_replay_tape,
            serialize_replay_tape,
        )

        tape = build_replay_tape(
            loop
        )
        data = serialize_replay_tape(
            tape
        )
        self._bus.emit(
            "jeeves.game_engine.loop_replay_exported",
            {
                "era": tape.era.value,
                "tree_digest": tape.tree_digest,
                "advances": len(tape.advances),
                "tape_digest": tape.digest,
                "bytes": len(data),
            },
        )
        return data

    def verify_game_loop_replay_tape(
        self,
        sandbox,
        data: bytes,
    ):
        """Parse and replay a portable tape against the exact sandbox authority."""
        from skeleton.jeeves.game_engine_session import (
            parse_replay_tape,
            verify_replay_tape,
        )

        tape = parse_replay_tape(
            data
        )
        verification = verify_replay_tape(
            sandbox,
            tape,
        )
        self._bus.emit(
            "jeeves.game_engine.loop_replay_tape_verified",
            {
                "era": tape.era.value,
                "tree_digest": tape.tree_digest,
                "tape_digest": tape.digest,
                "passed": verification.passed,
                "advances": verification.advances,
                "failure_index": verification.failure_index,
                "chain_digest": verification.chain_digest,
                "machine_digest": verification.machine_digest,
                "clock_digest": verification.clock_digest,
                "detail": verification.detail,
            },
        )
        return verification


    def game_clock(
        self,
        era,
    ):
        """Create the exact-rational caller-driven game simulation clock."""
        from skeleton.jeeves.game_engine_timing import (
            build_game_clock,
        )

        clock = build_game_clock(
            era
        )
        self._bus.emit(
            "jeeves.game_engine.clock_created",
            {
                "era": clock.era.value,
                "mode": clock.policy.mode.value,
                "simulation_hz": clock.policy.simulation_hz,
                "presentation_hz": clock.policy.presentation_hz,
                "max_catchup_steps": clock.policy.max_catchup_steps,
                "domains": [
                    {
                        "name": item.name,
                        "hz": item.hz,
                    }
                    for item
                    in clock.policy.domains
                ],
            },
        )
        return clock

    def advance_game_clock(
        self,
        clock,
        delta_ns: int,
    ):
        """Advance a deterministic game clock by caller-supplied nanoseconds."""
        frame = clock.advance(
            delta_ns
        )
        self._bus.emit(
            "jeeves.game_engine.clock_advanced",
            {
                "era": frame.era.value,
                "presentation_index": frame.presentation_index,
                "simulation_steps": frame.simulation_steps,
                "dropped_simulation_steps": frame.dropped_simulation_steps,
                "simulation_tick": frame.simulation_tick,
                "interpolation_alpha": frame.interpolation_alpha,
                "digest": frame.digest,
            },
        )
        return frame

    def game_input_normalizer(
        self,
        era,
    ):
        """Create the deterministic device-to-era input lowering boundary."""
        from skeleton.jeeves.game_engine_input import (
            build_input_normalizer,
        )

        normalizer = build_input_normalizer(
            era
        )
        self._bus.emit(
            "jeeves.game_engine.input_normalizer_created",
            {
                "era": normalizer.era.value,
                "devices": [
                    item.value
                    for item
                    in normalizer.policy.devices
                ],
                "max_players": normalizer.policy.max_players,
                "haptic_mode": normalizer.policy.haptic_mode.value,
            },
        )
        return normalizer

    def normalize_game_input(
        self,
        era,
        sample,
    ):
        """Normalize one host-independent device sample for an engine era."""
        normalizer = self.game_input_normalizer(
            era
        )
        value = normalizer.normalize(
            sample
        )
        self._bus.emit(
            "jeeves.game_engine.input_normalized",
            {
                "era": value.era.value,
                "tick": value.tick,
                "player": value.player,
                "device": value.device.value,
                "digest": value.digest,
                "buttons": int(
                    value.compatibility.buttons
                ),
            },
        )
        return value

    def normalize_game_haptic(
        self,
        era,
        request,
    ):
        """Normalize one deterministic haptic request through era capabilities."""
        from skeleton.jeeves.game_engine_input import (
            normalize_haptic,
        )

        value = normalize_haptic(
            era,
            request,
        )
        self._bus.emit(
            "jeeves.game_engine.haptic_normalized",
            {
                "era": value.era.value,
                "tick": value.tick,
                "player": value.player,
                "mode": value.mode.value,
                "channel": value.channel,
                "digest": value.digest,
            },
        )
        return value

    def game_save_manager(
        self,
        era,
        store=None,
        *,
        namespace: str = "jeeves-game",
    ):
        """Create historical save semantics over the existing SnapshotStore."""
        from skeleton.jeeves.game_engine_saves import (
            build_game_save_manager,
        )

        manager = build_game_save_manager(
            era,
            store,
            namespace=namespace,
        )
        self._bus.emit(
            "jeeves.game_engine.save_manager_created",
            {
                "era": manager.era.value,
                "medium": manager.policy.medium.value,
                "integrity": manager.policy.integrity.value,
                "player_state": manager.policy.player_state,
                "max_slots": manager.policy.max_slots,
            },
        )
        return manager

    def build_game_project(
        self,
        era,
        *,
        gameplay_dialect: str | None = None,
        sources=None,
        scripts=None,
        physics=None,
        audio=None,
        animation=None,
        navigation=None,
    ):
        """Create an executable era project with all deterministic evidence planes."""
        project = self.game_projects.create(
            era,
            gameplay_dialect,
            sources=sources,
            scripts=scripts,
            physics=physics,
            audio=audio,
            animation=animation,
            navigation=navigation,
        )
        self._bus.emit(
            "jeeves.game_project.created",
            {
                "era": project.era.value,
                "family": project.family.value,
                "asset_count": len(project.sources),
                "script_count": len(project.scripts),
                "physics_bodies": len(project.physics.bodies),
                "audio_sounds": len(project.audio.sounds),
                "animation_clips": len(project.animation.clips),
                "navigation_nodes": len(project.navigation.nodes),
                "navigation_edges": len(project.navigation.edges),
                "tree_digest": project.tree.digest,
            },
        )
        return project

    def evaluate_game_project(self, project):
        """Evaluate all seven deterministic project quality planes equally."""
        report = self.game_projects.evaluate(
            project
        )
        self._bus.emit(
            "jeeves.game_project.evaluated",
            {
                "era": project.era.value,
                "score": report.score,
                "runtime_score": report.runtime_score,
                "asset_score": report.asset_score,
                "script_score": report.script_score,
                "physics_score": report.physics_score,
                "audio_score": report.audio_score,
                "animation_score": report.animation_score,
                "navigation_score": report.navigation_score,
                "passed": report.passed,
                "failed": list(report.failed),
            },
        )
        return report

    def evolve_game_project(
        self,
        project,
        *,
        proposer=None,
        target: float = 1.0,
        max_rounds: int = 12,
        max_candidates: int = 32,
    ):
        """Adversarially improve a complete project without plane regressions."""
        from skeleton.jeeves.game_engine_project import (
            AdversarialGameProjectEvolution,
        )

        evolution = AdversarialGameProjectEvolution(
            self.game_projects
        )
        session = evolution.start(
            project
        )
        strategy = (
            proposer
            or evolution.canonical_candidates
        )
        result = evolution.evolve(
            session,
            strategy,
            target=target,
            max_rounds=max_rounds,
            max_candidates=max_candidates,
        )
        self._bus.emit(
            "jeeves.game_project.evolved",
            {
                "era": project.era.value,
                "target": target,
                "target_met": result.target_met,
                "rounds": len(result.rounds),
                "checkpoints": len(result.session.checkpoints),
                "tree_digest": result.session.sandbox.tree.digest,
            },
        )
        return result

    def package_game_project(
        self,
        project,
        *,
        require_quality: bool = True,
    ):
        """Create a deterministic hash-attested portable project package."""
        from skeleton.jeeves.game_engine_export import (
            build_project_package,
        )

        package = build_project_package(
            project,
            lab=self.game_projects,
            require_quality=require_quality,
        )
        self._bus.emit(
            "jeeves.game_project.packaged",
            {
                "era": project.era.value,
                "tree_digest": package.tree_digest,
                "package_digest": package.package_digest,
                "file_count": package.file_count,
                "total_bytes": package.total_bytes,
            },
        )
        return package

    def archive_game_project(
        self,
        project,
        *,
        require_quality: bool = True,
    ):
        """Emit deterministic portable ZIP bytes for a quality-gated project."""
        from skeleton.jeeves.game_engine_export import (
            archive_project_package,
        )

        package = self.package_game_project(
            project,
            require_quality=require_quality,
        )
        archive = archive_project_package(
            package
        )
        self._bus.emit(
            "jeeves.game_project.archived",
            {
                "era": project.era.value,
                "package_digest": package.package_digest,
                "archive_digest": archive.digest,
                "archive_bytes": len(archive.data),
            },
        )
        return archive

    def materialise_game_project(
        self,
        project,
        *,
        materialiser: str = "json",
        require_quality: bool = True,
    ) -> bytes:
        """Reuse Forge materialisers for a structured game-project export."""
        from skeleton.jeeves.game_engine_export import (
            materialise_project_package,
        )

        package = self.package_game_project(
            project,
            require_quality=require_quality,
        )
        data = materialise_project_package(
            package,
            materialiser=materialiser,
        )
        self._bus.emit(
            "jeeves.game_project.materialised",
            {
                "era": project.era.value,
                "package_digest": package.package_digest,
                "materialiser": materialiser,
                "bytes": len(data),
            },
        )
        return data

    def publish_game_project(
        self,
        project,
        lafs,
        *,
        name: str | None = None,
        chunk_bytes: int | None = None,
        require_quality: bool = True,
    ):
        """Publish a deterministic game-project archive through existing LAFS."""
        from skeleton.forge.lafs import CHUNK_MAX_BYTES
        from skeleton.jeeves.game_engine_export import (
            publish_project_package,
        )

        package = self.package_game_project(
            project,
            require_quality=require_quality,
        )
        publication = publish_project_package(
            package,
            lafs,
            name=name,
            chunk_bytes=(
                CHUNK_MAX_BYTES
                if chunk_bytes is None
                else chunk_bytes
            ),
        )
        self._bus.emit(
            "jeeves.game_project.published",
            {
                "era": project.era.value,
                "package_digest": package.package_digest,
                "archive_digest": publication.archive_digest,
                "manifest": publication.name,
                "chunks": len(publication.chunk_digests),
                "bytes": publication.total_bytes,
            },
        )
        return publication

    def compile_game_assets(self, sandbox, sources):
        """Compile deterministic era-constrained assets into a sandbox."""
        from skeleton.jeeves.game_engine_assets import (
            attach_asset_build,
            compile_asset_build,
        )

        source_values = tuple(sources)
        build = compile_asset_build(
            sandbox.era,
            source_values,
        )
        compiled = attach_asset_build(
            sandbox,
            source_values,
        )
        self._bus.emit(
            "jeeves.game_engine.assets_compiled",
            {
                "era": sandbox.era.value,
                "family": sandbox.family.value,
                "asset_count": len(build.assets),
                "manifest_digest": build.manifest_digest,
                "tree_digest": compiled.tree.digest,
            },
        )
        return compiled

    def evaluate_game_assets(self, sandbox, sources):
        """Validate compiled assets against their source recipes and era."""
        from skeleton.jeeves.game_engine_assets import AssetCompilerAdversary

        report = AssetCompilerAdversary().evaluate(
            sandbox,
            tuple(sources),
        )
        self._bus.emit(
            "jeeves.game_engine.assets_evaluated",
            {
                "era": sandbox.era.value,
                "score": report.score,
                "passed": report.passed,
                "failed": list(report.failed),
            },
        )
        return report

    def compile_game_scripts(self, sandbox, sources):
        """Compile bounded deterministic behavior programs into a sandbox."""
        from skeleton.jeeves.game_engine_scripts import (
            attach_script_build,
            compile_script_build,
        )

        source_values = tuple(sources)
        build = compile_script_build(
            sandbox.era,
            source_values,
        )
        compiled = attach_script_build(
            sandbox,
            source_values,
        )
        self._bus.emit(
            "jeeves.game_engine.scripts_compiled",
            {
                "era": sandbox.era.value,
                "family": sandbox.family.value,
                "script_count": len(build.scripts),
                "manifest_digest": build.manifest_digest,
                "tree_digest": compiled.tree.digest,
            },
        )
        return compiled

    def evaluate_game_scripts(self, sandbox, sources):
        """Validate compiled scripts, replay determinism, and gas bounds."""
        from skeleton.jeeves.game_engine_scripts import ScriptAdversary

        report = ScriptAdversary().evaluate(
            sandbox,
            tuple(sources),
        )
        self._bus.emit(
            "jeeves.game_engine.scripts_evaluated",
            {
                "era": sandbox.era.value,
                "score": report.score,
                "passed": report.passed,
                "failed": list(report.failed),
            },
        )
        return report

    def execute_game_script(
        self,
        sandbox,
        source,
        *,
        inputs=(),
        state=(),
    ):
        """Compile and execute one bounded behavior recipe in the era VM."""
        from skeleton.jeeves.game_engine_scripts import (
            EraScriptCompiler,
            ScriptVM,
        )

        compiled = EraScriptCompiler().compile(
            sandbox.era,
            source,
        )
        result = ScriptVM(
            sandbox.era
        ).run(
            compiled,
            inputs=tuple(inputs),
            state=tuple(state),
        )
        self._bus.emit(
            "jeeves.game_engine.script_executed",
            {
                "era": sandbox.era.value,
                "script_id": compiled.script_id,
                "steps": result.steps,
                "halted": result.halted,
                "exhausted": result.exhausted,
                "digest": result.digest,
            },
        )
        return result

    def compile_game_physics(self, sandbox, source):
        """Compile an era-constrained deterministic physics scene."""
        from skeleton.jeeves.game_engine_physics import (
            attach_physics_build,
            compile_physics_build,
        )

        build = compile_physics_build(
            sandbox.era,
            source,
        )
        compiled = attach_physics_build(
            sandbox,
            source,
        )
        self._bus.emit(
            "jeeves.game_engine.physics_compiled",
            {
                "era": sandbox.era.value,
                "family": sandbox.family.value,
                "source_digest": build.source_digest,
                "policy_digest": build.policy_digest,
                "manifest_digest": build.manifest_digest,
                "body_count": len(source.bodies),
                "constraint_count": len(source.constraints),
                "tree_digest": compiled.tree.digest,
            },
        )
        return compiled

    def evaluate_game_physics(self, sandbox, source):
        """Validate deterministic replay, contacts, snapshots, and constraints."""
        from skeleton.jeeves.game_engine_physics import PhysicsAdversary

        report = PhysicsAdversary().evaluate(
            sandbox,
            source,
        )
        self._bus.emit(
            "jeeves.game_engine.physics_evaluated",
            {
                "era": sandbox.era.value,
                "score": report.score,
                "passed": report.passed,
                "failed": list(report.failed),
            },
        )
        return report

    def simulate_game_physics(
        self,
        sandbox,
        source,
        *,
        steps: int = 1,
    ):
        """Compile a source scene into the era solver and advance fixed steps."""
        from skeleton.jeeves.game_engine_physics import world_from_source

        world = world_from_source(
            sandbox.era,
            source,
        )
        world.step(steps)
        self._bus.emit(
            "jeeves.game_engine.physics_simulated",
            {
                "era": sandbox.era.value,
                "steps": steps,
                "tick": world.tick,
                "body_count": len(world.bodies),
                "contacts": len(world.last_contacts),
                "fingerprint": world.fingerprint(),
            },
        )
        return world

    def compile_game_audio(self, sandbox, source):
        """Compile an era-constrained deterministic runtime audio scene."""
        from skeleton.jeeves.game_engine_audio import (
            attach_audio_build,
            compile_audio_build,
        )

        build = compile_audio_build(
            sandbox.era,
            source,
        )
        compiled = attach_audio_build(
            sandbox,
            source,
        )
        self._bus.emit(
            "jeeves.game_engine.audio_compiled",
            {
                "era": sandbox.era.value,
                "family": sandbox.family.value,
                "source_digest": build.source_digest,
                "policy_digest": build.policy_digest,
                "manifest_digest": build.manifest_digest,
                "sound_count": len(source.sounds),
                "tree_digest": compiled.tree.digest,
            },
        )
        return compiled

    def evaluate_game_audio(self, sandbox, source):
        """Validate replay, snapshot, voice budget, and spatial audio contracts."""
        from skeleton.jeeves.game_engine_audio import AudioAdversary

        report = AudioAdversary().evaluate(
            sandbox,
            source,
        )
        self._bus.emit(
            "jeeves.game_engine.audio_evaluated",
            {
                "era": sandbox.era.value,
                "score": report.score,
                "passed": report.passed,
                "failed": list(report.failed),
            },
        )
        return report

    def simulate_game_audio(
        self,
        sandbox,
        source,
        *,
        ticks: int = 32,
        schedule=None,
    ):
        """Run the deterministic era mixer without host audio side effects."""
        from skeleton.jeeves.game_engine_audio import HistoricalAudioMixer

        mixer = HistoricalAudioMixer(
            sandbox.era,
            listener=source.listener,
        )
        active_schedule = (
            schedule
            if schedule is not None
            else {
                index * 3: (sound,)
                for index, sound
                in enumerate(source.sounds)
            }
        )
        frames = mixer.run(
            active_schedule,
            ticks,
        )
        self._bus.emit(
            "jeeves.game_engine.audio_simulated",
            {
                "era": sandbox.era.value,
                "ticks": ticks,
                "frames": len(frames),
                "active_voices": len(mixer.voices),
                "fingerprint": mixer.fingerprint(),
            },
        )
        return frames, mixer

    def compile_game_animation(self, sandbox, source):
        """Compile bounded era-specific animation data into a sandbox."""
        from skeleton.jeeves.game_engine_animation import (
            attach_animation_build,
            compile_animation_build,
        )

        build = compile_animation_build(
            sandbox.era,
            source,
        )
        compiled = attach_animation_build(
            sandbox,
            source,
        )
        self._bus.emit(
            "jeeves.game_engine.animation_compiled",
            {
                "era": sandbox.era.value,
                "family": sandbox.family.value,
                "clip_count": len(build.clips),
                "source_digest": build.source_digest,
                "policy_digest": build.policy_digest,
                "manifest_digest": build.manifest_digest,
                "tree_digest": compiled.tree.digest,
            },
        )
        return compiled

    def evaluate_game_animation(self, sandbox, source):
        """Validate animation replay, snapshots, blending, root motion, and IK."""
        from skeleton.jeeves.game_engine_animation import AnimationAdversary

        report = AnimationAdversary().evaluate(
            sandbox,
            source,
        )
        self._bus.emit(
            "jeeves.game_engine.animation_evaluated",
            {
                "era": sandbox.era.value,
                "score": report.score,
                "passed": report.passed,
                "failed": list(report.failed),
            },
        )
        return report

    def simulate_game_animation(
        self,
        sandbox,
        source,
        *,
        clip_id=None,
        steps: int = 32,
        playback_rate: float = 1.0,
    ):
        """Run fixed-tick deterministic animation playback without host timing."""
        from skeleton.jeeves.game_engine_animation import HistoricalAnimator

        animator = HistoricalAnimator(
            sandbox.era,
            source,
        )
        if clip_id is not None:
            animator.play(
                clip_id,
                playback_rate=playback_rate,
            )
        poses = animator.step(
            steps
        )
        self._bus.emit(
            "jeeves.game_engine.animation_simulated",
            {
                "era": sandbox.era.value,
                "steps": steps,
                "poses": len(poses),
                "clip_id": animator.clip_id,
                "fingerprint": animator.fingerprint(),
            },
        )
        return poses, animator

    def evaluate_game_engine(self, sandbox):
        """Run the era-specific adversarial quality suite."""
        report = self.game_engines.evaluate(sandbox)
        self._bus.emit(
            "jeeves.game_engine.evaluated",
            {
                "era": sandbox.era.value,
                "family": sandbox.family.value,
                "score": report.score,
                "passed": report.passed,
                "failed": list(report.failed),
            },
        )
        return report

    def evolve_game_engine(
        self,
        sandbox,
        *,
        proposer=None,
        target: float = 1.0,
        max_rounds: int = 12,
        max_candidates: int = 32,
    ):
        """Snapshot and adversarially improve a sandbox until its gate passes."""
        from skeleton.jeeves.game_engine_runtime import AdversarialEngineEvolution

        evolution = AdversarialEngineEvolution(self.game_engines)
        session = evolution.start(sandbox)
        strategy = proposer or evolution.canonical_candidates
        result = evolution.evolve(
            session,
            strategy,
            target=target,
            max_rounds=max_rounds,
            max_candidates=max_candidates,
        )
        self._bus.emit(
            "jeeves.game_engine.evolved",
            {
                "era": sandbox.era.value,
                "family": sandbox.family.value,
                "target": target,
                "target_met": result.target_met,
                "rounds": len(result.rounds),
                "checkpoints": len(result.session.checkpoints),
                "tree_digest": result.session.sandbox.tree.digest,
            },
        )
        return result

    def _brain_get(self):
        if self._brain is None:
            from skeleton.jeeves.tactical import TacticalBrain
            self._brain = TacticalBrain(self.era)
        return self._brain

    @property
    def cortex(self):
        if self._cortex is None:
            from skeleton.cortex import JeevesCortex
            self._cortex = JeevesCortex(bus=self._bus)
        return self._cortex

    @cortex.setter
    def cortex(self, value) -> None:
        self._cortex = value

    def refer(self, stimulus: str, *, live: bool = False):
        return self.cortex.refer(stimulus, live=live)

    def improve(self, stimulus: str, *, rounds: int = 16):
        return self.cortex.improve(stimulus, rounds=rounds)

    def ascend(self, stimulus: str, *, rounds: int = 8):
        return self.cortex.ascend(stimulus, rounds=rounds)

    def think(self, stimulus: str, *, context: dict[str, Any] | None = None):
        """Neocortex think — the model in training, not a chat wrapper."""
        if not _cortex_can_think(self._cortex):
            # Observability stub: fall back to local hemispheres (BuilderBrain path).
            from skeleton.cortex.hemispheres import LeftHemisphere, RightHemisphere
            from skeleton.cortex.pfc import PrefrontalCortex
            ctx = context or {}
            left = LeftHemisphere().think(stimulus, ctx)
            right = RightHemisphere().think(stimulus, {**ctx, "left": left.to_dict()})
            pfc = PrefrontalCortex().think(
                stimulus, {**ctx, "left": left.to_dict(), "right": right.to_dict()}
            )
            from types import SimpleNamespace
            trace = SimpleNamespace(
                left=left, right=right, pfc=pfc, used_own=False, amalgam=None,
                to_dict=lambda: {
                    "left": left.to_dict(), "right": right.to_dict(), "pfc": pfc.to_dict(),
                },
            )
            self._bus.emit("jeeves.cortex.thought", {
                "stimulus": stimulus[:120], "fallback": "local",
            })
            return trace
        trace = self.cortex.think(stimulus, context)
        self._bus.emit("jeeves.cortex.thought", {
            "fp": trace.fingerprint, "used_own": trace.used_own,
            "hive": trace.hive_value,
        })
        return trace

    def bind_model(self, slot: str, backend=None, *, echo: bool = False, local: bool = False):
        if echo:
            return self.cortex.bind_echo(slot)
        if local or backend is None:
            return self.cortex.bind_local(slot)
        return self.cortex.bind(slot, backend)

    def acquire(self, slot: str) -> dict[str, Any]:
        out = self.cortex.acquire(slot)
        self._bus.emit("jeeves.cortex.acquired", out)
        return out

    def surpass(self, slot: str) -> dict[str, Any]:
        out = self.cortex.surpass(slot)
        self._bus.emit("jeeves.cortex.surpass", out)
        return out

    def recall(self, stimulus: str) -> dict[str, Any]:
        return self.cortex.recall(stimulus)

    def export_tract(self, slot: str) -> dict[str, Any]:
        out = self.cortex.export_tract(slot)
        self._bus.emit("jeeves.cortex.export", {"slot": slot, "size": out.get("size")})
        return out

    def import_tract(self, payload: dict[str, Any]) -> dict[str, Any]:
        out = self.cortex.import_tract(payload)
        self._bus.emit("jeeves.cortex.import", out)
        return out

    def train(self, *, epochs: int = 1) -> dict[str, Any]:
        out = self.cortex.train(epochs=epochs)
        self._bus.emit("jeeves.cortex.trained", {
            "epochs": out.get("epochs"), "held_rate": out.get("held_rate"),
        })
        return out

    def observe_run(self, *, era: str, walk: dict[str, Any], plan: dict[str, Any],
                    vision: str = "") -> dict[str, Any]:
        """Ingest a finished forge-run so own-system can recall extract outcomes."""
        extracted = bool((walk or {}).get("extracted"))
        collapsed = bool((walk or {}).get("collapsed"))
        hops = (walk or {}).get("hops")
        cores = (walk or {}).get("cores")
        bias = (plan or {}).get("room_bias") or "balanced"
        mix = (plan or {}).get("enemy_mix") or {}
        trash = float(mix.get("trash") or 0)
        elite = float(mix.get("elite") or 0)
        boss = float(mix.get("boss") or 0)
        t = float((walk or {}).get("t") or 0)
        collapse = float((walk or {}).get("collapse_max") or 0)
        slack = ((collapse - t) / collapse) if (extracted and collapse > 0 and t > 0) else (
            0.0 if (collapsed or not extracted) else 1.0
        )
        self.last_walk = dict(walk or {})
        self.last_walk["era"] = era
        self.last_walk["bias"] = bias
        self.last_walk["slack"] = slack
        ref = None
        try:
            ref = self.refer(vision or era or "")
        except Exception:
            ref = None
        if ref and ref.get("hit"):
            self.last_walk["reference"] = (ref.get("ref") or {}).get("title")
            era = era or str((ref.get("ref") or {}).get("era") or era)
        stim = (
            f"forge run {era} {vision} extract {extracted} "
            f"hops {hops} cores {cores} bias {bias}"
        )
        trace = self.think(stim, context={"walk": walk, "plan": plan, "era": era, "reference": (ref or {}).get("ref")})
        from skeleton.cortex.distill import ability_from
        from skeleton.cortex.port import Thought
        observed = Thought(
            slot="left", kind="walk",
            text=(
                f"HP = DPS × TTK ; observed mix trash={int(trash)} "
                f"elite={int(elite)} boss={int(boss)} slack={slack:.2f}"
            ),
            confidence=min(1.0, 0.55 + 0.45 * max(0.0, slack)),
            tags=("analytic", "mix", "walk", "observed", "left", str(era)),
            numbers=(trash, elite, boss, slack),
        )
        self.cortex.own.ingest(ability_from(observed, stim), stim)
        spawn = bool((plan or {}).get("spawn_weapon"))
        late = bool((plan or {}).get("extract_late"))
        bias_thought = Thought(
            slot="right", kind="walk",
            text=f"bias={bias} slack={slack:.2f}",
            confidence=min(1.0, 0.55 + 0.45 * max(0.0, slack)),
            tags=("gestalt", "spatial", "right", "observed", "bias", str(bias), str(era)),
            numbers=(slack,),
        )
        self.cortex.own.ingest(ability_from(bias_thought, stim), stim)
        policy_thought = Thought(
            slot="pfc", kind="plan",
            text=f"armed={int(spawn)} late={int(late)} slack={slack:.2f}",
            confidence=min(1.0, 0.55 + 0.45 * max(0.0, slack)),
            tags=("plan", "boilerplate", "observed", "policy", "pfc", str(era)),
            numbers=(float(spawn), float(late), slack),
        )
        self.cortex.own.ingest(ability_from(policy_thought, stim), stim)
        self._bus.emit("jeeves.observe_run", {
            "era": era, "extracted": extracted, "own": self.cortex.own.size,
        })
        card = trace.to_dict()
        cite = url = None
        if ref and ref.get("hit"):
            r = ref.get("ref") or {}
            cite = r.get("citation")
            url = r.get("url")
        return {
            **card,
            "G": round(float(card.get("G") or getattr(getattr(self.cortex, "genos_engine", None), "G", 1.0) or 1.0), 6),
            "law": card.get("law") or "ok",
            "citation": cite,
            "url": url,
            "stored_prose": 0,
            "extracted": extracted,
            "era": era,
        }

    def bind_pack(self, pack: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(pack, dict):
            raise TypeError("pack must be an object")
        # A compiled blend carries a synthetic era id such as
        # "arcade_golden_age~soulslike@0.50". Lazy TacticalBrain creation
        # must not try to recompile that synthetic id as a catalog era.
        # Create the brain from the current canonical default first, then
        # bind the already-compiled authoritative pack.
        brain = self._brain_get()
        pack = brain.bind_pack(pack)
        self.era = str(pack.get("era") or self.era)
        self._bus.emit("jeeves.era.bound", {"era": pack["era"], "dps": pack["primary_dps"]})
        return pack

    def bind_era(self, era: str) -> dict[str, Any]:
        from skeleton.cortex.era_bind import resolve
        raw = era or self.era
        card = resolve(raw)
        pack = card.get("pack")
        if pack is None:
            from skeleton.forge.eras import compile_era
            pack = compile_era(card.get("era") or raw)
        bound = self.bind_pack(pack)
        bound["citation"] = card.get("citation")
        bound["title"] = card.get("title")
        bound["stored_prose"] = 0
        bound["ref_era"] = card.get("ref_era")
        return bound

    def plan_build(self, pack: dict[str, Any] | None = None, *,
                   tensor=None, reading=None, vision: str = "") -> dict[str, Any]:
        """Jeeves-as-builder: design the run the forge will emit."""
        from skeleton.jeeves.builder import BuilderBrain
        if vision:
            pack = self.bind_era(vision)
        if pack is None:
            from skeleton.forge.eras import compile_era
            pack = compile_era(self.era)
        cx = self._cortex if _cortex_can_think(self._cortex) else None
        plan = BuilderBrain().plan(
            pack, tensor=tensor, reading=reading,
            cortex=cx, last_walk=self.last_walk,
        )
        self.last_plan = plan
        self._bus.emit("jeeves.build.planned", {
            "era": plan.era, "seed": plan.seed, "bias": plan.room_bias,
        })
        out = plan.to_dict()
        if vision:
            from skeleton.cortex.era_bind import resolve
            card = resolve(vision)
            if card.get("hit"):
                out["reference"] = card.get("title")
                out["citation"] = card.get("citation")
                out["url"] = card.get("url")
            out["era"] = card.get("era") or out.get("era")
            out["stored_prose"] = 0
            out["law"] = "ok"
        return out

    def advise(self, session_id: str, telemetry: dict[str, Any] | None = None) -> dict[str, Any]:
        """Tactical cascade. Opens nothing; uses bound era + live telemetry."""
        session = self._get(session_id)
        self._ensure_turn_capacity(session, 1)
        brain = self._brain_get()
        advice = brain.advise(telemetry or {})
        top = advice[0]
        session.add_turn("jeeves", top.text)
        self._bus.emit("jeeves.advice.issued",
                       {"session_id": session_id, "priority": top.priority, "axis": top.axis})
        return {
            "era": brain.era,
            "world": brain.observe(telemetry or {}).to_dict(),
            "advice": [a.to_dict() for a in advice],
            "next": top.to_dict(),
        }

    def _get(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionError("unknown session", context={"session_id": session_id})
        return session


# CI-1 compatibility: pipeline and older imports expect JeevesCore from this module.
# Keep this at module scope so the tutor Jeeves remains the canonical implementation.
JeevesCore = Jeeves
