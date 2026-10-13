"""Static, bounded whole-app capability intelligence for governed Jeeves.

This module NEVER loads/imports scanned code, invokes exports, writes sources,
reads credential paths, or turns a declaration into execution authority.
It works on an explicit reviewed inventory subset, not an entire repo in RAM.
"""
from __future__ import annotations

import ast
from hashlib import sha256
import io
import json
import keyword
from pathlib import PurePosixPath
import re
import tokenize

from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, digest

SCHEMA = "skeleton.ai.jeeves_static_intelligence.v1"
MAX_PATHS = 48
MAX_PARSE_BYTES = 128_000
MAX_SYMBOLS = 64
MAX_IMPORTS = 96
MAX_TOKENS = 10_000
CODE_SUFFIXES = frozenset((".py", ".ts", ".tsx", ".js", ".jsx",
                           ".mjs", ".cjs", ".rs", ".go", ".java",
                           ".gd", ".cs", ".kt", ".swift"))
JS_DECL = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:declare\s+)?(?:async\s+)?"
    r"(?:function|class|interface|type|const|let|enum)\s+([A-Za-z_$][\w$]*)",
    re.M)
JS_IMPORT = re.compile(r"^\s*import\s+(?:[\s\S]{0,180}?\s+from\s+)?"
                       r"['\"]([.][^'\"\n]{1,160})['\"]", re.M)
OTHER_DECLS = {
    ".rs": re.compile(r"^\s*pub(?:\([^)]{1,40}\))?\s+"
                      r"(?:async\s+)?(?:fn|struct|trait|enum|type)\s+(\w+)", re.M),
    ".go": re.compile(r"^\s*(?:func|type)\s+([A-Z]\w*)\b", re.M),
    ".gd": re.compile(r"^\s*(?:func|signal|class_name)\s+(\w+)\b", re.M),
    ".java": re.compile(r"^\s*public\s+(?:(?:static|final|abstract)\s+)*"
                        r"(?:class|interface|enum|record)\s+(\w+)\b", re.M),
    ".kt": re.compile(r"^\s*(?:public\s+)?(?:fun|class|interface|object)\s+(\w+)\b", re.M),
    ".swift": re.compile(r"^\s*(?:public|open)\s+(?:func|class|struct|enum|protocol)\s+(\w+)\b", re.M),
    ".cs": re.compile(r"^\s*public\s+(?:(?:static|sealed|abstract|partial)\s+)*"
                      r"(?:class|interface|enum|struct|record)\s+(\w+)\b", re.M),
}
IDENT = re.compile(r"^[A-Za-z_$][\w$]{0,95}$")


def _paths(paths):
    if type(paths) is not list or not 1 <= len(paths) <= MAX_PATHS:
        raise JeevesAppwideError("explicit bounded list of 1..48 paths required")
    if any(type(p) is not str for p in paths) or len(set(paths)) != len(paths):
        raise JeevesAppwideError("duplicate or non-string inspected path")
    return sorted(paths)


def _module_path(path):
    module = path[:-3].replace("/", ".")
    return module[:-9] if module.endswith(".__init__") else module


