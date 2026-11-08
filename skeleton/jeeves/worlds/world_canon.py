"""Typed, source-leased original-world authoring and executable browser handoff.

The proposal is deterministic and intentionally not represented as LLM output.  All
worlds must be explicitly reviewed before durable publication.  No network, eval,
external assets, or implicit grants are used by the compiled player.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import stat
import unicodedata
from typing import Any, Mapping

SCHEMA = "jeeves.world.canon.v1"
PLAYABLE_SCHEMA = "jeeves.world.playable.v1"
MAX_SOURCE_BYTES = 524288
MAX_SCENES = 128
MAX_CHOICES = 512
MAX_FLAGS = 64
MAX_STATES = 2048
ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,47}$")


class CanonError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return sha256(canonical(value)).hexdigest()


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CanonError("duplicate_json_key", key)
        out[key] = value
    return out


def _finite_json_float(token: str) -> float:
    """Reject JSON exponent overflow before it can bypass typed validation."""
    value = float(token)
    if not math.isfinite(value):
        raise CanonError("nonfinite_number")
    return value


def strict_json(raw: bytes) -> Any:
    if len(raw) > MAX_SOURCE_BYTES:
        raise CanonError("source_too_large")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                          parse_float=_finite_json_float,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              CanonError("nonfinite_number")))
    except CanonError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError,
            ValueError, OverflowError) as exc:
        raise CanonError("invalid_json") from exc


def _keys(value: Any, required: set[str], optional: set[str] = frozenset()) -> dict[str, Any]:
    if type(value) is not dict:
        raise CanonError("expected_object")
    if set(value) - required - optional or required - set(value):
        raise CanonError("invalid_fields", ",".join(sorted(set(value) ^ required)))
    return value


def _text(value: Any, field: str, limit: int = 400) -> str:
    if type(value) is not str or not value or len(value) > limit:
        raise CanonError("invalid_text", field)
    # Lone UTF-16 surrogates are valid Python str values but cannot be
    # serialized as UTF-8. Reject at the typed boundary, not during publish.
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise CanonError("invalid_unicode_scalar", field)
    if unicodedata.normalize("NFC", value) != value:
        raise CanonError("noncanonical_unicode", field)
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in value):
        raise CanonError("control_character", field)
    return value


def _id(value: Any, field: str) -> str:
    if type(value) is not str or ID_RE.fullmatch(value) is None:
        raise CanonError("invalid_identifier", field)
    return value


def _list(value: Any, field: str, limit: int) -> list[Any]:
    if type(value) is not list or len(value) > limit:
        raise CanonError("invalid_list", field)
    return value


def _flags(value: Any, field: str) -> list[str]:
    flags = [_id(v, field) for v in _list(value, field, MAX_FLAGS)]
    if len(set(flags)) != len(flags) or flags != sorted(flags):
        raise CanonError("flags_not_canonical", field)
    return flags


def validate(source: Any) -> dict[str, Any]:
    obj = _keys(source, {"schema", "id", "prompt", "protagonist", "region",
                         "start", "scenes", "choices", "endings"})
    if obj["schema"] != SCHEMA:
        raise CanonError("schema_mismatch")
    _id(obj["id"], "id")
    _text(obj["prompt"], "prompt", 4096)
    _text(obj["protagonist"], "protagonist")
    _text(obj["region"], "region")
    _id(obj["start"], "start")
    scenes = _list(obj["scenes"], "scenes", MAX_SCENES)
    choices = _list(obj["choices"], "choices", MAX_CHOICES)
    endings = _list(obj["endings"], "endings", MAX_SCENES)
    if not scenes or not endings:
        raise CanonError("empty_world")
    scene_ids: set[str] = set()
    for scene in scenes:
        _keys(scene, {"id", "title", "narrative"})
        sid = _id(scene["id"], "scene.id")
        if sid in scene_ids:
            raise CanonError("duplicate_scene", sid)
        scene_ids.add(sid)
        _text(scene["title"], "scene.title")
        _text(scene["narrative"], "scene.narrative", 4096)
    if obj["start"] not in scene_ids:
        raise CanonError("unknown_start")
    ending_ids: set[str] = set()
    for ending in endings:
        _keys(ending, {"scene", "label"})
        eid = _id(ending["scene"], "ending.scene")
        if eid in ending_ids or eid not in scene_ids:
            raise CanonError("invalid_ending", eid)
        ending_ids.add(eid)
        _text(ending["label"], "ending.label")
    choice_ids: set[str] = set()
    for choice in choices:
        _keys(choice, {"id", "from", "to", "label", "requires", "grants"})
        cid = _id(choice["id"], "choice.id")
        if cid in choice_ids:
            raise CanonError("duplicate_choice", cid)
        choice_ids.add(cid)
        if _id(choice["from"], "choice.from") not in scene_ids:
            raise CanonError("unknown_choice_source", cid)
        if _id(choice["to"], "choice.to") not in scene_ids:
            raise CanonError("unknown_choice_target", cid)
        if choice["from"] in ending_ids:
            raise CanonError("outgoing_from_ending", cid)
        _text(choice["label"], "choice.label")
        _flags(choice["requires"], "choice.requires")
        _flags(choice["grants"], "choice.grants")
    if len(canonical(obj)) > MAX_SOURCE_BYTES:
        raise CanonError("source_too_large")
    return obj


@dataclass(frozen=True)
class Proof:
    source_digest: str
    visited_scenes: tuple[str, ...]
    ending_witnesses: dict[str, tuple[str, ...]]
    states_explored: int

    def as_dict(self) -> dict[str, Any]:
        return {"source_digest": self.source_digest,
                "visited_scenes": list(self.visited_scenes),
                "ending_witnesses": {k: list(v) for k, v in
                                     sorted(self.ending_witnesses.items())},
                "states_explored": self.states_explored}


def prove(source: Any) -> Proof:
    world = validate(source)
    edges: dict[str, list[dict[str, Any]]] = {}
    for edge in world["choices"]:
        edges.setdefault(edge["from"], []).append(edge)
    for value in edges.values():
        value.sort(key=lambda item: item["id"])
    endings = {e["scene"] for e in world["endings"]}
    initial = (world["start"], frozenset())
    queue = deque([(initial, ())])
    visited = {initial}
    scene_seen: set[str] = set()
    witnesses: dict[str, tuple[str, ...]] = {}
    while queue:
        (scene, flags), path = queue.popleft()
        scene_seen.add(scene)
        if scene in endings:
            witnesses.setdefault(scene, path)
            continue
        outgoing = edges.get(scene, [])
        enabled = [e for e in outgoing if set(e["requires"]) <= flags]
        if not enabled:
            raise CanonError("reachable_dead_end", scene)
        for edge in enabled:
            state = (edge["to"], flags | frozenset(edge["grants"]))
            if state not in visited:
                visited.add(state)
                if len(visited) > MAX_STATES:
                    raise CanonError("state_budget_exhausted")
                queue.append((state, path + (edge["id"],)))
    if scene_seen != {s["id"] for s in world["scenes"]}:
        raise CanonError("unreachable_scenes",
                         ",".join(sorted({s["id"] for s in world["scenes"]} - scene_seen)))
    if set(witnesses) != endings:
        raise CanonError("unreachable_endings", ",".join(sorted(endings - set(witnesses))))
    return Proof(digest(world), tuple(sorted(scene_seen)), witnesses, len(visited))


def propose(*, world_id: str, premise: str, protagonist: str,
            region: str, goal: str) -> dict[str, Any]:
    """Make a minimal, explicitly authored proposal from a user's own brief."""
    _id(world_id, "world_id")
    _text(premise, "premise", 4096)
    _text(protagonist, "protagonist")
    _text(region, "region")
    _text(goal, "goal")
    source = {
        "schema": SCHEMA, "id": world_id, "prompt": premise,
        "protagonist": protagonist, "region": region, "start": "opening",
        "scenes": [
            {"id": "opening", "title": f"{protagonist} in {region}",
             "narrative": premise},
            {"id": "resolution", "title": "An authored resolution",
             "narrative": goal},
        ],
        "choices": [
            {"id": "pursue_goal", "from": "opening", "to": "resolution",
             "label": f"Pursue: {goal}", "requires": [], "grants": []},
        ],
        "endings": [{"scene": "resolution", "label": goal}],
    }
    prove(source)
    return source


