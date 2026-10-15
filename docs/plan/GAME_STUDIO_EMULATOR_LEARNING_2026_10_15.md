# Emulator-compatible original-game policy learning

The canonical original-game advanced reference engines are not libretro
cores and cannot load ROMs. This adapter implements **the same learning
environment protocol** (`spec/reset/step/preview/snapshot/restore/close`)
used by the Jeeves emulator training system. It supplies actual state-derived
observations and replay-backed transitions for the existing
`GamePolicyLearner` and `ParallelGamePolicyTrainer`.

* Canonical execution: `skeleton/ai/game_builder/advanced_gameplay_runtime.py`
* Integration: `skeleton/jeeves/game_studio_environment.py`
* Existing learning: `skeleton/jeeves/game_learning.py`
* Existing actors: `skeleton/jeeves/game_learning_parallel.py`
* Candidate CLI: `skeleton/jeeves/game_studio_policy_cli.py`

Use `GameEnvironmentRequest(target_id="studio:economy",kind="studio",
tree=studio_request_tree(make_studio_source("economy")),max_steps=32)`.
This produces the same policy-spec objects and independently replayable
snapshots as the other built-in learning environments. All **33 registered
reference game engines** can now expose their mechanics through this interface.
The policy action set is an explicit subset of at most 32 actual game commands;
an episode supports at most 128 accepted or rejected turns. Unsupported
commands, foreign scenes and forged snapshots fail closed.

## Actual candidate training

With the original project's rights cleared and private writable output path:

```bash
python -m skeleton.jeeves.game_studio_policy_cli \
  --engine economy --episodes 8 --max-steps 32 \
  --actions inspect wait survey buy:1 sell:1 travel:1 \
  --output /private/new-studio-candidate.json \
  --authorized --rights-cleared
```

The tool executes original gameplay episodes, performs **real tabular Q-value
updates** and writes a new candidate policy checkpoint and trace digests.
It never overwrites active policy state, never edits the production Jeeves
transformer or claims equivalent neural-weight improvement. Professional
model-weight training remains separately checkpoint-pinned under
`skeleton/ai/training/jeeves_production_game_session.py`, where no
session-to-neural-dataset integration is claimed in this slice.

Rewards combine observed progress, score/wealth, health, actually earned
outcomes, rejected action penalties, and per-step cost. This is task-specific
local policy learning; results require independent evaluation before promotion.
Preview intentionally supplies state fields, not imaginary frames. Full native
emulator pixels/audio remain exclusive to the approved libretro runtime.

## Opt-in learning from actual gameplay

The same candidate CLI also accepts `--played-actions inspect survey wait`
with `--consent-ref operator-consent:demo-9`. It executes those controls
against the real replay-authoritative engine, records the typed episode using
`GameDemonstrationRecorder`, independently replays all commands with
`learn_demonstrations`, and only then applies the genuine Q updates and
an imitation prior. The final candidate includes the demonstration digest
and number of measured action-derived optimizer updates.

This action-learning path is explicitly consent and rights-gated. It cannot
accept an uploaded unchecked label as sufficient proof and cannot silently
write production neural weights.

## Canonical application routing

The existing authenticated `backend/core/game_learning.py` workspace now
recognizes the exact `game/studio/session.json` project file, rejects
ambiguous engine roots, resolves `studio:<editor>` from the strictly
validated source rather than a fictional console ID, and advertises registered
studio engines through the existing catalog response. Normal project
simulation, human demonstration, local policy jobs, parallel actors and studio
campaigns can resolve the engine through the existing workspace authority.
Episode replay depth is limited to 128 even where a generic job asks for more.

This does **not** create a second ungoverned API or skip tenant/project/source
authority. Frontend integration and exact-head application tests remain
necessary before release.

## Real Jeeves neural candidate from replay-verified engine experience

An additional bridge, `skeleton/ai/training/jeeves_studio_curriculum.py`,
collects actual original-game state transitions into a training-only corpus.
Each episode is independently re-executed, with bounded action, seed,
engine source and SHA256 identity. On checkpoint training, untrusted serialized
claims are rejected, and the corpus is replay-verified a second time.

```bash
python -m skeleton.ai.training.jeeves_studio_curriculum \
  --engine economy --actions inspect survey wait --seed 9 \
  --output /private/engine-corpus.json --authorized --rights-cleared
sha256sum /private/engine-corpus.json
python -m skeleton.ai.training.jeeves_production_game_session \
  --run-id game-corpus-01 --attestation /private/attestation.json \
  --output-directory /private/new-candidate-folder \
  --studio-corpus /private/engine-corpus.json \
  --studio-corpus-expected-sha256 <independently-verified-64-hex-sha>
```

