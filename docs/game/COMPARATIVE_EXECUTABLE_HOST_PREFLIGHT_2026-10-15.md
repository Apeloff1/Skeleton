# Executable host readiness gate for the comparative native emulator studio

The previously added 30-game source/core doctor could report positive ROM SHA checks even on machines where the Linux-only native host could never launch. The new host preflight separates three facts:
- **Admissible source and approved core metadata**: exact, locally installed bytes and target/core mapping.
- **Executable sandbox prerequisites**: Linux, trusted root-owned /usr/bin/python3, bubblewrap and the matching worker/protocol source modules.
- **Confirmed minimal namespace capability**: optional `--probe-sandbox` invokes bubblewrap with /usr/bin/true only (no game/ROM/core/BIOS/model), bounded by an eight-second timeout.

Run the nonexecuting study audit:

```sh
python3 scripts/doctor_game_comparison.py \
  --manifest /srv/studies/study.json \
  --registry /srv/cores.json --output-dir /srv/reports
```

Add `--probe-sandbox` to exercise the minimal system-call sandbox capability. The report includes a host-root receipt, actionable failure reasons and a per-cohort `ready_for_simultaneous_live_desk` indicator. The doctor exits unsuccessfully if prerequisites are not met even where all game files have intact SHA-256 values.

The live operator launcher always checks a minimal sandbox syscall probe before creating any game lane and fails with explicit prerequisite codes. This does not make the native runtime Windows-compatible. Windows still needs its own qualified sandbox or a consciously deployed Linux host. No native cores, licensed ROMs or game behavior were executed by this repository change.

Regression tests: non-Linux host, absent bubblewrap, blocked probe, and source-ready / host-unlaunchable separation. Tests added, not locally executed during the GitHub source editing pass.
