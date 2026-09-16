# B001 — explicit artifact lineage

## Intent

Advance B001 (Repository intelligence spine) by connecting repository/build inputs to explicit Docker container stages and Compose service artifacts without guessing arbitrary command outputs.

## Changed behavior / paths

- `scripts/repo_intel_artifacts.py`
  - parses explicit Compose build context/dockerfile/target declarations;
  - parses Dockerfile stages and COPY/ADD relations;
  - resolves exact tracked file inputs and bounded directory selectors;
  - keeps dynamic, glob, missing, or unparsed inputs as unresolved evidence;
  - links stage-to-stage copies and Compose service targets;
  - computes explicit artifacts affected by changed source/selectors.
- `repo-intel/artifact-lineage-contract.json`
  - forbids arbitrary shell-output inference and unbounded directory fanout.
- `scripts/repo_intel_frontier.py`
  - merges artifact nodes/edges into the frontier graph;
  - writes `artifact-lineage.json`;
  - surfaces affected artifacts in `impact.json`;
  - adds `query --kind artifact` and artifact diagnostics/metrics.
- `tests/test_repo_intel_artifacts.py`
  - covers Compose context parsing, Docker file/directory/stage lineage, unresolved selectors, and forward artifact impact.
- CI/config/query/agent/merge-readiness contracts now require the artifact layer.

## Validation evidence

The focused Repository Intelligence workflow compiles `scripts/repo_intel_artifacts.py` and runs `tests/test_repo_intel_artifacts.py` with the rest of the index regression suite. The current branch’s real root/backend/frontend Dockerfiles and Compose contexts provide integration evidence when the frontier snapshot executes.

## Security impact

Positive/neutral. Dynamic or ambiguous inputs are surfaced rather than guessed. Secret values are never indexed. Artifact lineage augments supply-chain reasoning but does not claim SBOM, signature, provenance attestation, or vulnerability status.

## Quality / performance impact

Directory COPY inputs are represented by bounded selector nodes with counts/samples instead of one edge per tracked file, avoiding graph blow-up. The parser is stdlib-only and linear over the small set of Docker/Compose build declarations.

## Dependency / Dependabot impact

No new dependency. Dependabot configuration unchanged.

## Architecture / supply-chain / runtime-surface effect

The knowledge graph now connects tracked files/selectors → container stages → Compose services where declarations are explicit. `impact.json.affected_artifacts` exposes release-adjacent blast radius alongside code/test/security impact.

## Remaining noticeable gaps / next augmentation

- Link Compose-file changes themselves to service artifacts in forward impact, not only source/Dockerfile inputs.
- Add explicit workflow upload/release artifact declarations when present; do not infer arbitrary shell outputs.
- Add artifact hashes/attestations from real build evidence so declared lineage can be compared to produced artifacts.
- Add stored base snapshots for deleted-edge semantic/artifact diffs.
