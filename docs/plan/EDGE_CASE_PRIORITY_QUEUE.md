# Critical / High Edge-Case Priority Queue

Architecture lane: `PR #1904 / integration/architecture-map-v1`

Machine queue: [`machine/ai_edge_case_priority_queue.json`](../../machine/ai_edge_case_priority_queue.json)

This queue extracts the highest-risk obligations from the full historical/edge catalogue.

- P0 critical cases: **36**
- P1 high cases: **21**
- Total prioritized cases: **57**

A case remains open until it has passing executable evidence or an explicit accepted-risk disposition. Merely naming a future test does not close it.

| Rank | ID | Priority | Domain | Owners | Evidence modes | Title |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | `HIST-SYS-019` | P0 | security | WP-W00, WP-W01, WP-W13, WP-W14, WP-W15, WP-W20, WP-W27 | design_review, adversarial, negative_test, adversarial_eval, integration | Capability security |
| 2 | `OBSCURE-018` | P0 | context security | WP-W07, WP-W08, WP-W10, WP-W14, WP-W17, WP-W20, WP-W30 | adversarial, negative_test, adversarial_eval, integration | Compression changes trust geometry |
| 3 | `EDGE-CONTRACT-010` | P0 | text/security | WP-W00, WP-W01, WP-W10, WP-W14, WP-W20, WP-W29 | property, fuzz, adversarial, negative_test | Zero-width and confusable characters |
| 4 | `EDGE-CONTRACT-009` | P0 | text/security | WP-W00, WP-W01, WP-W10, WP-W18, WP-W20 | property, fuzz, adversarial, negative_test | Bidirectional control characters |
| 5 | `EDGE-DATA-010` | P0 | privacy/recovery | WP-W07, WP-W14, WP-W19, WP-W20, WP-W30 | fault_injection, property, recovery_drill, integration, adversarial_eval | Backup retains deleted sensitive data |
| 6 | `EDGE-SEC-008` | P0 | portability/security | WP-W13, WP-W20, WP-W23, WP-W24, WP-W29 | adversarial, negative_test, platform_test, e2e | Windows reserved device names |
| 7 | `EDGE-SEC-009` | P0 | filesystem security | WP-W13, WP-W20, WP-W22, WP-W24, WP-W27 | adversarial, negative_test, platform_test, adversarial_eval, integration | Alternate data streams |
| 8 | `EDGE-AI-001` | P0 | AI security | WP-W10, WP-W14, WP-W17, WP-W20 | adversarial, negative_test, adversarial_eval, integration | Indirect prompt injection in retrieved document |
| 9 | `EDGE-AI-002` | P0 | AI security | WP-W10, WP-W13, WP-W14, WP-W20 | adversarial, negative_test, adversarial_eval, integration | Instruction laundering through tool output |
| 10 | `EDGE-AI-013` | P0 | context/security | WP-W10, WP-W14, WP-W20, WP-W30 | adversarial, negative_test, adversarial_eval, integration | Policy trimmed from long context |
| 11 | `EDGE-AI-030` | P0 | authority | WP-W11, WP-W14, WP-W20, WP-W26 | adversarial, negative_test, adversarial_eval, integration | Hallucinated authorization |
| 12 | `EDGE-CONTRACT-001` | P0 | serialization | WP-W01, WP-W18, WP-W20, WP-W22 | property, fuzz, adversarial, negative_test | Duplicate JSON object keys |
| 13 | `EDGE-CONTRACT-020` | P0 | provenance/security | WP-W00, WP-W01, WP-W20, WP-W30 | property, fuzz, adversarial, negative_test | Canonicalization before signing |
| 14 | `EDGE-SEC-005` | P0 | artifact security | WP-W13, WP-W14, WP-W20, WP-W27 | adversarial, negative_test, recovery_drill, integration | Zip Slip |
| 15 | `EDGE-SEC-006` | P0 | artifact security | WP-W13, WP-W14, WP-W20, WP-W27 | adversarial, negative_test, recovery_drill, integration, adversarial_eval | Tarbomb / decompression bomb |
| 16 | `EDGE-SEC-007` | P0 | artifact security | WP-W13, WP-W14, WP-W20, WP-W27 | adversarial, negative_test, recovery_drill, integration, adversarial_eval | Archive symlink chain |
| 17 | `OBSCURE-024` | P0 | tool security | WP-W10, WP-W13, WP-W14, WP-W20 | adversarial, negative_test, fault_injection, property, adversarial_eval, integration | Tool description is attacker-controlled context unless curated |
| 18 | `EDGE-AI-021` | P0 | routing/privacy | WP-W06, WP-W20, WP-W30 | fault_injection, property, adversarial_eval, integration | Fallback changes privacy boundary |
| 19 | `EDGE-DATA-009` | P0 | privacy | WP-W07, WP-W08, WP-W20 | regression | Data retention applies to source but not derived embedding |
| 20 | `EDGE-SEC-001` | P0 | security | WP-W14, WP-W20, WP-W27 | adversarial, negative_test | TOCTOU authorization race |
| 21 | `EDGE-SEC-011` | P0 | network security | WP-W13, WP-W14, WP-W20 | adversarial, negative_test | DNS rebinding |
| 22 | `EDGE-SEC-015` | P0 | secrets/observability | WP-W02, WP-W20, WP-W21 | adversarial, negative_test | Secret in exception/log payload |
| 23 | `EDGE-SEC-016` | P0 | process security | WP-W02, WP-W13, WP-W20 | adversarial, negative_test | Environment-variable inheritance |
| 24 | `EDGE-SEC-018` | P0 | process security | WP-W13, WP-W20, WP-W24 | adversarial, negative_test, platform_test | Shell quoting divergence |
| 25 | `HIST-SYS-020` | P0 | security | WP-W13, WP-W14, WP-W20 | design_review, adversarial, negative_test, adversarial_eval, integration | Saltzer–Schroeder principles |
| 26 | `OBSCURE-025` | P0 | tool security | WP-W10, WP-W13, WP-W20 | adversarial, negative_test, fault_injection, property, adversarial_eval, integration | Capability discovery can become privilege discovery |
| 27 | `EDGE-AI-003` | P0 | memory security | WP-W07, WP-W20 | adversarial, negative_test, adversarial_eval, integration | Memory poisoning |
| 28 | `EDGE-SEC-002` | P0 | filesystem security | WP-W13, WP-W20 | adversarial, negative_test, platform_test | Symlink escape |
| 29 | `EDGE-SEC-003` | P0 | filesystem security | WP-W13, WP-W20 | adversarial, negative_test, platform_test, adversarial_eval, integration | Hardlink aliasing |
| 30 | `EDGE-SEC-004` | P0 | filesystem/web security | WP-W13, WP-W20 | property, fuzz, adversarial, negative_test, platform_test | Path traversal after decoding |
| 31 | `EDGE-SEC-012` | P0 | network security | WP-W13, WP-W20 | adversarial, negative_test | Redirect crosses egress boundary |
| 32 | `EDGE-SEC-013` | P0 | network security | WP-W13, WP-W20 | adversarial, negative_test | Metadata-service SSRF |
| 33 | `EDGE-SEC-014` | P0 | network security | WP-W13, WP-W20 | adversarial, negative_test | IPv4-mapped IPv6 bypass |
| 34 | `EDGE-SEC-017` | P0 | filesystem security | WP-W13, WP-W20 | adversarial, negative_test, platform_test | Temporary-file race |
| 35 | `EDGE-SEC-019` | P0 | process security | WP-W13, WP-W20 | adversarial, negative_test, fault_injection, property | Executable shadowing via PATH |
| 36 | `HIST-SYS-021` | P0 | information security | WP-W14, WP-W20 | design_review, adversarial, negative_test, adversarial_eval, integration | Bell-LaPadula / Biba |
| 37 | `HIST-AI-002` | P1 | planning | WP-W01, WP-W11, WP-W12, WP-W13, WP-W17, WP-W25, WP-W26, WP-W30 | design_review, fault_injection, property, adversarial_eval, integration | STRIPS planning |
| 38 | `EDGE-DIST-020` | P1 | autonomy/reliability | WP-W11, WP-W12, WP-W15, WP-W16, WP-W19, WP-W28, WP-W29 | fault_injection, property, adversarial_eval, integration | Livelock |
| 39 | `EDGE-DIST-021` | P1 | concurrency | WP-W11, WP-W12, WP-W13, WP-W16, WP-W18, WP-W19, WP-W29 | fault_injection, property, adversarial_eval, integration | Deadlock |
| 40 | `HIST-SYS-003` | P1 | formal workflow | WP-W01, WP-W11, WP-W12, WP-W18, WP-W19, WP-W26 | design_review, fault_injection, property | Petri nets |
| 41 | `EDGE-DATA-002` | P1 | artifact lifecycle | WP-W03, WP-W20, WP-W25, WP-W27, WP-W30 | fault_injection, property, recovery_drill, integration | Orphaned blob after metadata rollback |
| 42 | `EDGE-DATA-007` | P1 | migration/release | WP-W03, WP-W16, WP-W25, WP-W29, WP-W30 | fault_injection, property, recovery_drill, integration | Rollback code cannot read new data shape |
| 43 | `EDGE-DIST-010` | P1 | distributed failure | WP-W03, WP-W14, WP-W18, WP-W19, WP-W29 | fault_injection, property, adversarial_eval, integration | Split brain |
| 44 | `EDGE-DIST-027` | P1 | eventing | WP-W04, WP-W13, WP-W19, WP-W22, WP-W29 | fault_injection, property | Consumer commits side effect before inbox marker |
| 45 | `OBSCURE-005` | P1 | distributed operations | WP-W05, WP-W11, WP-W13, WP-W19, WP-W29 | fault_injection, property, adversarial_eval, integration | Timeout means unknown, not failed |
| 46 | `OBSCURE-010` | P1 | distributed data | WP-W03, WP-W08, WP-W20, WP-W25, WP-W29 | fault_injection, property, recovery_drill, integration, adversarial_eval | Read repair can resurrect stale data |
| 47 | `OBSCURE-029` | P1 | artifacts | WP-W00, WP-W03, WP-W25, WP-W27, WP-W30 | property, fuzz, recovery_drill, integration, adversarial_eval | Hash-based CAS still needs metadata migrations |
| 48 | `EDGE-DATA-005` | P1 | recovery | WP-W03, WP-W17, WP-W19, WP-W30 | fault_injection, property, recovery_drill, integration, adversarial_eval | Corrupt backup discovered only during restore |
| 49 | `HIST-SYS-025` | P1 | runtime state | WP-W00, WP-W18, WP-W25, WP-W30 | design_review, recovery_drill, integration, adversarial_eval | Smalltalk image persistence |
| 50 | `OBSCURE-014` | P1 | operations | WP-W03, WP-W17, WP-W19, WP-W30 | fault_injection, property, recovery_drill, integration, adversarial_eval | Backups are write-only until restoration is proven |
| 51 | `OBSCURE-021` | P1 | economics | WP-W05, WP-W06, WP-W21, WP-W30 | regression | Unknown usage must stay unknown |
| 52 | `EDGE-CONTRACT-013` | P1 | internationalization | WP-W01, WP-W23, WP-W29 | property, fuzz, e2e | Locale-sensitive casing |
| 53 | `EDGE-DATA-001` | P1 | data lifecycle | WP-W03, WP-W07, WP-W20 | recovery_drill, integration | Tombstone resurrection |
| 54 | `EDGE-DATA-006` | P1 | migration | WP-W03, WP-W25, WP-W30 | property, fuzz, recovery_drill, integration | Migration partially applied |
| 55 | `EDGE-DIST-007` | P1 | leases | WP-W16, WP-W22, WP-W29 | fault_injection, property | Stale lease holder resumes |
| 56 | `EDGE-DIST-024` | P1 | database | WP-W03, WP-W18 | regression | Write skew under snapshot isolation |
| 57 | `OBSCURE-007` | P1 | data lifecycle | WP-W07, WP-W27 | recovery_drill, integration, adversarial_eval | Garbage collection is part of data architecture |
