"""Independent mirror room for original playable quest/cinematic products.

The adversary executes typed failures against the real quest simulator and
authored scene graph. A review 'pass' never constitutes artistic, legal or
human-playtest approval. Calling frequency is externally governed and
unchanged by this module.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import random

from .contracts import canonical_digest
from .quest_scene_engine import (
    Affordance, Cue, DirectorAction, DirectorError, DirectorReplay,
    DirectorState, DirectorWorld, director_initial, director_step,
    director_play, director_verify,
)
from .quest_director_solver import solve_quest


class DirectorMirrorError(ValueError):
    """An adversarial execution or artifact integrity boundary failed."""


@dataclass(frozen=True, slots=True)
class DirectorProbe:
    index: int
    family: str
    passed: bool
    result_digest: str

    def payload(self):
        return {
            "index": self.index, "family": self.family,
            "passed": self.passed, "result_digest": self.result_digest,
        }


@dataclass(frozen=True, slots=True)
class DirectorMirrorReport:
    world_digest: str
    proof_digest: str
    browser_digest: str
    probes: tuple[DirectorProbe, ...]

    @property
    def passed(self):
        return len(self.probes) >= 64 and all(row.passed for row in self.probes)

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return {
            "schema": "skeleton.game_builder.director_mirror_room.v1",
            "world_digest": self.world_digest,
            "proof_digest": self.proof_digest,
            "browser_digest": self.browser_digest,
            "attempts": len(self.probes),
            "passed": sum(p.passed for p in self.probes),
            "failed": sum(not p.passed for p in self.probes),
            "probe_families": sorted({p.family for p in self.probes}),
            "probes": [p.payload() for p in self.probes],
            "human_playtested": False,
            "trained_ai_weights": False,
            "copyright_similarity_cleared": False,
            "native_hardware_cleared": False,
        }


def _reject(call) -> bool:
    try:
        call()
    except (DirectorError, PermissionError):
        return True
    return False


def review_director(
    world: DirectorWorld, proof: DirectorReplay, *,
    browser: bytes,
    authorized: bool,
    attempts: int = 128,
) -> DirectorMirrorReport:
    if not authorized:
        raise PermissionError("adversarial scene mirror requires operator permission")
    if not isinstance(world, DirectorWorld) or not isinstance(proof, DirectorReplay):
        raise DirectorMirrorError("typed authored game and genuine proof required")
    if type(attempts) is not int or not 64 <= attempts <= 512:
        raise DirectorMirrorError("bounded mirror-room action count required")
    if not isinstance(browser, bytes) or not 512 <= len(browser) <= 900000:
        raise DirectorMirrorError("missing playable source for review")
    director_verify(world, proof)
    if not proof.final.results:
        raise DirectorMirrorError("quest proof has no successful game progress")
    rng = random.Random(int(world.digest[:16], 16))
    observed = []
    for number in range(attempts):
        family = number % 12
        point = rng.randrange(len(proof.actions))
        action = proof.actions[point]
        # Verify every attack probes an actual mechanic, not hypothetical
        # assistant judgments. Sources and states are immutable typed values.
        if family == 0:
            name = "genuine_prefix_reconstruction"
            candidate = director_play(world, proof.actions[:point + 1])
            try:
                director_verify(world, candidate)
                passed = candidate.final.digest == proof.state_digests[point]
            except DirectorError:
                passed = False
        elif family == 1:
            name = "invented_scene_teleport"
            passed = _reject(lambda: director_step(
                world, director_initial(world),
                DirectorAction("travel", "nonexistent", world.starting_scene)))
        elif family == 2:
            name = "foreign_game_receipt"
            passed = _reject(lambda: director_verify(
                world, replace(proof, world_digest="0" * 64)))
        elif family == 3:
            name = "forged_final_reward"
            bad = replace(proof, final=replace(
                proof.final, narrative_flags=("outside_source",)))
            passed = _reject(lambda: director_verify(world, bad))
        elif family == 4:
            name = "manipulated_intermediate_hash"
            modified = list(proof.state_digests)
            modified[point] = "f" * 64
            passed = _reject(lambda: director_verify(
                world, replace(proof, state_digests=tuple(modified))))
        elif family == 5:
            name = "unavailable_quest_objective"
            passed = _reject(lambda: director_step(
                world, director_initial(world),
                DirectorAction("use", "unknown_objective", world.starting_scene)))
        elif family == 6:
            name = "unavailable_actor_script"
            passed = _reject(lambda: director_step(
                world, director_initial(world),
                DirectorAction("use", "run_unreviewed_actor", world.starting_scene)))
        elif family == 7:
            name = "unsanctioned_action_rewrite"
            mutated = list(proof.actions)
            mutated[point] = DirectorAction("wait", "wait", mutated[point].scene)
            bad = replace(proof, actions=tuple(mutated))
            passed = _reject(lambda: director_verify(world, bad))
        elif family == 8:
            name = "invalid_quest_strategy"
            passed = _reject(lambda: solve_quest(
                world, world.quests[0].key, strategy="unreviewed", authorized=True))
        elif family == 9:
            name = "missing_operator_approval"
            passed = _reject(lambda: solve_quest(
                world, world.quests[0].key, authorized=False))
        elif family == 10:
            name = "tampered_cutscene_grammar"
            passed = _reject(lambda: Cue(
                0, "unreviewed_animation_command", "hero", "untrusted"))
        else:
            name = "invalid_noncolliding_leash"
            passed = _reject(lambda: Affordance(
                "escort_attack", "escort_leash", "friend", proximity=0))
        observed.append(DirectorProbe(number, name, passed, canonical_digest({
            "world": world.digest, "family": name, "point": point,
            "accepted": passed,
        })))
    return DirectorMirrorReport(
        world.digest, proof.digest, sha256(browser).hexdigest(), tuple(observed),
    )


__all__ = [
    "DirectorMirrorError", "DirectorProbe", "DirectorMirrorReport",
    "review_director",
]
