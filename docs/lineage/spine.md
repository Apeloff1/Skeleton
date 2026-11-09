# Spine 1.0 (GB-20)

Parent #80 / after #1645 (GB-19 Sheaf). Wave facade only.

## Artifact not copied

- `artifacts/Spine/` is not in git.
- No multiplex vendor dump.
- No touch of `api/server.py` lifespan, security PRs, or `backend/gameforge/persistence/spine.py`.

## Public card

- Vertebrae == 33 (7C+12T+5L+5S+4Co); segments == 32.
- Topology is path-33 (connected, acyclic).
- Articulation is ROM-bounded (6 DOF per mobile segment).
- Axial load path conserves force without body weights; Kirchhoff residual ≈ 0.
- Digests use `spine-blake16` (16 hex); neutral digest is stable.
- Posture builders stay inside ROM.
- Constraint solver projects violations back into ROM.
- Serialize round-trips without digest drift.
- Every card has `stored_prose=0`.
- `capabilities()` exposes owner, contract, failure_modes, obs, security (network=0, torch=0, ace=fail-closed).

## Accept

`PYTHONPATH=. python -m unittest discover -s tests -p 'test_gb20*.py' -v`

`PYTHONPATH=. python scripts/check_spine.py` exits 0.

Import stays network-free. No torch.
