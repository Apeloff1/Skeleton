# NPC dialogue chain — bounded causal multi-scene quest replay

The operator supplies an existing playable walk receipt, initial canonical quest
actions, and 1–8 original authored NPC/scene/alternative steps. For every step,
the compiler rechecks the player's NPC proximity against the original walk
receipt, compiles the source-authored dialogue card at the **current** quest
digest, and commits exactly one of its previewed alternatives through the
canonical quest engine. The next contact uses the newly advanced quest digest,
not a stale original session. A locked scene, missing NPC, invalid alternative,
source drift or non-causal quest history aborts the entire chain without writes.

The receipt preserves the full final quest action history, ordered per-step
contact/choice digest proofs, source and walk leases, initial/final quest leases,
and explicit non-certification flags. No step claims dialogue was spoken,
native runtime executed, external evidence exists or release is qualified.

The typed Jeeves tool `studio_original_npc_dialogue_chain` requires
out-of-band operator `authorized=True` and router `allow_authoring=True`.
The CLI `scripts/studio_npc_dialogue_chain_cli.py` accepts `--project`,
`--walk-json`, `--steps-json`, optional `--actions-json`, and
`--expected-source`, `--expected-walk`, `--expected-quest`. Optional
`--html-preview` renders escaped, CSP-restricted read-only HTML.
`--publish` exclusively creates a private 0600 receipt in an existing
private directory; `--restore` independently recompiles and verifies it.
Files cannot be overwritten and symlinks, hard links, FIFOs, stale leases,
duplicate JSON keys and untrusted receipt changes fail closed.

The verified `final_quest_actions` and `final_quest_session_digest` are
handoff inputs to the builder/playable engine, not device qualification.
