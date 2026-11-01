# Authenticated offline Jeeves world-tool router

A reviewed static registry exposes the existing typed Jeeves original-world
adapters through one source-bound interface. It covers canon proof, story
revision, quest endings, faction consequences, NPC dialogue, guided movement,
the ending atlas, branch impact matrix and objective board.

Discover the exact contracts:

    python -m scripts.studio_world_tool_cli --catalog

Execute one typed JSON envelope:

    printf '%s' '<{"tool":"studio_authored_ending_atlas","arguments":{...}}>' |
      python -m scripts.studio_world_tool_cli --execute-stdin

The placeholder above must be replaced with valid JSON from the catalog.
Each request names a vetted tool and supplies its exact schema. The router
does **not** dynamically import user-provided names, grant authorization from
request fields, accept duplicate JSON keys, or claim native runtime evidence.

Authoring adapters require a separate explicit \`--allow-authoring\` operator
flag; read-only tools do not. This flag does not bypass any underlying source
lease, authorization, private persistence or security check. Tool outputs
carry request/result digests and preserve actual write evidence.

The router is a deterministic typed orchestration boundary, **not** an LLM
provider, permission elevation, game release certificate or external evidence
source. Focused regression:

    pytest -q tests/test_studio_world_tool_router.py
