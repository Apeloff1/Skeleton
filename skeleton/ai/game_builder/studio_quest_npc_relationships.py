"""Original NPC relationship authoring bound to canonical quest choice replay.

No NPC emotion, dialogue, observation or real-world social fact is inferred.
Only operator-authored and reviewed stage-choice effects alter sandbox trust.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
import os
from pathlib import Path
import re
import secrets
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress, replay_quest, start_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from .studio_quest_private_io import read_studio_private_json

SCHEMA = "skeleton.game_builder.studio_quest_npc_relationships.v1"
PLAN_SCHEMA = "skeleton.game_builder.studio_quest_npc_relationship_plan.v1"
HANDOFF_SCHEMA = "skeleton.game_builder.studio_quest_npc_relationship_handoff.v1"
PROMPT = "author reviewed original NPC relationship consequences for quest choices"
FILENAME = "studio_quest_npc_relationships.json"
MAX_SOURCE = 256 * 1024
MAX_PLAN = 131072
MAX_RECEIPT = 196608
MAX_HTML = 262144
MAX_ACTORS = 12
MAX_EFFECTS = 128


def _text(value: object, label: str, maximum: int, *, empty: bool = False) -> str:
    if (type(value) is not str or len(value) > maximum
            or (not empty and not value) or value.strip() != value
            or any(ord(c) < 32 or 0x7f <= ord(c) <= 0x9f
                   or c in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
                   for c in value)):
        raise StudioQuestError("invalid NPC relationship " + label)
    return value


def _actions(value: object) -> list[list[str]]:
    if type(value) is not list or len(value) > 64:
        raise StudioQuestError("invalid NPC replay action count")
    result = []
    for pair in value:
        if (type(pair) is not list or len(pair) != 2
                or any(type(x) is not str or not 1 <= len(x) <= 256 for x in pair)):
            raise StudioQuestError("invalid NPC replay action")
        result.append(list(pair))
    return result


def propose_quest_npc_relationships(
    documents: Mapping[str, Any], prompt: str, actors: object, actions: object,
    target_ending: str, *, authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC relationship proposal requires authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported NPC relationship prompt")
    _lease(expected_source_digest, "NPC relationship source")
    _lease(expected_initial_session_digest, "NPC relationship initial session")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale NPC relationship source")
    if start_quest(documents, authorized=True).digest != expected_initial_session_digest:
        raise StudioQuestError("stale NPC relationship initial session")
    if target_ending not in dict(program.endings):
        raise StudioQuestError("unknown NPC relationship ending")
    if type(actors) is not list or not 1 <= len(actors) <= MAX_ACTORS:
        raise StudioQuestError("NPC roster must contain 1 to 12 original actors")
    roster = []
    for actor in actors:
        ident = _text(actor, "actor ID", 64)
        if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", ident) is None:
            raise StudioQuestError("invalid original NPC actor identifier")
        roster.append({"id": ident, "name": ident,
                       "initial_trust": 0, "reviewed": False})
    if len(set(a["id"] for a in roster)) != len(roster):
        raise StudioQuestError("duplicate original NPC identifier")
    session = replay_quest(documents, _actions(actions), authorized=True)
    plan = {
        "schema": PLAN_SCHEMA, "actors": roster, "effects": [],
        "actions": [list(x) for x in session.choices],
        "target_ending": target_ending,
    }
    if len(_canonical(plan)) > MAX_PLAN:
        raise StudioQuestError("NPC relationship proposal exceeds byte budget")
    return plan


def _plan(value: object, program: Any) -> dict[str, Any]:
    if (type(value) is not dict or set(value) != {
            "schema", "actors", "effects", "actions", "target_ending"}
            or value.get("schema") != PLAN_SCHEMA
            or len(_canonical(value)) > MAX_PLAN):
        raise StudioQuestError("invalid typed NPC relationship plan")
    actors = value["actors"]
    if type(actors) is not list or not 1 <= len(actors) <= MAX_ACTORS:
        raise StudioQuestError("invalid NPC roster count")
    clean_actors = []
    ids = set()
    for row in actors:
        if type(row) is not dict or set(row) != {
                "id", "name", "initial_trust", "reviewed"}:
            raise StudioQuestError("invalid NPC roster row")
        ident = _text(row["id"], "ID", 64)
        if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", ident) is None or ident in ids:
            raise StudioQuestError("invalid or repeated NPC actor ID")
        ids.add(ident)
        trust = row["initial_trust"]
        if type(trust) is not int or not -50 <= trust <= 50:
            raise StudioQuestError("invalid bounded NPC initial trust")
        if type(row["reviewed"]) is not bool:
            raise StudioQuestError("NPC actor review must be boolean")
        clean_actors.append({"id": ident, "name": _text(row["name"], "name", 128),
                             "initial_trust": trust, "reviewed": row["reviewed"]})
    effects = value["effects"]
    if type(effects) is not list or len(effects) > MAX_EFFECTS:
        raise StudioQuestError("invalid bounded NPC effect count")
    stages = {stage.key: stage for stage in program.stages}
    seen = set()
    clean_effects = []
    for row in effects:
        if type(row) is not dict or set(row) != {
                "stage_id", "choice", "actor_id", "delta", "reason", "reviewed"}:
            raise StudioQuestError("invalid NPC effect row")
        stage = _text(row["stage_id"], "stage", 256)
        choice = _text(row["choice"], "choice", 256)
        actor = _text(row["actor_id"], "actor", 64)
        if stage not in stages or choice not in stages[stage].alternatives or actor not in ids:
            raise StudioQuestError("NPC effect refers to noncanonical action or actor")
        key = (stage, choice, actor)
        if key in seen:
            raise StudioQuestError("ambiguous duplicate NPC effect")
        seen.add(key)
        delta = row["delta"]
        if type(delta) is not int or delta == 0 or not -25 <= delta <= 25:
            raise StudioQuestError("invalid bounded NPC trust effect")
        if type(row["reviewed"]) is not bool:
            raise StudioQuestError("NPC effect review must be boolean")
        clean_effects.append({
            "stage_id": stage, "choice": choice, "actor_id": actor,
            "delta": delta, "reason": _text(row["reason"], "reason", 256),
            "reviewed": row["reviewed"],
        })
    target = _text(value["target_ending"], "ending", 256)
    if target not in dict(program.endings):
        raise StudioQuestError("unknown NPC relationship target ending")
    return {"schema": PLAN_SCHEMA, "actors": clean_actors,
            "effects": clean_effects, "actions": _actions(value["actions"]),
            "target_ending": target}


def compile_quest_npc_relationships(
    documents: Mapping[str, Any], authoring: object, *, authorized: bool,
    expected_source_digest: str, expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC relationship compile requires authorization")
    _lease(expected_source_digest, "NPC relationship source")
    _lease(expected_initial_session_digest, "NPC relationship initial session")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE:
        raise StudioQuestError("NPC relationship source exceeds byte budget")
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)
    if (program.source_digest != expected_source_digest
            or initial.digest != expected_initial_session_digest):
        raise StudioQuestError("stale NPC relationship source or initial session")
    plan = _plan(authoring, program)
    session = replay_quest(documents, plan["actions"], authorized=True)
    progress = quest_progress(session, documents)
    trust = {actor["id"]: actor["initial_trust"] for actor in plan["actors"]}
    applied = []
    effect_map = {(x["stage_id"], x["choice"]): [] for x in plan["effects"]}
    for effect in plan["effects"]:
        effect_map[(effect["stage_id"], effect["choice"])].append(effect)
    for stage_id, choice in session.choices:
        for effect in effect_map.get((stage_id, choice), []):
            old = trust[effect["actor_id"]]
            new = old + effect["delta"]
            if not -100 <= new <= 100:
                raise StudioQuestError("NPC trust overflow; revise authored effects")
            trust[effect["actor_id"]] = new
            applied.append({
                "stage_id": stage_id, "choice": choice,
                "actor_id": effect["actor_id"], "before": old,
                "delta": effect["delta"], "after": new,
                "reviewed": effect["reviewed"],
            })
    reviewed = all(a["reviewed"] for a in plan["actors"]) and all(
        e["reviewed"] for e in plan["effects"])
    eligible = plan["target_ending"] in progress["sandbox_endings_eligible"]
    if _canonical(documents) != before:
        raise StudioQuestError("NPC relationship source changed during compilation")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "session_digest": session.digest,
        "authoring": plan, "applied": applied,
        "final_trust": [{"actor_id": x["id"], "trust": trust[x["id"]]}
                        for x in plan["actors"]],
        "target_ending_eligible": eligible,
        "unmet_target_predicates": progress["unmet_ending_predicates"].get(
            plan["target_ending"], []),
        "all_authoring_reviewed": reviewed,
        "playable_handoff_allowed": bool(reviewed and plan["effects"] and eligible),
        "trust_is_authored_sandbox_state": True,
        "npc_behavior_observed": False,
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False, "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT - 128:
        raise StudioQuestError("NPC relationship receipt exceeds byte budget")
    result["relationship_digest"] = _digest(result)
    return result


def replay_quest_npc_relationships(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC relationship replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid NPC relationship receipt")
    checked = compile_quest_npc_relationships(
        documents, receipt.get("authoring"), authorized=True,
        expected_source_digest=receipt.get("source_digest"),
        expected_initial_session_digest=receipt.get("initial_session_digest"))
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("NPC relationship receipt differs from replay")
    return checked


def compile_npc_relationship_handoff(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_npc_relationships(
        documents, receipt, authorized=authorized)
    if not checked["playable_handoff_allowed"]:
        raise StudioQuestError("NPC handoff requires reviewed effects and eligible ending")
    session = replay_quest(documents, checked["authoring"]["actions"], authorized=True)
    if session.digest != checked["session_digest"]:
        raise StudioQuestError("NPC handoff canonical session diverged")
    result = {
        "schema": HANDOFF_SCHEMA, "project_id": checked["project_id"],
        "source_digest": checked["source_digest"],
        "session_digest": session.digest,
        "relationship_digest": checked["relationship_digest"],
        "canonical_choices": [list(x) for x in session.choices],
        "actor_roster": [{"id": x["id"], "name": x["name"]}
                         for x in checked["authoring"]["actors"]],
        "applied_relationship_effects": checked["applied"],
        "final_trust": checked["final_trust"],
        "target_ending": checked["authoring"]["target_ending"],
        "trust_is_authored_sandbox_state": True,
        "npc_behavior_observed": False, "native_gameplay_verified": False,
        "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_npc_relationships(
    documents: Mapping[str, Any], receipt: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    checked = replay_quest_npc_relationships(documents, receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT:
        raise StudioQuestError("NPC relationship publication exceeds byte budget")
    fd = _open_directory(directory)
    temp = ".npc-relationships-" + secrets.token_hex(16) + ".tmp"
    created = False
    linked = False
    try:
        before = os.fstat(fd)
        out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                      0o600, dir_fd=fd)
        created = True
        try:
            _write_all(out, raw)
            os.fsync(out)
        finally:
            os.close(out)
        os.link(temp, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        linked = True
        os.fsync(fd)
        verify_fd = _open_directory(directory)
        try:
            after = os.fstat(verify_fd)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise StudioQuestError("NPC relationship output directory changed")
        finally:
            os.close(verify_fd)
    except BaseException:
        if linked:
            os.unlink(FILENAME, dir_fd=fd)
            os.fsync(fd)
        raise
    finally:
        try:
            if created:
                os.unlink(temp, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME),
            "relationship_digest": checked["relationship_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_npc_relationships(
    documents: Mapping[str, Any], directory: Path, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC relationship restore requires authorization")
    _lease(expected_source_digest, "NPC relationship restore source")
    stored = read_studio_private_json(Path(directory) / FILENAME, MAX_RECEIPT)
    if stored.get("source_digest") != expected_source_digest:
        raise StudioQuestError("stale NPC relationship restore source")
    return replay_quest_npc_relationships(documents, stored, authorized=True)


_SCRIPT = """(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  byId('export').addEventListener('click', () => {
    try {
      const plan = JSON.parse(byId('plan').textContent);
      plan.actors = plan.actors.map((actor, i) => ({
        ...actor,
        name: byId('name-' + i).value,
        initial_trust: Number(byId('trust-' + i).value),
        reviewed: byId('actor-review-' + i).checked
      }));
      plan.effects = plan.effects.map((effect, i) => ({
        ...effect,
        delta: Number(byId('delta-' + i).value),
        reason: byId('reason-' + i).value,
        reviewed: byId('effect-review-' + i).checked
      }));
      const raw = JSON.stringify(plan);
      if (new TextEncoder().encode(raw).length > 131072) throw Error('oversize');
      const url = URL.createObjectURL(new Blob([raw], {type: 'application/json'}));
      const link = document.createElement('a');
      link.href = url; link.download = 'quest-npc-relationship-edited-plan.json';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      byId('status').textContent = 'Exported; canonical CLI review required.';
    } catch (_) {
      byId('status').textContent = 'Invalid edit; no export.';
    }
  });
})();"""


def render_npc_relationship_editor_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
) -> bytes:
    checked = replay_quest_npc_relationships(documents, receipt, authorized=authorized)
    plan = checked["authoring"]
    roster = "".join(
        '<fieldset><legend>' + escape(actor["id"]) + '</legend>'
        '<label for="name-' + str(i) + '">Original name</label>'
        '<input id="name-' + str(i) + '" maxlength="128" value="' +
        escape(actor["name"], quote=True) + '">'
        '<label for="trust-' + str(i) + '">Initial trust</label>'
        '<input type="number" min="-50" max="50" id="trust-' + str(i) +
        '" value="' + str(actor["initial_trust"]) + '">'
        '<label for="actor-review-' + str(i) + '">Reviewed</label>'
        '<input type="checkbox" id="actor-review-' + str(i) + '"' +
        (" checked" if actor["reviewed"] else "") + '></fieldset>'
        for i, actor in enumerate(plan["actors"]))
    effects = "".join(
        '<fieldset><legend>' + escape(e["stage_id"] + " / " + e["choice"] +
                                     " / " + e["actor_id"]) + '</legend>'
        '<label for="delta-' + str(i) + '">Trust delta</label>'
        '<input type="number" min="-25" max="25" id="delta-' + str(i) +
        '" value="' + str(e["delta"]) + '">'
        '<label for="reason-' + str(i) + '">Authored reason</label>'
        '<input maxlength="256" id="reason-' + str(i) + '" value="' +
        escape(e["reason"], quote=True) + '">'
        '<label for="effect-review-' + str(i) + '">Reviewed</label>'
        '<input type="checkbox" id="effect-review-' + str(i) + '"' +
        (" checked" if e["reviewed"] else "") + '></fieldset>'
        for i, e in enumerate(plan["effects"]))
    plan_json = _canonical(plan).decode("ascii").replace("<", "\\u003c")
    script_hash = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + script_hash +
           "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
        '<title>Original quest NPC relationships</title></head><body><main>'
        '<h1>Review authored NPC relationships</h1>'
        '<p>Only canonical quest choices affect authored sandbox trust.</p>' +
        roster + effects +
        '<script id="plan" type="application/json">' + plan_json + '</script>'
        '<button id="export" type="button">Export edited relationship plan</button>'
        '<p id="status" role="status" aria-live="polite"></p>'
        '<p>Canonical CLI replay and review required for playable handoff.</p>'
        '</main><script>' + _SCRIPT + '</script></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML:
        raise StudioQuestError("NPC relationship editor exceeds byte budget")
    return html
