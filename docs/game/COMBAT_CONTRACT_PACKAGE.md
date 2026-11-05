# Portable original combat game packages

Run `python -m skeleton combat-contract-package demo` to create a fully
playable offline game package with original authored source, canonical actions,
replay-verified earned victory, portable save and a deterministic manifest.
`build --source-json JSON --actions-json JSON --metadata-json JSON`
packages another authored contract; `verify --package-json JSON` reconstructs
the entire result; `play --package-json JSON` imports the validated save.

The manifest records package/world/contract IDs, original source digest,
earned credits and items, action count, publisher identifier and a strictly
bounded rights declaration. The declaration is **not** verified legal
provenance, a license grant or publisher authentication. Hashes are integrity
checks, not cryptographic signatures. Unwon contracts, forged credits, altered
source, changed actions and mutated portable saves fail closed.

This packaging vertical is offline, original and bounded. It does not certify
consumer devices, marketplace delivery or any release gate. Tests:
`pytest -q skeleton/testing/test_combat_contract_package.py`.
