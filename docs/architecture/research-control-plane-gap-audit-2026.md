# Research Control Plane Adversarial Gap Audit — 2026

Status: canonical adversarial audit for Track AD control plane
Updated: 2026-09-22
Scope: research-control-plane-internals + RCB001–RCB120

## Rule

The research plane is itself an attack surface. It processes untrusted papers, webpages, repositories, models, datasets, evaluator outputs, model-generated code, and expensive external jobs while influencing architecture decisions.

Therefore every control-plane claim is tested against:

- malicious inputs;
- stale metadata;
- partial failure;
- concurrency;
- incentive gaming;
- authority escalation;
- measurement error;
- human review failure;
- restore/replay;
- long-lived drift.

## Gap ledger — RCG001..RCG100

| ID | Severity | Gap | Failure | Required response |
| --- | --- | --- | --- | --- |
| RCG001 | P0 | Work-identity false merge | Two distinct works collapse into one evidence node | Prefer false split; require exact-ID or adjudicated merge; reversible split |
| RCG002 | P1 | Work-identity false split | One work appears as multiple independent sources | Identity graph + duplicate/derivative detection before independence counting |
| RCG003 | P0 | Status spoofing | Secondary metadata labels a submission as accepted | Official venue/publisher status outranks secondary graph |
| RCG004 | P1 | Version rollback | Older source version silently replaces newer evidence | Monotonic observed-version lineage; downgrade requires explicit attestation |
| RCG005 | P1 | Cross-identifier mismatch | DOI/arXiv/OpenReview links point to different revisions | Bind manifestation digests and explicit equivalence decision |
| RCG006 | P1 | Author/title collision | Similar titles/authors create wrong match | Fuzzy match is candidate-only, never authoritative |
| RCG007 | P1 | Source disappearance | Live URL vanishes after decision | Durable identifiers, metadata, checksums/references where lawful |
| RCG008 | P0 | Correction not propagated | Corrected source continues supporting old claim | Correction receipt invalidates dependent claims for review |
| RCG009 | P0 | Retraction not propagated | Retracted work remains active evidence | Retraction event forces review_due and blocks new promotion use |
| RCG010 | P1 | Artifact-paper mismatch | Code/model release does not correspond to paper result | Exact commit/release binding; mismatch recorded as reproducibility debt |
| RCG011 | P0 | Prompt injection in research content | Paper/webpage tells agent to reveal secrets or alter policy | Treat all source text as untrusted data; instruction firewall |
| RCG012 | P0 | Archive/decompression bomb | Research artifact exhausts parser resources | Size/decompression/path limits before extraction |
| RCG013 | P0 | Malicious repository execution | Fetched code executes during inspection | No execution before scan + isolated sandbox + explicit capability |
| RCG014 | P0 | Adapter credential exfiltration | Source adapter exposes ambient secrets | Task-scoped credentials; no ambient credentials; egress policy |
| RCG015 | P1 | Partial source refresh | Rate limit yields incomplete status set interpreted as current | Refresh completeness bit; partial refresh cannot replace last complete view |
| RCG016 | P1 | Stale source cache | Cache hides withdrawal/correction | TTL + forced refresh on consequential decision |
| RCG017 | P1 | First-party overweighting | Many first-party reports appear as consensus | Independence graph discounts same-organization cluster |
| RCG018 | P1 | Citation-count illusion | Self-citation/derivative literature inflates support | Citation count never used as truth score |
| RCG019 | P2 | Conflict/funding metadata absent | Relevant incentive correlation hidden | Optional COI/funding metadata for high-impact claims when available |
| RCG020 | P0 | License/terms violation | Research ingestion or storage exceeds allowed use | License/terms class on artifacts; restricted retention/execution paths |
| RCG021 | P0 | Protocol mutation after results | Hypothesis/metric changed to fit observed result | Immutable versioned protocol; exploratory fork after data exposure |
| RCG022 | P0 | Weak baseline | Challenger compared to intentionally poor reference | Baseline parity checklist and current tuned reference |
| RCG023 | P1 | Tuning-budget asymmetry | Challenger gets far more search than baseline | TuningBudget recorded and normalized/disclosed |
| RCG024 | P1 | Seed cherry-picking | Best seed reported as representative | Predeclared seed policy; all attempted seeds retained |
| RCG025 | P0 | Failed-run deletion | OOM/divergence removed from denominator | FailureRecord mandatory and linked to aggregate result |
| RCG026 | P1 | Early-stop bias | Candidate stopped or extended selectively | Stop rule frozen in manifest; deviations explicit |
| RCG027 | P0 | Metric switching | Primary metric changes after result visibility | Preregistration + exploratory labeling |
| RCG028 | P1 | Multiple-comparison inflation | Best of many candidates reported without search multiplicity | Attempt ledger + multiplicity accounting |
| RCG029 | P0 | Benchmark leakage | Training/search sees hidden evaluation answers | Custody capabilities + access ledger + separate promotion holdout |
| RCG030 | P0 | Evaluator drift | Judge/scorer changes across compared runs | Evaluator identity/version in manifest and result |
| RCG031 | P1 | Dataset drift | Comparison uses silently changed data | Dataset manifest digest and split identity |
| RCG032 | P1 | Hardware/runtime drift | Systems claim changes with driver/kernel/device | Environment/hardware manifest + portability scope |
| RCG033 | P1 | Clock/timing error | Unsynchronized timing produces false speedup | Monotonic clocks, synchronization, instrumentation contract |
| RCG034 | P1 | Warmup/cache/thermal confound | Cold/warm/JIT/thermal state differs by candidate | Measurement-state declaration and repeated steady-state trials |
| RCG035 | P1 | Lifecycle-cost omission | Training win hides synthesis/index/verification/ops cost | ComputeCost captures all material lifecycle dimensions |
| RCG036 | P0 | Synthetic ancestry loss | Generated data lineage becomes untraceable | Teacher/prompt/config/source ancestry mandatory |
| RCG037 | P0 | Partial checkpoint accepted | Incomplete checkpoint used as valid resume artifact | Manifest-atomic publication after digest verification |
| RCG038 | P0 | Resume semantics mismatch | Resumed run is not same experiment | Checkpoint binds optimizer/scheduler/RNG/data cursor/precision |
| RCG039 | P1 | RNG/data cursor drift | Resume changes sample order or randomness | Cursor/RNG capture + deterministic fixture |
| RCG040 | P1 | External-service nondeterminism | Hosted evaluator/provider drift makes replay impossible | Provider/version/date/fingerprint + semantic canaries |
| RCG041 | P0 | Duplicate expensive launch | Retry creates two paid jobs | Idempotency key + external reconciliation |
| RCG042 | P0 | Unknown launch outcome | Timeout leads to blind resubmit | UNKNOWN state; query provider before retry |
| RCG043 | P0 | Stale worker finalization | Expired worker writes authoritative result | Lease epoch fencing on every finalizing mutation |
| RCG044 | P0 | Budget race | Concurrent workers overspend shared budget | Transactional reservation + lease-bound spend |
| RCG045 | P1 | Priority starvation | High-cost/high-priority lane starves other research | Fairness/WIP quotas and aging policy |
| RCG046 | P1 | Scheduler gaming | Agent manipulates metadata to get priority | Priority components auditable; privileged fields not agent-controlled |
| RCG047 | P1 | Zombie run | Dead worker leaves run/resources indefinitely active | Heartbeat/lease expiry + reconciliation sweeper |
| RCG048 | P0 | Incomplete cancellation | Cancelled run continues spending or writing artifacts | Cooperative cancel + bounded escalation + final reconciliation |
| RCG049 | P1 | External orphan | Provider job exists without local ownership | External job map + orphan scanner |
| RCG050 | P1 | Provider idempotency mismatch | Provider ignores/reinterprets client idempotency | Local launch receipt + provider identity reconciliation |
| RCG051 | P0 | Blind-answer access | Research worker reads promotion answers | Capability isolation; no blind-eval capability for research principal |
| RCG052 | P0 | Derived-label leakage | Hidden answer becomes visible through derived artifacts | Derived labels inherit custody classification |
| RCG053 | P0 | Answer leakage through logs | Evaluator logs reveal hidden labels | Redaction + restricted log class + audit |
| RCG054 | P0 | Eval prompt/source committed publicly | Hidden evaluator material enters repository | Secret/eval custody scan and review |
| RCG055 | P1 | Judge-candidate correlation | Same-family evaluator shares errors with candidate | Independence edges + alternate/deterministic checks |
| RCG056 | P1 | Judge incentive gaming | Evaluator optimized toward desired conclusion | Hidden spot checks + disagreement escalation + incentive independence |
| RCG057 | P1 | Human reviewer bias | Reviewer invested in candidate outcome | Independence statement + second review for high-impact claims |
| RCG058 | P0 | Scorer tampering | Scorer code changes after outputs exist | Scorer digest/version immutable in manifest |
| RCG059 | P1 | Dynamic benchmark generator defect | Fresh task generator emits invalid/easy/leaky tasks | Generator validation + fixed anchor + expert-audit subset |
| RCG060 | P1 | Benchmark retirement ignored | Saturated/contaminated benchmark keeps deciding architecture | Health state and promotion block on retired/invalid benchmark |
| RCG061 | P0 | Research agent self-approval | Agent marks own result reproduced/accepted | Independent principal required for review/signoff |
| RCG062 | P0 | Research agent peeks hidden eval | Agent optimizes directly to promotion set | Custody capability denial + access alarm |
| RCG063 | P0 | Agent rewrites protocol | Agent changes rules after seeing result | Protocol digest frozen; mutation creates new version |
| RCG064 | P0 | Agent drops failures | Agent filters inconvenient failed runs | Run inventory generated by control plane, not agent report |
| RCG065 | P0 | Artifact fabrication | Agent invents logs/results not produced by run | Artifact receipts signed by runner/store and cross-checked |
| RCG066 | P0 | Source prompt injection to agent | Untrusted paper controls tool behavior | Content/instruction separation + policy-enforced tool authority |
| RCG067 | P0 | Research-agent privilege escalation | Agent requests stronger tools through generated text | Capabilities granted outside model text by principal policy |
| RCG068 | P0 | Cross-workspace data leak | One research task sees another tenant/project data | Workspace/tenant isolation + scoped stores |
| RCG069 | P0 | Generated-code supply-chain attack | Agent imports malicious dependency or action | Dependency allowlist/lock/SBOM/sandbox/scanners |
| RCG070 | P0 | Generated-data poisoning | Agent creates backdoored training/eval data | Lineage + poison/adversarial scan + independent evaluation |
| RCG071 | P0 | DB/blob split-brain | Metadata says artifact exists but object missing/wrong | Content digest + reconciliation + availability state |
| RCG072 | P0 | Outbox loss/duplication | State and event stream diverge | Transactional outbox + idempotent consumer + replay audit |
| RCG073 | P0 | Migration semantic corruption | Schema migration changes meaning of historical evidence | Historical fixtures + semantic migration review + rollback |
| RCG074 | P0 | Backup missing artifacts | DB restores but evidence blobs/checkpoints absent | Cross-plane restore manifest and drill |
| RCG075 | P0 | Restore duplicates live external jobs | Restored scheduler replays already-running side effects | External reconciliation before replay/launch |
| RCG076 | P0 | Audit-log tampering | Research history edited after decision | Tamper-evident append-only audit with separate authority |
| RCG077 | P0 | Signing/trust-root compromise | Forged result/review signatures appear valid | Key rotation/re-root/revocation and compromise recovery |
| RCG078 | P1 | Clock skew | Event ordering and lease expiry inconsistent | Server-authoritative/monotonic clocks + skew bounds |
| RCG079 | P0 | Deletion misses derived state | Sensitive artifact removed but index/cache/generated set remains | Tombstone propagation + derived-state inventory |
| RCG080 | P1 | Retention destroys required evidence | Cleanup removes proof needed for audit/reproduction | Retention classes + legal/audit holds + dependency checks |
| RCG081 | P1 | Claim expiry ignored | Stale conclusion silently justifies new decision | Query/promotion path rejects stale unreviewed claim |
| RCG082 | P0 | Debt retired too broadly | Toy result closes production-scale uncertainty | Retirement scope mandatory and machine-checked |
| RCG083 | P1 | Debt reopening ignored | Material model/hardware change leaves old debt closed | Reopen triggers linked to dependency graph |
| RCG084 | P1 | Contradiction prematurely resolved | One new paper erases conflicting evidence | Resolution requires scoped discriminating evidence; history retained |
| RCG085 | P0 | Scope inflation in ADR | Local result becomes universal architecture claim | ADR snapshot includes exact tested scope and untested dimensions |
| RCG086 | P1 | Negative evidence hidden | Unfavorable results not surfaced in current summary | Claim query includes strongest opposing/negative evidence |
| RCG087 | P1 | Evidence correlation undercounted | Shared code/data/provider hidden | Independence graph mandatory for consequential consensus |
| RCG088 | P1 | Fake independent reproduction | Replication reuses same hidden implementation assumptions | Independence statement + lineage analysis |
| RCG089 | P1 | Unavailable-data irreproducibility | Key result depends on inaccessible proprietary data | Mark reproduction ceiling and create local proxy debt |
| RCG090 | P1 | Portability assumption | Result assumed across scale/hardware/provider | Transfer evidence separate from source-scale evidence |
| RCG091 | P1 | Scorecard gaming | Metrics optimized for appearance rather than knowledge | No scalar score; independent dimensions + anti-gaming review |
| RCG092 | P1 | LOC/commit proxy misuse | Research productivity measured by volume | Accepted useful findings and information yield preferred |
| RCG093 | P0 | Planning/implementation confusion | Detailed plan reported as executed evidence | Separate PLANNING/REPRODUCTION/PRODUCTION states |
| RCG094 | P2 | Research bureaucracy lockup | Controls make cheap safe work impossible | C0/C1 fast path while preserving identity/audit |
| RCG095 | P1 | Reviewer backlog explosion | Agents launch more work than humans can validate | Reviewer capacity/WIP limit in scheduler |
| RCG096 | P0 | Unsafe fast-track | Reversible-looking change introduces new authority/data surface | Fast-track eligibility checks authority/privacy/state impact |
| RCG097 | P0 | Safe mode depends on failed service | Emergency path unavailable during control-plane outage | Dependency-reduced local safe-mode path |
| RCG098 | P0 | Break-glass becomes bypass | Emergency capability used for normal research | Time-bound scoped break-glass + dual audit + post-use review |
| RCG099 | P1 | Residency/jurisdiction violation | Research artifacts move across prohibited region/provider | Data class/residency metadata + placement constraints |
| RCG100 | P0 | Production-authority creep | Research subsystem gradually gains direct production mutation | Capability deny-by-default + invariant test proving no direct edge |

