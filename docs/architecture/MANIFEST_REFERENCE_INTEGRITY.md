# Manifest Reference Integrity

<!-- machine-git-blob: machine/manifest_reference_policy.json@22df0ae36845e420314dff9f4ef8008e78db2596 -->

Machine authority: `machine/manifest_reference_policy.json`

This control implements VOL-054's manifest-reference and generated-document binding gaps.

The validator resolves critical repository-path references from canonical machine manifests and fails when targets disappear or path spelling becomes non-canonical. It also computes Git blob identities for selected machine authorities and requires their human architecture documents to contain the exact current digest marker.

A matching digest proves identity/synchronization only. It does not promote capability maturity or replace executable evidence.
