# Wave 25 — Source-only engine-neutral scene hierarchy

The original canonical Godot scene evidence extractor now constructs a real
bounded parent-child scene graph with exact node identities, edges,
validated root ownership, parent references, maximum depth, child fanout,
type counts, isolated nodes, graph digest and rejection of missing parents,
duplicate path identities, cycles and ambiguous multi-parent relationships.

The reusable scene topology kernel is deterministic across input order,
does not instantiate nodes or load any script, mesh, game, texture, shader
or remote/relative resource. Godot source paths are resolved only inside the
already-retained scene's declared node table, never against the filesystem.

Existing wire bytes and source-text hashes, tenant/owner consent, robots,
source rights, network pacing, source review, Mongo snapshot CAS and the
existing implementation-hash binding still apply. No game builder
execution or automatic third-party asset rights are granted.

The source workflow compiles both new kernels and executes direct adversarial
DAG/hierarchy tests and an actual scripted canonical CrawlRun source
capture/replay with zero unsolicited network requests.
