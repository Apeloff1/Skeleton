"""Adversarial mirror room for the second, living-world game genre.

A 128+ attack campaign exercises the real NPC/quest reference state machine,
not a text-model verdict. Observations are content-addressed to the original
world, state and executable package. Native verification is a distinct gate.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import random
from hashlib import sha256

from .contracts import canonical_digest
from .living_story_runtime import (
    StoryError, StoryWorld, StoryReplay, first_story_state,
    story_choices, story_step, story_play, story_verify, npc_region,
)
from .living_story_export import StoryPackage, StoryExportError


class StoryMirrorError(ValueError):
    """Narrative world failed executable adversarial review."""


@dataclass(frozen=True, slots=True)
class StoryMirrorProbe:
    index: int
    family: str
    passed: bool
    expected: str
    observed: str
    evidence_digest: str

    def payload(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class StoryMirrorReport:
    world_digest: str
    proof_digest: str
    package_digest: str
    probes: tuple[StoryMirrorProbe, ...]

    @property
    def passed(self) -> bool:
        return bool(self.probes) and all(p.passed for p in self.probes)

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())

    def payload(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.story_mirror_room.v1",
            "world_digest": self.world_digest,
            "proof_digest": self.proof_digest,
            "package_digest": self.package_digest,
            "attempts": len(self.probes),
            "passed_count": sum(p.passed for p in self.probes),
            "failed_count": sum(not p.passed for p in self.probes),
            "families": sorted({p.family for p in self.probes}),
            "probes": [p.payload() for p in self.probes],
            "external_model_judgments": False,
            "native_console_proof_independently_required": True,
            "copyright_similarity_cleared": False,
        }


def _rejected(fn) -> str:
    try:
        fn()
    except (StoryError, StoryExportError, PermissionError):
        return "rejected"
    except Exception as err:
        return "unexpected:" + type(err).__name__
    return "accepted"


def review_living_story(
    world: StoryWorld, proof: StoryReplay, package: StoryPackage,
    *, authorized: bool, attempts: int = 128,
) -> StoryMirrorReport:
    if not authorized:
        raise PermissionError("story mirror requires operator authority")
    if (not isinstance(world, StoryWorld) or not isinstance(proof, StoryReplay)
            or not isinstance(package, StoryPackage)):
        raise StoryMirrorError("typed game, actual proof and package required")
    if type(attempts) is not int or not 64 <= attempts <= 512:
        raise StoryMirrorError("mirror attack budget must be between 64 and 512")
    story_verify(world, proof, authorized=True)
    if proof.final.ending is None:
        raise StoryMirrorError("narrative campaign lacks independently reachable ending")
    if package.manifest["world_digest"] != world.digest or package.manifest["proof_digest"] != proof.digest:
        raise StoryMirrorError("game and proof packaging do not match")
    for name, digest in package.manifest["files"].items():
        if sha256(package.files[name]).hexdigest() != digest:
            raise StoryMirrorError("narrative source changed before adversarial campaign")
    actions = tuple(r.action for r in proof.receipts)
    if not actions:
        raise StoryMirrorError("narrative proof has no player action")
    states = [first_story_state(world, authorized=True)]
    for action in actions:
        states.append(story_step(world, states[-1], action, authorized=True))
    if states[-1] != proof.final:
        raise StoryMirrorError("reference story replay final state diverged")
    rng = random.Random(int(world.digest[:16], 16))
    findings = []
    package_paths = tuple(sorted(package.manifest["files"]))
    for index in range(attempts):
        sample = rng.randrange(len(actions))
        state = states[sample]
        family = index % 12
        expected = "rejected"
        context = {"world": world.digest, "index": index, "sample": sample,
                   "state_digest": state.digest, "family": family}
        if family == 0:
            name = "verified-valid-story-prefix"
            expected = "reproduced"
            try:
                prefix = story_play(world, actions[:sample+1], authorized=True)
                observed = "reproduced" if prefix.final == states[sample+1] else "diverged"
            except Exception as err:
                observed = "unexpected:" + type(err).__name__
        elif family == 1:
            name = "unauthorized-narrative-action"
            observed = _rejected(lambda: story_step(world, state, "wait", authorized=False))
        elif family == 2:
            name = "injected-script-as-choice"
            observed = _rejected(lambda: story_step(world, state, "exec:rm -rf /", authorized=True))
        elif family == 3:
            name = "forged-world-identity"
            observed = _rejected(lambda: story_step(
                world, replace(state, world_digest="0" * 64), "wait", authorized=True))
        elif family == 4:
            name = "invented-quest-item"
            observed = _rejected(lambda: story_step(
                world, replace(state, inventory=("foreign_item",)), "wait", authorized=True))
        elif family == 5:
            name = "inflated-reputation"
            observed = _rejected(lambda: story_step(
                world, replace(state, faction_trust=(99, 99, 99)), "wait", authorized=True))
        elif family == 6:
            name = "inflated-quest-score"
            observed = _rejected(lambda: story_step(
                world, replace(state, score=99999), "wait", authorized=True))
        elif family == 7:
            name = "forged-replay-receipt"
            row = proof.receipts[0]
            forged = replace(proof, receipts=(replace(row, before_digest="a" * 64),
                                             *proof.receipts[1:]))
            observed = _rejected(lambda: story_verify(world, forged, authorized=True))
        elif family == 8:
            name = "forged-ending"
            forged = replace(proof, final=replace(proof.final, ending="discovery"
                                                  if proof.final.ending != "discovery" else "stewardship"))
            observed = _rejected(lambda: story_verify(world, forged, authorized=True))
        elif family == 9:
            name = "out-of-graph-teleportation"
            observed = _rejected(lambda: story_step(
                world, state, "travel:region_missing", authorized=True))
        elif family == 10:
            name = "injected-native-source"
            path = package_paths[index % len(package_paths)]
            bad = dict(package.files)
            bad[path] += b"external-code"
            observed = _rejected(lambda: StoryPackage(bad, package.manifest))
            context["file"] = path
        else:
            name = "postgame-real-choice-or-terminal-block"
            if world.intent.mode == "campaign":
                observed = _rejected(lambda: story_step(
                    world, proof.final, "wait", authorized=True))
            else:
                expected = "reproduced"
                try:
                    choice = story_choices(world, proof.final)[0]
                    nxt = story_step(world, proof.final, choice, authorized=True)
                    observed = "reproduced" if (
                        nxt.turn == proof.final.turn + 1
                        and nxt.status in {"epilogue", "open"}
                        and nxt.ending == proof.final.ending
                    ) else "diverged"
                except Exception as err:
                    observed = "unexpected:" + type(err).__name__
        context.update({"name": name, "expected": expected, "observed": observed})
        findings.append(StoryMirrorProbe(
            index, name, observed == expected, expected, observed,
            canonical_digest(context),
        ))
    return StoryMirrorReport(world.digest, proof.digest, package.digest, tuple(findings))


__all__ = [
    "StoryMirrorError", "StoryMirrorProbe", "StoryMirrorReport",
    "review_living_story",
]
