"""Existing Dragon stores: safe initialization and consent-bound human references.

No captured page becomes calibrated knowledge, a training grant, or a Lab
promotion. Runtime practice and canonical reviewed revisions retain their own
identities and are checked against current crawler authority at every use.
"""

from __future__ import annotations

import asyncio
from contextlib import closing, contextmanager
from hashlib import sha256
import os
from pathlib import Path
import re
import sqlite3
from typing import Iterator

from core.dragon_crawler import CrawlerError, crawler_application
from core.game_learning import GameLearningError
from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.dragon_source_review import CapturedSourceReviews
from skeleton.ai.game_builder.reviewed_knowledge import KnowledgeError, ReviewedKnowledgeStore
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

PRACTICE_MECHANICS = {"movement", "platforming", "physics", "exploration", "level_design"}
_seen: dict[str, tuple[int, int]] = {}
_ID = re.compile(r"^[0-9a-f]{64}$")
_RIGHT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _path(variable: str, *, create: bool = False) -> Path:
    raw = os.getenv(variable, "").strip()
    if not raw:
        raise GameLearningError("dragon_storage_unconfigured", "Configure durable Dragon storage.", 503)
    path = Path(raw).expanduser()
    if not path.is_absolute() or path.name in {"", ".", ".."}:
        raise GameLearningError(
            "dragon_storage_invalid", "Dragon storage must be a private regular database.", 503
        )
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise GameLearningError(
                "dragon_storage_invalid", "Dragon storage symlinks are not admitted.", 503
            )
    if not path.parent.is_dir():
        raise GameLearningError("dragon_storage_invalid", "Dragon storage directory is unavailable.", 503)
    if not path.exists() and create and variable not in _seen:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
            os.close(fd)
        except FileExistsError:
            pass
    if not path.is_file():
        raise GameLearningError(
            "dragon_storage_unavailable", "Dragon storage is unavailable; restore its original file.", 503
        )
    stat = path.stat()
    identity = (stat.st_dev, stat.st_ino)
    if variable in _seen and _seen[variable] != identity:
        raise GameLearningError(
            "dragon_storage_changed",
            "Dragon storage identity changed; restart with an explicitly restored store.",
            503,
        )
    if stat.st_uid != os.geteuid() or stat.st_mode & 0o077:
        raise GameLearningError(
            "dragon_storage_permissions", "Dragon databases must be private to the backend operator.", 503
        )
    _seen[variable] = identity
    return path


def _initialize_sync() -> dict:
    if os.getenv("SKL_DRAGON_RUNTIME_BOOTSTRAP", "").strip() != "1":
        return {"initialized": False, "code": "dragon_bootstrap_disabled"}
    practice = _path("SKL_DRAGON_PRACTICE_DB_PATH", create=True)
    knowledge = _path("SKL_DRAGON_KNOWLEDGE_DB_PATH", create=True)
    if _seen["SKL_DRAGON_PRACTICE_DB_PATH"] == _seen["SKL_DRAGON_KNOWLEDGE_DB_PATH"]:
        raise GameLearningError(
            "dragon_storage_invalid",
            "Practice and reviewed knowledge require their existing separate store paths.",
            503,
        )
    from skeleton.ai.webcrawler.dragon_practice_lab import DragonPracticeLab
    from core.dragon_reference_practice import initialize_reference_practice

    with closing(sqlite3.connect(str(practice), timeout=5)) as db:
        if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise GameLearningError(
                "dragon_storage_corrupt", "Dragon practice storage failed integrity validation.", 503
            )
        DragonPracticeLab(db)
    initialize_reference_practice(practice)
    with ReviewedKnowledgeStore(knowledge, existing_only=True) as store:
        if store.db.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise GameLearningError(
                "dragon_storage_corrupt", "Dragon knowledge storage failed integrity validation.", 503
            )
        CapturedSourceReviews(store)
    return {"initialized": True, "code": "ready"}


async def initialize_dragon_runtime() -> dict:
    """Initialize only empty schemas when the operator enabled bootstrap."""
    return await asyncio.to_thread(_initialize_sync)


