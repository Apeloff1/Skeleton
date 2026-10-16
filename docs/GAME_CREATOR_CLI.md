# Local game-creation CLI

The canonical operator entrypoint is **python -m skeleton dev game** (or
**skeleton-dev game** after installing the package). The commands live under
the existing developer CLI; they **do not** create a second engine, provider
runtime, studio database or API. Game generation remains owned by
skeleton.context.pipeline.GameForgeRun, emitted files by
skeleton.forge.projector, deterministic file identity by
skeleton.forge.source_manifest and dynamic Godot checks by
skeleton.forge.playtest.

## First project

Run from a local development checkout with Skeleton installed:

~~~bash
python -m skeleton dev game catalog
python -m skeleton dev game init my-adventure \
  --vision "An original exploration RPG with branching quests" \
  --era extraction_now --archetype auto
cd my-adventure

python -m skeleton dev game info
python -m skeleton dev game doctor --require-godot
python -m skeleton dev game build --playtest auto
python -m skeleton dev game verify
python -m skeleton dev game playtest --frames 300 --timeout 120
python -m skeleton dev game assets
python -m skeleton dev game package
~~~

The same verbs are available from outside a workspace with
--project /path/to/my-adventure. The init command accepts --dir to choose a
parent folder and --dry-run to show the planned files without creating them.

The project manifest **skeleton.game.json** is a small, validated local
configuration with name, vision, era and archetype. Additional design notes
belong in design/, source art belongs in assets/, and project-level tests
belong in tests/. The CLI never replaces the user's design work on init;
existing destinations are rejected.

## Iteration and qualification

- **catalog**: reads the existing forge era and archetype catalogs; reports only the currently wired Godot source target and package format.
- **info**: validated local project metadata and whether a Godot emission
  exists. It does not attest that emission is correct.
- **doctor**: era/configuration validation and whether a Godot executable is
  discoverable, including whether its artifact is verified. A missing Godot
  binary can be nonblocking for source-only work; --require-godot makes it
  a failed prerequisite.
- **build**: invokes the existing ten-stage GameForge creator pipeline with
  the pinned project vision, era and archetype. Outputs go only to
  build/godot. --playtest off|auto|require and
  --repair-mode apply|suggest delegate to the pipeline. No implicit
  overwriting: --overwrite is required to replace an existing generated
  project. The command returns stage failures and source identity evidence;
  a failure does not claim a successful build.
- **verify**: reads emitted UTF-8 source, recomputes each SHA-256 entry and
  validates the canonical source-manifest identity. It can also invoke the
  same headless gate with --playtest auto|require, frames and timeout.
  Changed, missing, unsafe or symlinked source files fail verification.
- **playtest**: requires an actual headless Godot import and scene boot
  through the canonical gate, defaults to 300 frames and 120 seconds. An
  unavailable executable is a failed playtest, not a fabricated pass.
- **assets**: bounded read-only digest inventory of assets/; it does not
  invent or silently import assets into emitted source.
- **package**: creates a deterministic Godot **source** ZIP from verified
  emitted text and available Forge evidence. A preexisting archive is
  protected unless --overwrite was explicitly set; --dry-run only plans.
  This is *not* a compiled executable, console ROM, platform export, or
  proof of successful gameplay.

The commands produce structured JSON; a nonzero process exit means the
requested operation did not succeed. Usage errors follow argparse's
standard exit code 2.

## Boundaries and follow-on work

Source receipt equality is not a runtime-playability verdict. To qualify
gameplay, require real Godot boot and eventually long-running playthrough
evidence. Native Windows, Linux, mobile, web, and console export require
separate toolchain, export-preset, signing, licensing and target-device
acceptance gates. Do not infer these from the source ZIP.

The typed creator command surface (create/edit/test/preview/export) stays
transport-neutral in skeleton.forge.creator.command_surface; this developer
workspace wrapper supplies local project workflow without bypassing that
authority boundary or enabling remote path writes.

Project validation is covered by
skeleton/testing/test_game_creator_cli.py and intentionally does not
require a model checkpoint or installed Godot binary.
