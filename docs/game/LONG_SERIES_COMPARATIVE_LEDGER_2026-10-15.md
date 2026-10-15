# Multi-study historical series library — 2026-10-15

The comparative studio can inspect **2–30 distinct game/emulator variants** per study with **at most ten active native game sessions**. A long-running franchise can be split into many studies, using the same `series_id` and original `release_order`. The cross-study ledger can merge **1–128 completed study reports** (up to 3,840 observed versions) into a human/AI-readable timeline without replaying any game a second time.

The ledger verifies each saved comparative report's exact `result_sha256` before collecting its actually observed checkpoints. It groups by series identifier and release order, keeps same-game emulator variants separate, and records SHA-256 evidence for earlier, middle and after gameplay checkpoints. It preserves linked locally-reviewed viewer, Jeeves and Dragon notes and proposed numerical build parameters without turning hypotheses into ground-truth design coefficients.

Across large series the ledger suggests adjacent-release comparisons as a **research queue**, but marks them `native_pair_comparison_executed: false` until an explicit new comparative native study is run. It never guesses missing installments or declares a complete canon just because indices are contiguous. It does not collect copyrighted ROMs, videos, artwork, dialogue or music. Dragon Family Academy remains the independent, authenticated consent-and-review owner before source adoption or learning-weight promotion.

### Merge previously completed reports

```bash
python3 scripts/merge_game_series_studies.py \
  --result /srv/studies/era_1.result.json \
  --result /srv/studies/era_2.result.json \
  --result /srv/studies/era_3.result.json \
  --output-dir /srv/study-reports
```

Outputs: `game_series_ledger.json` (compact hashed source-series knowledge graph with chronology, receipts and proposed parameters) and `game_series_ledger.html` (offline viewer with collapsible series history, observed title/core variants and review notes).

The 128-report bound is a memory/safety limit on one merge, not a claim that the software knows every existing game. The ledger combines **observations**, not model weights. Reviewed parameters must be separately evaluated and explicitly promoted by their existing owner.

**Remaining:** Operator-approved native cores and lawful ROMs; disc and large multi-file content require the host's existing bounded `GameContentBundle` integration; real gameplay, emulator compatibility and model-weight gain have not been verified in this source pass.
