# Dragon/Jeeves milestone — signed canary releases and independent regression watch

**Timestamp:** 2026-10-12 UTC · **PR:** #3605 · **Branch:** `feat/dragon-wisdom-review-20261010`

## Real retrieval-weight canary, not a simulated animation

`DragonWeightCanary` reads two **already approved, still-unexpired and HMAC-verified** retrieval versions from `DragonDurableWeightVault`: current candidate and immediately previous control. A separately signed operator canary plan identifies their exact index digests, owner, trusted operator/key, 1–25% traffic share, minimum paired evidence count, maximum latency ratio and bounded expiration. Each caller passes a privacy-preserving SHA-256 cohort digest; deterministic hashing ensures the same cohort consistently receives the same version while the plan remains active. The chosen result is routed through the real approved index, not merely labeled as a candidate. Raw user identifiers and query text are not stored in canary telemetry.

The canary cannot activate a new index, create model training data, mint XP, issue crawler rights, bypass the existing 100 mother matrices, or turn a successful canary into a global rollout on its own.

## Paired post-release evidence and emergency halt

A separately trusted Ed25519 assessor signs each unique paired result, binding owner, canary plan digest, hashed test-case identity, task family, source-group digest, baseline/candidate correctness, measured per-case latency, and observation time. The governor durably stores only the canonical signed outcome and an independent operator-owned HMAC. The signed plan and every stored sample are reverified on reads and process restart.

The candidate exposure stops **immediately at the next request** after any independently attested previously-correct case becomes incorrect or any paired candidate latency exceeds the plan's maximum ratio. Once halted, all canary-routed requests go to the previously approved control version. It also stops if the signed plan expires or the approved index versions no longer match the live verified vault.

If enough genuine paired observations exist (minimum 12, 3 task families, 3 source groups, 2 newly correct tasks, 0 regressions), the canary becomes `ready_for_operator_review`; this status does not change exposure to 100% or issue neural-weight authorization.

## Performance and safety

The read path uses bounded, immutable term postings from either current or prior vault generation. The custody ledger is verified on each route, so cross-process tampering is detectable even though verification incurs overhead. The workflow is optimized for correctness and trustworthy rollback, not claimed to achieve an unmeasured sub-millisecond performance target.

## Tests

The Dragon Source Safety suite tests actual candidate/control selection across multiple cohort digests, paired correctness gains, 12-case operator readiness, restart/reconstruction from the same SQLite database, refusal of duplicate or forged observations, tampered telemetry, incorrect operator keys, expiry, irreversible halt on signed factual or latency regressions, and signed rollback to the prior index.

**2026-10-12 UTC improvements:** (stable canary exposure across real approved index versions); (signed post-release quality feedback); (automatic candidate-exposure halt); (durable restart-safe audit); (no unauthorized full rollout).
