# Jeeves indexed cross-language source navigation — October 13, 2026

**DX-20: real source contents, not only filenames.** \`ai.code.search\`
performs case-sensitive or Unicode case-folded literal searches over a selected
real checkout tree and the canonical inventory's regular source/text files.
Supports canonical path prefix and stable path cursor. Each request examines
at most 72 files and 2 MB of source, with bounded match excerpts, SHA-256
source identity and explicit skipped/restricted/oversized counters. The search
does not import, call or execute any discovered module.

**DX-21: token-budgeted source paging.** \`ai.code.snippet\` provides
1–80 specific UTF-8 source lines, with a source SHA-256 expected identity
guard, total line count and forward cursor. Long source lines are clipped and
labeled, never represented as a complete file.

\`\`\`python
search = runtime.invoke("ai.code.search", {
    "prefix": "skeleton/ai/game_builder",
    "query": "class Jeeves",
    "max_files": 48, "max_matches": 20,
    "expected_snapshot": inventory_digest
})["result"]
source = runtime.invoke("ai.code.snippet", {
    "path": "skeleton/ai/game_builder/jeeves_appwide_fabric.py",
    "start_line": 250, "line_count": 40,
})["result"]
\`\`\`

Search results are bounded literal references and do not prove dependency
relationships, code quality, installed functionality or authorization.
No tests run in this requested build-only pass.
