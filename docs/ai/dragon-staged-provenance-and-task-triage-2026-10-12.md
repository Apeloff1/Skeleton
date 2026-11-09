# Dragon provenance and task-focused staged source triage
2026-10-12 UTC | PR #3605

Milestone 1 — Git identity hardening: The previously failing Python integration test exposed that repository identity '../secret' passed the untrusted staged catalog validator. Repository owner/name segments now begin with an ASCII alphanumeric character. This refuses path-like, dot-only and dash-leading components while preserving ordinary Git names. A Git SHA is still an unverified catalog claim, not attested server content.

Milestone 2 — README metadata scrutiny: Relative Git tree path names now reject traversal, empty or dot-only components, drive-like prefixes, backslash separators, and ASCII control characters. Staged observations still need valid HTTPS source URLs, source line numbers, bounded headings, and full existing append-only-chain validation.

Milestone 3 — Task-focused, host-diverse metadata review: rank_staged_research_leads validates the full previous raw-discovery chain before ranking any new source. It matches bounded human-supplied task terms against only observed README headings and URL tokens; it tracks original source IDs, Git provenance claims, and host labels. Host round-robin prevents one host dominating a short review batch. This provides a prioritization signal, NOT a claim of content quality, independent fact agreement, crawl authorization, source rights, model training or XP.

Regression tests: forged repository and README paths, valid Git identifiers, deterministic reverse-order outputs, host diversity, task syntax and rights-forgery refusal.

2026-10-12 UTC changes: (closed forged Git metadata acceptance); (strengthened relative README evidence paths); (added game-task-oriented lead selection without automatic network or weight promotion).

CI status: The previous run passed Frontend, Source Safety, Authenticated Backend, CodeQL and Shadow Weight, but failed one staged metadata provenance test in Dragon Python. This commit requests exact-head retesting; no green result is claimed until GitHub completes it.