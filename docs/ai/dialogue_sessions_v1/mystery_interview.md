# mystery_interview: dialogue simulation

## Scope
A deterministic, replay-safe narrative encounter for the mystery world plane. This component does not create account authority, authenticate world evidence, or generate actual dialogue prose.

## Profile
- Conversation identity: mystery_interview
- Domain: mystery
- Minimum negotiation rapport: 18
- Rapport gain: 4
- Negotiation stress: 2
- Ordered beats: opening, question, disclosure, offer, agreement, departure
- Protected evidence beats: disclosure and offer

## Runtime integration
1. Load the authoritative world-instance conversation state.
2. Authenticate the acting NPC and character access permissions.
3. Validate upstream event proof for protected narrative transitions.
4. Supply the exact optimistic state version and unique event identifier.
5. Execute the immutable `apply` transition and record its decision receipt.
6. Commit the new state and replay ledger atomically.
7. Publish downstream dialogue only after persistence succeeds.
8. Use `snapshot` for read-only UI presentation.

## Fail-closed contracts
Duplicate identities, stale versions, out-of-order dialogue beats, absent evidence and replayed proof identifiers never advance progression. Negotiation requires configured rapport. Withdrawal ends a conversation permanently unless a versioned recovery system is explicitly introduced.

## Security limitations
The proof string is structurally validated but **not authenticated**. Bind proof to real game events in the host runtime; never treat arbitrary language model output as an authorization grant. World identity, privacy and actual character dialogue remain external integration concerns.

## Testing and release
Run the associated deterministic Python regression tests. Compile the policy source, validate both JSON files, and require exact-head repository quality, security, ownership and E2E qualification. Synthetic fixtures are not player-experience or consumer-device release proof.

## Extension points
A typed parser may map natural-language NPC output to existing choices. Any new choice must carry a versioned schema migration and adversarial regression coverage. Expand localization, accessibility and narrative continuity through independent reviewed systems.
