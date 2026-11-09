"""Reviewed cross-world portal routes with independent canonical world custody.

World scenes and choices remain immutable; portals are an explicitly authored
overlay connecting a proven ending to another world's canonical start.
"""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from hashlib import sha256
import base64
import html
import os
import re
from typing import Any, Iterator

from .bundle import _artifact_read
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text,
    canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.portals.v1"
HANDOFF_SCHEMA = "jeeves.world.portals_handoff.v1"
RECEIPT_SCHEMA = "jeeves.world.portals_receipt.v1"
MAX_WORLDS = 8
MAX_PORTALS = 32
MAX_NETWORK_BYTES = 524288
MAX_HTML_BYTES = 1572864
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def validate_network(network: Any, worlds: dict[str, Any]) -> dict[str, Any]:
    obj = _keys(network, {
        "schema", "id", "prompt", "root_world", "world_digests",
        "portals", "approved", "review_note",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("portals_schema_mismatch")
    _id(obj["id"], "network.id")
    _text(obj["prompt"], "network.prompt", 4096)
    _text(obj["review_note"], "review_note", 512)
    if type(obj["approved"]) is not bool:
        raise CanonError("portals_invalid_approval")
    ids = obj["world_digests"]
    if type(ids) is not dict or not 2 <= len(ids) <= MAX_WORLDS:
        raise CanonError("portals_invalid_worlds")
    for wid, expected in ids.items():
        _id(wid, "world.id")
        if type(expected) is not str or not SHA256.fullmatch(expected):
            raise CanonError("portals_invalid_digest")
    if set(ids) != set(worlds):
        raise CanonError("portals_missing_world_sources")
    for wid, world in worlds.items():
        if world.get("id") != wid or prove(world).source_digest != ids[wid]:
            raise CanonError("portals_world_lease_mismatch", wid)
    root = _id(obj["root_world"], "root_world")
    if root not in ids:
        raise CanonError("portals_unknown_root")
    portals = _list(obj["portals"], "portals", MAX_PORTALS)
    seen: set[str] = set()
    edges: dict[str, list[str]] = {}
    endings = {
        wid: {e["scene"] for e in world["endings"]}
        for wid, world in worlds.items()
    }
    for portal in portals:
        _keys(portal, {"id", "from_world", "from_ending", "to_world", "label"})
        pid = _id(portal["id"], "portal.id")
        src = _id(portal["from_world"], "portal.from_world")
        dst = _id(portal["to_world"], "portal.to_world")
        ending = _id(portal["from_ending"], "portal.from_ending")
        _text(portal["label"], "portal.label", 400)
        if pid in seen:
            raise CanonError("portals_duplicate_portal", pid)
        seen.add(pid)
        if src not in worlds or dst not in worlds or src == dst:
            raise CanonError("portals_invalid_destination", pid)
        if ending not in endings[src]:
            raise CanonError("portals_invalid_source_ending", pid)
        edges.setdefault(src, []).append(dst)
    if [item["id"] for item in portals] != sorted(seen):
        raise CanonError("portals_not_sorted")
    reachable = {root}
    queue = deque([root])
    while queue:
        wid = queue.popleft()
        for dst in sorted(set(edges.get(wid, []))):
            if dst not in reachable:
                reachable.add(dst)
                queue.append(dst)
    if reachable != set(worlds):
        raise CanonError("portals_unreachable_worlds")
    if len(canonical(obj)) > MAX_NETWORK_BYTES:
        raise CanonError("portals_source_too_large")
    return obj


def propose_network(worlds: dict[str, Any], *, network_id: str,
                    prompt: str, root_world: str,
                    from_ending: str, to_world: str) -> dict[str, Any]:
    _id(network_id, "network_id")
    _text(prompt, "prompt", 4096)
    if len(worlds) != 2:
        raise CanonError("portals_proposal_requires_two_worlds")
    network = {
        "schema": SCHEMA, "id": network_id, "prompt": prompt,
        "root_world": root_world,
        "world_digests": {wid: prove(world).source_digest
                          for wid, world in sorted(worlds.items())},
        "portals": [{
            "id": "first_crossing", "from_world": root_world,
            "from_ending": from_ending, "to_world": to_world,
            "label": "Continue the original journey",
        }],
        "approved": False, "review_note": "Awaiting operator portal review.",
    }
    return validate_network(network, worlds)


def approve_network(network: Any, worlds: dict[str, Any],
                    review_note: str) -> dict[str, Any]:
    validate_network(network, worlds)
    _text(review_note, "review_note", 512)
    candidate = strict_json(canonical(network))
    candidate["approved"] = True
    candidate["review_note"] = review_note
    return validate_network(candidate, worlds)


def network_report(network: Any, worlds: dict[str, Any]) -> dict[str, Any]:
    validate_network(network, worlds)
    edges: dict[str, list[dict[str, Any]]] = {}
    for portal in network["portals"]:
        edges.setdefault(portal["from_world"], []).append(portal)
    for items in edges.values():
        items.sort(key=lambda item: item["id"])
    root = network["root_world"]
    queue = deque([(root, ())])
    seen = {root}
    witnesses: dict[str, list[dict[str, Any]]] = {root: []}
    while queue:
        wid, path = queue.popleft()
        for portal in edges.get(wid, []):
            dst = portal["to_world"]
            if dst in seen:
                continue
            source_proof = prove(worlds[wid])
            choice_path = source_proof.ending_witnesses[portal["from_ending"]]
            step = {
                "portal": portal["id"], "from_world": wid,
                "to_world": dst, "ending": portal["from_ending"],
                "source_choice_trace": list(choice_path),
            }
            next_path = path + (step,)
            witnesses[dst] = list(next_path)
            seen.add(dst)
            queue.append((dst, next_path))
    if seen != set(worlds):
        raise CanonError("portals_unreachable_worlds")
    return {
        "schema": HANDOFF_SCHEMA, "network_id": network["id"],
        "network_digest": digest(network),
        "root_world": root, "world_digests": network["world_digests"],
        "world_witnesses": {k: witnesses[k] for k in sorted(witnesses)},
        "approved": network["approved"],
        "qualification": "verified_world_source_paths_not_device_certified",
    }


PLAYER_JS = r"""
"use strict";
const model = JSON.parse(document.getElementById("portals-data").textContent);
const network = model.network;
const worlds = model.worlds;
const byWorld = new Map(Object.entries(worlds));
const portals = network.portals;
let currentWorld = network.root_world;
let currentScene = worlds[currentWorld].start;
let flags = new Map(Object.keys(worlds).map(id => [id, new Set()]));
let trace = [];
let steps = [];
let moves = 0;
const root = document.getElementById("play");
function element(tag, text) {
  const item = document.createElement(tag);
  item.textContent = text;
  return item;
}
function reset() {
  currentWorld = network.root_world;
  currentScene = worlds[currentWorld].start;
  flags = new Map(Object.keys(worlds).map(id => [id, new Set()]));
  trace = []; steps = []; moves = 0; render();
}
function button(text, action) {
  const item = element("button", text);
  item.type = "button";
  item.addEventListener("click", action);
  root.append(item);
}
function exportSession() {
  const state = {
    schema: "jeeves.world.portal_session.v1",
    network_id: network.id,
    network_digest: model.proof.network_digest,
    world_digests: network.world_digests,
    steps: steps.map(step => ({...step})),
    current_world: currentWorld,
    current_scene: currentScene,
    flags: Object.fromEntries(
      [...flags.entries()].map(([id, values]) => [id, [...values].sort()])
    )
  };
  let area = document.getElementById("session-export");
  if (!area) {
    area = document.createElement("textarea");
    area.id = "session-export";
    area.readOnly = true;
    area.rows = 10;
    area.setAttribute("aria-label", "Source-bound session JSON for operator review");
    root.append(area);
  }
  area.value = JSON.stringify(state);
  area.focus();
  area.select();
}

function showSessionImport() {
  let area = document.getElementById("session-import");
  if (!area) {
    area = document.createElement("textarea");
    area.id = "session-import";
    area.rows = 10;
    area.setAttribute("aria-label", "Paste untrusted session JSON to replay locally");
    root.append(area);
    button("Restore locally checked session", restoreSession);
  }
  area.focus();
}
function restoreSession() {
  const area = document.getElementById("session-import");
  let error = document.getElementById("session-error");
  if (!error) {
    error = element("p", "");
    error.id = "session-error";
    root.append(error);
  }
  try {
    if (!area || area.value.length > 524288) throw Error("Session exceeds limit");
    const data = JSON.parse(area.value);
    const fields = [
      "schema", "network_id", "network_digest", "world_digests",
      "steps", "current_world", "current_scene", "flags"
    ];
    if (!data || typeof data !== "object" || Array.isArray(data) ||
        JSON.stringify(Object.keys(data).sort()) !==
        JSON.stringify(fields.sort())) throw Error("Session fields invalid");
    if (data.schema !== "jeeves.world.portal_session.v1" ||
        data.network_id !== network.id ||
        data.network_digest !== model.proof.network_digest)
      throw Error("Session source lease mismatch");
    const worldIds = Object.keys(worlds).sort();
    if (!data.world_digests || typeof data.world_digests !== "object" ||
        JSON.stringify(Object.keys(data.world_digests).sort()) !==
        JSON.stringify(worldIds) ||
        worldIds.some(id => data.world_digests[id] !== network.world_digests[id]))
      throw Error("Session world lease mismatch");
    if (!Array.isArray(data.steps) || data.steps.length > 256)
      throw Error("Session move limit exceeded");
    let wid = network.root_world;
    let sid = worlds[wid].start;
    const restoredFlags = new Map(worldIds.map(id => [id, new Set()]));
    const restoredSteps = [];
    const restoredTrace = [];
    for (const step of data.steps) {
      if (!step || typeof step !== "object" || Array.isArray(step) ||
          JSON.stringify(Object.keys(step).sort()) !==
          '["id","kind","world"]' ||
          step.world !== wid || typeof step.id !== "string")
        throw Error("Session step invalid");
      const world = worlds[wid];
      if (step.kind === "choice") {
        if (world.endings.some(e => e.scene === sid))
          throw Error("Choice after ending");
        const choice = world.choices.find(c => c.id === step.id && c.from === sid);
        if (!choice || !choice.requires.every(flag => restoredFlags.get(wid).has(flag)))
          throw Error("Unreachable or unearned choice");
        choice.grants.forEach(flag => restoredFlags.get(wid).add(flag));
        restoredTrace.push(wid + ":" + choice.id);
        sid = choice.to;
      } else if (step.kind === "portal") {
        if (!world.endings.some(e => e.scene === sid))
          throw Error("Portal before ending");
        const portal = portals.find(p => p.id === step.id &&
          p.from_world === wid && p.from_ending === sid);
        if (!portal) throw Error("Invalid portal crossing");
        restoredTrace.push("portal:" + portal.id);
        wid = portal.to_world;
        sid = worlds[wid].start;
      } else throw Error("Invalid move type");
      restoredSteps.push({kind: step.kind, world: step.world, id: step.id});
    }
    if (data.current_world !== wid || data.current_scene !== sid ||
        !data.flags || typeof data.flags !== "object" ||
        JSON.stringify(Object.keys(data.flags).sort()) !== JSON.stringify(worldIds))
      throw Error("Session position mismatch");
    for (const id of worldIds) {
      const declared = data.flags[id];
      const actual = [...restoredFlags.get(id)].sort();
      if (!Array.isArray(declared) ||
          JSON.stringify(declared) !== JSON.stringify(actual))
        throw Error("Session flags mismatch");
    }
    currentWorld = wid; currentScene = sid;
    flags = restoredFlags; steps = restoredSteps;
    trace = restoredTrace; moves = steps.length;
    render();
  } catch (_) {
    error.textContent = "Session rejected: invalid, stale or unearned replay.";
  }
}
function render() {
  root.replaceChildren();
  const world = byWorld.get(currentWorld);
  const scene = world.scenes.find(s => s.id === currentScene);
  const ending = world.endings.find(e => e.scene === currentScene);
  root.append(element("h1", world.region + " — " + scene.title));
  root.append(element("p", scene.narrative));
  root.append(element("p", "World: " + currentWorld + " | Moves: " + moves));
  root.append(element("p", "Choice/portal history: " + trace.join(", ")));
  button("Export session JSON", exportSession);
  button("Import session JSON", showSessionImport);
  if (moves >= 256) {
    root.append(element("p", "Bounded play session completed."));
    button("Restart", reset);
    return;
  }
  if (ending) {
    root.append(element("h2", "Ending: " + ending.label));
    const options = portals.filter(p => p.from_world === currentWorld &&
      p.from_ending === currentScene);
    for (const portal of options) {
      button("Travel: " + portal.label, () => {
        currentWorld = portal.to_world;
        currentScene = worlds[currentWorld].start;
        steps.push({kind: "portal", world: portal.from_world, id: portal.id});
        trace.push("portal:" + portal.id);
        moves += 1; render();
      });
    }
    button("Restart", reset);
    return;
  }
  const available = world.choices.filter(c => c.from === currentScene &&
    c.requires.every(flag => flags.get(currentWorld).has(flag)));
  for (const choice of available) {
    button(choice.label, () => {
      for (const flag of choice.grants) flags.get(currentWorld).add(flag);
      currentScene = choice.to;
      steps.push({kind: "choice", world: currentWorld, id: choice.id});
      trace.push(currentWorld + ":" + choice.id);
      moves += 1; render();
    });
  }
}
render();
""".strip()


def render_playable(network: Any, worlds: dict[str, Any]) -> bytes:
    if not network["approved"]:
        raise CanonError("portals_review_required")
    report = network_report(network, worlds)
    embedded = canonical({
        "network": network, "worlds": worlds, "proof": report,
    }).decode("utf-8").replace("<", "\\u003c")
    script_hash = base64.b64encode(sha256(PLAYER_JS.encode()).digest()).decode()
    title = html.escape(network["id"], quote=True)
    output = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + script_hash +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'\">"
        "<title>Original world portals: " + title + "</title></head><body>"
        '<main id="play" aria-live="polite"></main>'
        '<script id="portals-data" type="application/json">' + embedded +
        "</script><script>" + PLAYER_JS + "</script></body></html>\n"
    ).encode("utf-8")
    if len(output) > MAX_HTML_BYTES:
        raise CanonError("portals_playable_too_large")
    return output


class PortalStore:
    """Descriptor-anchored custody with sorted multi-world exclusive locks."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(network_id: str) -> tuple[str, str, str]:
        _id(network_id, "network_id")
        return (
            network_id + ".portals.json",
            network_id + ".portals.playable.html",
            network_id + ".portals.receipt.json",
        )

    @staticmethod
    def _world_ids(network: Any) -> list[str]:
        if type(network) is not dict or type(network.get("world_digests")) is not dict:
            raise CanonError("portals_invalid_worlds")
        ids = network["world_digests"]
        if not 2 <= len(ids) <= MAX_WORLDS:
            raise CanonError("portals_invalid_worlds")
        return sorted(_id(wid, "world.id") for wid in ids)

    @staticmethod
    @contextmanager
    def _locks(fd: int, names: list[str]) -> Iterator[None]:
        created: list[str] = []
        try:
            for name in sorted(set(names)):
                try:
                    handle = os.open(
                        name + ".lock",
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600, dir_fd=fd,
                    )
                except FileExistsError:
                    raise CanonError("lease_busy", name) from None
                os.close(handle)
                created.append(name + ".lock")
            yield
        finally:
            for name in reversed(created):
                os.unlink(name, dir_fd=fd)

    def _sources(self, fd: int, ids: list[str]) -> dict[str, Any]:
        worlds: dict[str, Any] = {}
        for wid in ids:
            source = strict_json(self.worlds._read(fd, wid + ".json"))
            prove(source)
            if source["id"] != wid:
                raise CanonError("portals_world_identity_mismatch", wid)
            worlds[wid] = source
        return worlds

    def _read(self, fd: int, network_id: str) -> dict[str, Any]:
        data = strict_json(self.worlds._read(fd, self._names(network_id)[0]))
        if type(data) is not dict or data.get("id") != network_id:
            raise CanonError("portals_network_identity_mismatch")
        return data

    def propose(self, network_id: str, prompt: str, *,
                root_world: str, from_ending: str,
                to_world: str) -> dict[str, Any]:
        ids = sorted({_id(root_world, "root_world"), _id(to_world, "to_world")})
        fd = self.worlds._directory()
        try:
            worlds = self._sources(fd, ids)
            return propose_network(
                worlds, network_id=network_id, prompt=prompt,
                root_world=root_world, from_ending=from_ending,
                to_world=to_world,
            )
        finally:
            os.close(fd)

    def inspect(self, network_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            network = self._read(fd, network_id)
            worlds = self._sources(fd, self._world_ids(network))
            return {"network": validate_network(network, worlds),
                    "report": network_report(network, worlds)}
        finally:
            os.close(fd)

    def save(self, network_id: str, network: Any, *,
             expected_network_digest: str | None = None,
             create: bool = False) -> str:
        _id(network_id, "network_id")
        ids = self._world_ids(network)
        fd = self.worlds._directory()
        try:
            with self._locks(fd, [network_id + ".portals"] + ids):
                worlds = self._sources(fd, ids)
                validate_network(network, worlds)
                if network["id"] != network_id:
                    raise CanonError("portals_network_identity_mismatch")
                if network["approved"]:
                    raise CanonError("portals_approval_requires_review")
                try:
                    existing = self._read(fd, network_id)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    existing = None
                if create:
                    if existing is not None or expected_network_digest is not None:
                        raise CanonError("portals_already_exists")
                elif existing is None or digest(existing) != expected_network_digest:
                    raise CanonError("portals_stale_edit")
                self.worlds._write(fd, self._names(network_id)[0], canonical(network))
                return digest(network)
        finally:
            os.close(fd)

    def approve(self, network_id: str, *, expected_network_digest: str,
                review_note: str) -> str:
        fd = self.worlds._directory()
        try:
            network = self._read(fd, network_id)
            ids = self._world_ids(network)
            with self._locks(fd, [network_id + ".portals"] + ids):
                network = self._read(fd, network_id)
                worlds = self._sources(fd, ids)
                validate_network(network, worlds)
                if digest(network) != expected_network_digest:
                    raise CanonError("portals_stale_edit")
                approved = approve_network(network, worlds, review_note)
                self.worlds._write(fd, self._names(network_id)[0], canonical(approved))
                return digest(approved)
        finally:
            os.close(fd)

    def _outputs(self, network: Any, worlds: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
        report = network_report(network, worlds)
        playable = render_playable(network, worlds)
        name = self._names(network["id"])[1]
        receipt = {
            "schema": RECEIPT_SCHEMA, "network_id": network["id"],
            "network_digest": digest(network),
            "world_digests": network["world_digests"],
            "handoff": report,
            "artifacts": {name: sha256(playable).hexdigest()},
            "qualification": "original_offline_playable_not_device_or_release_certified",
        }
        if len(canonical(receipt)) > MAX_NETWORK_BYTES:
            raise CanonError("portals_receipt_too_large")
        return receipt, playable

    def editor(self, network_id: str, *, expected_network_digest: str) -> dict[str, str]:
        """Write a CSP-bound offline editor under the same multi-world lease."""
        from .portals_editor import render_editor
        fd = self.worlds._directory()
        try:
            network = self._read(fd, network_id)
            ids = self._world_ids(network)
            with self._locks(fd, [network_id + ".portals"] + ids):
                network = self._read(fd, network_id)
                worlds = self._sources(fd, ids)
                if digest(network) != expected_network_digest:
                    raise CanonError("portals_stale_edit")
                output = render_editor(network, worlds)
                name = network_id + ".portals.editor.html"
                self.worlds._write(fd, name, output)
                return {"html_file": name, "html_sha256": sha256(output).hexdigest(),
                        "network_digest": digest(network)}
        finally:
            os.close(fd)

    def compile(self, network_id: str, *, expected_network_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            network = self._read(fd, network_id)
            ids = self._world_ids(network)
            with self._locks(fd, [network_id + ".portals"] + ids):
                network = self._read(fd, network_id)
                worlds = self._sources(fd, ids)
                if digest(network) != expected_network_digest:
                    raise CanonError("portals_stale_edit")
                receipt, playable = self._outputs(network, worlds)
                names = self._names(network_id)
                self.worlds._write(fd, names[1], playable)
                self.worlds._write(fd, names[2], canonical(receipt))
                return receipt
        finally:
            os.close(fd)

    def verify(self, network_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            network = self._read(fd, network_id)
            ids = self._world_ids(network)
            with self._locks(fd, [network_id + ".portals"] + ids):
                network = self._read(fd, network_id)
                worlds = self._sources(fd, ids)
                receipt, playable = self._outputs(network, worlds)
                names = self._names(network_id)
                if strict_json(self.worlds._read(fd, names[2])) != receipt:
                    raise CanonError("portals_receipt_mismatch")
                if _artifact_read(fd, names[1]) != playable:
                    raise CanonError("portals_playable_mismatch")
                return receipt
        finally:
            os.close(fd)

    @staticmethod
    def _session_name(network_id: str, slot: str) -> str:
        _id(network_id, "network_id")
        _id(slot, "slot")
        return network_id + ".portals.session." + slot + ".json"

    def preview_session(self, network_id: str, session: Any) -> dict[str, Any]:
        """Read-only, untrusted trace proof for the Jeeves planning interface."""
        from .portals_replay import replay_session
        fd = self.worlds._directory()
        try:
            network = self._read(fd, network_id)
            worlds = self._sources(fd, self._world_ids(network))
            return replay_session(session, network, worlds)
        finally:
            os.close(fd)

    def _check_playable(self, fd: int, network: Any,
                        worlds: dict[str, Any]) -> None:
        receipt, playable = self._outputs(network, worlds)
        names = self._names(network["id"])
        if strict_json(self.worlds._read(fd, names[2])) != receipt:
            raise CanonError("portals_receipt_mismatch")
        if _artifact_read(fd, names[1]) != playable:
            raise CanonError("portals_playable_mismatch")

    def record_session(
        self, network_id: str, slot: str, session: Any, *,
        expected_network_digest: str,
        expected_session_digest: str | None = None,
        create: bool = False,
    ) -> dict[str, Any]:
        """CAS-persist a verified trace, never trusting browser-reported state."""
        from .portals_replay import STORED_SCHEMA, replay_session
        name = self._session_name(network_id, slot)
        fd = self.worlds._directory()
        try:
            network = self._read(fd, network_id)
            ids = self._world_ids(network)
            with self._locks(fd, [network_id + ".portals", name] + ids):
                network = self._read(fd, network_id)
                worlds = self._sources(fd, ids)
                if digest(network) != expected_network_digest:
                    raise CanonError("portals_stale_edit")
                self._check_playable(fd, network, worlds)
                report = replay_session(session, network, worlds)
                stored = {"schema": STORED_SCHEMA, "session": session,
                          "report": report}
                try:
                    old = strict_json(self.worlds._read(fd, name))
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_session_digest is not None:
                        raise CanonError("portal_session_already_exists")
                elif old is None or digest(old) != expected_session_digest:
                    raise CanonError("portal_session_stale_edit")
                self.worlds._write(fd, name, canonical(stored))
                return {"session_digest": digest(stored), "report": report}
        finally:
            os.close(fd)

    def verify_session(self, network_id: str, slot: str) -> dict[str, Any]:
        """Recompute saved source proof; reject stale and forged receipts."""
        from .portals_replay import STORED_SCHEMA, replay_session
        name = self._session_name(network_id, slot)
        fd = self.worlds._directory()
        try:
            network = self._read(fd, network_id)
            ids = self._world_ids(network)
            with self._locks(fd, [network_id + ".portals", name] + ids):
                network = self._read(fd, network_id)
                worlds = self._sources(fd, ids)
                self._check_playable(fd, network, worlds)
                stored = strict_json(self.worlds._read(fd, name))
                _keys(stored, {"schema", "session", "report"})
                if stored["schema"] != STORED_SCHEMA:
                    raise CanonError("portal_session_schema_mismatch")
                report = replay_session(stored["session"], network, worlds)
                if report != stored["report"]:
                    raise CanonError("portal_session_receipt_mismatch")
                return {"session_digest": digest(stored), "report": report}
        finally:
            os.close(fd)
