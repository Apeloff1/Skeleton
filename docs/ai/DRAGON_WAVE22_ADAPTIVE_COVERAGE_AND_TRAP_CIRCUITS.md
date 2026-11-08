# Dragon Wave 22 — Multilingual coverage-first frontier and facet trap circuit

Two operational layers augment the canonical source-acquisition worker.

**Coverage-first frontier scheduling** is an explicit opt-in
CrawlRequest.frontier_strategy="coverage". It ranks only already admitted
due frontier rows using operator-authored query terms, canonical URL path
terms, host distribution, source URL family distribution, depth and retry
attempts. Source *body* text, injected page directives, retrieved model
outputs and source-provided score values never influence the selection.
Unicode NFKC/casefold and bounded CJK bigrams improve navigation across
non-Latin research destinations. FIFO remains default; existing balanced
scheduling remains unchanged. Host cooldown remains absolute.

**Facet-antichain trap protection** is always active at the original
CrawlRun._enqueue authority boundary via frontier_circuit. It vetoes
multiply percent-encoded structural separators, disguised credential query
keys and more than 48 known variants of one path family spanning unrelated
query-key shapes. This supplements, rather than replaces, the earlier
24-per-(path,query-keyset) family limit. It is a veto only, with finite
per-snapshot work; no new URLs, hosts, cookies, headers, DNS lookup, source
rights, robots exception or network call can be granted.

Every added gate is included in the worker implementation digest. Old
snapshots whose code digest differs remain fail closed until explicit
operator-approved recovery. The source workflow compiles both modules
and runs contract/adversarial tests and actual scripted CrawlRun captures
checking finite request accounting, host isolation, deterministic replay
and inability to follow embedded unauthorized URLs.

This does not certify remote data, independent source corroboration, live
network dispatch, persistent Mongo multiworker concurrency, physical
Windows/WSL2 installation, complete release CI or launch readiness.
