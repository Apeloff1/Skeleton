"""Playable native desktop interface for the original world product session.

Uses Python's built-in Tk graphical toolkit; not a browser/HTML toy.
The canvas draws actual local physical tiles, NPC positions, buildings,
player marker and HUD, with clickable controls and arrow movement.
A screen/display and tkinter are required only when launching the GUI;
all deterministic gameplay, headless renders, saves and tests work offline.
"""
from __future__ import annotations

from .original_foundation_compiler import FoundationError
from .original_world_product_render import COLORS, BUILDING_COLORS
from .original_world_product_terrain import cell_at
from .original_world_product_missions import mission_report
from .original_world_product_session import (
    ProductAction, ProductSession, product_save, step_product, validate_product,
)

SIDE = 19
TILE_SIZE = 27
VIEW_RADIUS = SIDE // 2


def launch_desktop(state: ProductSession, *, save_path: str | None = None) -> None:
    validate_product(state)
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError as exc:
        raise FoundationError("desktop mode requires Python tkinter") from exc
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        raise FoundationError("no supported desktop display exists") from exc

    rule = validate_product(state)
    window.title("Original World Studio · " + rule.foundation.system.title)
    window.configure(bg="#16222a")
    session = [state]
    visible = SIDE * TILE_SIZE
    frame = tk.Frame(window, bg="#16222a", padx=13, pady=12)
    frame.pack(fill="both", expand=True)
    canvas = tk.Canvas(frame, width=visible, height=visible, bg="#17252d",
                       highlightthickness=0)
    canvas.grid(row=0, column=0, rowspan=14, sticky="n")
    panel = tk.Frame(frame, bg="#16222a", padx=13)
    panel.grid(row=0, column=1, sticky="nw")
    label = tk.Label(panel, text="", fg="#e4efe8", bg="#16222a",
                     font=("TkDefaultFont", 10), justify="left", wraplength=340)
    label.pack(anchor="w", pady=(0, 14))
    status = tk.StringVar(value="Explore your world with the arrow keys.")
    info = tk.Label(panel, textvariable=status, fg="#bfd8d4", bg="#16222a",
                    wraplength=330, justify="left")
    info.pack(anchor="w", pady=(0, 10))

    def draw() -> None:
        current = session[0]
        law = validate_product(current)
        landscape = current.terrain
        quest = mission_report(current)
        px, py = landscape.position
        canvas.delete("all")
        for dy in range(-VIEW_RADIUS, VIEW_RADIUS + 1):
            for dx in range(-VIEW_RADIUS, VIEW_RADIUS + 1):
                tile = cell_at(landscape, px + dx, py + dy)
                x0 = (dx + VIEW_RADIUS) * TILE_SIZE
                y0 = (dy + VIEW_RADIUS) * TILE_SIZE
                rgb = COLORS[tile.kind]
                color = "#%02x%02x%02x" % rgb
                canvas.create_rectangle(x0, y0, x0 + TILE_SIZE, y0 + TILE_SIZE,
                                        outline="#182c31", width=1, fill=color)
                if tile.elevation >= 4:
                    canvas.create_line(x0, y0 + TILE_SIZE, x0 + TILE_SIZE, y0,
                                       fill="#36434c", width=2)
                if tile.bridge:
                    canvas.create_line(x0 + 3, y0 + 14, x0 + TILE_SIZE - 3, y0 + 14,
                                       fill="#edc07d", width=5)
                if tile.building:
                    canvas.create_rectangle(x0 + 6, y0 + 6,
                                            x0 + TILE_SIZE - 6, y0 + TILE_SIZE - 6,
                                            fill=BUILDING_COLORS[tile.building], outline="#342e29")
        for person in current.society.inhabitants:
            dx, dy = person.x - px, person.y - py
            if abs(dx) > VIEW_RADIUS or abs(dy) > VIEW_RADIUS:
                continue
            x0 = (dx + VIEW_RADIUS) * TILE_SIZE
            y0 = (dy + VIEW_RADIUS) * TILE_SIZE
            canvas.create_oval(x0 + 9, y0 + 7, x0 + 20, y0 + 19,
                               fill="#ffe9d0", outline="#233447")
            canvas.create_text(x0 + 14, y0 + 24, text=str(person.id),
                               font=("TkDefaultFont", 7), fill="#1c3230")
        mid = VIEW_RADIUS * TILE_SIZE
        canvas.create_oval(mid + 5, mid + 5, mid + TILE_SIZE - 5,
                           mid + TILE_SIZE - 5, fill="#70e5f0",
                           outline="#113e54", width=3)
        canvas.create_line(mid + 13, mid + 5, mid + 13, mid + 21,
                           fill="#125469", width=2)
        label.configure(text="\n".join((
            law.foundation.system.title,
            law.source.spatial.architecture.title,
            law.source.advanced.mode.form.title,
            f"World turn {current.living.living_turns}",
            f"Position: {px}, {py}",
            f"Local energy {landscape.energy}",
            f"Food {landscape.provisions} / Water {landscape.freshwater}",
            f"Lumber {landscape.lumber} / Masonry {landscape.masonry}",
            f"Citizens: {len(current.society.inhabitants)}",
            f"World action points: {current.living.spatial.game.causal.action_points}",
            f"Original root: {quest['authored_root_id']}",
            f"Story proofs: {quest['verified_local_milestones']}/3",
            "Native Tk · physics · resident AI · authored world rules.",
        )))

    def perform(action: ProductAction) -> None:
        try:
            after, receipt = step_product(session[0], action)
            session[0] = after
            status.set(" · ".join(receipt.changes))
            draw()
        except FoundationError as exc:
            status.set("Cannot perform action: " + str(exc))

    def move(dx: int, dy: int) -> None:
        x, y = session[0].terrain.position
        target = cell_at(session[0].terrain, x + dx, y + dy)
        verb = "jump" if target.blocking or (
            target.elevation - cell_at(session[0].terrain, x, y).elevation > 1
        ) else "walk"
        perform(ProductAction("terrain", verb, x=x + dx, y=y + dy))

    def work(verb: str) -> None:
        x, y = session[0].terrain.position
        perform(ProductAction("terrain", verb, x=x, y=y))

    def save() -> None:
        if not save_path:
            status.set("Launch with --save PATH to enable one-click local saves.")
            return
        from pathlib import Path
        path = Path(save_path)
        try:
            if not path.parent.is_dir() or path.is_dir():
                raise FoundationError("save directory must already exist")
            temp = path.with_name(path.name + ".tmp")
            temp.write_text(product_save(session[0]), encoding="utf-8")
            temp.replace(path)
            status.set("Complete world, terrain and residents saved to " + str(path))
        except (OSError, FoundationError) as exc:
            status.set("Save rejected: " + str(exc))

    def button(title: str, handler) -> None:
        tk.Button(panel, text=title, command=handler, width=29,
                  bg="#27414a", fg="#eef7ee", activebackground="#3b6471",
                  activeforeground="#ffffff", relief="flat", pady=4).pack(pady=2)

    button("↑ North", lambda: move(0, -1))
    button("← West", lambda: move(-1, 0))
    button("→ East", lambda: move(1, 0))
    button("↓ South", lambda: move(0, 1))
    button("Forage local food", lambda: work("forage"))
    button("Harvest timber", lambda: work("chop"))
    button("Excavate stone", lambda: work("mine"))
    button("Collect fresh water", lambda: work("draw"))
    button("Construct a hearth", lambda: work("build_hearth"))
    button("Rest (uses provisions)", lambda: work("rest"))
    button("Advance whole world + NPC clock", lambda: perform(
        ProductAction("causal", "end_turn")))
    button("Save current world", save)
    for verb in rule.foundation.system.commands:
        button("Living-system: " + verb, lambda cmd=verb: perform(
            ProductAction("living", cmd)))

    # Real in-app command palette exposes all source genre, arc, spatial and
    # player/NPC agency actions, rather than only the simple tile shortcuts.
    tk.Label(panel, text="Complete game action", fg="#e8efec",
             bg="#16222a").pack(anchor="w", pady=(10, 3))
    command_input = tk.Entry(panel, width=32, bg="#f0f7f5", fg="#12343a")
    command_input.pack(anchor="w", pady=(0, 4))
    command_input.insert(0, "mode " + rule.source.advanced.mode.form.mechanics[0])

    def submit_command(_event=None) -> None:
        from .original_world_product_cli import parse_command
        text = command_input.get().strip()
        try:
            action = parse_command(text, session[0].terrain.position)
            perform(action)
        except FoundationError as exc:
            status.set("Command rejected: " + str(exc))

    command_input.bind("<Return>", submit_command)
    button("Execute complete-world command", submit_command)

    for key, dx, dy in (
        ("<Up>", 0, -1), ("<Down>", 0, 1),
        ("<Left>", -1, 0), ("<Right>", 1, 0),
    ):
        window.bind(key, lambda _event, x=dx, y=dy: move(x, y))
    window.bind("<space>", lambda _event: perform(
        ProductAction("causal", "end_turn")))
    draw()
    window.focus_force()
    window.mainloop()
