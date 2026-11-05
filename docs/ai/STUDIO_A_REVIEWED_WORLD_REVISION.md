# Reviewed original-world revision impact

This is a source-bound, field-level change review between a preserved original
world and the current canonical world. Both are independently proved. The
report identifies added/removed/modified scenes, choices, endings and top-level
authoring fields, and classifies causal effects separately from presentation.
A source digest and exact ending witness inventory anchor each comparison.

Use `python -m skeleton world-revision --store PRIVATE preview --world-id isles --old-world-file OLD.json`.
Review the result and retain its `impact_digest`. To publish an operator
reviewed source-bound HTML5 playable plus impact report, use
`python -m skeleton world-revision --store PRIVATE review --world-id isles --old-world-file OLD.json --expected-impact-digest DIGEST --review-note "Reviewed"`.
Verify with the same old source and `world-revision verify`.

The old source is read through a bounded no-symlink import. The current world
is re-read under an exclusive descriptor-anchored lease. An optimistic digest
rejects a revised world or changed impact. Receipt publication happens last;
verification recomputes both exact artifacts. Reports include field names and
identifiers, never private narrative prose. An impact review is **not** a
signature, a gameplay balancing certificate or a device/release qualification.

The typed Jeeves `world.revision_preview` tool is read-only; it cannot approve
or publish. Preserve the old source separately before changing canon.