The checkpoint trainer must still have a real independently pinned
`SKELETON_OWN` model, does actual optimizer updates only on a **candidate**,
and independently evaluates its held-out outputs. This does not automatically
train or promote live production weights, or prove improved game design.

## Create a game-engine project directly in Jeeves's learning workspace

The existing authenticated learning application now admits `console_id=
"studio:economy"` (and every registered original-game engine) in the
regular create-project route. It builds the actual default
`game/studio/session.json` from the canonical editor schema, not a fake
console profile. Native/libretro paths are unchanged. The normal project
get/simulate/record/train and replay-fenced source writes retain the tenant
and rights boundaries. Source types cannot be silently swapped across two
authoritative engines. The existing React Native learning-workspace console
picker now shows searchable **Original game** engine options from the same
backend catalogue. No parallel ungoverned API or fake hardware renderer was
introduced.

## Replay-linked measured game-state telemetry frame

`skeleton/jeeves/game_studio_frame.py` generates a deterministic 96x64 RGB24
status visualization from the actual source-executed per-step observation and
session receipt. `StudioGameEnvironment.preview()` exposes it through the
existing emulator-compatible `pixels_base64 / width / height / format`
frame contract without a second API, and carries a SHA-256 digest, explicit
state metric labels, and a source session digest. The existing frontend
recognizes `render_kind="reference_state_telemetry_raster"` and labels the
frame as telemetry, never as actual engine-world pixels or audio.

This is a visual monitor for learning mechanics, not a game renderer. Native
emulator RGB remains bound to the approved actual libretro framebuffer.

## AI-proposed rules and multi-circumstance model learning

`skeleton/jeeves/game_studio_rule_curriculum.py` is a pure, bounded
`rule_authoring_contract(source)` and `apply_rule_proposal(source, proposal)`
gateway. Jeeves may propose source-bound, non-executable typed data edits,
but never arbitrary Python, imported code, unknown model knobs, player
inventory, victory, identity, source ownership or policy promotion. The
existing editor and authored-scene normalization revalidates every change.
A proposal is pinned to a SHA-256 digest of the original canonical game
source; a stale model suggestion cannot mutate another engine version.

Admitted edit operations: `set` existing typed value, `add` or
`multiply` bounded integer settings, `toggle` existing boolean, or
one source-bound scalar leaf in an authored layout. At most 12 edits per
proposal and seven variants per curriculum are admitted. Layout edits
cannot create new objects, change IDs, add script/URL fields, bypass
original-only constraints, or silently reuse a scene under incompatible
settings. For engines without authored scenes, only settings variation is
available.

**Example rule batch for the default economy engine.** Generate the parent
SHA-256 from a canonical source through the `rule_authoring_contract`
helper, rather than typing or guessing it:

```json
{
  "schema_version": "skeleton.game_builder.ai_rule_batch.v1",
  "proposals": [
    {
      "schema_version": "skeleton.game_builder.ai_rule_proposal.v1",
      "proposal_id": "high-price-volatility",
      "base_digest": "<actual hash returned by rule_authoring_contract>",
      "reason": "Challenge the economic policy with more elastic market prices.",
      "scene_seed": null,
      "operations": [
        {"scope": "settings", "path": "price_elasticity", "op": "add", "value": 3},
        {"scope": "settings", "path": "trade_tax", "op": "add", "value": 5}
      ]
    }
  ]
}
```

After the source hash is inserted and the operator clears the source
training rights, the candidate-only CLI can use this reviewed proposal
JSON and the existing source instead of a new external provider:

```bash
python -m skeleton.jeeves.game_studio_rule_training_cli \
  --editor economy --proposals /private/ai-rule-batch.json \
  --episodes-per-scenario 4 --max-steps 24 --seed 23 \
  --output /private/new-rule-policy.json \
  --neural-corpus-output /private/new-rule-neural-corpus.json \
  --authorized --rights-cleared
```

The outcome contains a single policy conditioned on the actual scenario,
measured Q updates, baseline-vs-candidate returns for each circumstance
on disjoint held-out seeds, source and transition digests, and no
automatic production promotion.

`skeleton/ai/training/jeeves_studio_rule_corpus.py` replays one
actual policy-training trajectory per scenario, pins all distinct game
rules and scenario seeds, and generates bounded observed learning text.
`load_studio_curriculum` independently reconstructs that multi-source
corpus and checks the caller-supplied, independently obtained SHA-256.
The existing `jeeves_production_game_session` can then ingest the file
with its `--studio-corpus` and `--studio-corpus-expected-sha256` flags.
This **only** adds operator-admitted candidate neural-training data; the
compiled app must supply the real attested live checkpoint, run the optimizer
and independently evaluate generated outputs before any production promotion.

