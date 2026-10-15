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

## Measured candidate training utility and early-stop receipts

`game_studio_rule_training_cli.py` now spends episodes in *complete
round-robin scenario sweeps*, rather than eagerly consuming the entire
requested training budget. It counts accepted game commands, rejected
commands and productive changes in non-explicit-time observed gameplay
features from the **authoritative recorded training trace**. After two
full scenario sweeps with zero such changes across all scenarios, it
stops spending further episode budget and reports
`stopped_after_two_nonproductive_scenario_sweeps` and the exact
`unused_training_episode_budget`. Other runs continue up to the
operator's previously admitted maximum. No hidden extra optimization
or unapproved model promotion is invoked.

Each outcome now distinguishes the **maximum requested** episodes
from **actually executed** episodes and Q-value updates. The optional
checkpoint-derived neural training input uses the most productive
observed *training* trajectory per scenario (favoring productive state
changes, actual accepted commands and distinct states), still
independently replays every source on publication and never consumes
heldout evaluation episodes as optimizer examples. Informational
features are proxies—not a scientific proof of eventual neural
generalization or game design excellence. Existing campaign
champion acceptance also requires measurable six-angle source
differences and its independent Dragon, adversarial, heldout and
regression constraints.

These optimizations do not fix fundamentally absent native game
runtimes, guarantee a successful game outcome, or turn popular-game
sales into causally verified mechanics. Tests and actual candidate
weight production remain pending.

## Ten-run multispectral mirror-room training and post-simulation scrutiny

Implementation:
* `skeleton/jeeves/game_studio_multispectral.py`: ten-pass, independent
  source-bound postrun audit and ten derived numeric gameplay channels for
  **each** completed simulation. Every supplied step is replayed separately
  against the actual engine; the registered action palette, code/runtime
  digest, episode seed, complete transition digest chain, scalar rewards,
  terminal/command accounting and final observation/snapshot are checked.
  Intermediate original-game snapshots are reconstructed in **reverse
  checkpoint order**, using independently replayed prefixes (not time
  reversal of a physical world), and every analysis band is computed
  from real source projections. A failure raises and blocks acceptance.
* `skeleton/jeeves/game_studio_scenario_lab.py`: ten distinct analytical
  mirror perspectives: exploration, progress, safety, economy,
  adversarial pressure, boundary, temporal, causal, perturbation and
  recovery. Ten independent seed/angle scenarios are executed by a
  bounded four-worker executor; each includes multispectral evidence and
  **ten checks**. Every 43-family source runtime is eligible, subject to
  its actual declared features and actions. Different perspectives do not
  constitute independent cameras or prove exhaustiveness of world states.
* `backend/core/game_studio_learning.py` and
  `backend/routes/game_studio_learning.py`: source-scoped authenticated
  spectator route can request 1–10 runs, default 10, at 1–24 steps each;
  network responses contain explicit passed-run and sensor-hardware
  metadata. Spectator runs remain **independent of live policy updates**.
* `frontend/features/Jeeves/GameStudioScenarioLabPanel.tsx`: 10-run
  mirror control and per-run compact presentation of all ten analysis
  means, peaks, reverse checkpoints and strict audit counts.
* `skeleton/jeeves/game_studio_learning.py`: non-native studio candidate
  gameplay rounds now admit ten real **training** episodes each (1–10
  supported) and independently check ten source-matched mirror angles.
  Where changed-rule scrutiny executes paired baseline and candidate
  mirrors, the preflight reserves at most twenty such **auxiliary**
  source episodes (in addition to the normal training/evaluation budget);
  the actual executed work is rechecked before committing each round.
  Existing native emulator source budget, governance and review boundaries
  remain unchanged.
* `skeleton/jeeves/game_studio_multispectral_training.py`: standalone,
  operator- and rights-gated **actual Q-learning** from ten independently
  audited mirror seeds, ordered by witnessed source-state novelty, accepted
  actions and replay-work cost; executes ten additional real local
  game-action learning episodes and three separate heldout policy
  evaluation seeds. Produces candidate snapshots and digest receipts,
  **never** production Jeeves neural weights or automatic policy promotion.

Example, after entering a rights-cleared, original source and an
existing private candidate directory:

