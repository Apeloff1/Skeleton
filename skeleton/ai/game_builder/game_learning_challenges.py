"""Competitive metamorphic review of model shortcuts and dataset leakage.

Challenge the REVIEWER classifier using controlled edits to *metadata only*;
original gameplay labels and source evidence are unchanged. This reveals
models that merely recognize fields like 'attack_family' rather than robustly
interpreting gameplay. It does not imply a modified game was canonically
replayed. Held-out validation/test counterexamples never enter training.
"""
from __future__ import annotations

from dataclasses import dataclass,replace
from collections import Counter
from typing import Sequence

from .contracts import canonical_digest
from .competitive_mirror_training import TrainingCandidate,training_jsonl
from .game_model_promotion import validate_policy,predict_review,PromotionError
from .game_training_flow import _label


@dataclass(frozen=True,slots=True)
class ChallengeFailure:
    source_example_id: str
    challenge: str
    original_reject_probability: float
    challenged_reject_probability: float
    expected_reject: bool
    variant_digest: str
    source_split: str
    severity: int

    def payload(self):
        return dict(schema="skeleton.game_builder.reviewer_shortcut_failure.v1",
                    source_example_id=self.source_example_id,
                    challenge=self.challenge,
                    original_reject_probability=self.original_reject_probability,
                    challenged_reject_probability=self.challenged_reject_probability,
                    expected_reject=self.expected_reject,
                    variant_digest=self.variant_digest,
                    source_split=self.source_split,severity=self.severity)


@dataclass(frozen=True,slots=True)
class AdversarialChallengeReport:
    policy_digest: str
    source_evidence_digest: str
    attempted: int
    passed: int
    failed: tuple[ChallengeFailure,...]
    by_family: tuple[tuple[str,int,int],...]
    heldout: bool

    @property
    def accuracy(self):
        return self.passed/self.attempted if self.attempted else 0.0

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.reviewer_metamo_mirror.v1",
                    policy_digest=self.policy_digest,
                    source_evidence_digest=self.source_evidence_digest,
                    attempted=self.attempted,passed=self.passed,
                    failed=len(self.failed),
                    accuracy=round(self.accuracy,6),
                    by_family=[dict(family=f,attempted=n,passed=good)
                               for f,n,good in self.by_family],
                    failures=[p.payload() for p in self.failed],
                    heldout_test_cases_not_retrained=self.heldout,
                    learned_model_weights_mutated=False)


def _variants(case: TrainingCandidate):
    source=case.input
    if _label(case)==0:
        # Adversary inserts *labels* without changing the validated incident.
        # The genuine game witness still exists, so correct answer stays accept.
        return (
            ("spurious_attack_marker",dict(source,attack_family="synthetic_noise")),
            ("irrelevant_fields",dict(source,review_display_hint="warning")),
            ("schema_order",dict(reversed(list(source.items())))),
        )
    # A genuine corrupted replay is still corrupted when red-team labels or
    # display hints are masked. A robust model should not approve it.
    return (
        ("masked_attack_family",{k:v for k,v in source.items()
                                  if k!="attack_family"}),
        ("renamed_attack_family",dict(source,attack_family="unseen_new_attack")),
        ("irrelevant_fields",dict(source,review_display_hint="benign")),
    )


def challenge_reviewer(
    examples: Sequence[TrainingCandidate],policy: dict,*,
    authorized: bool,max_examples: int=256,
)->AdversarialChallengeReport:
    if not authorized:
        raise PermissionError("competitive game-model challenge requires owner authority")
    validate_policy(policy)
    if (not isinstance(examples,(tuple,list)) or not 2<=len(examples)<=8192
        or any(not isinstance(x,TrainingCandidate) for x in examples)
        or type(max_examples) is not int or not 2<=max_examples<=512):
        raise PromotionError("bounded typed independent gameplay challenge required")
    selected=sorted(examples,key=lambda x:x.example_id)[:max_examples]
    seen={x.example_id for x in selected}
    if len(seen)!=len(selected):
        raise PromotionError("repeated source receipts would inflate adversarial robustness")
    split={x.split for x in selected}
    if len(split)!=1:
        raise PromotionError("metamorphic test must not mix learning and held-out splits")
    score=Counter()
    failures=[]
    attempts=0
    passed=0
    for case in selected:
        original=predict_review(case,policy)
        target=bool(_label(case))
        for family,raw in _variants(case):
            attempts+=1
            variant=replace(case,input=raw,example_id=canonical_digest({
                "original":case.example_id,"challenge":family,
                "input":raw,
            }))
            outcome=predict_review(variant,policy)
            correct=outcome["predicted_reject"]==target
            score[(family,"attempts")]+=1
            score[(family,"passed")]+=int(correct)
            passed+=int(correct)
            if not correct:
                failures.append(ChallengeFailure(
                    case.example_id,family,
                    original["probability"],outcome["probability"],
                    target,canonical_digest(variant.payload()),case.split,
                    case.evidence.get("severity",2),
                ))
    families=tuple((name,score[(name,"attempts")],
                    score[(name,"passed")]) for name in sorted({
                    f for f,k in score}))
    return AdversarialChallengeReport(
        canonical_digest(policy),
        canonical_digest([x.payload() for x in selected]),
        attempts,passed,tuple(failures),families,
        selected[0].split in {"validation","test"},
    )


def challenging_train_examples(
    original: tuple[TrainingCandidate,...],report: AdversarialChallengeReport,*,
    authorized: bool,
) -> tuple[TrainingCandidate,...]:
    if not authorized:
        raise PermissionError("only train-project challenge cases may be distilled")
    if report.heldout or any(x.split!="train" for x in original):
        raise PromotionError("heldout challenge results may not contaminate future training")
    if canonical_digest(sorted((x.payload() for x in original),
                               key=lambda x:x["example_id"]))!=report.source_evidence_digest:
        # Caller must supply the same sorted bounded source family.
        raise PromotionError("counterexample source receipts cannot be substituted")
    failures={(f.source_example_id,f.challenge) for f in report.failed}
    examples=[]
    for case in sorted(original,key=lambda x:x.example_id):
        for family,raw in _variants(case):
            if (case.example_id,family) not in failures:
                continue
            examples.append(replace(
                case,input=raw,example_id=canonical_digest({
                    "original":case.example_id,"challenge":family,"input":raw,
                }),
                evidence=dict(case.evidence,
                              adversarial_challenge=family,
                              source_example_id=case.example_id,
                              challenge_report_digest=report.digest),
            ))
    training_jsonl(tuple(examples),authorized=True)
    return tuple(examples)


__all__=[
    "ChallengeFailure","AdversarialChallengeReport",
    "challenge_reviewer","challenging_train_examples",
]
