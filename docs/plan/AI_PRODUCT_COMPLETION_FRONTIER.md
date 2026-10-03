# AI Product Completion Frontier — reverse build

This lane builds from the user-visible end of the standalone local AI inward to
the already-established provider-independent execution spine.

The implementation is intentionally **non-atomic** and end-to-end, but it does
not create a second authority model.

## Canonical path

```text
user turn
  -> ConversationThread / ConversationMessage
  -> SQLiteConversationRepository reference authority
  -> canonical ContextSegment sources
  -> ContextCompiler trust/budget selection
  -> provider-context projection
  -> FunctionalAIRuntime
  -> CognitiveExecutionRuntime
  -> local model + governed tools + verification
  -> durable AIExecutionResult
  -> canonical assistant message
  -> stable product response envelope
```

The assembled backend can use its production conversation authority while this
portable lane proves the same canonical contracts against the SQLite reference
implementation.

## Delivered contracts

### 1. Canonical conversation authority

The product edge reuses `ConversationThread`, `ConversationMessage`, exact-next
sequencing, optimistic thread versions, branch lineage, causal user/assistant
links, and the existing conversation repository. The provisional duplicate
session store from the first reverse pass was removed.

### 2. Canonical trust-aware context

Conversation messages enter the existing context source adapters. External
product context is accepted only as evidence-class canonical `ContextSegment`
values. Product callers cannot inject trusted control, tool schemas, tool
results, or conversation-role segments through that evidence input.

The existing `ContextCompiler` remains authoritative for:
- trust inspection;
- tenant/purpose admission;
- deterministic ranking;
- token budgets and omission;
- source snapshots;
- context digest identity;
- provider projection that labels non-conversation evidence as untrusted data.

### 3. Full semantic idempotency fence

Each user turn persists a reserved SHA-256 identity covering:
- user message;
- idempotency key;
- external context segment identities/content digests;
- attachment refs;
- allowed tool IDs;
- model/tool/repeat budgets.

A retry with the same idempotency key but changed execution semantics fails
closed before model execution.

### 4. Runtime policy/compiler identity fence

A second digest binds the turn to:
- exact instruction-policy identity;
- canonical context budget;
- context compiler version.

A process restart cannot silently replay an old execution under a changed
product policy/compiler identity and then label the result with a new context.

### 5. Exact execution correlation

The canonical user-message identity deterministically derives the Functional AI
request, operation, and execution IDs. The committed assistant message binds:
- operation ID;
- content-addressed AI result identity;
- context ID/digest/compiler version/source snapshot;
- tool receipts;
- memory refs;
- evidence/citation refs;
- artifact refs.

The response envelope independently re-checks those bindings against the durable
`AIExecutionResult`.

### 6. Crash-safe execution/commit recovery

There is an explicit regression for the dangerous window:

1. local model execution completes and is durably finalized;
2. assistant-message commit crashes;
3. process retries the same canonical turn;
4. the durable execution result is recovered;
5. the assistant message is committed;
6. the model is **not invoked a second time**.

This prevents duplicate cost/effects from a product-state commit failure.

### 7. Durable cancellation

Cancellation first records the execution cancellation request, then interrupts
the active local inference task. `LocalInferenceEngine` propagates task
cancellation to the worker's cooperative cancellation event.

The cognitive runtime then materializes one terminal `cancelled` result.
Conversation authority receives a deterministic system-derived cancellation
marker so the thread no longer ends on an orphan user turn and later turns can
continue without fabricating an assistant success.

### 8. Shared in-process execution join

Concurrent retries of the same canonical execution join one active async task.
Ordinary client coroutine cancellation is shielded from the durable execution;
only the explicit cancellation path owns authority to stop the operation.

### 9. Full restart replay

Acceptance closes and reopens both conversation and execution repositories,
constructs a fresh runtime, and proves the same response/execution/context
identity is replayed without invoking local inference again.

### 10. First-class assembled local provider

The engine provider registry can now activate `AI_PROVIDER=local` from an
explicit content-addressed model artifact. Local activation:

