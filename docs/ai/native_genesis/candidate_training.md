# Real candidate training and no-promotion guarantee

The genesis checkpoint is an actual, untrained native transformer. It is
generated from an operator-selected architecture, original train-only
vocabulary and explicit random seed, not a downloaded model or echoed answer.

A separate call constructs the candidate training plan with the genesis
model SHA-256, tokenizer SHA-256, source lineage, training code digest,
optimizer limits and candidate-only status. This feeds the existing
`native_candidate.CandidateTrainer` implementation.

The trainer independently restores the genesis checkpoint into a separate
transformer object. Only that clone receives gradient updates. It checks
actual native `fit` step counts, batch source hashes, wall limits,
post-training finite-model restoration and champion immutability. The output
is a new candidate checkpoint, never a hot-swapped serving model.

The source-only doctor does **not** execute SGD and therefore reports
`weights_trained=false`. The two-token native smoke test does real
inference but does **not** train. The real training result is reportable
only after `CandidateTrainer.train()` completes, produces changed model
weights and yields a verifiable content-addressed checkpoint.

If candidate quality is poor, that is a measurable result, not a reason
to bypass the independent evaluation gates. This is an original foundational
transformer and is not represented as a frontier-class pretrained LLM.
