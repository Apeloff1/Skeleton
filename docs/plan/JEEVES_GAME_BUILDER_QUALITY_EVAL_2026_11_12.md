# Jeeves local game-building quality diagnostics

Status: implemented measurement harness; useful-game quality and competitive
superiority remain unestablished. This public diagnostic suite is owned by the
existing `skeleton/eval` plane. It does not create a model, provider, runtime
owner, source-write authority, deployment permission, or promotion authority.

## What the suite measures

`skeleton/eval/game_builder_quality.py` defines 24 fixed synthetic tasks and a
deterministic scorer. Its taskset digest binds prompts, output field contracts,
expected constraints, alias groups, and instructions. The taskset is public;
calling it held-fixed does not make it a hidden holdout or prove that a model
has not seen similar material during training.

| IDs | Capability | Deterministic checks |
| --- | --- | --- |
| gb01–gb04 | Requirement extraction | Explicit features, input methods, numeric conditions, and unresolved decisions |
| gb05–gb07 | Constraints | Offline persistence, resource ceilings, and excluded features |
| gb08–gb11 | Structured design | Scene inventory, bounded inventory, state transitions, and save data types |
| gb12–gb15 | Godot/GDScript text | Velocity units, gravity integration, signal connection, and Godot 4 method names |
| gb16–gb19 | Debugging | Duplicate signal guard, diagonal normalization, timer reset, and health clamping |
| gb20–gb22 | Grounding | Evidence identifiers, missing facts, instruction-in-evidence resistance, and unproved release claims |
| gb23–gb24 | Iteration consistency | Preserve approved values while applying the requested change |

The report keeps **structure**, **requirements**, **correctness assertions**, and
**latency** separate. A field can satisfy a fact check while another field or the
JSON contract fails; the report retains both observations. Unknown fields,
duplicate JSON keys, non-finite JSON, wrong scalar types, fabricated evidence,
and added requirements do not pass the applicable checks. Requirement labels
accept documented aliases and order changes rather than requiring golden prose.

Code is inert text. The few code assertions compare lexical statement shapes,
ignoring whitespace/comments and keeping string literals atomic. This avoids a
comment or quoted snippet satisfying a code check, but it is deliberately
conservative: an equivalent alternate expression may fail. It does **not** parse
all GDScript semantics, compile a script, execute generated code, validate a
complete game, measure maintainability, or establish security of arbitrary code.

Natural-language quality beyond these bounded labels, creative quality, fun,
visual quality, asset rights, playable-game completion, real export quality,
independent human acceptance, and comparative superiority are explicitly
unmeasured. Those require separate blinded language/code review, native game
tests, real playtesting, and the canonical benchmark-governance process.

## Run against the operator's real local model

The operator script uses the existing `load_gguf_deployment` loader and
`LocalInferenceEngine`. Only an existing digest-pinned local GGUF deployment
whose admitted model ID is `jeeves` is accepted. There is no model download,
provider credential, hosted fallback, replacement model, training, or generated
code execution. The local adapter supplies its existing native artifact checks,
bounded subprocess execution, credential filtering, and cancellation behavior.
This is not an independently attested network sandbox.

From the repository root, start a short diagnostic in a **new** private directory:

```sh
.venv/bin/python scripts/evaluate_jeeves_game_builder_quality.py \
  --manifest /absolute/path/to/jeeves.json \
  --output-dir /absolute/path/to/new-private-diagnostic \
  --limit 6 --output-tokens 192 --task-seconds 120 --total-seconds 900
```

Run the complete suite in a separate new directory by omitting `--limit`:

```sh
.venv/bin/python scripts/evaluate_jeeves_game_builder_quality.py \
  --manifest /absolute/path/to/jeeves.json \
  --output-dir /absolute/path/to/new-private-full-suite \
  --output-tokens 192 --task-seconds 120 --total-seconds 1800
```

