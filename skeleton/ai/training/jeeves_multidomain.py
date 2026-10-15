"""Rights-gated Jeeves gaming, AI and coding specialist curriculum.

The 384 contracts are executable dataset routing and evaluation specialists,
not 384 independent neural networks. Candidate SGD stays with the existing
pinned, production-derived Jeeves optimizer; this module never trains weights.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any

SCHEMA = "skeleton.jeeves.multidomain_corpus.v1"
CATALOG_SCHEMA = "skeleton.jeeves.training_modules.v1"
ROOT = (Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[3])
CATALOG = ROOT / "machine/jeeves_training_modules.json"
DOMAINS = ("gaming", "ai", "coding")
LENSES = ("construct", "counterexample", "repair", "edge_cases",
          "resource", "security", "portability", "verification")
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{2,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _error(message: str) -> ValueError:
    return ValueError("Jeeves multidomain curriculum: " + message)


def _strict_object(raw: bytes) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _error("duplicate JSON key")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(_error("non-finite JSON")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("invalid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise _error("JSON object required")
    return value


def validate_catalog(path: Path = CATALOG) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or not 1024 <= path.stat().st_size <= 1024 * 1024:
        raise _error("catalogue missing or outside size boundary")
    raw = path.read_bytes()
    value = _strict_object(raw)
    rows = value.get("modules")
    if (value.get("schema_version") != CATALOG_SCHEMA or
            value.get("module_count") != 384 or
            value.get("model_execution") != "only through attested candidate optimizer" or
            value.get("independent_model_promotion") != "required" or
            not isinstance(rows, list) or len(rows) != 384):
        raise _error("invalid catalogue structure or model boundary")
    seen: set[str] = set()
    coverage: dict[str, dict[str, set[str]]] = {domain: {} for domain in DOMAINS}
    for item in rows:
        if not isinstance(item, dict):
            raise _error("module entry must be object")
        domain, topic, lens, identity = (item.get("domain"), item.get("specialty"),
                                         item.get("lens"), item.get("module_id"))
        if (domain not in DOMAINS or lens not in LENSES or
                not isinstance(topic, str) or not re.fullmatch(r"[a-z][a-z0-9_]{2,31}", topic) or
                identity != f"jeeves.{domain}.{topic}.{lens}" or identity in seen or
                item.get("backend") != "production_jeeves_candidate_only"):
            raise _error("duplicate, unknown or malformed executable specialist")
        if any(not isinstance(item.get(key), str) or len(item[key]) < 6
               for key in ("objective", "assignment", "anchor_terms", "review_dimension")):
            raise _error("specialist lacks executable competency contract")
        seen.add(identity)
        coverage[domain].setdefault(topic, set()).add(lens)
    if any(len(coverage[d]) != 16 or
           any(lenses != set(LENSES) for lenses in coverage[d].values()) for d in DOMAINS):
        raise _error("incomplete gaming/AI/coding specialty x lens coverage")
    return {"catalog_sha256": sha256(raw).hexdigest(), "modules": 384,
            "domains": sorted(DOMAINS), "catalogue_valid": True,
            "model_training_executed": False}


def generate_modules() -> list[dict[str, str]]:
    """Return checked execution contracts without accepting novel unreviewed IDs."""
    validate_catalog()
    return _strict_object(CATALOG.read_bytes())["modules"]


def _rows(path: Path, digest: str, split: str, allowed: set[str]) -> tuple[dict[str, Any], ...]:
    if (path.is_symlink() or not path.is_file() or not _SHA.fullmatch(str(digest))
            or not 1 <= path.stat().st_size <= 16 * 1024 * 1024):
        raise _error(f"{split} input missing, unpinned or oversized")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != digest:
        raise _error(f"{split} SHA256 mismatch")
    result: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not 1 <= len(line) <= 24000 or len(result) >= 4096:
            raise _error(f"{split} malformed record length or count")
        row = _strict_object(line)
        if row.get("split") != split or row.get("module_id") not in allowed:
            raise _error(f"{split} unregistered module or incorrect split")
        for key in ("id", "source_project_id"):
            if not isinstance(row.get(key), str) or not _ID.fullmatch(row[key]):
                raise _error(f"{split} invalid {key}")
        for key in ("prompt", "answer"):
            if not isinstance(row.get(key), str) or not 24 <= len(row[key].strip()) <= 12000:
                raise _error(f"{split} invalid {key}")
        rights = row.get("rights")
        if (not isinstance(rights, dict) or rights.get("training_permitted") is not True
                or rights.get("human_reviewed") is not True
                or any(not isinstance(rights.get(key), str) or len(rights[key].strip()) < 5
                       for key in ("source_ref", "rights_basis"))):
            raise _error(f"{split} rights declaration absent or incomplete")
        result.append(row)
    if not result:
        raise _error(f"{split} dataset empty")
    return tuple(result)


def _grams(text: str) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", text.casefold())
    n = min(6, len(words))
    return {tuple(words[i:i+n]) for i in range(len(words) - n + 1)} if n else set()


def _split_guard(train: tuple[dict[str, Any], ...], test: tuple[dict[str, Any], ...]) -> None:
    if {r["source_project_id"] for r in train} & {r["source_project_id"] for r in test}:
        raise _error("source-project leakage between train and heldout")
    ids = [r["id"] for r in train + test]
    if len(set(ids)) != len(ids):
        raise _error("duplicate training/heldout record identity")
    for field in ("prompt", "answer"):
        originals = [" ".join(r[field].casefold().split()) for r in train]
        if len(set(originals)) != len(originals):
            raise _error(f"duplicated training {field}")
        exact = set(originals)
        index: dict[tuple[str, ...], list[set[tuple[str, ...]]]] = defaultdict(list)
        for row in train:
            grams = _grams(row[field])
            for word in grams:
                index[word].append(grams)
        for row in test:
            if " ".join(row[field].casefold().split()) in exact:
                raise _error(f"heldout {field} exactly duplicates training")
            grams = _grams(row[field])
            checked: set[int] = set()
            for word in grams:
                for candidate in index.get(word, ()):
                    identity = id(candidate)
                    if identity not in checked and candidate and len(grams & candidate) / min(len(grams), len(candidate)) >= .85:
                        raise _error(f"heldout {field} near-duplicates training")
                    checked.add(identity)
    from .jeeves_game_corpus import _split_contamination
    from .jeeves_game_design_benchmark import BENCHMARK
    benchmark = tuple(prompt for _family, prompt, _terms in BENCHMARK)
    for row in train + test:
        if any(_split_contamination(row["prompt"], prompt) for prompt in benchmark):
            raise _error("corpus contaminates immutable game benchmark")


def load_multidomain_corpus(manifest_path: Path) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]], dict[str, Any]]:
    """Load operator-reviewed original records, not synthetic fill-in examples."""
    if (manifest_path.is_symlink() or not manifest_path.is_file()
            or not 32 <= manifest_path.stat().st_size <= 64 * 1024):
        raise _error("manifest missing, symbolic or oversized")
    raw = manifest_path.read_bytes()
    config = _strict_object(raw)
    if config.get("schema_version") != SCHEMA or config.get("rights_reviewed") is not True:
        raise _error("multidomain manifest lacks schema or human rights review")
    if not isinstance(config.get("review_id"), str) or len(config["review_id"].strip()) < 5:
        raise _error("independent rights-review ID required")
    names = config.get("train_file"), config.get("heldout_file")
    if (names[0] == names[1] or any(not isinstance(n, str) or not _ID.fullmatch(n)
                                      or not n.endswith(".jsonl") for n in names)):
        raise _error("split files must be different safe JSONL basenames")
    modules = {m["module_id"]: m for m in generate_modules()}
    train = _rows(manifest_path.parent / names[0], config.get("train_sha256"), "train", set(modules))
    test = _rows(manifest_path.parent / names[1], config.get("heldout_sha256"), "heldout", set(modules))
    _split_guard(train, test)
    if len(train) < 18 or len(test) < 9:
        raise _error("require 18 train and 9 heldout examples at minimum")
    for domain in DOMAINS:
        if (sum(modules[r["module_id"]]["domain"] == domain for r in train) < 4 or
                sum(modules[r["module_id"]]["domain"] == domain for r in test) < 2):
            raise _error("each domain requires independent train and heldout data")
    if len({r["source_project_id"] for r in train}) < 2 or len({r["source_project_id"] for r in test}) < 2:
        raise _error("each split requires at least two source projects")
    active = sorted({r["module_id"] for r in train + test})

    def frame(row: dict[str, Any]) -> str:
        # This is executable specialization: the optimizer actually sees
        # the module's objective, adversarial lens, and domain constraints.
        # Heldout references remain separate and are never fit.
        contract = modules[row["module_id"]]
        return (
            f"Jeeves module {contract['module_id']}. "
            f"Objective: {contract['objective']}. "
            f"Lens: {contract['assignment']}. "
            f"Constraints: {contract['anchor_terms']}. "
            "User: " + row["prompt"].strip() + " Jeeves: " + row["answer"].strip()
        )
    training = tuple(frame(r) for r in train)
    heldout = {domain: tuple(frame(r) for r in test if modules[r["module_id"]]["domain"] == domain)
               for domain in DOMAINS}
    receipt = {"schema_version": SCHEMA, "rights_review_id": config["review_id"],
               "manifest_sha256": sha256(raw).hexdigest(),
               "train_sha256": config["train_sha256"], "heldout_sha256": config["heldout_sha256"],
               "train_examples": len(train), "heldout_examples": len(test),
               "active_modules": active, "registered_modules": len(modules),
               "independent_projects": True, "heldout_used_for_training": False,
               "legal_rights_independently_verified": False,
               "creative_quality_established": False}
    return training, heldout, receipt


def load_training_corpus(manifest_path: Path):
    """Preserve the existing game corpus loader while admitting multidomain."""
    if (manifest_path.is_symlink() or not manifest_path.is_file()
            or not 32 <= manifest_path.stat().st_size <= 64 * 1024):
        raise _error("training corpus manifest missing or oversized")
    schema = _strict_object(manifest_path.read_bytes()).get("schema_version")
    if schema == SCHEMA:
        return load_multidomain_corpus(manifest_path)
    from .jeeves_game_corpus import SCHEMA as GAME_SCHEMA, load_approved_corpus
    if schema == GAME_SCHEMA:
        return load_approved_corpus(manifest_path)
    raise _error("unknown approved training corpus schema")


def _mirror(name: str, train, heldout, receipt):
    documents = tuple(train) + tuple(t for part in heldout.values() for t in part)
    if name == "structure":
        evidence = {"bad_dialogue_shapes": sum(
            not t.startswith("Jeeves module ") or " User: " not in t or " Jeeves: " not in t
            for t in documents)}
    elif name == "lexical":
        counts = Counter(word for t in documents for word in re.findall(r"[a-z]+", t.casefold()))
        evidence = {"unique_terms": len(counts), "observed_tokens": sum(counts.values()),
                    "most_common": [word for word, _ in counts.most_common(10)]}
    elif name == "balance":
        evidence = {"training_examples": len(train),
                    "heldout_by_domain": {domain: len(rows) for domain, rows in sorted(heldout.items())}}
    elif name == "custody":
        evidence = {"train_sha256": receipt["train_sha256"], "heldout_sha256": receipt["heldout_sha256"],
                    "review_id": receipt["rights_review_id"],
                    "rights_declaration_is_not_legal_verification": True}
    else:
        raise _error("unknown mirror angle")
    digest = sha256(json.dumps(documents, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {"mirror": name, "evidence": evidence, "input_digest": digest,
            "weight_updates": 0, "independent_critic_model_ran": False}


def digest_with_mirrors(manifest: Path, *, workers: int = 4):
    """Four true concurrent data analyses; optimizer mirror arms are separate."""
    if type(workers) is not int or not 1 <= workers <= 4:
        raise _error("mirror workers outside 1..4")
    train, heldout, receipt = load_multidomain_corpus(manifest)
    names = ("structure", "lexical", "balance", "custody")
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="jeeves-digest") as pool:
        futures = [pool.submit(_mirror, name, train, heldout, receipt) for name in names]
        mirrors = [future.result() for future in futures]
    return {"schema_version": "skeleton.jeeves.parallel_digest.v1",
            "dataset_manifest_sha256": receipt["manifest_sha256"],
            "active_modules": len(receipt["active_modules"]),
            "registered_modules": receipt["registered_modules"], "mirrors": mirrors,
            "all_mirrors_finished": True, "actual_candidate_training_executed": False,
            "independent_model_evaluation_complete": False}


__all__ = ["SCHEMA", "CATALOG_SCHEMA", "CATALOG", "validate_catalog",
           "generate_modules", "load_training_corpus", "load_multidomain_corpus",
           "digest_with_mirrors"]