def edit(source: Any, operation: Mapping[str, Any]) -> dict[str, Any]:
    """Atomic typed edit transaction: intermediate graph states never publish.

    A batch lets an author add a scene, its incoming choice and its ending
    together, without disabling referential or temporal proof.
    """
    world = validate(source)
    candidate = strict_json(canonical(world))
    top = _keys(operation, {"action", "value"})
    if top["action"] == "batch":
        operations = _list(top["value"], "batch", 64)
        if not operations:
            raise CanonError("empty_edit_batch")
    else:
        operations = [top]
    for operation_item in operations:
        op = _keys(operation_item, {"action", "value"})
        action = op["action"]
        value = op["value"]
        if action == "add_scene":
            _keys(value, {"id", "title", "narrative"})
            candidate["scenes"].append(value)
        elif action == "add_choice":
            _keys(value, {"id", "from", "to", "label", "requires", "grants"})
            candidate["choices"].append(value)
        elif action == "add_ending":
            _keys(value, {"scene", "label"})
            candidate["endings"].append(value)
        elif action in {"replace_scene", "replace_choice", "replace_ending"}:
            required = ({"id", "title", "narrative"} if action == "replace_scene"
                        else {"id", "from", "to", "label", "requires", "grants"}
                        if action == "replace_choice" else {"scene", "label"})
            _keys(value, required)
            key = "scene" if action == "replace_ending" else "id"
            collection = ("endings" if action == "replace_ending"
                          else "choices" if action == "replace_choice" else "scenes")
            matches = [i for i, item in enumerate(candidate[collection])
                       if item[key] == value[key]]
            if len(matches) != 1:
                raise CanonError("unknown_edit_target", str(value[key]))
            candidate[collection][matches[0]] = value
        elif action in {"remove_scene", "remove_choice", "remove_ending"}:
            _keys(value, {"id"})
            collection = ("scenes" if action == "remove_scene" else
                          "choices" if action == "remove_choice" else "endings")
            key = "scene" if action == "remove_ending" else "id"
            before = len(candidate[collection])
            candidate[collection] = [item for item in candidate[collection]
                                     if item[key] != value["id"]]
            if len(candidate[collection]) != before - 1:
                raise CanonError("unknown_edit_target", str(value["id"]))
        else:
            raise CanonError("unsupported_edit", str(action))
    prove(candidate)
    return candidate

