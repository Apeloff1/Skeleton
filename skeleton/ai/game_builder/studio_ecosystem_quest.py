"""Deterministic, causal quest-playthrough simulator for original studio briefs.

This executes stage unlocking and authored choices against both studio source
formats; it does NOT simulate physics, cinematics, real witnesses, actual
resource supply, or game-engine genre mechanics. Unobserved evidence is never
minted by authoring a choice. Results are sandbox-only and never release proof.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence


class StudioQuestError(ValueError):
    """An invalid authored graph, session, or action."""


def _digest(value: object) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise StudioQuestError("invalid canonical quest input") from exc
    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class QuestStage:
    key: str
    prerequisites: tuple[str, ...]
    alternatives: tuple[str, ...]
    reward: str


@dataclass(frozen=True, slots=True)
class QuestProgram:
    project_id: str
    source_digest: str
    stages: tuple[QuestStage, ...]
    endings: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def stage_ids(self) -> tuple[str, ...]:
        return tuple(s.key for s in self.stages)


@dataclass(frozen=True, slots=True)
class QuestSession:
    project_id: str
    source_digest: str
    choices: tuple[tuple[str, str], ...]
    completed: tuple[str, ...]
    digest: str

    def receipt(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.studio_quest_session.v1",
            "project_id": self.project_id,
            "source_digest": self.source_digest,
            "choices": [list(pair) for pair in self.choices],
            "completed": list(self.completed),
            "session_digest": self.digest,
            "external_evidence_verified": False,
            "native_genre_runtime_verified": False,
            "release_certified": False,
        }


def _require_text(value: object, kind: str) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 256
            or value.strip() != value or any(ord(c) < 32 for c in value)):
        raise StudioQuestError("invalid " + kind)
    return value


def compile_quest_program(documents: Mapping[str, Any]) -> QuestProgram:
    """Validate the authored DAG and freeze the exact source contract."""
    if not isinstance(documents, Mapping):
        raise StudioQuestError("missing authoritative documents")
    quest = documents.get("quest")
    narrative = documents.get("narrative")
    if not isinstance(quest, dict) or not isinstance(narrative, dict):
        raise StudioQuestError("quest and narrative sections required")
    pid = _require_text(quest.get("project_id"), "project ID")
    if narrative.get("project_id") != pid:
        raise StudioQuestError("cross-section project ID mismatch")
    if quest.get("release_certified") is not False or narrative.get("release_certified") is not False:
        raise StudioQuestError("unearned release certification")
    primary = quest.get("stage_graph")
    legacy = quest.get("stages")
    if bool(primary) == bool(legacy):
        raise StudioQuestError("exactly one authored stage graph required")
    source = primary if primary else legacy
    if not isinstance(source, list) or not 1 <= len(source) <= 64:
        raise StudioQuestError("invalid quest stage count")
    stages: list[QuestStage] = []
    seen: set[str] = set()
    for position, item in enumerate(source):
        if not isinstance(item, dict):
            raise StudioQuestError("invalid stage record")
        key = _require_text(item.get("id"), "stage ID")
        if key in seen:
            raise StudioQuestError("repeated stage ID")
        if primary:
            if "prerequisites" in item:
                if "entry" in item:
                    raise StudioQuestError("mixed entry and prerequisite contracts")
                deps = item["prerequisites"]
            elif "entry" in item:
                # The original wave-1 corpus spells the sequential dependency
                # as new_game / <previous_stage>_complete, not prerequisites.
                expected = "new_game" if position == 0 else stages[-1].key + "_complete"
                if item["entry"] != expected:
                    raise StudioQuestError("authored entry does not match causal order")
                deps = [] if position == 0 else [stages[-1].key]
            else:
                raise StudioQuestError("missing authored stage dependency contract")
        else:
            deps = [stages[-1].key] if stages else []
        if (not isinstance(deps, list) or len(deps) > 64
                or any(not isinstance(dep, str) for dep in deps)):
            raise StudioQuestError("invalid stage prerequisites")
        requirements = tuple(_require_text(dep, "prerequisite") for dep in deps)
        if len(set(requirements)) != len(requirements):
            raise StudioQuestError("duplicate prerequisites")
        choices = item.get("alternatives")
        if (not isinstance(choices, list) or not 1 <= len(choices) <= 8
                or any(not isinstance(c, str) for c in choices)):
            raise StudioQuestError("missing authored choices")
        options = tuple(_require_text(c, "alternative") for c in choices)
        if len(set(options)) != len(options):
            raise StudioQuestError("repeated alternative")
        reward = _require_text(item.get("reward"), "stage reward")
        seen.add(key)
        stages.append(QuestStage(key, requirements, options, reward))
    # The stage graph is deliberately topologically ordered. Cycles and
    # forward references fail instead of producing non-terminating gameplay.
    built: set[str] = set()
    for stage in stages:
        if not set(stage.prerequisites).issubset(built):
            raise StudioQuestError("unreachable, cyclic or forward-linked quest stage")
        built.add(stage.key)
    if not isinstance(narrative.get("endings"), list) or not narrative["endings"]:
        raise StudioQuestError("missing authored endings")
    endings: list[tuple[str, tuple[str, ...]]] = []
    ending_keys: set[str] = set()
    for ending in narrative["endings"]:
        if not isinstance(ending, dict):
            raise StudioQuestError("invalid ending")
        key = _require_text(ending.get("id"), "ending ID")
        raw = ending.get("requires")
        requires = [raw] if isinstance(raw, str) else raw
        if (key in ending_keys or not isinstance(requires, list)
                or not 1 <= len(requires) <= 16):
            raise StudioQuestError("invalid or repeated ending requirements")
        required = tuple(_require_text(x, "ending requirement") for x in requires)
        if len(set(required)) != len(required):
            raise StudioQuestError("duplicate ending predicate")
        endings.append((key, required))
        ending_keys.add(key)
    return QuestProgram(pid, _digest({"quest": quest, "narrative": narrative}),
                        tuple(stages), tuple(endings))


def _state(program: QuestProgram, choices: tuple[tuple[str, str], ...]) -> QuestSession:
    completed = tuple(stage for stage, _ in choices)
    payload = {"project_id": program.project_id,
               "source_digest": program.source_digest,
               "choices": choices, "completed": completed}
    return QuestSession(program.project_id, program.source_digest, choices,
                        completed, _digest(payload))


def start_quest(documents: Mapping[str, Any], *, authorized: bool) -> QuestSession:
    if not authorized:
        raise PermissionError("studio quest run requires operator authorization")
    return _state(compile_quest_program(documents), ())


def available_stages(session: QuestSession, documents: Mapping[str, Any]) -> tuple[str, ...]:
    program = compile_quest_program(documents)
    verify_quest_session(session, documents, program=program)
    complete = set(session.completed)
    return tuple(stage.key for stage in program.stages
                 if stage.key not in complete and set(stage.prerequisites).issubset(complete))


def step_quest(session: QuestSession, documents: Mapping[str, Any], *,
               stage: str, alternative: str, authorized: bool) -> QuestSession:
    if not authorized:
        raise PermissionError("studio quest step requires operator authorization")
    program = compile_quest_program(documents)
    verify_quest_session(session, documents, program=program)
    stage_def = next((x for x in program.stages if x.key == stage), None)
    if stage_def is None or alternative not in stage_def.alternatives:
        raise StudioQuestError("action is not an authored alternative")
    done = set(session.completed)
    if stage in done or not set(stage_def.prerequisites).issubset(done):
        raise StudioQuestError("stage locked or already completed")
    return _state(program, session.choices + ((stage, alternative),))


def verify_quest_session(session: QuestSession, documents: Mapping[str, Any],
                         *, program: QuestProgram | None = None) -> None:
    """Replay every choice, without relying on mutable cached state."""
    if not isinstance(session, QuestSession):
        raise StudioQuestError("invalid quest session type")
    program = program or compile_quest_program(documents)
    if (session.project_id != program.project_id
            or session.source_digest != program.source_digest
            or len(session.choices) > len(program.stages)):
        raise StudioQuestError("session source/length mismatch")
    complete: set[str] = set()
    for key, choice in session.choices:
        stage = next((s for s in program.stages if s.key == key), None)
        if (stage is None or key in complete or choice not in stage.alternatives
                or not set(stage.prerequisites).issubset(complete)):
            raise StudioQuestError("session contains illegal history")
        complete.add(key)
    if session != _state(program, session.choices):
        raise StudioQuestError("session state or digest differs from replay")


def quest_progress(session: QuestSession, documents: Mapping[str, Any]) -> dict[str, object]:
    """Return executable stage progress; no false environmental evidence."""
    program = compile_quest_program(documents)
    verify_quest_session(session, documents, program=program)
    done = set(session.completed)
    # Stage IDs and their explicitly awarded tokens are *simulation* tokens.
    # Unfulfilled narrative requirements remain unresolved. No forged proof.
    facts = done | {s.reward for s in program.stages if s.key in done}
    reachable = [key for key, requirements in program.endings
                 if set(requirements).issubset(facts)]
    missing = {key: sorted(set(reqs) - facts)
               for key, reqs in program.endings if not set(reqs).issubset(facts)}
    return {
        "schema": "skeleton.game_builder.studio_quest_progress.v1",
        "project_id": session.project_id,
        "stage_total": len(program.stages),
        "stage_completed": len(done),
        "available": list(available_stages(session, documents)),
        "sandbox_endings_eligible": reachable,
        "unmet_ending_predicates": missing,
        "session_digest": session.digest,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }


def replay_quest(documents: Mapping[str, Any], actions: Sequence[tuple[str, str]],
                 *, authorized: bool) -> QuestSession:
    if not authorized:
        raise PermissionError("studio quest replay requires operator authorization")
    if not isinstance(actions, (list, tuple)) or len(actions) > 64:
        raise StudioQuestError("invalid bounded replay")
    session = start_quest(documents, authorized=True)
    for pair in actions:
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                or not all(isinstance(p, str) for p in pair)):
            raise StudioQuestError("invalid replay action")
        session = step_quest(session, documents, stage=pair[0],
                             alternative=pair[1], authorized=True)
    return session


def start_catalog_quest(project_id: str, *, authorized: bool) -> tuple[dict[str, dict[str, Any]], QuestSession]:
    """Only the registered studio catalog may supply the authored source."""
    if not authorized:
        raise PermissionError("studio quest load requires authorization")
    from .studio_ecosystem_catalog import read_blueprint
    documents = read_blueprint(project_id)
    return documents, start_quest(documents, authorized=True)
