# Sheaf 1.1 (GB-19)

Parent #80. Wave 3 adapter. Facade only.

## Artifact not copied

- `artifacts/Sheaf/` is not in git.
- Ports 8792-8796 are not opened.

## Public card

- Cover has 12 opens.
- Restriction is exact: r composed r equals the direct restriction.
- Glue skips cite/feed cycles.
- Stalk at a site is the germ over opens containing the site.
- Cech H0 = 1 and H1 = 1 for the constant sheaf on the cycle nerve.
- Nerve 1-skeleton is a 12-cycle.
- Every card has `stored_prose=0`.
- `capabilities()` exposes owner, contract, failure_modes, obs, security.

## Accept

`python -m unittest tests.test_gb19_sheaf -v`

`python scripts/check_sheaf.py` exits 0.
