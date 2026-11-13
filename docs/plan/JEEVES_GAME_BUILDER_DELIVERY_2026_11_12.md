# Jeeves local model and playable game delivery

Status: implementation and acceptance plan. This document records architecture,
run instructions, and required evidence; it does not certify model quality,
engine compatibility, production release, or competitive superiority.

The user priority is Jeeves, then Dragon, then Skeleton. This increment connects
Jeeves's useful local design work to a game the user can launch, control, finish,
and restart. Richer text must change the committed game in observable ways.
More proposal fields or generated files alone do not establish that outcome.

## L00 — Ownership and product outcome

The existing `skeleton/forge/game_builder.py:build_playable_game` owns the
brief-to-Godot build. `game_design_spec.py` commits the design identity,
`game_content.py` materializes bounded content, `genre_project.py` attaches the
runtime, and `playtest.py` executes the engine gate. Preserve this route for the
CLI and the charter-protected engine API rather than creating another builder.

`skeleton/forge/ai_builder` owns guarded model proposals. A local adapter may
consume the declared inference owner, but may not become another inference
runtime, credential owner, or shell executor. `skeleton/provider_runtime.py`
remains the credential-bearing model boundary. `skeleton/ai/game_builder` is a
separate declared native owner for existing dual-rival/research/qualification
systems, not a replacement home for the staged Forge implementation.

The acceptance outcome is an original, bounded game with comprehensible
controls, readable feedback, a meaningful goal, loss/recovery, and a completed
loop. Model assistance is optional and explicitly identified. A deterministic
build remains useful when no trained model has been configured.

## L01 — Architecture and dependencies

Keep the existing chain:

```text
user brief -> deterministic design -> optional bounded model proposal
           -> schema/authority guard -> committed design/content
           -> canonical emitter -> static checks -> real Godot acceptance
           -> reviewed local artifact
```

All work consumes one build deadline. Reserve time for materialization and
verification rather than permitting the model to consume the entire budget.
Unknown readiness is unavailable, and a model denial cannot authorize another
provider or enlarge the budget.

The staged mapping is `AIFT-FORGE`: `skeleton/forge` to `skeleton/ai/forge`.
Changed Python implementations must remain semantically equivalent; non-Python
content must retain byte parity. Native overlays and the nested creator and
pipeline mappings retain their existing owners.

## L02 — Typed proposal and result contracts

Extend the existing versioned `ai_builder/plan_schema.py` contract. Accept only
finite, typed design values that the compiler and runtime actually implement.
No arbitrary engine class, filename, path, command, source code, shader, URL,
resource load, or tool invocation can arrive through a design value.

Preserve the locked brief, genre, engine, scope and schema identity. Bind the
accepted proposal, model identity, configuration and resulting design digest.
An absent, invalid, stale, oversized, duplicate-key, non-finite or unsupported
proposal must produce an intelligible decision without pretending model work
succeeded. Compatibility with prior deterministic specs and existing planner
hooks must be tested.

Both `ai_builder/plan_guard.py` and `game_builder.py:_apply_planner` currently
filter model data. Both boundaries and the actual content/emitter consumers
must agree on any new field. Otherwise the feature merely accepts and discards
model output. Keep the `skeleton.game_builder_run.v1` result and its existing
8 MiB inline-file budget compatible, or explicitly version and migrate it.

## L03 — Admission and authority

Use the operator-selected local model and the existing bounded inference
controls. Reuse workspace execution custody when a local model invocation
shares the Jeeves workspace. Do not infer readiness from a model path or GGUF
header alone. Do not automatically download weights, switch models, send a
hosted request, or grant the model filesystem/network access.

Keep the existing Forge charter and authenticated tenant/actor bindings for
engine API calls. Output publication is a separate, explicit local operation.
Generated projects do not acquire source rights, release approval, trained-model
status, or distribution permissions from a favorable planner or QA verdict.