```bash
python -m skeleton.jeeves.game_studio_multispectral_training \
  --engine economy --seed 13 --max-steps 8 \
  --output /private/candidates/ten-run-original-game.json \
  --authorized --rights-cleared
```

The 10 numeric analysis channels per source episode are **motion,
economy, vitals, objectives, reward, events, control, temporal, novelty
and safety**. They derive from the same actual engine's observed
gameplay states, accepted/rejected commands, recorded reward components
and authored event list. This is *multiband game telemetry*, NOT
physical multispectral photometry, independently measured thermal
emission, RGB camera/depth sensor stacks or real GPU image semantics.
It is mathematically unsound to market ten projections from one state
as ten independent sensors; the audit records that distinction.

Research inspiration, without implementation-identity or metric claims:
* DreamerV3 general world-model training and replay ratio:
  https://www.nature.com/articles/s41586-025-08744-2
* Prioritized Level Replay, revisiting productive levels:
  https://proceedings.mlr.press/v139/jiang21b.html
* Structured domain randomization with semantics preserved:
  https://link.springer.com/article/10.1007/s10462-025-11431-3
* EnvDreamer (October 2026): validator-admitted environment variety:
  https://arxiv.org/abs/2610.04301

The implementation draws from these ideas but does not claim
DreamerV3, TD-error PLR, true real-to-sim multispectral sensors,
native 3D/graphics/audio simulation, proprietary game content,
trained live model checkpoints or automatically verified increases
in game-model accuracy. Training tests and all 43 real engine
integration gates must run on the exact PR head before release.

## Adaptive shadow-clone saturation and escalating per-sim scrutiny

**Critical semantics change**: `10` is a *consecutive unproductive
cycle requirement after evidence stops improving*, NOT the total
simulation count. Every original studio simulation gets its own
independently maintained source-verified history and counters. The
new `skeleton/jeeves/game_studio_shadow_saturation.py` executes a
fresh source-bound simulation at every iteration, then forks one
actual **saved intermediate game checkpoint** into an isolated shadow
environment and takes an alternate allowed action. The fork state,
next command, transition digest, parent source and independent full
replay must agree. Each primary and shadow path passes the existing
ten-check multispectral audit, including reverse checkpoint prefix
verification. A cycle has at least **20 independent baseline checks**
plus escalating extra checks up to **8 additional gates at peak**
(when source and actions support the check).

A newly seen semantic witness is keyed to the authoritative action
name, accepted/rejected outcome, directions of real gameplay-state
changes (excluding time), signs of source-computed reward components
and terminal/failure state. New source seeds and raw digest changes
alone cannot inflate learned novelty. An optional, rights-authorized
*actual local Q-policy candidate* receives one newly executed episode
per cycle. Its measured newly visited state-action combinations and
maximum observed Q-value change (default significance threshold 0.0001)
also reset the inactivity counter. This means a policy that is still
changing measurably **cannot be declared saturated** even if its
spectator-visible state signatures have repeated.

**Stop rule**: only after **10 consecutive independently audited
primary-plus-shadow cycles** with neither new semantic evidence nor
material Q-policy gains is
`saturation_within_tested_bounds=true` issued. This is at least
20 further executions after the last novel event, with their real
source receipts. The more restrictive bound of at most 64 cycles
per original simulation, max 12 game actions per episode, limited
simulation replay-work budget, and at most four independent thread
workers prevents runaway resource consumption. Exhausting a bound,
being cancelled, or exhausting source seeds yields an explicit
`*_unproven` status. **No finite test can prove that there is
literally nothing more to learn about a game.**

Each cycle records a SHA-256-linked receipt carrying the parent
checkpoint and fork identity, a complete accepted/rejected and reward
observation chain for *both* paths, both source-verifiable transition
digests, their multispectral audit hashes, reverse checkpoints,
new semantic evidence digests, candidate Q update counts, Q coverage
gain, measured Q-value delta, cumulative novelty, dry streak, peak
scrutiny level, actual gameplay steps and the replay-work estimate.
The receipts form a strict chained log, not a spreadsheet with
fabricated scores.