For a fixed subset use `--task-ids gb01,gb05,gb12,gb16,gb20,gb23` instead of
`--limit`. Results use canonical task order. The output budget must be 64–256
tokens per task; there is one in-flight generation. Each task has a 1–600 second
deadline and the invocation has a finite total deadline of at most 14,400
seconds. The underlying deployment's own stricter bounds remain in force.
The seed and temperature are recorded; the runner requests temperature zero.

Token exhaustion remains visible through `finish_reason=length` and
`possibly_truncated=true`. A syntactically complete JSON prefix at the token
limit cannot become an all-checks task pass. The harness never trims an answer
into a passing JSON object, retries a failed sample until it passes, or hides a
failed slice. A full suite of measured responses is not a suite of successful
responses.

## Retained artifacts and strict resume

The output directory is private (0700 on POSIX). Files are create-only and 0600;
existing results are never overwritten. Do not store results inside the source
tree or commit deployment model paths, weights, or runtime binaries.

- `run.json`: source head, evaluation/runner/test/runtime source hashes, model
  and runtime digests, deployment/config identity, execution profile,
  environment, task selection, seed, and budgets.
- `taskset.json`: complete fixed synthetic prompts and deterministic scoring
  checks, bound by the recorded taskset SHA-256.
- `source-snapshot/`: actual measured evaluation, runner, test, and selected
  native adapter source bytes at their recorded hashes; useful when a run used
  an uncommitted working tree. These are retained as evidence, never executed.
- `00-gb01.json`, etc.: full response text, response/request digests, individual
  checks, distinct dimension counts, elapsed time, finish reason, native local
  execution receipt digest, token observations, and stable error class.
- `summary-NN.json`: summary for an immutable completed prefix, remaining task
  IDs, stop reason, source-identity check, and resume cursor.

Per-task files form a hash chain bound to the run identity. A hash chain detects
unaccounted edits; it is not independent attestation that model execution or
semantic correctness occurred. Resume also recomputes scores from stored raw
responses, so a changed counter cannot create a passing result.

After an interrupted invocation, use the **same** arguments and add `--resume`:

```sh
.venv/bin/python scripts/evaluate_jeeves_game_builder_quality.py \
  --manifest /absolute/path/to/jeeves.json \
  --output-dir /absolute/path/to/existing-private-full-suite \
  --output-tokens 192 --task-seconds 120 --total-seconds 1800 --resume
```

Resume rejects changes in source head, measured source/test files, taskset,
model, configuration, selected tasks, environment, and budgets. It requires a
contiguous prefix of valid results, verifies the chain, and never skips unknown
or corrupt files. An incomplete file is held for operator inspection rather
than silently deleted. An acknowledged failed diagnostic is retained as a
failed sample; resuming proceeds to the next unmeasured task, not a favorable
replacement of the failure. Each resumed invocation receives the same recorded
finite invocation budget.

The existing local OS-backed inference lease serializes runners using that
result workspace and retains POSIX child ownership after supervisor death.
It is not a global scheduler across every other application, model, or
workspace on the host. Operators must serialize other heavyweight local model
campaigns or record interference as a changed environment.

Exit 0 means every selected task was measured and the source identity remained
stable; inspect the actual failed-check counts. Exit 3 means incomplete or
failed execution; exit 2 means the run was held by an input, identity, artifact,
runtime, or operator interruption condition. A partial report never establishes
24-task completion or a quality win.

## Qualification and next evidence

Focused scorer and artifact checks:

```sh
.venv/bin/python -m unittest discover -s tests -p test_game_builder_quality.py -v
```

These tests verify strict JSON/type handling, aliases, constraint drift,
instruction-in-evidence failures, static code false positives, latency bounds,
identity changes, tampering, partial files, create-only persistence, and strict
resume. They do not load a GGUF or simulate genuine model quality.

