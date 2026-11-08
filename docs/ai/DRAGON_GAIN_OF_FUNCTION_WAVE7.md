# Dragon Wave 7 — Live Crawler Capability Expansion

This wave delivers actual document acquisition, extraction, scheduling and
pagination in the canonical Dragon `CrawlRun` worker and the existing authenticated
Jeeves crawler workspace. It is not another diagnostic/advisory pipeline.

## New executable crawler behavior

1. **Markdown** (`text/markdown`, `text/x-markdown`): preserve narrative and
   code snippets as untrusted text, extract headings and bounded inline,
   reference or autolinks, exclude images and fenced/inline-code links from
   automatic discovery. Retained links must pass the same canonical source
   allowlist, robots checks, host cooldown, pre-I/O budget and DNS/socket
   admission as every other URL.
2. **CSV** (`text/csv`, `application/csv`): deterministic table-to-evidence
   conversion using quoted CSV parsing, finite rows, columns and cells,
   retaining field names for lexical retrieval. CSV values never create links
   and formula strings are not executed.
3. **Ordinary JSON and JSON-LD**: preserve bounded nested field paths and
   scalar text as captured, unreviewed source evidence. Sensitive common
   credential keys are redacted in the retained projection. Generic JSON
   URL/href fields do not enqueue URLs. Valid JSON Feed 1/1.1 retains the
   separate preexisting feed-link discovery behavior.
4. **JSON Lines and code/config/docs**: capture NDJSON, Python, C/C++, Rust,
   Go, Java, JavaScript, TypeScript, CSS, Markdown-adjacent reStructuredText
   and AsciiDoc, YAML, TOML, and shell source content as *inert external text*.
   No code import, execution, YAML tag construction, formula evaluation or
   hidden filesystem reads are introduced.
5. **Real HTTP pagination**: navigate source-bound `Link` headers with
   `rel=next` and explicitly typed feed `rel=alternate`. The pinned socket
   transport now preserves repeated `Link` header instances under an 8 KiB
   metadata limit. HTML `<link rel=next>` and feed alternates are supported
   by the same canonical frontier. Untrusted link values can never widen the
   account's seeded host allowlist.
6. **Optional balanced real frontier scheduling**: the operator may choose
   `frontier_strategy=balanced` rather than default `fifo` when creating a
   crawl. Dispatch ordering compares only existing due URLs using operator
   query/URL-path lexical overlap, previously captured host counts, retry
   pressure, and breadth-first depth. It does not create new targets or
   bypass the actual robots, rate, byte, request, worker-lease or consent
   checks. The mode persists in the exact request binding and snapshot.

## Interfaces and custody

- `CrawlRequest.frontier_strategy` is a strictly validated immutable
  `fifo|balanced` grant, saved at creation by `backend/core/dragon_crawler.py`
  and validated by `backend/routes/dragon_academy.py`.
- The Jeeves crawl creation screen supplies an explicit balanced-strategy
  switch. Existing FIFO remains the default and is preserved in snapshots.
- Capture provenance records the original raw response-body digest, canonical
  document hash and an explicit parser-text truncation signal. The existing
  source text truncation, source-use policy, unreviewed status, training
  hold, source rights and storage receipts are unchanged in authority.
- The structured-content parsers are independent of network, database and
  AI runtimes; only canonical `run_slice` can execute a request or persist
  a result. All new formats remain subject to the 24 KB retained text cap
  and bounded 4 MiB snapshot.

## Qualification

```sh
python -m compileall -q skeleton/ai/webcrawler
python -m unittest discover -s tests -p 'test_ai_webcrawler_dragon_gain7.py' -v
python -m unittest discover -s tests -p 'test_ai_webcrawler_dragon_live_discovery.py' -v
node frontend/scripts/test-dragon-atlas-contract.cjs
```

The gain-of-function suite tests actual `CrawlRun.run_slice` with a strictly
scripted transport, not an external network call. It covers bytes, robots,
host/consent scope, fenced evidence, snapshot replay and dispatch order.
It does not constitute real Internet/Mongo, Windows/WSL2/device-pressure,
merge, publication or release certification. Existing skipped/failed gates
retain their fail-closed holds.
