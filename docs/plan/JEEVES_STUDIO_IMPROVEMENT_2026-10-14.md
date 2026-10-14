# Jeeves studio implementation and improvement loop

This additive implementation extends the existing Jeeves, Dragon, creator,
application workspace, and product owners. The requested implementation window
is 2026-10-14 04:39:16–06:39:16 UTC. The final user steering prioritizes the app,
its editors/builders/simulations, and remembered improvement over more example
content. Automated tests were neither added nor run. This is source and measured
candidate evidence; existing enterprise/masterplan closure flags stay unchanged.

## What was built

| Area | Concrete implementation |
| --- | --- |
| Hardware execution | 34 compiled native libretro libraries, 29 operator-approved configurations and 46 mapped hardware targets. Libraries, upstream revisions, licenses, runtime assets, firmware and installed interpreter identities are pinned. The old six-core registry remains unchanged. |
| Target authoring | 169 canonical console profiles with explicit known hardware limits, conservative authoring limits, codecs, controller layouts, native source/toolchain readiness and unsupported operations. |
| Visual editing | Palette and pixel editing, new tiles/banks/sprites, tile transforms, layered maps/collision/entity placement, controller bindings, crop/fish/NPC/quest/economy/audio configuration and exact source editing. |
| Real assets | NES/GB/SNES/SMS/Genesis/GBA tile encodings, hardware map/palette entries, PS1 TIM at all four supported depths, bounded PNG decode/quantization and PCM/WAV import. These are encoded assets, not an assertion that every target program consumes them. |
| Native editor binding | NES and Game Boy starter programs consume edited pattern/palette/map/collision/sprite/goal data. Later asset edits regenerate the data include without silently replacing user-edited program code. Modified kernels lose the automatic integration claim. |
| Editor recovery | Exact full-manifest compare-and-swap, versioned application journals, bounded inverse edits, undo/redo, native asset/source inspection, and conservative tile-grid reachability reports. |
| Design simulation | Actual controller steps, collision, hazards/goals, entity interactions, crop preparation/water/growth/harvest, fish state, NPC quests, combat, rendered PNG, bounded PCM and replay. This is explicitly separate from hardware emulation. |
| Synthesis | One or three distinct source origins, current owned source references or clearly authored inspiration, role/conflict decisions, original assets, exact provenance and a coherent original world. The Zelda/Pokémon/Harvest Moon example is authored inspiration, not measured commercial ROM behavior. |
| Runtime editing | Real top-down adventure/fishing/farming mechanics, world/map/entity/economy edits, browser/SDL2/Python renderers, controller play, local saves and live observation. The separate Python side-view adapter exists; full portable side-view export is explicitly unavailable. |
| Fidelity | `pixel`, `enhanced`, and `cinematic` profiles affect actual palette grading, lighting, layers, particles and camera rendering. The studio can trial the next profile in the improvement loop. These are bounded 2D profiles, not an automatic AAA renderer or subjective artistic qualification. |
| Desktop compiler | Fixed approved Go compiler builds native browser launchers for Windows AMD64, Linux AMD64/ARM64 and macOS Intel/Apple silicon. Actual C99/SDL2 compilation remains with the existing native build owner. |
| Learning triangle | Actual Q-policy training/play, Dragon source/layout/pixel inspection and separate ordinary/perturbed held-out comparison, with measured champion gates and retained rejected experiments. |
| Durable campaigns | Up to 100,000 requested rounds, 1–8 rounds per slice, 131,072 total planned transitions per slice, finite automatic authorization, pause/resume/cancel, complete round snapshots and paged evidence. Configured rounds are never counted as executed work. |
| Jeeves app use | Provider-compatible app/creator tools, current project/source inspection, typed studio edits, real simulation/play, queued builds/training/comparison/export and campaign commands, under existing host tool grants and application authority. |

## The improvement loop

1. A current owned project/source and optional admitted policy are bound to the
   exact executable request, source/context, code, teacher and runtime identities.
2. A proposal uses bounded editable parameters and remembered accepted/rejected
   directions. Opaque native ROMs may be played and policies trained; unsupported
   native game code is not rewritten automatically.
