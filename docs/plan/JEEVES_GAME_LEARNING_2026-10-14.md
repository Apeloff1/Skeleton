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

## Playable emulator and parallel-learning continuation

The continuation began at 03:32:31 UTC with six concurrent implementation lanes.
It adds real libretro execution through an approved native-core registry, rather
than treating native source emitters as emulators. The catalogue now contains
375 profiles, including an explicit emulator entry for all 169 canonical Dragon
hardware targets. Unmapped cores, unavailable SDKs, required firmware and unsupported
hardware render callbacks remain visible as unavailable dependencies.

Six pinned upstream cores were compiled and privately installed with their
licenses, source revisions and exact binary hashes: Gambatte, FCEUmm, Genesis
Plus GX, Snes9x, mGBA and PCSX-ReARMed. Their approvals cover 15 hardware targets.
Sega CD firmware was not installed or approved. The PS1 installation explicitly
selects its core's HLE BIOS mode, which is not complete commercial-game compatibility.
No commercial ROMs, firmware, platform keys or vendor SDKs were downloaded.

The native worker requires bubblewrap isolation, a private bounded temp filesystem,
stripped environment, readonly approved content/core/firmware, and CPU, address-space,
file and process limits. The fixed system Python interpreter is hash-checked in both
processes; the actual worker version binds the environment identity. Host and worker
use length-bounded JSON plus independently hashed binary blocks. Native crashes,
timeouts, missing sandbox capabilities and state-capacity excess retire or refuse
the operation. Native state plus its JSON snapshot is capped at the application's
actual 8 MiB persistence boundary. Large readonly content is pinned through verified
hardlinks; writable or cross-device copying has a separate 64 MiB aggregate limit.

Studio play now runs continuously in an isolated process with keyboard, touch,
gamepad and bounded console input. A single controller lease, epoch, ordered input
sequence and revision fence prevent competing writers. Viewers see measured frames;
the optional browser sound control plays actual captured PCM with sample identity
and gap reporting. Pause, reset, stop, takeover and interrupted-session recovery
are explicit. Account changes, source withdrawal and project edits fence stale
control, streams and publication.

Consented demonstrations retain actual input, observations, rewards and exact
environment/source lineage. Replay must reproduce the recorded transitions before
the learner consumes them. Imitation counts and Q updates are separate from authored
feedback; feedback never invents game rewards. Arbitrary controller inputs can be
recorded as controller evidence but only exact registered policy actions supply a
finite-action imitation prior. Authentication proves the recorded account issuer,
not that the controller was operated by a biological human. No authenticated human
play data was available or invented in this session.

Parallel training uses one to eight real processes. Each batch pins a frozen policy
and deterministic episode assignments; the parent validates measured actor receipts
and applies updates in a central episode-atomic commit. Pending batches and their
acknowledged prefixes support exact resume. Operational materialization paths do not
change semantic source identity. Actor credits and interactive slots are separate;
uncertain worker termination retains capacity rather than advertising a freed slot.
The instance viewer displays real sampled frames and measured progress.

The source/asset/map/controller editor uses exact revision files and native build
plans. Build requests execute fixed compiler arguments in isolated workers, validate
the actual command exits and artifact structure/hash, and expose authenticated
downloads. Supported RGBDS, cc65, DASM, SDCC/devkitSMS and desktop compiler adapters
still require their installed dependencies. Licensed or unimplemented targets remain
source-only. The user cannot submit a shell command, Makefile or arbitrary host path
to the compiler. Original game generation also fixes duplicate platform-floor corner
tiles discovered during the actual original-game learning workload.

Cartridge/disc/PC media has a streamed upload path: 1 MiB immutable indexed chunks,
2 GiB per file, 4 GiB per bundle, 8 GiB per-owner reservations and 32 upload slots.
Completion streams exact file hashes and validates linked CUE/M3U/GDI/ISO/CHD media;
only then does it associate an admitted source with the current project. The private
shared media cache verifies exact files and is bounded to 8 GiB. Partial uploads
expire, withdrawal blocks current use, and cleanup removes original chunks and
derived private caches. Historical policies, exports and already pinned execution
copies are not claimed globally erased. Browser and native clients read bounded
local file slices and expose received-byte progress and resume.

## Operator setup and measured learning work

The reproducible bootstrap uses fixed upstream revisions and operator-installed
compilers. It never downloads game content or firmware and never installs through
an authenticated web request:

```sh
python scripts/install_game_emulator_cores.py --source-root /absolute/private/core-sources --install-root /absolute/private/cores --fetch-sources
export SKL_GAME_EMULATOR_REGISTRY=/absolute/private/cores/cores.json
python -m skeleton.jeeves.game_learning_cli train --target emulator:game_boy --rom /absolute/original.gb --workers 2 --episodes 4 --episode-steps 64 --policy-file .local/native-policy.json
python -m skeleton.jeeves.game_learning_cli train --target eight_bit_tile_1983 --workers 4 --episodes 8 --episode-steps 64 --policy-file .local/reference-policy.json
```

The mGBA recipe additionally requires an installed CMake binary; `--cmake-binary`
selects it explicitly. The headless cartridge JSON path remains limited to 2 MiB;
larger and multi-file media use the studio's file-backed upload path. Exact parallel
resume retains worker count and the frozen pending-batch checkpoint. Local policy
files are private operator artifacts, not application consent or promotion receipts.

Actual requested learning was performed after the learner source froze, without
running an automated test framework:

| Workload | Completed episodes | Actual Q updates | Actors |
| --- | ---: | ---: | ---: |
| 24 original projects across the Forge genres, using their discrete generated-game simulator | 192 | 8,238 | 4 |
| All 11 existing coded reference engines | 88 | 5,431 | 4 |
| Original Signal Garden cartridge through the experimental DMG runtime | 8 | 768 | 4 |
| Same original cartridge through the actual approved Gambatte native core and sandbox | 4 | 256 | 2 |
| Total | 292 | 14,693 | |

The source/build evidence and exact policy identities are recorded in
`machine/ai_game_learning_session_evidence_2026-10-14.json`. Policies and measured
episode traces are retained in private workspace artifacts. The native result
establishes actual execution and learning on this original cartridge; it does not
certify the other five cores, arbitrary games, hardware timing, game mastery or
all-console compatibility. Q updates are learning work, not a held-out improvement
claim. No evaluations, automated tests, deployment, merge, production model
promotion or masterplan completion was performed. Python compilation/Ruff,
scoped TypeScript/ESLint and the production web export passed.