Before competitive use, freeze an independently reviewed workload, untouched
holdout, scorer, model/configuration, environment, resource budget, sample plan,
primary outcome, practical effect, exclusions, and independent verifier under
`machine/competitive_ai_benchmark_governance.json`. Preserve all adverse results;
do not tune this public taskset and present the rerun as a held-out quality gain.
Latency samples from 24 heterogeneous diagnostics do not qualify p95/p99 serving
performance. There is no aggregate superiority score and no automatic promotion.

For game-builder delivery, use diagnostic failures to create separately tracked
implementation improvements, then evaluate on independent tasks and actual
playable/exported game acceptance. A small local model producing valid JSON is
useful plumbing evidence, not proof that it can independently build an
impressive game.

## Explicit structured-output configuration experiment

`--structured-output` is an opt-in candidate configuration. Plain JSON
instructions remain the default. The candidate passes a schema derived only
from each task's requested field names/types to the existing local inference
request. Schemas require the requested keys and deny unknown keys; they do not
contain expected answers, answer enums, alias lists, or semantic constraints.
The model can still produce factually wrong but structurally valid answers.

The native adapter owns schema-constrained decoding and whole-object validation
through its existing `--json-schema-file` path. Without tools it returns a typed
`structured_output` object, with `text=None`. The runner serializes that validated
object as canonical JSON for the unchanged scorer and records
`response_representation=canonical-json-of-runtime-validated-structured-output`.
This is not the original stdout formatting; the native execution receipt binds
the stdout identity. The runner never extracts JSON from prose, strips fences,
normalizes an answer into correctness, or executes generated code.

Run the candidate in a new result directory by adding `--structured-output` to
the full-suite command. Keep model weights, runtime, taskset, scorer, seed,
output/time budgets, and environment fixed. `run.json` records the generation
mode, each task schema digest, and request-policy digest in addition to runtime
configuration. The user task text remains fixed; the native structured-output
protocol and schema are the deliberately changed experimental condition.

This experiment changes inference configuration, not model weights or training.
It was selected after the baseline exposed instruction-following failures, so it
is a public diagnostic improvement experiment, not a preregistered independent
competitive study. Existing artifacts remain immutable; updated runner versions
cannot resume an older source identity as though nothing changed.

## First real local baseline, 2026-11-12

Executed all 24 tasks against the existing operator-owned
`Qwen3-0.6B-Q8_0.gguf`, model ID `jeeves`, CPU profile (2 threads, GPU layers 0,
4096 context), seed 17, temperature 0, output budget 192 tokens, per-task 120
seconds, invocation budget 1800 seconds. No model was downloaded or substituted.
The full result directory is the local artifact
`/workspace/artifacts/jeeves-game-quality-baseline`; it contains all responses,
source snapshots, `run.json`, `taskset.json`, and `summary-24.json`.

| Identity | Bound value |
| --- | --- |
| Source HEAD plus retained working-tree file hashes | `1d663d7e7188285a0433ba6ca087aa7d97fb8257` plus `run.json` source map |
| Model SHA-256 | `9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031` |
| Runtime SHA-256 | `7119bef261611b26f326f7c4da4dc3fdeb7bb28e2faf1ec392bda7b21215ef52` |
| Fixed taskset SHA-256 | `ddb5b43ba5aa5c14fc0598f32264dd94e58d0fa0b6f7035901468b5779c28ff1` |
| Baseline runtime config SHA-256 | `7e191dd852b1ad025f9d30d4c63010b9bd3cb7d3e8282969b1812b6fa749f69f` |
| Baseline run identity SHA-256 | `214c98ddd9e57e69169950a9d037763236f6e4b4e107f9b8f64b066adcd0d3e2` |

All 24 responses completed; none reported truncation or a deadline. The measured
source identity remained unchanged. A same-source completed resume revalidated
all artifacts and returned the identical final summary without generating more
responses. This is real GGUF execution evidence, not a native fixture run.

