"""Human-readable terminal play for Lantern Quay with recoverable checkpoints.

This interface calls the canonical gameplay step function; it never awards a
victory from textual commands without a replay-proven dock delivery and choice.
"""
from __future__ import annotations

from typing import Any, TextIO

from .harbor_crafting_guidance import legal_actions
from .harbor_crafting import (
    HarborError, canonical, demo_actions, export_bundle, initial_state,
    normalize_action, step, validate_source, verify_bundle,
)

MAX_COMMAND_BYTES = 128


def render(source: dict[str, Any], state: dict[str, Any]) -> str:
    world = validate_source(source)
    rows = [list(row) for row in world["map"]]
    for resource in world["resources"]:
        if state["stock"][resource["id"]] > 0:
            x, y = resource["at"]
            rows[y][x] = resource["id"][0].upper()
    x, y = world["dock"]
    rows[y][x] = "D"
    x, y = state["npc_pos"]
    rows[y][x] = "M"
    x, y = state["pos"]
    rows[y][x] = "@"
    inventory = ",".join(
        f"{item}:{qty}" for item, qty in sorted(state["inventory"].items())
    ) or "empty"
    return "\n".join("".join(row) for row in rows) + (
        f"\ntick={state['tick']}/{world['max_ticks']}"
        f" coins={state['coins']} reputation={state['reputation']}"
        f" inventory={inventory} delivered={str(state['delivered']).lower()}"
        f" ending={state['ending'] or 'none'}\n"
    )


def parse_command(line: str) -> dict[str, str] | str:
    if not isinstance(line, str) or len(line.encode("utf-8")) > MAX_COMMAND_BYTES:
        raise HarborError("terminal command exceeds byte limit")
    parts = line.strip().lower().split()
    if not parts:
        raise HarborError("empty terminal command")
    if parts == ["save"]:
        return "save"
    if parts == ["undo"]:
        return "undo"
    if parts == ["redo"]:
        return "redo"
    if parts == ["hint"]:
        return "hint"
    if parts == ["help"]:
        return "help"
    if parts == ["quit"]:
        return "quit"
    if len(parts) == 1:
        simple = {
            "north": {"op": "move", "direction": "north"},
            "south": {"op": "move", "direction": "south"},
            "east": {"op": "move", "direction": "east"},
            "west": {"op": "move", "direction": "west"},
            "gather": {"op": "gather"},
            "deliver": {"op": "deliver"},
            "wait": {"op": "wait"},
            "signal": {"op": "choose", "choice": "signal"},
            "shelter": {"op": "choose", "choice": "shelter"},
        }
        if parts[0] in simple:
            return simple[parts[0]]
    if len(parts) == 2 and parts[0] in ("craft", "trade"):
        return normalize_action({
            "op": parts[0], "recipe" if parts[0] == "craft" else "item": parts[1]
        })
    raise HarborError("unsupported terminal command")


