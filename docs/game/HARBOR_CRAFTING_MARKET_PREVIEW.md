# Lantern Quay market preflight and safe action commitment

The market preview uses canonical game transitions to show the first illegal
action and the accepted prefix, without mutating the original save. It supports
NPC stock checks, coin spending, gathering, crafting, movement collisions and
delivery/ending requirements. It does not mint rewards or skip game rules.

Commands: market-preview --bundle save.json --actions planned.json;
verify-market-preview --preview preview.json; market-apply --preview preview.json
--expected-terminal-digest DIGEST. The apply operation refuses partial or
rejected previews and requires the exact verified checkpoint digest. It creates
a fresh replay-verified market ledger from the complete action sequence.

The CLI reads bounded preview and market reports with their explicit schema
limits, rather than accidentally applying the smaller base-bundle limit.
Malformed action shapes fail closed; legal-shaped but impossible actions return
an explicit rejected preview. Rehashed forged preview results are rejected by
full deterministic replay. These are portable JSON operations, not a claim of
device qualification.