- requires `AI_LOCAL_MODEL_PATH`;
- validates bounded UTF-8 JSON, duplicate keys, non-finite values, artifact
  size, schema, and exact model digest before activation;
- registers only the local adapter;
- rejects external secondary-provider and semantic-verifier configuration;
- exposes a non-secret artifact/model receipt through provider status;
- performs no provider network I/O and requires no hosted-model credential.

The local provider is declared in the machine construction contract instead of
being a hidden test-only adapter.

### 11. Local model authority invariants

The provider-neutral local adapter now fails closed on:

- requested model identity that differs from the activated artifact;
- model tool calls that were not offered;
- tool calls when tools are disabled;
- missing required/specific tool calls;
- missing required structured output;
- expired/deadline-exceeding local inference.

Cancellation signals the cooperative local backend and uses a bounded grace
period so a non-cooperative Python worker thread cannot indefinitely hold the
request coroutine.

### 12. Assembled backend -> engine -> local-model path

Acceptance exercises the same authenticated backend/engine boundary used by the
assembled application with hosted-provider credentials absent. The engine
coordinator selects the local provider, executes through durable cognitive
state, verifies the result, emits local provider receipts, and persists the
terminal execution result before product commit.

This proves local inference is reachable from the assembled engine rather than
only from the lower `FunctionalAIRuntime` test surface.

### 13. Reconnectable canonical turns

Canonical chat supports two delivery modes over one execution identity:

- `wait`: compatibility behavior that waits for the terminal result;
- `deferred`: durably submits the turn and immediately returns operation and
  execution identity.

A later authenticated turn-status call can observe the durable engine state and
finalize the canonical assistant message. The original prompt/context body does
not need to be resent.

The engine submission store exposes a read-authorized **non-content handoff
binding** containing context ID/digest, compiler version, source snapshot,
operation/execution/turn/tenant identity, handoff digest, actor/capability,
idempotency key, and trace identity. Prompt, instruction, and history content
are deliberately not returned by that recovery endpoint.

### 14. Product cancellation and abandoned-turn closure

The product edge now exposes explicit turn cancellation. Terminal
failed/cancelled executions receive deterministic system-derived closure
markers in canonical conversation history.

That marker has two jobs:

1. preserve the immutable audit lineage explaining why no assistant success
   follows the user turn;
2. allow the next user turn to parent the closed tip instead of leaving the
   thread permanently blocked on an orphan user message.

Abandoned user turns and their closure markers are excluded from **both**
auxiliary history and canonical model-facing context projection. They remain in
product/audit history but cannot silently influence later inference.

### 15. Exact conversation ancestry

Normal user turns now explicitly parent the current active transcript tip.
Idempotent retries of an already-persisted incomplete user turn reuse its
original parent identity. This preserves user -> assistant -> user -> assistant
ancestry across multiple turns, reconnects, failures, and cancellations.

The frontend product client now exposes bounded start/follow/cancel/reconnect
helpers against the assembled `/api/ai/chat` route, carries abort signals, and
keeps transport delivery mode outside semantic execution identity.

### 16. Lower safety planes remain authoritative

This bridge does not:
- grant tool authority or approvals;
- verify model claims;
- declare side effects successful;
- bypass postcondition proof;
- promote models;
- turn retrieved/memory text into trusted control;
- replace execution, evidence, governance, security, or learning planes.

Effectful-tool postcondition enforcement remains below this layer in
`CognitiveExecutionRuntime`, so a permissive external verifier cannot turn an
unproven side effect into publishable success.

### 17. Explicit reverse learning handoff

The reverse path now continues one step inward from a completed product turn into
an offline learning candidate without granting the running model self-modification
authority.

Only explicitly selected canonical assistant messages can enter the handoff. Each
selected message must retain its causal user message, direct parent lineage,
operation/result identity, context identity/digest, and provider receipt lineage.
The handoff is fail-closed for missing inline content, mixed threads/branches,
unauthorized data classes, duplicate identities, oversized corpora, and tool-
augmented turns unless the caller separately opts those turns into learning.

