"""Jeeves' source-addressed Forge library, curriculum and practical proficiency.

Every registered handbook has a constant-space reference. Learning requires
source-grounded questions and real preview evidence, NOT fictional model weight
updates or implied permanent mastery. The existing host owns authentication,
training evidence persistence, and any eventual CAS project modification.
"""
from __future__ import annotations

from hashlib import sha256
from importlib import import_module
import json
from typing import Any

from skeleton.forge.game_frontier_studio import StudioError
from skeleton.forge.game_frontier_studio_authoring import AUTHORING_ACTIONS
from skeleton.forge.game_frontier_studio_production_recipes import _DOMAINS, _slug
from skeleton.forge.game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
from skeleton.forge.game_frontier_studio_final_production import FINISHES

SCHEMA = "skeleton.jeeves.forge_book_curriculum.v1"
GENERATIONS = (
    ("worldline", "game_frontier_studio_worldline_handbooks", 9_000),
    ("phase", "game_frontier_studio_phase_handbooks", 90_000),
    ("campaign", "game_frontier_studio_campaign_handbooks", 900_000),
    ("chronicle", "game_frontier_studio_chronicle_handbooks", 9_000_000),
    ("epoch", "game_frontier_studio_epoch_handbooks", 90_000_000),
    ("saga", "game_frontier_studio_saga_handbooks", 900_000_000),
    ("epic", "game_frontier_studio_epic_handbooks", 9_000_000_000),
)
TOTAL_REFERENCES = sum(count for _, _, count in GENERATIONS)
if TOTAL_REFERENCES != 9_999_999_000:
    raise RuntimeError("exact seven-generation Forge manuscript index drift")

COMPETENCIES = (
    "original_world_canon", "source_blueprint_traceability",
    "gameplay_system_design", "multi_route_navigation",
    "npc_and_quest_continuity", "physical_environment_observations",
    "native_authority_and_playtest", "recovery_and_source_receipts",
    "rights_and_comparative_review", "longform_epic_production",
)
# A sequential, 7-level dependency graph; every course level contains the
# entire indexed library of that generation, without allocating the collection.
PREREQUISITES = {
    name: (GENERATIONS[n-1][0],) if n else ()
    for n, (name, _, _) in enumerate(GENERATIONS)
}


def _module(generation: str):
    for key, path, count in GENERATIONS:
        if generation == key:
            module = import_module("skeleton.forge." + path)
            actual = getattr(module, "BOOK_COUNT", getattr(module, "VOLUME_COUNT", None))
            if actual != count:
                raise StudioError("Forge book index drift: old references cannot be trusted")
            return module, count
    raise StudioError("Unknown exact Forge book generation")


def _id(generation: str, index: int) -> tuple[object, tuple[str, ...]]:
    module, count = _module(generation)
    if type(index) is not int or not 0 <= index < count:
        raise StudioError("Forge book reference outside existing indexed library")
    return module, module.identity(index)


def reference(generation: str, index: int) -> dict[str, Any]:
    """Reversible stable reference to ANY individual book, O(1) memory."""
    module, identity = _id(generation, index)
    if generation == "worldline":
        book = module.volume_metadata(*identity)
    else:
        book = module.metadata(*identity)
    path = book.get("path")
    if not isinstance(path, str) or not path.endswith(".md"):
        # Original worldline metadata uses its canonical volume path field.
        path = next((v for k, v in book.items()
                     if "path" in k and isinstance(v, str) and v.endswith(".md")), None)
    if not path:
        raise StudioError("Original source book has no canonical reference path")
    return {
        "schema": SCHEMA,
        "ref": f"forgebook:{generation}:{index}",
        "generation": generation, "index": index, "identity": list(identity),
        "path": path, "metadata": book,
        "unrendered": True, "trained": False,
    }


def from_uri(uri: str) -> dict[str, Any]:
    if type(uri) is not str or len(uri) > 80:
        raise StudioError("exact Forge book URI required")
    parts = uri.split(":")
    if len(parts) != 3 or parts[0] != "forgebook" or not parts[2].isdigit():
        raise StudioError("Forge book URI must be a registered exact reference")
    if len(parts[2]) > 13 or (len(parts[2]) > 1 and parts[2][0] == "0"):
        raise StudioError("Non-canonical Forge book reference")
    return reference(parts[1], int(parts[2]))


