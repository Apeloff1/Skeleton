# Offline scene weather and travel collision

`python -m skeleton scene-weather demo` plays an original weather-gated
Lantern Hollow journey through the canonical scene engine. The authored
weather cycle can contain clear, rain, storm or fog. A weather gate names
an existing scene exit and one or more conditions that temporarily block
that exit. Each legal `scene` action is executed by the canonical scene
travel engine, retaining item requirements, scene transitions and endings.

The additional `wait` action advances weather without inventing scene
items, bypassing collision or granting an ending. Waits and scene actions
share the authored world step budget. The overlay persists a source-bound
nested scene snapshot, ordered action journal, event bus digest and
parent-linked save receipts. A resumed save is replayed from the original
source before accepting any new action.

Use `scene-weather simulate --source-json '<source>' --actions-json
'<actions>'`, `scene-weather verify --session-json '<save>'`, and
`scene-weather resume --session-json '<save>' --actions-json '<actions>'`.
Weather source objects require exactly schema_version, world, cycle and
blocked_exits; rules require exactly scene_id, exit_id and conditions.
All input and output are bounded JSON; no scripts or network are executed.
The receipts detect drift but do not authenticate author identity.
