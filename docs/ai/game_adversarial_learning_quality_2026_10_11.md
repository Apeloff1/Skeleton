# Progressive adversarial learning assurance — October 2026

Status: implemented incremental **local game-review classifier** controls in stacked PR #3643 (based on game-builder PR #3642). This specification does not imply an autonomous foundation-model training system, complete game-console coverage, industry certification, or consumer hardware qualification.

## 1. The actual closed loop

```text
New original world + source-rights gate
    -> canonical replay, NPC witnesses, quest evidence, real game playtester
    -> independent game-test almanac + reviewed quarantine
    -> source-project split firewall
       [TRAIN projects] --> isolated ranker SGD + TRAIN metamorphic augmentation
       [VALIDATION projects] --> checkpoint/threshold selection only
       [TEST projects] --> sealed, one-time qualification only
    -> typed model + model SHA + evidence/standard SHA
    -> adversarial qualification (danger recall, controls, family, calibration,
       Wilson confidence, per-project regression, metadata counterfactuals)
    -> operator staging -> six role attestations -> shadow
    -> unseen usage projects -> replay -> evaluator -> quality ledger
    -> different unseen idle projects -> replay -> evaluator -> quality ledger
    -> explicit operator activation OR blocked/rollback
    -> advisory ranker hints only; canonical game validator remains mandatory
    -> propose next strictly higher standard for the next generation
```

There are **no learning shortcuts** between evaluation and TRAIN data. Failures of TEST, usage or idle folds produce *aggregate capability-gap objectives*, not sample-level training examples. New source-reviewed TRAIN game projects must be acquired, verified, and quarantined before attempting a subsequent fit.

## 2. Five independence boundaries

| Evidence lane | What it may do | What it must never do |
|---|---|---|
| TRAIN | Fit local classifier; augment original TRAIN cases with replay-preserving counterfactuals | Learn from protected or unreviewed evaluation data |
| VALIDATION | Choose fit checkpoint/threshold and inspect training-time generalization | Feed the evaluator's examples to SGD |
| TEST | Judge frozen candidate after model selection | Tune the same candidate after seeing its scores |
| Usage shadow/live | Re-run new canonical game playtests and compare candidate/champion | Serve as a source of new gradient steps; bypass game validator |
| Idle shadow/live | Run a separate new source cohort while operator/host permits | Recycle an earlier usage, idle, TEST or VALIDATION project |

The observed gameplay digest is project-scoped; replaying one game many times must not inflate independent-project counts. The historical source firewall reads the verified append-only journal, not merely the most recently displayed `usage` and `idle` slots. New generations must use fresh validation and TEST projects; previously TRAIN-only projects can remain TRAIN but can never be silently promoted to a test lane.

Legacy candidate evidence without an explicit three-way split is conservatively treated as protected. This can impose new project acquisition costs, but it prevents inventing missing historical provenance.

## 3. Required acceptance vector

All required dimensions fail closed. A strong global score cannot forgive an individual severe failure.

1. **Independent cohorts:** required project count, nonoverlap, unique source example IDs, represented projects and both classes.
2. **Model semantics:** local registered input-feature schema, finite bounded weights, fixed candidate digest, unchanged canonical rights/gameplay authority.
3. **Predictive performance:** balanced accuracy, per-game accuracy, Brier calibration and Wilson lower bound for danger recall.
4. **Safety-critical evidence:** no severe incident missed, sufficient adverse-family support and no family with missed danger.
5. **Shortcut resistance:** source-preserving metadata/envelope counterfactuals on independent folds; strict standard enables this on live and idle evidence as well.
6. **Champion preservation:** never hide per-game or adversarial regressions in global aggregates; compare the same fresh cohort to the installed incumbent.
7. **Promotion custody:** six distinct reviewer identities with six role signoffs, explicit operator authority, candidate/evaluation digests, both usage and idle results, crash-recoverable state and immutable journal receipts.

The standard admits independent **policy ratchets**. `next-standard` is available only after a verified active promotion, and proposes higher project coverage, per-class support, attack-family support, accuracy/confidence, stricter calibration/generalization and a high counterfactual target. It never changes the active model or installed standard by itself. Ratchets are not evidence that the current model already meets the next benchmark.

## 4. Training feedback ledger

Each gate failure is grouped into a typed, high-priority objective. The planner retains counts for **all** blockers, refuses malformed or contradictory verdicts, and refuses unbounded categories rather than silently truncating an incomplete review.

