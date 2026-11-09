# Reviewed game-builder knowledge — operational milestone

## Implemented behavior

The canonical owner is skeleton/ai/game_builder. The module
reviewed_knowledge.py turns **explicitly reviewed, exact-span research notes**
into a persistent, revisioned SQLite knowledge library for the game builder.
knowledge_cli.py exposes local ingestion and retrieval. This is an executable
knowledge storage/retrieval implementation, not a new provider or crawler.

An active revision requires a named reviewer, declared license identifier,
explicit use scopes, full-content digest, observation time, and at least one
reviewed finding with an exact source span. Findings carry a mechanic, stance,
dependence group and confidence **estimate** (ppm). The source body is used to
verify the span and is **not retained**. Only bounded excerpts, findings and
provenance are stored, allowing an authorized custodian to revalidate the source
digest later against the independently held original.

Each source has an append-only revision chain. An importer must present the
previous digest when revising, preventing blind stale writes. Latest revisions
supersede earlier claims. A retracted revision removes a source from retrieval
while retaining history until owner erasure. Owners are partitioned by SQLite
primary key and all queries. Store reads validate canonical JSON, revision
parents, content hashes and observation chronology before serving evidence.

Retrieval enforces rights per request and ranks words found in the mechanic,
statement, tags, and source title. By default, repeated statements from a
shared dependence group, mechanic and stance count once. The library preserves
opposing evidence rather than deciding truth. A brief contains verified
citations, source offsets/excerpts, library root, contradiction warnings,
source-group count and a mandatory human-decision flag. Revalidation rejects
stale briefs or substituted citations.

## Reviewed JSON input example

Save this UTF-8 JSON document in reviewed-source.json:

~~~json
{
  "owner": "demo-studio",
  "source_id": "movement-study-01",
  "source_url": "https://example.org/authorized-research",
  "title": "Reviewed movement study",
  "text": "Jump timing should remain predictable.",
  "observed_at": "2026-10-08T12:00:00Z",
  "license_id": "operator-supplied-license-id",
  "allowed_scopes": ["design_reference", "research"],
  "reviewer_id": "human-reviewer-id",
  "approved": true,
  "notes": [
    {
      "note_id": "jump-timing-01",
      "mechanic": "platforming",
      "statement": "Jump timing should be readable and predictable.",
      "start": 0,
      "end": 38,
      "stance": "supports",
      "confidence_ppm": 850000,
      "dependence_group": "original-observer-group",
      "tags": ["platforming", "timing"]
    }
  ],
  "status": "active"
}
~~~

Offsets are Python Unicode-codepoint offsets into the source text, not byte
offsets. The full excerpt is 38 characters long. A quote must fit the 1000
character default span limit and the input source must fit 1,000,000 characters.
A rights declaration is **not a license-verification service**. The trusted
operator is responsible for checking acquisition, retention, consent, and use
rights before admitting material.

## Local operator workflow

All commands use an operator-managed SQLite file. The explicit
--trusted-local-operator flag acknowledges that the embedding process already
authenticated the operator. **The switch itself is not authentication** and
must not be exposed as an HTTP permission check.

~~~bash
python -m skeleton.ai.game_builder.knowledge_cli \
  --store ./game-knowledge.sqlite3 --trusted-local-operator \
  import --input ./reviewed-source.json

python -m skeleton.ai.game_builder.knowledge_cli \
  --store ./game-knowledge.sqlite3 --trusted-local-operator \
  query --owner demo-studio --text "platforming jump" \
  --scope design_reference --limit 12

python -m skeleton.ai.game_builder.knowledge_cli \
  --store ./game-knowledge.sqlite3 --trusted-local-operator \
  brief --owner demo-studio --text "platforming" \
  --minimum-independent-groups 1

python -m skeleton.ai.game_builder.knowledge_cli \
  --store ./game-knowledge.sqlite3 --trusted-local-operator \
  history --owner demo-studio --source-id movement-study-01
~~~

To revise, advance observed_at and use import --expected-parent with the
previous receipt's revision_digest. For a revocation, submit a newer record with
status "retracted", approved false and notes []. To erase **every** retained
revision and excerpt of an owner:

~~~bash
python -m skeleton.ai.game_builder.knowledge_cli \
  --store ./game-knowledge.sqlite3 --trusted-local-operator \
  erase-owner --owner demo-studio --confirm-erasure demo-studio
~~~

