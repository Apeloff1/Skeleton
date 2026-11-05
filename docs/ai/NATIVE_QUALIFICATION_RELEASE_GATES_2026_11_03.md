# Native AI qualification is not release certification

Model scores and code quality are independent claims. This package publishes
bounded performance evidence but **never** makes the final merge/release
decision. A perfect 480/480 model score alone is insufficient.

Required independent CI and source gates: Merge Readiness, Backend Quality,
App Foundation E2E, Workflow Input Security, Sealed Context Guard, Artifact
Policy, Malware Gate, Repository Hygiene, Secret Scanning, Dependency Review
and exact base/head provenance; all on the final change SHA.

Required runtime and consumer gates: approved checkpoint license,
unmodified tokenizer/model activation, actual native first-generation,
restart recovery, cross-process custody, true context window admission,
memory and data deletion, device RAM/CPU/GPU limits, clean offline install,
quantized-model fidelity, binary artifact verification and external rights
review. Unavailable or skipped evidence is a hold.

This draft intentionally includes no weight file, no 1.9GB package and no
claim of passing model quality. Original task scores only exist after the
operator runs the true native backend with recorded evidence. This runbook
must not be used to bypass branch protection or auto-merge checks.
