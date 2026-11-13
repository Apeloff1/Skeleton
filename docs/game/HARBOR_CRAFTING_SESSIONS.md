# Lantern Quay — deterministic session custody

## Historical save, resume, and alternate endings

A verified bundle can be rewound to any accepted tick. The operation rebuilds
the state from source and the original event prefix, not from a stored
unverified checkpoint:

    python -m scripts.game.harbor_crafting checkpoint --bundle lantern-save.json --tick 17 > dock-save.json

Resume a partial save with an optimistic terminal-digest lease. Pass the
terminal_digest from dock-save.json; a stale or modified save fails closed:

    python -m scripts.game.harbor_crafting resume --bundle dock-save.json --actions final-choice.json --expected-terminal-digest DIGEST --require-win > finished-save.json

A branch portfolio takes a JSON object mapping original branch names to
continuation action arrays. For example, from the tick-17 dock save:
{"beacon":[{"op":"choose","choice":"signal"}],"shelter":[{"op":"choose","choice":"shelter"}]}.
The following commands produce and verify two independent source-replayed
ending bundles:

    python -m scripts.game.harbor_crafting portfolio --bundle dock-save.json --branches choices.json > choices-portfolio.json
    python -m scripts.game.harbor_crafting verify-portfolio --bundle choices-portfolio.json

Every branch is recomputed from the exact verified root and compared to the
saved event chain and terminal digest. Portfolio branch count and total bytes
are bounded. Historical events are immutable across continuation. These
operations are local deterministic custody, not networked distributed CAS
or cryptographic authentication.

Focused acceptance:

    pytest -q skeleton/testing/test_harbor_crafting_campaign.py skeleton/testing/test_harbor_crafting_sessions.py