| Category | Measured | Strict complete task passes | Valid requested JSON shape | Parse rejections |
| --- | --- | --- | --- | --- |
| Requirements | 4 | 0 | 1 | 3 |
| Constraints | 3 | 0 | 0 | 3 |
| Structured design | 4 | 0 | 0 | 4 |
| GDScript text | 4 | 0 | 2 | 2 |
| Debugging | 4 | 0 | 0 | 4 |
| Grounding | 3 | 0 | 0 | 3 |
| Iteration consistency | 2 | 2 | 2 | 0 |

Strict totals: structure 5/24, requirement assertions 5/21, correctness
assertions 2/28, all-check task passes 2/24. Time across the 24 tasks was 106.326
seconds; median 4.295 seconds; maximum 7.803 seconds. These heterogeneous samples
do not qualify tail performance. The strict correctness/requirement counts
include assertions inaccessible after JSON parse rejection; they must not be
read as an independent finding that every rejected answer's facts were wrong.

Observed failures include:

- Nineteen outputs used markdown fences despite the JSON-only contract. Some
  enclosed correct facts. The strict scorer deliberately did not strip fences.
- `gb12` asserted that Godot 4 `move_and_slide` takes a velocity argument;
  `gb13` proposed `velocity.y = velocity.y * delta + gravity`; `gb14` invented
  `connect_body_entered("coin");`; `gb15` used `isOnFloor` and `move`.
- `gb16` selected `frame_count` instead of the collected-state guard. `gb19`
  returned health 1 and no death after a hit of 2 from health 1. `gb20` omitted
  the supplied S1 evidence identifier. These are content issues beyond fences.
- `gb23` and `gb24` preserved the approved values and applied the requested
  changes; they passed all deterministic checks.

Known scoring limitations were identified without modifying the frozen taskset
or scorer: `gb01` used the reasonable label `local saves`, absent from the
frozen alias group, creating a false negative. `gb17` returned `normalize`, a
real mutating Vector2 method, while the frozen key accepts `normalized`; the
prompt does not adequately distinguish the return-value/mutation requirement.
Those cases need independent adjudication and a future explicitly versioned
taskset; they are not silently rescored in this baseline or its candidate.

The baseline shows useful execution and some constrained iteration consistency.
It also exposes unreliable JSON compliance and specific game-code/content
errors. It does not establish impressive game-building ability, general model
quality, production readiness, or an advantage over another product.

## Structured candidate observed results, 2026-11-12/13 UTC

The first structured attempt was held at `gb01` by `LocalInferenceOverloaded`
before a native output was produced (0.042 seconds); 23 tasks were unmeasured.
Its complete failure record remains at
`/workspace/artifacts/jeeves-game-quality-structured`. An unrelated Expo process
was using about 2.85 GB RSS. Its owner stopped it; a subsequent read-only probe
observed about 6.25 GB allocation headroom against an estimated 2.116 GB first
request requirement. This is evidence of the changed resource envelope, not an
independent retrospective proof of the exact initial rejection branch.

A fresh complete candidate ran in
`/workspace/artifacts/jeeves-game-quality-structured-clean`. It retained the same
model/runtime/configuration, taskset/scorer bytes, seed, and token/time budgets
as the baseline. The explicit changed condition was native structured-output
decoding and its associated schema protocol. Runner/test source changed to add
that experiment; both versions are preserved in their source snapshots.

The clean run measured 24/24 real responses, had no truncation/deadline result,
and retained an unchanged measured source identity. A completed same-source
resume revalidated the identical result. Baseline and clean-candidate counts:

| Measurement | Plain baseline | Structured candidate |
| --- | --- | --- |
| Requested JSON shape | 5/24 | 24/24 |
| Requirement assertions passing under the strict scorer | 5/21 | 19/21 |
| Correctness assertions passing under the strict scorer | 2/28 | 19/28 |
| All deterministic checks passing for a task | 2/24 | 15/24 |
| Requirement tasks passing | 0/4 | 2/4 |
| Constraint tasks passing | 0/3 | 2/3 |
| Structured-design tasks passing | 0/4 | 3/4 |
| GDScript-text tasks passing | 0/4 | 2/4 |
| Debugging tasks passing | 0/4 | 1/4 |
| Grounding tasks passing | 0/3 | 3/3 |
| Iteration tasks passing | 2/2 | 2/2 |

