# LAFS evidence admission and operator controls

- Historical cabinet remains a shared installation-level store. In an authenticated
  or detected deployed host, set LAFS_OPERATOR_TENANT and LAFS_OPERATOR_ID to the
  actual installation administrator; other tenant admins cannot use these routes.
- Online learning is disabled unless LAFS_ONLINE_LEARNING=true. Sweeps and manual
  ingestion share the same policy. A fetched Wikipedia revision is bounded,
  digest-bound, deduplicated and pending; no automatic reinforcement is applied.
- The retained evidence digest covers canonical title, exact extract, revision
  and admitted URL. The response digest records the observed wire response;
  raw entire HTTP response is not retained. Neither digest authenticates truth.
- Pending/rejected/legacy online data is excluded from retrieval and propagation.
  Legacy data requires source re-ingestion/review; no historical records deleted.
- Review is an explicit digest-bound administrative action. It grants retrieval
  eligibility, not instruction authority or an independent factual validation.
- PDF extraction uses the existing isolated file decoder, with shared bounded
  physical admission. No private attachments are added to the global Delta memory.
- Ask selects a declared selectable local model explicitly, with extractive
  fallback if none is available. Native execution and the physical engine host
  still require independent device and deployment qualification.
- Hard limits: source response 128 KiB, extract 12,000 characters, 12 topics per
  batch, 2 concurrent source fetches, 12 MiB cabinet. Large-cabinet migration and
  historical provenance recovery remain open.
