# Meticulous Adventure Game Design Frameworks

## Core systems (10× depth)
- **Room graph**: Explicit connectivity, gated exits, on-enter scripts, hotspot density balanced for readability.
- **Inventory + state machines**: Items have states; combinations are enumerated, never free-parsed. Feedback is immediate and visual/audio.
- **Puzzle ladder**: Observable clue → item/state requirement → application → flag reward. Three hint levels minimum (environmental, social, direct).
- **Dialogue with flags**: Nodes check and set adventure flags. No orphan branches. Character voice consistent.
- **Save/flag model**: All progress is flag- or item-state driven so it serializes cleanly.

## Adventure-specific pillars
1. Environmental storytelling first.
2. Fairness: every solution is clued in the world.
3. Strong verb/hotspot feedback (highlight, sound, text).
4. Era-authentic pacing and presentation.
5. No soft-locks; critical path always recoverable.

## Quality bar beyond prior pipelines
- Every room has lighting, audio bed, and interactive vs scenic distinction.
- Every item has material description and silhouette note.
- Every puzzle has explicit solution steps and hint ladder.
- Asset specs name palette size, sprite limits, and animation frame budgets per era.