def locate(global_index: int) -> dict[str, Any]:
    """Every book in all seven families can be located without an index scan."""
    if type(global_index) is not int or not 0 <= global_index < TOTAL_REFERENCES:
        raise StudioError("Global book position outside indexed collection")
    for name, _, count in GENERATIONS:
        if global_index < count:
            return reference(name, global_index)
        global_index -= count
    raise StudioError("Book address resolution failed closed")


def curriculum_catalog() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "book_count": TOTAL_REFERENCES, "indexed_not_materialized": True,
        "curriculum_levels": [
            {"generation": name, "book_count": count,
             "prerequisites": list(PREREQUISITES[name]),
             "competencies": list(COMPETENCIES),
             "first_reference": f"forgebook:{name}:0",
             "last_reference": f"forgebook:{name}:{count-1}"}
            for name, _, count in GENERATIONS
        ],
        "assessment_model": "objective_source_exercise_plus_real_host_preview",
        "provider_training": "not_started",
        "weight_promoted": False,
        "mastery_requires_measured_evidence": True,
    }


def lesson(generation: str, index: int) -> dict[str, Any]:
    """Build a practical training unit from a real book reference and axes."""
    ref = reference(generation, index)
    axes = ref["identity"]
    parent = None
    if generation != "worldline":
        parent_gen = GENERATIONS[[g[0] for g in GENERATIONS].index(generation)-1][0]
        parent = f"forgebook:{parent_gen}:{index//10}"
    concepts = [
        ("Describe the exact original design domain", axes[0]),
        ("Identify the actual spatial treatment", axes[1]),
        ("Name the source-grounded director", axes[2]),
        ("Identify the canonical game worldline", axes[3]),
    ]
    for n, coordinate in enumerate(axes[4:], 4):
        concepts.append((f"Resolve source-generation axis {n-3}", coordinate))
    return {
        "schema": SCHEMA,
        "reference": ref, "parent_reference": parent,
        "competencies": list(COMPETENCIES),
        "prerequisites": list(PREREQUISITES[generation]),
        "questions": [
            {"question_id": n+1, "prompt": question, "type": "exact_source_axis"}
            for n, (question, _) in enumerate(concepts)
        ],
        "source_exercise_action": exemplar(generation, index),
        "mastery_threshold": 1.0,
        "practice": "Preview this book's exact source action against the host-owned project; never run hidden model code",
        "self_study_not_weight_training": True,
    }


def exemplar(generation: str, index: int) -> str:
    """Choose a real, executable blueprint from exactly the selected book.

    Every book's 50 source archetypes x 10 systems x 10 finish passes includes
    a concrete first recipe. No untrusted code, textual regex or guessed name
    becomes an authoring operation.
    """
    _, parts = _id(generation, index)
    domain, treatment, director, worldline, *rest = parts
    family = next(actions for name, actions, _ in _DOMAINS if name == domain)
    stem = f"{domain}_{_slug(family[0])}__{treatment}___{GAMEPLAY_LAYERS[0]}"
    stem += f"____{director}_____{FINISHES[0]}______{worldline}"
    suffix_lengths = (7, 8, 9, 10, 11, 12)
    for label, size in zip(rest, suffix_lengths):
        stem += "_" * size + label
    name = generation + "_" + stem
    if name not in AUTHORING_ACTIONS:
        raise StudioError("Curriculum book does not resolve to a real editor action")
    return name


def assessment(generation: str, index: int, answers: list[str]) -> dict[str, Any]:
    """Deterministic skills checkpoint with source-backed answer key.

    The returned certificate is an exportable learning receipt, never an
    automatically persisted mastery record or a neural-weight promotion.
    """
    item = lesson(generation, index)
    truth = item["reference"]["identity"]
    if (type(answers) is not list or len(answers) != len(truth)
            or any(type(v) is not str or len(v) > 80 for v in answers)):
        raise StudioError("Assessment requires every typed answer in exact axis order")
    checks = [answer.strip() == expected for answer, expected in zip(answers, truth)]
    request = {
        "schema": "skeleton.jeeves.forge_curriculum_assessment.v1",
        "ref": item["reference"]["ref"],
        "answered": len(checks), "passed": sum(checks),
        "checks": checks, "score": sum(checks)/len(checks),
        "mastery_earned": all(checks),
        "practical_preview_verified": False,
        "weight_trained": False, "promotion": "not_performed",
    }
    digest = sha256(json.dumps(request, sort_keys=True,
                               separators=(",", ":")).encode()).hexdigest()
    return {**request, "receipt_sha256": digest}


