# Operator Quickstart — Pareto path

Fastest path from idea to structured package.

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

## 3. Data corpora
- `data/game_building/` — Pareto patterns + math/physics
- `data/game_data_v2/` — assets, mechanics, UX, music direction, logic, self-improvement
- `data/conversational/` — model conversational patterns

## 4. Rules
- Data-only in these layers
- Operator approves installs, BIOS, content, native tests
- Prefer vertical slice before full production
- Every critical puzzle needs a visible clue and hint ladder

## 5. Next
Expand via adventure or full creation tools. Run fairness and design checklists. Target a qualified core only after operator approval.