This demonstrates improved observed contract compliance on this public fixed
diagnostic, while the remaining content failures prevent a reliable game-builder
quality claim. It is not a randomized, blinded, independent, or competitor
comparison, and formatting rejection confounded the baseline assertion totals.
No inference about hidden-task generalization or creative game quality follows.

The candidate corrected the velocity/gravity expressions in `gb12`/`gb13` and
passed the three bounded grounding tasks. Remaining responses included:

- `gb04`: unresolved decisions `platform`, `target`, `choice`, omitting the
  requested camera/multiplayer distinctions.
- `gb06`: both enemies and textures marked violated, despite 48 MB fitting the
  64 MB texture ceiling.
- `gb09`: four correct inventory items but `free_slots=2` instead of zero.
- `gb14`: fabricated `connect_body_entered_coin_to_on_body_entered`; `gb15`:
  `move` instead of `move_and_slide`.
- `gb16`: `frame_count` guard set after scoring; `gb17`: `diagonal` instead of
  a Vector2 normalization method; `gb19`: health 1/no death instead of 0/death.
- `gb01`: the same `Local Saves` alias limitation already disclosed for the
  baseline. The frozen scorer was not changed to improve this result.

The clean candidate observed 99.533 seconds total, median 3.631 seconds, maximum
8.891 seconds. Background host conditions differed and other native tests could
use CPU; these numbers are descriptive only and do not establish a latency win,
resource-efficiency improvement, or qualified tail behavior.

| Candidate evidence | Value |
| --- | --- |
| Request policy SHA-256 | `b3457d9a003fb2b1ceb3fdd6fc5e86c9e2d90bd9c174fb1468724c1df716beb6` |
| Protocol/source/config identity SHA-256 | `a7fdee5248682f7a850e20c942f75269af734c126ffad92d96e76d087e09ed90` |
| Clean final result-chain SHA-256 | `45278724c5a63d234bc51f5cbea45b0c075163e2a2c612f6d55802eaef859e2b` |
| Source, individual schema hashes, and complete typed-object responses | Clean candidate `run.json`, `source-snapshot/`, and per-task JSON files |

The held and clean attempts share protocol/source/config identity because that
digest describes their declared conditions, not a unique execution nonce. Their
directories, result chains, completion states, and resource observations are
distinct and retained. Do not substitute the clean result for the held record.
Neither attempt grants model promotion, primary-model replacement, publication,
or release authority.

## Separately pinned coding-model candidate, 2026-11-13 UTC

A third complete campaign evaluated the separate operator-owned
Qwen2.5-Coder-1.5B-Instruct Q4_K_M candidate. The primary Jeeves manifest and
weights were unchanged. The coding candidate used a separate deployment
manifest at `/workspace/jeeves-coding-model/jeeves.json`; results are retained at
`/workspace/artifacts/jeeves-game-quality-coder15b`.

The experiment retained the exact public taskset and scorer, structured-output
mode, seed 17, temperature 0, output 192, 120-second task deadlines,
1800-second invocation budget, 2 CPU threads, 4096 context, and GPU layers 0.
Weights, quantization, and the recognized coding ChatML template changed
together. The canonical deployment profile selector had also gained the named
coding profile; the new source hashes and actual bytes are retained. This is a
comparison of two declared model configurations, not an isolated causal estimate
for parameter count, quantization, or training alone.

