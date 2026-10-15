# Cross-core native differential training evidence — 2026-10-15

New `skeleton.jeeves.game_emulator_cross_core.compare_native_emulator_cores` compares **2–8 different operator-approved libretro implementations** on the *same* canonical target, exact legal content source, policy action tape or multi-controller frame tape, selected controller devices, seed and current signed registry digest. It invokes the existing active native qualifier separately for every core, so each core gets 2–10 fresh isolated worker executions and its own internal replay-consistency score.

The result includes source registry identity, deterministic input-tape digest, per-core native run/audio/video receipts, each within-core replay-audit digest and each pair's exact final-frame/PCM hash equality. A mismatch is a review candidate, not proof of which core is wrong. Core differences in rendering resolution, clock phase, region setup, game implementation, filters or incidental presentation may cause legitimate inequality.

### Explicit operator command

```bash
python3 scripts/qualify_game_emulator.py \
  --registry /srv/skeleton-emulators/cores.json \
  --target nes --core fceumm --compare-core nestopia \
  --source /srv/lawful-homebrew/hello.nes \
  --action idle --action right --action a --runs 3
```

This uses **existing installed/approved cores**; source recipes alone are not enough. The CLI also accepts the existing bounded `--controller-tape-json` for precise multi-port comparison, or regular `--action` selectors. `--compare-core` and `--explore-scenarios` are mutually exclusive to preserve the cost ceiling. At most **65,536** requested native step/reset frames can be spent across the entire cross-core comparison; invalid or unapproved cores fail closed. No game, BIOS, source code or licensed SDK is fetched or bundled by this function.

### Completion and limits

This code is implemented in the existing Jeeves registry, host and controller audit, but has not executed a native ROM in the development session. No new compiled cores, emulator-accuracy certificates, model weights, model-training improvement, ROM legal-rights verification or gameplay-success verdict are claimed. Independent lawful homebrew ROMs and qualified Linux hosts are required for meaningful measurements.