## P0 invariant summary

P0 research-plane invariants:

1. source text is untrusted data, never authority;
2. official status/version identity is preserved;
3. protocol/result/evaluator identities are immutable;
4. failed runs cannot disappear;
5. blind promotion answers are inaccessible to research agents;
6. agents cannot self-review or self-promote;
7. stale workers cannot finalize authoritative state;
8. external unknown outcomes are reconciled before retry;
9. budgets are transactional and fenced;
10. checkpoints/results/artifacts are digest-bound;
11. audit history is tamper-evident;
12. restore reconciles external jobs before replay;
13. deletion propagates to derived state;
14. debt retirement is scoped and evidence-backed;
15. stale claims cannot silently drive new decisions;
16. research planning cannot masquerade as reproduction;
17. safe mode remains available under partial control-plane failure;
18. break-glass is scoped, time-bound, audited and reviewed;
19. residency/privacy constraints participate in placement;
20. no research principal has direct production mutation authority.

## Fault campaigns

Required compound campaigns:

### Campaign A — source compromise
- prompt-injected paper;
- malicious archive;
- stale accepted-status cache;
- retraction during ongoing experiment.

Expected:
- no privilege escalation;
- source change receipt;
- dependent claim review;
- experiment lineage preserved.

### Campaign B — runner ambiguity
- launch response lost;
- worker network partition;
- lease expires;
- worker returns late with result.

