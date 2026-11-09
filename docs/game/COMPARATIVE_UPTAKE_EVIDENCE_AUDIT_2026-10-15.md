# Dragon/Jeeves learning uptake with native hash-chain verification — 2026-10-15

The comparative game studio now computes a **typed learning-uptake audit** and includes its receipt in the offline user-visible comparison, as well as the pending Dragon intake envelope.

For every actually observed game, `game_comparison_uptake.py` recalculates the entire ≤64-step native action evidence chain over policy action, real video/PCM hashes, transition identity and objective telemetry. It then verifies that the earlier/middle/after observation receipts match the exact source native step, frame, audio and chosen action. A changed row or misbound checkpoint fails the audit rather than being quietly counted as learning.

The resulting audit keeps five categories explicitly separate:

1. **Actual native observation:** game count and hash-reverified steps.
2. **Locally reviewed knowledge candidates:** attributed viewer/Jeeves/Dragon notes and attached stage receipts. Local review is not independent validation.
3. **Real study-local Q learning:** isolated per-game Q-table update count and exact resulting Q-policy SHA-256 if explicitly authorized and successfully trained by the existing Jeeves learning owner.
4. **Held-out measured improvement:** zero unless a separate, actual independent holdout evaluation establishes it; this module cannot infer learning benefit from visual differences.
5. **Production large-model weights:** unchanged; cross-game weight promotion always requires independent source rights/consent, held-out performance, adversarial checks and user authorization.

The offline HTML comparison viewer shows a compact summary of those five levels and the uptake digest, alongside controller panels, graphs, notes and full event receipts. The Dragon comparative intake carries the same audit identity, counts and promotion gates but **does not adopt reviewed notes into authoritative memory or train its weights**.

Contract tests are added in `tests/test_game_comparison_uptake.py` (using synthetic fixtures) to check intact chains and reject tampered image/step receipts. Live emulator execution, held-out evaluation and model-weight gain have not been performed in this change.
