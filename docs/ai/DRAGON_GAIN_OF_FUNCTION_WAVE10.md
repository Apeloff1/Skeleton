# Dragon Wave 10 — Real scholarly, temporal and research-artifact ingestion

This change extends the existing live canonical Dragon CrawlRun worker.
It does not create a daemon, parallel crawler, unbounded network grant,
trusted training importer, knowledge promotion route or new persistence
authority. All supported formats pass the existing scoped consent, robots,
public-IP/DNS/redirect checks, host cooldown, pre-I/O budget reservations,
cancellation and backend Mongo custody.

## Executable source acquisition

| Format | Explicit MIME(s) | Retained evidence | Excluded behavior |
| --- | --- | --- | --- |
| WebVTT/SubRip | text/vtt; application/x-subrip; text/srt | Ordered timestamped cue text | No style/media scripts, NOTE links or auxiliary fetch |
| iCalendar | text/calendar; application/ics | Finite event title, date, description, location | No recurrence expansion, alarm, attendee harvesting, remote timezone or scheduling |
| RIS | application/x-research-info-systems; text/ris | Citation title/author/abstract/DOI | No automatic citation approval or link traversal |
| BibTeX | application/x-bibtex; text/x-bibtex | Literal title, bibliography fields and metadata | No macro expansion, TeX execution or symbolic concatenation |
| Jupyter | application/x-ipynb+json; application/vnd.jupyter | Inert Markdown/source-code cells | No kernel, output, widget, execution, attachments or credential-indicator code |
| RDF | application/n-triples; application/n-quads | Finite syntax-checked assertions | No IRI navigation, context expansion, SPARQL or inferred truth |

The new parser families share explicit per-artifact complexity and output
limits. Unicode decoding for these types uses strict UTF-8. Every accepted
document enters the existing content hash, preserved text hash, source-rights
receipt and lexical evidence retrieval pipeline. Embedded links cannot enqueue
URLs; newly admitted MIME values do not widen hosts, ports, request methods,
authenticated headers, resource limits, database permissions or execution grants.

## Limits, rollback, recovery

- No more than 1024 timed cues, 256 events, 256 notebook cells, 256 RIS/BibTeX
  references or 512 RDF statements, subject to the existing 2 MiB response
  limit and 24 KiB retained text per source.
- Parser truncation is recorded explicitly. Oversized structure, invalid
  UTF-8, incomplete syntax, executable BibTeX macros and unbalanced fields
  fail before source publication.
- Malformed documents still consume reserved HTTP request accounting. The
  unchanged worker retains exact checkpoints and requires fresh authority
  checks before another network dispatch.
- Existing implementation hash binding includes every new active parser.
  Prior runtime snapshots with a different code digest require the existing
  explicit operator recovery path; this work introduces no silent downgrade.
- Revert the draft or disable these explicit MIME types for rollback. Existing
  source-use withdrawal, erasure and captured-evidence holds remain authoritative.

## Qualification boundaries

The source workflow compiles every new parser, runs adversarial parser tests
and executes actual scripted CrawlRun.run_slice capture/replay tests. The
transport asserts that no embedded URL, attendee, DOI, RDF IRI, notebook widget
or media metadata produces an unexpected request.

Physical Windows/WSL2, persistent Mongo, live Internet, proxy/DNS rebinding,
distributed leasing, full repository-wide CI, mirror parity, merge and release
certification remain separate unverified gates. This is a draft-only addition.