`skeleton/jeeves/game_studio_shadow_cli.py` runs the **whole ten-parent
mirror room** by default with a single user-admitted rights and
training command. Its append-only, exclusive, fsynced NDJSON ledger
captures each cycle before processing continues. Only after comparing
the persisted ledger to the real receipt chain does it publish a new
separate final private certificate. If interrupted or capped it
preserves incomplete forensic evidence and **does not** claim
completion or merge/promote any live neural weights.

Example:

```bash
python -m skeleton.jeeves.game_studio_shadow_cli \
  --engine economy --seed 13 --steps 3 \
  --max-cycles-per-sim 24 --max-replay-work-per-sim 10000 \
  --workers 2 --authorized --rights-cleared \
  --ledger /private/receipts/game-shadow.ndjson \
  --output /private/receipts/game-shadow-certificate.json
```

The default runs ten independent parent perspectives and their
shadow clones, extending each individually until its ten-dry-cycle
threshold or an explicitly reported resource limit. Use
`--spectator-only` to disable Q policy updates; otherwise it
actually performs local candidate Q training. The output includes
candidate policies and replay custody, never live production
neural-weight changes. Use `--angles explore` for a smaller,
explicitly scoped investigation. Evidence from one angle cannot
certify the other nine.

The authenticated Jeeves spectator panel has an explicit **Shadow
scrutiny** control for 12- or 16-cycle read-only investigation of
one selected perspective at a time. The API uses a tenant/owner
campaign scope, one global admission semaphore, an explicit replay
budget and no live training mutation. It reports the full chain's
cycle-by-cycle knowledge gains and visible fork/checkpoint evidence
along with precise inconclusive/within-bound saturation labels.
These short interactive investigations are **not substitutes** for
the full ten-parent operator-run marathon.

Security boundaries: original-only source rights, bounded
validator-approved engine commands, no user-provided executable
callbacks in authenticated API, exclusive candidate/ledger paths,
no external ROM or proprietary game cloning, source and transport
digests, no automatic policy promotion. Native rendering/thermal,
real GPU optics, all physically possible world outcomes and the
production Jeeves transformer remain separate unsatisfied release
requirements. Regression tests exist but exact-head execution,
perf soak and E2E still require verification.

### Reverify receipts against the actual source after completion

The saved certificate is not accepted just because its JSON hashes
match. A second independent, operator-invoked verification can re-run
every recorded primary and shadow path against the same canonical
source, reconstruct each saved intermediate fork and alternate action,
confirm original-game transition digests, and match every persistent
ledger entry to the recovered receipt set and its precise write order.

```bash
python -m skeleton.jeeves.game_studio_shadow_cli \
  --engine economy --output /private/receipts/game-shadow-certificate.json \
  --ledger /private/receipts/game-shadow.ndjson \
  --verify-only
```

This mode **reads** existing saved files, does not issue new candidate
training or change original worlds, and refuses certificates if the
source, receipt history, source action replay, checkpoint fork or
serialized append-only log differs. The default training command now
runs this same independent source reconstruction before issuing its
own final certificate. The live spectator endpoint does not perform
these exhaustive post-hoc full-room reverifications on each request
because it is intentionally restricted to short read-only previews.

## High-order multi-item/ability/weapon/tool/movement/sensory factor training

The new `skeleton/jeeves/game_studio_multifactor.py` defines 25
independent *declared factor categories*: items, abilities, weapons,
tools, style, movement, expression, reaction, consequence, actions,
environment, ambience, music, apparel, status effects, NPC behavior,
quests, physics, economy, camera, time, accessibility, localization,
network, and save/load plus the runtime's remaining typed controls.
A requested factor is only executable when the original game editor
exposes an actual validated setting or the game engine registers an
action with matching semantics. The catalogue reports **unimplemented
for this engine** otherwise. It cannot fake playable music, facial
expressions, atmosphere, weapons, acoustic spectrograms, photometric
measurements or native avatar movement by inventing a string label.

**Multi-combinations instead of single-control tests.** A finite,
source-valid three-way interaction planner composes existing original
engine settings and approved actions. It considers up to 512 typed
candidate worlds, greedily choosing bounded variants that cover new
one-, two- and three-way factor-interaction witnesses. Each design
bank handles at most eight simultaneous axes; **axis offset** allows
the next bank of actual controls to be studied without silently
ignoring remaining categories. Each action plan executes a sequence
of multiple real registered commands; every setting combination is
revalidated by the original editor including all cross-constraints.
The plan records source and design hashes, source-control axes, and
fraction of *offered interaction opportunities* covered—not a claim
that all possible game states were explored.