Full privacy erasure also requires clearing operator-managed backups, WAL
archives, original source copies and downstream derived artifacts.

## Programmatic builder handoff

~~~python
from skeleton.ai.game_builder import ReviewedKnowledgeStore

with ReviewedKnowledgeStore("./game-knowledge.sqlite3") as library:
    brief = library.build_brief(
        "demo-studio", "platforming", scope="design_reference",
        min_independent_groups=1, authorized=True,
    )
    library.require_fresh_brief(brief, authorized=True)
    research_payload = brief.to_payload()
    # A separately authorized producer can use research_payload as
    # untrusted, structured evidence and request human design approval.
~~~

Do not promote excerpts into system instructions or auto-execute their contents.
Source statements are evidence to evaluate, not commands to the assistant, game
engine or CI. Existing candidate, evaluator, rights and release gates own all
game-builder promotion authority.

## Independent rights-cleared design handoff

Use the existing game-builder rights authority to check more than an imported
rights label. The library's source identifier, content SHA-256 and license
identifier must match a separately registered SourceRecord in RightsLedger.
High-risk unresolved similarity findings, forbidden use, missing licenses and
stale research all prevent a cleared design-reference handoff.

~~~python
from skeleton.ai.game_builder import (
    ReviewedKnowledgeStore,
    RightsLedger,
    clear_research_for_design,
    require_cleared_research_current,
)

rights = RightsLedger()
# The host must independently register real SourceRecords with reviewed
# EvaluatorProvenance and the same exact source IDs/body digests/licenses.
with ReviewedKnowledgeStore("./game-knowledge.sqlite3") as library:
    brief = library.build_brief(
        "demo-studio", "platforming", authorized=True,
    )
    packet = clear_research_for_design(
        library, brief, rights, project_id="my-original-game",
        artifact_digest="a" * 64, human_approved=True, authorized=True,
    )
    require_cleared_research_current(
        packet, library, rights, authorized=True,
    )
    # packet.to_payload() is untrusted structured research for the
    # existing game-builder producer, not code, release or training authority.
~~~

This bridge reuses the canonical RightsLedger. It cannot infer source rights,
authenticate an operator, approve expressive asset copying, or validate
real-world source ownership. It requires registered rights records before use
and conservatively rejects changed rights ledgers until rebuilt.

## Recovery, reliability, security and economics

- BEGIN IMMEDIATE serializes writer state changes. Optimistic parent-digest
  fencing prevents stale revision replacement. A crash before commit leaves no
  half-revision. SQLite WAL is not physical redundancy or distributed consensus.
- Integrity checking rejects invalid JSON, noncanonical payloads, mismatched
  hashes, duplicate keys and broken ancestry. SHA-256 does not authenticate
  authors or protect a whole-store rewrite by a privileged attacker. Higher
  assurance requires independent signatures and durable witnesses.
- Imports, stored excerpts, query results, and total owner revision scans have
  hard limits. The bounded path is deliberately suitable for local/medium scale
  vetted source libraries; it does not claim web-scale ingestion.
- Source titles, reviews, excerpts and rights IDs can be confidential. The
  embedding application must enforce authentication, encryption, backups,
  retention, monitoring, incident response and owner-authorized erasure.
- The estimated confidence field is reviewer-supplied, not calibrated ground
  truth. Source dependence likewise requires reviewer diligence.
- A source with training_candidate scope has **no authority to train or
  promote weights**. Separate training data-rights, contamination,
  time-leakage, candidate, and model-release gates remain mandatory.
- Changed source rights are represented by a superseding revision. Downstream
  exports must check freshness; retraction alone does not delete previously
  copied research packets.
- Capacity controls avoid unbounded memory/cost, but a large owner scan remains
  linear in retained revisions. Improve indexing under canonical ownership as
  demand grows; do not silently bypass limit enforcement.

## Verification and closeout

~~~bash
python -m unittest tests.test_game_builder_reviewed_knowledge \
  tests.test_game_builder_knowledge_cli \
  tests.test_game_builder_knowledge_rights_bridge -v
python scripts/check_ai_file_tree.py
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
~~~

The milestone implements governed local research admission, immutable custody,
safe querying and a citation-bearing design handoff. It does not implement
unrestricted browsing, a model trainer, automated copyright determination,
signature trust, source-code synthesis, or an actual published game. Masterplan
completion requires independent validation, exact-head CI, and signed release
evidence; the PR is not a completion signature.
