# Jeeves game learning and console workspaces

This implementation composes current main's coded Dragon and Jeeves owners into
an authenticated `/game-learning` studio and a headless local operator. The
one-hour source session runs 2026-10-14 02:30:16–03:30:16 UTC. No automated tests
were added or run. It is an implementation candidate, not studio qualification,
complete hardware compatibility, enterprise promotion or general game mastery.

## Actual capability boundaries

| Input or target | Implemented behavior |
| --- | --- |
| Existing 11 Jeeves engine eras | Execute the coded legacy, transitional 3D and modern reference engines, with explicit actions, measured observations/rewards, actual raster/draw output and replayable checkpoints. Named console associations describe reference profiles. |
| Current Dragon native targets | Reuse the canonical target/style/emitter catalog and original source builders. Their native source, SDK, toolchain and licensing requirements remain visible. Emitted C/SDK source is not silently treated as a running hardware emulator. |
| Thumby gameplay | Reuse the existing trusted native Python game logic through a bounded adapter. Local observations include actual gameplay state. Host raster preview does not establish device display compatibility. |
| Game Boy cartridges | Execute an experimental DMG CPU, memory-mapped bus, timer, joypad and basic background/window/sprite raster. ROM-only and MBC1 profiles are bounded to 2 MiB. CGB-only cartridges, other mappers, audio/RTC and cycle-perfect bus behavior remain unavailable. |
| Original generated games | Seeded maps, mechanics, assets and editable portable projects cover the existing Forge genres. Their discrete local simulator trains on the generated map/rules. It is an explicit approximation of continuous browser rendering. |
| ROM/project/archive digestion | Parse actual NES, GB/GBC, SNES, Genesis/SMD, GBA and N64 structures; inspect bounded ZIP/project/text/asset/trace sources. Metadata ingestion does not grant execution support or recover a complete game's design automatically. |
| Dragon gathered knowledge | Read exact owner-scoped, consented and independently reviewed existing Dragon source revisions and evidence, and check withdrawal before reuse. This workflow does not start another scraper or invent unavailable records. |

## Studio workflow

Open `/game-learning` from the Jeeves product action. Select a registered target,
create a server-owned project, ingest a source or current Dragon revision, and
edit its source files with revision checks. Reset a simulation, apply one or more
of its actual registered actions, and inspect measured observations and frames.

Start bounded local Q-learning from the project/source or reuse its exact parent
policy. Jobs expose committed episodes, policy identity, checkpoints and terminal
state. Stop requests remain requests until the worker acknowledges quiescence.
An interrupted job resumes from its last complete episode. A new job forks learned
values from an explicitly bound parent; changed environment or code identity
rejects incompatible reuse. Candidate/baseline evaluation executes paired held-out
seeds without exploration. A fixed-ROM seed changes bounded real idle execution
phase; it does not create a new unseen game.

Generation consumes classified source cues and measured policy lineage, producing
an original candidate project. Review and explicitly adopt its editable files or
export its authorized exact version. Native outputs use the actual Dragon source
emitters and their supported styles. A compatible Game Boy maze adaptation also
includes actual original 32 KiB cartridge bytes and assembly. No imported ROM
assets or game code are copied into the generated game.

The application requires the existing authenticated backend, CORE_DB Mongo store,
canonical engine storage admission and configured Dragon Academy store for Dragon
records. Policy learning itself uses no hosted model or provider SDK. Missing
stores, engine admission, source rights or SDKs produce explicit unavailable states.

## Headless local work

The operator uses the same runtime, policy and generation modules. After a normal
repository installation, `skeleton-game-learning` is also available. Examples:

