# Release security evidence

Use this checklist for release candidates and production artifact promotion. It complements the repository security policy and is intended to keep release evidence explicit rather than inferred from a successful build.

## Required evidence

- [ ] current source revision is recorded;
- [ ] dependency audit completed for production dependencies;
- [ ] SBOM generated for each deployable artifact;
- [ ] HIGH/CRITICAL container findings are resolved or have an explicit, reviewed exception;
- [ ] image and CI container references are immutable digests;
- [ ] provenance/attestation evidence is present for release artifacts;
- [ ] secret scanning completed without unresolved high-confidence findings;
- [ ] malware/IOC and artifact-integrity checks completed;
- [ ] canonical Merge Readiness evidence covers the release revision;
- [ ] known residual risks and any external/admin-only controls are recorded.

## Fail-closed rule

Missing evidence is not equivalent to a clean result. If a required producer cannot run, produces malformed output, or cannot bind evidence to the exact release revision, promotion should stop until the evidence is regenerated or an explicit exception is reviewed through the repository's documented security process.

## Binding evidence to a revision

Record the exact commit SHA and artifact digest alongside each result. Do not rely on branch names, mutable tags, timestamps alone, or an earlier CI run when the release revision has changed.

This document is a checklist, not proof that every control is currently implemented or enforced by GitHub repository settings.