The resulting corpus is content-addressed and deterministic. Repository-backed
handoff binds the corpus to an exact durable thread version and rejects a moving
or over-window transcript instead of learning from an ambiguous snapshot. It can
train the credential-free local recurrent backend into a **candidate-only**
artifact. The builder refuses to overwrite the exact path named by
`AI_LOCAL_MODEL_PATH`, reloads the exact candidate bytes, performs one bounded
offline inference qualification, and emits a digest-bound qualification receipt.
A broken candidate is deleted rather than left behind as a plausible artifact.

Evaluation firewall, Mirror Room qualification, promotion, rollout and rollback
remain distinct authorities.

### 18. Multi-method training and all-angle view coverage

The reverse path now compiles one accepted learning set through a single
content-addressed multi-method training authority instead of requiring separate
trainers for each learning style. The compiler can materialize 19 learning
families: causal LM, supervised instruction, self-supervised span reconstruction,
preference, distillation, contrastive, replay, curriculum, adversarial
robustness, multiview grounding, denoising autoencoding, sequence-to-sequence,
reward modeling, reinforcement traces, imitation, retrieval-grounded training,
pseudo-label/semi-supervised training, multitask training and active-learning
views.

Methods with missing evidence are skipped rather than fabricated. The training
receipt records configured, materialized and skipped methods, exact source
digests, method counts, budget drops and the deterministic plan digest.

Multiview training has an independent spherical camera-coverage contract. It
covers azimuth, elevation and roll, including canonicalized top/bottom poles,
and can vary FOV, distance and exposure under hard view-count bounds. Training
uses deterministic stratified subsets so a complete 360-degree source plan does
not explode into an unbounded Cartesian product. The view layer emits pose and
augmentation identities only; it never claims to have rendered image pixels.

The recurrent trainer now removes avoidable inner-loop work: multi-method
corpora are compiled in memory, gradient buffers are reused, embedding updates
are sparse by touched token row, epoch loss is collected from the existing
forward pass, and the multi-method builder uses bounded early stopping when
improvement plateaus. Multi-method training also accumulates gradients across
four documents by default, reducing optimizer-update overhead while plain
corpus training keeps one-document updates for compatibility. Receipts expose
the accumulation factor and exact optimizer-step count. Exact artifact validation and candidate-only promotion
semantics remain unchanged.

### 19. Adaptive training allocation and qualification evidence

Training-method selection is now a bounded deterministic optimization loop rather
than a fixed equal-cost sweep. Development, regression and Mirror Room validation
observations can report validation gain, compute units, evidence identity and
sample count for each method. The allocator shrinkage-weights gain-per-compute,
retains mandatory general learning methods, explores methods without evidence,
drops non-mandatory methods with negative observed efficiency and enforces both
per-method and total-repeat caps.

Promotion holdouts and production observations are explicitly rejected as
allocator feedback. This keeps the final evaluation firewall from becoming a
training oracle and preserves the holdout query budget for promotion decisions.

A separate qualification bridge reconciles the exact trained model/artifact and
training-plan digest with an explicit model-to-Mirror binding, Mirror Room
promotion evidence, evaluation-firewall promotion evidence, optional camera
coverage and adaptive-allocation identity. The resulting bundle has no production
authority and no self-modification authority. It exposes only candidate digest,
independent verifier identity and evidence references suitable for the existing
model lifecycle registry's CANDIDATE -> VALIDATED transition; lifecycle policy
still owns that transition and later activation.

### 20. Canonical model-program bridge

The reverse trainer now enters the repository's existing model-development
contracts instead of terminating at an ad-hoc product receipt. Every compiled
multi-method plan exposes a deterministic corpus digest derived from the exact
training document identities and content digests. The product/model-program
bridge authenticates the written local artifact again, proves the receipt's
model and artifact identities match the bytes, and maps the candidate into
`skeleton.learning.model_program.ModelArtifact` and `TrainingReceipt`.
The compiled-corpus digest becomes the canonical dataset digest for this
reverse-training run.

