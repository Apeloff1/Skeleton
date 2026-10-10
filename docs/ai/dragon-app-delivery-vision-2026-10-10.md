# Dragon: a connected research, design and making journey

This increment turns previously separate Dragon capabilities into a usable journey in the companion. It does not certify the entire Dragon vision as complete. Completion is measured by executable user journeys and deployment evidence, not a percentage of source files or catalog entries.

## The product vision and its current boundaries

| Journey | Available foundation and this increment | Still required for the full vision |
| --- | --- | --- |
| Discover gaming and engineering knowledge | Existing source catalog, sequential acquisition jobs and topic Almanakks; the companion now exposes source counts, pipeline stages and next actions. | Qualify sustained live acquisition, source-specific failures, coverage and operating costs. A discovered URL is not acquired or reviewed knowledge. |
| Distil and challenge knowledge | Existing reviewed source store, independent Wiki review, separate signed Hoag approval, sparse advisory memory and recrawl lifecycle; the new search exposes distilled statements with exact revision and approval lineage. | Qualify autonomous reviewer quality and adversarial coverage. Retrieval and signed review are not trained neural weights. |
| Explore an organized knowledge world | Browse paginated Almanakks, inspect project findings and identify stale source dependencies from the companion. | Rich topic navigation, large-corpus usability studies and measured recall/precision across actual owner collections. |
| Shape an original game | Edit target, supported genre, title and seed; desktop emitters also consume their supported stage, difficulty, palette, theme, candidate and hero settings. The brief separates effective controls from metadata. | General engine construction, arbitrary mechanics and content synthesis, richer authoring, asset workflows, and verified support for every desired system. Catalog entries do not imply emitters. |
| Deliver traceable source | Generate through the existing shared resource scheduler using a current approved brief. Download a native source archive containing the exact design and citations through the existing native workshop. | Compilation and gameplay evidence on each supported target; source generation is not a compiled or playtested game. Existing compiler adapters cover a subset of source emitters. |
| Learn from making | Each committed project produces an idempotent Almanakk source-synthesis finding with lineage. Failed projection writes can be recovered without regenerating the game. | Measured play sessions, controlled experiments, validated generalization and reviewed promotion of genuinely new findings. A synthesis journal is not empirical learning. |
| Run quietly as a standalone companion | Existing scheduling, resource admission and owner isolation govern the new generation path. Offline operator commands inspect knowledge and prepare briefs without provider calls. | Packaged consumer deployment, sustained memory/CPU/thermal/battery measurements, crash/update drills and platform qualification. Local route tests do not establish this. |

## The connected user experience

Open the Dragon Academy and use the delivery workbench. Explore knowledge by mechanic or design question; inspect the source title, distilled statement, confidence and current approval. Browse Almanakks and inspect their project findings. Switch to design, choose a supported target/style and edit the controls the emitter actually consumes. Preparing a brief resolves the current source revisions, independent support and blockers. Generation requires explicit approval of that exact brief.

The brief is useful even when blocked: unsupported target/style, insufficient independent approved support or source contradictions remain visible. The server reconstructs the brief before generation. Editing the design, changing knowledge, revoking approval or reaching the five-minute maximum expiry requires a new brief. Browser state cannot promote knowledge or supply authoritative citations.

Successful generation refreshes the existing native workshop, where the source archive is available. The workbench reports source generation separately from compilation and gameplay. Its learning projection is explicitly `source_synthesis`; it carries no training, memory promotion or release authority. If the artifact committed but its Almanakk projection failed, the recovery control rebuilds that projection from the persisted artifact.

## Construction coverage, L00–L13

