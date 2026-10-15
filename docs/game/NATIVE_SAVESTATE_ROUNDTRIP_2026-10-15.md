# Native checkpoint/restore replay audit — October 15, 2026

The new `run_native_savestate_roundtrip` in `skeleton/jeeves/game_emulator_savestate_audit.py` uses the existing operator-approved, sandboxed libretro worker's actual `retro_serialize` and `retro_unserialize` ABI calls. It is an executable qualification mechanism, not a pretend reference simulation.

An operator chooses a 2–64-step policy or four-port raw-controller input tape and a checkpoint strictly inside the tape. The runner starts the actual approved core and lawful ROM, performs the prefix, records a native checkpoint, performs the suffix, **restores the checkpoint in the same native worker process**, then performs the identical suffix again. The original and repeated suffix are compared for native video SHA-256, PCM SHA-256, callback/sample counts, observed state-derived values, reward and chained transition digests. The output retains the first divergent suffix step and exact per-step result hashes.

```bash
python3 scripts/qualify_game_emulator.py \
  --registry /srv/skeleton-emulators/cores.json \
  --target nes --core fceumm \
  --source /srv/lawful-homebrew/hello.nes \
  --action idle --action right --action a --action left \
  --checkpoint-at 2 --seed 11
```

The same CLI supports `--controller-tape-json` instead of `--action` and respects the existing `--controller-device` topology. `--checkpoint-at`, `--compare-core`, and `--explore-scenarios` are mutually exclusive high-cost modes. Content/legal/firmware authority and source checks remain with the existing Jeeves owners.

Bounds: at most 64 selected input steps, 1–8 frames per step, at most 2,048 total requested native frames including reset, one sandboxed worker, bounded native snapshot serialization. Native failures fail closed. There is no disk download, ROM/firmware bundling, model training or automatic promotion.

**Important limitations:** Native checkpoint restoration is *not* inverse CPU execution or arbitrary backward frame stepping, and passing this audit does not prove full hardware compatibility, graphics/audio fidelity, game completion, intellectual property rights or parameter gain. No actual ROM or native core was executed by this code-editing session.
