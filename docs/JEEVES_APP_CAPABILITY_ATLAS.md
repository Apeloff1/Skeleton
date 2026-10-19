# Jeeves application capability atlas and local workbench

The local workbench exposes installed source families and a fixed set of typed
adapters. Use it to inspect capabilities, preview original mechanics, compile
bounded source previews and prepare reviewed edits. The assembled product's AI
chat, crawler, build jobs and training controls are covered in the
[studio operator guide](ai/STUDIO_CRAWLER_BUILDER_TRAINING.md); start a new
installation with the [first-install guide](ai/FIRST_INSTALL_AI_AND_CRAWLER.md).

The workbench is a separate existing loopback interface. Its local adapters do
not call a model or inherit the assembled application's provider credentials.
A discovered module is metadata until an explicit adapter supports its operation.

## Open an operator-owned workspace

From the checkout root, after installing the application dependencies:

```bash
python -m skeleton.ai.game_builder.game_workspace_cli init \
  --root /absolute/private/jeeves-workspace --trusted-local-operator
python -m skeleton.ai.game_builder.game_workspace_cli create \
  --root /absolute/private/jeeves-workspace --project original_studio \
  --genre rpg --trusted-local-operator
python -m skeleton.ai.game_builder.game_workspace_cli serve \
  --root /absolute/private/jeeves-workspace --port 0 --open-browser
```

`init` requires a new directory beneath an existing real parent. `create` makes
an empty original project and selects it; it does not deliver a finished game.
For an existing workspace, use `select` instead of creating another project.
The server prints its actual `127.0.0.1` URL. Keep its session capability private;
the server refuses a public bind and cross-origin editing. Stop it with Ctrl-C.

Select the active **current** project before using project actions. Previous
and demo sources remain references until forked through their existing workflow.

## Discover the installed application

The **Whole-App Capability Cockpit** lists installed families and canonical
actions. **Complete application capabilities** provides a separate whole-checkout
inventory and appwide adapter selector. The two selectors have separate state.

Frontend families resolve to the current source tree:

| Atlas family | Installed source path |
| --- | --- |
| `frontend_features` | `frontend/src/features` |
| `frontend_components` | `frontend/src/components` |
| `frontend_services` | `frontend/src/services` |
| `frontend_state` | `frontend/src/state` |

These are source directories, not browser URLs or arbitrary execution targets.
The atlas also describes backend, Forge, crawler/Dragon, Jeeves, learning,
packaging and other installed families. A partial installation can report a
family as absent. Files and directories found through discovery do not become
callable tools.

Each registered action describes its effect, required/optional parameters,
operator confirmation requirement and relevant runtime dependencies. A source
file count or adapter count does not establish working feature coverage.
Read the live catalog rather than treating historical counts as installation
requirements.

## Run a bounded operation

1. Refresh the relevant cockpit or scan the whole application.
2. Select an action and inspect its required fields. Common previews receive an
   editable example; other actions need the displayed typed arguments.
3. For an action requiring confirmation, deliberately check the confirmation
   box, then invoke it. The box resets when the selection changes, after a
   refresh and after a successful confirmed operation.
4. Inspect the receipt's actual result and source identities. A staged proposal
   still requires the existing separate source review and commit operation.

The session token authenticates access to this local interface. The confirmation
box records intent for the selected operation; a request boolean or a catalog
hash cannot create privileges. Requests must still satisfy the active-project,
typed-argument, operator and original-owner checks.

Common canonical operations include:

| Action | Actual result |
| --- | --- |
| `studio.editor.preview` | Validate typed settings and run the existing deterministic preview |
| `studio.editor.stage` | Prepare an exact-source editor proposal for later human review |
| `studio.source.propose` | Stage one permitted current-project source edit with its expected SHA |
| `forge.graph` | Validate bounded component, port, wire and cycle constraints |
| `game.compile.original` | Compile a bounded original browser source preview with a winning replay |
| `game.compile.native` | Render browser and Godot source from the same verified original world |
| `game.mirror.review` | Run the existing bounded original-game replay/mirror and return its receipt |
| `game.console.source.stage.artwork` | Stage generated native source incorporating concrete original sprite pixels |
| `system.triad` | Exercise bounded gameplay, assets, music and reference integrity through deterministic role adapters |

Browser/Godot source generation does not establish that Godot or a native
executable ran. The native-art action does not invoke a toolchain or emulator.
For actual governed compiler jobs, previews and package exports, use the
[assembled studio workflow](ai/STUDIO_CRAWLER_BUILDER_TRAINING.md).

## Keep requests coherent with the catalog

`app_atlas()` and `/api/jeeves-app-atlas` return a `catalog_digest`. The canonical
request body may pin it with `expected_catalog_digest`; the cockpit does this
automatically. `compose_app_request()` freezes the selected project, registered
action, bounded arguments, argument digest and catalog identity without executing
anything or granting authority. Dispatch returns that `request_digest` alongside
the result and catalog digest.

