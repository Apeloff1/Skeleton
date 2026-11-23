"""Deterministic original-world revision impact and replay-compatibility proof.

Compare authored source trees, not UI summaries. Changed source invalidates old
replay leases even when the rendered game appears visually unchanged.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import StudioQuestError, compile_quest_program
from .studio_ecosystem_story_html import render_story_html

IMPACT_SCHEMA = "skeleton.game_builder.studio_revision_impact.v1"
MAX_SOURCE_BYTES = 512 * 1024
MAX_CHANGED_PATHS = 128
MAX_RECURSION_DEPTH = 16

def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical revision impact source") from exc

def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()

def compare_revision_sources(
    before: Mapping[str, Any], after: Mapping[str, Any], *,
    authorized: bool,
) -> dict[str, object]:
    """Report bounded exact changed source paths and conservative replay holds."""
    if authorized is not True:
        raise PermissionError("revision impact requires operator authorization")
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        raise StudioQuestError("revision impact requires two original source trees")
    originals = []
    for source in (before, after):
        raw = _canonical(source)
        if len(raw) > MAX_SOURCE_BYTES:
            raise StudioQuestError("revision impact source exceeds byte budget")
        proof = audit_canon_source(source, authorized=True)
        if not proof["canon_consistent"]:
            raise StudioQuestError("revision impact refuses contradictory canon")
        originals.append((raw, proof, compile_quest_program(source)))
    old_raw, old_proof, old_program = originals[0]
    new_raw, new_proof, new_program = originals[1]
    if old_proof["project_id"] != new_proof["project_id"]:
        raise StudioQuestError("revision impact cross-project comparison refused")
    changed: list[dict[str, object]] = []

    def walk(a: Any, b: Any, path: list[str | int], depth: int) -> None:
        if depth > MAX_RECURSION_DEPTH:
            raise StudioQuestError("revision impact depth exceeded")
        if len(changed) >= MAX_CHANGED_PATHS:
            raise StudioQuestError("revision impact changed-path budget exhausted")
        if type(a) is dict and type(b) is dict and set(a) == set(b):
            for key in sorted(a):
                walk(a[key], b[key], path + [key], depth + 1)
        elif type(a) is list and type(b) is list and len(a) == len(b):
            for index, (left, right) in enumerate(zip(a, b, strict=True)):
                walk(left, right, path + [index], depth + 1)
        elif a != b or type(a) is not type(b):
            changed.append({"path": path, "before_digest": _digest(a),
                            "after_digest": _digest(b)})

    walk(before, after, [], 0)
    if (sha256(_canonical(before)).digest() != sha256(old_raw).digest()
            or sha256(_canonical(after)).digest() != sha256(new_raw).digest()):
        raise StudioQuestError("revision impact source changed during proof")
    old_html = sha256(render_story_html(before)).hexdigest()
    new_html = sha256(render_story_html(after)).hexdigest()
    old_gameplay = [(s.key, s.prerequisites, s.alternatives, s.reward)
                    for s in old_program.stages]
    new_gameplay = [(s.key, s.prerequisites, s.alternatives, s.reward)
                    for s in new_program.stages]
    gameplay_unchanged = (old_gameplay == new_gameplay
                          and old_program.endings == new_program.endings)
    payload: dict[str, object] = {
        "schema": IMPACT_SCHEMA, "project_id": old_proof["project_id"],
        "before_source_digest": sha256(old_raw).hexdigest(),
        "after_source_digest": sha256(new_raw).hexdigest(),
        "before_canon_digest": old_proof["source_digest"],
        "after_canon_digest": new_proof["source_digest"],
        "before_html_sha256": old_html, "after_html_sha256": new_html,
        "changed_paths": changed, "changed_path_count": len(changed),
        "authored_gameplay_contract_unchanged": gameplay_unchanged,
        "rendered_playable_html_changed": old_html != new_html,
        "existing_save_replay_lease_valid": old_raw == new_raw,
        "new_save_required": old_raw != new_raw,
        "ending_obligations": new_proof["ending_obligations"],
        "originality_rights_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["impact_digest"] = _digest(payload)
    return payload
