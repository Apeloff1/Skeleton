# Resource budgets and pre-allocation holds

Genesis policy enforces bounded input dimensions for the model architecture,
native vocabulary, training steps, token coverage, immutable checkpoint
size and wall-clock runtime. The memory estimator runs before any tensor
allocation and conservatively budgets embeddings, projection matrices,
layer norms, FFNs, activations and Python storage overhead.

The prediction is a **capacity estimate**, not a profiler measurement.
It rejects over-budget configurations rather than allocating an enormous
model and hoping an exception provides admission.

After construction, the actual native runtime publishes its logical model
byte size, exact architecture and tokenizer digest. The checkpoint is
serialized and checked against an explicit byte ceiling, then independently
restored before publication. Mismatched model or tokenizer identities are
fatal.

The train bridge is single-use and acquires a model-scoped POSIX process
fence. The trainer counts actual optimizer updates, verifies batch receipts
and refuses a mismatch against preflight-tokenized step estimates. A
post-gradient failure is ambiguous; it must not quietly retry and
duplicate optimization or replace an immutable artifact.

This design does not attest GPU memory, thermal stability, laptop battery,
CUDA device parity, Windows driver support or physical inference latency.
Only a tested device can provide those qualifications.