3. Jeeves trains a candidate policy from actual transitions. The current champion
   and candidate then play an ordinary held-out seed and a separate jittered seed.
   Training and evaluation seed partitions are distinct.
4. Dragon checks real preview bytes and decoded pixels, typed capacity/source
   constraints and supported layout reachability. Pixel checks measure palette
   occupancy, dominance, luminance range, edge density, opacity and flat frames.
   These are specialist numeric reviews; no hosted model critic is fabricated.
5. The adversarial role records the perturbed candidate/champion comparison.
   Positive ordinary gain, no perturbed regression and hard checks are required
   before the candidate replaces the campaign champion.
6. A complete round/report/policy/lesson snapshot commits behind current worker
   token, attempt epoch, lease, campaign cursor, source and teacher fences. Rejected
   candidates also teach the next proposal. Projection failures retain the exact
   committed payload for repair; partial or stale work cannot invent progress.
7. The next bounded slice can start automatically only after the previous physical
   worker has quiesced and the exact issuing attempt is completed. Cancellation,
   pause, expiry, withdrawal, code changes or failed publication stop continuation.

A campaign reuses one existing project job slot across terminal slices, preserving
attempt/stream identity. This avoids exhausting the existing 512-job project limit
long before a 100,000-round budget. The campaign's authoritative cursor and history
are distinct from that reused execution handle. All-round evidence is paged;
runtime memory carries bounded recent lessons rather than an ever-growing array.

Lessons remain scoped and digest-bound. Historical outcomes are not silently
relabelled as measurements of a new source, environment, runtime or human. Contextual
reuse can influence proposals only after original source/teacher authority is checked;
it cannot import a champion, grant consent, or prove generalization automatically.

## Application and agent integration

The existing `/game-learning` page now includes visual console authoring,
successor/world editing, actual browser play, learning campaign control and evidence.
Automatic continuation is explicit and expires; the UI defaults to a six-hour
scope. The existing authenticated endpoint resolver and live job/event owners are
used. No separate scraper, provider, database, runtime service or product shadow
store was introduced.

| API owner | Surface |
| --- | --- |
| Console studio | `/api/game-console-studio/profiles`, `/projects`, `/projects/{id}/document`, `/projects/{id}/handoff` |
| Successor | `/api/game-successor/sources`, scoped synthesis/candidate adoption/comparison, current world editing and desktop packages |
| Campaigns | `/api/game-studio-learning/projects/{id}/campaigns`, `/campaigns/{id}`, pulse/pause/resume/cancel, paged rounds and scoped lessons |
| Agent commands | `/api/game-studio-tools/catalog` and `/execute` |
| Existing execution | `/api/game-learning` projects, sources, simulations, jobs, builds, artifacts, live play and recordings |

The executable studio command registry supports current inspection, console/world
edits, simulation, native/desktop build, training, synthesis/comparison, play
start/input/control, campaign creation/control, round pages and lesson search.
Public bodies never provide a library path, shell command, provider credential,
Mongo selector or consent bypass.

`Jeeves.app_tool_registry()` still composes the existing app/creator discovery tools.
A trusted application host can call `register_application_studio_tools()` with its
current scope, approved project IDs, owning event loop and exact-command authorizer.
The existing agent ToolExecutor must separately grant `studio_inspect` or
`studio_execute`. The server-derived `studio_agent_user_id(scope)` bridges account
IDs such as email addresses to the agent's canonical identifier format; model
arguments cannot choose another actor.

Existing dotted app/creator/shadow tool names were rejected by the canonical tool
name validator. The registered names and permission comparisons now use valid
underscores. Object argument schemas now use `maxProperties`. Command/result
receipts use one UTF-8 canonical JSON encoding, and mutating simulation/play
responses project bounded receipts before returning so a large frame/trace does
not turn a successful operation into a misleading tool failure.

## Operator setup

Build tooling is explicitly installed by an operator, outside product input:

```sh
python scripts/install_game_desktop_toolchains.py --root /absolute/private/toolchains --cc65 --rgbds
```

