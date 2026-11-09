# Operator-run boomerang native emulator exploration — 2026-10-15

## Purpose

Run more *real* emulation trials, not another empty 169-machine checkbox. This capability wraps the existing isolated native libretro qualification runner and repeats legally approved homebrew input scenes under bounded, deterministic variations. It is explicitly a measurement of novel video/audio responses, **not** proof the production AI has learned everything.

## Behavior

Each scenario uses 2–10 fresh isolated libretro-worker sessions, records canonical frame, PCM, callback and transition evidence and compares deterministic replay via the existing audit. The scenario planner starts with a base input tape and constructs the reverse order, left/right/up/down mirror, rotations, edge-to-center interleaving, and bounded one-step changes. Every four evaluations it places an *already visited* scenario back into the queue (seeded), and reshuffles all scenes after the current queue is exhausted. Old baseline scenarios are reintroduced periodically.

After **10 consecutive scenes with no new observed final audio/video hash combination** by default, it stops, or it stops at an explicit maximum. Replay divergence still reports independently even if an audiovisual signature is not novel. The novelty metric cannot infer game success, mastery, coverage of all game branches, emulator hardware correctness, weight gain, or legal rights.

Operator caps: 2–80 scenarios, 2–10 worker runs per scenario, up to 64 actions each, 1–8 frames per action, 3–20 scenario no-novelty threshold, at most 131,072 requested native frames including reset upper bounds. A failing native core, unauthorized ROM, corrupt record, missing firmware, cancelled task or inconsistent registry stops with an error rather than generating fake evidence. There is no hidden background queue or non-user-approved network/core access.

## Explicit operator command

```bash
python3 scripts/qualify_game_emulator.py \
  --registry /srv/skeleton-emulators/cores.json \
  --target nes --core fceumm \
  --source /srv/lawful-homebrew/hello.nes \
  --action idle --action right --action a --action left \
  --runs 2 --explore-scenarios 24 --stagnation-window 10 \
  --seed 117 --frames-per-step 2
```

Without `--explore-scenarios`, the existing direct replay-qualification CLI remains the default. Raw multiport controller tapes have their own replay mode; the current boomerang scenario generator only modifies declarative policy actions to avoid inventing unsafe device-specific vectors.

## Training admission conditions

Collected receipts can inform later scenario choice and be scored by separate Dragon/Jeeves reviewers. Actual production-model training and shadow-weight promotion remain **independent**, requiring lawful rights, verified execution, measured baseline and improvement criteria, evidence checkpoints and authorized promotion. No licensed ROMs, keys or BIOS are bundled, and no game was run in the code-editing environment.
