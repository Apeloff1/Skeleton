# Reviewed original accessible narrative and keyboard gameplay

This Studio A vertical adds authored scene summaries, descriptive action
labels, ending explanations and semantic offline HTML5 playback. It is not
a blanket accessibility certification. Every canonical scene, choice and
ending must have exactly one accessible descriptor in sorted ID order.
Duplicate action descriptions at one scene are rejected to prevent
ambiguous navigation. The source is leased to the exact canonical world
digest; a world revision invalidates the lease.

User prompt and authored descriptors become a typed unapproved proposal.
The operator `python -m skeleton world-accessibility --store DIR` supports
propose (with scenes-json, choices-json, endings-json), inspect, save,
edit, approve, editor, compile, verify, player and player-slot.
Every persisted edit revokes approval. The offline editor exports only
unapproved JSON; CLI revalidates before saving. Source custody uses
descriptor-anchored locks, compare-and-swap digests and exact artifact
verification. Jeeves tool previews are read-only.

The playable uses native buttons, keyboard focus restored to the scene
heading, aria-live narrative, textContent and a CSP-hashed script. No
network, external assets or dynamic HTML injection is allowed. The
proof records complete source coverage and canonical ending witnesses.

Focused regression: `python -m pytest skeleton/testing/test_jeeves_world_accessibility.py -q`.
No screen-reader, device or release certification is claimed.

Scene landmark metadata is applied to the rendered narration: a region
landmark produces an explicitly named ARIA region, while main narration
remains within the primary document landmark.
