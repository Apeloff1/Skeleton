# Manifest Reference Integrity

<!-- machine-git-blob: machine/manifest_reference_policy.json@c53d7e58cc0bc9a1314c865081f7f567de920068 -->

Machine authority: `machine/manifest_reference_policy.json`

This control implements VOL-054's manifest-reference and generated-document binding gaps.

The validator resolves critical repository-path references from canonical machine manifests and fails when targets disappear or path spelling becomes non-canonical. It also computes Git blob identities for selected machine authorities and requires their human architecture documents to contain the exact current digest marker.

A matching digest proves identity/synchronization only. It does not promote capability maturity or replace executable evidence.
