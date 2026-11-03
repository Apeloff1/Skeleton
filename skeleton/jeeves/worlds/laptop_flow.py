"""Laptop-first reviewed world creation, builder handoff and replay custody.

This is a source-level, offline flow. It deliberately does not claim that an
engine executable, Windows installer or consumer device has been qualified.
"""
from __future__ import annotations

from hashlib import sha256
import os
from typing import Any

from .bundle import _artifact_read
from .session import SessionStore
from .studio_engine import StudioEngineStore
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _text, canonical, compile_html,
    digest, edit, propose, prove, strict_json,
)

REVIEW_SCHEMA = "jeeves.world.laptop_review.v1"
BUILDER_SCHEMA = "jeeves.world.builder_handoff.v1"
RECEIPT_SCHEMA = "jeeves.world.laptop_receipt.v1"
MAX_OUTPUT_BYTES = 1572864


class LaptopFlow:
    """A small real consumer path using existing canonical source ownership.

    A review is separate from a proposal. A successful edit does not implicitly
    approve anything; only an explicit operator review writes an approval lease.
    Compilation checks that lease under the same world lock as its source read.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)
        self.sessions = SessionStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str, str]:
        _id(world_id, "world_id")
        return (
            world_id + ".laptop.review.json",
            world_id + ".laptop.builder.json",
            world_id + ".laptop.playable.html",
            world_id + ".laptop.receipt.json",
        )

    def propose(self, brief: Any) -> dict[str, Any]:
        obj = _keys(brief, {"id", "premise", "protagonist", "region", "goal"})
        source = propose(
            world_id=obj["id"], premise=obj["premise"],
            protagonist=obj["protagonist"], region=obj["region"], goal=obj["goal"])
        source_digest = self.worlds.publish(source, create=True)
        return {
            "world_id": source["id"], "source_digest": source_digest,
            "proof": prove(source).as_dict(), "review_required": True,
            "qualification": "typed_proposal_not_approved",
        }

    def inspect(self, world_id: str) -> dict[str, Any]:
        world = self.worlds.read(world_id)
        source_digest = digest(world)
        fd = self.worlds._directory()
        try:
            try:
                review = strict_json(self.worlds._read(fd, self._names(world_id)[0]))
                reviewed = self._validate_review(review, world)
            except CanonError as exc:
                if exc.code in {"not_found", "review_stale_source"}:
                    reviewed = False
                else:
                    raise
        finally:
            os.close(fd)
        return {
            "world": world, "source_digest": source_digest,
            "proof": prove(world).as_dict(), "reviewed": reviewed,
            "qualification": "reviewed_source" if reviewed else "review_required",
        }

    @staticmethod
    def _validate_review(review: Any, world: Any) -> bool:
        obj = _keys(review, {"schema", "world_id", "source_digest", "review_note"})
        if obj["schema"] != REVIEW_SCHEMA or obj["world_id"] != world["id"]:
            raise CanonError("review_invalid")
        _text(obj["review_note"], "review_note", 512)
        if len(obj["review_note"].strip()) < 8:
            raise CanonError("review_note_too_short")
        if obj["source_digest"] != digest(world):
            raise CanonError("review_stale_source")
        return True

    def review(self, world_id: str, expected_digest: str, operation: Any,
               review_note: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        _text(review_note, "review_note", 512)
        if len(review_note.strip()) < 8:
            raise CanonError("review_note_too_short")
        current = self.worlds.read(world_id)
        if digest(current) != expected_digest:
            raise CanonError("stale_source")
        revised = edit(current, operation)
        if digest(revised) == expected_digest:
            raise CanonError("review_requires_change")
        new_digest = self.worlds.publish(revised, expected_digest=expected_digest)
        return self.approve_current(world_id, new_digest, review_note)

    def approve_current(self, world_id: str, expected_digest: str,
                        review_note: str) -> dict[str, Any]:
        """Explicitly approve a pre-existing edited canon without rewriting it.

        Required for worlds already authored through the established operator
        editor; never called by a read-only Jeeves tool.
        """
        _id(world_id, "world_id")
        _text(review_note, "review_note", 512)
        if len(review_note.strip()) < 8:
            raise CanonError("review_note_too_short")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                latest = self._world(fd, world_id)
                if digest(latest) != expected_digest:
                    raise CanonError("stale_source")
                review = {
                    "schema": REVIEW_SCHEMA, "world_id": world_id,
                    "source_digest": expected_digest, "review_note": review_note,
                }
                self.worlds._write(fd, self._names(world_id)[0], canonical(review))
                return {
                    "world_id": world_id, "source_digest": expected_digest,
                    "review_digest": digest(review), "proof": prove(latest).as_dict(),
                    "reviewed": True,
                }
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    @staticmethod
    def _lock(fd: int, world_id: str) -> None:
        try:
            handle = os.open(
                world_id + ".lock",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        source = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(source)
        if source["id"] != world_id:
            raise CanonError("identity_mismatch")
        return source

    def _reviewed(self, fd: int, world_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        world = self._world(fd, world_id)
        try:
            review = strict_json(self.worlds._read(fd, self._names(world_id)[0]))
        except CanonError as exc:
            if exc.code == "not_found":
                raise CanonError("review_required") from None
            raise
        self._validate_review(review, world)
        return world, review

    @staticmethod
    def _outputs(world: Any, review: Any) -> tuple[dict[str, Any], bytes, bytes]:
        proof = prove(world).as_dict()
        html = compile_html(world).encode("utf-8")
        if len(html) > MAX_OUTPUT_BYTES:
            raise CanonError("laptop_html_too_large")
        handoff = {
            "schema": BUILDER_SCHEMA, "world_id": world["id"],
            "source_digest": digest(world), "review_digest": digest(review),
            "canon_proof": proof,
            "scene_nodes": sorted(world["scenes"], key=lambda x: x["id"]),
            "choice_edges": sorted(world["choices"], key=lambda x: x["id"]),
            "ending_nodes": sorted(world["endings"], key=lambda x: x["scene"]),
            "start_scene": world["start"], "player_html_sha256": sha256(html).hexdigest(),
            "session_contract": "jeeves.world.session.v1",
            "qualification": "typed_source_handoff_not_engine_binary_or_device_certified",
        }
        builder = canonical(handoff)
        if len(builder) > MAX_OUTPUT_BYTES:
            raise CanonError("laptop_builder_too_large")
        return handoff, builder, html

    def _expected(self, world_id: str, fd: int) -> tuple[dict[str, Any], bytes, bytes]:
        world, review = self._reviewed(fd, world_id)
        handoff, builder, html = self._outputs(world, review)
        names = self._names(world_id)
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world_id,
            "source_digest": digest(world), "review_digest": digest(review),
            "builder_file": names[1], "builder_sha256": sha256(builder).hexdigest(),
            "html_file": names[2], "html_sha256": sha256(html).hexdigest(),
            "canon_proof_digest": digest(handoff["canon_proof"]),
            "qualification": "source_verified_not_engine_binary_or_device_certified",
        }
        return receipt, builder, html

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                receipt, builder, html = self._expected(world_id, fd)
                if receipt["source_digest"] != expected_digest:
                    raise CanonError("stale_source")
                names = self._names(world_id)
                # Receipt is published last. Interrupted writes are never valid.
                self.worlds._write(fd, names[1], builder)
                self.worlds._write(fd, names[2], html)
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
                receipt, builder, html = self._expected(world_id, fd)
                names = self._names(world_id)
                stored = strict_json(self.worlds._read(fd, names[3]))
                if stored != receipt:
                    raise CanonError("laptop_receipt_mismatch")
                if _artifact_read(fd, names[1]) != builder:
                    raise CanonError("laptop_builder_mismatch")
                if _artifact_read(fd, names[2]) != html:
                    raise CanonError("laptop_html_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def engine_inspect(self, world_id: str, era: str) -> dict[str, Any]:
        """Use the existing Studio Engine owner; never invent missing planes."""
        laptop = self.verify(world_id)
        engine = StudioEngineStore(self.worlds.root).inspect(world_id, era)
        if engine["source_digests"]["world"] != laptop["source_digest"]:
            raise CanonError("laptop_engine_source_mismatch")
        return {"laptop": laptop, "engine": engine}

    def engine_compile(self, world_id: str, era: str,
                       expected_digests: Any) -> dict[str, Any]:
        preview = self.engine_inspect(world_id, era)
        if expected_digests != preview["engine"]["source_digests"]:
            raise CanonError("laptop_engine_stale_source")
        owner = StudioEngineStore(self.worlds.root)
        receipt = owner.compile(world_id, expected_digests, era)
        if owner.verify(world_id) != receipt:
            raise CanonError("laptop_engine_verify_mismatch")
        return {"laptop": self.verify(world_id), "engine": receipt}

    def engine_verify(self, world_id: str) -> dict[str, Any]:
        laptop = self.verify(world_id)
        engine = StudioEngineStore(self.worlds.root).verify(world_id)
        if engine["source_digests"]["world"] != laptop["source_digest"]:
            raise CanonError("laptop_engine_source_mismatch")
        return {"laptop": laptop, "engine": engine}

    def create_session(self, world_id: str, slot: str, imported: Any = None) -> dict[str, Any]:
        lease = self.verify(world_id)["source_digest"]
        return self.sessions.create(world_id, slot, imported=imported,
                                    expected_world_digest=lease)

    def choose(self, world_id: str, slot: str, choice_id: str,
               expected_session_digest: str) -> dict[str, Any]:
        lease = self.verify(world_id)["source_digest"]
        return self.sessions.choose(world_id, slot, choice_id, expected_session_digest,
                                    expected_world_digest=lease)

    def inspect_session(self, world_id: str, slot: str) -> dict[str, Any]:
        lease = self.verify(world_id)["source_digest"]
        return self.sessions.inspect(world_id, slot, expected_world_digest=lease)

    def export_session(self, world_id: str, slot: str) -> dict[str, Any]:
        lease = self.verify(world_id)["source_digest"]
        return self.sessions.export(world_id, slot, expected_world_digest=lease)

    def preflight_restore(self, world_id: str, imported: Any) -> dict[str, Any]:
        """Check a save against the currently approved, compiled world.

        This never creates a player slot. A subsequent restore revalidates the
        same source lease under the session writer lock and remains no-clobber.
        """
        lease = self.verify(world_id)["source_digest"]
        return self.sessions.preflight_import(
            world_id, imported, expected_world_digest=lease)

    def diagnose(self, world_id: str, slot: str | None = None) -> dict[str, Any]:
        """Read-only operator recovery map; never substitutes for verification.

        Every successful stage is proved from the current canonical source.
        A failed stage prevents downstream claims and gives a bounded error code.
        No write, auto-approval, or silent source regeneration occurs.
        """
        _id(world_id, "world_id")
        report: dict[str, Any] = {
            "schema": "jeeves.world.laptop_diagnostic.v1",
            "world_id": world_id, "checks": {},
            "qualification": "diagnostic_only_not_consumer_or_device_certified",
        }
        try:
            current = self.inspect(world_id)
        except CanonError as exc:
            report["checks"]["source"] = {"ok": False, "error": exc.code}
            report["next_action"] = "repair_or_restore_canonical_world_source"
            return report
        report["source_digest"] = current["source_digest"]
        report["checks"]["source"] = {"ok": True}
        report["checks"]["review"] = {"ok": current["reviewed"]}
        if not current["reviewed"]:
            report["next_action"] = "review_and_approve_canonical_source"
            return report
        try:
            self.verify(world_id)
        except CanonError as exc:
            report["checks"]["builder"] = {"ok": False, "error": exc.code}
            report["next_action"] = "compile_and_verify_reviewed_source"
            return report
        report["checks"]["builder"] = {"ok": True}
        if slot is not None:
            try:
                session = self.inspect_session(world_id, slot)
            except CanonError as exc:
                report["checks"]["session"] = {"ok": False, "error": exc.code}
                report["next_action"] = "inspect_session_or_restore_from_trusted_export"
                return report
            report["checks"]["session"] = {
                "ok": True, "session_digest": session["session_digest"],
                "revision": session["revision"],
            }
        report["next_action"] = "source_playable_handoff_ready_for_engine_validation"
        return report
