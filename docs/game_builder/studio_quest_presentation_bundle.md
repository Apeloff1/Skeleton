# Source-replayed quest presentation assembly

This integration compiles an **operator-reviewed localized display** and
**canonical sandbox achievements** for the same original authored quest
session. Neither translated strings nor achievement labels are allowed to
change the stage graph, choice effects, earned predicates or ending.

Author a localization plan with the Jeeves localization tool and an
achievement plan with the Jeeves achievement tool. Edit them in their offline
CSP-protected editors and persist private receipts. Assemble the two receipts
with:

\`python -m scripts.studio_quest_presentation_bundle_cli --project
studio_puzzle_expedition_copper_mesa --expected-source DIGEST
--expected-session DIGEST --localization-file /private/locale.json
--achievements-file /private/awards.json --preview-html\`

The read-only HTML preview shows reviewed strings and canonically unlocked
milestones. Use \`--handoff\` only after every localization row is explicitly
reviewed and the target ending is eligible in the canonical replay. The
builder handoff carries source/session digests, immutable canonical choice
keys, translated display labels, earned sandbox achievements and a digest.

Receipt contents are recomputed against source, then cross-compared for
identical project, initial session, final session, actions, ending and
eligibility. Any mismatch fails closed. Private JSON input rejects symlinks,
duplicate keys, mutable descriptor reads and oversized files. Neither
translation provenance, external platform awards, native gameplay, device
qualification nor release certification is asserted. Regression:
\`pytest tests/test_studio_quest_presentation_bundle.py\`.
