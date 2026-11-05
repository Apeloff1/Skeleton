# Native candidate training — real offline optimizer, candidate-only output

This layer extends the existing Skeleton TinyTransformer SGD implementation. It
does not create a competing inference backend or modify the serving champion.

**Implemented:** 576 original, explicitly scoped training examples across 24
non-game AI domains; deterministic 432/72/72 train/validation/holdout splits;
independent source-answer oracles; finite operator-controlled optimizer budgets;
native tokenizer-compatibility admission; copied checkpoint SGD with per-batch
source receipts; model-scoped POSIX process fencing; immutable private candidate
checkpoint output; authenticated SQLite event ledger; candidate publication
outbox; and genuinely generated native validation and holdout measurements.

**Separate control surface:** 288 source-bound adversarial admission vectors
across 12 domains. These measure actual policy code, not model intelligence.

Training source records do not establish learned capability. Real training
requires an operator-provided approved checkpoint and hardware. Model results
do not authorize serving activation, promotion, release or merge.

Run static source inspection and native generation qualification separately.