def play_live(
    source: dict[str, Any], input_stream: TextIO, output_stream: TextIO,
    *, course: Any = None, contract_save: Any = None,
) -> int:
    world = validate_source(source)
    authored_course = None
    if course is not None:
        from .harbor_crafting_time_trials import validate_course
        authored_course = validate_course(course, world)
    if contract_save is not None:
        if course is not None:
            raise HarborError("cannot combine trial and contract live modes")
        from .harbor_crafting_contracts import next_order, verify_save
        verify_save(contract_save)
        pending = next_order(contract_save)
        if pending["status"] != "ready" or pending["source"] != world:
            raise HarborError("contract live source mismatch or board complete")
    state = initial_state(world)
    actions: list[dict[str, str]] = []
    redo_stack: list[dict[str, str]] = []
    max_commands = world["max_ticks"] * 4 + 16
    output_stream.write("LANTERN QUAY | north south east west gather craft ID trade ID deliver signal shelter wait hint undo redo save quit\n")
    output_stream.write(render(world, state))
    for _ in range(max_commands):
        line = input_stream.readline(MAX_COMMAND_BYTES + 2)
        if line == "":
            output_stream.write("EOF: no victory; replay-verifiable checkpoint follows\n")
            output_stream.write("CHECKPOINT " + canonical(export_bundle(world, actions)).decode("utf-8") + "\n")
            return 2
        try:
            command = parse_command(line)
            if command == "undo":
                if not actions:
                    raise HarborError("no action to undo")
                redo_stack.append(actions.pop())
                restored = export_bundle(world, actions)
                state = verify_bundle(restored)
                output_stream.write("UNDO " + restored["terminal_digest"] + "\n")
                output_stream.write(render(world, state))
                continue
            if command == "redo":
                if not redo_stack:
                    raise HarborError("no action to redo")
                candidate = redo_stack[-1]
                restored = export_bundle(world, actions + [candidate])
                updated = verify_bundle(restored)
                actions.append(candidate)
                redo_stack.pop()
                state = updated
                output_stream.write("REDO " + restored["terminal_digest"] + "\n")
                output_stream.write(render(world, state))
                continue
            if command == "hint":
                available = legal_actions(world, state)
                descriptions = []
                for option in available:
                    action = option["action"]
                    descriptions.append(
                        action.get("direction") or action.get("recipe")
                        or action.get("item") or action.get("choice")
                        or action["op"]
                    )
                output_stream.write("LEGAL NOW " + ", ".join(descriptions) + "\n")
                if authored_course is not None:
                    from .harbor_crafting_time_trials import time_trial_report
                    report = time_trial_report(export_bundle(world, actions), authored_course)
                    output_stream.write(
                        "TRIAL_PROGRESS "
                        + str(len(report["visits"])) + "/"
                        + str(len(authored_course["checkpoints"]))
                        + " checkpoints, deadline="
                        + str(authored_course["deadline"]) + "\n"
                    )
                continue
            if command == "help":
                output_stream.write("Move, gather, craft, trade, deliver and choose an ending. hint lists legal actions; undo/redo replay verified history; save exports a checkpoint.\n")
                continue
            if command == "save":
                output_stream.write("CHECKPOINT " + canonical(export_bundle(world, actions)).decode("utf-8") + "\n")
                continue
            if command == "quit":
                output_stream.write("QUIT: no victory; replay-verifiable checkpoint follows\n")
                output_stream.write("CHECKPOINT " + canonical(export_bundle(world, actions)).decode("utf-8") + "\n")
                return 2
            updated = step(world, state, command)
        except HarborError as exc:
            output_stream.write("REJECTED " + str(exc) + "\n")
            continue
        actions.append(command)
        redo_stack.clear()
        state = updated
        output_stream.write(render(world, state))
        if state["ending"] is not None:
            bundle = export_bundle(world, actions, require_win=True)
            if verify_bundle(bundle, require_win=True) != state:
                raise HarborError("interactive replay divergence")
            label = "GAME_VICTORY" if contract_save is not None else "VICTORY"
            output_stream.write(label + " " + state["ending"] + " " + bundle["terminal_digest"] + "\n")
            if authored_course is not None:
                from .harbor_crafting_time_trials import (
                    time_trial_report, verify_time_trial_report,
                )
                report = time_trial_report(bundle, authored_course)
                verified = verify_time_trial_report(report)
                output_stream.write(
                    "TRIAL " + verified["status"] + " "
                    + (verified["medal"] or "no-medal") + "\n"
                )
                output_stream.write(
                    "TRIAL_REPORT " + canonical(report).decode("utf-8") + "\n"
                )
                output_stream.write("CHECKPOINT " + canonical(bundle).decode("utf-8") + "\n")
                return 0 if verified["status"] == "finished" else 2
            if contract_save is not None:
                from .harbor_crafting_contracts import append_save
                try:
                    progressed = append_save(
                        contract_save, bundle, expected_digest=contract_save["save_digest"])
                except HarborError as exc:
                    output_stream.write("CONTRACT_REJECTED " + str(exc) + "\n")
                    output_stream.write("CHECKPOINT " + canonical(bundle).decode("utf-8") + "\n")
                    return 2
                output_stream.write("CONTRACT_EARNED " + pending["order"]["id"] + "\n")
                output_stream.write("CONTRACT_SAVE " + canonical(progressed).decode("utf-8") + "\n")
            output_stream.write("CHECKPOINT " + canonical(bundle).decode("utf-8") + "\n")
            return 0
    output_stream.write("COMMAND_BUDGET_EXHAUSTED: no victory; checkpoint follows\n")
    output_stream.write("CHECKPOINT " + canonical(export_bundle(world, actions)).decode("utf-8") + "\n")
    return 2


def scripted_demo_commands() -> str:
    """Human input equivalent of the original deterministic victory fixture."""
    lines: list[str] = []
    for action in demo_actions():
        op = action["op"]
        if op == "move":
            lines.append(action["direction"])
        elif op == "craft":
            lines.append("craft " + action["recipe"])
        elif op == "trade":
            lines.append("trade " + action["item"])
        elif op == "choose":
            lines.append(action["choice"])
        else:
            lines.append(op)
    return "\n".join(lines) + "\n"
