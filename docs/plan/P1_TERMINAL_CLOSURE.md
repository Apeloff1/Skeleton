# P1 Terminal Closure Authority

P1 has two machine concerns that previously looked contradictory.

The execution map and task backlog are active planning/provenance ledgers. Their
schemas deliberately remain active and preserve historical dependency/evidence
state.

The file machine/ai_p1_terminal_closure.json is the terminal closure authority
for the bounded P1 production frontier.

The terminal claim is intentionally narrow: 107/107 P1 frontier volumes are
closed as the trustworthy-production frontier, all 513 governed risk
obligations are evidence-backed, and 314 volumes remain explicitly deferred to
P2. It does not claim the 421-volume masterplan is complete.

Run the independent check with:

    python scripts/check_p1_terminal_closure_manifest.py --json

The verifier fails closed if the 421/107/314 partition changes, any of the 513
risk obligations loses evidence, accepted-risk substitution appears, or the
canonical P1 terminal gap verifier reopens.

This resolves the status ambiguity without rewriting the historical task DAG or
fabricating task signatures.
