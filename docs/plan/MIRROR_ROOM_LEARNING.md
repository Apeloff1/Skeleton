# Mirror Room Learning Plane

The Mirror Room is the offline adaptation surface for Skeleton's existing
`feedback-learning` plane. It is evidence-control, not a second production
orchestration runtime, and it never mutates production behavior directly.

## Learning lifecycle

1. Bind an offline experiment manifest, frozen production baseline, metric
   policy, hermetic sandbox policy, and whole-run budget.
2. Admit only scenarios whose data class fits experiment eligibility.
   Non-public scenarios require an explicit learning authorization receipt.
3. Reject duplicate payloads anywhere in the corpus so one example cannot leak
   across train, validation, or the sealed holdout under different IDs.
4. Give the candidate generator TRAIN scenarios only. Accumulated hard examples
   are ordered first in the next curriculum; validation and holdout payloads
   never enter generator feedback.
5. Maintain two champion tracks. A learner champion is selected only from TRAIN
   evidence and is the only parent fed back to the generator. A hidden qualified
   champion is selected by validation against the frozen production baseline.
6. Execute baseline/candidate pairs with identical deterministic seeds.
   Validation confidence bounds receive a family-wise correction for the
   bounded candidate search.
7. Touch the sealed holdout once, after search ends, comparing only the best
   hidden validation-qualified candidate to the original production baseline.
8. Replay the selected champion-forming training/validation lineage and holdout
   with `verify_selected_lineage` when exact reproducibility evidence is
   required.
9. Emit non-authoritative promotion evidence. The external promotion/release
   plane remains the only production mutation path.

## Isolation and authority

The default sandbox permits bounded compute only. Network access, filesystem
writes, subprocesses, and external side effects are forbidden. Per-episode and
whole-run step, token, cost, generation, candidate, and episode ceilings fail
closed. Behavior-parameter digests prevent cosmetic candidate identities from
revisiting an already explored behavior.

The generator and sandbox evaluator must have different stable identities.
Promotion verification must be independent of both the candidate producer and
sandbox evaluator. Every candidate remains `production_authority=False` and
`direct_self_modify=False`.

## Data discipline

`MirrorScenario.data_class` is checked against the experiment's allowed data
classes. Public scenarios need no additional receipt. Internal, confidential,
and restricted scenarios require `authorization_ref`. Optional `source_ref`
keeps source custody visible without entering promotion authority.

Payload digests are globally unique in a run. This blocks direct holdout
contamination and prevents duplicate examples from silently receiving excess
statistical weight.

## Selection discipline

Paired evaluation orients every metric so positive delta means improvement.
Guardrails must remain inside their regression budget. Improvement metrics must
clear their configured lower confidence bound. Validation uses a Bonferroni
style family-wise confidence adjustment based on the maximum bounded candidate
search; holdout uses family size one because it is not a search surface.

Small benchmarks remain small benchmarks: the experiment manifest still owns
minimum sample requirements, and external evaluation/release evidence remains
required before production promotion.

## Hard-example memory and curriculum

Training comparisons produce `HardExample` records. The engine accumulates the
hardest cases across generations, rejects digest drift for reused scenario IDs,
and orders the next TRAIN curriculum hard-first. Validation results never
choose the learner parent. They update only a hidden qualification track, so
the generator cannot infer validation outcomes from its next champion. A
bounded stagnation patience stops the search after repeated generations with no
TRAIN improvement, preserving budget for a later materially different run.

## Replay

Run-level replay reconstructs candidate identity from immutable generation
records, verifies the sealed holdout digest, and re-executes the exact episodes
that formed train-selected learner champions and hidden validation-qualified
champions, plus final holdout evidence. Any candidate,
scenario, executor, policy, or outcome drift fails closed. Replay receipts are
evidence-only and grant no production authority.

## Promotion boundary

Mirror Room qualification means only that a candidate is eligible to be
considered by the external promotion path. The handoff requires at least two
evaluation references and preserves the original production baseline as the
rollback identity.

## Built-in adaptive learner

`DeterministicCoordinateLearner` provides a provider-neutral reference
adaptation strategy for bounded numeric policy surfaces. Callers declare
`NumericDimension` objects with explicit lower/upper bounds and step policy;
the learner then performs deterministic derivative-free coordinate search using
only TRAIN-visible `LearningFeedback`.

