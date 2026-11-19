# Campaign production end-to-end acceptance

The CLI acceptance suite exercises actual `python -m skeleton` dispatch,
not only direct function imports. It edits canonical source, replays authored
combat to a terminal game, packages the full save and nested journals,
verifies export integrity, imports an active checkpoint and resumes it,
and rejects tampered reward and stale-source input before delivery.

Run `python -m pytest skeleton/testing/test_combat_campaign_author.py
skeleton/testing/test_combat_campaign_package.py
skeleton/testing/test_combat_campaign_end_to_end.py -q` when the
required CI test executor is available. No test pass is implied merely by
publishing these tests. The offline artifact is an integrity-checked game
save, not a trusted or signed distribution package.