| Coding candidate identity | Bound value |
| --- | --- |
| Model SHA-256 | `cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046` |
| Runtime SHA-256, shared with the earlier campaigns | `7119bef261611b26f326f7c4da4dc3fdeb7bb28e2faf1ec392bda7b21215ef52` |
| Manifest file-byte SHA-256 | `0048c42c93b27fe9bfae136054cb80d29bc8d81796ba7e02df7df105bfe82edb` |
| Canonical manifest JSON-payload SHA-256 | `58e37f3550382f84102caca2bf82cefd968f046d4af0f3c3b8aa5ef870cb4707` |
| Run identity SHA-256 | `38fc9e4dddce4dcb15357a0cec3682bd8d0380004464271e5422e42b9a52ecd9` |
| Final result-chain SHA-256 | `2070ade71828056f90744727efce22e671a56419869d244a738e7c1db5552112` |

File-byte and canonical-payload digests are deliberately labelled separately;
pretty-printing changes the former without changing the latter. Each run's
actual deployment file bytes, runtime configuration identity, request policy,
and source snapshot remain authoritative for reproducing that run.

All 24 coding-candidate tasks produced real native responses without a
truncation/deadline result; the measured source identity remained unchanged.
There were **72 complete diagnostic responses** across the plain 0.6B baseline,
structured 0.6B candidate, and structured 1.5B coding candidate, plus the
separately retained resource-held attempt that produced no model response.

| Measurement | 0.6B plain | 0.6B structured | 1.5B coding structured |
| --- | --- | --- | --- |
| Requested JSON shape | 5/24 | 24/24 | 24/24 |
| Requirement assertions | 5/21 | 19/21 | 19/21 |
| Correctness assertions | 2/28 | 19/28 | 17/28 |
| Strict task passes | 2/24 | 15/24 | 13/24 |
| Requirement tasks | 0/4 | 2/4 | 2/4 |
| Constraint tasks | 0/3 | 2/3 | 2/3 |
| Structured-design tasks | 0/4 | 3/4 | 2/4 |
| GDScript-text tasks | 0/4 | 2/4 | 1/4 |
| Debugging tasks | 0/4 | 1/4 | 1/4 |
| Grounding tasks | 0/3 | 3/3 | 3/3 |
| Iteration tasks | 2/2 | 2/2 | 2/2 |

The coding candidate still multiplied horizontal velocity by delta, asserted a
velocity argument for `move_and_slide`, used the old-style
`connect('body_entered', self, '_on_body_entered')` form in a Godot 4 task, named
the movement method `move`, and returned health 1/no death for the clamped-damage
case. It marked both enemy and texture limits violated and returned one free
inventory slot after filling a four-slot inventory. It passed the three bounded
grounding tasks and the two approved-value preservation tasks.

Frozen-scorer caveats still apply. `gb01` again used `local saves`; `gb17` returned
`Normalize`, a genuine mutating Vector2 method under an underspecified prompt.
`gb10` returned `dead on zero health` rather than the required state identifier
`dead`, despite correctly disabling movement. Report the actual values and
consumer-contract failure rather than extrapolating that result into a broad
reasoning deficit. No alias or reference answer was changed during comparison.

Observed coding-candidate time was 172.757 seconds total, median 7.147 seconds,
maximum 9.303 seconds. Background conditions and native test activity were not
controlled, so these are descriptive timings, not a qualified speed comparison.
These public diagnostic counts provide no reason to automatically replace or
promote the primary model. They do not establish a general model ranking,
competitive superiority, trained-model improvement, independent language/code
quality, or impressive playable-game quality. The evidence supports the narrower
engineering conclusion: native schema decoding improved observed output-contract
compliance, while both small local model configurations retain material
game-code and reasoning failures that need grounded assistance and independent
gameplay/code acceptance.

## Optional Godot source-reference development experiment

`--reference-pack godot46` explicitly adds a frozen, locally rendered reference
pack from the existing evaluation owner. The default has no reference context:
all original task prompts and system instructions remain unchanged. A grounded
full-suite invocation is:

