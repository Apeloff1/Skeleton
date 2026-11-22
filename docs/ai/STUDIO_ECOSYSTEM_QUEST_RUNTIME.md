# Original studio quest-playthrough sandbox

The canonical studio catalog contains authored narrative/quest/scene source,
not real native genre gameplay. The new `studio_ecosystem_quest.py` exercises
quest-stage prerequisites and authored alternative choices for BOTH source
contract variants (`stages` and `stage_graph`) without inventing external
evidence or claiming production certification.

Usage:

```python
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    start_catalog_quest, compile_quest_program, step_quest, quest_progress
)
docs, session = start_catalog_quest("studio_arena_fighting_glacial_fjord", authorized=True)
first = compile_quest_program(docs).stages[0]
session = step_quest(session, docs, stage=first.key,
                     alternative=first.alternatives[0], authorized=True)
print(quest_progress(session, docs))
```

For every action, the runtime checks the exact authoring source hash, replayed
history, prerequisites, membership in available authored alternatives, and
immutable session digest. Stage rewards are explicitly **simulation-only**
tokens; missing external proof stays missing and end-state claims are
`release_certified: false`. No shell, unapproved external provider, file
writes or privileged resource access is introduced. This is not a replacement
for the existing native quest engine or physical evidence/asset rendering.
