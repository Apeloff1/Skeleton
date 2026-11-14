# Native SFT operator runbook

## Source inventory

Run the package entry point with --inventory to confirm 768 independent
evaluation cases, 32 fixed domains and the separate original training
source identity. The inventory path does not allocate model tensors or
simulate model output.

Next use --doctor --approve-candidate-only. The doctor verifies original
training rights, independent answer checks, train/validation/holdout
partition isolation, tokenizer vocabulary fitting, model capacity,
challenge integrity and exact source overlap. It creates no weights.

## Initial checkpoint

Prepare an owner-private POSIX directory under a trusted parent, such as
a private subdirectory of the operator's home. Source and architecture
identity must be reviewed. --bootstrap --approve-candidate-only
--genesis-directory PATH generates actual seeded transformer weights,
restores them to verify identity, and publishes an immutable source-bound
checkpoint. This is initialization, not training.

## Real training

Prepare a different owner-private candidate directory and a model-scoped
lock directory. Use --train --approve-candidate-only
--candidate-directory PATH --state-directory PATH. The operator may
supply a bounded epoch, optimizer-step, learning-rate and wall-time policy.

The operation clones the initialized model. It constructs all response-only
gradient windows before mutation, checks the step budget and token coverage,
then executes actual CPU native SGD. Initial and epoch validation losses
come from actual logits. A candidate requires improved validation loss,
an independently restorable checkpoint, preserved tokenizer identity and
unchanged original champion weights.

A failed run returns held status. A missing or partial checkpoint must
not be retried blindly, overwritten or promoted.

## Real independent evaluation

--probe requires a trusted candidate directory, checkpoint hash, model
hash and tokenizer hash. --case-start and --case-count select a bounded
source segment. A default segment covers a single 24-case domain.

Repeat over the 32 source domains, then stitch only gap-free results
with identical source/model identity. Independent reexecution verifies
stable inference receipts for each evaluated case. Actual timing is
measured but not compared as part of deterministic replay.

--compare additionally requires a separately pinned champion model and
checkpoint. The same source IDs must be evaluated on both models.
Critical-case regression remains an explicit hold. A positive overall
score cannot independently authorize activation.

## Review

Keep candidate-only status through human/source rights review, source
contamination review, heldout challenge accuracy, rollback testing,
device qualification and final Git commit CI. Do not treat an older
passed workflow, a skipped test or a cancelled run as a green gate.
