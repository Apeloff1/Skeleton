"""Executable adversarial mirror room for genuinely playable original games.

Every counted attempt exercises the Python game engine or the materialized
package and records a digest-bound result. Expected rejection is a PASS only
when a deliberately forged replay, state or action is actually refused.
Neither random text review nor an LLM's confidence counts as an attempt.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
import random
from typing import Callable

from .contracts import canonical_digest
from .dual_runtime_export import DualRuntimePackage, DualRuntimeExportError
from .playable_compiler import CompiledPlayableProject
from .playable_simulation import (
    GameReplay, GameplayError, PlayState, advance, initial_state,
    play_actions, verify_replay,
)


class MirrorRoomError(ValueError):
    """Missing proof, unsafe probe budget or compromised game invariants."""


@dataclass(frozen=True, slots=True)
class MirrorProbe:
    index: int
    family: str
    expected: str
    observed: str
    passed: bool
    evidence_digest: str

    def to_payload(self) -> dict[str, object]:
        return {
            "index": self.index, "family": self.family,
            "expected": self.expected, "observed": self.observed,
            "passed": self.passed, "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True, slots=True)
class MirrorReport:
    world_digest: str
    proof_digest: str
    package_digest: str
    probes: tuple[MirrorProbe, ...]
    failures: tuple[int, ...]

    @property
    def passed(self) -> bool:
        return bool(self.probes) and not self.failures

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.mirror_room.v1",
            "world_digest": self.world_digest,
            "proof_digest": self.proof_digest,
            "package_digest": self.package_digest,
            "attempts": len(self.probes),
            "families": sorted({p.family for p in self.probes}),
            "passed_count": sum(p.passed for p in self.probes),
            "failed_count": len(self.failures),
            "failures": list(self.failures),
            "probes": [p.to_payload() for p in self.probes],
            "adversarial_runtime": "python-reference-simulator",
            "native_hardware_reviewed": False,
            "human_ux_reviewed": False,
            "copyright_similarity_cleared": False,
        }


def _expect_rejected(attack: Callable[[], object]) -> str:
    try:
        attack()
    except (GameplayError, DualRuntimeExportError, PermissionError):
        return "rejected"
    except Exception as exc:
        return "unexpected_exception:" + type(exc).__name__
    return "accepted"


def _sha(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def review_playable_project(
    project: CompiledPlayableProject,
    package: DualRuntimePackage,
    *,
    authorized: bool,
    attempts: int = 128,
) -> MirrorReport:
    """Replay a real winning proof, then run deterministic adversarial probes.

    Attacks are bounded to 64-512 attempts and isolated to in-memory copies.
    Forgeries must be rejected by *real runtime validation*; no exception is
    interpreted as success other than a specific expected domain exception.
    """
    if not authorized:
        raise PermissionError("adversarial mirror-room execution requires authorization")
    if not isinstance(project, CompiledPlayableProject) or not isinstance(package, DualRuntimePackage):
        raise MirrorRoomError("typed built source and dual-runtime package required")
    if type(attempts) is not int or not 64 <= attempts <= 512:
        raise MirrorRoomError("mirror-room attempt budget must be 64 to 512")
    world = project.world
    proof = project.proof
    verify_replay(world, proof, authorized=True)
    if proof.final_state.status != "won":
        raise MirrorRoomError("only a replay-proven game can enter the mirror room")
    if (package.manifest["world_digest"] != world.digest
            or package.manifest["proof_digest"] != proof.digest):
        raise MirrorRoomError("package belongs to another game")
    if set(package.manifest["files"]) | {"release.json"} != set(package.files):
        raise MirrorRoomError("package file inventory mismatch")
    manifest_body = {
        key: value for key, value in package.manifest.items()
        if key != "manifest_digest"
    }
    if package.manifest.get("manifest_digest") != canonical_digest(manifest_body):
        raise MirrorRoomError("release manifest metadata digest changed")
    serialized_manifest = (
        json.dumps(package.manifest, sort_keys=True, ensure_ascii=True,
                   separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")
    if package.files["release.json"] != serialized_manifest:
        raise MirrorRoomError("serialized release manifest changed")
    for name, expected in package.manifest["files"].items():
        if _sha(package.files[name]) != expected:
            raise MirrorRoomError("package file changed before adversarial review")
    baseline_actions = tuple(r.action for r in proof.action_receipts)
    if not baseline_actions:
        raise MirrorRoomError("game replay proof has no inputs")
    rng = random.Random(int(world.digest[:16], 16))
    states: list[PlayState] = [initial_state(world, authorized=True)]
    for action in baseline_actions:
        states.append(advance(world, states[-1], action, authorized=True))
    if states[-1] != proof.final_state:
        raise MirrorRoomError("reference trace no longer converges to proof")
    findings: list[MirrorProbe] = []
    directions = ("up", "left", "right", "down")
    package_paths = tuple(sorted(package.manifest["files"]))
    for index in range(attempts):
        family = index % 12
        cursor = rng.randrange(len(baseline_actions))
        state = states[cursor]
        chosen = directions[rng.randrange(4)]
        case_id = {
            "index": index, "state": state.digest,
            "world": world.digest, "sample": cursor,
            "direction": chosen,
        }
        expected = "rejected"
        if family == 0:
            name = "valid-prefix-replay"
            expected = "reproduced"
            length = min(cursor + 1, 24)
            try:
                observed = "reproduced" if play_actions(
                    world, baseline_actions[:length], authorized=True,
                ).final_state == states[length] else "diverged"
            except Exception as exc:
                observed = "unexpected_exception:" + type(exc).__name__
        elif family == 1:
            name = "unauthorized-game-action"
            observed = _expect_rejected(
                lambda: advance(world, state, chosen, authorized=False))
        elif family == 2:
            name = "injected-game-action"
            injected = ("teleport", "up;rm -rf /", "", "UP")[index % 4]
            observed = _expect_rejected(
                lambda: advance(world, state, injected, authorized=True))
        elif family == 3:
            name = "forged-world-identity"
            forged = replace(state, world_digest="0" * 64 if world.digest != "0" * 64 else "1" * 64)
            observed = _expect_rejected(
                lambda: advance(world, forged, chosen, authorized=True))
        elif family == 4:
            name = "inflated-health-state"
            forged = replace(state, health=world.intent.starting_health + index + 1)
            observed = _expect_rejected(
                lambda: advance(world, forged, chosen, authorized=True))
        elif family == 5:
            name = "tampered-proof-chain"
            row = proof.action_receipts[0]
            altered = replace(row, before_digest="f" * 64)
            # The typed replay constructor itself may refuse a forged boundary.
            # Construct it *inside* the rejection probe so this counts as
            # correctly blocked tampering, rather than crashing the mirror.
            observed = _expect_rejected(
                lambda: verify_replay(world,
                    replace(proof, action_receipts=(altered, *proof.action_receipts[1:])),
                    authorized=True))
        elif family == 6:
            name = "tampered-proof-final-state"
            observed = _expect_rejected(
                lambda: verify_replay(world,
                    replace(proof, final_state=replace(
                        proof.final_state, score=proof.final_state.score + index + 1)),
                    authorized=True))
        elif family == 7:
            name = "tampered-proof-action"
            row = proof.action_receipts[0]
            observed = _expect_rejected(
                lambda: verify_replay(world,
                    replace(proof, action_receipts=(
                        replace(row, action="unsupported"), *proof.action_receipts[1:])),
                    authorized=True))
        elif family == 8:
            name = "terminal-replay-overflow"
            observed = _expect_rejected(
                lambda: advance(world, proof.final_state, chosen, authorized=True))
        elif family == 9:
            name = "tampered-source-file"
            path = package_paths[index % len(package_paths)]
            case_id["file"] = path
            bad_files = dict(package.files)
            bad_files[path] += b"malicious-payload"
            observed = _expect_rejected(
                lambda: DualRuntimePackage(bad_files, package.manifest))
        elif family == 10:
            name = "tampered-release-manifest"
            forged = dict(package.manifest)
            forged["files"] = dict(forged["files"])
            path = package_paths[index % len(package_paths)]
            case_id["file"] = path
            forged["files"][path] = "0" * 64
            observed = _expect_rejected(
                lambda: DualRuntimePackage(package.files, forged))
        else:
            name = "deterministic-single-transition"
            expected = "reproduced"
            try:
                actual = advance(world, state, baseline_actions[cursor], authorized=True)
                observed = "reproduced" if actual == states[cursor + 1] else "diverged"
            except Exception as exc:
                observed = "unexpected_exception:" + type(exc).__name__
        case_id["family"] = name
        case_id["expected"] = expected
        case_id["observed"] = observed
        findings.append(MirrorProbe(
            index=index, family=name, expected=expected,
            observed=observed, passed=observed == expected,
            evidence_digest=canonical_digest(case_id),
        ))
    failures = tuple(probe.index for probe in findings if not probe.passed)
    return MirrorReport(
        world_digest=world.digest, proof_digest=proof.digest,
        package_digest=str(package.manifest["manifest_digest"]),
        probes=tuple(findings), failures=failures,
    )


__all__ = [
    "MirrorRoomError", "MirrorProbe", "MirrorReport", "review_playable_project",
]
