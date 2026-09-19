# Primitives 1.1 (GB-17)

Parent #80. Wave 3 adapter. Facade only.

## Artifact not copied

- `artifacts/Primitives/` is not in git.
- `artifacts/Viscera/` is not imported.
- No vendor dump.

## Public card

- `kind_count() == 12` and stays 12.
- Kinds: bond quench witness gossip fork house compact silu gelu rms_norm ring merkle.
- `Ring` cap 24.
- Merkle root present; proof verifies.
- `viscera_card(G, law, cite, root)` is thin. `skeleton.viscera` is not imported.
- Every card has `stored_prose=0`.
- `capabilities()` exposes owner, contract, failure_modes, obs, security.

## Files not copied

The artifact tree under `artifacts/Primitives` stays off main. This packet ships the facade in `skeleton/primitives/` plus this lineage note and tests.

## Accept

`python -m unittest tests.test_gb17_primitives -v`

`python scripts/check_primitives.py` exits 0.

Import of `skeleton` stays network-free. This packet does not add HF or torch.
