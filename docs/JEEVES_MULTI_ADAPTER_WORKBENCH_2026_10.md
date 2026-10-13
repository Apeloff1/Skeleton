# Jeeves multi-adapter production preview — 13 October 2026

**DX-14: appwide preview composition.** Existing Jeeves editor templates,
editable system previews, RPG/world directors, Universal Forge graph previews,
Dragon companion simulation, crawler planning and registered capability catalogs
can now be composed into one *preflighted*, deterministic \`studio.batch_preview\`
request. It dispatches through the existing Jeeves runtime and produces one
canonical receipt per requested adapter. There is no parallel executor or
new authorization domain.

**DX-15: bounded batch custody.** A batch is restricted to 12 distinct,
allow-listed, read-or-compute actions. Each action is preflighted for effect,
operator gate and active project where needed. Inputs and combined results have
strict UTF-8 byte limits; excessive subresults are omitted with retained
digests, not silently declared complete.

\`\`\`python
from skeleton.ai.game_builder.jeeves_appwide_fabric import JeevesAppwideRuntime

# runtime = JeevesAppwideRuntime(scanned_inventory, workspace=workspace)
receipt = runtime.invoke("studio.batch_preview", {
    "jobs": [
        {"action": "inventory.report", "params": {}},
        {"action": "editor.catalog", "params": {}},
        {"action": "crawler.plan", "params": {"limit": 3}},
    ]
})
\`\`\`

**Limits:** This batch intentionally cannot mutate sources, invoke a tool plan,
trigger compilers, approve outputs, start a crawler, deploy model weights or
change game persistence. Side-effectful release/build actions remain separate
explicitly reviewed canonical operations. No tests were executed in this build.
