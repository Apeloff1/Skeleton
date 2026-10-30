# Game studio ecosystem: original production content catalog (draft)

Owner: `skeleton/ai/game_builder`, extending the existing original studio and playable compiler.

The catalog contains 512 *linked source-production briefs*: eight purpose-specific
JSON documents per project (4,096 original documents). Each includes playable
offline-grid preview intent, narrative/canon, character relationships, branching
quests, scene direction, visual recipes, audio direction, and explicit verification
obligations. Thirty-two original genre concepts across sixteen environments give differentiated starting points,
not consumer-ready games. No copied engine source, model checkpoints, third-party
training sets, executable source downloads, or copyrighted game assets are embedded.

Use `python scripts/studio_ecosystem_cli.py --genre puzzle_expedition` to search
the catalog; `--project <id>` reads a complete plan. To build a solvable,
deterministic HTML5 grid *preview* through the existing engine, run
`python scripts/studio_ecosystem_cli.py --project <id> --compile-preview --output ./new_output_dir`.
The result includes a real simulated winning replay receipt.

To compile multiple source briefs into playable offline grid previews, create an
output folder and run `python scripts/studio_ecosystem_cli.py --genre
puzzle_expedition --materialize-batch --output ./preview_outputs`.
This uses source-validated project IDs, a total output byte budget, per-project
exclusive directory creation, real replay verification and content-addressed
receipts; it does **not** silently overwrite prior outputs, import arbitrary
scripts, or activate any other runtime. The operator should set the output
root to its own scratch/artifact storage rather than commit generated HTML to Git. The production
genres, 3D models, animations, music, dialogue, native builds, and multiplayer
systems are **not** implemented by these content briefs. None is certified for
publication without independent completion and review.

Design boundaries:
- Existing `skeleton.ai.game_builder.playable_compiler` and `playable_world`
  remain the only preview compiler and replay proof owners.
- Content is read-only, lazily loaded and indexed; the CLI does not fetch
  providers or mutate the catalog or existing project workspaces.
- A safe project identifier, exact schema, cross-document identity, bounded
  source size, duplicate-key rejection, and release hold are enforced.
- `release_certified: false` is not negotiable in these source files.
- Preview compilation requires explicit authorization and cannot prove the
  remaining game production, original-rights, device or consumer-release gates.
- Large weights, external engine source and derived assets should remain in
  attributable optional stores with on-demand acquisition and rights checks;
  massive vendoring is not a quality strategy.

Future reviewed drafts should connect scene, quest, visual and audio briefs to
the existing native studio editors, real render/audio engines, provenance and
release evidence. Distinguish measured runnable results from design requirements.