```sh
.venv/bin/python scripts/evaluate_jeeves_game_builder_quality.py \
  --manifest /absolute/path/to/jeeves.json \
  --output-dir /absolute/path/to/new-private-grounded-suite \
  --structured-output --reference-pack godot46 \
  --output-tokens 192 --task-seconds 120 --total-seconds 1800
```

The first pack contains eight agent-written summaries of primary Godot 4.6 API
documentation and two explicitly labelled derived implementation patterns. It
covers velocity/motion, physics processing, floor contact, vectors, Area2D,
signals, one-time effects, and terminal-state handling. Source URLs and the
distinction between documented API behavior and derived patterns remain in
metadata. These notes are **untrusted source data**, not system policy,
permissions, verified generated code, human signoff, or a model-promotion record.

Selection uses only the `gdscript` and `debugging` categories under the explicit
`code_debugging` scope. The same complete reference text is appended to the
**user prompt** for all eight selected tasks; the other sixteen prompts remain
unchanged. The pack does not import the taskset/scorer, inspect task IDs, contain
per-task answer keys, or change the fixed tasks, expected assertions, aliases,
or scoring implementation. The model's existing instructions continue to treat
supplied documents as untrusted task data.

The frozen pack metadata records ID/version, Godot version, review date, scope,
selected categories, source URLs, facts/source kinds, rendered context, maximum
context allowance, byte count, and digest. The runner adds that metadata and a
per-request context-admission map to `run.json`, binds them into request-policy
identity, and retains `reference-pack.json` plus the reference module's actual
source bytes in `source-snapshot/`. The actual expanded user prompt is bound by
each native request digest; the taskset's original task-prompt digest remains
unchanged and must not be mistaken for the expanded inference prompt.

Before the first native dispatch, the runner prepares **every selected request**
and uses the loaded model's exact rendering/conservative input counter with the
canonical `LocalInputBudget` validator. Input plus output must fit the declared
context budget. Reference text is limited to 2200 UTF-8 bytes; it is never
silently shortened, character-trimmed, or selected to fit a failing individual
task. An oversized pack or campaign is rejected before model generation. Any
pack reduction must be reviewed, assigned its changed digest, and frozen before
a new campaign begins. Resume checks the pack metadata, rendered text, source,
request-policy identity, and all existing source/model/configuration bindings.

Focused qualification now includes 34 runner/scorer/artifact tests and 14
reference-pack contract tests. Integration checks demonstrate category-only
selection, unchanged default prompts/instructions, user-context placement,
request-digest changes, metadata round-trip identity, strict whole-campaign
budget admission, and Unicode byte bounds without truncation. A read-only
preflight on the actual 0.6B deployment admitted all 24 requests: eight had
reference context, and the largest conservative input-plus-192-output bound was
2600 against a 4096 context limit.

The final pack used for this phase has 1309 UTF-8 context bytes and canonical
digest `cd88d2c65b1413157cf4c9fb78bd83e61f8c9d77600f2aa03ac00a763306bf72`.
The taskset remains
`ddb5b43ba5aa5c14fc0598f32264dd94e58d0fa0b6f7035901468b5779c28ff1`; the
scorer module bytes remain
`26e11aed1857a44b0928098d8b650e9f1467768c49340b3c07cd78b6cbaf49c0`.

This is **post-diagnostic development grounding**: the reference material and
scope were chosen after observing failures on this public taskset. A changed
result can inform implementation work, but cannot establish untouched-holdout
generalization, training improvement, independent language/code quality,
competitive superiority, or a general-purpose impressive game builder. All
earlier raw artifacts and their exact source snapshots remain intact. The
existing frozen-scorer caveats continue to apply.

### Grounded campaign result: no net strict-score gain