Expected:
- one external job;
- stale finalization rejected;
- reconciled run state.

### Campaign C — benchmark compromise
- hidden-answer access attempt;
- evaluator digest changes;
- dynamic generator emits invalid examples.

Expected:
- access denied/audited;
- old result invalidated for comparison;
- benchmark state degraded/retired.

### Campaign D — restore
- DB restored from backup;
- object store has partial artifact set;
- external provider job still active;
- old worker lease token reappears.

Expected:
- no duplicate job;
- missing artifact detected;
- old lease invalid;
- reconciliation required before scheduling.

### Campaign E — research-agent gaming
- scorer exploit;
- failed-run deletion attempt;
- protocol rewrite;
- self-review attempt;
- hidden-eval access request.

Expected:
- all blocked or recorded as policy incidents;
- no debt retirement or ADR acceptance.

### Campaign F — governance pressure
- reviewer backlog;
- expensive C5 candidate;
- stale claim near promotion;
- operator requests fast-track.

Expected:
- WIP limit;
- stale claim review;
- decision-value review;
- no authority bypass.

## Audit checkpoint

~~~text
checkpoint_id: PLAN-20260922-RESEARCH-CONTROL-PLANE-GAP-AUDIT
created_at: 2026-09-22
gap_range: RCG001..RCG100
scope: Track AD research control plane
open_p0_blocks_research_authority_expansion: true
production_authority_granted: false
~~~
