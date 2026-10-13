# Jeeves original game variants — source-producing portfolio (Oct 2026)

\`studio.production.variants_plan\` produces from one to four real,
different original playable game worlds using the installed deterministic
compiler with bounded independent seeds and optional palette rotation.
Every world has a distinct SHA-bound world identity, an intrinsic Python
winning-replay receipt, its own offline HTML and Godot source tree and
a concrete package manifest.

\`studio.production.variants_stage\` revalidates the portfolio plan digest
then stages each independently generated project package using canonical
\`GameWorkspace.propose\`. A later source-stage failure records which
variant proposal bundles were already created and which remain, without
claiming an all-or-nothing transaction.

The user can subsequently page persisted proposals, inspect exact source
diffs, approve individual SHA-256 versions, and commit actual project
files using the existing canonical GameWorkspace writer.

**Limit:** at most four original worlds and 6 MB of source candidates
per call; no fictitious global variation count is claimed as built games,
and no native binary or hardware certification is implied. No repository
test suite was executed in this workpass.
