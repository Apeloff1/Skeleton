"""Laptop-first reviewed world creation, builder handoff and replay custody.

This is a source-level, offline flow. It deliberately does not claim that an
engine executable, Windows installer or consumer device has been qualified.
"""
from __future__ import annotations

from hashlib import sha256
import os
from typing import Any

from .bundle import _artifact_read
from .session import (SessionStore, SCHEMA as SESSION_SCHEMA, export_session as portable_export,
                      import_session as portable_import, replay_choices, validate_session)
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
        """Inspect source and approval in one canonical writer snapshot."""
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source_digest = digest(world)
                try:
                    review = strict_json(self.worlds._read(fd, self._names(world_id)[0]))
                    reviewed = self._validate_review(review, world)
                except CanonError as exc:
                    if exc.code in {"not_found", "review_stale_source"}:
                        reviewed = False
                    else:
                        raise
                return {
                    "world": world, "source_digest": source_digest,
                    "proof": prove(world).as_dict(), "reviewed": reviewed,
                    "qualification": "reviewed_source" if reviewed else "review_required",
                }
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

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

    def preview_edit(self, world_id: str, expected_digest: str, operation: Any) -> dict[str, Any]:
        """Reviewable, side-effect-free typed edit with exact source CAS.

        The candidate is never approved or published by preview. A reviewer must
        subsequently submit the identical operation against the original digest.
        """
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                current = self._world(fd, world_id)
                if digest(current) != expected_digest:
                    raise CanonError("stale_source")
                candidate = edit(current, operation)
                candidate_digest = digest(candidate)
                if candidate_digest == expected_digest:
                    raise CanonError("review_requires_change")
                before = {kind: {item["id" if kind != "endings" else "scene"]: item
                         for item in current[kind]}
                          for kind in ("scenes", "choices", "endings")}
                after = {kind: {item["id" if kind != "endings" else "scene"]: item
                        for item in candidate[kind]}
                         for kind in ("scenes", "choices", "endings")}
                changes = {}
                for kind in ("scenes", "choices", "endings"):
                    changes[kind] = {
                        "added": sorted(after[kind].keys() - before[kind].keys()),
                        "removed": sorted(before[kind].keys() - after[kind].keys()),
                        "modified": sorted(k for k in before[kind].keys() & after[kind].keys()
                                           if before[kind][k] != after[kind][k]),
                    }
                return {
                    "schema": "jeeves.world.review_preview.v1",
                    "world_id": world_id,
                    "source_digest": expected_digest,
                    "candidate_digest": candidate_digest,
                    "operation_digest": digest(operation),
                    "changes": changes,
                    "proof": prove(candidate).as_dict(),
                    "reviewed": False,
                    "published": False,
                }
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def review(self, world_id: str, expected_digest: str, operation: Any,
               review_note: str, *, expected_candidate_digest: str | None = None,
               expected_operation_digest: str | None = None) -> dict[str, Any]:
        """Publish an explicitly reviewed edit under one canonical writer lease.

        Source CAS, proof, and review custody share a single lock. A concurrent
        editor cannot slip a revision between publication and approval. If the
        second durable write fails, the source remains unapproved (fail closed).
        """
        _id(world_id, "world_id")
        _text(review_note, "review_note", 512)
        if len(review_note.strip()) < 8:
            raise CanonError("review_note_too_short")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                current = self._world(fd, world_id)
                if digest(current) != expected_digest:
                    raise CanonError("stale_source")
                if expected_operation_digest is not None:
                    if (not isinstance(expected_operation_digest, str) or
                            len(expected_operation_digest) != 64 or
                            expected_operation_digest != digest(operation)):
                        raise CanonError("review_operation_mismatch")
                revised = edit(current, operation)
                new_digest = digest(revised)
                if expected_candidate_digest is not None:
                    if (not isinstance(expected_candidate_digest, str) or
                            len(expected_candidate_digest) != 64 or
                            expected_candidate_digest != new_digest):
                        raise CanonError("review_candidate_mismatch")
                if new_digest == expected_digest:
                    raise CanonError("review_requires_change")
                proof = prove(revised).as_dict()
                review = {
                    "schema": REVIEW_SCHEMA, "world_id": world_id,
                    "source_digest": new_digest, "review_note": review_note,
                }
                # Revoke earlier approvals before changing source bytes.
                # Otherwise an A -> B -> A retry could borrow a previously
                # valid review if the next source/review pair is interrupted.
                try:
                    os.unlink(self._names(world_id)[0], dir_fd=fd)
                except FileNotFoundError:
                    pass
                else:
                    os.fsync(fd)
                self.worlds._write(fd, world_id + ".json", canonical(revised))
                self.worlds._write(fd, self._names(world_id)[0], canonical(review))
                return {
                    "world_id": world_id, "source_digest": new_digest,
                    "review_digest": digest(review), "proof": proof,
                    "reviewed": True,
                }
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

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
        except OSError as exc:
            # Host filesystem failures must not escape as untyped tracebacks.
            # Never remove a lock we did not successfully create.
            raise CanonError("lease_unavailable") from exc
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
        try:
            self._validate_review(review, world)
        except CanonError as exc:
            # A successfully written world with an interrupted review write
            # has no approval, even if an old review remains on disk.
            if exc.code == "review_stale_source":
                raise CanonError("review_required") from None
            raise
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

    def _verified_snapshot(self, fd: int, world_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """Validate the exact compiled artifacts while caller owns world lock."""
        receipt, builder, html = self._expected(world_id, fd)
        names = self._names(world_id)
        stored = strict_json(self.worlds._read(fd, names[3]))
        if stored != receipt:
            raise CanonError("laptop_receipt_mismatch")
        if _artifact_read(fd, names[1]) != builder:
            raise CanonError("laptop_builder_mismatch")
        if _artifact_read(fd, names[2]) != html:
            raise CanonError("laptop_html_mismatch")
        world = self._world(fd, world_id)
        if digest(world) != receipt["source_digest"]:
            raise CanonError("laptop_source_changed_after_verify")
        return receipt, world

    def verify(self, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                return self._verified_snapshot(fd, world_id)[0]
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def engine_inspect(self, world_id: str, era: str) -> dict[str, Any]:
        """Read laptop and Studio Engine previews under one canonical lease.

        The Studio Engine owner still performs all nine-plane validation.
        Preview never synthesizes missing sources or authorizes compilation.
        """
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                laptop, _world = self._verified_snapshot(fd, world_id)
                engine = StudioEngineStore(self.worlds.root)._inspect_snapshot(
                    fd, world_id, era)
                if engine["source_digests"]["world"] != laptop["source_digest"]:
                    raise CanonError("laptop_engine_source_mismatch")
                return {"laptop": laptop, "engine": engine}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def engine_compile(self, world_id: str, era: str,
                       expected_digests: Any) -> dict[str, Any]:
        preview = self.engine_inspect(world_id, era)
        if expected_digests != preview["engine"]["source_digests"]:
            raise CanonError("laptop_engine_stale_source")
        owner = StudioEngineStore(self.worlds.root)
        receipt = owner.compile(world_id, expected_digests, era)
        # Both receipts must be verified under ONE canonical world lease.
        # Independent sequential verifiers could accept different revisions.
        final = self.engine_verify(world_id)
        if (final["engine"] != receipt or
                final["engine"]["source_digests"] != expected_digests or
                final["laptop"] != preview["laptop"]):
            raise CanonError("laptop_engine_source_mismatch")
        return final

    def engine_verify(self, world_id: str) -> dict[str, Any]:
        """Prove the laptop player and Studio Engine recipe in one snapshot."""
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                laptop, _world = self._verified_snapshot(fd, world_id)
                engine = StudioEngineStore(self.worlds.root)._verify_snapshot(fd, world_id)
                if engine["source_digests"]["world"] != laptop["source_digest"]:
                    raise CanonError("laptop_engine_source_mismatch")
                return {"laptop": laptop, "engine": engine}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _session_guard(self, fd: int, world_id: str) -> None:
        """Verify review, playable, builder and receipt under session's lock."""
        self._verified_snapshot(fd, world_id)

    def create_session(self, world_id: str, slot: str, imported: Any = None) -> dict[str, Any]:
        return self.sessions.create(
            world_id, slot, imported=imported, source_guard=self._session_guard)

    def choose(self, world_id: str, slot: str, choice_id: str,
               expected_session_digest: str) -> dict[str, Any]:
        return self.sessions.choose(
            world_id, slot, choice_id, expected_session_digest,
            source_guard=self._session_guard)

    def inspect_session(self, world_id: str, slot: str) -> dict[str, Any]:
        return self.sessions.inspect(world_id, slot, source_guard=self._session_guard)

    def export_session(self, world_id: str, slot: str) -> dict[str, Any]:
        return self.sessions.export(world_id, slot, source_guard=self._session_guard)

    def preflight_restore(self, world_id: str, imported: Any) -> dict[str, Any]:
        """Read-only restore check pinned to the approved playable lease."""
        return self.sessions.preflight_import(
            world_id, imported, source_guard=self._session_guard)

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
            report["next_action"] = (
                "retry_after_current_writer_finishes" if exc.code == "lease_busy"
                else "inspect_custody_permissions_without_removing_foreign_locks" if exc.code == "lease_unavailable"
                else "repair_or_restore_canonical_world_source")
            return report
        report["source_digest"] = current["source_digest"]
        report["checks"]["source"] = {"ok": True}
        report["checks"]["review"] = {"ok": current["reviewed"]}
        if not current["reviewed"]:
            report["next_action"] = "review_and_approve_canonical_source"
            return report
        try:
            verified_receipt = self.verify(world_id)
        except CanonError as exc:
            report["checks"]["builder"] = {"ok": False, "error": exc.code}
            report["next_action"] = (
                "retry_after_current_writer_finishes" if exc.code == "lease_busy"
                else "inspect_custody_permissions_without_removing_foreign_locks" if exc.code == "lease_unavailable"
                else "compile_and_verify_reviewed_source")
            return report
        report["checks"]["builder"] = {"ok": True}
        if slot is not None:
            try:
                session = self.inspect_session(world_id, slot)
            except CanonError as exc:
                report["checks"]["session"] = {"ok": False, "error": exc.code}
                report["next_action"] = (
                    "retry_after_current_writer_finishes" if exc.code == "lease_busy"
                    else "inspect_custody_permissions_without_removing_foreign_locks" if exc.code == "lease_unavailable"
                    else "inspect_session_or_restore_from_trusted_export")
                return report
            report["checks"]["session"] = {
                "ok": True, "session_digest": session["session_digest"],
                "revision": session["revision"],
            }
        try:
            acceptance = self.acceptance(world_id, slot)
        except CanonError as exc:
            report["checks"]["acceptance"] = {"ok": False, "error": exc.code}
            report["next_action"] = (
                "retry_after_current_writer_finishes" if exc.code == "lease_busy"
                else "inspect_custody_permissions_without_removing_foreign_locks" if exc.code == "lease_unavailable"
                else "repair_canonical_replay_or_save_before_engine_handoff")
            return report
        # Separate diagnostic stages may observe different approved revisions.
        # Never report a green handoff by mixing two valid generations, including
        # a player save changed after the initial session inspection.
        observed_session = report["checks"].get("session")
        accepted_session = acceptance.get("existing_session")
        session_changed = (
            slot is not None and (
                not isinstance(accepted_session, dict) or
                accepted_session.get("slot") != slot or
                accepted_session.get("session_digest") != observed_session.get("session_digest") or
                accepted_session.get("revision") != observed_session.get("revision") or
                accepted_session.get("restorable") is not True
            )
        )
        if (acceptance["source_digest"] != current["source_digest"] or
                acceptance["receipt_digest"] != digest(verified_receipt) or
                session_changed):
            report["checks"]["acceptance"] = {
                "ok": False, "error": "laptop_diagnostic_source_changed"}
            report["next_action"] = "restart_diagnostic_after_source_change"
            return report
        report["checks"]["acceptance"] = {
            "ok": True, "ending_witness_count": len(acceptance["ending_witnesses"]),
            "portable_roundtrip_verified": acceptance["portable_roundtrip_verified"],
            "persisted_slot_verified": acceptance["persisted_slot_verified"],
        }
        report["next_action"] = "source_playable_handoff_ready_for_engine_validation"
        return report

    def acceptance(self, world_id: str, slot: str | None = None) -> dict[str, Any]:
        """Read-only source acceptance under one canonical world writer lease.

        Every ending replay and optional persisted save preflight observes the
        same reviewed world and compiled artifacts. No player slot is created.
        This does not qualify a native engine, model, device or installation.
        """
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                receipt, world = self._verified_snapshot(fd, world_id)
                proof = prove(world).as_dict()
                witnesses = proof["ending_witnesses"]
                if len(witnesses) > 128 or sum(map(len, witnesses.values())) > 8192:
                    raise CanonError("laptop_acceptance_budget")
                checked: list[dict[str, Any]] = []
                for ending_scene, choices in sorted(witnesses.items()):
                    replay = replay_choices(world, choices)
                    if replay["scene"] != ending_scene or replay["ending"] is None:
                        raise CanonError("laptop_acceptance_ending_mismatch")
                    state = validate_session({
                        "schema": SESSION_SCHEMA, "world_id": world_id,
                        "world_digest": receipt["source_digest"], "choices": list(choices),
                        "scene": replay["scene"], "flags": replay["flags"],
                        "ending": replay["ending"], "revision": len(choices),
                    }, world)
                    restored = portable_import(portable_export(state, world), world)
                    if restored != state:
                        raise CanonError("laptop_acceptance_restore_mismatch")
                    checked.append({
                        "ending_scene": ending_scene, "choice_ids": list(choices),
                        "ending": state["ending"], "session_digest": digest(state),
                    })
                existing = None
                if slot is not None:
                    # The acceptance caller already owns the canonical world
                    # lease. Re-entering LaptopFlow.inspect_session/export/
                    # preflight_restore would invoke verify() and deadlock on
                    # that same non-reentrant lease (lease_busy). Read through
                    # the SessionStore using the pinned source digest instead.
                    # Its read-only methods revalidate replay and save checks,
                    # while the outer lease excludes concurrent world/session
                    # writers for the entire three-step inspection.
                    source_lease = receipt["source_digest"]
                    view = self.sessions.inspect(
                        world_id, slot, expected_world_digest=source_lease)
                    exported = self.sessions.export(
                        world_id, slot, expected_world_digest=source_lease)
                    preview = self.sessions.preflight_import(
                        world_id, exported, expected_world_digest=source_lease)
                    if preview["session_digest"] != view["session_digest"]:
                        raise CanonError("laptop_acceptance_session_mismatch")
                    existing = {
                        "slot": slot, "session_digest": view["session_digest"],
                        "revision": preview["revision"], "restorable": preview["restorable"],
                    }
                return {
                    "schema": "jeeves.world.laptop_acceptance.v1",
                    "world_id": world_id, "source_digest": receipt["source_digest"],
                    "review_digest": receipt["review_digest"],
                    "receipt_digest": digest(receipt),
                    "ending_witnesses": checked, "portable_roundtrip_verified": True,
                    "persisted_slot_verified": existing is not None,
                    "existing_session": existing,
                    "qualification": "offline_source_acceptance_not_engine_or_device_certified",
                }
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
