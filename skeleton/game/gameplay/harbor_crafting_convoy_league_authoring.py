"""Transactional convoy league editor: CAS, bounded edits, verified previews."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _integer, _keys, canonical, digest, validate_source
from .harbor_crafting_convoy_league import (
    MAX_LEAGUE_BYTES, MAX_SAVE_BYTES, build_league, validate_league, verify_league,
)

REVISION_SCHEMA = "skeleton.game.harbor.convoy-league-revision.v1"
MAX_REVISION_BYTES = MAX_LEAGUE_BYTES * 2 + MAX_SAVE_BYTES * 2 + 8192
FIELDS = {
    "schema", "source", "before", "edits", "after", "preview_sessions",
    "before_preview", "after_preview", "revision_digest",
}
EDIT_FIELDS = {"kind", "target", "value"}
KINDS = {"minimum-bounty", "minimum-hull", "target-score", "max-total-ticks", "encounter-strength", "encounter-reward", "convoy-hull", "convoy-max-turns"}


def edit_league(source: Any, league: Any, edits: Any, *,
                expected_digest: str, preview_save: Any = None) -> dict[str, Any]:
    world = validate_source(source)
    before = validate_league(league, world)
    if type(expected_digest) is not str or digest(before) != expected_digest:
        raise HarborError("stale convoy league board lease")
    if not isinstance(edits, list) or not 1 <= len(edits) <= 16:
        raise HarborError("invalid league edit count")
    after = deepcopy(before)
    touched: set[tuple[str, str]] = set()
    for edit in edits:
        _keys(edit, EDIT_FIELDS, "league edit")
        kind, target, value = edit["kind"], edit["target"], edit["value"]
        if kind not in KINDS or type(target) is not str:
            raise HarborError("unsupported league edit")
        key = (kind, target)
        if key in touched:
            raise HarborError("duplicate league edit")
        touched.add(key)
        if kind in {"target-score", "max-total-ticks"}:
            if target != "league":
                raise HarborError("league-wide edit target mismatch")
            _integer(value, 1, 8 * world["max_ticks"] if kind == "max-total-ticks" else 1600, "league edit value")
            after["target_score" if kind == "target-score" else "max_total_ticks"] = value
        else:
            parts = target.split(":")
            if len(parts) not in {1, 2}:
                raise HarborError("invalid league combat edit target")
            found = next((round_ for round_ in after["rounds"] if round_["id"] == parts[0]), None)
            if found is None:
                raise HarborError("unknown league round")
            if kind in {"encounter-strength", "encounter-reward"}:
                if len(parts) != 2:
                    raise HarborError("encounter edit requires round:enemy")
                encounter = next(
                    (item for item in found["board"]["encounters"] if item["id"] == parts[1]),
                    None,
                )
                if encounter is None:
                    raise HarborError("unknown league encounter")
                _integer(value, 1 if kind == "encounter-strength" else 0,
                         12 if kind == "encounter-strength" else 100, "league combat edit")
                encounter["strength" if kind == "encounter-strength" else "reward"] = value
            elif kind in {"convoy-hull", "convoy-max-turns"}:
                if len(parts) != 1:
                    raise HarborError("convoy edit requires a round id")
                _integer(value, 1,
                         20 if kind == "convoy-hull" else world["max_ticks"],
                         "league convoy edit")
                found["board"]["hull" if kind == "convoy-hull" else "max_turns"] = value
            else:
                if len(parts) != 1:
                    raise HarborError("threshold edit requires a round id")
                _integer(value, 0 if kind == "minimum-bounty" else 1,
                         1200, "league edit value")
                found["minimum_bounty" if kind == "minimum-bounty" else "minimum_hull"] = value
    validate_league(after, world)
    preview_sessions = None
    before_preview = None
    after_preview = None
    if preview_save is not None:
        verify_league(preview_save)
        if preview_save["source"] != world or preview_save["league"] != before:
            raise HarborError("league preview source or board mismatch")
        preview_sessions = deepcopy(preview_save["sessions"])
        before_preview = deepcopy(preview_save)
        after_preview = build_league(world, after, preview_sessions)
    revision = {
        "schema": REVISION_SCHEMA, "source": deepcopy(world), "before": before,
        "edits": deepcopy(edits), "after": after, "preview_sessions": preview_sessions,
        "before_preview": before_preview, "after_preview": after_preview,
    }
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("league revision exceeds byte budget")
    return revision


def verify_league_revision(revision: Any) -> dict[str, Any]:
    _keys(revision, FIELDS, "league revision")
    if revision["schema"] != REVISION_SCHEMA or len(canonical(revision)) > MAX_REVISION_BYTES:
        raise HarborError("unsupported or oversized league revision")
    if revision["revision_digest"] != digest({
        key: value for key, value in revision.items() if key != "revision_digest"
    }):
        raise HarborError("league revision digest mismatch")
    rebuilt = edit_league(
        revision["source"], revision["before"], revision["edits"],
        expected_digest=digest(revision["before"]),
        preview_save=revision["before_preview"],
    )
    if rebuilt != revision:
        raise HarborError("league revision replay mismatch")
    return {
        "verified": True, "board_digest": digest(rebuilt["after"]),
        "preview_complete": (
            rebuilt["after_preview"]["complete"] if rebuilt["after_preview"] is not None else None
        ),
    }
