# Cooperative market production portfolio

`python -m skeleton scene-market-party-portfolio accept` runs the
original authored cooperative campaign to an earned victory, stores its
canonical replay checkpoint in an optimistic save vault, records the
winning replay in the offline league, exports all three, imports them and
verifies the same source, state and ranking.

`pack --checkpoint-json JSON --vault-json JSON --league-json JSON
--slot NAME` produces one portable integrity-checked portfolio.
`import --bundle-json JSON` validates all nested canonical exports,
replays their histories, checks matching source digests and the selected
save slot, and independently reconstructs the ranking and portfolio
checksum. An edited inner export or a recomputed outer checksum does not
bypass replay validation.

A portfolio does not create currency, game objects, rewards or victory.
It does not merge saves or certify a signed build, online identity,
anti-cheat service, installer, device or consumer release. Its serialized
payload is bounded to two MiB and inherits all canonical reducer limits.

A production portfolio requires both a winning canonical checkpoint and at
least one replay-verified earned league attempt for that exact checkpoint.
An empty league or a nonwinning saved run fails closed, even when its outer
checksum is recomputed. Inspect-only saves remain valid outside portfolios.
