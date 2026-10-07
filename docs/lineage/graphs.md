# Graphs 1.2 (GB-18)

Parent #80. Wave 3 adapter. Facade only.

## Artifact not copied

- `artifacts/Graphs/` is not in git.
- No multiplex vendor dump.
- HTTP stays on the existing API port. Ports 8792-8796 are not opened.

## Public card

- House vertices == 27.
- Spectral card carries lambda_max and Fiedler.
- Unit path flow is conserved (Kirchhoff residual 0).
- Motif card counts wedges and triangles.
- GAT-lite rows are stochastic.
- `mermaid()` and `dot()` are non-empty.
- Every card has `stored_prose=0`.
- `capabilities()` exposes owner, contract, failure_modes, obs, security.

## Accept

`python -m unittest tests.test_gb18_graphs -v`

`python scripts/check_graphs.py` exits 0.

Import stays network-free. No torch.