| Failure family | Next allowed work |
|---|---|
| Critical danger missed | Independently replay severe TRAIN-only incidents and matched genuine controls |
| Attack-family escape | Acquire more original TRAIN worlds exercising that exploit and require all matched replays |
| Per-game champion regression | Repair weak TRAIN-world behaviors and retain a per-game veto |
| Counterfactual shortcut | TRAIN-only metadata invariance and nested evidence experiments; never train on failed sealed tests |
| Weak Wilson recall confidence | Add distinct projects rather than repeat identical runs |
| Calibration failure | Fit/calibrate on TRAIN and permitted validation, then check against newly sealed test games |
| Insufficient project or family coverage | Acquire new independently authored original games and underrepresented attack families |
| All current tests pass | Pursue a new measurable frontier and propose a strictly stronger standard; do not assume self-improvement occurred |

Every report includes source/candidate digests, precise counts, prioritized actions, mandatory independent verification and explicit `model_promotion_approved: false`. Confidential evaluation examples, usernames and project-specific failed receipts are not copied into the feedback outputs.

## 5. Active-use and idle runtime contract

A host may invoke the existing `usage` or `idle-pass` commands with distinct reviewed original-world blueprints. The two modes are **separate** qualification obligations; one cannot stand in for the other.

For deployment safety the current project exposes *bounded, operator-triggered evaluation*, not an invisible OS background service. Production idle detection, thermals/battery-aware budgets, consent, foreground preemption and pause/resume checkpointing require an explicit host-owned scheduler integration. Until then, the CLI's idle label means an independently requested idle cohort, not proof of OS user inactivity.

CLI sequence from the existing game-builder module:

```shell
python -m skeleton.ai.game_builder.game_model_cli evaluate --root STUDIO --trusted-local-operator
python -m skeleton.ai.game_builder.game_model_cli stage --root STUDIO --trusted-local-operator
python -m skeleton.ai.game_builder.game_model_cli approve --root STUDIO --reviewers-file REVIEWS.json --trusted-local-operator
python -m skeleton.ai.game_builder.game_model_cli usage --root STUDIO --director-blueprints USAGE_A.json USAGE_B.json --trusted-local-operator
python -m skeleton.ai.game_builder.game_model_cli idle-pass --root STUDIO --director-blueprints IDLE_A.json IDLE_B.json --trusted-local-operator
python -m skeleton.ai.game_builder.game_model_cli activate --root STUDIO --trusted-local-operator
python -m skeleton.ai.game_builder.game_model_cli next-standard --root STUDIO --trusted-local-operator
python -m skeleton.ai.game_builder.game_model_cli status --root STUDIO
```

Commands above require pre-existing original worlds, reviewed quarantine examples, and actual independent approvals. They are **not** guaranteed to succeed on arbitrary sample inputs. No verification step overwrites model weights. Rollback is explicit via `rollback --reason "A documented safety reason of sufficient length"`; interruption recovery is explicit via `recover`.

## 6. Fault matrix and observability

The focused test suite injects unreviewed/duplicate sources, source overlap, unqualified or unauthorized operations, calibration/critical misses, insufficient family coverage, weak model shortcut resistance, champion regression, source-unsafe improvement outputs, standards weakening and active-model restaging. The registry tests also verify immutable chained receipts and recovery after interruption between ledger and state publication.

The qualification workflow pins checkout to the PR's **exact SHA** and runs Python on Ubuntu and Windows. A workflow green signal confirms only these assertions; it does not independently measure commercial competitor quality, prove hardware-specific runtime behavior, certify rights, or qualify a large-language-model checkpoint.

## 7. Next implementation acceptance work

- Connect real host activity, CPU/memory/thermal and foreground-preemption signals to an owner-authorized idle coordinator. Suspend immediately on foreground activity and never infer consent from mere inactivity.
- Track platform/genre/era-specific evaluation families and a protected, rotating adversarial holdout bank, with explicit minimum per-family and per-generation source counts.
- Add reviewer identity attestation backed by separate credential authorities and artifact signing; a distinct-looking reviewer ID string is not cryptographic proof of human independence.
- Integrate real-world game-quality measures including readability, controls, pacing, accessibility, narrative consistency, NPC agency and performance into verified evaluator modules, avoiding model-generated self-grading.
- Promote language-model weights **only** through their separate Jeeves/Dragon training and model-serving authority, with signed weights, independent holdout evaluation, canary/rollback and exact producer revision binding. The local review classifier cannot authorize that promotion.
- Record independent benchmark baselines and competitor comparisons with reproducible public cases, hardware setup and uncertainty. Never claim superiority from arbitrary generated case counts.

**Completion rule:** promotion is confirmed only for a named source revision, exact model digest, standard digest, immutable evidence chain, independently passing frozen/usage/idle cohorts and explicit operator approval. Every other state remains staged, blocked, shadow, rolled back, or under verification.
