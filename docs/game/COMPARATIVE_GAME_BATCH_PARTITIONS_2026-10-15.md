# Safe 30-game, three-cohort output partitions — 2026-10-15

One comparative study supports up to thirty game variants, at most ten live native emulator sessions. For a plan with `max_active=10`, executing `--batch 0`, `--batch 1` and `--batch 2` now writes **different** evidence and viewer files:

- `<study_id>.batch-0.result.json`, `<study_id>.batch-0.viewer.html`, `<study_id>.batch-0.dragon-intake.json`
- `<study_id>.batch-1.result.json`, `<study_id>.batch-1.viewer.html`, `<study_id>.batch-1.dragon-intake.json`
- `<study_id>.batch-2.result.json`, `<study_id>.batch-2.viewer.html`, `<study_id>.batch-2.dragon-intake.json`

`<study_id>.plan.json` remains shared and stable. Omitting `--batch` executes the full study sequentially in bounded cohorts and writes the unpartitioned result.

Merge three separately completed cohorts using:

```bash
python3 scripts/merge_game_series_studies.py \
  --result /srv/reports/example.batch-0.result.json \
  --result /srv/reports/example.batch-1.result.json \
  --result /srv/reports/example.batch-2.result.json \
  --output-dir /srv/reports
```

The long-series ledger checks every exact report digest, distinguishes source partitions and prevents duplicate game observations from being counted twice when both a full-study and batch result were supplied. A conflicting ROM/core digest under the same study/game identity is rejected, not treated as fresh training evidence. The outputs contain evidence, not ROM or BIOS bytes. No actual games or model training were run during this repository patch.
