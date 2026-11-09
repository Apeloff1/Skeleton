# Commerce, VIP and Tournament Promotion — 2026-09-15

## Scope

This mining batch promotes four exact-shared Lorebuffa/Openworld policy surfaces into the dependency-free frontier kernel:

| Wave | Surface | Shared source blob | Frontier target |
| --- | --- | --- | --- |
| 21 | Shop / commerce / IAP | `c7bb3661f98642bc0e4220b624bcc7fd71e25d25` | `skeleton/frontier/commerce.py` |
| 22 | VIP subscription / entitlement | `f67aedc7877bf6e8c9e6bf11d97507f426383ac1` | `skeleton/frontier/vip.py` |
| 23 | VIP daily challenge / points | `3d23e083f91053d9df6450043fc12bad7829aa51` | `skeleton/frontier/vip_daily.py` |
| 24 | Tournament lifecycle | `14d5c55aba152c7a6000c8fea7da8603dbdf18cf` | `skeleton/frontier/tournament.py` |

Each source blob is byte-identical between `Apeloff1/Lorebuffa` and `Apeloff1/Openworld`, so each behavior family is promoted once rather than duplicated.

## Wave 21 — Commerce

### Preserved policy

- level-gated shop availability;
- exact catalog costs and currency balances;
- repeatable consumables versus one-time ownership items;
- item, bait and upgrade grant planning;
- personalized deterministic daily deals;
- one-time and cooldown bundle semantics;
- currency-pack and bundle reward shapes.

### Hardening

The source `PurchaseItemRequest.quantity` is an unconstrained integer. Source cost is calculated by multiplying catalog cost by this value, followed by a negative `$inc` to deduct it. A negative quantity therefore creates a negative cost and can turn the deduction into a wallet credit. The frontier quote path accepts positive quantities only.

Source bundle/currency-pack endpoints accept IAP-shaped requests while payment verification is not a kernel invariant. The frontier never treats a client purchase request as proof of payment. Paid plans require `VerifiedPurchaseEvidence`, supplied by an external provider-verification boundary and bound to subject, product, transaction, currency and exact price. Consumed transaction IDs fail closed on replay.

Daily-deal generation no longer reseeds process-global `random`. A private SHA-256-seeded `Random` instance makes the same subject/day deterministic without perturbing unrelated randomness. Each deal also carries the semantic digest of the quoted catalog item and recomputes the discount before purchase, preventing same-ID catalog rebinding.

## Wave 22 — VIP entitlement

### Preserved policy

- Bronze through Diamond tiers;
- 30 days per purchased month;
- extension from an existing future expiry;
- one-time three-day Bronze trial;
- gem-priced subscriptions;
- USD-priced subscriptions;
- tier daily gems/coins;
- percentage benefits, flags and exclusive grants;
- cancellation of future renewal without deleting remaining entitlement.

### Hardening

The source accepts `duration_months` without a positive bound. Under gem payment a negative duration can produce a negative gem cost, turning the debit into a credit. The frontier requires a positive month count.

The source has explicit payment methods `gems`, `usd`, and `trial`, but the USD path reaches entitlement activation without a provider-verification step; unrecognized methods also bypass the gem/trial branches. The frontier exposes three separate planners instead of one stringly typed mutation path:

- `plan_gem_subscription` requires sufficient balance and returns an exact debit plan;
- `plan_trial_subscription` enforces the one-time three-day Bronze trial;
- `plan_usd_subscription` requires verified purchase evidence and consumes the transaction identity exactly once.

Expired state is normalized to the free tier before benefits or claims are computed, so stale persistence cannot continue granting paid benefits.

## Wave 23 — VIP daily / points

### Preserved policy

- player-level-gated Catch-of-the-Day difficulties;
- source fish pools, target-count ranges and base VIP points;
- tier-based VIP point multiplier;
- difficulty coin multiplier;
- cumulative point milestones that do not spend points;
- source milestone reward amounts.

### Hardening

The source claim endpoint marks the daily challenge as `claimed=True` after paying it, but does not reject a pre-existing claimed flag before paying again. Repeating the claim can therefore mint VIP points and coins from one completed challenge. Frontier state requires `completed=True`, `claimed=False`, matching subject and matching challenge date, then atomically returns a state with `claimed=True` alongside the reward plan.

The source also accepts fuzzy substring fish-name matches. Frontier progress uses exact canonical fish IDs so a different species cannot satisfy a target merely because one display name contains another token.

Challenge generation uses isolated SHA-256-seeded randomness instead of modifying process-global RNG state.

## Wave 24 — Tournament lifecycle

### Preserved policy

- coin/gem entry fees;
- participant limits;
- additive score/fish/perfect-catch statistics;
- max-style biggest-fish and combo metrics;
- score-first, biggest-fish tiebreak semantics;
- source rank reward tiers;
- minimum-cast participation rule;
- final result and payout planning.

### Hardening

Tournament creation and scoring source models allow unchecked integers. Frontier specs require a valid time window, positive participant capacity and a non-negative entry fee. Score and additive stat deltas cannot be negative.

Live source ranking sorts or counts by score alone while finalization sorts by score then biggest fish. Frontier has one canonical order everywhere: score descending, biggest fish descending, stable user ID ascending. `leaderboard`, `rank_of`, and finalization all reuse this exact ordering.

Source finalization can be invoked while the tournament is still active and awards user wallets before the tournament status is durably switched to ended. A partial failure or retry can therefore create payout replay risk. Frontier finalization is gated by `end_time`, returns no direct mutations, and emits a stable SHA-256 finalization identity over tournament identity and canonical result material. Persistence can use that identity as an idempotency boundary before applying the payout plan.

## Deliberately not promoted

The frontier kernel does not contain:

- FastAPI routers or HTTP error envelopes;
- Pydantic transport models;
- MongoDB/Motor clients;
- direct wallet or inventory writes;
- provider SDKs or receipt validation code;
- client-asserted paid entitlement activation;
- presentation catalogs, icons, colors, names or marketing copy;
- scheduled background mutation jobs.

Large catalogs and application persistence remain source-owned. Provider verification remains an external trust boundary; the kernel accepts only already-verified, tightly bound evidence.

## Evidence

Focused regression suites:

- `skeleton/testing/test_frontier_commerce_policy.py`
- `skeleton/testing/test_frontier_vip_policy.py`
- `skeleton/testing/test_frontier_vip_daily_policy.py`
- `skeleton/testing/test_frontier_tournament_policy.py`

Correctness is gated. Machine-dependent timing is not a merge criterion for these policy modules.