def manifest(generation: str, index: int, *, include_content: bool = True) -> dict[str, Any]:
    """Really render a book now; attach bytes, canonical path and SHA receipt."""
    module, axes = _id(generation, index)
    meta = reference(generation, index)
    if generation == "worldline":
        rendered = module.handbook_receipt(*axes)
    else:
        rendered = module.receipt(*axes)
    # A rendered manuscript is necessarily a real exact source artifact
    # even though the indexed catalogue itself is virtual.
    markdown = rendered.get("markdown")
    if not isinstance(markdown, str):
        raise StudioError("Source renderer returned no real Markdown")
    raw = markdown.encode("utf8")
    if not 0 < len(raw) <= 512_000:
        raise StudioError("Materialized book exceeds bounded learning artifact")
    digest = sha256(raw).hexdigest()
    if rendered.get("content_sha256") not in (None, digest):
        raise StudioError("Book renderer failed source integrity verification")
    out = {
        "schema": "skeleton.jeeves.forge_book_manifest.v1",
        "reference": meta["ref"], "path": meta["path"],
        "source_dimensions": list(axes),
        "content_sha256": digest, "bytes": len(raw),
        "content_realized": True,
        "book_quality_kind": rendered.get("quality_kind", "source_document_structure"),
        "weight_trained": False,
    }
    if include_content:
        out["markdown"] = markdown
    return out


def materialize_archive(requests: list[dict[str, Any]]) -> tuple[bytes, dict[str, Any]]:
    """Physically manifest 1..4 exact books as a deterministic downloadable ZIP.

    Materializes only request-selected source manuals, never an impossible
    billion-file archive; byte SHA receipts are checked before packaging.
    A complete archive has a deterministic manifest and no filesystem writes.
    """
    from io import BytesIO
    from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

    if type(requests) is not list or not 1 <= len(requests) <= 4:
        raise StudioError("Book manifestation requires one to four exact references")
    resolved = []
    seen = set()
    for item in requests:
        if type(item) is not dict or set(item) != {"generation", "index"}:
            raise StudioError("Exact generation and index required for each manifested book")
        gen, idx = item["generation"], item["index"]
        if type(gen) is not str or type(idx) is not int:
            raise StudioError("Book manifestation requires typed exact references")
        key = (gen, idx)
        if key in seen:
            raise StudioError("Duplicate book manifestation identity")
        seen.add(key)
        resolved.append(manifest(gen, idx))
    payloads = []
    total = 0
    for item in resolved:
        path = item["path"]
        if (not isinstance(path, str) or len(path) > 400
                or path.startswith("/") or any(x in (".", "..", "")
                                                 for x in path.split("/"))
                or not path.endswith(".md")):
            raise StudioError("Source book path violates safe archive boundary")
        content = item.pop("markdown").encode("utf8")
        total += len(content)
        if total > 1_500_000:
            raise StudioError("Materialized manuscript bundle exceeds 1.5MB")
        if sha256(content).hexdigest() != item["content_sha256"]:
            raise StudioError("Manifested source content hash mismatch")
        payloads.append((path, content))
    record = {
        "schema": "skeleton.jeeves.forge_book_bundle.v1",
        "manifestations": resolved,
        "complete": True,
        "books_physically_rendered": len(resolved),
        "training_weights_promoted": False,
    }
    payloads.append(("manifest.json", (json.dumps(record, ensure_ascii=False,
                         sort_keys=True, separators=(",", ":")) + "\n").encode("utf8")))
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in payloads:
            info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=6)
    zipped = buffer.getvalue()
    return zipped, {
        **record, "archive_sha256": sha256(zipped).hexdigest(),
        "archive_bytes": len(zipped),
    }
