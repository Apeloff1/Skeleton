# Studio A integrated original-world playable assembly

The assembly composes five independent reviewed Studio A source planes into
one original HTML5 game: NPC testimony, causal rumor propagation, authored
localization, accessible narration and dramatic pacing. It reuses the
canonical world and reviewed cast, not a parallel world model. Authors edit
and approve each plane through its own typed CLI and offline editor. The
assembly itself has no write path for authored source, only source-bound
compilation and verification.

The operator `python -m skeleton world-studio --store DIR inspect
--world-id ID` returns the exact seven source digests and proof digests.
`compile --world-id ID --expected-digests-json JSON` acquires the shared
world lock, re-reads every source, re-proves all five systems, rejects any
unapproved plane or stale digest, and writes HTML5 and manifest before
publishing a receipt last. `verify` recomputes all artifacts and checks
their exact bytes. `preview --choices-json JSON --locale fr` and
`player --slot SLOT --locale fr` replay real canonical choices with
source-verified NPC knowledge, testimony, localization, accessibility and
pacing. A persisted player slot is independently replay-validated.
Jeeves previews are read-only and never approve or publish.

The compiled browser uses one deterministic choice loop, a locale selector,
NPC witness/rumor state, authored scene accessibility and pacing notes.
It uses native buttons, focus restoration, textContent and CSP-hashed
inline code; no network, external assets, eval or private context notes.
Proof and artifact digests are bound to the exact source versions.

Focused regression: `python -m pytest skeleton/testing/test_jeeves_world_studio_assembly.py -q`.
No native device, consumer installation or release certification is claimed.

Cross-plane proof also traverses real choices with both testimony and rumor
knowledge state. If a character's disclosed testimony conflicts with a
rumor they have learned about the same claim, the entire assembly fails
closed. Mutually exclusive branch outcomes remain representable. The
cross-plane proof digest is included in the source-bound receipt.
