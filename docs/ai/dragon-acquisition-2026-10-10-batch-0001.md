# Dragon acquisition: first sequential batch

Checked 2026-10-10. Registry range [0, 32), sorted by source ID. Branch selected because main did not contain the durable progress file; implementation is in PR #3605. This is a data-only acquisition change, not runtime deployment or canonical admission.

## Counts

{
  "newly_checked": 32,
  "fetched_representations": 19,
  "repository_metadata": 10,
  "target_page_representations": 6,
  "shells": 2,
  "wrong_target_redirects": 1,
  "retrieval_failed": 11,
  "unresolved_moves": 2,
  "blocked_from_admission": 32,
  "distilled": 0,
  "approved": 0,
  "additional_license_files_fetched": 1
}

Fetched representations include shells and a redirect to the wrong target. Every candidate remains blocked from admission. A successful retrieval is not a robots, rights or source-review receipt. The original hashed registry is unchanged.

## Findings and follow-up

- The Gamasutra foliage article URL returned a general Game Developer blog index. Do not attribute the missing article to that response.
- The GDC Vault URL contains a trailing `):` suspected parsing artifact and failed retrieval. Preserve the original; confirm a corrected URL from primary evidence in a later repair pass.
- Two GitHub endpoints report repository moves. Preserve destination API IDs; resolve without assuming continuity of content or license.
- One YouTube playlist returned only shell metadata. No video, transcript, creator verification or engagement measurements were acquired.
- LMMS returned a 403 through the retrieval tool. No alternate access was attempted.
- NME license file identity was verified against its Git blob SHA. This supports a license-file observation, not a covered-asset inventory or legal clearance.

Topic triage records preserve the actual discovery headers, citations and tool-representation identities. All machine findings, hypotheses, prototype lessons and product lessons remain empty. Negative retrieval observations are separate from source evidence. Two game repository metadata candidates (Mode and Edgar) are recorded without claiming release/edition completeness or cross-provider identity resolution.

## Gates and continuation

No source was admitted to ReviewedKnowledgeStore, permanent Wiki/HOAG memory, training or release. No reviewed-note pack was rebuilt because this batch supplied no eligible evidence. Sparse routing weights remain distinct from neural parameters.

Next first-pass cursor: 32 / 4405 (0.726%). The separate retry queue retains all 32 unresolved sources, so advancing discovery does not silently discard them. Approval coverage: 0 / 4405. Global game/video coverage is unknown.

Validation: first shard SHA-256 matched the immutable manifest; registry/progress digest, sorted contiguous cursor and unique source IDs checked; NME license Git blob hash independently recomputed; output JSON and cross-file counts checked. No runtime code changed. Architecture checks were not rerun for this data-only batch. The earlier implementation report records historical failures; their current status is not asserted by this change.
