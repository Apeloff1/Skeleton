# Compile steps for another agent

Target repo: `Apeloff1/Skeleton`. Branch: `ai-tree/capability-fill-1.8.0`. Do not merge.

1. Copy `ai_tree_fill/` to `contrib/ai-tree-fill/ai_tree_fill/`. Do not overwrite `skeleton/ai/capability_map.py`. That file stays the schema owner.
2. Add a facade only:

```python
# skeleton/ai/tree_fill.py
"""Non-owning facade. Bodies live in contrib/ai-tree-fill."""
from importlib import import_module

def load():
    return import_module("ai_tree_fill")
```

3. Run `python3 -m unittest tests.test_tree_fill` from this package. Required green:
   - QR reconstructs to 1e-6
   - CG solves the 2x2 SPD system
   - bare sentence raises `stored-prose`
   - empty trajectory raises `gb-16`
   - mass 1.2 on prior 1.0 raises `mass-snowball`
   - unknown organ `hit=0`
   - snapshot 48 available, 0 unavailable
4. Wire evidence into the existing map by calling `probe_all()` and copying `CapabilityEvidence` fields onto the VOL-113 registry. Missing evidence must remain unavailable. Do not default to available.
5. Leave `machine/ai_file_tree.json` ownership as-is until a signed admission claims `contrib/ai-tree-fill`. Unowned tracked files fail closed.
6. Mobile bank stays dark: speculative RAG, SSE, bench GPU, HF import off. Bank card green.
7. Push is review-only. No merge authority from this package.

Capability families: numerics, planes, organs (16), governance, learning. Each descriptor carries owner, contract, failure_modes, obs, security.