def compile_manifest(source: Any) -> dict[str, Any]:
    proof = prove(source)
    return {"schema": PLAYABLE_SCHEMA, "world": source,
            "proof": proof.as_dict()}


_PLAYER_JS = r"""
"use strict";
const model = JSON.parse(document.getElementById("world-data").textContent);
const world = model.world;
const byId = new Map(world.scenes.map(s => [s.id, s]));
const ending = new Map(world.endings.map(e => [e.scene, e.label]));
let current = world.start;
let flags = new Set();
let trace = [];
const root = document.getElementById("play");
function element(tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
}
function render() {
  root.replaceChildren();
  const scene = byId.get(current);
  root.append(element("h1", scene.title));
  root.append(element("p", scene.narrative));
  root.append(element("p", "Choices taken: " + trace.join(", ")));
  if (ending.has(current)) {
    root.append(element("h2", "Ending: " + ending.get(current)));
    const restart = element("button", "Restart");
    restart.addEventListener("click", () => {
      current = world.start; flags = new Set(); trace = []; render();
    });
    root.append(restart);
    return;
  }
  const choices = world.choices.filter(c => c.from === current &&
    c.requires.every(f => flags.has(f)));
  for (const choice of choices) {
    const button = element("button", choice.label);
    button.addEventListener("click", () => {
      for (const flag of choice.grants) flags.add(flag);
      trace.push(choice.id);
      current = choice.to;
      render();
    });
    root.append(button);
  }
}
render();
""".strip()


def compile_html(source: Any) -> str:
    import html
    import base64
    manifest = compile_manifest(source)
    # Escaping '<' prevents embedded JSON from terminating its script element.
    embedded = canonical(manifest).decode("utf-8").replace("<", "\\u003c")
    policy_hash = base64.b64encode(sha256(_PLAYER_JS.encode()).digest()).decode()
    title = html.escape(source["id"], quote=True)
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
        f"script-src 'sha256-{policy_hash}'; style-src 'none'; "
        "connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'\">"
        f"<title>{title}</title></head><body><main id=\"play\" aria-live=\"polite\">"
        "</main><script id=\"world-data\" type=\"application/json\">"
        f"{embedded}</script><script>{_PLAYER_JS}</script></body></html>\n"
    )