A coordinate selected by TRAIN evidence expands its next step within the hard
dimension span. Coordinates that do not change in the learner champion contract
toward their configured minimum step. Search dimensions rotate across
generations, candidate artifacts are content-addressed, and all candidates still
flow through the same validation/holdout/promotion boundaries.

This is intentionally a conservative reference learner rather than a universal
optimizer. Rich model-weight training, symbolic program search, or
domain-specific policy learning can implement the same `CandidateGenerator`
contract while inheriting Mirror Room isolation, replay, statistical, and
promotion controls.

## Cross-run TRAIN memory

`TrainingLearningArchive` lets Mirror Room carry safe experience across
separate sandbox runs without turning validation or holdout into adaptation
feedback. The archive extractor walks only `selected_for_learning`
transitions and serializes the TRAIN report digest, TRAIN utility delta,
parameter deltas, learner lineage, and TRAIN hard-example digests.

The archive payload explicitly carries no validation report, holdout report,
promotion receipt, final qualified champion, or production authority. It can be
scoped by experiment before reuse.

The built-in `DeterministicCoordinateLearner` accepts an optional scoped
training archive. Positive prior TRAIN gains warm-start coordinate step sizes,
rank historically useful dimensions earlier, and bias the first probe toward
the historically useful direction. Current-run TRAIN evidence can still expand
or contract those steps normally. Archive identity is included in the learner
strategy digest so warm and cold search strategies cannot alias.

## 100-attempt adversarial ratchet

`AdversarialMirrorRoom` is the delivery-oriented red-team loop. It performs
exactly 100 candidate attempts by default and refuses to emit delivery evidence
before all 100 are complete.

Each attempt is a strict ratchet:

1. The learner proposes exactly one novel candidate whose parent is the current
   ratchet baseline.
2. After proposal, an independent adversary receives only TRAIN-visible state
   and produces fresh, previously unseen TRAIN challenges targeted at that
   candidate.
3. The candidate is compared with the current baseline on the ordinary TRAIN
   corpus plus the fresh attacks.
4. The same candidate is independently compared with the current baseline on a
   stable validation set. The validation seed is stable across all 100 attempts
   and the confidence bound is corrected for the 100-candidate search family.
5. Acceptance requires both reports to pass, a non-trivial weighted gain,
   at least the configured number of metrics to improve by a strict positive
   margin, and—by default—no regression on any metric. An accepted candidate
   becomes the next attempt's baseline. A rejected candidate cannot change the
   baseline.
6. Every attempt emits an `AdversarialStandard` hash-chain record containing
   the current baseline identity and validation metric floors. The next
   attempt's validation baseline must reproduce those floors exactly, which
   detects evaluator drift and proves that standards did not silently fall.
7. Hard examples from the fresh attacks are retained as TRAIN-only memory for
   the next proposal. Validation and holdout payloads are never exposed to the
   learner or adversary.

The campaign validates up front that step, token, cost, generation, and episode
budgets can support the worst-case full 100-attempt run. It does not use the
ordinary stagnation early-stop rule because delivery requires all 100 attempts.

The sealed holdout is untouched during attempts 1–99. After attempt 100, the
final ratcheted baseline is compared once against the original production
baseline. `qualify_adversarial_delivery` can then emit evidence only when the
100-attempt chain is complete, at least the configured minimum number of
upgrades were accepted, the final holdout passes, and the delivery verifier is
independent of the learner, sandbox evaluator, adversary, and candidate
producer.

The adversarial delivery receipt is still evidence-only. It carries the
original baseline as rollback identity and does not grant production mutation
authority.


## High-end content delivery constitution

After attempt 100, the final ratcheted candidate must re-run against the entire
accumulated adversarial corpus in one cumulative gauntlet. This prevents a late
upgrade from passing its newest attack while forgetting an older failure. The
sealed holdout remains separate and opens only after the cumulative gauntlet.

`HighEndContentConstitution.canonical()` makes the delivery bar explicit across
intent fidelity, factual correctness, epistemic calibration, reasoning
coherence, completeness, specificity, usefulness, structure, style, robustness,
constraint compliance, evidence quality, self-consistency, information density,
and safety. Each dimension has independent validation, cumulative-gauntlet, and
sealed-holdout floors.

