# Active native emulator qualification — 2026-10-15

## Actual execution path

The existing `GameEmulatorRegistry` approves core/firmware bytes, and `EmulatorEnvironment` launches the actual Linux bubblewrap-isolated libretro worker. New `game_emulator_qualification.run_emulator_qualification` connects those existing owners to the previously delivered offline trace/PCM/replay audit.

The caller must choose a canonical hardware target, **explicit core ID**, exact current approved registry digest and rights-cleared content. The runner creates **one fresh native process per pass** (2–10 runs), replays the same policy action tape, captures actual frames/audio/controller and hash-chain evidence, then computes the first replay divergence. It never selects a reference-game substitute when libretro cannot run.

### Operator command

```bash
python3 scripts/qualify_game_emulator.py \
  --registry /srv/skeleton-emulators/cores.json \
  --target nes --core fceumm \
  --source /srv/lawful-homebrew/hello.nes \
  --action idle --action right --action a --action idle \
  --runs 3 --seed 27 --frames-per-step 1
```

The source must be a nonsymlink operator-owned file within 16 MiB; larger disc and multi-file content remains exclusively under the existing governed content-bundle owner. By default only hash/evidence summaries are output. `--include-traces` adds actual validated bounded offline `skeleton.game.trace.v1` episode records (8 MiB aggregate cap), usable by the existing learning ingestion owner after provenance and legal review. Additional named controller devices can be passed via `--controller-device`; the host/worker enforce the 4-port limit.

### Bounds

- 2–10 actual independent worker initialization attempts, not background loops.
- At most 64 actions per run and 4,096 total requested step **plus reset** frames per batch; 1–8 frames per action.
- Every core must already be installed and approved, with an exact matching registry digest; firmware availability is checked by the normal registry.
- The original media hash, worker source, compiled ELF hash, system firmware and core options remain environment-bound across all runs.
- Difference audit reports per-step video PCM SHA-256, observation, policy reward, callbacks and chained native frame receipts.
- Source data and core binaries are not fetched, compiled or distributed here.
- No legal-rights proof, hardware emulation correctness, real game victory, model weight training or weight promotion is implied by repeatable frames.

The batch does **not** make a native core boot successfully on this development environment. Qualification must be run by an operator with an actual supported Linux sandbox and licensed/homebrew content. Unavailable core, missing firmware, malformed source or changed registry is a failing result; not a synthetic successful report.