```sh
python -m skeleton.jeeves.game_learning_cli catalog
python -m skeleton.jeeves.game_learning_cli train --target nes --episodes 16 --episode-steps 128 --policy-id nes-reference-v1 --policy-file .local/policy.json
python -m skeleton.jeeves.game_learning_cli train --target nes --episodes 8 --episode-steps 128 --policy-id nes-reference-v1 --policy-file .local/policy.json --resume
python -m skeleton.jeeves.game_learning_cli train --target nes --episodes 8 --episode-steps 128 --policy-id nes-reference-v2 --policy-file .local/policy-v2.json --fork-parent .local/policy.json
python -m skeleton.jeeves.game_learning_cli build-dmg --seed 42 --title 'Signal Garden' --output .local/signal-garden.gb
python -m skeleton.jeeves.game_learning_cli train --target game_boy --rom .local/signal-garden.gb --episodes 8 --episode-steps 128 --policy-id dmg-exploration-v1 --policy-file .local/dmg-policy.json
python -m skeleton.jeeves.game_learning_cli evaluate --target nes --episode-steps 128 --policy-file .local/policy.json --heldout-seed 1000001 --heldout-seed 1000002 --evidence-file .local/evaluation.json
```

`nes` in the training example is the registered eight-bit reference simulation,
not a NES cartridge interpreter. Game Boy visual-change reward measures
exploration, not an inferred win or understanding of arbitrary games. Policy
files are private operator checkpoints, not application rights or promotion
receipts. Keep exact source, target, step budget and configuration for resume.
The commands above document the interface; training/evaluation were not executed
in this no-tests implementation session.

## Construction levels and remaining acceptance

| Level | Source disposition |
| --- | --- |
| L00 intent/ownership | Existing Jeeves game-engine, Dragon acquisition, backend and frontend owners; `machine/ai_game_learning.json`. |
| L01 dependencies | Actual canonical Dragon catalog, source emitter and custody APIs; no new runtime service. |
| L02 contracts | Typed bounded sources, projects, transitions, policy snapshots and exact-version APIs. |
| L03 authority | Verified tenant/owner, revision/idempotency fences, explicit source rights and existing storage admission. |
| L04 control flow | Actual reset/step, episode-atomic training, paired evaluation, candidate generation and explicit adoption. |
| L05 state | Existing Mongo project/source/session/job/policy records; immutable input bindings and checkpoint cursor. |
| L06 security/privacy | Bounded extraction, no uploaded-code execution, current source scope, safe export and account fences. |
| L07 recovery | Leased workers, cooperative cancellation/deadline, acknowledged checkpoint replay and exact-parent policy fork. |
| L08 observability | Real episodes, rewards, updates, state/action traces, source/policy/code identity and job errors. |
| L09 economics | Bounded worker capacity, source/file/state/update/episode budgets and actual storage admission. |
| L10 verification | Source checks/builds only in this session; hardware, interruption, isolation and fault acceptance remain unverified. |
| L11 deployment/rollback | Additive route/modules; disable entrypoints while retaining canonical state and existing engine owners. |
| L12 operators | Studio controls and private headless checkpoint/build operator; no deployment performed. |
| L13 qualification | No enterprise grade, masterplan checkbox, production route or model promotion changed. |

Source compilation, lint, scoped TypeScript and the web build are distinct from
live gameplay/ROM correctness and production acceptance. Full commercial-ROM
compatibility, installed licensed SDKs, production learning promotion, all-game
simulation, genre fidelity and studio quality require further execution evidence.

## Integration basis

The integration branch starts from current-main commit `c85512043` in an isolated checkout. Existing Dragon implementations remain canonical. The earlier AI-chat draft #3782 and its subsequent user-authored updates are left intact; this change does not overwrite its branch or blindly replace current-main source.

## Build artifacts from this session

The operator enumerated 206 registered profiles from the actual current-main registry. The production web export includes `/game-learning`. The original cartridge build produced 32,768 bytes with SHA-256 `2990f2ad87de761e634a37b67b9213205150e821f10eafc9db86c6f29f5acd39`. This is generated binary/structural evidence, not a gameplay or hardware compatibility result. No simulation, policy training, evaluation or automated tests were executed during this source session.