Promotion evidence is likewise typed rather than string-only. A
`ModelPromotionReceipt` can be produced from a qualified bridge only when its
candidate model, artifact and training-plan identities match and the model
promotion verifier differs from the trainer, Mirror verifier and evaluation
firewall evaluator. The receipt binds the learning qualification and
model-program bridge digests into its evaluation references.

This still does not mutate `AI_LOCAL_MODEL_PATH`. Model promotion evidence,
runtime artifact selection and provider activation remain separate authorities,
so the training system cannot silently self-activate a model merely because it
trained or evaluated successfully.

### 21. Real pixel learning and cross-view identity

The camera-learning path now accepts real image signal rather than camera hashes
alone. Sanitized image bytes are re-authenticated against the multimodal intake
digest, decoded with bounded dimensions, checked against sanitized width/height
metadata, and reduced into deterministic RGB statistics, luminance histograms,
4x4 spatial features and edge density. Those features are content-addressed and
bound to the exact camera-view identity.

Camera coverage is now self-authenticating. Coverage-plan digests are recomputed
from policy + exact view inventory, and pixel-derived observations require an
authenticated subset whose view references are proven members of that coverage.
This prevents a camera-view hash and a coverage digest from being paired
arbitrarily after training.

A twentieth executable learning family, `cross_view_consistency`, consumes two
or more authenticated visual observations and trains one invariant target across
their camera poses. Existing `multiview_grounding` still creates per-view
supervision; cross-view consistency adds the complementary requirement that
scene/object identity survive viewpoint changes.

Product candidate training can also accept supplemental `TrainingExample`
values under a separate explicit opt-in. This lets accepted dialogue and
authenticated multimodal/camera examples train one artifact and one training
plan while preserving exact supplemental-example, visual-observation and camera
coverage digests in the evaluation manifest. Supplemental examples are rejected
without opt-in and may not collide with conversation-derived example ids.

### 22. Closed local train-evaluate-reallocate loop

The local learning plane now has a separate developmental evaluator for training
feedback. It authenticates exact baseline and candidate artifacts, runs the same
bounded offline prompts against both models with no tools or network access, and
scores only explicitly declared required/forbidden output terms. Raw outputs are
not promoted into allocator state; content digests, scores, token work and exact
model identities form the deterministic report.

Developmental reports are explicitly non-production and are not promotion
holdouts. A report converts directly into the existing
`MethodValidationObservation` with `evaluation_class="development"`, allowing
measured candidate gain per compute unit to drive the adaptive method allocator.
This closes an executable local loop:

`train candidate -> developmental compare vs baseline -> allocator observation
-> next method weights -> retrain`

Promotion evaluation, Mirror holdout, lifecycle validation and activation remain
separate authorities, so optimizing the training loop cannot consume or tune
against the final promotion oracle.

### 23. Automatic method-probe training optimization

The local learner can now execute a bounded optimization round instead of
requiring a human to hand-assemble allocator observations. It discovers methods
compatible with the actual signal inventory, preserves mandatory general methods,
trains a deterministic candidate probe for each selected method, verifies the
probe artifact and its materialized training-plan attribution, compares it
against the exact baseline on the development-only suite, and feeds every
verified gain-per-compute observation into the adaptive allocator.

The resulting method weights are then used to train one final combined local
candidate. Probe artifacts are content-addressed in their evaluation reports and
may be deleted after evaluation; the report retains exact probe model and
artifact digests. The final optimization receipt binds baseline identity, source
example digests, probe report digests, allocation identity and final
model/artifact/training-plan identity.

The optimizer is bounded by probe count, probe epochs and gradient-accumulation
budgets. It refuses to overwrite the baseline or an existing final output and
has no production or promotion authority. The result still enters the ordinary
Mirror/evaluation/lifecycle path before activation.

### 24. Persistent continual learning, replay, and developmental rollback

Training optimization now persists across generations instead of ending after
one candidate. A content-addressed continual-learning state retains an append-only
developmental champion history, accepted replay examples, round receipts and the
currently selected developmental champion. State snapshots are written
atomically, verify their own digest on load, and can optionally authenticate the
active champion artifact bytes after restart.

