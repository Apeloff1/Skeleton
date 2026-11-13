# Scene Market End-to-End Acceptance

Run \`python -m skeleton scene-market-accept demo\` for a deterministic
gameplay delivery report. The acceptance runner replays the same authored
market quest through canonical simulation, mid-run checkpoint resume,
portable checksum-bound export/import, and interactive command streams.
It rejects forged export metadata, confirms earned credits, finite stock,
crafting, deliveries and reputation, and can independently replay an
authoring receipt. The output report includes exact source and state digests,
portable checksum, checkpoint and interactive evidence, and a digest of
the report itself.

\`audit --source-json JSON --actions-json JSON\` accepts an original authored
source and action witness; default acceptance requires an earned victory.
\`--allow-loss\` explicitly allows a verified losing playthrough, without
relabeling it as a victory. \`--include-editor\` adds separate transactional
editor replay evidence for a market source with at least one offer.

This is a single-source offline gameplay acceptance artifact. It does not
certify game-device support, consumer installation, payment readiness,
rights clearance or full repository CI. Every report must be tied to its
exact source digest and checked against the live branch SHA.
