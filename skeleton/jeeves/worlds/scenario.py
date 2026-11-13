"""Authored end-to-end gameplay acceptance scenarios with canonical replay custody.

A suite is not an invented test result: the author specifies concrete player
choices and exact expected terminal or intermediate state. Approval and compile
are separate, explicit operator actions with source and suite digest leases.
"""
from __future__ import annotations

from hashlib import sha256
import os
from typing import Any

from .bundle import _artifact_read
from .session import replay_choices
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text, _flags,
    canonical, compile_html, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.scenario_suite.v1"
REPORT_SCHEMA = "jeeves.world.scenario_report.v1"
RECEIPT_SCHEMA = "jeeves.world.scenario_receipt.v1"
MAX_CASES = 128
MAX_TRACE = 512
MAX_HTML = 1572864


def validate_suite(suite: Any, world: Any) -> dict[str, Any]:
    proof = prove(world)
    obj = _keys(suite, {
        "schema", "world_id", "world_digest", "cases", "approved", "review_note",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("scenario_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != proof.source_digest:
        raise CanonError("scenario_source_lease_mismatch")
    if type(obj["approved"]) is not bool:
        raise CanonError("scenario_invalid_approval")
    _text(obj["review_note"], "review_note", 512)
    cases = _list(obj["cases"], "cases", MAX_CASES)
    if not cases:
        raise CanonError("scenario_empty_suite")
    seen: set[str] = set()
    scenes = {item["id"] for item in world["scenes"]}
    endings = {item["scene"] for item in world["endings"]}
    known_choices = {item["id"] for item in world["choices"]}
    known_flags = {flag for choice in world["choices"] for flag in choice["grants"]}
    for case in cases:
        _keys(case, {"id", "choices", "expect"})
        cid = _id(case["id"], "case.id")
        if cid in seen:
            raise CanonError("scenario_duplicate_case", cid)
        seen.add(cid)
        choices = [_id(value, "case.choice") for value in
                   _list(case["choices"], "case.choices", MAX_TRACE)]
        if not set(choices) <= known_choices:
            raise CanonError("scenario_unknown_choice", cid)
        expected = _keys(case["expect"], {"scene", "flags", "ending"})
        if _id(expected["scene"], "case.scene") not in scenes:
            raise CanonError("scenario_unknown_scene", cid)
        flags = _flags(expected["flags"], "case.flags")
        if not set(flags) <= known_flags:
            raise CanonError("scenario_unknown_flag", cid)
        if type(expected["ending"]) is not bool:
            raise CanonError("scenario_invalid_ending_expectation", cid)
        if expected["ending"] != (expected["scene"] in endings):
            raise CanonError("scenario_ending_inconsistent", cid)
    if len(canonical(obj)) > 524288:
        raise CanonError("scenario_suite_too_large")
    return obj


def run_suite(suite: Any, world: Any) -> dict[str, Any]:
    """Replay every authored case; mismatch is reported, never silently passed."""
    validate_suite(suite, world)
    endings = {item["scene"] for item in world["endings"]}
    cases = []
    for case in suite["cases"]:
        expected = case["expect"]
        try:
            actual = replay_choices(world, case["choices"])
            observed = {
                "scene": actual["scene"], "flags": actual["flags"],
                "ending": actual["scene"] in endings,
            }
            ok = observed == expected
            error = None
        except CanonError as exc:
            observed = None
            ok = False
            error = exc.code
        cases.append({
            "id": case["id"], "passed": ok,
            "choice_trace": list(case["choices"]),
            "expected": expected, "observed": observed, "error": error,
        })
    passed = sum(case["passed"] for case in cases)
    report = {
        "schema": REPORT_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "suite_digest": digest(suite),
        "total": len(cases), "passed": passed, "failed": len(cases) - passed,
        "complete": passed == len(cases), "cases": cases,
        "qualification": "authored_canonical_replay_not_device_certified",
    }
    if len(canonical(report)) > 524288:
        raise CanonError("scenario_report_too_large")
    return report


class ScenarioStore:
    """POSIX descriptor-anchored scenario custody and exact-source handoff."""

    def __init__(self, root: str) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str, str]:
        _id(world_id, "world_id")
        return (
            world_id + ".scenario.json",
            world_id + ".scenario.report.json",
            world_id + ".scenario.playable.html",
            world_id + ".scenario.receipt.json",
        )

    @staticmethod
    def _lock(fd: int, world_id: str) -> None:
        try:
            handle = os.open(
                world_id + ".lock",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=fd,
            )
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("scenario_identity_mismatch")
        return world

    def _suite(self, fd: int, world_id: str, world: Any) -> dict[str, Any]:
        suite = strict_json(self.worlds._read(fd, self._names(world_id)[0]))
        return validate_suite(suite, world)

    def propose(self, world_id: str, cases: list[dict[str, Any]]) -> dict[str, Any]:
        world = self.worlds.read(world_id)
        return validate_suite({
            "schema": SCHEMA, "world_id": world_id,
            "world_digest": digest(world), "cases": cases,
            "approved": False, "review_note": "Awaiting explicit scenario review",
        }, world)

    def save(self, world_id: str, suite: Any, *,
             expected_world_digest: str) -> str:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                if digest(world) != expected_world_digest:
                    raise CanonError("scenario_stale_source")
                validate_suite(suite, world)
                if suite["approved"]:
                    raise CanonError("scenario_implicit_approval_forbidden")
                name = self._names(world_id)[0]
                try:
                    self.worlds._read(fd, name)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                else:
                    raise CanonError("scenario_already_exists")
                self.worlds._write(fd, name, canonical(suite))
                return digest(suite)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            suite = self._suite(fd, world_id, world)
            return {"suite": suite, "report": run_suite(suite, world)}
        finally:
            os.close(fd)

    def approve(self, world_id: str, *, expected_suite_digest: str,
                review_note: str) -> str:
        _id(world_id, "world_id")
        _text(review_note, "review_note", 512)
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                suite = self._suite(fd, world_id, world)
                if digest(suite) != expected_suite_digest:
                    raise CanonError("scenario_stale_suite")
                if suite["approved"]:
                    raise CanonError("scenario_already_approved")
                if not run_suite(suite, world)["complete"]:
                    raise CanonError("scenario_assertions_failed")
                updated = strict_json(canonical(suite))
                updated["approved"] = True
                updated["review_note"] = review_note
                validate_suite(updated, world)
                self.worlds._write(fd, self._names(world_id)[0], canonical(updated))
                return digest(updated)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    @staticmethod
    def _outputs(world: Any, suite: Any) -> tuple[dict[str, Any], tuple[bytes, bytes]]:
        report = run_suite(suite, world)
        if not suite["approved"]:
            raise CanonError("scenario_review_required")
        if not report["complete"]:
            raise CanonError("scenario_assertions_failed")
        report_bytes = canonical(report)
        playable = compile_html(world).encode("utf-8")
        if len(playable) > MAX_HTML:
            raise CanonError("scenario_playable_too_large")
        names = ScenarioStore._names(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "suite_digest": digest(suite),
            "report_digest": digest(report),
            "artifacts": {
                names[1]: sha256(report_bytes).hexdigest(),
                names[2]: sha256(playable).hexdigest(),
            },
            "qualification": "reviewed_replay_not_release_certified",
        }
        return receipt, (report_bytes, playable)

    def compile(self, world_id: str, *, expected_suite_digest: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                suite = self._suite(fd, world_id, world)
                if digest(suite) != expected_suite_digest:
                    raise CanonError("scenario_stale_suite")
                receipt, outputs = self._outputs(world, suite)
                names = self._names(world_id)
                for name, data in zip(names[1:3], outputs):
                    self.worlds._write(fd, name, data)
                self.worlds._write(fd, names[3], canonical(receipt))
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
                stored = strict_json(self.worlds._read(fd, names[3]))
                world = self._world(fd, world_id)
                suite = self._suite(fd, world_id, world)
                receipt, outputs = self._outputs(world, suite)
                if stored != receipt:
                    raise CanonError("scenario_receipt_mismatch")
                for name, expected in zip(names[1:3], outputs):
                    if _artifact_read(fd, name) != expected:
                        raise CanonError("scenario_artifact_mismatch", name)
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
