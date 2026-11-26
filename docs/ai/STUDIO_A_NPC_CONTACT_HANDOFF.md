# Source-verified NPC contact handoff

The canonical walk receipt is the only source of player position and movement
clock. The authored cast determines the NPC's current patrol coordinate and
knowledge. The hazard simulator must independently confirm that the character
is alive. No generated dialogue, external evidence or native runtime
qualification is claimed.

```sh
python -m scripts.studio_npc_contact_handoff_cli \
  --project ORIGINAL_PROJECT --expected-source SHA256 \
  --session-json 'CANONICAL_WALK_RECEIPT_JSON' \
  --expected-session SESSION_SHA256 --npc-id AUTHOR_NPC_ID \
  --html-sha256 --publish /path/to/private-0700-directory
```

A completed waypoint-to-playable receipt can be supplied instead through
`--walk-handoff-json` and `--expected-prior-session`; it is canonically
replayed before its resulting walk session is admitted for NPC contact.
`--restore` requires the exact resulting session SHA-256 and a private
receipt directory. The read-only Jeeves tool
`studio_original_npc_contact_handoff` accepts the same typed session and
NPC identity, with authorization held out-of-band.

A successful result is **contact eligibility**, not a conversation event.
It carries source-bound authored knowledge and a deterministic proximity
proof, with no fabricated voice, canon change, choice, or NPC autonomy.
