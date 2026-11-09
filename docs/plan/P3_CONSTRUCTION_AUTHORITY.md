# P3 Construction Authority

This layer implements the remaining P3 construction/manual and technology-radar
contracts without granting itself phase-completion authority.

Construction packets are deterministic projections of explicit machine sources.
They must contain authority, scope, work, evidence, unresolved, and handoff
sections. They always carry `completion_authority=false`.

The technology radar is a bounded state machine:

`watch -> trial/hold/exit`
`trial -> adopt/hold/exit`
`adopt -> hold/exit`
`hold -> watch/trial/exit`

Adoption requires an ADR plus at least two evidence references. Vendor-backed
candidates must retain an explicit exit or migration criterion, preventing a
trial from silently becoming permanent lock-in.

P3-CONSTRUCTION-AUTHORITY-01 remains dependency-fenced until
P3-ACCEPTANCE-01 is evidence-landed.