Each round trains against the current champion and combines new examples with a
bounded deterministic spread of prior replay memory. The resulting challenger is
evaluated twice: an acquisition suite measures new capability while a separate
retention suite measures loss on established capability. Explicit policy sets
the minimum acquisition gain and maximum tolerated retention drop. A challenger
that violates either bound is rejected; when configured its artifact is deleted,
the current champion remains unchanged, and the rejected round still stays in
the append-only audit history.

Accepted examples enter bounded replay memory and accepted challengers become a
new developmental generation. Previous champions remain addressable by exact
model/artifact digest, so rollback selects an earlier authenticated local
artifact without mutating or erasing the lineage. None of these transitions has
production authority; Mirror, firewall, lifecycle validation and governed model
promotion still remain downstream.

### 25. Dependency-aware autonomous capability curriculum

The developmental plane can now score one exact local model directly against
bounded capability suites. Absolute score receipts bind the suite, model,
artifact, per-case output digests, token work and weighted mastery score without
needing a comparison candidate.

Capability objectives add explicit mastery thresholds, priorities, training
method hints and prerequisite capability IDs. The curriculum planner evaluates
the active developmental champion, resolves the dependency graph, blocks skills
whose prerequisites are not yet mastered, ranks eligible deficits by
priority-weighted mastery gap, and selects a bounded set of next targets.

Selected target suites are merged into the acquisition suite. Already-mastered
capabilities become retention evidence so the next continual-learning round must
improve the selected targets without excessive regression on prior capabilities.
During bootstrap, when no mastered retention inventory exists yet, the
development acquisition suite doubles as a non-promotion stability witness.

A curriculum round therefore executes:

`score champion -> resolve prerequisites -> rank mastery gaps -> select target
-> choose hinted training methods -> continual replay training -> acquisition /
retention gate -> rescore capability map`

When every declared capability meets its threshold, the planner produces no
target, performs no training, and writes no challenger artifact. Curriculum
state has no production or promotion authority.

### 26. Gated recurrent local model core

The multi-method learning path now defaults to a bounded GRU-style local model
instead of the original plain Elman recurrence. The gated backend uses explicit
update and reset gates around recurrent state, giving the local learner a direct
mechanism for preserving useful state and controlling replacement of prior
context while retaining the same provider-neutral inference interface.

The gated model remains credential-free and offline. It uses NumPy only, owns no
tools or network authority, and serializes every embedding, gate, recurrent,
output and bias tensor into one content-addressed JSON artifact under
`skeleton.numpy_gated_recurrent_lm.v1`. Loading recomputes the model identity
and the artifact loader authenticates the exact bytes before execution.

Multi-method, product, optimizer, continual-learning and curriculum training now
use `gated_recurrent` by default. The plain-corpus builder keeps the legacy
`elman_recurrent` default for compatibility and can opt into the gated backend
explicitly. Both architectures continue through the same atomic artifact writer,
training receipts and provider-neutral local inference runtime.

Architecture identity is evidence, not an implicit implementation detail. The
product evaluation manifest records it, qualification rejects manifest/receipt
architecture drift, and the canonical model-program bridge verifies that the
declared architecture matches the authenticated artifact schema before creating
canonical training or promotion evidence.

Focused regressions cover deterministic gated training, serialize/reload
identity, deterministic inference, gated multi-method defaults, legacy Elman
compatibility, architecture-drift rejection, schema/architecture mismatch
rejection, and averaged gradient accumulation for both recurrent backends.

## Acceptance gate

`AI Product Completion Acceptance` now compiles the product bridge and executes:
- canonical context compiler regressions;
- canonical conversation repository regressions;
- canonical product multi-turn/trust/correlation acceptance;
- full semantic-idempotency fencing;
- runtime policy/compiler drift rejection;
- execution-success / assistant-commit crash recovery;
- in-flight local-model cancellation;
- full repository reopen/replay without reinference;
- existing VS-001 local Functional AI regression;
- strict local model artifact/provider activation;
- local model identity/tool/deadline/cancellation invariants;
- authenticated backend -> engine -> local-model execution with hosted
  credentials absent;
