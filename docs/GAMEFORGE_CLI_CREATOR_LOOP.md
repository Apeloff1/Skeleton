# GameForge CLI creator-loop controls

The CLI and the ten-stage GameForge pipeline now carry the same questionnaire
answer shape used by `skeleton.context.questionnaire.intake`.

```bash
python -m skeleton run "A quiet original village" \
  --answers '{"pace":"unhurried","death":"nothing","genre":"rpg"}' \
  --archetype auto --out build/village --playtest auto --json

python -m skeleton run --answers-file ./answers.json \
  --out build/village --playtest require --repair-mode apply
```

`--answers @path.json` is equivalent to `--answers-file path.json`.
Answers are capped at 64 KiB and validated against known questionnaire beat
IDs/choices; creative brief facets accept strings. Malformed JSON, unknown
fields/options, and invalid playtest/repair policies fail with exit 2, rather
than silently creating an unrelated game. `--playtest off` disables headless
verification; `auto` runs it when the Godot binary exists; `require` treats a
missing or failed Godot boot as a failure. The pipeline still returns exit 1
for a failed generation/proof.

Questionnaire-derived tensor axes now survive the pipeline's tensor stage
unless an explicit era or blend overrides the questionnaire. A JSON run
includes the structured `intake` evidence and `playtest` result.

This change does **not** claim parity with the separate `/gameforge/run`
shared-command engine, or cockpit steering persistence across processes.
Those remain separate tracked integration gaps.

## API parity for Godot target

`POST /gameforge/run` and the shared `run` command accept `{"target":"godot","answers":{"pace":"unhurried"},"vision":"A quiet village"}`.
The Godot target now invokes the same `GameForgeRun.execute` ten-stage
pipeline as the CLI. HTTP responses carry its in-memory game/report including
emitted `files` and intake evidence; server output paths and overwrite
controls are deliberately rejected. Playtest and repair modes are explicit
and bounded. The existing JSON/YAML game-spec command remains unchanged for
compatibility, so this is **Godot-target parity**, not yet complete parity
for every materialization target.

## Persistent local creator steering

The CLI stores **operator choices only**, atomically with private permissions, in
`~/.skeleton/cockpit.json` (override using `SKELETON_COCKPIT_STATE`).

```sh
python -m skeleton cockpit BIND ERA cozy_wholesome
python -m skeleton cockpit BIND ARCHETYPE auto
python -m skeleton cockpit SET AXIS intimacy 0.95
python -m skeleton cockpit SNAPSHOT --out ./creator.json
python -m skeleton run "A quiet village" --out build/village --playtest auto
python -m skeleton cockpit RESTORE ./creator.json
```

Saved era, axis adjustments, blends, generation and archetype survive CLI
invocations. Explicit `--era` or `--blend` takes priority for one run. The
file never contains ledgers, inference traces, credentials or session data.
Malformed steering fails closed; RESTORE repairs it from a valid snapshot.
Failed pipeline stages are reported by name and error; JSON adds
`failed_stages` for diagnosing required headless-Godot boot failures.

## Final emission evidence

The seal stage (not the earlier emit stage) now writes final
`CONTEXT_LEDGER.json` and `CONTEXT_TENSOR.json`, plus
`build_report.md` under the requested output folder. The report records
real build seed, oracle cue, final stage mass, Godot boot result, sim result,
SHA-256 of the generated file manifest, and final append-only ledger head.
Field coverage is explicitly **unmeasured** unless a numeric field metric
is actually available: it is not invented to satisfy a checklist.
Ledger verification errors fail the seal stage rather than passing with a
false `sealed` value. Failed builds do not gain a false final acceptance
report.