The receipt lists exact downloads, pinned source commits, compiler hashes,
licenses and required environment configuration. Go 1.27.2 and SDL2 headers are
SHA-pinned; cc65 and RGBDS are built from exact upstream revisions with private
build dependencies. Tool installation does not download games or licensed firmware.

Native core setup uses the existing operator installer:

```sh
python scripts/install_game_emulator_cores.py --source-root /absolute/private/core-sources --install-root /absolute/private/cores --fetch-sources --core gambatte --core fceumm --jobs 1
```

Select additional named recipes explicitly. The source catalog contains 35 pinned
recipes. Hardware renderers, firmware, build headers and runtime assets are declared
per core. Missing requirements leave a target unavailable. Configure the resulting
`SKL_GAME_EMULATOR_REGISTRY` on the backend; a changed registry is a new execution
identity and does not silently grandfather old policy bindings.

Console builds use fixed trusted compiler commands, private exact-source material,
mandatory bubblewrap isolation, no compiler network and bounded process/memory/log/
artifact/disk/deadline resources. The old host-UID-wide process cap was replaced by
actual compiler subtree monitoring so concurrent legitimate builds can start.

Desktop exports embed exact original files in a native local launcher. The launcher
serves only an unguessable loopback path, checks Host/Origin and content identities,
uses a local CSP, and offers bounded atomic OS-local saves and graceful quit. Its
renderer is the player's browser. macOS packages contain `.app` structure; signing,
notarization and foreign-OS execution are not asserted by cross-compilation.

## Productive evidence and source checks

The detailed machine evidence is
`machine/ai_game_studio_session_evidence_2026-10-14.json`. It distinguishes actual
local work from configured budgets and historical evidence.

- Both visual-editor native bindings compiled through actual ca65/ld65 or RGBDS.
  The resulting NES and Game Boy cartridges each executed 150 real controller
  steps in FCEUmm/Gambatte and produced captured native frames.
- An original NES cartridge trained for eight episodes on two actual emulator
  workers, committing 1,024 Q updates.
- The first triangle workload executed editor, successor and native-ROM rounds,
  retaining complete actual reports and lessons. Final checkpoint/resume workload
  totals are recorded in the machine evidence.
- Original successor optimizer work executed 10,240 transitions, eight candidates
  and disjoint held-out seeds. Movement target error changed 0.07027 to 0.02308.
  This compares authored numeric movement targets; it does not measure commercial
  game superiority or player satisfaction.
- All five desktop OS/architecture compiler targets produced valid native binaries
  and exact packages. Linux launcher/browser play and persistent save readback ran.
  Windows/macOS/ARM target execution was not performed.
- Native SDL2 source compiled and ran. Three fidelity profiles produced distinct
  actual preview hashes. Native/profile receipts remain separate from emulator
  hardware compatibility.
- Production Expo web export completed: 186 HTML routes, 292 files and 33,303,280
  bytes, with the new console/successor/campaign/automatic control UI in the bundle.
- Python compilation/lint, frontend TypeScript/ESLint, whitespace, architecture,
  construction, capability, provider-bootstrap and enterprise source validators
  passed as recorded. No automated test suite was run.

The application still needs its existing authenticated backend, CORE_DB Mongo,
governed storage admission, configured approved cores/toolchains and Dragon source
custody. An authenticated Mongo/API deployment was not exercised in this session.

## Remaining capability limits

Compilation and mapped targets are not compatibility proof for every game. The
four firmware-blocked cores and the hardware-renderer-blocked core remain inactive.
Only the source-declared ROM metadata families receive structural semantic parsing;
other admitted native media remains explicitly opaque. Commercial gameplay feel,
full design understanding and best-in-class artistic quality cannot be inferred
from a ROM filename, catalog entry, renderer preset or iteration count.

The NES/GB starter bindings implement one physical viewport with movement,
collision, sprites and a goal. Native farming, full genre mechanics, APU/music,
scrolling and other target bindings remain separate implementation work. The app
provides richer design simulation and original top-down portable runtime mechanics;
it does not label those as completed hardware ports.

The loop learns bounded policies and empirical proposal directions. It does not
rewrite production application code or foundation-model weights, guarantee monotonic
quality, certify 100,000 successful runs, or mark the AI masterplan complete.
