# Wave 26 — Unity and USD source-only scene graphs

Canonical Dragon source extraction now builds bounded parent-child
structural graphs for Unity Transform/RectTransform fileID references
and nested ASCII USD prim declarations. Both use the same deterministic
scene topology kernel delivered in Wave 25.

Unity never constructs YAML objects, instantiates MonoBehaviour classes or
loads prefabs. Unknown local parent references remain explicitly unresolved.
Duplicate identities, cycles and self-parenting are refused.
USD parses finite local prim and brace hierarchy; reference composition,
payload loading and foreign schemas remain inert. Unsupported syntax is
not misrepresented as validated structural metadata.

Every captured scene remains unreviewed external evidence. Original
consent, robots, source-use policy, DNS, request and byte budgets and
versioned snapshot custody remain authoritative. These graph sketches
grant no game building, external asset reuse, runtime or training rights.

Source-only tests exercise exact parent/child counts, depth, cycles,
unresolved external parents and canonical run_slice/replay with no
unsolicited network request. Device/runtime and full release gates are
separate and remain unqualified.
