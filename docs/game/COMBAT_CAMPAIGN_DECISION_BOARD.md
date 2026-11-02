# Player combat decision board

The offline combat campaign now has a read-only choice inspector.
`python -m skeleton combat-campaign-board demo` previews the first authored
hero turn. To inspect a verified checkpoint, use
`combat-campaign-board inspect --session-json JSON
--expected-source-digest DIGEST`.

Every attack, guard or rest preview is evaluated by the actual human-controlled
campaign reducer, including deterministic opponent turns, health carryover,
earned currency, encounter transitions and replayable save digests.
`choices_truncated` reports when the bounded presentation limit hides
otherwise legal actions. No currency is minted by the inspector; no preview
mutates the supplied checkpoint. This is decision support, not a guaranteed
winning strategy, an authorization signature or hardware qualification.
