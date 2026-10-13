# Advanced original Dialogue & Social Choice engine

**12 October 2026 UTC.** Stacked on voxel PR #3713 and game-builder #3642.

A bounded original role-playing dialogue engine now executes source-authored witness
conversations. NPCs have individual trust, memory and testimony; the player must
earn disclosure, ask the correct topic, listen, record, and independently verify
at least two distinct first-hand witnesses before a nonterminal event/quest unlock.
Choices affect trust and reputation, gifts consume finite stock, conversation
consumes stamina, and testimony has strict evidence custody and replay provenance.

Authored scenes validate exact speaker counts, factual claims in the *fictional
game world*, title, venue and finite original text. Fictional truth labels do NOT
fact-check real-world sources. No scraped dialogue or third-party story assets
are imported. Source commits still require the existing local human approval.

This is advanced Python reference gameplay (not voice synthesis, a general
language model, a Godot implementation, a commercial native binary or an
unbounded 500-speaker active simulation). At most eight speakers are modeled
actively; background population is represented explicitly. Native and platform
certification stay false until separately verified.

Example:
  python -m skeleton.ai.game_builder.system_editor_cli play --editor dialogue --seed 3 --actions steps.json
  python -m unittest tests.test_game_builder_advanced_dialogue -v

Proposed total advanced reference families: 31 / 43, pending exact-head
Windows/Ubuntu regression evidence. No release or merge sign-off is claimed.
