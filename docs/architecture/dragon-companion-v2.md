# Dragon Companion v2 — executable acceptance contract
The companion lives in a half-hatched egg, with the shell cap always present. Glasses with a white bridge bandage are visible only while distilling. Crawling and knowledge ingestion remain separate authorities.

## Research autonomy boundaries
Conversation interests are bounded, user-authored topic hints. The research mission proposal is inert and requires explicit authorization before a backend crawl can be dispatched. No conversation history is sent to a search provider by this module.

## Replay contract
The visual journal accepts monotonically contiguous sequence numbers, deduplicates event IDs, rejects out-of-order events, and refuses burn/chunk/complete without an accepted acquisition and an active burn. An event gap is visible as a replay-required warning. This is a frontend safety layer, not proof of persisted indexing: the backend must supply durable completion receipts before claiming storage success.

## Remaining production gates
- Authenticated, cursor-based backend event stream, reconnect and bounded backfill
- Hash-chain or signed provenance validation; event IDs alone are not authenticity
- Explicit mission approval with source and privacy controls
- Real distillation completion event separate from burn completion
- Reduced-motion, screen-reader, low-power and battery-aware settings
- End-to-end mobile/web tests, exact-head CI and final asset fidelity pass

Status: implemented as a companion enhancement tranche; **not signed**.
