# Thirty-game comparative emulator installation readiness doctor — October 15, 2026

The existing comparative studio now includes a **non-executing installation/readiness audit**. Unlike a native gameplay test, the doctor inspects exact study metadata, the installed and operator-approved libretro registry, core-target mappings, local ROM/disc file identities, controller port declarations and the shared temporary-storage budget for each up-to-ten-game cohort. It reports precise per-game source/installed-core failures and per-cohort disk-plan blockers before the user attempts live play or Q learning.

### Standard source and disk preflight

```bash
python3 scripts/doctor_game_comparison.py \
  --manifest /srv/studies/my_comparison.json \
  --registry /srv/skeleton-emulators/cores.json \
  --output-dir /srv/studies/reports
```

Writes `<study_id>.readiness.json` with 2–30 individually inspected game records and a cohort execution schedule. Small single-file ROMs are always streamed and SHA-256 checked against the pinned source manifest. Native core declarations must resolve through the installed approved registry. Media failures and missing core mappings appear in the report, rather than being reported as success.

For large disc games, the normal check verifies regular-file/symlink-safe content descriptors, exact declared sizes and the host's canonical companion-media metadata, without automatically reading terabytes of local content. An operator who wants to verify **every byte of all declared tracks** can run the same command with `--deep-hash`. That may require substantial disk I/O; it still does **not** execute native code, acquire copyrighted game media or boot any emulator.

### What is displayed

- Each game: title ID, hardware target, core ID, selected controller-family legend, generic/hardware-label status, selected controller devices, installed registry resolution, exact source hash status, rights-receipt presence, source/core blockers.
- Each study cohort: ordered game IDs, manifest concurrency cap (1–10), actually available temporary free disk at preflight, two-copy conservative per-game disk budget, execution wave sizes, and whether all selected games can fit in a single live desk simultaneously.
- Study summary: observed 30-game maximum, number of compared game pairs, actual source/core preflight successes, 169-target catalog count, independent hardware accuracy verification count **zero**, and the content hash depth used.
- A deterministic summary digest for later operator review.

The doctor is a **preflight**, not a declaration of hardware/controller accuracy, playable titles, successful game mechanics, legal rights, new Dragon knowledge or model-weight training. The strict source and registry checks do not substitute for the live native emulator worker, replay audit or a substantive gameplay-quality test.

Unit source tests added in `tests/test_game_comparison_readiness.py` use tiny invented binary fixtures instead of actual game ROMs. The doctor itself has not been run on the user's own emulator registry in this session.
