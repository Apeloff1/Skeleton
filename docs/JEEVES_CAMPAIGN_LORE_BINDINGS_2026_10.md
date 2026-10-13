# Game campaign ↔ signed story/cast/plot continuity — October 2026

**DX-119–DX-126:** The working original 2–8-scene campaign runtime now
can link *every* source game scene to a real existing scene in the
canonical 100-chapter/1000-act/9999-scene story history.

Jeeves uses \`load_story_workspace\` to fully verify the underlying
original history before accepting these links. Every game node must have
a unique real authored story source path; never invent missing NPCs,
geography, original dialogue, event backstories or unreviewed locations.

The linkage project source \`game/campaigns/<id>_lore.json\` includes exact
campaign and story source SHA-256; signed bible digest, full story index
digest; scene order, chapter/act/scene, regions, canonical cast and causal
event IDs. It is recomputed on the proposal and the **human actual commit**
boundaries through the canonical existing GameWorkspace.

Supported operations:
\`studio.campaign.lore.plan\`,
\`studio.campaign.lore.stage\`,
\`studio.campaign.lore.verify\`.

This produces real **referential continuity and historical causal
integrity**, rather than a false claim to have fully authored or finished
all plot lines, alternate branch dialogue or original characters.
No game binaries run, and no repository test suites executed in this pass.