## L04 — Control flow and working gameplay

Compile the brief first; obtain at most the configured bounded proposal;
validate it; generate content; attach the actual playable runtime; verify and
repair under the original deadline. Return a stable failure or clearly labeled
deterministic result when model assistance cannot be used.

The output must support the declared genres rather than returning the same
scene with a renamed title. Movement, attack/jump/interact, enemies or hazards,
progression, objective completion, defeat and restart must execute in the
native engine. Controls and current state must be visible to the player.
Visual polish should improve navigation, threats, actions and feedback while
preserving readability, rather than hiding incomplete gameplay.

## L05 — State, identity and artifacts

The design/content digests identify exactly what was built. Preserve the
project, execution, actor and tenant identities already carried by the result.
The emitted file map is an artifact candidate; a log marker is a separate
observation. Never treat either as a replacement for canonical build state.

User-selected output directories retain the projector's existing no-clobber and
path checks. A failed build must preserve existing user files. If gameplay saves
are added, declare their owner, format/version, bounds, corruption behavior,
restore semantics and migration before claiming persistent progression.

## L06 — Security, privacy and rights

Treat briefs, local references and model output as untrusted data. Avoid
unescaped interpolation into GDScript or scene syntax. Use deterministic
serialization and closed numeric/color/enumeration values. Deny traversal,
external resource references, unexpected files and oversized input/output.

Do not place access tokens, host paths, prompts or provider credentials in
ordinary logs or exported qualification receipts. Imported Dragon evidence
keeps its explicit review, source digest and rights boundaries. Preserve
original-source authorship and do not generate claims of permission or
commercial provenance from similarity scores.

## L07 — Failure, cancellation and recovery

Test unavailable models, malformed/late responses, exhausted context/output
budgets, concurrent workspace use, deadline expiration, absent Godot, import
failure, runtime script errors and output collisions. A timeout stops admission
of later work and cannot publish a success result.

Existing `_call_bounded` stops waiting for a daemon thread; it does not prove
that a native model child stopped. The model adapter must honor real process
cancellation/ownership and preserve physical custody until execution settles.
Do not confuse waiting less time with reclaiming the underlying resource.

## L08 — Observability and review evidence

Expose whether the compiler or model supplied the accepted design, why a
proposal was refused, the sealed design identity, verification mode, engine
identity/source, time budgets and observed outcomes. Distinguish static checks,
Python oracle results, engine import, actual gameplay actions and framebuffer
observations. A process exit code alone does not prove a playable game.

Receipts should contain nonsecret identities, digests, counts, bounded timing
and verdicts. Keep raw model text and user content out of routine diagnostics.
Do not write test passes or benchmark numbers into this plan before executing
the corresponding check on the reviewed revision.

## L09 — Performance, capacity and economics

Preserve the canonical builder's default 120-second total deadline, bounded
repair rounds, local concurrency, context/output budgets and inline artifact
limit. The opt-in local-model operator entrypoint has its own explicit finite
planning and end-to-end deadline arguments; its longer default does not enlarge
the engine API's ceiling. Any exception must remain explicit at its existing
admission boundary. Measure model
latency separately from materialization, import and gameplay verification.

Bound enemies, projectiles, particles, map size, loops, generated assets and
frame work. Test enough game time to reveal accumulation rather than inferring
stability from a short startup. Hardware/headless observations do not establish
mobile, GPU, Windows or sustained-frame-rate qualification.

## L10 — Verification and adversarial evaluation

Use existing focused suites as the compatibility baseline:

```bash
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  tests/forge_ai_builder \
  skeleton/testing/test_game_build_contracts.py \
  skeleton/testing/test_game_builder_golden.py \
  skeleton/testing/test_game_studio_swarm.py
```

Add meaningful cases for strict typed proposals, guard agreement, local model
refusal/cancellation, generation limits and actual runtime actions. Use a
synthetic model only to test plumbing; it does not establish trained-model
language or design quality. Evaluate useful model quality with an identified
operator model, fixed prompts, fixed budgets and independent human judgments.

