"""Jeeves' native-first, audited game-studio interaction and delegation plane.

All 38 studio facets share the EXISTING typed creator command contract.
The model proposes; the human confirms; the host's ToolExecutor acts. This
module cannot mint grants or claim a successful effect from generated text.
Questionnaires, model deliberations, multimodal references and execution
outcomes have durable hash-linked receipts.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Any

from skeleton.forge.creator.command_surface import build_creator_command
from skeleton.jeeves.ai.creator_runbook_runtime import (
    CreatorRunbook, CreatorRunbookRunner, RunbookState,
)
from skeleton.jeeves.ai.creator_runbook_store import CreatorRunbookStore
from skeleton.jeeves.agent.tools import ToolExecutor

SCHEMA = "jeeves.studio_interaction.v1"
MAX_EVENT_BYTES = 192 * 1024
MAX_EVENTS = 100_000
MAX_STEPS = 32
ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:@+-]{0,127}$")
HEX = re.compile(r"^[a-f0-9]{64}$")

FACETS: dict[str, tuple[str, str]] = {
    "vision": ("What is the game's distinctive fantasy and player promise?", "design"),
    "platform": ("Which platforms, eras, SDKs and resource profiles matter?", "engineering"),
    "engine": ("What runtime, engine and renderer will ship?", "engineering"),
    "scope": ("What are the actual completion criteria and priorities?", "production"),
    "canon": ("Which lore and continuity rules must never break?", "narrative"),
    "world": ("Which worlds, biomes, regions and sky/underworld layers exist?", "world"),
    "map": ("What are the topology, geography and navigational affordances?", "world"),
    "pathing": ("Which routes, transport and alternate paths are possible?", "world"),
    "story": ("Which arcs, acts, scenes and endings define the experience?", "narrative"),
    "dialogue": ("Which dialogue branches can alter future outcomes?", "narrative"),
    "cast": ("Which character histories and visual anchors define the cast?", "narrative"),
    "npc": ("What are NPC needs, schedules, agency and interactions?", "simulation"),
    "quests": ("What are quest dependencies, rewards and failure alternatives?", "design"),
    "combat": ("What are combat loops, effects and tactical constraints?", "design"),
    "movement": ("What are traversal dynamics and camera controls?", "simulation"),
    "physics": ("Which contact, momentum, traction and environmental forces apply?", "simulation"),
    "weather": ("How do wind, rain, turbulence, updraft and seasons behave?", "simulation"),
    "economy": ("How do items, crafting, scarcity and trade interact?", "design"),
    "inventory": ("Which inventory, equipment and weight systems exist?", "design"),
    "progression": ("How do skills, factions and reputation evolve?", "design"),
    "puzzles": ("Which puzzles support multiple valid solutions?", "design"),
    "multiplayer": ("Which synchronization, authority and lobby rules apply?", "engineering"),
    "accessibility": ("Which input, visual, audio and cognitive options ship?", "quality"),
    "localization": ("Which languages, cultural and formatting needs apply?", "quality"),
    "ui": ("Which screens, menus, HUD and input mappings must work?", "interface"),
    "ux": ("Which interaction flows, tutorials and usability measures apply?", "interface"),
    "sprite_forge": ("Which sprite sheets, animation states and palettes are needed?", "forge"),
    "asset_forge": ("Which original meshes, materials and props are needed?", "forge"),
    "scene_forge": ("Which scene graphs, triggers and transitions are needed?", "forge"),
    "animation_forge": ("Which rigs, poses, transitions and timing curves apply?", "forge"),
    "audio_forge": ("Which music, ambience, effects and mixing states apply?", "forge"),
    "lighting_forge": ("Which shadows, lighting and environmental passes apply?", "forge"),
    "cinematics": ("Which camera tracks, shot language and cutscenes apply?", "forge"),
    "playtest": ("Which gameplay paths and engine evidence must be reproduced?", "quality"),
    "qa": ("Which syntactic, functional and adversarial gates must pass?", "quality"),
    "training": ("What original, licensed or public-domain sources may improve Jeeves?", "ai"),
    "delegation": ("Which tasks need specialist tools and approval?", "ai"),
    "release": ("Which packaging, provenance and distribution targets apply?", "production"),
}


class StudioInteractionError(ValueError):
    """Invalid or unauthorized studio transition."""


def canonical(value: object) -> bytes:
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise StudioInteractionError("studio evidence must be finite canonical JSON") from exc
    if len(data) > MAX_EVENT_BYTES:
        raise StudioInteractionError("studio evidence exceeds event size")
    return data


def digest(value: object) -> str:
    return sha256(canonical(value)).hexdigest()


def identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise StudioInteractionError(f"invalid {label} identifier")
    return value


def questions(*, group: str | None = None) -> tuple[dict[str, str], ...]:
    """Use the same question contract in chat, Galaxy Studio and CLI."""
    return tuple({"facet": facet, "group": kind, "question": question}
                 for facet, (question, kind) in FACETS.items()
                 if group is None or group == kind)


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    d: dict[str, object] = {}
    for k, v in items:
        if k in d:
            raise StudioInteractionError("duplicate JSON field in journal")
        d[k] = v
    return d


@dataclass(frozen=True, slots=True)
class StudioProposal:
    facet: str
    operation: str
    payload: Mapping[str, Any]
    after: tuple[str, ...] = ()
    modality_refs: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.facet not in FACETS:
            raise StudioInteractionError("unknown game production facet")
        if self.operation not in ("create", "edit", "test", "preview", "export"):
            raise StudioInteractionError("operation not supported by creator surface")
        if not isinstance(self.payload, Mapping):
            raise StudioInteractionError("creator payload must be a mapping")
        canonical(dict(self.payload))
        for name, refs in (("dependency", self.after), ("modality", self.modality_refs),
                           ("source", self.source_refs)):
            if len(refs) > 32 or len(set(refs)) != len(refs):
                raise StudioInteractionError(f"invalid {name} references")
            for ref in refs:
                identifier(ref, name)


class StudioEvidenceJournal:
    """Append-only SQLite journal: every observation links to prior history.

    No caller-supplied success flags: only an observed Runner status with a
    validated downstream receipt can create an execution_succeeded record.
    """

    EVENTS = frozenset((
        "question_answered", "modality_registered", "model_inference_observed", "model_proposed",
        "plan_compiled", "plan_approved", "execution_succeeded",
        "execution_uncertain", "execution_aborted",
    ))

    def __init__(self, path: Path | str, *, project_id: str, session_id: str):
        self.project_id = identifier(project_id, "project")
        self.session_id = identifier(session_id, "session")
        self.path = Path(path)
        if not self.path.is_absolute() or self.path.is_symlink():
            raise StudioInteractionError("journal needs an absolute non-symlink path")
        self._lock = RLock()
        self._db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None,
                                   check_same_thread=False)
        self._db.execute("PRAGMA busy_timeout=10000")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("""CREATE TABLE IF NOT EXISTS studio_event (
            sequence INTEGER PRIMARY KEY, project_id TEXT NOT NULL,
            session_id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
            previous TEXT, digest TEXT NOT NULL UNIQUE)""")
        self.read()

    def read(self) -> tuple[dict[str, Any], ...]:
        """Verify complete ancestry (including identities), reject corruption."""
        with self._lock:
            prev: str | None = None
            out: list[dict[str, Any]] = []
            for seq, project, session, kind, payload, prior, head in self._db.execute(
                "SELECT sequence,project_id,session_id,kind,payload,previous,digest "
                "FROM studio_event ORDER BY sequence"
            ):
                if (seq != len(out) or seq >= MAX_EVENTS or project != self.project_id
                        or session != self.session_id or kind not in self.EVENTS
                        or prior != prev or not isinstance(payload, str)
                        or len(payload.encode("utf-8")) > MAX_EVENT_BYTES):
                    raise StudioInteractionError("studio receipt chain or ownership differs")
                try:
                    value = json.loads(payload, object_pairs_hook=_pairs,
                                       parse_constant=lambda x: (_ for _ in ()).throw(
                                           StudioInteractionError("nonfinite journal number")))
                except (ValueError, TypeError, UnicodeError) as exc:
                    raise StudioInteractionError("invalid persisted studio receipt") from exc
                row = {"schema": SCHEMA, "sequence": seq, "project_id": project,
                       "session_id": session, "kind": kind, "payload": value,
                       "previous": prior}
                if not isinstance(head, str) or not HEX.fullmatch(head) or digest(row) != head:
                    raise StudioInteractionError("studio event content hash mismatch")
                row["digest"] = head
                out.append(row)
                prev = head
            return tuple(out)

    def append(self, kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if kind not in self.EVENTS:
            raise StudioInteractionError("unsupported studio event")
        body = dict(payload)
        canonical(body)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                rows = self.read()
                sequence = len(rows)
                if sequence >= MAX_EVENTS:
                    raise StudioInteractionError("journal needs archival before more work")
                event = {
                    "schema": SCHEMA, "sequence": sequence,
                    "project_id": self.project_id, "session_id": self.session_id,
                    "kind": kind, "payload": body,
                    "previous": rows[-1]["digest"] if rows else None,
                }
                head = digest(event)
                self._db.execute("INSERT INTO studio_event VALUES (?,?,?,?,?,?,?)", (
                    sequence, self.project_id, self.session_id, kind,
                    canonical(body).decode("utf-8"), event["previous"], head,
                ))
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
            return {**event, "digest": head}

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "StudioEvidenceJournal":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class JeevesStudioController:
    """Native model -> reviewed proposal -> host-authorized CreatorRunbook."""

    def __init__(self, journal: StudioEvidenceJournal) -> None:
        self.journal = journal

    def answer(self, facet: str, value: str, *, actor_id: str) -> dict[str, Any]:
        if facet not in FACETS or not isinstance(value, str) or not 1 <= len(value) <= 8192:
            raise StudioInteractionError("questionnaire answer missing or invalid")
        return self.journal.append("question_answered", {
            "facet": facet, "answer": value, "actor_id": identifier(actor_id, "actor"),
        })

    def attach(self, *, modality: str, artifact_digest: str, source_id: str,
               rights_scope: str) -> dict[str, Any]:
        if modality not in ("image", "video", "audio", "text", "3d", "scene", "motion"):
            raise StudioInteractionError("unrecognized multimodal source type")
        if not HEX.fullmatch(artifact_digest):
            raise StudioInteractionError("external attachment needs a real SHA256")
        identifier(source_id, "source")
        if rights_scope not in ("original", "licensed", "public_domain", "reference_only"):
            raise StudioInteractionError("unreviewed attachment rights")
        return self.journal.append("modality_registered", {
            "modality": modality, "artifact_sha256": artifact_digest,
            "source_id": source_id, "rights_scope": rights_scope,
            "model_weights_modified": False,
        })

    def propose(self, proposals: Sequence[StudioProposal], *,
                model_checkpoint_sha256: str, actor_id: str = "jeeves") -> dict[str, Any]:
        if not HEX.fullmatch(model_checkpoint_sha256):
            raise StudioInteractionError("proposal needs a real local checkpoint digest")
        if not 1 <= len(proposals) <= MAX_STEPS:
            raise StudioInteractionError("proposal batch outside runbook limits")
        identifier(actor_id, "agent")
        steps: list[dict[str, Any]] = []
        for index, p in enumerate(proposals):
            if not isinstance(p, StudioProposal):
                raise StudioInteractionError("typed proposal required")
            step_id = f"step-{index:03d}"
            if any(dep not in {s["step_id"] for s in steps} for dep in p.after):
                raise StudioInteractionError("dependencies must precede the action")
            command = build_creator_command(
                p.operation, project_id=self.journal.project_id, payload=dict(p.payload)
            )
            steps.append({
                "index": index, "step_id": step_id, "after": list(p.after),
                "command": command.to_dict(), "dispatch_performed": False,
            })
        plan = {"kind": "creator-plan", "project_id": self.journal.project_id,
                "execution_authority": "none", "dispatch_performed": False,
                "steps": steps, "plan_sha256": digest(steps)}
        CreatorRunbook(plan)  # validate against the real executor contract
        self.journal.append("model_proposed", {
            "model_checkpoint_sha256": model_checkpoint_sha256,
            "model_id": actor_id, "proposal_facets": [p.facet for p in proposals],
            "source_refs": [list(p.source_refs) for p in proposals],
            "modality_refs": [list(p.modality_refs) for p in proposals],
            "plan_sha256": plan["plan_sha256"], "executed": False,
        })
        self.journal.append("plan_compiled", {
            "plan_sha256": plan["plan_sha256"], "steps": len(steps), "executed": False,
        })
        return plan

    def approve(self, plan: Mapping[str, Any], *, reviewer_id: str) -> dict[str, Any]:
        approved = CreatorRunbook(plan)
        identifier(reviewer_id, "reviewer")
        observed = self.journal.read()
        if not any(row["kind"] == "plan_compiled" and
                   row["payload"]["plan_sha256"] == approved.plan_sha256 for row in observed):
            raise StudioInteractionError("plan does not belong to this reviewed session")
        if any(row["kind"] == "plan_approved" and
               row["payload"]["plan_sha256"] == approved.plan_sha256 for row in observed):
            raise StudioInteractionError("plan approval already recorded")
        return self.journal.append("plan_approved", {
            "plan_sha256": approved.plan_sha256,
            "reviewer_id": reviewer_id, "grants_issued": False,
        })

    def runner(self, plan: Mapping[str, Any], *, executor: ToolExecutor,
               store: CreatorRunbookStore) -> CreatorRunbookRunner:
        contract = CreatorRunbook(plan)
        if contract.project_id != self.journal.project_id:
            raise StudioInteractionError("runbook belongs to another project")
        if not any(row["kind"] == "plan_approved" and
                   row["payload"]["plan_sha256"] == contract.plan_sha256
                   for row in self.journal.read()):
            raise StudioInteractionError("unapproved model actions cannot execute")
        if store.plan_sha256 != contract.plan_sha256:
            raise StudioInteractionError("durable runbook store bound to another plan")
        return CreatorRunbookRunner(contract, executor=executor,
                                   persist=store.persist, restored=store.load())

    def observe(self, *, runner: CreatorRunbookRunner,
                store: CreatorRunbookStore, step_id: str) -> dict[str, Any]:
        """Inspect the HOST-persisted runner, never a caller-constructed success.

        The runner already validates a real CreatorCommandReceipt before writing
        succeeded. Loading the matching CAS store verifies its entire durable
        chain before the supplementary studio journal records the result.
        """
        if not isinstance(runner, CreatorRunbookRunner) or not isinstance(store, CreatorRunbookStore):
            raise StudioInteractionError("host-owned runner and durable store required")
        identifier(step_id, "step")
        plan_sha256 = runner.plan.plan_sha256
        if store.plan_sha256 != plan_sha256 or runner.plan.project_id != self.journal.project_id:
            raise StudioInteractionError("runbook ownership or persistence binding differs")
        persisted = store.load()
        snapshot = runner.snapshot()
        if persisted is None or persisted != snapshot:
            raise StudioInteractionError("runner is not equal to durable verified state")
        if not any(row["kind"] == "plan_approved" and
                   row["payload"]["plan_sha256"] == plan_sha256 for row in self.journal.read()):
            raise StudioInteractionError("cannot observe unapproved plan")
        matches = [entry for entry in snapshot["steps"] if entry["step_id"] == step_id]
        if len(matches) != 1:
            raise StudioInteractionError("unknown runbook step")
        outcome = matches[0]
        status_to_event = {
            RunbookState.SUCCEEDED.value: "execution_succeeded",
            RunbookState.IN_DOUBT.value: "execution_uncertain",
            RunbookState.ABORTED.value: "execution_aborted",
        }
        kind = status_to_event.get(outcome["status"])
        if kind is None or (outcome["status"] == RunbookState.SUCCEEDED.value and
                            not outcome["receipt_digest"]):
            raise StudioInteractionError("cannot issue success from an unverified state")
        if any(row["kind"].startswith("execution_") and
               row["payload"].get("step_id") == step_id and
               row["payload"].get("plan_sha256") == plan_sha256
               for row in self.journal.read()):
            raise StudioInteractionError("outcome already observed; reconcile existing receipt")
        return self.journal.append(kind, {
            "plan_sha256": plan_sha256,
            "step_id": step_id,
            "status": outcome["status"],
            "attempts": outcome["attempts"],
            "command_receipt_sha256": outcome["receipt_digest"],
            "observation_sha256": outcome["observation_digest"],
            "reason": outcome["outcome_reason"],
            "runbook_state_sha256": snapshot["head_digest"],
        })



__all__ = ["FACETS", "questions", "StudioProposal", "StudioEvidenceJournal",
           "JeevesStudioController", "StudioInteractionError"]