**Meticulous source measurements.** A bounded experiment compares
a multi-factor world with the unchanged original world at the *same
seed*, using an identical action schedule where possible and
independent source-replay multispectral audits. It then explicitly
removes each of up to four active factors and executes each
counterfactual world again, with source custody, accepted controls,
reward and productive-state evidence. A selected two-factor
difference-of-differences estimates the **measured interaction
contrast**. This is evidence of an observed conditional difference,
not proof of global causal generalization or real-world performance.

**Actual parameter/weight gain.** With explicit rights admission,
each source-combination has its *own* GamePolicyLearner and three
actual local Q-learning episodes; no training policy from one
environment is blindly copied to another. Each candidate records:
exact pre/post policy snapshot digests, actual update count,
newly visited state-action parameters, changed Q parameters,
signed per-parameter Q delta, maximum/summed absolute Q-weight
changes, trace digests, and two separately held-out evaluation seeds
and results. All candidate weights remain local and
**no neural production weights are changed automatically**.
Unsupported sensory/cinematic functionality cannot claim parameter
gain for a modality it did not execute.

**Replay-verifiable neural candidate input.** The new
`skeleton/ai/training/jeeves_studio_multifactor_corpus.py` derives
a training-only multi-source text corpus from the actual *training
episode actions* of each original engine variant—not from heldout
evaluation episodes or from arbitrary claimed success. Every
original source, setting interaction, action, transition label and
source-verified reward is independently replayed on publication
and loading. `load_studio_curriculum` now recognizes this
schema with an operator-pinned SHA-256, so the existing
`jeeves_production_game_train` checkpoint-derived
candidate optimizer can ingest it, with the same independent
holdout and no auto-promotion restrictions. **No actual production
checkpoint optimizer run is claimed by these code changes.**

Operator entry points:

```bash
# Design only. Inspect which categories really execute in this engine.
python -m skeleton.jeeves.game_studio_multifactor_cli \
  --editor economy --plan-only --interaction-order 3 \
  --axis-offset 0 --scenarios 8 \
  --output /private/factors/plan.json

# Execute actual factor ablations and source-bound local Q training,
# then prepare a separately pinned, training-only neural candidate corpus.
python -m skeleton.jeeves.game_studio_multifactor_cli \
  --editor economy --interaction-order 3 \
  --axis-offset 0 --scenarios 8 --steps 4 --seed 11 \
  --train-local-q --authorized --rights-cleared \
  --output /private/factors/weight-candidates.json \
  --neural-corpus-output /private/factors/replayed-neural-input.json
```

To run actual neural optimizer steps against an *independently
verified live production checkpoint*, admit the pinned corpus
through the already existing
`jeeves_production_game_session` / `jeeves_production_game_train`
`--studio-corpus` and `--studio-corpus-expected-sha256`
arguments, plus that trainer's source/holdout/optimizer controls.
The checkpoint remains untouched until the operator separately
accepts a verified candidate. A generated text corpus by itself
has zero transformer weight updates.

The authenticated `/game-studio-learning` frontend now displays
all declared categories with explicit missing capabilities,
control-bank navigation, bounded three-way source designs and
on-demand read-only dual-scenario experiments with per-factor
ablations and interaction contrasts. Owner-scoped backend routes
deny foreign/non-studio inputs and restrict each UI measurement
call to at most three legal variants and four gameplay steps.
Model-training weight updates require the separate rights-gated
CLI; viewing a scenario never changes campaign policies.

**Unverified release gates:** Exact-head regression tests and
TypeScript build, actual production transformer optimizer runs,
native multimedia rendering, full weapon/ability/tool
simulation fidelity, user-perceived emotion/music quality,
per-modality benchmark improvements, load/soak/E2E, and
all-engine production completeness remain pending.

### Parameter-gain effectiveness receipts

