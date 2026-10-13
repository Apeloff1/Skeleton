# Competitive Game-AI Learning — Promotion Ladder (October 2026)

This implementation extends the original project learning pyramid: **playable
game evidence → game-tester almanac → adversarial mirror → quarantined
examples → project-separated experiment → promotion benchmark → signed-off
shadow candidate → fresh in-use and idle playtests → locally active advisory
reviewer**. It does not assume that an isolated classifier is a full Jeeves,
Dragon, Wiki or HOAG neural model.

## Proven vs not yet proven

The repository actually fits **two** isolated logistic game-review
classifiers: a 128-feature v1 baseline and a second-generation
**256-feature normalized-evidence v2** that is now the default operator
promotion candidate. Both produce real learned, deterministic numeric
weights. The v2 training set is expanded only with source-preserving,
adversarially transformed examples from train projects; validation
selects its checkpoint, and test projects remain strictly held out.
The v2 representation excludes attack-family labels and normalizes
nested witness/replay data. Neither classifier trains or edits
Dragon/Jeeves LLM parameters. Its role is to
prioritize suspicious evidence for the authoritative original-game replay
verifier. An active advisory result must never authorize a quest victory,
story change, copyrighted asset, platform export, or commercial launch.

A local `ReviewerRegistry` stores content-addressed source models,
benchmark evidence, a transition journal, explicit reviewers, newly observed
game tests and rollback receipts. The six roles are Wiki, HOAG, mirror,
human design, rights and device. Each attestation must name a **different**
reviewer and refer to the exact model and evaluation digests. These are
operator-attested claims, **not cryptographically verified external account
identities**, and should not be represented as automated product approvals.

## Non-negotiable structured standards

`game_model_promotion.py` independently recalculates model predictions using
the actual input-only feature extractor. The default programmatic v1 baseline
tests source integrity, project-heldout splitting, project count, both
classes, balanced accuracy, Brier calibration, Wilson 95% lower confidence
on danger detection, high-severity attack recall, individual games, attack
family sample support, generalization and incumbent-regression comparisons.
Every field has an explicit reject reason.

Standards are versioned, content-addressed and **monotonic**: a later
model round cannot silently weaken a minimum or relax a maximum.

The operational CLI goes further by default:
`--minimum-counterfactual-accuracy 0.98`. This rigorous condition
red-teams **labels masquerading as knowledge**: adding an irrelevant
`attack_family` field to a valid case, removing the family name from an
actually corrupted case, or changing field presentation must not invert the
answer. This catches a genuine weakness in simple schema-based classifiers.
The existing isolated **v1** ranker is blocked by the source-preserving
wrapper challenge on the focused benchmark. The current v2 implementation
passes the stricter 98% test on that same original-game benchmark
(including the actual Linux and Windows CI training/promotion tests).
These results prove this particular evaluation, not competitive
industry-wide superiority or creative model generalization.

The CLI uses `--feature-version robust_v2` by default. For a baseline
comparison use `--feature-version baseline_v1`. An explicit reduction of
`--minimum-counterfactual-accuracy` to zero is intended **only for
lab demonstrations**; it cannot justify consumer-production claims.

`game_learning_challenges.py` turns failed *train*-project probes into
traceable, quarantined hard examples. Held-out validation and test failures
may contribute only aggregate evaluation reports; they cannot be copied back
into training without an independent new dataset and review.

## Reproducible pipeline

Initialize an original local game studio, then produce and quarantine
independently tested, legal original game datasets from **multiple different
projects**. To create them, the existing tester CLI is:

```sh
python -m skeleton.ai.game_builder.game_workspace_cli playtest-game \
  --root ORIGINAL_STUDIO \
  --director-blueprint /path/to/approved-original-world.json \
  --testers 5 --attack-families 24 --quarantine-learning \
  --trusted-local-operator
```

Repeat with diverse independently authored worlds until train, validation
and test contain enough entire projects and both positive/negative classes.
For the immutable resumable shard workflow:

```sh
python -m skeleton.ai.game_builder.game_workspace_cli train-dataset \
  --root ORIGINAL_STUDIO --trusted-local-operator --epochs 75
```

To run the strict, independently recomputed candidate assessment:

```sh
python -m skeleton.ai.game_builder.game_model_cli evaluate \
  --root ORIGINAL_STUDIO --trusted-local-operator
```

If **passed**, stage the exact fitted model with the same source set:

```sh
python -m skeleton.ai.game_builder.game_model_cli stage \
  --root ORIGINAL_STUDIO --trusted-local-operator
```

