# Cooperative campaign handoff

The `scene-market-party-handoff` command closes a source→play→fork→save→rank→export vertical without introducing a second economy or inventing rewards. It reads a canonical cooperative market checkpoint from an existing save slot, replays a chosen prefix and a bounded set of turns, and requires an earned winning state. It then stages a **new** save slot with optimistic revision checks, records a ranked attempt through the existing league reducer, and exports a portable portfolio.

## Commands

`python -m skeleton scene-market-party-handoff accept` runs the original playable campaign, forks it halfway, resumes the winning turns, writes the branch to a separate vault slot, ranks the earned result, verifies all exports and returns a compact receipt.

`plan --vault-json ... --league-json ... --from-slot campaign --to-slot branch --sequence N --turns-json '[...]' --attempt-id branch-win --expected-vault-revision R --expected-league-revision L` returns a checksummed transaction with source, fork, save, ranking and portfolio witnesses. The input may be literal JSON or the repository's supported JSON argument form.

`verify --vault-json ... --league-json ... --receipt-json ...` independently rebuilds the exact transaction from the original parents. `apply` performs the same validation and materializes the updated vault, league, playable checkpoint and portable portfolio. Neither operation changes its input documents.

## Safety and scope

A source slot cannot be overwritten. The target slot must not exist, both revision leases must be exact integers, attempts must be unique, and the child must reach the canonical earned-victory phase. Every replay is source-bound. The final receipt is bounded to 8 MiB and has a deterministic checksum; a recomputed checksum on a forged receipt cannot bypass reconstruction. This is **offline integrity**, not actor authentication, online consensus, a cryptographic signature, or device-release qualification.

Focused tests cover replay equivalence, CAS conflicts, source confusion, forged nested receipts, malformed identifiers, incomplete gameplay, portable exports, CLI dispatch and deterministic acceptance.