**Existing governed campaigns:** `skeleton/jeeves/game_studio_learning.py`
now advertises actual studio engine setting knobs to its deterministic
bandit search. It proposes schema-validated edits to the exact
`game/studio/session.json` source, runs candidate Q-training in the
existing campaign authority and compares real source-bound evaluations
against the champion and adversarial perturbations. Invalid changes are
recorded as rejected proposals. The bandit is *not* falsely represented
as another natural-language LLM inference call; separate AI-model text
proposals enter through the explicit declarative proposal contract.

Release gates remain pending: exact-head Python tests, worker/IPC
integration, runtime security checks, actual campaign trials, actual
neural optimizer run, independent domain benchmarks and engine/world quality.
No complete engine/app, hardware, audio, rendering or real-world
generalization quality claim follows merely from these registrations.

## Parallel emulator-style rule-curriculum workers

`GameEnvironmentRequest(kind="studio_rules",
target_id="studio-rules:<editor>", max_steps=<plan.max_steps>,
tree={"game/studio/rule_curriculum.json": <canonical-plan-json>})`
now reconstructs the exact scenario graph through the existing isolated
emulator-style rollout actor interface. The request admits one exact
source file, rejects unapproved content/ROM/registry data and derives its
environment specification from the same source-verified plan.

Both the scenario scheduler's own source SHA and every underlying studio
game implementation digest bind the learning environment. Changes to
the rule engine or gameplay logic invalidate stale policy evidence.
Snapshots independently replay the scheduled scenario and command log;
policy training uses `GamePolicyLearner`, and the existing parallel
rollout actors can execute this request without inventing an emulator.

The training CLI itself now uses this `GameEnvironmentRequest` factory
for local measured updates and heldout evaluation. It does not
automatically start parallel workers, and CI/live worker execution
has not been independently observed for this commit.

## Advanced scenario laboratory and parallel visible simulations (2026-10-15)

The existing game-learning campaign UI now exposes
`GameStudioScenarioLabPanel` for source-registered `studio:*` projects.
Users can control 2, 4 or 6 mirrored spectator angles and per-view step
budgets, with a finite four-worker thread pool and one user-authorized
scoped preview route. The 96 × 64 visual panels are sampled real
`StudioGameEnvironment.preview()` state telemetry, **not** native
rendered gameplay, actual training episode captures, neural output,
libretro video or production-world camera recordings. Every frame/summary
derives from actual engine state and source-bound replay data. Spectators
do not mutate game source, campaign progress, policies or weight updates.

GET `/api/game-studio-learning/campaigns/{id}/mirror-views?lanes=4&steps=12&sample=0`
uses the campaign's scoped current champion source, code and rights guards,
bounded concurrency and per-request deterministic seeds. The frontend
refreshes these **read-only spectator runs** while the campaign is active
only when the user enables viewing; it stops/aborts on component unload
or account/campaign switch. No hidden perpetual background simulator is
created.

GET `/api/game-studio-learning/campaigns/{id}/scenario-drafts` consumes
a bounded page of *committed* measured campaign evidence and asks
`propose_scenarios` for strictly typed, source-sha-bound feasible rule
changes. Outputs explicitly distinguish hypothetical variants from
supported failure-stress cases. It cannot execute untrusted suggestions
as Python, claim known successful scenarios or approve adoption. The
existing governed Jeeves campaign engine supports such rule settings as
candidate mutations and learns from actual Q-updates, held-out
perturbations, Dragon checks and replay receipts.

GET `/api/game-studio-learning/engines/{id}/test-manifest` enumerates
every registered source action, every bounded editor field's min/default/
max or enum axes, six mirrored perspectives and eighteen mandatory
contract checks (scene checksum, replay, snapshot, invalid controls,
resource conservation, rights, heldout contamination, telemetry, etc.).
An unexecuted checklist is **not** a passed test. Full combinations of
game states cannot be exhaustively enumerated for nontrivial worlds;
the matrix covers declared types and risk categories instead.

