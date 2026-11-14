# Studio cross-section continuity audit

The canonical eight-section studio design input is now checked for **internal
causal consistency**, independently of the current HTML5 preview compiler.

It validates that each authored scene binds exactly one real quest stage in
order, each stage has a legal authored choice and acyclic prerequisites, its
dialogue hooks refer to existing cast IDs, its art/audio requirements are
present, and all QA/release gates remain explicitly untested. Narrative ending
predicates without playable causal proof are reported as unresolved rather
than silently accepted.

```python
from skeleton.ai.game_builder.studio_ecosystem_continuity import audit_catalog_continuity
report = audit_catalog_continuity("studio_arena_fighting_glacial_fjord")
assert report["source_consistent"]
assert not report["release_certified"]
print(report["unbound_ending_predicates"])
```

Source consistency is **not** evidence of real game-genre execution, actual
asset creation, multiplayer qualification, external witness testimony, or
device readiness. No runtime publishing permission is granted.
