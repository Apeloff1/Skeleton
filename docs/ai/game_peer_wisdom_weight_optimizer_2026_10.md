# Game-AI multi-actor wisdom, adversarial weight optimization, and qualification

Scope: original-game local reviewer, **not** neural Jeeves/Dragon foundation models.
The implementation is stacked on game-builder #3642 via #3643. All third-party
knowledge is quarantined and rights-reviewed. No new binary OS service, web
crawler, transcriber, independent real benchmark, or LLM trainer is asserted.

## 1. Five independent contributions; five non-transferable permissions

| Actor / layer | Evidence it supplies | Authority it cannot supply |
|---|---|---|
| Wiki | Current, owner-bound, human-reviewed source revision and exact-span evidence, retractions, independent publisher groups, stance and uncertainty | Self-awarded model training rights or model promotion |
| Dragon | Content-addressed game domain almanac; original peer article/video/blog/paper reference metadata, mechanics, uncertainty and provenance pointers; research agenda | Copy third-party expressive text/audio/frames to weights |
| Jeeves logic | Deterministic if/then research plans when evidence supports, contradicts or is missing; must generate new original-game experiments | Assert that programmatic conditions are an LLM's independently verified conclusions |
| HOAG quality | Typed predeclared benchmark thresholds and independent champion/challenger comparison via the existing PromotionStandard | Turn an attractive research source into a measured model improvement or fake competitor score |
| Mirror/training | Actual isolated 256-dimensional review-classifier SGD, source-preserving train-only transformations, validation-model selection, frozen final TEST, independent usage/idle | Bypass rights, canonical gameplay verification, independent reviewer signoff or install core Jeeves/Dragon weights |