| Layer | Concrete implementation and acceptance |
| --- | --- |
| L00 — intent | An owner can move from reviewed knowledge to an editable, original native source project with inspectable provenance. |
| L01 — architecture | `DragonDelivery` composes existing reviewed knowledge, Wiki/Hoag, Almanakk and native practice owners. No service, runtime root or provider boundary is added. |
| L02 — contracts | `game.native_delivery`, brief/request schemas and existing-owner state domains are declared in the machine contracts. |
| L03 — authority | Principal derives from authentication; strict request parsing rejects owner injection and truthy non-boolean approval. Exact current signed review lineage gates delivery. |
| L04 — state | Existing SQLite stores retain authority; brief is derived. The generated bundle embeds canonical design and historical cited brief under its source digest. |
| L05 — orchestration | Prepare, explicitly approve, reserve shared resources, reconstruct current evidence, generate, commit, project learning, refresh the companion. |
| L06 — execution | Target-specific existing emitters consume the design; unsupported settings are labelled metadata. Knowledge is cited guidance, not automatically translated into arbitrary game logic. |
| L07 — failures | Stale evidence and mismatched designs fail closed; pressure defers generation. Missing runtime/storage is visible. No fabricated build success. |
| L08 — recovery | Owner/request identity deduplicates retry; archive readback verifies integrity. Source-synthesis projection recovery is separately idempotent. Old artifacts remain downloadable even when their historical brief is no longer current approval. |
| L09 — observability | Owner counters, acquisition stages, runtime readiness, blockers, execution receipt, immutable source digest and learning receipt expose actual progress. No global completion number. |
| L10 — economics | Shared execution pool admits work and reserves the configured artifact ceiling. Duplicate execution consumes no second artifact allowance. No model, network or compiler invocation is introduced on this path. |
| L11 — evaluation | Domain tests exercise current/revoked/expired knowledge, changed design, original source, restart and deduplication. HTTP tests exercise auth, scheduler deferral, budget accounting, artifact retrieval and projection failure/recovery. Frontend contract tests and app TypeScript compilation cover response handling. |
| L12 — deployment | Use the existing backend application, companion and resource runtime. Configure reviewed knowledge/practice storage and review custody using existing operator controls. CI runs the new domain, route and frontend checks. |
| L13 — rollback | Revert the additive workbench/routes/composition if necessary. No table migration or destructive source rewrite is introduced. Preserve generated bundles and existing stores; their extra JSON/README files are historical source content. |

## Operator controls and policy

`policy://game.native_delivery/default@1` names the deterministic code-owned gate in `DragonDelivery.brief`, the delivery routes and `DragonNativePracticeLab.generate`: authenticated owner; explicit approval; current independently approved supporting evidence; implemented target/style; matching exact design/brief; resource admission; immutable original source artifact. It is not a remotely loaded prompt or a new approval authority.

Use `SKL_DRAGON_KNOWLEDGE_DB_PATH` and `SKL_DRAGON_PRACTICE_DB_PATH` under the existing deployment's storage policy. Existing review signing and custody configuration (`SKL_DRAGON_REVIEW_SIGNING_KEY_HEX`, and custody anchor settings when required) remains authoritative. Generation additionally requires an owner-bound `DragonExecutionPool` and an eligible approved practice lesson matching the cited mechanics. Do not disable custody or inject a fake execution pool to make a deployment appear ready.

The read-only local operator surface shares the same composition:

```sh
python -m skeleton.ai.game_builder.dragon_almanac_cli delivery-status \
  --database /path/to/knowledge.sqlite --owner OWNER \
  --trusted-local-operator --now UNIX_SECONDS
python -m skeleton.ai.game_builder.dragon_almanac_cli delivery-search \
  --database /path/to/knowledge.sqlite --owner OWNER \
  --trusted-local-operator --now UNIX_SECONDS --query movement
python -m skeleton.ai.game_builder.dragon_almanac_cli delivery-brief \
  --database /path/to/knowledge.sqlite --owner OWNER \
  --trusted-local-operator --now UNIX_SECONDS --query movement \
  --design /path/to/design.json
```

CLI acknowledgement is for an already trusted local operator, not a substitute for HTTP authentication. Explicit time supports reproducible evidence inspection. The command does not grant permission to train, publish or bypass source restrictions.

## Release evidence and limits

The focused evidence lives in `tests/test_dragon_delivery.py`, `backend/tests/test_dragon_delivery_routes.py` and `frontend/scripts/test-dragon-delivery.cjs`; CI includes all three. The broader Dragon suite, existing companion tests, app typecheck and mandatory architecture gates must remain green. A passing construction validator establishes contract consistency, not a universal engine or enterprise qualification.

Before a consumer release, qualify the full live journey on the intended packaged platforms with representative data, real approvals, target compilers and captured gameplay. Establish corpus coverage and resource budgets with measured denominators. Legal clearance and publication remain separate decisions. The overall vision has no defensible single completion percentage yet.
