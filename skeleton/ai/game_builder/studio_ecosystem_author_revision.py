"""Source-leased original-world authoring with canon proof and offline playable export."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_story_html import render_story_html

REVISION_SCHEMA = "skeleton.game_builder.studio_author_revision_request.v1"
RECEIPT_SCHEMA = "skeleton.game_builder.studio_author_revision_receipt.v1"
MAX_REQUEST_BYTES = 8192
MAX_SOURCE_BYTES = 512 * 1024
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_EDITS = 16

def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical authored revision") from exc

def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()

def _allowed_path(section: str, path: list[object]) -> bool:
    value = tuple(path)
    if section == "narrative":
        if value in (("premise",), ("foundation", "chronology"),
                     ("foundation", "moral_problem"), ("foundation", "tone")):
            return True
        return (len(path) == 3 and path[0] in ("plot_beats", "endings")
                and type(path[1]) is int and 0 <= path[1] < 64
                and path[2] in (("cause", "goal", "decision", "consequence")
                                if path[0] == "plot_beats" else ("consequence",)))
    if section == "cast":
        if value in (("protagonist", "name"), ("protagonist", "public_goal"),
                     ("protagonist", "private_burden"), ("protagonist", "arc")):
            return True
        return (len(path) == 3 and path[0] == "support"
                and type(path[1]) is int and 0 <= path[1] < 64
                and path[2] in ("name", "knows", "relationship"))
    if section == "scene":
        return (len(path) == 3 and path[0] == "episode_plan"
                and type(path[1]) is int and 0 <= path[1] < 64
                and path[2] in ("site", "weather_state", "dialogue_hook"))
    return False

def preview_canon_revision(
    documents: Mapping[str, Any], request: Mapping[str, Any], *,
    authorized: bool,
) -> tuple[dict[str, Any], bytes, dict[str, object]]:
    """Compile a revised original source without mutating the registered catalog."""
    if authorized is not True:
        raise PermissionError("authored revision requires operator authorization")
    if (type(request) is not dict
            or set(request) != {"schema", "project_id", "expected_source_digest", "edits"}
            or request.get("schema") != REVISION_SCHEMA
            or len(_canonical(request)) > MAX_REQUEST_BYTES):
        raise StudioQuestError("invalid or oversized authored revision request")
    if type(request["project_id"]) is not str or not isinstance(documents, Mapping):
        raise StudioQuestError("invalid authored revision source")
    before = audit_canon_source(documents, authorized=True)
    if (not before["canon_consistent"]
            or request["project_id"] != before["project_id"]
            or request["expected_source_digest"] != before["source_digest"]):
        raise StudioQuestError("stale or contradictory authored revision source")
    edits = request["edits"]
    if type(edits) is not list or not 1 <= len(edits) <= MAX_EDITS:
        raise StudioQuestError("invalid authored revision edit count")
    raw = _canonical(documents)
    if len(raw) > MAX_SOURCE_BYTES:
        raise StudioQuestError("authored revision source exceeds byte budget")
    revised = json.loads(raw)
    changed: list[dict[str, object]] = []
    seen: set[str] = set()
    for edit in edits:
        if type(edit) is not dict or set(edit) != {"section", "path", "value"}:
            raise StudioQuestError("invalid authored revision edit")
        section, path, value = edit["section"], edit["path"], edit["value"]
        if (type(section) is not str or type(path) is not list
                or any(type(part) not in (str, int) for part in path)
                or not _allowed_path(section, path)):
            raise StudioQuestError("revision targets protected or unknown source field")
        if (type(value) is not str or not value or value.strip() != value
                or any(ord(char) < 32 for char in value)):
            raise StudioQuestError("invalid authored revision text")
        try:
            if len(value.encode("utf-8", "strict")) > 512:
                raise StudioQuestError("authored revision text exceeds byte budget")
        except UnicodeError as exc:
            raise StudioQuestError("invalid authored revision Unicode") from exc
        key = _canonical([section, path]).decode("ascii")
        if key in seen:
            raise StudioQuestError("duplicate authored revision target")
        seen.add(key)
        target: Any = revised[section]
        try:
            for part in path[:-1]:
                target = target[part]
            previous = target[path[-1]]
        except (KeyError, IndexError, TypeError) as exc:
            raise StudioQuestError("authored revision target does not exist") from exc
        if type(previous) is not str or previous == value:
            raise StudioQuestError("authored revision must change existing prose")
        target[path[-1]] = value
        changed.append({"section": section, "path": path,
                        "before_digest": _digest(previous),
                        "after_digest": _digest(value)})
    if len(_canonical(revised)) > MAX_SOURCE_BYTES:
        raise StudioQuestError("revised authored source exceeds byte budget")
    after = audit_canon_source(revised, authorized=True)
    if not after["canon_consistent"]:
        raise StudioQuestError("authored revision violates canon continuity")
    html = render_story_html(revised)
    if len(html) > MAX_ARTIFACT_BYTES:
        raise StudioQuestError("authored playable export exceeds byte budget")
    if audit_canon_source(documents, authorized=True)["source_digest"] != before["source_digest"]:
        raise StudioQuestError("authored source drift during revision")
    receipt: dict[str, object] = {
        "schema": RECEIPT_SCHEMA, "project_id": before["project_id"],
        "base_source_digest": before["source_digest"],
        "revised_source_digest": after["source_digest"],
        "base_proof_digest": before["proof_digest"],
        "revised_proof_digest": after["proof_digest"],
        "playable_html_sha256": sha256(html).hexdigest(),
        "edits": changed, "canon_consistent": True,
        "ending_obligations": after["ending_obligations"],
        "original_catalog_unchanged": True,
        "native_genre_runtime_verified": False,
        "originality_rights_verified": False, "release_certified": False,
    }
    receipt["receipt_digest"] = _digest(receipt)
    return revised, html, receipt

def write_revision_bundle(
    output: Path, documents: Mapping[str, Any], html: bytes,
    receipt: Mapping[str, Any],
) -> None:
    """Create private directory with exclusive source, playable HTML and receipt."""
    if not isinstance(output, Path) or ".." in output.parts or output.exists() or output.is_symlink():
        raise StudioQuestError("authored revision requires a new safe output directory")
    payloads = {
        "source.json": _canonical(documents) + b"\n",
        "story.html": html,
        "receipt.json": _canonical(receipt) + b"\n",
    }
    if any(len(value) > MAX_ARTIFACT_BYTES for value in payloads.values()):
        raise StudioQuestError("authored revision artifact exceeds byte budget")
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    fd: int | None = None
    created: list[str] = []
    try:
        fd = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for name, content in payloads.items():
            handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=fd)
            created.append(name)
            with os.fdopen(handle, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        os.fsync(fd)
    except BaseException:
        for name in reversed(created):
            try:
                if fd is not None:
                    os.unlink(name, dir_fd=fd)
            except OSError:
                pass
        try:
            output.rmdir()
        except OSError:
            pass
        raise
    finally:
        if fd is not None:
            os.close(fd)


def load_revision_bundle(
    source_dir: Path, *, authorized: bool, project_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reopen a bounded authored revision for another edit, never as signed evidence.

    Digests detect accidental/tampered content; they do not authenticate an
    external author or grant asset rights. Caller still supplies authorization.
    """
    import stat
    if authorized is not True:
        raise PermissionError("authored revision import requires operator authorization")
    if (not isinstance(source_dir, Path) or ".." in source_dir.parts
            or source_dir.is_symlink() or not source_dir.is_dir()):
        raise StudioQuestError("invalid authored revision directory")
    if type(project_id) is not str or not project_id:
        raise StudioQuestError("invalid authored revision project")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise StudioQuestError("duplicate revision bundle JSON key")
            value[key] = item
        return value
    fd = os.open(source_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        payloads: dict[str, bytes] = {}
        for name in ("source.json", "story.html", "receipt.json"):
            handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            with os.fdopen(handle, "rb") as stream:
                status = os.fstat(stream.fileno())
                if not stat.S_ISREG(status.st_mode) or status.st_size > MAX_ARTIFACT_BYTES:
                    raise StudioQuestError("invalid authored revision artifact type or size")
                raw = stream.read(MAX_ARTIFACT_BYTES + 1)
                if len(raw) > MAX_ARTIFACT_BYTES:
                    raise StudioQuestError("authored revision artifact grew during read")
                payloads[name] = raw
    finally:
        os.close(fd)
    try:
        source = json.loads(
            payloads["source.json"].decode("utf-8", "strict"),
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite authored revision JSON")),
        )
        receipt = json.loads(
            payloads["receipt.json"].decode("utf-8", "strict"),
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite authored revision receipt")),
        )
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise StudioQuestError("invalid authored revision bundle JSON") from exc
    if type(source) is not dict or type(receipt) is not dict:
        raise StudioQuestError("invalid authored revision bundle objects")
    digest = receipt.get("receipt_digest")
    if (receipt.get("schema") != RECEIPT_SCHEMA
            or receipt.get("project_id") != project_id
            or type(digest) is not str or len(digest) != 64
            or receipt.get("release_certified") is not False
            or receipt.get("originality_rights_verified") is not False):
        raise StudioQuestError("invalid authored revision bundle receipt")
    unsigned = dict(receipt)
    del unsigned["receipt_digest"]
    if _digest(unsigned) != digest:
        raise StudioQuestError("authored revision receipt digest mismatch")
    proof = audit_canon_source(source, authorized=True)
    if (not proof["canon_consistent"] or proof["project_id"] != project_id
            or proof["source_digest"] != receipt.get("revised_source_digest")
            or proof["proof_digest"] != receipt.get("revised_proof_digest")):
        raise StudioQuestError("authored revision source/proof mismatch")
    html = payloads["story.html"]
    if (sha256(html).hexdigest() != receipt.get("playable_html_sha256")
            or html != render_story_html(source)):
        raise StudioQuestError("authored revision playable HTML drift")
    return source, receipt
