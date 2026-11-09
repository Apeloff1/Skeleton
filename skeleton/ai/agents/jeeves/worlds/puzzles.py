"""Original scene puzzles with reviewed answers and proof-bound choice unlocks.

Puzzles are not arbitrary scripts: an exact authored answer unlocks a named
canonical choice. The bounded verifier explores solving and travelling so a
playable cannot silently strand a player behind an impossible gate.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import base64
import html
import os
from typing import Any

from .bundle import _artifact_read
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text,
    canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.puzzles.v1"
PROOF_SCHEMA = "jeeves.world.puzzles_proof.v1"
RECEIPT_SCHEMA = "jeeves.world.puzzles_receipt.v1"
MAX_PUZZLES = 16
MAX_STATES = 8192


def validate_puzzles(data: Any, world: Any) -> dict[str, Any]:
    prove(world)
    obj = _keys(data, {
        "schema", "world_id", "world_digest", "prompt", "puzzles",
        "approved", "review_note",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("puzzles_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != digest(world):
        raise CanonError("puzzles_source_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    _text(obj["review_note"], "review_note", 512)
    if type(obj["approved"]) is not bool:
        raise CanonError("puzzles_invalid_approval")
    puzzles = _list(obj["puzzles"], "puzzles", MAX_PUZZLES)
    if not puzzles:
        raise CanonError("puzzles_empty")
    choice_by_id = {choice["id"]: choice for choice in world["choices"]}
    endings = {entry["scene"] for entry in world["endings"]}
    ids: set[str] = set()
    gates: set[str] = set()
    for puzzle in puzzles:
        _keys(puzzle, {
            "id", "scene", "question", "answer", "hint", "unlock_choice",
        })
        pid = _id(puzzle["id"], "puzzle.id")
        scene = _id(puzzle["scene"], "puzzle.scene")
        gate = _id(puzzle["unlock_choice"], "puzzle.unlock_choice")
        if pid in ids:
            raise CanonError("puzzles_duplicate_id", pid)
        if gate in gates:
            raise CanonError("puzzles_duplicate_gate", gate)
        ids.add(pid)
        gates.add(gate)
        if scene in endings or gate not in choice_by_id or (
            choice_by_id[gate]["from"] != scene
        ):
            raise CanonError("puzzles_invalid_gate", pid)
        _text(puzzle["question"], "puzzle.question", 2048)
        _text(puzzle["hint"], "puzzle.hint", 2048)
        answer = _text(puzzle["answer"], "puzzle.answer", 128)
        if answer != answer.strip() or "\n" in answer or "\t" in answer:
            raise CanonError("puzzles_invalid_answer", pid)
    if [puzzle["id"] for puzzle in puzzles] != sorted(ids):
        raise CanonError("puzzles_not_sorted")
    if len(canonical(obj)) > 524288:
        raise CanonError("puzzles_source_too_large")
    return obj


def prove_puzzles(data: Any, world: Any) -> dict[str, Any]:
    obj = validate_puzzles(data, world)
    by_scene: dict[str, list[dict[str, Any]]] = {}
    by_choice: dict[str, str] = {}
    for puzzle in obj["puzzles"]:
        by_scene.setdefault(puzzle["scene"], []).append(puzzle)
        by_choice[puzzle["unlock_choice"]] = puzzle["id"]
    choices: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        choices.setdefault(choice["from"], []).append(choice)
    for group in choices.values():
        group.sort(key=lambda choice: choice["id"])
    endings = {entry["scene"] for entry in world["endings"]}
    initial = (world["start"], frozenset(), frozenset())
    queue = deque([(initial, ())])
    seen = {initial}
    puzzle_witnesses: dict[str, list[str]] = {}
    gate_witnesses: dict[str, list[str]] = {}
    ending_witnesses: dict[str, list[str]] = {}
    while queue:
        (scene, flags, solved), path = queue.popleft()
        if scene in endings:
            ending_witnesses.setdefault(scene, list(path))
            continue
        enabled = 0
        for puzzle in by_scene.get(scene, ()):
            if puzzle["id"] in solved:
                continue
            enabled += 1
            next_path = path + ("solve:" + puzzle["id"],)
            puzzle_witnesses.setdefault(puzzle["id"], list(next_path))
            state = (scene, flags, solved | {puzzle["id"]})
            if state not in seen:
                seen.add(state)
                if len(seen) > MAX_STATES:
                    raise CanonError("puzzles_state_budget")
                queue.append((state, next_path))
        for choice in choices.get(scene, ()):
            if not set(choice["requires"]) <= flags:
                continue
            if choice["id"] in by_choice and by_choice[choice["id"]] not in solved:
                continue
            enabled += 1
            if choice["id"] in by_choice:
                gate_witnesses.setdefault(choice["id"], list(path + (choice["id"],)))
            state = (
                choice["to"],
                flags | frozenset(choice["grants"]),
                solved,
            )
            if state not in seen:
                seen.add(state)
                if len(seen) > MAX_STATES:
                    raise CanonError("puzzles_state_budget")
                queue.append((state, path + (choice["id"],)))
        if enabled == 0:
            raise CanonError("puzzles_reachable_dead_end", scene)
    missing = endings - set(ending_witnesses)
    if missing:
        raise CanonError("puzzles_unreachable_endings", ",".join(sorted(missing)))
    missing_gates = set(by_choice) - set(gate_witnesses)
    if missing_gates:
        raise CanonError("puzzles_unreachable_gates", ",".join(sorted(missing_gates)))
    missing_puzzles = {puzzle["id"] for puzzle in obj["puzzles"]} - set(puzzle_witnesses)
    if missing_puzzles:
        raise CanonError("puzzles_unreachable", ",".join(sorted(missing_puzzles)))
    return {
        "schema": PROOF_SCHEMA,
        "world_id": world["id"],
        "world_digest": digest(world),
        "puzzles_digest": digest(obj),
        "states_explored": len(seen),
        "puzzle_witnesses": {key: puzzle_witnesses[key] for key in sorted(puzzle_witnesses)},
        "gate_witnesses": {key: gate_witnesses[key] for key in sorted(gate_witnesses)},
        "ending_witnesses": {key: ending_witnesses[key] for key in sorted(ending_witnesses)},
        "qualification": "bounded_solve_and_travel_reachability",
    }


def propose_puzzles(world: Any, *, prompt: str, puzzle_id: str, scene: str,
                    question: str, answer: str, hint: str,
                    unlock_choice: str) -> dict[str, Any]:
    _text(prompt, "prompt", 4096)
    source = {
        "schema": SCHEMA, "world_id": world["id"], "world_digest": digest(world),
        "prompt": prompt, "approved": False,
        "review_note": "Awaiting original-author puzzle review",
        "puzzles": [{
            "id": puzzle_id, "scene": scene, "question": question,
            "answer": answer, "hint": hint, "unlock_choice": unlock_choice,
        }],
    }
    prove_puzzles(source, world)
    return source


def edit_puzzles(data: Any, world: Any, operation: Any) -> dict[str, Any]:
    obj = validate_puzzles(data, world)
    op = _keys(operation, {"action", "value"})
    candidate = strict_json(canonical(obj))
    action, value = op["action"], op["value"]
    if action == "add_puzzle":
        _keys(value, {"id", "scene", "question", "answer", "hint", "unlock_choice"})
        candidate["puzzles"].append(value)
        candidate["puzzles"].sort(key=lambda puzzle: puzzle["id"])
    elif action == "replace_puzzle":
        _keys(value, {"id", "scene", "question", "answer", "hint", "unlock_choice"})
        matches = [i for i, puzzle in enumerate(candidate["puzzles"]) if puzzle["id"] == value["id"]]
        if len(matches) != 1:
            raise CanonError("puzzles_unknown_edit")
        candidate["puzzles"][matches[0]] = value
    elif action == "remove_puzzle":
        _keys(value, {"id"})
        before = len(candidate["puzzles"])
        candidate["puzzles"] = [p for p in candidate["puzzles"] if p["id"] != value["id"]]
        if len(candidate["puzzles"]) == before:
            raise CanonError("puzzles_unknown_edit")
    else:
        raise CanonError("puzzles_unsupported_edit")
    candidate["approved"] = False
    candidate["review_note"] = "Review required after puzzle edit"
    prove_puzzles(candidate, world)
    return candidate


_PLAYER_JS = r"""
"use strict";
const model = JSON.parse(document.getElementById("puzzle-data").textContent);
const world = model.world;
const puzzles = model.puzzles.puzzles;
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
const gates = new Map(puzzles.map(p => [p.unlock_choice, p.id]));
const root = document.getElementById("play");
let scene = world.start;
let flags = new Set();
let solved = new Set();
let trace = [];
function element(tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
}
function render() {
  root.replaceChildren();
  const current = scenes.get(scene);
  root.append(element("h1", current.title), element("p", current.narrative));
  root.append(element("p", "Actions: " + trace.join(", ")));
  if (endings.has(scene)) {
    root.append(element("h2", "Ending: " + endings.get(scene)));
    const restart = element("button", "Restart");
    restart.addEventListener("click", () => {
      scene = world.start; flags = new Set(); solved = new Set(); trace = []; render();
    });
    root.append(restart);
    return;
  }
  for (const puzzle of puzzles.filter(p => p.scene === scene && !solved.has(p.id))) {
    const section = element("section", "");
    section.append(element("h2", puzzle.question));
    const answer = document.createElement("input");
    answer.setAttribute("aria-label", "Answer for " + puzzle.id);
    const submit = element("button", "Solve " + puzzle.id);
    const feedback = element("p", "");
    feedback.setAttribute("role", "status");
    submit.addEventListener("click", () => {
      if (answer.value.trim() === puzzle.answer) {
        solved.add(puzzle.id); trace.push("solve:" + puzzle.id); render();
      } else {
        feedback.textContent = "Try again. Hint: " + puzzle.hint;
      }
    });
    section.append(answer, submit, feedback);
    root.append(section);
  }
  for (const choice of world.choices.filter(c => c.from === scene)) {
    if (!choice.requires.every(f => flags.has(f))) continue;
    if (gates.has(choice.id) && !solved.has(gates.get(choice.id))) continue;
    const button = element("button", choice.label);
    button.addEventListener("click", () => {
      for (const flag of choice.grants) flags.add(flag);
      trace.push(choice.id); scene = choice.to; render();
    });
    root.append(button);
  }
}
render();
""".strip()


def compile_puzzles_html(data: Any, world: Any) -> bytes:
    prove_puzzles(data, world)
    if not data["approved"]:
        raise CanonError("puzzles_review_required")
    payload = canonical({"world": world, "puzzles": data}).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_PLAYER_JS.encode()).digest()).decode("ascii")
    title = html.escape(world["id"], quote=True)
    content = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "script-src 'sha256-" + policy + "'; connect-src 'none'; "
        'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
        '<title>' + title + ' puzzles</title></head><body>'
        '<main id="play" aria-live="polite"></main>'
        '<script id="puzzle-data" type="application/json">' + payload + '</script>'
        '<script>' + _PLAYER_JS + '</script></body></html>\n'
    ).encode("utf-8")
    if len(content) > 1048576:
        raise CanonError("puzzles_playable_too_large")
    return content


class PuzzleStore:
    def __init__(self, root: str) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (
            world_id + ".puzzles.json",
            world_id + ".puzzles.playable.html",
            world_id + ".puzzles.receipt.json",
        )

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        return world

    def _read(self, fd: int, world_id: str, world: Any) -> dict[str, Any]:
        data = strict_json(self.worlds._read(fd, self._names(world_id)[0]))
        validate_puzzles(data, world)
        return data

    @staticmethod
    def _lock(fd: int, world_id: str) -> None:
        try:
            handle = os.open(
                world_id + ".lock",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=fd,
            )
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def propose(self, world_id: str, **kwargs: Any) -> dict[str, Any]:
        return propose_puzzles(self.worlds.read(world_id), **kwargs)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            data = self._read(fd, world_id, world)
            return {"puzzles": data, "proof": prove_puzzles(data, world)}
        finally:
            os.close(fd)

    def publish(self, world_id: str, data: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                candidate = strict_json(canonical(data))
                if type(candidate) is not dict:
                    raise CanonError("expected_object")
                candidate["approved"] = False
                candidate["review_note"] = "Review required after source publication"
                prove_puzzles(candidate, world)
                name = self._names(world_id)[0]
                try:
                    existing = self._read(fd, world_id, world)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    existing = None
                if create:
                    if existing is not None or expected_digest is not None:
                        raise CanonError("puzzles_already_exists")
                elif existing is None or digest(existing) != expected_digest:
                    raise CanonError("puzzles_stale_edit")
                self.worlds._write(fd, name, canonical(candidate))
                return digest(candidate)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def approve(self, world_id: str, *, expected_digest: str, review_note: str) -> str:
        _text(review_note, "review_note", 512)
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                data = self._read(fd, world_id, world)
                if digest(data) != expected_digest:
                    raise CanonError("puzzles_stale_edit")
                data["approved"] = True
                data["review_note"] = review_note
                prove_puzzles(data, world)
                self.worlds._write(fd, self._names(world_id)[0], canonical(data))
                return digest(data)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, data: Any, world: Any) -> tuple[dict[str, Any], bytes]:
        proof = prove_puzzles(data, world)
        playable = compile_puzzles_html(data, world)
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "puzzles_digest": digest(data),
            "proof_digest": digest(proof), "html_sha256": sha256(playable).hexdigest(),
            "html_file": self._names(world["id"])[1],
            "qualification": "offline_reviewed_puzzle_gated_playable",
        }
        return receipt, playable

    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        """Publish a source-leased, network-disabled editor, not an approval."""
        from .puzzles_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                data = self._read(fd, world_id, world)
                if digest(data) != expected_digest:
                    raise CanonError("puzzles_stale_edit")
                content = render_editor(data, world)
                name = world_id + ".puzzles.editor.html"
                self.worlds._write(fd, name, content)
                return {
                    "html_file": name, "html_sha256": sha256(content).hexdigest(),
                    "puzzles_digest": digest(data),
                }
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                data = self._read(fd, world_id, world)
                if digest(data) != expected_digest:
                    raise CanonError("puzzles_stale_edit")
                receipt, playable = self._outputs(data, world)
                _, html_name, receipt_name = self._names(world_id)
                self.worlds._write(fd, html_name, playable)
                self.worlds._write(fd, receipt_name, canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                data = self._read(fd, world_id, world)
                receipt, playable = self._outputs(data, world)
                _, html_name, receipt_name = self._names(world_id)
                if strict_json(self.worlds._read(fd, receipt_name)) != receipt:
                    raise CanonError("puzzles_receipt_mismatch")
                if _artifact_read(fd, html_name) != playable:
                    raise CanonError("puzzles_playable_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
