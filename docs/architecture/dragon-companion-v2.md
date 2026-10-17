# Dragon Companion v2 — executable acceptance contract
The companion lives in a half-hatched egg, with the shell cap always present. Glasses with a white bridge bandage are visible only while distilling. Crawling and knowledge ingestion remain separate authorities.

## Research autonomy boundaries
Conversation interests are bounded, user-authored topic hints. The research mission proposal is inert and requires explicit authorization before a backend crawl can be dispatched. No conversation history is sent to a search provider by this module.

## Replay contract
The visual journal accepts monotonically contiguous sequence numbers, deduplicates event IDs, rejects out-of-order events, and refuses burn/chunk/complete without an accepted acquisition and an active burn. An event gap is visible as a replay-required warning. This is a frontend safety layer, not proof of persisted indexing: the backend must supply durable completion receipts before claiming storage success.

## Production gates
- Authenticated cursor replay: `GET /api/dragon-academy/crawler/feed` prefers the signed-in account's latest non-deleted canonical crawler checkpoint. Operational events are projected at read time into companion wire events. The projection does not burn, distill, copy page text, or create reviewed knowledge. The practice-lab journal is the fallback when no checkpoint is stored or crawler storage cannot be read. `after_sequence` plus optional `last_event_digest` must match that event's digest or the route returns 409 and does not fall back. The companion resets and backfills after 409. A retained tail older than the first checkpoint event reports `history_truncated`; the client continues from that tail instead of inventing the missing prefix. This is bounded polling, not a new stream service.
- Hash chain: journal pages include `previous_digest` and `digest`. The reducer rejects a broken cursor, a digest that is not the event id, and a later event that drops provenance. The chain detects tampering. It is not a signature, a review, or training permission.
- Mission approval: `approveResearchMission` requires explicit approval, research privacy, and at least one public host. The result keeps `includeConversationHistory: false` and does not dispatch a crawl. Opening capture copies the topic words and offers each approved host as an `https` seed line. Consent stays off until the operator turns it on.
- Distillation: `distill_complete` is a separate event. The burn receipt still enters distillation. Sealing requires `distilled: true` after that burn and removes the glasses. Capture events never light the fire or the glasses.
- Comfort: system reduced motion, an explicit low-power choice, a screen reader, and battery-saver animation reduction all stop decorative motion. Low battery also slows the academy feed poll. Petting stays cosmetic.
- Still open: end-to-end mobile and web tests, exact-head CI, and a final asset-fidelity pass. Those are not claimed by this tranche.

Status: canonical crawl checkpoints project into the companion feed on the existing owners; **not signed**.
