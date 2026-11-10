# Wave 22 — Exact finite dependency topology

All CycloneDX, SPDX, npm, Cargo, Go and Python pylock source formats now
report real dependency structural metrics beyond node and edge totals.

The new graph analyzer applies iterative Kosaraju to distinguish true
strongly connected cycles from nodes merely blocked downstream of cycles.
It computes exact finite transitive reachability per node, dependency
reverse blast radius, SCC-condensed longest path, hotspot ranking,
root-reachable component count and a deterministic bound source digest.

The original supplier/license/rights stance is unchanged: all dependency
assertions remain unreviewed external statements. No vulnerabilities are
automatically resolved, packages installed, licenses inferred, nodes fetched
or provider model called. The canonical CrawlRun source snapshot still
owns retention, authority and the original hash chain.

The source workflow includes adversarial SCC, diamond, chain, disconnected
and consistency tests plus verification of the newly integrated projection.
Device, external package-manager and main branch certification remain held.