class WorldStore:
    """Descriptor-anchored local custody; explicit exclusive lease per world.

    Requires POSIX dir_fd and O_NOFOLLOW.  Unknown platforms fail closed rather
    than quietly falling back to symlink-following path operations.
    """
    def __init__(self, root: str | os.PathLike[str]) -> None:
        if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
            raise CanonError("platform_not_supported")
        path = Path(root)
        if path.is_symlink():
            raise CanonError("symlink_root")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.is_symlink():
            raise CanonError("symlink_root")
        self.root = path

    def _directory(self) -> int:
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            os.close(fd)
            raise CanonError("not_directory")
        return fd

    @staticmethod
    def _read(fd: int, name: str) -> bytes:
        try:
            handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=fd)
        except FileNotFoundError:
            raise CanonError("not_found", name) from None
        try:
            info = os.fstat(handle)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SOURCE_BYTES:
                raise CanonError("unsafe_source_file", name)
            with os.fdopen(os.dup(handle), "rb") as stream:
                data = stream.read(MAX_SOURCE_BYTES + 1)
            if len(data) > MAX_SOURCE_BYTES:
                raise CanonError("source_too_large")
            return data
        finally:
            os.close(handle)

    @staticmethod
    def _write(fd: int, name: str, data: bytes) -> None:
        if len(data) > MAX_SOURCE_BYTES * 3:
            raise CanonError("output_too_large")
        import secrets
        temp = "." + secrets.token_hex(16) + ".tmp"
        handle = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            with os.fdopen(handle, "wb", closefd=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        finally:
            os.close(handle)
            try:
                os.unlink(temp, dir_fd=fd)
            except FileNotFoundError:
                pass

    def read(self, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self._directory()
        try:
            source = strict_json(self._read(fd, world_id + ".json"))
            validate(source)
            if source.get("id") != world_id:
                raise CanonError("identity_mismatch")
            prove(source)
            return source
        finally:
            os.close(fd)

    def publish(self, source: Any, *, expected_digest: str | None = None,
                create: bool = False) -> str:
        proof = prove(source)
        world_id = source["id"]
        if create and expected_digest is not None:
            raise CanonError("invalid_lease")
        fd = self._directory()
        lock = world_id + ".lock"
        try:
            try:
                lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                  os.O_NOFOLLOW, 0o600, dir_fd=fd)
            except FileExistsError:
                raise CanonError("lease_busy") from None
            try:
                os.close(lock_fd)
                try:
                    existing = strict_json(self._read(fd, world_id + ".json"))
                    old_digest = prove(existing).source_digest
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old_digest = None
                if create:
                    if old_digest is not None:
                        raise CanonError("already_exists")
                elif old_digest is None or expected_digest != old_digest:
                    raise CanonError("stale_source")
                self._write(fd, world_id + ".json", canonical(source))
                return proof.source_digest
            finally:
                os.unlink(lock, dir_fd=fd)
        finally:
            os.close(fd)

    def compile(self, world_id: str, expected_digest: str) -> dict[str, str]:
        _id(world_id, "world_id")
        source = self.read(world_id)
        proof = prove(source)
        if proof.source_digest != expected_digest:
            raise CanonError("stale_source")
        output = compile_html(source).encode("utf-8")
        fd = self._directory()
        try:
            # Recheck under exclusive lease to avoid publishing an old revision.
            lock = world_id + ".lock"
            try:
                lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                  os.O_NOFOLLOW, 0o600, dir_fd=fd)
            except FileExistsError:
                raise CanonError("lease_busy") from None
            try:
                os.close(lock_fd)
                if digest(strict_json(self._read(fd, world_id + ".json"))) != expected_digest:
                    raise CanonError("stale_source")
                self._write(fd, world_id + ".html", output)
                return {"world_id": world_id, "source_digest": expected_digest,
                        "html_sha256": sha256(output).hexdigest(),
                        "html_file": world_id + ".html"}
            finally:
                os.unlink(lock, dir_fd=fd)
        finally:
            os.close(fd)
