# P3 Domain Intelligence

This slice implements the executable behavior owned by
`P3-DOMAIN-INTELLIGENCE-01`.

It creates one explicit custody registry for specialized domains, requires a
bounded capability envelope and evaluation owner, rejects parallel Jeeves
custody, fails closed on stale or provenance-free evidence, preserves the
simulation-vs-real evidence boundary, and introduces uncertainty-aware teaching
recommendations that request more evidence rather than overclaiming learner
state.

The canonical module is mirrored exactly through the governed AI tree:

- `skeleton/jeeves/domain_system.py`
- `skeleton/ai/agents/jeeves/domain_system.py`

Run:

    python -m unittest -q skeleton.testing.test_p3_domain_intelligence
