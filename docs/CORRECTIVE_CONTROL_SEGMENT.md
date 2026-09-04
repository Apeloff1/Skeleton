# Corrective Control Segment

This segment is the quality-and-repair control plane that now spans the active generation surfaces in Skeleton. It did not replace the forge, plan, or pipeline layers; it sits around them and makes them self-checking, historically visible, and selectively self-correcting.

## What this segment is

The segment joins five capabilities into one operating lane:

1. **Verification** — each surface can score its own output against a bounded contract.
2. **Persistence** — quality results and repair attempts are written into the organism ledger area.
3. **Targeting** — the system can identify the latest failure, recurring failures, and the most common repair targets.
4. **Bounded repair** — selected surfaces can attempt one conservative repair pass, then re-verify.
5. **Operator visibility** — runtime cards expose quality, failures, repairs, and recent activity.

## Surfaces covered now

| Surface | Verify | Persist quality | Persist repair | Optional repair |
|---|---|---|---|---|
| Forge / Godot materialisation | Yes | Yes | Yes | Yes |
| Plan / command deck | Yes | Yes | Yes | Yes |
| Game logic pipeline | Yes | Yes | No | No |
| NPC pipeline | Yes | Yes | Yes | Yes |
| Dialogue tree path | Yes | Yes | Yes | Yes |

## Core modules

### Shared quality contract

- `skeleton/intelligence/quality.py`
- shared `QualityIssue`, `QualitySignal`, `QualityReport`

### Surface verifiers

- `skeleton/intelligence/forge_verifier.py`
- `skeleton/intelligence/plan_verifier.py`
- `skeleton/intelligence/pipeline_verifier.py`
- `skeleton/intelligence/npc_verifier.py`
- `skeleton/intelligence/dialogue_verifier.py`

### Surface repair scaffolds

- `skeleton/forge/repair.py`
- `skeleton/intelligence/plan_repair.py`
- `skeleton/intelligence/pipeline_repair.py`

### Organism persistence and operator surfaces

- `skeleton/organism/quality_state.py`
- `skeleton/organism/repair_card.py`
- `skeleton/organism/product.py`
- `skeleton/organism/nervous.py`
- `skeleton/organism/doctor.py`
- `skeleton/organism/satellites.py`

## Persistence model

The segment writes into `acquired/organism/quality.jsonl` through `quality_state.py`.

Two kinds of records are persisted:

- **quality** records — first-pass output assessment
- **repair** records — bounded repair attempts and their after-state

This separation matters because the history stays honest:

- a failure remains a failure even if a later repair succeeds
- repair success rate can be measured independently
- operator cards can show both the latest failure and the latest repair

## Repair targeting model

The system now supports multiple repair selectors:

- latest failure
- latest repair
- repair candidate list per surface
- recurring repair target rollups
- recurring failure issue rollups

Forge failures persist structured evidence, including:

- project issues
- blocking issues
- top file reports
- issue names
- top failing paths

That evidence lets the forge repair path prefer hard-failure files before weaker score-only targets.

## Repair card

`repair_card.py` is the shared operator-facing control surface.

It carries:

- quality rollup
- failure rollup
- repair rollup
- recent activity
- latest failure
- latest repair
- top recurring repair target
- top recurring failure issue
- top failing surface

This card is now reused across the active operator surfaces instead of rebuilding the same view repeatedly.

## Current forge repair rules

The forge repair pass is still intentionally bounded. It currently knows how to:

- add missing `extends Node`
- add a stub `func`
- comment out `eval(`
- restore `run/main_scene`
- restore `EventBus` autoload in `project.godot`
- stub `scripts/autoloads/event_bus.gd`
- stub `scenes/levels/run_level.tscn`
- restore player packed-scene reference in `run_level.tscn`
- stub `scenes/door.tscn`
- restore door packed-scene reference in `run_level.tscn`

This is not a general autonomous rewrite system. It is a one-pass rule-based repair layer designed to stay predictable.

## Current plan repair rules

The plan repair pass can currently fill missing:

- `era`
- `primary_dps`
- `room_bias`

It then re-verifies and persists the repair separately.

## Current pipeline repair rules

### NPC repair

The NPC repair scaffold can fill or seed:

- missing name
- missing archetype
- missing traits
- minimal dialogue tree
- minimal behaviour graph

### Dialogue repair

The dialogue repair scaffold can fill or seed:

- missing entry
- minimal node set
- minimal outgoing edge for an otherwise dead entry

## Operator surfaces using this segment

The following operator-facing cards now consume the segment directly:

- `product`
- `nervous`
- `doctor`
- `satellites`

The intent is that the organism can now report not just whether it is healthy, but whether its generation surfaces are:

- failing repeatedly
- repairing successfully
- targeting the same files over and over
- clustering around the same issue families

## Tests covering this segment

The control segment is backed by dedicated tests, including:

- `skeleton/testing/test_forge_verifier.py`
- `skeleton/testing/test_forge_repair.py`
- `skeleton/testing/test_plan_verifier.py`
- `skeleton/testing/test_plan_repair.py`
- `skeleton/testing/test_pipeline_verifier.py`
- `skeleton/testing/test_pipeline_repair.py`
- `skeleton/testing/test_game_logic_quality.py`
- `skeleton/testing/test_pipeline_npc_quality.py`
- `skeleton/testing/test_dialogue_quality.py`
- `skeleton/testing/test_operator_quality.py`
- `skeleton/testing/test_quality_state.py`

## Where this segment stops today

What is real now:

- shared quality contract
- shared repair history
- operator repair card
- evidence-aware forge repair targeting
- bounded repair on forge, plan, NPC, and dialogue
- recent activity and recurrence rollups

What is not yet real:

- multi-pass repair loops
- learned repair policies
- game-logic repair path
- explicit operator commands for querying only failures or only repairs
- a fully durable command surface for steering repair policy thresholds

## Recommended next steps

1. Add a **game-logic repair path** so the active generation surfaces reach parity.
2. Add **surface-specific operator commands** for recent failures, recent repairs, and recurring targets.
3. Add **repair telemetry summaries** to top-level status docs and product copy.
4. Consider one **bounded second-pass repair mode** only after the one-pass path proves stable.

## Segment status

Status: **active and integrated**.

This is now one of the real app segments, not a side experiment. It has:

- runtime surfaces
- persistent state
- coverage tests
- bounded execution paths
- documentation

Its role in the app is to keep generation surfaces measurable, repairable, and visible to operators.
