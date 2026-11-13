# Verified offline model weight inventory

The CLI `skeleton-local-model-inventory STORE` reads the existing canonical
`WeightShardStore` manifest and physical object layout. It validates every
manifest against the original `WeightLoadPlan` digest and streams each shard
through the canonical SHA-256 and size verifier. It is read-only and does not
download, activate or qualify a model. Output contains only digests, shard
counts, total bytes and an immutable receipt digest; never private paths.

An invalid, missing, symlinked or corrupt manifest or object fails the entire
inventory rather than returning a misleading partial list. The scan has an
operator-bounded entry count and aggregate byte budget. The default is
4096 manifests and the canonical maximum weight byte contract.

Run `python -m skeleton.ai.model_runtime.offline_inventory STORE` or use
the installed CLI entry point. Tests are in
`skeleton/testing/test_offline_weight_inventory.py`.

This verifies local content identity only. Tokenizer compatibility, device
availability, license provenance, model decoding and runtime activation still
require their own checks before inference.
