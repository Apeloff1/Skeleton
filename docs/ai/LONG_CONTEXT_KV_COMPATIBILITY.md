# Generation-fenced CPU KV layout compatibility

`LongContextKvCompatibility` reads the current durable stream head using
`compare_window`, checks its canonical record digest and generation, checks
the canonical token-window digest, bounds token IDs against the declared
vocabulary, and computes the worst-case KV footprint for the **prefix through
the window stop**. The operator CLI `head-kv-observe` exposes the same
payload-free diagnostic.

This verifies **declared layout compatibility only**. It does not inspect
actual KV tensors, attest the live tokenizer state or model weights, grant
execution, authorize a principal, allocate RAM, qualify GPU/Metal, or persist
a cache. GPU and M-chip requests explicitly hold. A CPU-compatible receipt
still requires backend identity, actual memory reservation, pressure guards,
head revalidation, and durable execution accounting. The observation digest
is unkeyed and never an authenticity proof.

Focused tests:
`python -m unittest tests.flgb.test_long_context_kv_compatibility`.
Release remains held pending exact-head checks and real device validation.
