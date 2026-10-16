# Operator Quickstart — Pareto path

This page covers data-only planning helpers. For a running application, start with
[installation](../../README.md#first-install), configure the owner and AI model, then
open Product → Studio → Game learning. A brief or checklist is not a compiled game.

## 1. Unified brief (when facade is available)
```python
from skeleton.ai.agents.jeeves.unified_game_capability import make_unified
u = make_unified()
print(u.quick_brief("My Game", genre="adventure", era="16bit"))
```

## 2. Checklists before any gate
```python
from skeleton.ai.agents.jeeves.actionable_checklists import all_checklists
for name, items in all_checklists().items():
    print(name, len(items))
```

## 3. Optional compressed reference corpora
- `data/game_building/` — Pareto patterns + math/physics
- `data/game_data_v2/` — assets, mechanics, UX, music direction, logic, self-improvement
- `data/conversational/` — model conversational patterns

Stream the `.gz` files and inspect their `manifest.json`; do not concatenate all
variants or count repeated lines as distinct design insights. Dataset admission and
training rights remain separate.

## 4. Rules
- Data-only in these layers
- Operator approves installs, BIOS, content, native tests
- Prefer vertical slice before full production
- Every critical puzzle needs a visible clue and hint ladder

## 5. Next
Expand via adventure or full creation tools. Run fairness and design checklists. Target a qualified core only after operator approval.