Source-informed original scenario motifs use public factual charts:
Nintendo official June 30, 2026 publisher-reported worldwide lifetime
Switch software units (e.g. Mario Kart 8 Deluxe 71.53M,
Animal Crossing: New Horizons 50.29M, Super Smash Bros. Ultimate 38.14M),
and the separate US 2025 full-year **dollar-sales ranking** reported by
Circana (e.g. Battlefield 6 #1, NBA 2K26 #2, Borderlands 4 #3).
These two scales cannot be merged or normalized into game-quality scores.
No copyrighted levels, characters, dialogue, images, code, ROM, physics
tables or maps are captured or redistributed; only original high-level
mechanic stress questions are drafted. A sale rank is not causal proof
that one game design decision is best.

`mirrored_rule_comparison` pairs baseline and proposed rule worlds on the
same seeds across six named angles, with bounded concurrent execution,
source/transition identities, rejection counts and worst-case return
differences. The separate rule-candidate trainer now stores these
checks against heldout scenario seeds alongside its real Q-learning,
but **does not** automatically promote a scenario for merely passing a
sampled angle test or train the live Jeeves production checkpoint.

Release limitations: exact-head CI and tests unverified; long-running
resource/performance load, native audio/GPU/network/hardware emulation,
all possible training angles, actual neural candidate updates and
independently proven game-design quality are not complete. This is a
substantial reference-engine **training and research plane** rather
than full implementation of every physical production engine.

## Executable diagnostics, concurrent evaluation and real work evidence

The `skeleton/jeeves/game_studio_engine_diagnostics.py` tool permits
paged execution of **every** registered engine command without
mislabeling an initially unavailable input as successful gameplay.
For each selected control it resets the original runtime twice,
checks deterministic observed transitions, independently restores
the snapshot and records either accepted actual game action or a
typed rejected state. Its additional contract run tests canonical
source identity, invalid fields, unknown action rejection, same
seed reset, snapshot reconstruction and visual telemetry identity.

```bash
python -m skeleton.jeeves.game_studio_engine_diagnostics \
  --engine economy --seed 7 --offset 0 --limit 32
# Inspect next_offset and repeat until null to exercise the *entire*
# registered action palette. The pass list is executable evidence,
# not a claim that every imaginable state was exhaustively tested.
```

The authenticated `GET /api/game-studio-learning/engines/{editor}/probes`
API bounds each call to sixteen separately replay-verified commands
(the UI requests eight) with a single backend diagnostics admission
semaphore, and displays actual passes/rejections from each page.
An unset/failed probe cannot be surfaced as a completed test.

**Concurrent *training-campaign* evaluation:** the canonical
`StudioLearningCampaign._round` now evaluates multiple ordinary and
adversarial control runs using a bounded four-thread executor only for
original-game studio reference runtimes; all true emulator providers
retain their existing sequential execution path. Six further
`mirrored_rule_comparison` angles compare paired source-world
circumstances for each genuinely modified studio candidate, and
their worst-case observed reward difference is an explicit additional
champion-acceptance gate. The recorded round counts actual mirrored
steps, not the requested maximum. These measurements become part
of committed campaign evidence and deterministic report digests.
The spectator viewer is a distinct, read-only concurrent view—not
the campaign's frozen training-step framebuffer.

Actual production release still requires exact-head execution of
the runnable suites, backend/frontend type and security checks,
independent gameplay/engine acceptance, dataset rights checks,
real checkpoint-derived neural training, and native graphics,
sound, networking, persistence and platform verification. Nothing
here certifies 43 complete shipping-grade game engines.

## Effective learning per simulated compute — admission gate

To prevent simulation volume being misrepresented as training progress,
`mirrored_simulations` now measures each executed lane's accepted versus
rejected controls, **non-time gameplay state changes**, distinct numeric
game states, deterministic state-trajectory digest and actual replayed
action applications (sum of 1..N for a source runner that replays the
entire accepted game command log every step). Plain clock changes and
no-op actions do not count as new gameplay knowledge.

Paired source-matched evaluations publish an
`informative_for_rule_selection` flag only when at least four actions
were executed in total, at least two productive state transitions
occurred across the paired experiments, at least two candidate commands
were valid and at least one measurable reward/state-trajectory
difference is observed. An uninformative variant can be classified
`insufficient_behavioral_evidence` but **cannot** pass the new champion
promotion gate merely because it happened to avoid a reward regression.
This is a conservative evidence screen, not proof of causality or
game-design excellence. Novelty per 100 replayed action applications
exposes the cost of redundant source replay.

The campaign now admits worst-case additional mirrored work **before**
starting a slice, and fences the observed total executed steps against
the authorized budget before committing the round. This prevents
unbounded auxiliary scenario checking when an episode budget is
nearly exhausted. Round receipts include actual effective state
changes, replay work, worst observed difference and the reason
insufficient scenarios did not promote.

`propose_scenarios` uses bounded local numeric perturbations rather
than leaping directly to the largest/smallest permitted engine values.
It consumes a digest denylist of previously tried settings from
checked committed campaign history and avoids rediscovering identical
original-game variants. The user-facing scenario lab shows previously
explored and skipped counts, plus per-lane *productive* changes. It
never treats public sales positions as optimization rewards or
derives causal training labels from commercial game popularity.

These are **implemented gate and telemetry contracts**, not claims
that training metrics have been measured in a live compiled app. CI,
native engine acceptance, all scripted tests and real hardware/emulator
performance still need separate evidence before sign-off.
