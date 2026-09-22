# Capability index (GB-36)

Parent #80. One registry. Empty is legal.

## Placement

- `skeleton/frontier/capabilities.py`
- Does not fork #81.
- Does not edit `skeleton/architecture_index.py` (#1908 occupied).

## Public card

- Lazy-import Wave 3 adapters.
- Each card has owner, contract, failure_modes, obs, security.
- Missing layers are skipped.

## Accept

`python -m unittest tests.test_gb36_capabilities -v`

`python scripts/check_capabilities.py` exits 0.
