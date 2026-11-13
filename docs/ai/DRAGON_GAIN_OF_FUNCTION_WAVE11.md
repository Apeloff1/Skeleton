# Dragon Wave 11 — Multilingual and backward site traversal

Existing canonical CrawlRun now admits finite XHTML sitemap hreflang alternate
links, HTML and HTTP Link language alternatives, and rel=prev pagination.
HTML anchor rel=nofollow links are excluded. The shared relation predicate
rejects unrecognized or malformed languages and unrelated link relations.

Every nominated URL must remain in the immutable host allowlist and is
processed only by the existing canonical worker after consent, robots, DNS,
redirect checks, host cooldown, finite budget and owner lease fencing.
No separate network client, policy grant, source trust or persistence owner.

The regression suite exercises the actual canonical run_slice with scripted
robots and sitemap responses, asserts four permitted frontier URL identities,
zero cross-host dispatches and exact snapshot replay. Full external network,
device, Mongo and release gates remain unqualified; this stays a draft.
