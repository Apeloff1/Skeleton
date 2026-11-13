# Mixed signed/unsigned original-game epoch-chain verification

Run `python -m skeleton app audit-mixed-library-epochs` with two to six
`--unsigned-generation` and matching `--signed-generation` arguments.
Each argument is a bounded JSON array of the same independently pinned entry
objects accepted by `audit-mixed-library-continuity`. Supply
`--trusted-local-operator` only for an explicitly authorized local audit.

The command independently reexecutes every game at every adjacent transition,
checks replay-prefix preservation, signer-policy history, original world identity
and private save custody, and reexecutes the entire chain a second time before
returning a deterministic SHA-256 chain receipt. At least one game must advance
at each transition. The operation does not create or modify source, saves,
packages, receipts or directories. Inputs are bounded to six generations and
eight games total (including at least one unsigned and one signed game).

A chain digest is a point-in-time observational identifier, not a cryptographic
signature, monotonic counter, revocation feed, rights proof, package signature,
native Godot execution or consumer-device qualification. Keep all release,
malware, secret, CodeQL, workflow-input and device holds active. Never use a
successful offline replay as evidence of native runtime acceptance.
