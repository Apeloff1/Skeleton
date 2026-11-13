# Studio A — source-leased offline review editor

The original-world `world-factions` and `world-evidence` CLI commands now
support `editor --world-id ID --expected-digest DIGEST` and
`verify-editor --world-id ID`. The editor emits an offline CSP-hashed HTML
workbench and source-bound receipt. It displays the canonical authored JSON,
lets the author type a JSON `{"action":"...","value":...}` request, and
downloads the request without mutating or approving the source.

Run `edit --world-id ID --expected-digest DIGEST
--operation-file ID.factions.operation.json` (or evidence equivalent) to
submit the request. The server-side typed edit validator, not JavaScript,
decides whether it is valid. Every accepted edit revokes approval; a fresh
operator review and compile are required. The digest is a revision fence,
not proof of a user's identity.

The workbench does not access the network, accept arbitrary HTML, execute
source text, or bypass provenance/rights policy. A hash-based CSP allows
only the bundled script; embedded authored strings are JSON escaped.
Verification regenerates the exact HTML and receipt from the current
canonical source and refuses stale or forged artifacts. The editor is
an authoring aid, not a standalone game or a release certification.