def _python_contract(text, path):
    try:
        tree = ast.parse(text, filename=path)
    except (SyntaxError, ValueError, RecursionError) as exc:
        return {"status": "parse_failed", "error_kind": type(exc).__name__,
                "declared_symbols": [], "static_imports": [],
                "total_symbols": 0, "total_imports": 0}
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                continue
            entry = {"name": node.name,
                     "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                     "line": node.lineno}
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                entry["async"] = isinstance(node, ast.AsyncFunctionDef)
                entry["parameters"] = [
                    a.arg[:96] for a in (
                        node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                    )[:24]]
            else:
                entry["methods"] = [
                    n.name for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not n.name.startswith("_")
                ][:24]
            names.append(entry)
    module = _module_path(path)
    package = module if path.endswith("/__init__.py") else module.rpartition(".")[0]
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(n.name for n in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = package.split(".") if package else []
            if node.level:
                prefix = prefix[:max(0, len(prefix) - node.level + 1)]
                base = ".".join(prefix + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            if base:
                imports.add(base)
            for name in node.names:
                if name.name != "*" and base:
                    imports.add(base + "." + name.name)
                elif name.name != "*" and not base and node.level:
                    imports.add(name.name)
    selected = sorted(imports)
    return {"status": "parsed", "declared_symbols": names[:MAX_SYMBOLS],
            "static_imports": selected[:MAX_IMPORTS],
            "total_symbols": len(names), "total_imports": len(selected)}


def _generic_contract(text, path):
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in (".js", ".jsx", ".ts", ".tsx", ".cjs", ".mjs"):
        found = [{"name": m.group(1), "kind": "syntax_export",
                  "line": text.count("\n", 0, m.start()) + 1}
                 for m in JS_DECL.finditer(text)]
        imports = sorted(set(m.group(1) for m in JS_IMPORT.finditer(text)))
        return {"status": "heuristic_unverified", "declared_symbols": found[:MAX_SYMBOLS],
                "static_imports": imports[:MAX_IMPORTS],
                "total_symbols": len(found), "total_imports": len(imports),
                "ui_event_handler_mentions": min(
                    len(re.findall(r"\bon(?:Click|Change|Submit|Input)\s*=", text)), 10000)}
    pattern = OTHER_DECLS.get(suffix)
    found = [{"name": m.group(1), "kind": "syntax_declaration",
              "line": text.count("\n", 0, m.start()) + 1}
             for m in pattern.finditer(text)] if pattern else []
    return {"status": "heuristic_unverified", "declared_symbols": found[:MAX_SYMBOLS],
            "static_imports": [], "total_symbols": len(found), "total_imports": 0}


class JeevesStaticIntelligence:
    """Explicit snapshot-bound, bounded syntax study of visible source files.

    The inventory is authoritative for path safety; these signatures are
    discovery hints, never a trusted runtime contract or callable adapter.
    """

    def __init__(self, inventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("reviewed AppwideInventory required")
        inventory._require_scanned()
        self.inventory = inventory

    def _inspect(self, path, expected=None):
        entry = self.inventory._files.get(path)
        if entry is None or not entry.readable or entry.kind != "source":
            raise JeevesAppwideError("source not indexed or restricted")
        if PurePosixPath(path).suffix.lower() not in CODE_SUFFIXES:
            raise JeevesAppwideError("no static adapter for this source language")
        text = self.inventory._safe_file(path, max_size=MAX_PARSE_BYTES)
        data = text.encode("utf-8")
        current = sha256(data).hexdigest()
        if expected is not None and expected != current:
            raise JeevesAppwideError("stale source identity; refresh before use")
        result = (_python_contract(text, path) if path.endswith(".py")
                  else _generic_contract(text, path))
        return {"path": path, "source_sha256": current,
                "language": PurePosixPath(path).suffix.lower(),
                "bytes": len(data), **result,
                "callable_by_jeeves": False,
                "runtime_adapter_verified": False}

    def contracts(self, paths, *, expected_snapshot=None, expected_sources=None):
        paths = _paths(paths)
        inv = self.inventory
        if expected_snapshot is not None and expected_snapshot != inv._digest:
            raise JeevesAppwideError("stale inventory snapshot")
        if expected_sources is None:
            expected_sources = {}
        if type(expected_sources) is not dict or any(
            type(k) is not str or type(v) is not str or
            not re.fullmatch(r"[a-f0-9]{64}", v)
            for k, v in expected_sources.items()
        ) or set(expected_sources) - set(paths):
            raise JeevesAppwideError("invalid expected source digests")
        documents = [self._inspect(p, expected_sources.get(p)) for p in paths]
        body = {"schema": SCHEMA, "mode": "static_contracts",
                "inventory_snapshot": inv._digest, "documents": documents,
                "inspected_files": len(documents),
                "repository_files_not_inspected": max(0, len(inv._files) - len(documents)),
                "static_discovery_not_execution": True,
                "untrusted_metadata": True}
        return {**body, "digest": digest(body)}

    def impact(self, paths, *, changed, expected_snapshot=None):
        if type(changed) is not str or changed not in paths:
            raise JeevesAppwideError("changed path must be in inspected scope")
        view = self.contracts(paths, expected_snapshot=expected_snapshot)
        docs = view["documents"]
        paths_set = {d["path"] for d in docs}
        python_modules = {_module_path(p): p for p in paths_set if p.endswith(".py")}
        frontend_modules = {}
        for p in paths_set:
            if PurePosixPath(p).suffix.lower() in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
                frontend_modules[str(PurePosixPath(p).with_suffix(""))] = p
        edges = set()
        for doc in docs:
            for imp in doc["static_imports"]:
                target = python_modules.get(imp)
                if target is None and imp.startswith("."):
                    ref = str(PurePosixPath(doc["path"]).parent / imp)
                    # PurePosixPath retains literal ".."; normalize only within
                    # selected paths, never use this path for file operations.
                    parts = []
                    for segment in ref.split("/"):
                        if segment == "..":
                            if parts:
                                parts.pop()
                        elif segment != ".":
                            parts.append(segment)
                    target = frontend_modules.get("/".join(parts))
                if target is not None and target != doc["path"]:
                    edges.add((doc["path"], target))
        incoming = sorted(src for src, dst in edges if dst == changed)
        outgoing = sorted(dst for src, dst in edges if src == changed)
        body = {"schema": SCHEMA, "mode": "selected_scope_impact",
                "inventory_snapshot": view["inventory_snapshot"],
                "changed_source": changed,
                "changed_sha256": next(d["source_sha256"] for d in docs if d["path"] == changed),
                "direct_selected_dependents": incoming,
                "selected_dependencies": outgoing,
                "selected_edges": [list(e) for e in sorted(edges)],
                "scope_files": len(docs),
                "unexamined_repository_files": view["repository_files_not_inspected"],
                "graph_complete": False, "refactor_safe_to_apply": False,
                "operator_review_required": True}
        return {**body, "digest": digest(body)}

    def context(self, paths, *, query, budget_chars=8000, limit=12,
                expected_snapshot=None):
        if type(query) is not str or not 1 <= len(query) <= 180:
            raise JeevesAppwideError("bounded context objective required")
        if type(budget_chars) is not int or not 1200 <= budget_chars <= 20000:
            raise JeevesAppwideError("explicit context character budget required")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise JeevesAppwideError("bounded context source count required")
        view = self.contracts(paths, expected_snapshot=expected_snapshot)
        terms = query.lower().split()
        def score(doc):
            path = doc["path"].lower()
            symbols = {s["name"].lower() for s in doc["declared_symbols"]}
            return (sum(5 for t in terms if t in path) +
                    sum(2 for t in terms if any(t in n for n in symbols)))
        ranked = sorted(view["documents"], key=lambda d: (-score(d), d["path"]))
        records = []
        used = 0
        for doc in ranked:
            row = {"path": doc["path"], "source_sha256": doc["source_sha256"],
                   "language": doc["language"], "parse_status": doc["status"],
                   "symbols": [s["name"] for s in doc["declared_symbols"][:24]],
                   "imports": doc["static_imports"][:16],
                   "relevance": score(doc), "source_not_included": True}
            n = len(json.dumps(row, sort_keys=True, ensure_ascii=True))
            if used + n > budget_chars:
                continue
            records.append(row)
            used += n
            if len(records) >= limit:
                break
        body = {"schema": SCHEMA, "mode": "bounded_context",
                "inventory_snapshot": view["inventory_snapshot"],
                "query": query, "budget_chars": budget_chars,
                "used_metadata_chars": used, "selected": records,
                "unselected_in_scope": len(ranked) - len(records),
                "repo_files_out_of_scope": view["repository_files_not_inspected"],
                "contents_or_secrets_loaded_into_packet": False,
                "requires_operator_review_for_execution": True,
                "character_budget_is_not_token_budget": True}
        return {**body, "digest": digest(body)}

    def duplicates(self, paths, *, expected_snapshot=None, threshold=0.86):
        if type(threshold) not in (int, float) or not 0.75 <= threshold <= 1:
            raise JeevesAppwideError("near duplicate similarity threshold must be 0.75..1")
        view = self.contracts(paths, expected_snapshot=expected_snapshot)
        rows = view["documents"]
        exact = {}
        for row in rows:
            exact.setdefault(row["source_sha256"], []).append(row["path"])
        exact_groups = [
            {"sha256": key, "paths": val}
            for key, val in sorted(exact.items()) if len(val) > 1
        ]
        # Parsing is static; source tokens only feed fingerprints, never replies.
        shingles = {}
        for row in rows:
            if row["language"] != ".py" or row["status"] != "parsed":
                continue
            text = self.inventory._safe_file(row["path"], max_size=MAX_PARSE_BYTES)
            tokens = []
            try:
                for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                    if tok.type in (tokenize.ENCODING, tokenize.COMMENT,
                                    tokenize.NL, tokenize.NEWLINE,
                                    tokenize.INDENT, tokenize.DEDENT,
                                    tokenize.ENDMARKER):
                        continue
                    value = tok.string
                    if tok.type == tokenize.NAME and not keyword.iskeyword(value):
                        value = "<identifier>"
                    elif tok.type == tokenize.STRING:
                        value = "<literal>"
                    elif tok.type == tokenize.NUMBER:
                        value = "<number>"
                    tokens.append(value[:96])
                    if len(tokens) >= MAX_TOKENS:
                        break
            except (tokenize.TokenError, IndentationError):
                continue
            if len(tokens) >= 64:
                shingles[row["path"]] = set(tuple(tokens[i:i+4])
                                            for i in range(len(tokens)-3))
        near = []
        keys = sorted(shingles)
        for i, left in enumerate(keys):
            for right in keys[i+1:]:
                if next(r["source_sha256"] for r in rows if r["path"] == left) == next(
                    r["source_sha256"] for r in rows if r["path"] == right
                ):
                    continue
                a, b = shingles[left], shingles[right]
                if min(len(a), len(b)) < 24:
                    continue
                intersection = len(a & b)
                similarity = intersection / (len(a) + len(b) - intersection)
                if similarity >= threshold:
                    near.append({"left": left, "right": right,
                                 "similarity": round(similarity, 4)})
        near.sort(key=lambda item: (-item["similarity"], item["left"], item["right"]))
        body = {"schema": SCHEMA, "mode": "scoped_duplicate_candidates",
                "inventory_snapshot": view["inventory_snapshot"],
                "files_compared": len(rows),
                "exact_groups": exact_groups, "near_python_candidates": near[:100],
                "comparison_complete_for_entire_repo": False,
                "near_matches_must_be_manually_reviewed": True,
                "no_files_deleted": True}
        return {**body, "digest": digest(body)}