The catalog hashes listed adapter/domain-source files and includes the typed
action, tool and editor contracts. It does not attest every transitive dependency,
the loaded interpreter, standard library, model readiness or the entire deployed
app. A changed catalog is refused before dispatch; changes to listed owners
during an operation prevent publication of a matching successful receipt.

Arguments use finite JSON with at most 16 top-level fields, 16 nested levels,
16,384 value nodes and 256,000 canonical JSON bytes. Individual actions impose
further constraints. Duplicate JSON keys, nonfinite values and excessive nesting
are refused. Keep model-generated arguments as untrusted data and allow the host
to validate them.

If a request reports a stale catalog, refresh the cockpit, recheck the current
action and arguments, and confirm again where required. For source conflicts,
reopen the affected source and review the diff against its new SHA. Do not remove
source checks or replay a previous confirmation to force an action through.

The appwide API has a separate catalog digest and inventory snapshot. Its exact
envelopes and rescan recovery are documented in the
[whole-repository inventory guide](JEEVES_WHOLE_REPO_INVENTORY_AND_GOVERNED_ACTIONS.md).

## Stage native artwork and audio source

The canonical `game.console.source.stage.artwork` action accepts eleven base
fields plus `artist_tiles`, with optional `animation_fps` and `music_density`:
a complete request can therefore contain **14 action fields**, within the
16-field envelope. Its `project`, action ID and confirmation belong to the
outer request, not to `args`.

| Fields | Meaning |
| --- | --- |
| `intent`, `target`, `source_platform` | Bounded original game intent and registered target/design basis |
| `rights_evidence_sha256`, `creative_identity` | Authorship-document reference and original identity statements; not independent rights clearance |
| `style`, `contrast`, `animation_frames` | Typed original art controls |
| `source_file`, `expected_sha256`, `reason` | Exact target entrypoint, current source identity and concrete review rationale |
| `artist_tiles` | Six actual 8×8 indexed sprites: six arrays of 64 integer values in `0..3` |
| `animation_fps`, `music_density` | Optional bounded controls consumed by the applicable native source integration |

Supported exact entrypoints are `main.asm` for `nintendo_game_boy` and
`nintendo_game_boy_color`, `main.s` for `nintendo_famicom`, `game.asm` for
`sega_master_system`, and `game.c` for `sega_game_gear`. Target-specific animation
and audio evidence must be read from the actual result; accepting controls does
not prove every target plays them. The generated source is staged through the
existing optimistic-SHA proposal owner. It remains uncommitted until separately
reviewed, and makes no emulator or physical-hardware claim.

## Understand triad and model readiness

`system.triad` binds Jeeves, Dragon and adversarial **deterministic local
adapters** for a bounded original maze, procedural assets, music and reference
partition integrity. It records zero model calls, no independent model review,
no weight changes and no automatic knowledge promotion. Role names do not
establish independent AI judgment or a measured improvement in game quality.

The operation requires these optional installed reference-pack files:

- `data/game_building/manifest.json`
- `data/game_building/pareto/game_design_pareto_corpus.txt.gz`
- `data/game_building/math_physics/game_math_physics_corpus.txt.gz`

The [reference-pack guide](../data/game_building/README.md) describes their
provenance. The catalog reports metadata availability; execution separately
verifies compressed and decoded digests, byte/row limits and held-out partition
integrity. Generated reference rows are neither measured gameplay nor model
training permission.

The default production image source allowlists exclude these optional packs.
A healthy chat/backend installation can therefore have an unavailable triad
reference dependency. An operator must supply the expected files and matching
manifest through the installation's explicit data configuration before invoking
it. Refresh after changing availability. Do not replace a missing pack with
unverified content or interpret a model installation as satisfying this gate.
Actual chat inference uses the separately configured canonical engine boundary;
see [AI activation](ai/FIRST_INSTALL_AI_AND_CRAWLER.md).

## Recorded operation and limits

The [18 October operator record](ai/evidence/enterprise-2026-10-18/studio/qualification-summary.json)
binds the five changed workbench owners to exact byte hashes, using source base
`f511c704ec07816697a9df34c5fc622c02565b21`. Its observed catalog digest is
`777fa6428b3447c6d1dd8a84bbf618298a378ab9f9bb4206920eb8a3889236a2`.
These identify that recorded operation, not all later source revisions.

That run observed **29 canonical actions**, **36 appwide adapters**, 46 listed
catalog source owners and 16 listed triad source owners. Chromium exercised cold
workbench loading, confirmation, actual source compilation, appwide Forge
forwarding, replay/mirror review and the triad with zero page errors. HTTP
operations also observed stale-catalog/confirmation/JSON-budget refusal and a
complete 14-field native-art proposal. No proposal was committed, no native
compiler/emulator ran, and no model call or automated test suite was run for
this workbench qualification. The owned temporary server was stopped afterward.

This is bounded operator evidence. Universal console support, full-app execution
coverage, transformer improvement, subjective game quality and enterprise
qualification remain separate claims requiring their own evidence.
