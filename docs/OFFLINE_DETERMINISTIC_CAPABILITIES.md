# Standalone deterministic capabilities — October 2026

**Scope:** 29 built-in, typed, bounded local computations plus a
32-node deterministic dependency graph. This extends the functional
abilities of Skeleton's standalone AI without collecting new training
examples, training a transformer, trusting internet content or granting
tool execution authority.

**Release status:** Committed to PR #3593; exact-head CI and real Windows
installer acceptance are required before signoff. The underlying methods
are deterministic algorithms, **not** generative-language proficiency.

## Two independent execution planes

1. **Model inference:** Native checkpoints or operator-provided GGUF
   deployments generate text and require separate model/runtime trust,
   context persistence and target-hardware qualification.
2. **Deterministic capability execution:** Strict JSON task dispatch to an
   explicit allowlist of 24 operations, each with closed-form or bounded
   calculations, no model dependency and a SHA-256 result receipt.

A model may *propose* a JSON task, but its text is never sufficient
authorization for filesystem access, network fetch, subprocess execution,
credential access or package installation. An external trusted authority
must still validate any proposed task and explicit permissions. The
capability engine implements no such I/O operations.

## Single-operation API

A user-selected file \`task.json\` might contain:

\`\`\`json
{
  "operation": "grid.shortest_path",
  "args": {
    "start": {"x": 0, "y": 0},
    "goal": {"x": 3, "y": 0},
    "width": 4,
    "height": 4,
    "blocked": [{"x": 1, "y": 0}, {"x": 2, "y": 0}]
  }
}
\`\`\`

\`\`\`sh
SkeletonOffline.exe --capability-list --json
SkeletonOffline.exe --capability-file task.json --json
python -m skeleton app local-ai --capability-file task.json --json
\`\`\`

The example shortest-path result is 5 steps over 6 visited cells.
Results include the operation identity, result SHA-256, deterministic
execution receipt and explicit false flags for model inference,
network/filesystem access and authority granting.

### Operation catalog

| Domain | Operations |
| --- | --- |
| Arithmetic | \`math.add\`, \`math.multiply\`, \`math.sum\` |
| Grid navigation | \`grid.move\`, \`grid.neighbors\`, \`grid.manhattan\`, \`grid.shortest_path\` |
| Simulation | \`physics.advance_1d\`, \`physics.integrate_2d\` |
| Geometry | \`collision.aabb\`, \`collision.point_rect\` |
| Game logic | \`state.transition\`, \`inventory.update\`, \`game.damage\`, \`game.coins\`, \`game.cooldown\`, \`game.animation_frame\` |
| Events | \`events.order\`, \`events.elapsed\` |
| Structured content | \`json.select\`, \`text.normalize\`, \`evidence.lookup\`, \`content.sha256\` |
| Policy recommendation | \`policy.local_action\` |

Geometry uses half-open boxes so sharing only a boundary does not count
as overlap. Grid search uses deterministic breadth-first traversal
with fixed neighbor order and bounded 32x32 dimensions. Integer
motion/physics uses fixed-tick arithmetic; the 2D update is
semi-implicit (symplectic) Euler with a closed-form discrete sum,
not continuous physics.

The \`policy.local_action\` result deliberately has two different
fields: \`policy_allow\` is a theoretical local policy recommendation,
and \`executor_permission_granted\` is **always false**. A claimed
operator-selected flag is not actual OS permission.

## Multi-step capability graph

For fully specified game calculations, submit one bounded typed DAG:

\`\`\`json
{
  "schema_version": "skeleton.offline_capability_graph.v1",
  "nodes": [
    {
      "id": "health",
      "operation": "game.damage",
      "args": {"health": 20, "damage": 7}
    },
    {
      "id": "points",
      "operation": "game.coins",
      "args": {"coins": 3, "points_per_coin": 5}
    },
    {
      "id": "score",
      "operation": "math.add",
      "args": {
        "a": {"$ref": "health"},
        "b": {"$ref": "points"}
      }
    }
  ],
  "outputs": ["score"]
}
\`\`\`

\`\`\`sh
SkeletonOffline.exe --capability-graph-file gameplay.json --json
python -m skeleton app local-ai --capability-graph-file gameplay.json --json
\`\`\`

The output is \`score=28\`. Object/list subfields can be selected
with a typed \`{"$ref":"prior-node","path":["position","x"]}\`
reference. References can target **only earlier nodes**; forward links,
self-links, cycles, duplicate identities, unrecognized operations,
unbounded nesting and malformed arguments fail closed. Nodes produce
their own operation and result hash, and the graph has a canonical
content hash for replay comparison.

### Resource controls and boundaries

| Control | Limit |
| --- | ---: |
| Single task JSON input | 8 KiB |
| Single operation receipt | 32 KiB |
| Graph input and cumulative resolved arguments | 64 KiB each |
| Graph output receipt | 64 KiB |
| Graph nodes | 32 |
| Grid dimensions | 32x32 |
| Per-source numerical input | Bounded integers, usually within +/-1,000,000 |
| Full model inference or training during task execution | None |

Output sizes limit long paths; inputs outside the exact schema are
rejected rather than silently coerced. The graph does **not** support
loops, script execution, user-provided callable functions, plugin
imports, network URLs, shell commands or file-writing tools.

A deterministic result means that the same admitted input produces the
same arithmetic output. It does **not** certify the semantics of a
generative interpretation of a user's request, trust in external source
content, formal proof of implementation, or whole-host airgapping.

## Sparse training and actual hardware information

The active supervised training curriculum is **36 examples by default**
for 36 task modes, optionally 48 or 72 with explicit resource-policy
profiles. The existing 720-example reference bank is not automatically
trained on. No new training records are created by the capability engine.

\`scripts/training/sparse_capability.py --profile auto\` uses a
read-only local resource probe:

- Linux: free memory from \`/proc/meminfo\`, cgroup memory budget and
  CPU affinity/quota where available.
- Windows: native \`GlobalMemoryStatusEx\` total/available RAM and
  logical CPUs without a PowerShell subprocess.
- macOS and uncertain environments: do **not** treat installed physical
  RAM as free memory; default to the smallest sample profile until
  reliable available-memory measurements are established.

This is a dataset preparation policy only. Real training still requires
measurement of checkpoint, activations, optimizer memory, accelerator
support, throughput, thermal constraints and held-out proficiency.

## Adversarial verification

The focused P2 Local Inference workflow includes operation-by-operation
tests, randomized motion reference checks, pathfinding and collision
edge cases, ambiguous/duplicate JSON rejection, invalid Unicode,
reference bounds, DAG cycles, typed path validation, strict mode
separation and no-data-growth checks.

The Windows installer workflow also exercises the **installed frozen
console**, including one pathfinding task, one 3-node gameplay DAG,
and negative duplicate-key/self-reference cases. A queued workflow is
not equivalent to a passing test; rely on an exact-head successful CI
verdict before release.