**Rights and knowledge are distinct:** source citation clearance does not mean
model-training permission. Sources must remain registered for
\`FACTS_IDEAS_REFERENCE\`; authorship, license and similarity controls are
enforced by the existing RightsLedger. This architecture intentionally does
**not** convert the article, blog or video's text, quotes, frames or transcript
into neural gradient data. If a later pipeline is authorized to train on
licensed external material, that requires a **separate** model-training
permission and independently proven corpus chain.

## 2. Dragon media-source admission and almanac synthesis

- Accept an operator-reviewed ReviewedKnowledgeStore with exact source URLs,
  source SHA, revision chain, evidence spans, reviewed mechanic claims,
  independent source-dependence groups, and confidence.
- Require a matching design_reference KnowledgeBrief and canonical
  ClearedResearchPacket. Verify both against the *live* Wiki library and
  RightsLedger immediately before distillation.
- Require one SourceMediaReceipt per referenced source, bound to its exact
  revision. Accepted kinds: video, article, blog, paper, technical_report,
  community_review, original_playtest.
- Peer-review evidence digests **without cryptographic attestation** are only
  metadata claims. A forged 64-character hash cannot elevate confidence,
  trigger model training, certify a paper, or sign an almanac.
- Condense each independently sourced stance into a single mechanic/dependence-
  group vote. Hundreds of reposts by one publisher cannot multiply support.
- Limit reference-confidence heuristics, explicitly mark disagreements,
  carry uncertainty, and create action-specific Jeeves research tasks.
- Preserve references, source rights revisions, mechanism identifiers,
  score summaries, and instruction conditions. Do **not** copy third-party
  paragraphs, video frames or transcripts into the Dragon almanac.
- Publish immutable, content-addressed JSON under
  \`training/dragon_peer_almanacs/<digest>.json\` through an operator-owned
  GameWorkspace. Replay is idempotent. Digest collisions with altered content,
  symlink destinations, stale rights and missing review fail closed.

The output includes no promotion permission, no copied copyrighted expression,
no executable downloaded code, no training samples and no model parameters.

## 3. Genuine model-weight optimization

\`OptimizerSchedule\` defines a bounded, completely enumerated lattice of
learning-rate and epoch settings. Each trial calls the actual existing
\`train_robust_game_reviewer\` with \`evaluate_test=False\`.

1. The TRAIN partition alone contributes gradients. Only TRAIN worlds receive
   adversarially equivalent metadata/envelope augmentation.
2. Each trial chooses epochs and threshold using independently authored
   VALIDATION worlds, including source-preserving adversarial presentations.
3. Trials are compared using a predeclared tuple: minimum ordinary-vs-
   adversarial balanced accuracy, adversarial Brier score, ordinary Brier score.
   Exact ties prefer fewer epochs and smaller learning rate.
4. **No trial opens TEST.** The chosen schedule is deterministically refitted
   once. Its policy digest, chosen validation score and adversarial score must
   exactly match the selection-only checkpoint.
5. The frozen winner alone is evaluated against TEST and the incumbent
   champion using the existing model-promotion gate, with per-project,
   attack-family, danger-recall, calibration and monotonic-standard checks.
6. The result provides real trained local reviewer weights, a signed-by-digest
   experiment receipt and a separate independent PromotionEvaluation;
   \`deployment_authorized\` remains false.
7. Trusted \`optimize-stage\` may place a passing optimized candidate into the
   **existing** staged registry. Six distinct role reviews, usage, idle,
   explicit human/operator activation and rollback remain mandatory. It cannot
   directly swap active model weights.

Use the explicit local CLI:

\`\`\`shell
python -m skeleton.ai.game_builder.game_model_cli optimize \
  --root STUDIO --trusted-local-operator \
  --epoch-candidates 30 60 --learning-rates 0.08 0.16 0.28
python -m skeleton.ai.game_builder.game_model_cli optimize-stage \
  --root STUDIO --trusted-local-operator \
  --epoch-candidates 30 60 --learning-rates 0.08 0.16 0.28
\`\`\`

Default high-quality strict counterfactual bar remains 0.98 in the CLI.
An optimized model may fail the gate; success is never assumed. Windows shell
examples may require command-line continuation syntax adjustment.

## 4. Integrated knowledge-to-games admission

\`run_integrated_learning_cycle\` requires all five lanes' relevant evidence
before launching a real local reviewer training run:

- Fresh canonical reviewed Wiki brief and matching reference-rights packet;
- Dragon-almanac claim structure with independent source groups;
- No unresolved source disagreement in any requested mechanic;
- At least two independent supporting groups per mechanic, with the declared
  minimum heuristic research readiness;
- At least two **distinct original TRAIN world digests** whose independent,
  quarantined gameplay evidence explicitly covers the same mechanic;
- A predeclared, typed, bounded optimizer schedule and quality standard;
- Explicit local operator authorization.

If any mechanic lacks the right original-game evidence, the entire integrated
run returns a **gap plan** instead of reporting partial success and secretly
fitting on its easier mechanics. The operator must create new original games,
independently replay gameplay, obtain legitimate source-almanac receipts,
quarantine the complete TRAIN examples and try again. Source articles are never
used as substitutes for replayed original-game labels.

## 5. Adversarial failure and recovery matrix

| Failure | Required behavior |
|---|---|
| Source retracted or claim revised | Recompute Wiki brief and rights clearance; invalidate stale Dragon synthesis |
| New rights decision or unresolved similarity | Stop; refuse cleared research reuse |
| Wrong media-source revision | Reject peer source classification |
| Fake peer-review digest | Carry as unverified metadata only; cannot add epistemic weight |
| Repeated same publisher, article, or source ID | Collapse dependent confidence votes or reject duplicate source receipt |
| Contradictory peer claim | Create explicit conflict/research task; block integrated optimizer |
| Mechanic with one or zero original TRAIN worlds | Return missing-world gap; no weight updates |
| Unknown, malformed mechanic metadata | Reject before aligning claims with original gameplay |
| Unauthorized invocation | Fail closed; do not fit or publish |
| Candidate training on TEST / selecting by TEST | Reject; selection-only receipts have TEST unopened |
| Divergent SGD weights on replay | Reject non-reproducible checkpoint before final qualification |
| Weaker quality standard, missing independent cohort, copied evidence | Existing promotion registry keeps activation blocked |
| Foreground resumes during idle evaluation | Cooperative preemption; no observer state publication |
| New full optimization lacks uplift against installed model | Retain incumbent, return blocked evaluation or remain experimental |

The test suite simulates unsupported sources, rights changes, source retraction,
duplicate medium receipts, deterministic almanac replay, staged vs active
authority, false claim inflation, independent original-world alignment,
validation-only hyperparameter selection, exact replay weights and refusal of
unreviewed protected labels. Tests are designed as gates, not demonstrations
that an LLM has become wiser or beaten a competitor.

## 6. Standards, measurement and honest industry comparability

The design borrows the **evaluation discipline**, not the data or results, of
MLCommons AILuminate: keep public practice and protected evaluation separate,
report per-category results, evaluate fixed model configurations, and prevent
unreviewed test prompts from becoming future training data. AILuminate's
12-hazard safety taxonomy is not automatically a game-quality or game-engine
benchmark; no official MLCommons score is claimed.

Model capability must be measured independently on actual original games by
console/PC era, platform, genre and task using canonical replay plus verified
scenario quality. Production benchmarks require independently controlled real
assets, hardware footprints, confidence intervals, latency, reliability,
readability, scene composition, NPC agency, dialogue/witness accuracy, ethics
and originality/rights scores. Existing local classifier accuracy is NOT a
proxy for all these areas.

## 7. Planned next integration beyond this PR

- Route real Dragon crawler transcripts or articles into ReviewedKnowledgeStore
  *through* the existing authenticated source-rights intake. Preserve
  uploader consent, source terms, transcript provenance and revocation.
- Bind actual Jeeves inference and HOAG comparison services as separately
  authenticated actors, with verifiable receipts rather than label strings.
- Implement signed reviewer credentials and nonce-bound approvals; six
  different names by themselves do not prove independent human review.
- Introduce model serving admission for actual Jeeves/Dragon weights under the
  canonical \`skeleton/ai/learning\` control plane with signed checkpoint,
  independently measured validation, protected canary and rollback.
- Only propose stronger standards when evaluated capabilities truly exceed a
  predeclared model-level benchmark; do not substitute file counts or generated
  almanac counts for useful performance.
- Add fresh hardware telemetry and proper host-level idle/service integration;
  current idle scheduler only cooperates with supplied trusted probes.

**Release condition:** exact-head Linux/Windows tests, dependency/rights review,
source-identity integrity, reviewer challenge accuracy, heldout evidence,
usage+idle original-world replays, verified independent attestations, rollback
and operator approval. Draft PR remains unmerged until qualified.