Canonical golden tests default to playtest **off**. For real engine acceptance:

```bash
SKELETON_GODOT_BIN=/absolute/path/to/godot \
SKELETON_GAME_BUILDER_REQUIRE_GODOT=1 \
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_game_builder_golden.py \
  tests/test_forge_interactive_runtime.py
```

The interactive suite requires an engine when the explicit requirement flag is
set; an absent binary must fail rather than produce a qualifying skipped run.

Verify input/action-driven goal and defeat/restart observations separately from
`CORE_LOOP_OK`, whose original implementation is a content-oracle calculation.
Require a real Godot process for native assertions; a fake binary can test only
subprocess contracts. New native acceptance must bind exact checked-out source,
engine/archive digests and the emitted project identity.

## L11 — Deployment, migration and rollback

After source implementation and review, root freezes a canonical source commit.
Only then synchronize reviewed AIFT-FORGE mirror pairs and update its source
Git-tree pin from that frozen commit. The general mirror helper creates missing
files only and refuses changed existing mirrors. The historical integrated
source-pin repair script is not a Forge pin updater.

Run AI-tree parity/ownership and required construction checks on the final
combined change. Preserve compatibility sources, native overlays, historical
proposal schemas and deterministic generation. Rollback restores code and
routing/policy choices; it must not silently delete user projects or saves.

## L12 — Operator runbook

Inspect the current command before supplying optional model-specific arguments:

```bash
python -m skeleton game --help
```

The existing deterministic path can produce a local project and demand actual
engine execution:

```bash
SKELETON_GODOT_BIN=/absolute/path/to/godot python -m skeleton game \
  'A small top-down shooter. Fantasy: an original storm observatory. Core loop: clear threats, recover power, and reach the beacon. Scope: small prototype.' \
  --out ./build/storm-observatory --playtest require --json
```

Use a new output directory. Model configuration must be provisioned through the
existing local model preparation path; no example here supplies invented model
credentials or pretends that an untrained fixture is a useful assistant.

The opt-in local-model bridge uses an existing operator-provisioned deployment
manifest. It produces a project only after guarded planning and the requested
verification policy:

```bash
SKELETON_GODOT_BIN=/absolute/path/to/godot python scripts/build_jeeves_game.py \
  'A small top-down shooter. Fantasy: an original storm observatory. Scope: small prototype.' \
  --manifest /absolute/private/local-model.json \
  --out ./build/jeeves-observatory --require-model --playtest require \
  --report ./artifacts/jeeves-observatory.json
```

Supply `--workspace-database` with the existing Jeeves database when sharing its
execution lease namespace. `--require-model` prevents a deterministic fallback
from satisfying this particular command. Without it, inspect the planning
receipt to distinguish a compiler result from accepted model assistance. A
model proposal and source fixtures never establish trained-model quality.

Open `project.godot` with the qualified Godot version and use its displayed
controls. Confirm movement, combat or platforming, loss, restart and successful
completion. Preserve the project and nonsecret evidence for review. A failed
model, engine or permission check is a diagnostic to resolve, never an
instruction to remove a guard or reinitialize user data.

## L13 — Exit evidence and competitive limits

A reviewable prototype increment requires the combined source, mirror parity,
strict proposal regressions, deterministic compatibility, real native gameplay
observations and clear model/procedural attribution. Shipping and physical-device
acceptance remain separate. Do not remove an existing limitation merely because
the new code contains the corresponding feature name.

For a comparative claim, freeze equivalent briefs, model/hardware/budgets,
product versions and task rules. Compare completed player journeys, design
faithfulness, readability, control quality, crash/recovery behavior and measured
latency. Independent qualitative review is required for fun and visual quality.
An attractive screenshot, larger file count or model-generated self-score cannot
establish that the product beats competitors.
