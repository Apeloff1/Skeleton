# Vertical integration and open PR reconciliation — 2026-11-19

Status: read-only source and CI inventory plus an implementation decision record.
This is not a release, native-device, model-quality or competitive-superiority
certificate. The user priority remains Jeeves, Dragon, then Skeleton.

## Frozen inventory and integration base

The inventory cutoff is **2026-11-19 23:54:21.750 UTC**. The
[complete JSON ledger](VERTICAL_OPEN_PR_LEDGER_2026_11_19.json) accounts for
**181 open PRs, including 54 drafts, at 175 unique immutable heads**. It records
all **1,613 observed Actions runs** through its external audit reference,
retaining 1,272 latest workflow/event/head-branch check groups in the repository.
The full audit also preserves earlier run IDs. Every head query returned its full
reported result count; none exceeded the requested 100-run page.

The repository JSON is a compact projection with every PR's decision and
immutable identity plus the 1,272 latest check groups. The exact original full
snapshot and metadata for all 1,613 observed run IDs are preserved outside Git
in `/workspace/artifacts/verticals/pr-audit-full.json` and
`pr-audit-workflow-metadata.json`, packaged together in `pr-audit-full.zip`.
The ledger records each artifact's SHA-256 and byte count. The complete run
metadata was retrieved again after cutoff; its later outcomes do not replace
the independently preserved frozen snapshot.

Discovery used the paginated connected-user inventory and independent,
nonoverlapping all-author date partitions, then captured #5699 and #5700 before
the cutoff. New PRs and subsequent head/check changes are excluded from this
snapshot. Refresh deliberately at the next integration checkpoint rather than
letting ongoing remote activity prevent delivery.

Build on current main **`881c918d74b7be665def64c52485979e12d96132`**.
Preserve its current features and canonical owners. Use the open branches as
sources of individually reviewed behavior, tests and receipts. Do not replace
main with a donor checkout or replay a large branch merely because its PR is
newest.

## Selected product increments

| Priority | User outcome | Integration boundary |
| --- | --- | --- |
| Jeeves | Choose a typed guided workflow and execute it through a clear, consistent AI surface. | Existing backend/frontend workflow owners; remove duplicate AI routes while preserving deep links, authority, cancellation and unavailable states. |
| Dragon | Create, save, reopen and revise a NativeProduction project. | Existing Dragon product, project and artifact authorities; source identities and saved revisions remain bound. |
| Skeleton Forge | Observe a durable build and retrieve a verifiable source ZIP after recovery. | Existing Forge builder, job and export owners; retries, failure, restart and artifact download must remain honest. |

These are concrete delivery workloads, not declarations that the entire
repository or every open experiment is complete. Their implementation tests and
browser evidence belong in the eventual draft; this inventory ran no new
product, model or native acceptance tests.

## Donor decisions

| PRs | Relevant behavior | Decision for this increment |
| --- | --- | --- |
| #5642 → #5643 → #5646 | Local office/memory/media helpers, bounded ranking and STRIPS plan proof. | Reference typed plans and receipts. The planner is not a pretrained model; adapt only through the current owner. |
| #5627 | Golden brief, playtest failure taxonomy, asset manifest and job observation. | Reuse useful workflow semantics after review. Avoid installing its separate Studio office/agent surface wholesale. |
| #5629 → #5630 → #5636 | Independent local review, durable replay and uncertain-dispatch denial. | Reference recovery invariants. Exact-head secret scanning and source qualification failed; no verified-readiness claim. |
| #5692, #5693, #5694 | Static story, character and plot dictionaries; #5694 also repairs an existing JSX apostrophe. | Optional content helpers requiring real call sites, typed behavior and tests. These PRs alone add no working end-user journey. |
| #5495 and its crawler lineage | Checkpointed acquisition, navigation and Jeeves discourse integration. | Distinct from the visual Dragon lineage. Review narrowly; 850 unique commits and 342 branch-delta paths make wholesale replay inappropriate. |
| #5616; #5611 → #5612; #5602 → #5603 → #5604 | Real Three process custody, pose parity, incident evidence and independent revalidation. | Three sibling lines after #5601. If needed, reconcile their overlapping operator/tests; #5616 alone does not include its siblings. |
| #5432, #5434 → #5436 | Owner-bound delivery, redemption and source-bound coverage receipts. | Reference source ZIP durability and honest progress. Preserve current export and account authorities. |
| #5283 | Historical single-host inference custody. | All nine branch-delta paths already have identical bytes in main. Exclude redundant replay. |
| #5300 | Genre catalogue expansion. | Its changed runtime catalogue already matches main; remaining differences are CI/tests. Do not count this as a missing 158-genre feature. |
| #5370, #5376 | Historical offline-builder recovery. | Twelve of thirteen paths already match main; the only remaining difference is an extra trailing blank line. Exclude. |
| #5398 | Galaxy profile recovery. | Sixty-two of sixty-six paths already match main. Review only the two remaining UI paths, archive workflow and pin metadata if a current defect requires them. |
| #5404, #5405, #5479, #5487 and other broad recovery branches | Recovered runtime, application, source and CI families. | Discovery references only; preserve main and resolve a demonstrated current gap at its owner. |
| #5464–#5474 model/runtime and dispatcher lines | Retrieval, cognition, GPU/tuning, memory and scheduling experiments. | Defer broad runtime cutovers from these three user-facing increments. Focused source success does not qualify native performance or competitive quality. |
| #5591 → #5617 → #5622 → #5625 → #5632 → #5634 → #5637 → #5695 → #5697 → #5699 | Local-only Docker, offline image/data custody and guarded authenticated chat acceptance. | Latest source leaf is #5699 at `1c125afe5cfc4b9def2f4698b776cb7d50c00272`. Preserve this deployment reference separately; synthetic Docker probes do not prove production applications, licensed GGUF or physical accelerators. |

