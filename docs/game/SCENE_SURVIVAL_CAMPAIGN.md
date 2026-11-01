# Replay-verified offline survival campaign

`python -m skeleton scene-survival-campaign demo` runs two authored tile
survival stages through the existing movement, collision, hazards, shelter,
food and locked-exit runtime. Each stage has a unique identifier and a
nonnegative earned reward. Progression occurs **only** when the underlying
survival replay reaches `won`. The next stage starts with its own authored
initial state; earlier stage resources cannot be fabricated or carried over.

`simulate --source-json ... --actions-json ...`, `resume --session-json ...
--actions-json ...`, `verify --session-json ...`, `export --session-json
...`, and `import --bundle-json ...` provide deterministic CLI execution.
All payloads are JSON, bounded, strict-schema, and independently replayed.
Portable exports include a checksum and bind the entire stage history,
source digest, state digest and save lineage. A checksum is an integrity
check, not a signature or authentication of an untrusted publisher.

A campaign holds at most eight authored stages and 512 total actions. Invalid
or terminal actions never earn rewards. An interrupted session is resumable
from its last verified checkpoint. This vertical is not yet device-qualified
and does not replace final-head CI or release acceptance.
