from __future__ import annotations

import hashlib
import unittest

from skeleton.ai.evaluation.verifier_gaming import (
    GamingChallenge,
    VerifierDescriptor,
    VerifierGamingError,
    VerifierGamingGate,
    VerifierJudgement,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class VerifierGamingTests(unittest.TestCase):
    def verifier(self, name: str, family: str) -> VerifierDescriptor:
        return VerifierDescriptor(
            verifier_id=name,
            family_id=family,
            implementation_digest=sha(name + ":code"),
            training_root=sha(name + ":training"),
            evaluation_root=sha(name + ":eval"),
        )

    def challenge(self, *, author: str = "red-team") -> GamingChallenge:
        return GamingChallenge(
            challenge_id="reward-hack-v1",
            author_family_id=author,
            corpus_digest=sha("challenge-corpus"),
            target_failure_modes=(
                "reward-proxy-exploit",
                "format-gaming",
                "verifier-disagreement",
            ),
            passed=True,
            evidence_ref="evidence:reward-hack-v1",
        )

    def judgement(self, candidate: str, verifier: VerifierDescriptor, score: float = 0.9):
        return VerifierJudgement(
            candidate_id=candidate,
            verifier_identity=verifier.identity,
            verifier_family_id=verifier.family_id,
            passed=True,
            score=score,
            evidence_ref=f"evidence:{verifier.verifier_id}",
        )

    def test_promotion_requires_two_independent_verifier_families(self) -> None:
        gate = VerifierGamingGate()
        first = self.verifier("v1", "symbolic")
        with self.assertRaisesRegex(VerifierGamingError, "diversity"):
            gate.qualify(
                candidate_id="candidate-a",
                generator_family_id="generator",
                verifiers=(first,),
                judgements=(self.judgement("candidate-a", first),),
                gaming_challenge=self.challenge(),
            )

    def test_generator_cannot_verify_or_author_challenge(self) -> None:
        gate = VerifierGamingGate()
        first = self.verifier("v1", "generator")
        second = self.verifier("v2", "behavioral")
        with self.assertRaisesRegex(VerifierGamingError, "not independent"):
            gate.qualify(
                candidate_id="candidate-a",
                generator_family_id="generator",
                verifiers=(first, second),
                judgements=(),
                gaming_challenge=self.challenge(),
            )
        with self.assertRaisesRegex(VerifierGamingError, "cannot author"):
            gate.qualify(
                candidate_id="candidate-a",
                generator_family_id="generator",
                verifiers=(
                    self.verifier("v3", "symbolic"),
                    self.verifier("v4", "behavioral"),
                ),
                judgements=(),
                gaming_challenge=self.challenge(author="generator"),
            )

    def test_all_verifier_families_must_pass_threshold(self) -> None:
        gate = VerifierGamingGate(minimum_score=0.75)
        first = self.verifier("v1", "symbolic")
        second = self.verifier("v2", "behavioral")
        with self.assertRaisesRegex(VerifierGamingError, "threshold"):
            gate.qualify(
                candidate_id="candidate-a",
                generator_family_id="generator",
                verifiers=(first, second),
                judgements=(
                    self.judgement("candidate-a", first),
                    self.judgement("candidate-a", second, score=0.5),
                ),
                gaming_challenge=self.challenge(),
            )

    def test_successful_receipt_binds_diverse_evidence(self) -> None:
        gate = VerifierGamingGate(minimum_score=0.75)
        first = self.verifier("v1", "symbolic")
        second = self.verifier("v2", "behavioral")
        receipt = gate.qualify(
            candidate_id="candidate-a",
            generator_family_id="generator",
            verifiers=(first, second),
            judgements=(
                self.judgement("candidate-a", first),
                self.judgement("candidate-a", second, score=0.8),
            ),
            gaming_challenge=self.challenge(),
        )
        self.assertEqual(receipt.verifier_families, ("behavioral", "symbolic"))
        self.assertEqual(len(receipt.judgement_digests), 2)
        self.assertEqual(len(receipt.digest), 64)

    def test_unknown_or_duplicate_judgement_fails_closed(self) -> None:
        gate = VerifierGamingGate()
        first = self.verifier("v1", "symbolic")
        second = self.verifier("v2", "behavioral")
        duplicate = self.judgement("candidate-a", first)
        with self.assertRaisesRegex(VerifierGamingError, "duplicate"):
            gate.qualify(
                candidate_id="candidate-a",
                generator_family_id="generator",
                verifiers=(first, second),
                judgements=(duplicate, duplicate, self.judgement("candidate-a", second)),
                gaming_challenge=self.challenge(),
            )


if __name__ == "__main__":
    unittest.main()
