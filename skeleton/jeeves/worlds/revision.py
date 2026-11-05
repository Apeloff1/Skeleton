"""Deterministic source-revision impact review and playable handoff.

A revision can alter causal gameplay even if its prose is polished. This
operator-reviewed plane reports field-level semantic changes, witnesses and
bounded playable bytes without exposing old or new private prose in the report.
"""
from __future__ import annotations

from hashlib import sha256
import os
from typing import Any

from .bundle import _artifact_read
from .world_canon import (
    CanonError, WorldStore, _id, _text, canonical, compile_html,
    digest, prove, strict_json,
)

SCHEMA = "jeeves.world.revision_impact.v1"
RECEIPT_SCHEMA = "jeeves.world.revision_receipt.v1"
MAX_ARTIFACT = 1572864


def _delta(before: list[dict[str, Any]], after: list[dict[str, Any]],
           identity: str, semantic: set[str]) -> dict[str, Any]:
    previous = {item[identity]: item for item in before}
    current = {item[identity]: item for item in after}
    common = sorted(previous.keys() & current.keys())
    changes = []
    for key in common:
        fields = sorted(name for name in previous[key]
                        if previous[key][name] != current[key][name])
        if fields:
            changes.append({
                "id": key, "fields": fields,
                "causal": any(name in semantic for name in fields),
            })
    return {
        "added": sorted(current.keys() - previous.keys()),
        "removed": sorted(previous.keys() - current.keys()),
        "modified": changes,
    }


def analyze_revision(old_world: Any, new_world: Any) -> dict[str, Any]:
    old_proof, new_proof = prove(old_world), prove(new_world)
    if old_world["id"] != new_world["id"]:
        raise CanonError("revision_identity_mismatch")
    if old_proof.source_digest == new_proof.source_digest:
        raise CanonError("revision_unchanged")
    scenes = _delta(old_world["scenes"], new_world["scenes"], "id", set())
    choices = _delta(old_world["choices"], new_world["choices"], "id",
                     {"from", "to", "requires", "grants"})
    endings = _delta(old_world["endings"], new_world["endings"], "scene", set())
    top = sorted(field for field in ("prompt", "protagonist", "region", "start")
                 if old_world[field] != new_world[field])
    structural = any(part["added"] or part["removed"]
                     for part in (scenes, choices, endings))
    causal = (structural or "start" in top or
              any(item["causal"] for item in choices["modified"]))
    old_witness = {key: list(value) for key, value in
                   sorted(old_proof.ending_witnesses.items())}
    new_witness = {key: list(value) for key, value in
                   sorted(new_proof.ending_witnesses.items())}
    report = {
        "schema": SCHEMA, "world_id": new_world["id"],
        "old_world_digest": old_proof.source_digest,
        "new_world_digest": new_proof.source_digest,
        "top_level_fields": top, "scenes": scenes,
        "choices": choices, "endings": endings,
        "old_ending_witnesses": old_witness,
        "new_ending_witnesses": new_witness,
        "old_states_explored": old_proof.states_explored,
        "new_states_explored": new_proof.states_explored,
        "causal_change": causal,
        "review_class": "causal_review_required" if causal else "presentation_review",
        "playable_sha256": sha256(compile_html(new_world).encode()).hexdigest(),
        "qualification": "source_diff_not_release_or_device_certified",
    }
    if len(canonical(report)) > 524288:
        raise CanonError("revision_report_too_large")
    return report


class RevisionStore:
    """Publish operator-reviewed impact evidence against current source."""
    def __init__(self, root: str) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".revision.impact.json",
                world_id + ".revision.playable.html",
                world_id + ".revision.receipt.json")

    def preview(self, world_id: str, old_world: Any) -> dict[str, Any]:
        return analyze_revision(old_world, self.worlds.read(world_id))

    @staticmethod
    def _outputs(old_world: Any, new_world: Any, note: str):
        _text(note, "review_note", 512)
        impact = analyze_revision(old_world, new_world)
        report = canonical(impact)
        playable = compile_html(new_world).encode()
        if len(playable) > MAX_ARTIFACT:
            raise CanonError("revision_playable_too_large")
        names = RevisionStore._names(new_world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": new_world["id"],
            "old_world_digest": digest(old_world),
            "new_world_digest": digest(new_world),
            "impact_digest": digest(impact), "review_note": note,
            "review_class": impact["review_class"],
            "artifacts": {names[0]: sha256(report).hexdigest(),
                          names[1]: sha256(playable).hexdigest()},
            "qualification": "operator_reviewed_not_release_certified",
        }
        return receipt, (report, playable)

    def _locked(self, fd: int, world_id: str) -> dict[str, Any]:
        source = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(source)
        if source["id"] != world_id:
            raise CanonError("revision_identity_mismatch")
        return source

    def _lease(self, fd: int, world_id: str) -> None:
        try:
            handle = os.open(world_id + ".lock",
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def review(self, world_id: str, old_world: Any, *,
               expected_impact_digest: str, note: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lease(fd, world_id)
            try:
                source = self._locked(fd, world_id)
                receipt, outputs = self._outputs(old_world, source, note)
                if type(expected_impact_digest) is not str or (
                    receipt["impact_digest"] != expected_impact_digest
                ):
                    raise CanonError("revision_stale_preview")
                names = self._names(world_id)
                for name, content in zip(names[:2], outputs):
                    self.worlds._write(fd, name, content)
                self.worlds._write(fd, names[2], canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str, old_world: Any) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lease(fd, world_id)
            try:
                names = self._names(world_id)
                stored = strict_json(self.worlds._read(fd, names[2]))
                if type(stored) is not dict or type(stored.get("review_note")) is not str:
                    raise CanonError("revision_invalid_receipt")
                source = self._locked(fd, world_id)
                receipt, outputs = self._outputs(
                    old_world, source, stored["review_note"])
                if receipt != stored:
                    raise CanonError("revision_receipt_mismatch")
                for name, expected in zip(names[:2], outputs):
                    if _artifact_read(fd, name) != expected:
                        raise CanonError("revision_artifact_mismatch", name)
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