Every local-Q candidate now records an explicit
`measured_learning_efficiency` section: exact optimizer update count,
actual source-accepted commands, productive non-clock state transitions,
newly explored state-action parameters per 100 updates, changed Q
parameters per 100 updates, absolute Q-weight movement per update,
independent holdout mean-return delta and negative transfer detection.
This is machine-readable source evidence and must not be confused
with production transformer training or universal game design
generalization. Every action selected as an item, ability, tool or
weapon factor is scheduled early enough to actually be exercised
within the requested bounded episode depth; seed jitter cannot
silently omit it from the tested source path.

The experiment receipts also explicitly distinguish action factors
*scheduled for the test* from actions genuinely **attempted and
accepted** by the original runtime. A multi-weapon, tool, item,
ability or music action that is unavailable or rejected at that
actual world state is flagged as unexecuted; it must not be treated
as effective factor-training evidence merely because its command
name appears in a planned schedule.

## Exact factorial source scrutiny, temporal noncommutativity and Q-weight distribution

A dedicated `skeleton/jeeves/game_studio_factorial_scrutiny.py`
analyzer complements the original multi-factor scenario planner.
For a selected two-factor case it executes the *complete four-corner*
on/off intervention lattice per seed; three factors execute the
*complete eight-corner* lattice per seed. Each experiment uses
actual registered game settings and actions, validated against
the original editor's source rules, with ten independent
multispectral checks per corner, explicit accepted/rejected
action slots, per-step state/reward/transition receipts and
source-controlled game snapshots.

Default viewer scrutiny compares two independent matched game seeds;
the rights-admitted CLI supports **three**. Per seed, every main effect,
pair interaction and (if selected) triple interaction uses the
exact signed inclusion/exclusion/Möbius contrast of the corresponding
source-executed cells. Results expose per-seed effect size, mean,
minimum, maximum, population spread, sign reversal and the worst
observed joint-world regression. Small samples **never** claim
statistical significance or transferable causal identification.
Illegal intermediate source worlds remain explicit constraint
failures, not discarded silently or replaced with cherry-picked
favorable seeds.

After the factorial cube, the original baseline and full joint
worlds are re-executed **in reverse world execution order**. All
transition, telemetry and source receipts must match their original
world run to establish execution-order independence of the reference
game; this is different from changing the in-game action order.

A *second, distinct* stress layer reverses the **actual sequence of
registered gameplay commands** within a completed joint world.
The changed action order is independently replayed with its own
ten-check audit and complete per-step evidence. Only real differences
in gameplay-state trajectories, accepted/rejected controls and
recorded reward—not the inevitable difference between action-log
hashes—are labeled order-dependent mechanics. Original-sequence
success does not imply success under another sequence. The
`robust_joint_gain_under_tested_orders` gate requires nonregression
on the tested action orderings in addition to measured positive
joint returns, actual accepted interventions and complete seed
coverage.

Instability, illegal intermediate worlds, missing interventions,
negative matched-seed returns or action-order regression create
specific source-derived reasons in a bounded adversarial
re-examination queue. The queue gives proposed *new, disjoint*
source-game seeds, but performs **zero** hidden background runs.
Further sampling requires fresh authorized execution; reaching a
budget ceiling remains explicitly incomplete.

Each genuine local `GamePolicyLearner` candidate now records an
expanded per-parameter evidence distribution: newly visited
state-action values, signed and absolute Q-value movement, positive
versus negative changes, numbers of source-state bins before/after,
quantiles of absolute Q changes (median/p90/p99), change counts and
weight movement by registered action index, highest-magnitude
parameter update samples and truncation status, plus an unambiguous
digest over the *full* source-bound Q snapshot. Evaluating a
neural candidate still requires the separate, existing
checkpoint-derived optimizer; these tabular Q deltas are **not**
transformer weight tensors.

The deterministic factorial replay verifier can reconstruct
every saved source variation, intervention, per-seed action transcript
and multi-angle receipt to reject tampering. Authenticated user
views now show exact lattice coverage, source-replayed check counts,
seed variability, action ordering sensitivity and reasons for
additional scrutiny. Tests were authored for complete 4/8-cell
lattices, tampered receipts, source-rights protection, invalid
source combinations, quantitative Q deltas, reverse order
re-execution and descriptive risk flags. Their exact-head
execution and production behavior have **not yet been verified**.
