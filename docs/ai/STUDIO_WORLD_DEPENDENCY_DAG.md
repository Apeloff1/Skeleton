# Canonical world dependency DAG — Studio A

The operator authors a bounded, typed graph of up to eight reviewed world-tool
requests. Each step has a stable identifier and an explicit set of predecessor
step identifiers. A deterministic topological compiler preserves author order
when dependencies do not constrain it; missing predecessors, cycles, duplicate
IDs, duplicate edges, invalid JSON types and unauthorized execution fail closed.

The graph compiles through the existing source-bound read-only world batch
planner and its canonical provenance and catalog leases. It does **not** grant
tool authority, perform arbitrary imports, or claim a native game build.
The compiled plan is executed only through the reviewed world batch router.
Each output is replay-verified against current canonical sources before
immutable private publication. Source drift rejects stale receipts.

CLI:

```sh
python -m scripts.studio_world_dependency_cli \
  --expected-catalog <64-hex-current-world-tool-catalog-digest> \
  --graph '<typed JSON graph>' --html-sha256
```

For persistence, provide an existing owner-private directory with `--publish`.
Use `--restore` and `--expected-catalog` to verify the saved execution.
`--editor-directory` exports the existing CSP-bound plan editor. Editing a
plan in that editor does not mutate the graph's dependency constraints:
recompile an explicitly authored graph to change dependencies.

The static Jeeves tool is `studio_original_world_dependency`. Its request
schema requires `schema`, `expected_catalog_digest`, and `graph`.
The prompt is exactly `compile dependency-ordered original world workflow`.

Run focused tests with
`python -m pytest -q tests/test_studio_world_dependency.py`.
Exact-head integration/security CI is still required. HTML5 quest receipts
are available only when downstream reviewed tools actually produce them.
No native runtime, rights, device, or release qualification is claimed.
