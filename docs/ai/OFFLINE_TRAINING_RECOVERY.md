# Offline training and capability-evaluation recovery

**Date:** 2026-10-13  
**Source identity:** PR #3593, commit `7f9be557bac3a4108dfc683716b15437de30f547`  
**Integration:** fresh `main`-based branch, additive files only

The original algorithmically synthetic `offline_foundations_v1` curriculum is
recovered with its SHA-bound manifest, held-out train/validation/test splits,
and reproducible training corpus. This does not include third-party scraped
material, licensed game code, private player data, or already trained weights.

The corresponding learning and evaluation contracts cover original synthetic
example generation, independent curriculum verification, sparse capability
probes, resource admission, and durable capability evidence bookkeeping. CLI
scripts allow local execution without uploading prompts or data to a provider.
The source-pinned regression tests cover held-out samples, generated corpus
identities, false capability inflation, resource budgeting and ledger receipts.

## What this is not

- No claim of new model weights, frontier-model training, a functional
  auto-improving model, or safe hyperweight promotion.
- A closed-loop promotion decision still needs independent baseline/model
  quality evidence; passing deterministic synthetic examples alone cannot
  justify changing production parameters.
- The `manifest.json` declares the data to be original synthetic content;
  its `license_id` is null and an independent legal review has not been
  completed. A content hash protects integrity, not provenance authenticity.
- This tranche does not replace or update any current-main inference engine,
  online crawler, model weights, or scheduler.

Run exact-head functional and security/packaging CI before asserting verified
full app readiness. Modules and fixture data were copied without modification
from the pinned source, rather than overwritten onto newer `main` files.
