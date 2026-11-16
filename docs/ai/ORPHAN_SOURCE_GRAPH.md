# Source graph orphan recovery

The installed command `python -m skeleton orphan-source-graph --root .`
enumerates local Python source without importing it. It seeds possible
reachability from both package metadata formats and the root package and
CLI. Additional service or application roots may be supplied explicitly
with repeated --entry options. Production test directories are excluded.
Absolute, relative, package initializer and recognized literal dynamic
imports contribute edges; unresolved computed calls are counted. A
missing root, ambiguous source identity, unreadable file, skipped link,
metadata drift or inventory ceiling is visible as incomplete evidence.

The planner condenses cycles into indivisible components and orders the
unreferenced component DAG dependency-first. Component IDs, source hashes,
graph, roots and plan are deterministic; output may be truncated without
changing the complete plan digest. Byte-identical groups are discovery
leads, not authorization to collapse mirrored modules or change ownership.
The graph is a conservative static model: a conditional import is not
runtime reachability, dynamic plugins and backend/frontend consumers may
not be detected, and an unreferenced candidate is not proof of an orphan.
Use explicit domain roots and review owner boundaries before integrating.
No source modules are executed or modified. This is a trusted-checkout
audit, not filesystem isolation or an atomic snapshot.

The same package now recognizes independently pinned portfolio receipts
in the existing archive inspector; inspection proves historical bytes,
not fresh source replay. All runtime, native, release and merge holds
remain in force.
