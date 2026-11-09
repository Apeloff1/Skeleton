# Dragon Wave 15 — Multimodal asset-source inventory without execution

The canonical Dragon CrawlRun worker now admits bounded source metadata for
PNG, JPEG, GIF and PCM WAV, a no-extraction ZIP central-directory inventory,
Wavefront OBJ geometry, and glTF 2.0 scene graphs.

Media parsers inspect signatures, geometry and bounded structural metadata.
They do not decode pixels or audio, invoke codecs or GPU renderers, execute
scripts, play media, decode glTF buffers, fetch referenced image/material
URIs or grant any right to train on captured assets.

ZIP inventory refuses encrypted/symlink/traversal/duplicate and overlarge
entry catalogs; it exposes extension counts, not internal file paths or raw
member content. glTF validates finite node indices and rejects cycles. OBJ
validates bounded face and coordinate data, never loading MTL or texture
references. Missing or malformed media structures fail before source
publication, while the existing network attempt remains accounted.

Every MIME value is explicitly registered in the original canonical
CrawlPolicy. The existing execution-code digest binds all parser code,
strict request and source-rights limits remain, and source text is hashed
and retained as unreviewed evidence in existing Mongo snapshot custody.

Dedicated tests cover binary corruption, malicious archive entries, node
cycles, forbidden material references, and real scripted canonical worker
capture, exact replay and no unsolicited network requests. These tests
do not constitute native media codec, device, DNS/proxy, live Internet,
distributed worker, merge or launch qualification.
