# Dragon Wave 14 — RSS 1.0 linked research and HTML semantic landmarks

The canonical Dragon worker now recognizes bounded RSS 1.0 documents
serialized in RDF/XML. Only explicit RSS 1.0 item/link elements are accepted
as frontier hints. RDF resource arcs, channel homepages, external entity
declarations, arbitrary link predicates, out-of-scope hosts and references
without the RSS1 channel marker are never promoted into crawler dispatch.

For already acquired HTML, the source extractor now enriches retained
unreviewed text with finite H1-H6 heading labels, figure captions, quoted
text, summaries, definition pairs, and a short meta description. The extractor
skips script, iframe, canvas, style, SVG and template content, never loads
images or external media, and does not generate additional URLs. The ordinary
HTML extraction and rights rules remain canonical.

RSS1/HTML inputs still require consent, host allowlisting, robots, runtime
reservation and backend lease fencing. HTML semantic extraction is best
effort and never overrides canonical link authorization. Feed XML failure is
fail-closed; unsupported RDF/XML can remain inert XML source evidence.

Source CI additionally compiles the new module and runs direct parser tests
plus actual scripted CrawlRun run_slice and snapshot replay checks. The
branch retains draft, security, final-head CI, Mongo/worker and real-device
holds pending independent qualification.
