# Jeeves whole-repository operational inventory — 13 October 2026

**Reference tree:** `b4c630bb823fe23837c71bcf35c39575db91b2a6` (PR #3718). An independent GitHub recursive tree inspection counted **58,884 tracked files**, with no truncated tree response. This is a repository-level baseline, *not* a count of working features or the live runtime installation; later commits may change it.

## Measured scale and relevant subsystems

| Repo subtree | Tracked files |
| --- | ---: |
| `skeleton/ai/game_builder/` | 152 |
| `skeleton/ai/webcrawler/` | 226 |
| `skeleton/ai/runtime/` | 1,709 |
| `skeleton/ai/forge/` | 84 |
| `skeleton/jeeves/` | 271 |
| `skeleton/ai/training/` | 68 |
| `skeleton/ai/learning/` | 63 |
| `backend/` | 2,501 |
| `frontend/` | 718 |
| `apps/jeeves/` | 20 |
| `satellites/` | 11,732 |
| `tests/` | 1,488 |
| `.github/workflows/` | 391 |

There were **50,528 Python files, 2,745 JSON files and 1,278 TSX files** across the entire tracked tree. The counts are overlapping by parent/subtree and must not be summed. The codebase also includes binary assets and snapshots, which must never be treated as importable or safe to execute just because their paths were found.

## Completed source inventory architecture

`skeleton/ai/game_builder/jeeves_appwide_fabric.py` indexes *every visible regular file* in a real checked-out repository tree in a deterministic bounded traversal (maximum 200,000 regular entries, 32 subdirectory levels; no symlink following). It groups files by overlapping forge/crawler/companion/Jeeves/editor/game/learning/runtime/frontend/security/build/data categories, supports paginated substring searches, reports exclusions explicitly and returns a content-addressed inventory snapshot. Sensitive environment, credential, private-session, key and vault paths are **metadata only** and cannot be read through this interface. Binary resources require specialized adapters.

Real source reads require a reviewed relative path, bounded UTF-8 data, and rechecking the file to prevent stale metadata or symlink attacks. A source edit request returns only a content-addressed review diff and must specify the exact previous SHA; it **does not write back to the checked-out repository**. Game project edits use the preexisting GameWorkspace source proposal/commit flow, not an alternate file writer.

The `JeevesAppwideRuntime` dispatcher uses a fixed set of registered action IDs, and now delegates to the already installed canonical runtime where possible:

- All actual typed system editors: enumerate fields and validate/preview settings; produce original editor source templates.
- Forges: inspect reviewed tool fabrics, discover universal forge component types and run bounded graph validation through the canonical installed adapters.
- Game creation: invoke the existing bounded browser game compiler, native Godot source compiler and replay-based adversarial mirror with an explicit operator permit. This is a real small-scope prototype engine, not the entire 100-chapter game production pipeline.
- Source planning and editing: inspect thousands of known paths, preview exact source changes, run active-project approved system assembly and hand off typed reviewed proposals.
- Crawler and companion: discover installed crawler workers, run bounded research-planning calculations, provide dragon event visuals and rehearse companion state via the existing guarded runtime. No background acquisition or automatic model learning occurs by simply discovering a module.
- Jeeves/chat/story: existing phase-controlled director, chapter context and source-linked chat session, with no fake model inference claims.
- Internal improvement: source-diff proposals with evidence references and mandatory mirror, benchmark, security, rollback and operator gates. Candidate evidence is not considered corroborated merely because an LLM supplied two source digests. Weights, shadow weights, hyperweights and installed app code remain unchanged unless separately authorized and actually validated.

The loopback-only Studio now exposes `/api/jeeves-appwide-status`, `/api/jeeves-appwide-catalog` and `/api/jeeves-appwide-invoke`. The existing session token/same-origin restrictions still apply. Its Whole Application pane has a file inventory search, subsystem filters, registered-adapter selector, JSON arguments, results receipt and explicit approval checkbox.

## Non-negotiable distinction

**Knowing a file is not equivalent to being able to safely manipulate its runtime.** All scanned files have browseable metadata; only the registered reviewed actions have a concrete execution or review adapter. No generic arbitrary module import, reflective invocation, shell access, neural model mutation, credential exposure, git branch push, app deployment or bulk unreviewed edit is granted by this change. Those subsystems require explicit adapters, bounded permissions and independent integration tests before claims of fully operative product coverage.

### Subsequent closure plan

1. Automatically extract typed public interfaces and UI control manifests from every major subsystem; reconcile exported actions with actual executor bindings and required auth policy.
2. Construct a dependency graph and provenance-verified adapter expansion queue for each remaining unwired app family, prioritized by capability importance and consumer-visible completion.
3. Bind installed model provider inference and per-scene production to the supervised Jeeves director, while preserving exact-source human approval.
4. Execute repeatable app-wide action tests and deep offline builds, then record benchmark improvements, fail-closed behavior, UI state impacts and training/weights promotion proofs.
5. Scale historical source, retrieval and working context without ever claiming that all 58,884 source files are simultaneously resident in model memory.

**Source discovery target:** all visible non-excluded files of the installed checkout.
**Execution target:** verified runtime adapter coverage, not raw file count.
**Claimed full-app capability completion:** not established by this milestone.