The complete grounded run is retained at
`/workspace/artifacts/jeeves-game-quality-grounded`, including the frozen pack,
source snapshots, all per-task responses/receipts, `summary-24.json`, and a
create-only `comparison-to-structured.json` audit. All 24 responses completed,
none reported truncation or deadline, the measured source identity remained
unchanged, and all strict context preflights passed. A same-source resume
revalidated all pack/response/source identities and returned the identical final
summary without another model generation. Across the four complete
campaigns there are now **96 real diagnostic responses**, plus the separately
retained resource-held attempt with no model output.

| Measurement | 0.6B structured without reference | 0.6B structured with reference |
| --- | --- | --- |
| Requested JSON shape | 24/24 | 24/24 |
| Requirement assertions | 19/21 | 19/21 |
| Correctness assertions | 19/28 | 19/28 |
| Strict task passes | 15/24 | 15/24 |
| Requirement tasks | 2/4 | 2/4 |
| Constraint tasks | 2/3 | 2/3 |
| Structured-design tasks | 3/4 | 3/4 |
| GDScript-text tasks | 2/4 | 2/4 |
| Debugging tasks | 1/4 | 1/4 |
| Grounding tasks | 3/3 | 3/3 |
| Iteration tasks | 2/2 | 2/2 |

The audit confirms matching model/runtime/configuration, seed, budgets, taskset,
scorer identity and scorer module bytes. Source HEAD changed between phases,
and runner/test/reference sources changed deliberately; the recorded
`local_ai.py`, native inference engine, and llama.cpp adapter bytes are identical
between the ungrounded and grounded runs. All sixteen control responses outside
the selected categories are identical as retained canonical structured values.

Five selected responses changed (`gb12`, `gb14`, `gb15`, `gb16`, `gb17`), with one
strict pass gained and one lost:

- **Improved `gb15`:** `is_on_floor` / `move_and_slide` replaced `is_on_floor` /
  `move`, matching the requested Godot 4 methods.
- **Regressed `gb12`:** the previously correct `direction * speed` became
  `velocity.x * speed`; the no-velocity-argument answer remained correct.
- **Still failed `gb14`:** `area.body_entered.connect(handler)` copied the
  generic reference form without binding the requested `_on_body_entered`
  method. A valid generic API example is not a completed task-specific edit.
- **Still failed `gb16`/`gb17`:** the guard stayed `frame_count` and its timing
  value became `screen_width`; the vector method became `velocity`. Those
  values do not satisfy the task choices or normalization API.
- `gb13` gravity integration and `gb18` timer reset remained correct. `gb19`
  remained health 1/no death; this reference pack did not solve the arithmetic
  and terminal-state task.

Observed total time was 96.628 seconds, median 3.872 seconds, maximum 5.297
seconds. These remain descriptive, uncontrolled timings; no speed, tail,
resource-efficiency, or performance-improvement claim is made.

| Grounded evidence | Bound value |
| --- | --- |
| Source HEAD plus retained working-tree snapshots | `0cc6283f5b8c081e4f372d9c6970f703d646bbda` plus the run source map |
| Reference module SHA-256 | `76b5f3e3b42ae28a7569e3a52820f816010946a6029fad9dd898923a38dbb971` |
| Reference pack canonical digest | `cd88d2c65b1413157cf4c9fb78bd83e61f8c9d77600f2aa03ac00a763306bf72` |
| Run identity SHA-256 | `4648819a6d1e1b08ffa3bb2eb73e7541034ed3bd12ace93a9760e5ae887de1f7` |
| Final result-chain SHA-256 | `4ee886da3b3944fcb8aa13cd3868b882c083376dee867133af0633b481ca0e23` |

The best observed strict task count remains 15/24, shared by the 0.6B structured
configuration with and without this reference pack; the separate 1.5B coding
configuration scored 13/24. This pack produced no net gain on the fixed
diagnostic. The primary model and default inference behavior remain unchanged;
there is no automatic promotion or general model ranking. The paired regression,
known scorer limitations, and all adverse outputs remain in the record. Further
grounding or product changes require separately recorded development experiments
and independent task/code/gameplay acceptance before claiming broader quality.
