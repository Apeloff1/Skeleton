"""Reviewed counterfactual endings derived from an actual canonical player save.

No model assertion is treated as a transition. Every hypothetical route is
replayed through the same source-validated transition function as real play.
This is an authoring and review artifact, not player-state mutation.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import html
import os
from typing import Any

from .bundle import _artifact_read
from .session import SessionStore, replay_choices, validate_session
from .world_canon import (
    CanonError, MAX_STATES, WorldStore, _id, _keys, _text, canonical,
    compile_html, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.counterfactual_review.v1"
REPORT_SCHEMA = "jeeves.world.counterfactual_report.v1"
RECEIPT_SCHEMA = "jeeves.world.counterfactual_receipt.v1"
MAX_VARIANTS = 64
MAX_STEPS = 512
MAX_REPORT_BYTES = 1048576


def validate_review(data: Any, world: Any, session: Any) -> dict[str, Any]:
    proof = prove(world)
    validate_session(session, world)
    obj = _keys(data, {
        "schema", "world_id", "world_digest", "session_slot",
        "session_digest", "choices", "prompt", "max_steps",
        "max_variants", "approved", "review_note",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("counterfactual_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != proof.source_digest:
        raise CanonError("counterfactual_world_lease_mismatch")
    _id(obj["session_slot"], "session_slot")
    if obj["session_digest"] != digest(session) or obj["choices"] != session["choices"]:
        raise CanonError("counterfactual_session_lease_mismatch")
    _text(obj["prompt"], "prompt", 2048)
    if type(obj["max_steps"]) is not int or not 0 <= obj["max_steps"] <= MAX_STEPS:
        raise CanonError("counterfactual_step_budget")
    if obj["max_steps"] < len(session["choices"]):
        raise CanonError("counterfactual_step_budget")
    if type(obj["max_variants"]) is not int or not 1 <= obj["max_variants"] <= MAX_VARIANTS:
        raise CanonError("counterfactual_variant_budget")
    if type(obj["approved"]) is not bool:
        raise CanonError("counterfactual_approval_invalid")
    _text(obj["review_note"], "review_note", 512)
    if len(canonical(obj)) > 524288:
        raise CanonError("counterfactual_source_too_large")
    return obj


def propose_review(world: Any, session: Any, *, slot: str, prompt: str,
                   max_steps: int = 128, max_variants: int = 64) -> dict[str, Any]:
    prove(world)
    validate_session(session, world)
    _id(slot, "session_slot")
    proposal = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "session_slot": slot,
        "session_digest": digest(session), "choices": list(session["choices"]),
        "prompt": prompt, "max_steps": max_steps,
        "max_variants": max_variants, "approved": False,
        "review_note": "Original author review required",
    }
    return validate_review(proposal, world, session)


def edit_review(data: Any, world: Any, session: Any, operation: Any) -> dict[str, Any]:
    validate_review(data, world, session)
    op = _keys(operation, {"action", "value"})
    candidate = strict_json(canonical(data))
    if op["action"] == "set_limits":
        limits = _keys(op["value"], {"max_steps", "max_variants"})
        candidate.update(limits)
    elif op["action"] == "set_prompt":
        _keys(op["value"], {"prompt"})
        candidate["prompt"] = op["value"]["prompt"]
    else:
        raise CanonError("counterfactual_unsupported_edit")
    candidate["approved"] = False
    candidate["review_note"] = "Source changed; renewed review required"
    return validate_review(candidate, world, session)


def _available(world: Any, scene: str, flags: frozenset[str]) -> list[dict[str, Any]]:
    return sorted(
        (edge for edge in world["choices"]
         if edge["from"] == scene and set(edge["requires"]) <= flags),
        key=lambda edge: edge["id"],
    )


def _complete(world: Any, prefix: tuple[str, ...], alternative: str,
              budget: int) -> tuple[str, ...]:
    """Bounded BFS after a real prefix and one alternate choice.

    Exhaustion is not mistaken for proof of unreachable. Every returned path
    is independently replayed, including its prefix and alternative.
    """
    initial_trace = prefix + (alternative,)
    if len(initial_trace) > budget:
        raise CanonError("counterfactual_step_budget_exhausted")
    initial = replay_choices(world, list(initial_trace))
    endings = {item["scene"] for item in world["endings"]}
    if initial["scene"] in endings:
        return initial_trace
    state = (initial["scene"], frozenset(initial["flags"]))
    queue = deque([(state, initial_trace)])
    seen = {state}
    truncated = False
    while queue:
        (scene, flags), trace = queue.popleft()
        edges = _available(world, scene, flags)
        if len(trace) >= budget:
            truncated |= bool(edges)
            continue
        for edge in edges:
            next_flags = flags | frozenset(edge["grants"])
            next_trace = trace + (edge["id"],)
            if edge["to"] in endings:
                replay = replay_choices(world, list(next_trace))
                if replay["scene"] != edge["to"] or replay["ending"] is None:
                    raise CanonError("counterfactual_replay_disagreement")
                return next_trace
            next_state = (edge["to"], next_flags)
            if next_state in seen:
                continue
            if len(seen) >= MAX_STATES:
                raise CanonError("counterfactual_state_budget_exhausted")
            seen.add(next_state)
            queue.append((next_state, next_trace))
    if truncated:
        raise CanonError("counterfactual_step_budget_exhausted")
    raise CanonError("counterfactual_no_ending")


def build_report(data: Any, world: Any, session: Any) -> dict[str, Any]:
    validate_review(data, world, session)
    original = replay_choices(world, session["choices"])
    choices = session["choices"]
    variants: list[dict[str, Any]] = []
    for index, step in enumerate(original["steps"][:-1] if choices else []):
        flags = frozenset(step["flags"])
        for edge in _available(world, step["scene"], flags):
            if edge["id"] == choices[index]:
                continue
            if len(variants) >= data["max_variants"]:
                raise CanonError("counterfactual_variant_budget_exhausted")
            trace = _complete(world, tuple(choices[:index]), edge["id"],
                              data["max_steps"])
            outcome = replay_choices(world, list(trace))
            variants.append({
                "divergence_step": index,
                "original_choice": choices[index],
                "alternative_choice": edge["id"],
                "choice_witness": list(trace),
                "ending": outcome["ending"],
                "scene": outcome["scene"],
                "flags": outcome["flags"],
                "ending_changed": outcome["ending"] != original["ending"],
                "flags_added": sorted(set(outcome["flags"]) - set(original["flags"])),
                "flags_removed": sorted(set(original["flags"]) - set(outcome["flags"])),
            })
    report = {
        "schema": REPORT_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "session_digest": digest(session),
        "review_digest": digest(data), "prompt": data["prompt"],
        "original": {
            "choice_witness": list(choices), "scene": original["scene"],
            "ending": original["ending"], "flags": original["flags"],
        },
        "variants": variants, "complete": True,
        "qualification": "deterministic_source_replay_not_release_certified",
    }
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise CanonError("counterfactual_report_too_large")
    return report


def approve_review(data: Any, world: Any, session: Any, note: str) -> dict[str, Any]:
    validate_review(data, world, session)
    _text(note, "review_note", 512)
    build_report(data, world, session)
    candidate = strict_json(canonical(data))
    candidate["approved"] = True
    candidate["review_note"] = note
    return validate_review(candidate, world, session)


def compile_review(data: Any, world: Any, session: Any) -> dict[str, Any]:
    validate_review(data, world, session)
    if not data["approved"]:
        raise CanonError("counterfactual_review_required")
    return build_report(data, world, session)


def render_report(report: Any) -> bytes:
    if type(report) is not dict or report.get("schema") != REPORT_SCHEMA:
        raise CanonError("counterfactual_report_schema")
    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; ",
        "script-src 'none'; style-src 'none'; img-src 'none'; ",
        "base-uri 'none'; form-action 'none'\">",
        "<title>Reviewed world branch consequences</title></head><body>",
        "<main><h1>Reviewed branch consequences</h1>",
        "<p>Original author prompt: ", esc(report["prompt"]), "</p>",
        "<p>World source SHA-256: ", esc(report["world_digest"]), "</p>",
        "<p>Original ending: ", esc(report["original"]["ending"]), "</p>",
        "<p>Original choices: ", esc(", ".join(report["original"]["choice_witness"])), "</p>",
        "<ol>",
    ]
    for variant in report["variants"]:
        parts.extend([
            "<li>At decision ", esc(variant["divergence_step"]),
            ", choose ", esc(variant["alternative_choice"]),
            " instead of ", esc(variant["original_choice"]),
            ". Ending: ", esc(variant["ending"]),
            ". Witness: ", esc(", ".join(variant["choice_witness"])),
            ". Changed: ", esc(variant["ending_changed"]), "</li>",
        ])
    parts.extend(["</ol><p>Deterministic source replay; no device or release qualification.</p>",
                  "</main></body></html>\n"])
    return "".join(parts).encode("utf-8")


class CounterfactualStore:
    """Same world-level exclusive lock as canonical session and world editors."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)
        self.sessions = SessionStore(root)

    @staticmethod
    def _name(world_id: str, slot: str) -> str:
        return _id(world_id, "world_id") + "." + _id(slot, "slot") + ".counterfactual.json"

    @staticmethod
    def _names(world_id: str, slot: str) -> tuple[str, str, str, str]:
        stem = _id(world_id, "world_id") + "." + _id(slot, "slot") + ".counterfactual"
        return (stem + ".playable.html", stem + ".report.html",
                stem + ".report.json", stem + ".receipt.json")

    def _sources(self, fd: int, world_id: str, slot: str):
        _id(world_id, "world_id")
        _id(slot, "slot")
        world = self.sessions._world(fd, world_id)
        session = self.sessions._session(fd, world_id, slot, world)
        return world, session

    def _read(self, fd: int, world_id: str, slot: str, world: Any, session: Any):
        review = validate_review(
            strict_json(self.worlds._read(fd, self._name(world_id, slot))),
            world, session,
        )
        if review["session_slot"] != slot:
            raise CanonError("counterfactual_slot_mismatch")
        return review

    def _lock(self, fd: int, world_id: str) -> int:
        _id(world_id, "world_id")
        try:
            return os.open(world_id + ".lock",
                           os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                           0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None

    def read(self, world_id: str, slot: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world, session = self._sources(fd, world_id, slot)
            return self._read(fd, world_id, slot, world, session)
        finally:
            os.close(fd)

    def publish(self, world_id: str, slot: str, data: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        _id(world_id, "world_id")
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world, session = self._sources(fd, world_id, slot)
                validate_review(data, world, session)
                if data["session_slot"] != slot:
                    raise CanonError("counterfactual_slot_mismatch")
                try:
                    old = digest(self._read(fd, world_id, slot, world, session))
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("already_exists")
                elif old is None or old != expected_digest:
                    raise CanonError("stale_counterfactual")
                self.worlds._write(fd, self._name(world_id, slot), canonical(data))
                return digest(data)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, world: Any, session: Any, review: Any):
        report = compile_review(review, world, session)
        artifacts = [
            compile_html(world).encode("utf-8"),
            render_report(report), canonical(report),
        ]
        names = self._names(world["id"], review["session_slot"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "session_digest": digest(session),
            "review_digest": digest(review),
            "artifacts": {
                name: sha256(payload).hexdigest()
                for name, payload in zip(names[:3], artifacts)
            },
            "qualification": "operator_review_only_not_release_certified",
        }
        return receipt, artifacts

    def compile(self, world_id: str, slot: str, expected_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world, session = self._sources(fd, world_id, slot)
                review = self._read(fd, world_id, slot, world, session)
                if digest(review) != expected_digest:
                    raise CanonError("stale_counterfactual")
                receipt, artifacts = self._outputs(world, session, review)
                names = self._names(world_id, slot)
                for name, payload in zip(names[:3], artifacts):
                    self.worlds._write(fd, name, payload)
                self.worlds._write(fd, names[3], canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str, slot: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world, session = self._sources(fd, world_id, slot)
                review = self._read(fd, world_id, slot, world, session)
                expected, artifacts = self._outputs(world, session, review)
                names = self._names(world_id, slot)
                if strict_json(self.worlds._read(fd, names[3])) != expected:
                    raise CanonError("counterfactual_receipt_mismatch")
                for name, payload in zip(names[:3], artifacts):
                    if _artifact_read(fd, name) != payload:
                        raise CanonError("counterfactual_artifact_mismatch", name)
                return expected
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