- deferred turn submission and one-shot terminal probes;
- durable non-content handoff reconstruction after process-style reconnect;
- exact multi-turn parent lineage;
- cancellation closure followed by a clean next turn whose model context omits
  the abandoned request;
- frontend conversation transport route/reconnect contract checks;
- explicit accepted-turn -> deterministic learning-candidate lineage;
- privacy/tool-use learning admission guards;
- candidate-artifact training that refuses active-model overwrite;
- deterministic 19-family training-plan compilation and missing-signal skipping;
- in-memory multi-method artifact construction with bounded early stopping;
- sparse/reused recurrent gradient execution;
- spherical azimuth/elevation/roll/FOV camera coverage and bounded multiview
  training subsets;
- deterministic validation-gain-per-compute method allocation with promotion
  holdout exclusion;
- exact training -> Mirror Room -> evaluation-firewall -> lifecycle evidence
  reconciliation without production authority;
- compiled-corpus -> canonical ModelArtifact/TrainingReceipt conversion;
- independently verified canonical ModelPromotionReceipt creation without
  runtime self-activation;
- real authenticated pixel observations in multiview training;
- authenticated camera coverage subsets and tamper rejection;
- cross-view consistency training across multiple camera images;
- explicit supplemental multimodal examples in the same product candidate;
- executable local baseline-vs-candidate development evaluation feeding
  holdout-safe adaptive reallocation;
- bounded automatic method probes -> verified gain -> allocation -> final
  candidate training;
- restart-safe continual learning with deterministic experience replay;
- acquisition/retention gating with catastrophic-forgetting rejection;
- authenticated developmental champion rollback with append-only history;
- absolute developmental capability scoring on the active local champion;
- dependency-aware autonomous target selection from measured mastery gaps;
- no-op completion when all declared capabilities satisfy thresholds;
- gated recurrent multi-method training with legacy Elman compatibility;
- architecture identity preserved through evaluation, qualification and the
  canonical model-program bridge.

This frontier closes the product-edge seam by using existing authorities more
deeply, not by building a parallel chat stack. It is an engineering completion
frontier, not a claim that model quality, general intelligence, or SI capability
is complete.


### 22. Governed activation and executable rollback

Qualification now reaches an explicit runtime-selection boundary instead of
ending at promotion evidence. A promoted local candidate and its exact rollback
baseline are re-authenticated from disk and bound into one
`LocalModelActivationManifest`. The manifest records candidate/baseline artifact
and model digests, the canonical `ModelPromotionReceipt`, training receipt,
learning qualification, model-program bridge, verifier identity, cache/seed
settings, and an explicit operator authorization reference. The manifest is
content-addressed, written atomically, and must be deployment-pinned through
`AI_LOCAL_ACTIVATION_DIGEST`.

Governed local startup uses
`AI_LOCAL_ACTIVATION_MANIFEST` + `AI_LOCAL_ACTIVATION_DIGEST`. The operator may
set `AI_LOCAL_ACTIVATION_TARGET=candidate` (default) or
`AI_LOCAL_ACTIVATION_TARGET=rollback`. Both targets are loaded from the same
authenticated manifest; rollback therefore selects the exact pre-promotion
baseline bytes rather than a mutable loose path. A target is rejected when no
activation manifest is configured, and `AI_LOCAL_MODEL_PATH`, cache, or seed
overrides must agree with the selected manifest target.

This closes the reverse functional chain as an executable control path:

`accepted product turn -> bounded training candidate -> offline execution
qualification -> Mirror Room -> sealed evaluation firewall -> independent model
promotion receipt -> operator-authorized activation -> candidate execution or
authenticated rollback`.

None of these learning or evaluation objects can switch the target themselves.
Production selection remains an operator/deployment action, and both candidate
and rollback preserve the same digest-pinned evidence chain.
