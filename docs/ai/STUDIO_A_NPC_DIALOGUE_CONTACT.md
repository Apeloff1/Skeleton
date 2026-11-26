# Source-verified playable NPC dialogue contact

This vertical composes the **actual playable walk**, **authored NPC patrol/contact**
and **canonical quest/dialogue replay**. An NPC's original authored dialogue
choices become previewable only when the current player is alive, near that NPC,
the scene belongs to the same NPC, the quest stage is unlocked, and all three
caller-supplied source/walk/quest leases match the canonical replay.

It is a **read-only handoff**: no speech, reward, branch choice, external
evidence, native runtime qualification, or release certification is asserted.
A private JSON receipt can be published without overwrite and restored only
after complete replay. No model-supplied authority, source, or arbitrary Python
import path is trusted.

CLI:

```sh
python -m scripts.studio_npc_dialogue_contact_cli \
  --project ORIGINAL_PROJECT --expected-source SOURCE_SHA256 \
  --expected-walk WALK_SHA256 --expected-quest QUEST_SHA256 \
  --walk-json WALK_RECEIPT_JSON --npc-id AUTHOR_NPC \
  --scene-id AUTHOR_SCENE --quest-actions '[]'
```

Use `--publish PRIVATE_EXISTING_DIRECTORY` to persist, then `--restore`
with the three leases to verify the exact saved source and session. The
Jeeves allowlisted tool is `studio_original_npc_dialogue_contact`; its
out-of-band `authorized` argument cannot be provided by a model request.

Regression contract: `tests/test_studio_npc_dialogue_contact.py`. The
deterministic tests cover valid replay, wrong NPC, locked scene, authored
knowledge drift, missing alternatives, stale lease, forged receipt, bounded
input, private no-overwrite publication, duplicate JSON, symlink refusal,
CLI and Jeeves router parity. This feature is not device/release qualified.