@contextmanager
def _library() -> Iterator[tuple[ReviewedKnowledgeStore, CapturedSourceReviews]]:
    path = _path("SKL_DRAGON_KNOWLEDGE_DB_PATH")
    # Existing file only: connect must never recreate a disappeared authority.
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as probe:
        names = {row[0] for row in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {
            "game_builder_knowledge",
            "game_builder_source_candidates",
            "game_builder_source_reviews",
            "game_builder_captured_source_bindings",
        }
        if not required.issubset(names):
            raise GameLearningError(
                "dragon_storage_uninitialized",
                "Initialize Dragon runtime using the operator bootstrap setting.",
                503,
            )
    store = ReviewedKnowledgeStore(path, existing_only=True)
    try:
        yield store, CapturedSourceReviews(store)
    finally:
        store.close()


def _scope(scope: dict) -> str:
    if (
        not isinstance(scope, dict)
        or set(scope) != {"tenant_id", "owner_id"}
        or not _ID.fullmatch(str(scope.get("owner_id", "")))
        or not isinstance(scope.get("tenant_id"), str)
        or not 1 <= len(scope["tenant_id"]) <= 128
    ):
        raise GameLearningError("dragon_scope_invalid", "Authenticated Dragon scope is required.", 403)
    return scope["owner_id"]


def reviewed_scope_from_workspace(scope: dict) -> dict[str, str]:
    """Translate an already authenticated workspace account, not caller JSON.

    Workspaces preserve the verified account email; Academy uses its scoped
    SHA. This adapter never grants a role or accepts a non-email fallback ID.
    """
    if not isinstance(scope, dict) or set(scope) != {"tenant_id", "owner_id"}:
        raise GameLearningError("dragon_scope_invalid", "Verified workspace scope is required.", 403)
    owner, tenant = scope["owner_id"], scope["tenant_id"]
    if (
        not isinstance(owner, str)
        or not 3 <= len(owner) <= 200
        or owner != owner.strip()
        or "@" not in owner
        or any(c.isspace() for c in owner)
        or not isinstance(tenant, str)
        or not 1 <= len(tenant) <= 128
        or tenant != tenant.strip()
    ):
        raise GameLearningError("dragon_scope_invalid", "A verified account-email scope is required.", 403)
    return {"tenant_id": tenant, "owner_id": sha256((tenant + "\x00" + owner.lower()).encode()).hexdigest()}


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise GameLearningError("dragon_candidate_not_found", "Source candidate not found.", 404)
    return value


def _public(candidate: dict) -> dict:
    return {key: value for key, value in candidate.items() if key not in {"owner_id", "request_digest"}}


def _error(exc: Exception) -> GameLearningError:
    if isinstance(exc, GameLearningError):
        return exc
    if isinstance(exc, CrawlerError):
        return GameLearningError(
            "dragon_source_unavailable", "The captured source or its consent is no longer available.", 409
        )
    if isinstance(exc, LookupError):
        return GameLearningError("dragon_candidate_not_found", "Source candidate not found.", 404)
    if isinstance(exc, sqlite3.Error):
        return GameLearningError("dragon_storage_unavailable", "Dragon durable storage is unavailable.", 503)
    if isinstance(exc, KnowledgeError):
        conflict = any(word in str(exc) for word in ("conflict", "already", "version", "idempotency"))
        return GameLearningError(
            "dragon_review_conflict" if conflict else "dragon_reference_rejected",
            str(exc),
            409 if conflict else 422,
        )
    return GameLearningError("dragon_reference_rejected", "Dragon reference is not admissible.", 422)


async def runtime_readiness() -> dict:
    checks = {}
    admitted_paths = {}
    for kind, variable, required in [
        (
            "practice",
            "SKL_DRAGON_PRACTICE_DB_PATH",
            {
                "dragon_practice_lessons",
                "dragon_practice_attempts",
                "dragon_reference_practice_intents",
                "dragon_reference_practice_attempts",
            },
        ),
        (
            "knowledge",
            "SKL_DRAGON_KNOWLEDGE_DB_PATH",
            {
                "game_builder_knowledge",
                "game_builder_source_candidates",
                "game_builder_source_reviews",
                "game_builder_captured_source_bindings",
            },
        ),
    ]:
        try:
            path = _path(variable)
            admitted_paths[kind] = path
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
                tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not required.issubset(tables):
                    raise GameLearningError(
                        "dragon_storage_uninitialized", "Initialize empty Dragon schemas.", 503
                    )
            checks[kind + "_storage"] = {"available": True, "code": "ready"}
        except (GameLearningError, sqlite3.Error) as exc:
            checks[kind + "_storage"] = {
                "available": False,
                "code": getattr(exc, "code", "dragon_storage_unavailable"),
            }
    if (
        len(admitted_paths) == 2
        and _seen["SKL_DRAGON_PRACTICE_DB_PATH"] == _seen["SKL_DRAGON_KNOWLEDGE_DB_PATH"]
    ):
        for check in checks.values():
            check.update(available=False, code="dragon_storage_invalid")
    available = all(check["available"] for check in checks.values())
    return {
        "schema_version": "skeleton.dragon.runtime_readiness.v1",
        "configured": bool(
            os.getenv("SKL_DRAGON_PRACTICE_DB_PATH") and os.getenv("SKL_DRAGON_KNOWLEDGE_DB_PATH")
        ),
        "available": available,
        "checks": checks,
        "actions": (
            []
            if available
            else [
                {
                    "code": "configure_dragon_storage",
                    "message": "Configure private persistent Dragon database paths and enable SKL_DRAGON_RUNTIME_BOOTSTRAP=1 for empty initialization.",
                }
            ]
        ),
        "limits": {
            "max_candidates": 64,
            "max_quote_chars": 1000,
            "max_statement_chars": 2048,
            "max_practice_steps": 512,
            "default_practice_steps": 128,
            "max_practice_seconds": 10,
            "max_practice_attempts_per_day": 16,
            "offset_unit": "unicode_codepoints",
        },
        "capabilities": {
            "source_review": checks["knowledge_storage"]["available"],
            "measured_local_practice": available,
            "automatic_promotion": False,
            "training_rights": False,
        },
        "mechanics": [
            {
                "id": item.value,
                "label": item.value.replace("_", " ").title(),
                "practice_supported": item.value in PRACTICE_MECHANICS,
            }
            for item in Mechanic
        ],
    }


async def create_candidate(scope: dict, request: dict) -> dict:
    owner = _scope(scope)
    try:
        if request["mechanic"] not in {item.value for item in Mechanic}:
            raise KnowledgeError("unknown mechanic")
        evidence = await crawler_application.source_evidence(
            scope, request["session_id"], request["source_id"]
        )
        with _library() as (_, reviews):
            value = reviews.create(owner, request, evidence)
        await crawler_application.assert_context(scope, [value["source_ref"]])
        return {"candidate": {**_public(value), "current_source_usable": True, "current_source_error": None}}
    except (CrawlerError, KnowledgeError, LookupError, sqlite3.Error) as exc:
        raise _error(exc) from exc


async def get_candidate(scope: dict, identifier: str) -> dict:
    owner = _scope(scope)
    try:
        with _library() as (_, reviews):
            value = reviews.get(owner, _identifier(identifier))
        return {"candidate": await _annotated_candidate(scope, value)}
    except (KnowledgeError, LookupError, sqlite3.Error) as exc:
        raise _error(exc) from exc


async def list_candidates(
    scope: dict, *, state: str | None = None, cursor: str | None = None, limit: int = 20
) -> dict:
    owner = _scope(scope)
    if cursor is not None:
        _identifier(cursor)
    try:
        with _library() as (_, reviews):
            values, following = reviews.list(owner, state=state, after=cursor or "", limit=limit)
        return {
            "candidates": [await _annotated_candidate(scope, value) for value in values],
            "next_cursor": following,
        }
    except (KnowledgeError, sqlite3.Error) as exc:
        raise _error(exc) from exc


async def _assert_candidate(scope: dict, candidate: dict, *, approved: bool = False) -> None:
    if approved and (candidate["state"] != "approved" or candidate["knowledge"] is None):
        raise GameLearningError(
            "dragon_reference_not_approved", "An explicitly approved design reference is required.", 409
        )
    try:
        await crawler_application.assert_context(scope, [candidate["source_ref"]])
    except CrawlerError as exc:
        raise _error(exc) from exc
    if not CapturedSourceReviews.unexpired(candidate):
        raise GameLearningError("dragon_source_expired", "Source use consent has expired.", 409)
    if approved:
        knowledge = candidate["knowledge"]
        text_digest = sha256(
            (candidate["statement"] + "\nExact source quotation: " + candidate["exact_quote"]).encode()
        ).hexdigest()
        await assert_reviewed_references(
            scope,
            [
                {
                    "schema_version": "skeleton.dragon.reviewed_reference.v1",
                    "candidate_id": candidate["candidate_id"],
                    "review_id": candidate["review"]["review_id"],
                    "source_id": knowledge["source_id"],
                    "revision_digest": knowledge["revision_digest"],
                    "note_id": knowledge["note_id"],
                    "content_digest": text_digest,
                    "crawler_reference": candidate["source_ref"],
                }
            ],
        )


def _same_review_source_reference(current: dict, retained: dict) -> bool:
    """Compare already-authorized pins without replacing their stored identity.

    An untouched legacy v1 pin may match a newly issued v2 pin at policy
    version zero. Callers must first assert the retained pin against live
    crawler authority; a changed source-use policy is never equivalent.
    """
    identity_fields = {"session_id", "source_id", "source_digest", "request_digest", "consent_id"}
    schemas = {"skeleton.dragon.crawler_reference.v1", "skeleton.dragon.crawler_reference.v2"}
    for reference in (current, retained):
        if not isinstance(reference, dict):
            return False
        schema = reference.get("schema_version")
        v2 = schema == "skeleton.dragon.crawler_reference.v2"
        if (
            not isinstance(schema, str)
            or schema not in schemas
            or set(reference)
            != identity_fields | {"schema_version"} | ({"source_use_version"} if v2 else set())
            or any(
                not isinstance(reference[key], str) or not 1 <= len(reference[key]) <= 256
                for key in identity_fields
            )
            or any(
                _ID.fullmatch(reference[key]) is None
                for key in ("source_id", "source_digest", "request_digest")
            )
            or v2
            and (
                type(reference["source_use_version"]) is not int
                or not 0 <= reference["source_use_version"] <= 2**31 - 1
            )
        ):
            return False
    if current == retained:
        return True
    return (
        retained["schema_version"] == "skeleton.dragon.crawler_reference.v1"
        and current["schema_version"] == "skeleton.dragon.crawler_reference.v2"
        and current["source_use_version"] == 0
        and all(current[key] == retained[key] for key in identity_fields)
    )


async def _annotated_candidate(scope: dict, candidate: dict) -> dict:
    try:
        await _assert_candidate(scope, candidate, approved=candidate["state"] == "approved")
        status = {"current_source_usable": True, "current_source_error": None}
    except GameLearningError as exc:
        status = {"current_source_usable": False, "current_source_error": exc.code}
    prepared = None
    if candidate["state"] == "pending_review":
        with _library() as (_, reviews):
            intent = reviews.review_intent(_scope(scope), candidate["candidate_id"])
        if intent is not None:
            prepared = {
                key: value
                for key, value in intent.items()
                if key not in {"request_digest", "reviewer_id", "candidate_id"}
            }
    return {**_public(candidate), **status, "prepared_review": prepared}


async def review_candidate(scope: dict, identifier: str, request: dict) -> dict:
    owner = _scope(scope)
    try:
        if request["decision"] == "approve_design_reference" and (
            request.get("rights_acknowledged") is not True
            or not _RIGHT.fullmatch(request.get("rights_reference") or "")
        ):
            raise KnowledgeError("explicit design/research rights attestation is required")
        with _library() as (_, reviews):
            candidate = reviews.get(owner, _identifier(identifier))
        await _assert_candidate(scope, candidate)
        evidence = await crawler_application.source_evidence(
            scope, candidate["session_id"], candidate["source_id"]
        )
        if not _same_review_source_reference(evidence["reference"], candidate["source_ref"]):
            raise KnowledgeError("source identity changed")
        with _library() as (_, reviews):
            reviews.validate_approval(owner, identifier, request, evidence["source"]["text"])
            intent = reviews.begin_review(owner, identifier, request, owner)
            value = reviews.finish_review(owner, identifier, intent, evidence["source"]["text"])
        await _assert_candidate(scope, value)
        return {"candidate": {**_public(value), "current_source_usable": True, "current_source_error": None}}
    except (CrawlerError, KnowledgeError, LookupError, sqlite3.Error) as exc:
        raise _error(exc) from exc


async def resume_review(scope: dict, identifier: str, review_id: str) -> dict:
    owner = _scope(scope)
    _identifier(identifier)
    _identifier(review_id)
    try:
        with _library() as (_, reviews):
            candidate = reviews.get(owner, identifier)
            intent = reviews.review_intent(owner, identifier, review_id)
        if intent is None:
            raise KnowledgeError("exact prepared review intent is unavailable")
        await _assert_candidate(scope, candidate)
        evidence = await crawler_application.source_evidence(
            scope, candidate["session_id"], candidate["source_id"]
        )
        if not _same_review_source_reference(evidence["reference"], candidate["source_ref"]):
            raise KnowledgeError("source identity changed")
        with _library() as (_, reviews):
            value = reviews.finish_review(owner, identifier, intent, evidence["source"]["text"])
        await _assert_candidate(scope, value, approved=value["state"] == "approved")
        return {
            "candidate": {
                **_public(value),
                "current_source_usable": True,
                "current_source_error": None,
                "prepared_review": None,
            }
        }
    except (CrawlerError, KnowledgeError, LookupError, sqlite3.Error) as exc:
        raise _error(exc) from exc


async def _live_bindings(scope: dict) -> tuple[list[dict], dict[str, dict]]:
    owner = _scope(scope)
    with _library() as (_, reviews):
        bindings = reviews.bindings(owner)
    live = []
    for binding in bindings:
        if not CapturedSourceReviews.unexpired(binding):
            continue
        try:
            await crawler_application.assert_context(scope, [binding["source_ref"]])
            live.append(binding)
        except CrawlerError as exc:
            if exc.status not in {403, 404, 409, 410, 422}:
                raise
    return live, {binding["source_id"]: binding for binding in live}


def _projection(hit, binding: dict) -> tuple[dict, dict]:
    citation = hit.to_payload()
    text = hit.statement + "\nExact source quotation: " + hit.exact_quote
    content_digest = sha256(text.encode()).hexdigest()
    reference_id = canonical_digest({"revision_digest": hit.revision_digest, "note_id": hit.note_id})
    pin = {
        "schema_version": "skeleton.dragon.reviewed_reference.v1",
        "candidate_id": binding["candidate_id"],
        "review_id": binding["review_id"],
        "source_id": hit.source_id,
        "revision_digest": hit.revision_digest,
        "note_id": hit.note_id,
        "content_digest": content_digest,
        "crawler_reference": binding["source_ref"],
    }
    return {
        "reference_id": reference_id,
        "content_digest": content_digest,
        "text": text,
        "statement": hit.statement,
        "exact_quote": hit.exact_quote,
        "mechanic": hit.mechanic,
        "source_url": hit.source_url,
        "source_ref": binding["source_ref"],
        "citation": citation,
        "source_pin": binding["source_ref"],
        "review_pin": pin,
        "classification": "human_reviewed_design_reference",
        "truth_verified": False,
        "training_allowed": False,
        "practice_history_url": "/api/dragon-academy/knowledge/candidates/"
        + binding["candidate_id"]
        + "/practice",
    }, pin


async def search_reviewed_references(scope: dict, query: str, limit: int = 8) -> dict:
    owner = _scope(scope)
    if type(limit) is not int or not 1 <= limit <= 8:
        raise GameLearningError("dragon_query_bounds", "Reference limit must be between 1 and 8.")
    try:
        _, by_source = await _live_bindings(scope)
        with _library() as (store, _):
            store.source_verifier = (
                lambda source: source["source_id"] in by_source
                and source["revision_digest"] == by_source[source["source_id"]]["revision_digest"]
            )
            hits = store.search(
                owner,
                query,
                limit=limit,
                authorized=True,
                diversify=False,
                allowed_revisions={
                    source_id: binding["revision_digest"] for source_id, binding in by_source.items()
                },
            )
            # This application helper exposes only its explicitly source-bound
            # annotations. Legacy separately-reviewed libraries keep their owner API.
            pairs = [_projection(hit, by_source[hit.source_id]) for hit in hits if hit.source_id in by_source]
        for reference, pin in pairs:
            reference["practice_receipts"] = await _practice_discovery(scope, owner, pin["candidate_id"])
        pins = [pin for _, pin in pairs]
        await assert_reviewed_references(scope, pins)
        return {
            "schema_version": "skeleton.dragon.reviewed_references.v1",
            "references": [value for value, _ in pairs],
            "evidence_refs": pins,
            "requires_human_decision": True,
            "training_allowed": False,
        }
    except (CrawlerError, KnowledgeError, LookupError, sqlite3.Error) as exc:
        raise _error(exc) from exc


async def assert_reviewed_references(scope: dict, pins: list[dict]) -> None:
    owner = _scope(scope)
    if not isinstance(pins, list) or len(pins) > 64:
        raise GameLearningError(
            "dragon_reference_bounds", "Bounded reviewed-reference identities are required."
        )
    if not pins:
        return
    try:
        with _library() as (store, reviews):
            bindings = {row["source_id"]: row for row in reviews.bindings(owner)}
            current = {row["source_id"]: row for row in store._rows(owner)}
            sources = []
            for pin in pins:
                if (
                    not isinstance(pin, dict)
                    or set(pin)
                    != {
                        "schema_version",
                        "candidate_id",
                        "review_id",
                        "source_id",
                        "revision_digest",
                        "note_id",
                        "content_digest",
                        "crawler_reference",
                    }
                    or pin["schema_version"] != "skeleton.dragon.reviewed_reference.v1"
                ):
                    raise KnowledgeError("invalid reviewed-reference identity")
                binding = bindings.get(pin["source_id"])
                source = current.get(pin["source_id"])
                if (
                    binding is None
                    or source is None
                    or not CapturedSourceReviews.unexpired(binding)
                    or source["revision_digest"] != binding["revision_digest"]
                    or source["status"] != "active"
                ):
                    raise KnowledgeError("reviewed reference is unavailable")
                entries = [entry for entry in source["notes"] if entry["note"]["note_id"] == pin["note_id"]]
                if len(entries) != 1:
                    raise KnowledgeError("reviewed note is unavailable")
                entry = entries[0]
                digest = sha256(
                    (
                        entry["note"]["statement"] + "\nExact source quotation: " + entry["exact_quote"]
                    ).encode()
                ).hexdigest()
                expected = {
                    "schema_version": "skeleton.dragon.reviewed_reference.v1",
                    "candidate_id": binding["candidate_id"],
                    "review_id": binding["review_id"],
                    "source_id": binding["source_id"],
                    "revision_digest": binding["revision_digest"],
                    "note_id": entry["note"]["note_id"],
                    "content_digest": digest,
                    "crawler_reference": binding["source_ref"],
                }
                if pin != expected:
                    raise KnowledgeError("reviewed-reference identity changed")
                sources.append(binding["source_ref"])
        for source in sources:
            await crawler_application.assert_context(scope, [source])
    except (CrawlerError, KnowledgeError, LookupError, sqlite3.Error) as exc:
        raise GameLearningError(
            "dragon_reviewed_reference_withdrawn",
            "Reviewed reference or its source consent is no longer usable.",
            409,
        ) from exc


async def practice_candidate(scope: dict, identifier: str, request: dict) -> dict:
    owner = _scope(scope)
    with _library() as (_, reviews):
        candidate = reviews.get(owner, _identifier(identifier))
    if candidate["mechanic"] not in PRACTICE_MECHANICS:
        raise GameLearningError(
            "dragon_practice_unsupported", "This mechanic has no supported local reference exercise.", 409
        )
    if candidate["version"] != request["expected_version"]:
        raise GameLearningError("dragon_review_conflict", "Source candidate version changed.", 409)

    async def authorize():
        with _library() as (_, reviews):
            current = reviews.get(owner, identifier)
            bindings = reviews.bindings(owner)
        if current != candidate or not any(row["candidate_id"] == identifier for row in bindings):
            raise GameLearningError("dragon_review_conflict", "Reviewed reference changed.", 409)
        await _assert_candidate(scope, current, approved=True)

    await authorize()
    from core.dragon_reference_practice import run_reference_practice

    return await run_reference_practice(
        path=_path("SKL_DRAGON_PRACTICE_DB_PATH"),
        owner=owner,
        candidate=_public(candidate),
        request=request,
        authorize=authorize,
    )


async def practice_history(scope: dict, identifier: str, limit: int = 20) -> dict:
    owner = _scope(scope)
    with _library() as (_, reviews):
        candidate = reviews.get(owner, _identifier(identifier))
    await _assert_candidate(scope, candidate, approved=True)
    from core.dragon_reference_practice import list_reference_practice

    values = await asyncio.to_thread(
        list_reference_practice, _path("SKL_DRAGON_PRACTICE_DB_PATH"), owner, identifier, limit=limit
    )
    await _assert_candidate(scope, candidate, approved=True)
    return {"practices": values}


async def _inspect_reference_practice(scope: dict, candidate_id: str, practice_id: str) -> dict:
    owner = _scope(scope)
    _identifier(candidate_id)
    _identifier(practice_id)
    with _library() as (_, reviews):
        candidate = reviews.get(owner, candidate_id)
    await _assert_candidate(scope, candidate, approved=True)
    from core.dragon_reference_practice import read_reference_practice

    result = await asyncio.to_thread(
        read_reference_practice, _path("SKL_DRAGON_PRACTICE_DB_PATH"), owner, candidate_id, practice_id
    )
    expected_pin = {
        key: candidate[key]
        for key in (
            "candidate_id",
            "version",
            "mechanic",
            "knowledge",
            "source_ref",
            "source_digest",
            "valid_until",
        )
    }
    practice = result["practice"]
    if (
        practice.get("status") != "completed"
        or practice.get("practice_id") != practice_id
        or practice.get("source_pin") != expected_pin
        or not _ID.fullmatch(str(result.get("receipt_digest", "")))
        or not _ID.fullmatch(str(practice.get("runtime_digest", "")))
    ):
        raise GameLearningError(
            "dragon_practice_receipt_changed", "The measured practice identity differs.", 409
        )
    await _assert_candidate(scope, candidate, approved=True)
    evidence = {
        "schema_version": "skeleton.dragon.practice_reference.v1",
        "candidate_id": candidate_id,
        "practice_id": practice_id,
        "receipt_digest": result["receipt_digest"],
        "source_pin": expected_pin,
        "runtime_digest": practice["runtime_digest"],
    }
    return {
        **result,
        "evidence_ref": evidence,
        "classification": "measured_reference_observation",
        "truth_verified": False,
        "training_allowed": False,
        "xp_awarded": 0,
    }


async def inspect_reference_practice(scope: dict, candidate_id: str, practice_id: str) -> dict:
    try:
        return await _inspect_reference_practice(scope, candidate_id, practice_id)
    except (CrawlerError, KnowledgeError, LookupError, sqlite3.Error) as exc:
        raise _error(exc) from exc


async def assert_reference_practice(scope: dict, pins: list[dict]) -> None:
    _scope(scope)
    if not isinstance(pins, list) or len(pins) > 16:
        raise GameLearningError(
            "dragon_practice_reference_bounds", "At most sixteen exact practice references may be cited."
        )
    for pin in pins:
        if (
            not isinstance(pin, dict)
            or set(pin)
            != {
                "schema_version",
                "candidate_id",
                "practice_id",
                "receipt_digest",
                "source_pin",
                "runtime_digest",
            }
            or pin["schema_version"] != "skeleton.dragon.practice_reference.v1"
        ):
            raise GameLearningError(
                "dragon_practice_reference_invalid", "An exact measured practice reference is required."
            )
        current = await inspect_reference_practice(scope, pin["candidate_id"], pin["practice_id"])
        if current["evidence_ref"] != pin:
            raise GameLearningError(
                "dragon_practice_reference_withdrawn",
                "Measured practice or its source authority changed.",
                409,
            )


async def _practice_discovery(scope: dict, owner: str, candidate_id: str) -> list[dict]:
    try:
        path = _path("SKL_DRAGON_PRACTICE_DB_PATH")
    except GameLearningError as exc:
        if exc.code == "dragon_storage_unconfigured":
            return []
        raise
    from core.dragon_reference_practice import list_reference_practice

    recent = await asyncio.to_thread(list_reference_practice, path, owner, candidate_id, limit=2)
    for row in recent:
        if row.get("status") == "completed":
            exact = await inspect_reference_practice(scope, candidate_id, row["practice_id"])
            return [{"practice_id": row["practice_id"], "receipt_digest": exact["receipt_digest"]}]
    return []
