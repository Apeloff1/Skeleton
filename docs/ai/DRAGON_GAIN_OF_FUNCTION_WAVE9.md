# Dragon Wave 9: omnidirectional source acquisition and live host discipline

This branch adds production acquisition paths to the existing authenticated
CrawlRun state machine. All source content remains unreviewed evidence; no
content creates an owner grant, runtime secret, JavaScript execution permission,
model-training permission, publication permission or unrestricted network call.

## Source types admitted by the canonical worker

- **HTTP content codings:** identity, gzip and zlib-wrapped deflate. Wire and
  decoded bodies independently fit the original reserved byte cap; truncated
  compressed streams, appended members, invalid checksums and expansion bombs
  fail before evidence retention. The on-wire SHA-256 and expanded-body SHA-256
  remain distinct and the larger byte count is charged.
- **Office documents:** DOCX and ODT paragraph/header text from bounded ZIP
  packages, with no external relationships, macro execution, HTML rendering
  or off-disk extraction. DOCX footnotes, endnotes and comments are finite.
- **Digital books:** EPUB spine XHTML chapters in reading order, with bounded
  OPF/container references and no external-resource loading. Inert chapter
  text is extracted even when the archive contains images and scripts.
- **Spreadsheets:** XLSX worksheet values/shared strings and ODS tables. No
  cell formula, WEBSERVICE, DDE, macro, external workbook, script or OLE
  object is executed. The projection labels worksheet and cell identity.
- **Presentations:** PPTX and ODP slide text with finite slide counts. No
  presentation action, media, animation or embedded object is executed.
- **PDF:** pypdf 7.0.0 runs inside an isolated POSIX child process with
  address-space, CPU, core-dump and file-size rlimits, a hard wall timeout,
  at most 64 pages, finite decoded page streams and bounded output. Scanned
  image-only PDFs are rejected, not hallucinated into OCR. On native Windows,
  PDF extraction fails closed unless running via WSL2/a supported POSIX worker.
- **Generic XML, GPX and KML:** strict UTF-8, no DTD/entities, finite tree,
  depth and node budgets; sensitive common XML element names are redacted.
  XML attributes do not grant URL fanout.
- **HTML semantics:** bounded table rows and inert embedded JSON-LD are
  indexed as labeled unreviewed source text; no JSON-LD URL is enqueued.
- **Generic octet-stream downloads:** only a matching exact filename extension
  (seed URL or strict Content-Disposition basename) AND magic bytes may
  refine ambiguous binary content into a permitted Office, PDF or XML parser.
  Effective/declared MIME and inference reason are source-bound audit fields.

## Real network and source restrictions

- Site X-Robots-Tag headers and HTML robots meta narrow retention/following.
  Repeated headers are combined; malformed overlarge robots metadata denies
  both storage and link following. Noarchive/noindex never retain source text.
- Retry-After on 429/503 delays the whole origin, not just the failed URL.
  Persisted host_ready state fences sibling URLs and survives snapshot replay.
- Robots Request-rate is combined with Crawl-delay and operator delay. A
  requirement beyond the finite consent horizon rejects that dispatch.
- RSS, Atom and JSON Feed next-page relations traverse the ordinary crawler
  frontier. An optional admitted sitemap.txt is UTF-8 and bounded, with no
  out-of-host or relative URL expansion.
- Bounded transport accepts explicitly supported text and document types.
  Every request still requires original consent, DNS/socket pinning, robots
  admission, host cooldown, before-I/O byte reservations, cancellation,
  checkpoint persistence, and existing user/tenant owner scope.

## Qualification

Source CI compiles every changed crawler module and runs the existing Dragon
campaign suite plus the new, format-specific canonical worker regressions.
Those tests use real CrawlRun.run_slice with strictly scripted transports;
PDF tests additionally run the actual isolated parser.

The following do not count as successful qualification until independently
verified on the exact final SHA: physical device/Windows/WSL2 execution, live
Internet + proxy + DNS races, persistent Mongo, distributed worker leasing,
native performance/load, all repository-wide required CI gates, merge, release
and publication. Existing unrelated mirror-tree, dependency or security
failures remain release holds; skipped jobs are not passes.