The canonical high-end dossier requires exactly 100 attempts, at least 25
accepted baseline ratchets, monotonic baseline and standard hash chains,
strict positive per-step metric lift, cumulative re-validation over all
discovered attacks, a sealed holdout, at least 2% weighted validation gain over
the original baseline, at least 1% lift on every quality dimension, strong
absolute quality floors, a worst-case holdout floor, balanced dimension
coverage with multiple attack families per dimension, at least five blind
independent quality judges, bounded judge disagreement, an independent final
verifier, and the original production baseline as rollback identity.

These are evidence contracts rather than a claim that any fixed rubric is
universally state of the art. The evaluator and challenge corpus must themselves
be strong; the architecture ensures that weak evidence cannot silently become a
delivery claim.


### Independent blind quality panel

High-end delivery additionally requires at least five calibrated blind judges
on distinct evaluation channels in the canonical tier. Judge identities cannot
overlap the learner,
sandbox evaluator, adversary, final verifier, or candidate producer. Every
receipt is bound to the exact final candidate, constitution, calibration
artifact, and evidence digest.

The panel uses the median score for robust dimension consensus and rejects
dimension-level judge spreads above the constitutional disagreement ceiling.
Critical dimensions also require every judge individually to clear the holdout
floor, so a strong average cannot hide a severe dissent on correctness, safety,
intent, reasoning, calibration, usefulness, robustness, evidence quality,
constraint compliance, or self-consistency.


## Progressive standards and anti-forgetting retention

The delivery ratchet now raises the acceptance bar continuously across attempts
1 through 100. `AdversarialRatchetPolicy` defines both starting and final
weighted-gain and strict-metric thresholds plus an escalation exponent. Each
attempt receipt records the exact thresholds it had to clear, and campaign
validation rejects any standard sequence that decreases or drifts from policy.

Every attempt is also a cumulative retention exam. After the adversary adds a
fresh challenge, the proposed candidate is evaluated against the base TRAIN
corpus **and every adversarial challenge discovered so far**, always against the
current ratchet baseline. An upgrade therefore cannot be accepted by solving
today's attack while forgetting yesterday's. Attempt receipts bind the complete
retention-scenario digest set, and the campaign audit requires the set to grow
by exactly the fresh challenges on each round.

This makes the baseline ratchet inductive: if baseline N retained all attacks
through N, candidate N+1 can become baseline N+1 only by matching or improving
that accumulated standard while also clearing a progressively higher gain bar.

High-end content delivery adds a temporal-quality requirement on top of the
technical ratchet. The canonical constitution requires the final weighted
standard to be at least four times the initial acceptance bar and requires
accepted upgrades in every 25-attempt quartile. A campaign that improves early
and then spends the remaining attempts producing decorative or stagnant
variants cannot qualify as high-end delivery.

## Mirror Room Observatory

The Mirror Room now includes an evidence-only product surface that makes the
100-attempt ratchet visible while it runs. The learning engine publishes only
immutable receipt projections to `MirrorRoomObservatory`; the UI never writes
into candidate generation, evaluation, promotion, or production state.

The Observatory exposes:

- a 1..100 ratchet grid showing accepted and rejected challengers;
- baseline-versus-challenger quality and detail comparisons for every attempt;
- cumulative quality/detail ascent curves using the effective accepted baseline;
- per-content-dimension deltas so quality growth is inspectable rather than a
  single opaque score;
- progressive gain bars, retained adversarial-suite size, and rejection reasons;
- delivery gates for attempt completion, cumulative gauntlet, sealed holdout,
  and final delivery readiness;
- a governed file tree spanning the canonical learning engine, AI mirror,
  backend read adapter, frontend screen, tests, and CI gate.

The projection contains candidate identities and aggregate metric evidence only.
It does not expose scenario payloads or holdout content. The API is read-only
and marked `Cache-Control: no-store` so a user watching an active campaign sees
fresh evidence.

The physical product tree is also declared in
`machine/mirror_room_file_tree.json`. The broader governed AI mapping continues
to bind `skeleton/learning` to `skeleton/ai/learning` by exact git tree
identity.
