# Playable campaign acceptance

`python -m skeleton scene-survival-campaign-accept demo` executes the
complete original two-stage survival game, verifies the exact action
sequence and stage rewards, restarts from a deterministic checkpoint,
imports the final portable save and emits a replay-derived receipt.

Use `run --source-json ... --actions-json ... --checkpoint-at N` to
qualify an authored campaign, then `verify`, `export` and `import` to
recheck the receipt. Incomplete or losing runs cannot receive a winning
acceptance receipt. Every receipt is tied to the exact authored source,
journal, checkpoint, final state, earned score and portable bundle.

This is functional acceptance only. The receipt is not a cryptographic
signature, ownership attestation, security approval or release certificate.
