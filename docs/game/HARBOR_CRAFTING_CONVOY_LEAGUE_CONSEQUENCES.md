# Earned convoy league choices and portable endings

League consequences reuse the canonical convoy contract evaluator for each
played round. A player may choose **relief** (earned reputation) or **salvage**
(earned credits) separately per round. Each contract's authored prerequisites,
crafted items, defeated enemies, hull and bounty thresholds, and dock delivery
are evaluated against the independently replayed convoy report.

The championship never awards free crafting materials or alters the canonical
save. Every token is namespaced by its original round ID, so two stages can
both award a cargo token without impersonating each other. Partial or failed
championships cannot claim the complete ending. Choice comparison computes
both endings from the same exact gameplay digest.

The choice package seals the source-bound league package and the distinct
round contract boards. Its play object contains replay-verifiable consequences
and a package/play digest; verification rebuilds both and rejects forged
reputation, credits, choices, source, prerequisites and completion.

Use `league-consequences`, `league-verify-consequences`,
`league-choice-compare`, `league-choice-package`,
`league-choice-verify-package`, `league-choice-play`, and
`league-choice-verify-play`. The fixture
`harbor_lantern_quay_convoy_league_contracts.json` contains the original
two-stage required quest chains. This is a gameplay/CLI delivery, not a claim
of graphical device certification.