Every remaining open PR has an explicit classification and disposition in the
JSON ledger. A deferred or reference-only disposition preserves the candidate
for later review; it does not assert its functionality is absent or complete.

## Dependency and overlap traps

The ledger contains **131 named parent edges**. For **39 edges**, the indexed
parent's current head is not an ancestor of the child. Record both SHAs and
inspect the actual delta: a named stack is not a guarantee that a child includes
later parent commits. Conversely, missing ancestry is not proof of a missing
fix; equivalent cherry-picked patches can already exist. The latest Docker
leaf, for example, already contains the strict internal-network test semantics
also repaired on older parent/companion branches.

Most older donor trees predate large mainline integrations. A two-tree
comparison against main can show hundreds of current paths absent in a donor.
Those are **not deletion instructions**. The ledger separates the donor's
merge-base delta, byte-identical paths already in main, current-tree differences,
and paths also changed on main. These are navigation aids, not semantic defect
counts.

## CI companions and binary deposits remain separate

The ten main-targeted qualification companions are **#5618, #5623, #5624,
#5626, #5633, #5635, #5638, #5696, #5698 and #5700**. Six currently share the
implementation's exact head; four differ in source-test repair history.
They are evidence branches, not additional product features or independent
merge candidates. Compare source SHA and repair hunks before reusing a receipt.

All **22 `assets(dragon)` deposit PRs** add only one README relative to their
recorded base at the captured heads. They add no binary payload. Keep these
placeholders distinct from separate original-byte blob transport and
reconstruction evidence. Titles, manifests and synthetic fixtures cannot
substitute for verified original bytes or real renderer/device acceptance.

## What the observed CI proves

Exact-head workflow metadata exists for all 175 heads; five have no Actions
runs (#5466, #5443, #5440, #5438, #5434). Source or product readiness cannot be
inferred from secret scanning, dynamic **Analyze (actions)**, a skipped job,
a deliberate merge hold, an ancestor receipt or a workflow that creates no jobs.

The checked #5616 operator push run
[44412466040](https://github.com/Apeloff1/Skeleton/actions/runs/44412466040)
and #5604 exact-source push run
[44239778906](https://github.com/Apeloff1/Skeleton/actions/runs/44239778906)
failed with **zero jobs**. No Three qualification is established by those runs.
The latest Docker companion successes inspected at the cutoff are Actions
CodeQL and secret scanning, not physical protected-chat acceptance.

#5646's Backend Quality run passed six focused source jobs but failed the
specialized CI tier contract. #5627 passed App Foundation while its backend
boundary and Expo contract jobs failed. The narrative helpers' exact-head
Backend Quality jobs also expose source/architecture/route failures. These
failures must be diagnosed against the assembled draft; this document does not
attribute them to the helper additions.

The ledger preserves run URLs, event types, outcomes, query times and the nine
explicitly inspected job sets. Current evidence makes no competitive claim.
