# Author-to-playable game production acceptance

`python -m skeleton combat-campaign-production-accept demo` proves the
original edited two-encounter game can be won through actual player turns,
checkpointed, replayed, and exported as a portable offline game save.

`accept --author-report-json '<json>'` accepts only a verified transactional
campaign author report, then searches bounded canonical legal moves.
It requires a real victory, exact replay witness, interactive gameplay
acceptance and portable import/export equality. `verify --receipt-json
'<json>'` recomputes the full chain from the authored source, not merely
its checksum. Budget exhaustion is a hard acceptance failure, **not** an
unwinnability verdict. No release, rights, hardware or author authentication
is implied.

Focused test:
`python -m unittest skeleton.testing.test_combat_campaign_production_acceptance -v`.
Exact-head CI remains required for integration and release decisions.
