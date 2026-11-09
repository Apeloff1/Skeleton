"""Integrated exact-source assurance gate for authored offline world experiences.

The gate is deliberately downstream of three independent verticals:
operator-reviewed scenario acceptance, exhaustive state invariants, and
canonical choice consequence analysis. A missing/stale/tampered dependency
never becomes an implicit pass or a release claim.
"""
from __future__ import annotations

from hashlib import sha256
import os
from typing import Any

from .bundle import _artifact_read
from .choice_impact import ChoiceImpactStore, analyze_choice_impact
from .invariants import InvariantStore, prove_invariants
from .scenario import ScenarioStore, run_suite
from .world_canon import (
    CanonError, WorldStore, _id, canonical, compile_html, digest,
    prove, strict_json,
)

SCHEMA = "jeeves.world.assurance_handoff.v1"
RECEIPT_SCHEMA = "jeeves.world.assurance_receipt.v1"
MAX_HTML = 1572864


class AssuranceStore:
    """One world lease protects the full upstream receipt and artifact proof."""

    def __init__(self, root: str) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (
            world_id + ".assurance.handoff.json",
            world_id + ".assurance.playable.html",
            world_id + ".assurance.receipt.json",
        )

    @staticmethod
    def _lock(fd: int, world_id: str) -> None:
        try:
            handle = os.open(
                world_id + ".lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                os.O_NOFOLLOW, 0o600, dir_fd=fd,
            )
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        source = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(source)
        if source["id"] != world_id:
            raise CanonError("assurance_world_identity_mismatch")
        return source

    def preview(self, world_id: str) -> dict[str, Any]:
        """Read-only model-visible diagnostics; never approves or publishes."""
        world = self.worlds.read(world_id)
        results: dict[str, Any] = {
            "schema": "jeeves.world.assurance_preview.v1",
            "world_id": world_id, "world_digest": digest(world),
            "choice_impact": analyze_choice_impact(world),
            "scenario": None, "invariants": None,
            "ready_for_compile": False, "missing_or_invalid": [],
        }
        for name, store in (
            ("scenario", ScenarioStore(str(self.worlds.root))),
            ("invariants", InvariantStore(str(self.worlds.root))),
        ):
            try:
                data = store.inspect(world_id)
                results[name] = {
                    "approved": data["suite"]["approved"],
                    "report": data["report"],
                }
                if not data["suite"]["approved"] or not data["report"]["complete"]:
                    results["missing_or_invalid"].append(name + "_not_approved_or_failed")
            except (CanonError, OSError):
                results["missing_or_invalid"].append(name + "_unavailable")
        # Existing compiled receipts are independently required at compile time.
        for name, store in (
            ("scenario", ScenarioStore(str(self.worlds.root))),
            ("invariants", InvariantStore(str(self.worlds.root))),
            ("choice_impact", ChoiceImpactStore(str(self.worlds.root))),
        ):
            try:
                store.verify(world_id)
            except (CanonError, OSError):
                results["missing_or_invalid"].append(name + "_receipt_unverified")
        results["missing_or_invalid"] = sorted(set(results["missing_or_invalid"]))
        results["ready_for_compile"] = not results["missing_or_invalid"]
        return results

    def _upstream(self, fd: int, world: Any) -> dict[str, Any]:
        """Recompute all dependency receipts and artifacts UNDER our world lock."""
        world_id = world["id"]
        scenario_names = ScenarioStore._names(world_id)
        invariant_names = InvariantStore._names(world_id)
        impact_names = ChoiceImpactStore._names(world_id)
        scenario = strict_json(self.worlds._read(fd, scenario_names[0]))
        invariants = strict_json(self.worlds._read(fd, invariant_names[0]))
        impact_receipt = strict_json(self.worlds._read(fd, impact_names[2]))
        if type(impact_receipt) is not dict or (
            type(impact_receipt.get("require_distinct")) is not bool
        ):
            raise CanonError("assurance_invalid_impact_receipt")
        expected = {
            "scenario": (
                scenario_names, *ScenarioStore._outputs(world, scenario),
            ),
            "invariants": (
                invariant_names, *InvariantStore._outputs(world, invariants),
            ),
            "choice_impact": (
                impact_names,
                *ChoiceImpactStore._outputs(
                    world, impact_receipt["require_distinct"],
                ),
            ),
        }
        result: dict[str, Any] = {}
        for name, (names, receipt, outputs) in expected.items():
            stored = strict_json(self.worlds._read(fd, names[-1]))
            if stored != receipt:
                raise CanonError("assurance_upstream_receipt_mismatch", name)
            # Scenario/invariant names are 4-tuples, choice impact 3-tuple.
            artifact_names = names[1:-1] if len(names) == 4 else names[:2]
            for artifact_name, data in zip(artifact_names, outputs):
                if _artifact_read(fd, artifact_name) != data:
                    raise CanonError("assurance_upstream_artifact_mismatch", name)
            result[name] = {
                "receipt_sha256": sha256(canonical(receipt)).hexdigest(),
                "report_digest": receipt["report_digest"] if name != "choice_impact"
                                 else receipt["report_digest"],
                "artifact_digests": receipt["artifacts"],
            }
        return result

    @staticmethod
    def _outputs(world: Any, upstream: dict[str, Any]) -> tuple[dict[str, Any], tuple[bytes, bytes]]:
        proof = prove(world)
        handoff = {
            "schema": SCHEMA, "world_id": world["id"],
            "world_digest": proof.source_digest,
            "ending_witnesses": {
                key: list(value) for key, value in
                sorted(proof.ending_witnesses.items())
            },
            "assurance_dependencies": upstream,
            "all_source_checks_verified": True,
            "qualification": "source_assurance_only_not_release_or_device_certified",
        }
        data = canonical(handoff)
        playable = compile_html(world).encode("utf-8")
        if len(data) > 524288 or len(playable) > MAX_HTML:
            raise CanonError("assurance_artifact_budget")
        names = AssuranceStore._names(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world),
            "handoff_digest": digest(handoff),
            "upstream_receipts": {
                key: value["receipt_sha256"] for key, value in sorted(upstream.items())
            },
            "artifacts": {
                names[0]: sha256(data).hexdigest(),
                names[1]: sha256(playable).hexdigest(),
            },
            "qualification": "exact_source_checks_not_release_certified",
        }
        return receipt, (data, playable)

    def compile(self, world_id: str, *, expected_world_digest: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                if digest(world) != expected_world_digest:
                    raise CanonError("assurance_stale_source")
                upstream = self._upstream(fd, world)
                receipt, outputs = self._outputs(world, upstream)
                names = self._names(world_id)
                for name, data in zip(names[:2], outputs):
                    self.worlds._write(fd, name, data)
                self.worlds._write(fd, names[2], canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                names = self._names(world_id)
                stored = strict_json(self.worlds._read(fd, names[2]))
                world = self._world(fd, world_id)
                upstream = self._upstream(fd, world)
                receipt, outputs = self._outputs(world, upstream)
                if stored != receipt:
                    raise CanonError("assurance_receipt_mismatch")
                for name, data in zip(names[:2], outputs):
                    if _artifact_read(fd, name) != data:
                        raise CanonError("assurance_artifact_mismatch", name)
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
