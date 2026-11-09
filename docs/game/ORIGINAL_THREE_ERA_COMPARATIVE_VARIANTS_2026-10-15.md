# Original three-era design variants from comparative game observations — 2026-10-15

The comparative studio's earlier/middle/after **observation points** are now complemented by a separate builder for three **new original editor projects**, using Skeleton's canonical `ConsoleProject` owner.

This system accepts one intact `skeleton.game.comparative_study_result.v1` report from actual native emulator sessions, **2–30** explicitly selected observed games, and one supported original output console target. It verifies the exact report digest before using observed audiovisual stage receipts, reviewer-attributed notes and optional numerical design hypotheses.

It produces:
- **Earlier original variant:** simple, original authored tile barrier layout and original palette.
- **Middle original variant:** two authored navigation decisions and distinct original palette.
- **After original variant:** three authored barriers/alternate passages and a distinct original palette.

Each is generated through the existing `create_console_project` / `ConsoleProject` validation path. A reachability check protects the generated player-to-goal route against solid tile edits. The three variants have distinct project manifests and typed editor files so Jeeves/the user can open and further edit them. Source-game ROM bytes, maps, characters, sprites, music, dialogue, plots and videos are not copied into generated files. Evidence receipts from source games remain as SHA-256 references only. A locally reviewed build parameter (e.g., movement speed, camera lookahead) remains a proposal requiring empirical validation, rather than being injected as an undocumented exact game fact.

## Operator command

```bash
python3 scripts/forge_game_comparison_variants.py \
  --result /srv/study-reports/genre_evolution_one.result.json \
  --game prototype_a --game prototype_b \
  --target nes --project-prefix original_evolution \
  --seed 1204 --output-dir /srv/original-projects
```

For each stage the script outputs `original_evolution_<stage>.editor.json` (the canonical original editor document) and `original_evolution_<stage>.files.json` (its canonical editable project file mapping), plus a `original_evolution.forge_receipt.json` with source hash lineage, project digests and no-compile status.

All three are **original validated editor designs**, not evidence that actual hardware executables were compiled. To build ROMs, hand off their editable files to the existing approved ConsoleProject native asset and build pipeline with separately validated toolchain; it remains subject to each console's actual native binding and runtime tests. No model weights are changed. A named baseline target is required; adding 30 source games never means starting 30 emulator instances here.

Tests: `tests/test_game_comparison_variant_forge.py` covers an integrity failure, duplicate game refs, unsupported hardware and a three-variant canonical document. It uses strictly fabricated unit-test fixtures to validate the code contract, never as claimed observational evidence. Native game play or hardware tests were not run in this repository edit.