Prepare a local JSON array containing six entries, each with:
`role`, `reviewer_id`, `candidate_digest`, `evaluation_digest`,
`note`, and `approved`. Valid roles are `wiki`, `hoag`, `mirror`,
`human`, `rights`, and `device`. All IDs must be unique and trace
to actual independent responsible reviewers. The current implementation
verifies the claim's structure and exact hashes, not ownership of those IDs.

```sh
python -m skeleton.ai.game_builder.game_model_cli approve \
  --root ORIGINAL_STUDIO --reviewers-file independent-reviews.json \
  --trusted-local-operator
```

A shadow model still requires **two distinct fresh game cohorts**, each
made of at least two previously unseen, independently reviewed original
worlds. Each world is really simulated through five playtester policies,
the canonical mission replay and all 24 gameplay fault families.

```sh
python -m skeleton.ai.game_builder.game_model_cli usage \
  --root ORIGINAL_STUDIO --director-blueprints /games/usage-a.json /games/usage-b.json \
  --trusted-local-operator

python -m skeleton.ai.game_builder.game_model_cli idle-pass \
  --root ORIGINAL_STUDIO --director-blueprints /games/idle-c.json /games/idle-d.json \
  --trusted-local-operator
```

`idle-pass` can be called by an **existing locally supervised idle-work
scheduler** when fresh approved fixtures are present; this commit does not
start a daemon or change the number/frequency of previous automated mirror
calls. It does actual offline verification, not a timer that marks a model
complete. The idle and usage cohorts may not contain any source project used
during fitting/heldout testing, or overlap each other.

Only then can the operator activate the **local advisory reviewer**:

```sh
python -m skeleton.ai.game_builder.game_model_cli activate \
  --root ORIGINAL_STUDIO --trusted-local-operator
```

To infer through the actual installed local weights, with a bounded
structured evidence object (an input-only JSON object):

```sh
python -m skeleton.ai.game_builder.game_model_cli predict \
  --root ORIGINAL_STUDIO --game-digest SHA256_OF_ORIGINAL_WORLD \
  --evidence-file /path/to/evidence-input.json \
  --trusted-local-operator
```

The response retains `canon_replay_required: true`; the model cannot
publish its answer as a confirmed game fact. Roll back if a new active
cohort regresses, or with an explicit reason:

```sh
python -m skeleton.ai.game_builder.game_model_cli rollback \
  --root ORIGINAL_STUDIO --reason "Unexpected original-game reviewer regression" \
  --trusted-local-operator
```

`status` requires no write permission. `recover` is an explicitly
authorized fail-closed recovery step after a power loss between writing an
immutable ledger entry and replacing the current registry state; its hash
chain must still reproduce exactly.

## Adversarial evaluation and fault tolerance

The verifier exercises two independent strategies: actual replay
verification for gameplay/mission correctness, and the model-specific
metamorphic challenge for shortcut detection. Each result carries source
world, replay and model IDs. Entire projects stay within exactly one train,
validation or test split; future live/idle checks demand new project IDs.

The registry journals every state transition as an immutable SHA-256
content-derived receipt, with a source-pinned candidate **including all
evaluation metadata**. Changing a benchmark report without altering the
numerical model weights invalidates its custody. State/journal divergence
blocks work until safe recovery. Missing/reordered entries, unauthorized
promotion, duplicate reviewers, missing fresh cohorts, tampered candidates,
weakening standards and severe new mistakes fail closed.

## Visibility in the local studio

The browser-based file-tree workbench now shows read-only reviewer
progression (phase, independent signoffs, usage and idle verification
status, model source count and rollback incident) through the
authenticated `/api/model-status` endpoint. This does not permit
browser-side model promotion or expose the trained weight vectors.
Run the existing supervised workbench server to view it:

```sh
python -m skeleton.ai.game_builder.game_workspace_cli serve \\
  --root ORIGINAL_STUDIO --open-browser
```

## Further competitive work

Still required for true advanced neural-model promotion: a reviewed
Jeeves/Dragon weight-training adapter, model checkpoints and optimizer
custody, genuinely licensed external source intake, adversarial prompt
injection defenses, independent human narrative/creative playtesting,
longitudinal live telemetry, larger and more diverse held-out real games,
statistical drift studies, hardware-target performance and a genuine
versioned *runtime inference routing* interface for each model family.

A local reviewer promotion does not establish that any of those systems
has been completed. Strict v2 shortcut robustness deliberately reveals
why older, seemingly accurate classifiers should **not** receive
unqualified product-readiness claims.
