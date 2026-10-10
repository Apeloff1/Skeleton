"""Native, local-only homebrew game map editor with usable toolbar options.

Real desktop Tk interface over the independent deterministic editor core:
11 bounded operations, editable brush parameters, immutable save-as,
undo/redo, AI-free procedural suggestions and platform-budget inspection.
No script console, game ROM importer, external art loader, network service,
licensed commercial game patcher or model training functionality.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.game.game_project import _read_json, _write_new
from skeleton.ai.runtime.homebrew_editor import (
    HomebrewEditor, HomebrewEditorError, EDITOR_TOOLS,
)
from skeleton.ai.runtime.homebrew_porting import (
    ART_DIRECTIONS, CREATIVE_MODES, HYBRID_MODES, QUALITY,
    make_homebrew_port, verify_port_gameplay, HomebrewPortError,
)

CELL = 24
DEFAULT_STAMP = ("###", "#?#", "###")
TARGETS = ("chip8-vip", "windows-11", "game-boy", "playstation-5")


def open_homebrew_editor(project: str | Path, output: str | Path | None = None) -> int:
    """Launch native Tk editor; read one explicitly named HOME-BREW capsule."""
    editor = HomebrewEditor(_read_json(Path(project)))
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError as exc:
        raise HomebrewEditorError("native Tk editor UI is unavailable") from exc
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise HomebrewEditorError("native editor display is unavailable") from exc

    width, height = len(editor.tiles[0]), len(editor.tiles)
    root.title("Skeleton | Homebrew-Only Game Editor")
    root.resizable(False, False)

    chosen = tk.StringVar(value="paint")
    tile = tk.StringVar(value=".")
    shape = tk.StringVar(value="circle")
    radius = tk.IntVar(value=1)
    seed = tk.IntVar(value=42)
    density = tk.IntVar(value=25)
    threshold = tk.IntVar(value=5)
    iterations = tk.IntVar(value=1)
    filled = tk.BooleanVar(value=True)
    marker = tk.StringVar(value="G")
    transform = tk.StringVar(value="flip_horizontal")
    order = tk.StringVar(value="horizontal_first")
    target = tk.StringVar(value="windows-11")
    saved_to = tk.StringVar(value=str(output) if output is not None else "")
    status = tk.StringVar(value="Original content only. No imported ROMs or assets.")
    press_cell: tuple[int, int] | None = None

    container = tk.Frame(root)
    container.pack(fill="both", expand=True)
    canvas = tk.Canvas(
        container, width=width * CELL, height=height * CELL,
        background="#131923", highlightthickness=0,
    )
    canvas.pack(side="left")
    sidebar = tk.Frame(container, padx=9, pady=7)
    sidebar.pack(side="right", fill="y")
    tk.Label(sidebar, text="HOME-BREW EDITOR", font=("Arial", 11, "bold")).pack(anchor="w")
    tk.Label(sidebar, text="Original games only • offline", foreground="#225b3b").pack(anchor="w")

    def selector(title: str, value: Any, choices: tuple[str, ...]) -> None:
        tk.Label(sidebar, text=title).pack(anchor="w")
        tk.OptionMenu(sidebar, value, *choices).pack(fill="x")

    selector("Tool", chosen, tuple(EDITOR_TOOLS))
    selector("Terrain", tile, (".", "#"))
    selector("Brush geometry", shape, ("circle", "diamond", "square"))
    selector("Marker", marker, ("S", "G"))
    selector("Transform", transform, ("flip_horizontal", "flip_vertical", "rotate_180"))
    selector("Route mode", order, ("horizontal_first", "vertical_first"))
    selector("Design target (not a release license)", target, TARGETS)

    def slider(title: str, variable: Any, low: int, high: int) -> None:
        tk.Scale(sidebar, label=title, orient="horizontal",
                 from_=low, to=high, variable=variable).pack(fill="x")

    slider("Brush radius", radius, 0, 8)
    slider("Wall percentage", density, 0, 70)
    slider("Procedural seed", seed, 0, 255)
    slider("Smooth iterations", iterations, 1, 4)
    slider("Smooth threshold", threshold, 3, 8)
    tk.Checkbutton(sidebar, text="Filled rectangle", variable=filled).pack(anchor="w")
    tk.Label(sidebar, text="New output path (never overwrites)").pack(anchor="w")
    tk.Entry(sidebar, textvariable=saved_to, width=33).pack(fill="x")

    def render() -> None:
        canvas.delete("all")
        for y, row in enumerate(editor.tiles):
            for x, cell in enumerate(row):
                xa, ya = x * CELL, y * CELL
                if cell == "#":
                    canvas.create_rectangle(xa, ya, xa + CELL, ya + CELL,
                                            fill="#475978", outline="#34445d")
                elif cell == "S":
                    canvas.create_rectangle(xa, ya, xa + CELL, ya + CELL,
                                            fill="#317f60", outline="#205c49")
                    canvas.create_text(xa + CELL // 2, ya + CELL // 2,
                                       text="S", fill="white")
                elif cell == "G":
                    canvas.create_rectangle(xa, ya, xa + CELL, ya + CELL,
                                            fill="#b88b32", outline="#785923")
                    canvas.create_text(xa + CELL // 2, ya + CELL // 2,
                                       text="G", fill="white")
                else:
                    canvas.create_rectangle(xa, ya, xa + CELL, ya + CELL,
                                            fill="#e2e7eb", outline="#bdc9d0")

    def report(message: str) -> None:
        status.set(message[:225])

    def fail(exc: Exception) -> None:
        report("Rejected: " + str(exc))
        messagebox.showerror("Homebrew editor rejected operation", str(exc))

    def point(event: Any) -> tuple[int, int]:
        x, y = int(event.x) // CELL, int(event.y) // CELL
        if not 0 <= x < width or not 0 <= y < height:
            raise HomebrewEditorError("pointer left the editor canvas")
        return x, y

    def selected_commands(
        first: tuple[int, int], last: tuple[int, int],
    ) -> list[dict[str, Any]]:
        x0, y0 = first
        x1, y1 = last
        tool = chosen.get()
        palette = tile.get()
        if tool == "paint":
            return [{"op": "paint", "x": x1, "y": y1, "tile": palette}]
        if tool == "brush":
            return [{"op": "brush", "x": x1, "y": y1,
                     "radius": int(radius.get()), "shape": shape.get(),
                     "tile": palette}]
        if tool == "line":
            return [{"op": "line", "x0": x0, "y0": y0,
                     "x1": x1, "y1": y1, "tile": palette}]
        if tool == "rectangle":
            return [{"op": "rectangle", "x0": x0, "y0": y0,
                     "x1": x1, "y1": y1, "filled": bool(filled.get()),
                     "tile": palette}]
        if tool == "flood":
            return [{"op": "flood", "x": x1, "y": y1, "tile": palette}]
        if tool == "stamp":
            return [{"op": "stamp", "x": x1, "y": y1,
                     "pattern": list(DEFAULT_STAMP)}]
        if tool == "move_marker":
            return [{"op": "move_marker", "marker": marker.get(), "x": x1, "y": y1}]
        if tool == "noise":
            return [{"op": "noise", "seed": int(seed.get()),
                     "wall_percent": int(density.get()),
                     "x0": x0, "y0": y0, "x1": x1, "y1": y1}]
        if tool == "smooth":
            return [{"op": "smooth", "iterations": int(iterations.get()),
                     "threshold": int(threshold.get())}]
        if tool == "transform":
            return [{"op": "transform", "mode": transform.get()}]
        if tool == "carve_route":
            return [{"op": "carve_route", "order": order.get()}]
        raise HomebrewEditorError("selected tool unavailable")

    def do_apply(first: tuple[int, int], last: tuple[int, int]) -> None:
        try:
            commands = selected_commands(first, last)
            result = editor.apply(
                commands, expected_tile_sha256=editor.tile_sha256,
                require_grid_route=False, require_controller_win=False,
            )
            report(
                f"Edited {len(commands)} action(s); "
                f"spent {result['commands_spent']}/256. "
                f"Use Analyze to validate."
            )
            render()
        except (HomebrewEditorError, ValueError, TypeError) as exc:
            fail(exc)

    def on_down(event: Any) -> None:
        nonlocal press_cell
        try:
            press_cell = point(event)
        except HomebrewEditorError:
            press_cell = None

    def on_up(event: Any) -> None:
        nonlocal press_cell
        if press_cell is None:
            return
        try:
            end = point(event)
        except HomebrewEditorError as exc:
            fail(exc)
            press_cell = None
            return
        do_apply(press_cell, end)
        press_cell = None

    def undo() -> None:
        try:
            editor.undo()
            render()
            report("Undo applied; all source assets remain original.")
        except HomebrewEditorError as exc:
            fail(exc)

    def redo() -> None:
        try:
            editor.redo()
            render()
            report("Redo applied.")
        except HomebrewEditorError as exc:
            fail(exc)

    def analyze() -> None:
        try:
            report_data = editor.analyze(target_ids=[target.get()])
            report(
                f"Grid route: {report_data['goal_grid_reachable']} | "
                f"Real controller: {report_data['controller_status']} | "
                f"Wall density: {report_data['wall_density_percent']}% | "
                f"Dead ends: {report_data['dead_ends']} | "
                f"Native exporter: {report_data['target_options'][0]['exporter_implemented']}"
            )
            messagebox.showinfo(
                "Homebrew gameplay, complexity and legal limits",
                "\n".join((
                    "Controller: " + report_data["controller_status"],
                    "Target: " + target.get(),
                    "Playable input frames: " + str(report_data["winning_input_frames"]),
                    "Colliders: " + str(report_data["collider_rectangles"]),
                    "Walkable cells: " + str(report_data["walkable_tiles"]),
                    "Dead ends: " + str(report_data["dead_ends"]),
                    "Hints: " + ", ".join(report_data["suggested_editor_tools"]),
                    "Publication authorization: NOT VERIFIED",
                )),
            )
        except (HomebrewEditorError, ValueError, TypeError) as exc:
            fail(exc)

    def candidate_search() -> None:
        try:
            options = editor.variants(
                seeds=[int(seed.get()) + i for i in range(4)],
                wall_percent=int(density.get()),
            )
            text = "\n".join(
                "Seed {seed}: {status}, {dead} dead ends, {density}% walls".format(
                    seed=item["seed"],
                    status=item["analysis"]["controller_status"],
                    dead=item["analysis"]["dead_ends"],
                    density=item["analysis"]["wall_density_percent"],
                )
                for item in options
            )
            messagebox.showinfo(
                "Original procedural suggestions (preview only)",
                text + "\nApply the Noise tool with a chosen seed. "
                "Candidates are never auto-applied or auto-published.",
            )
            report("Generated 4 reproducible original candidates; no edits made.")
        except (HomebrewEditorError, ValueError, TypeError) as exc:
            fail(exc)

    def save_as() -> None:
        try:
            address = saved_to.get().strip()
            if not address:
                raise HomebrewEditorError("choose a new, unused save-as path")
            exported = editor.export_capsule()
            where = _write_new(Path(address), exported)
            report(f"Original homebrew saved to {where}; publishing not approved.")
        except (HomebrewEditorError, ValueError, TypeError, OSError) as exc:
            fail(exc)

    def open_windows_port_studio() -> None:
        """Separate compact dialog to avoid overflowing the map tool sidebar."""
        studio = tk.Toplevel(root)
        studio.title("Original Homebrew → Enhanced Windows Port")
        studio.resizable(False, False)
        theme = tk.StringVar(value="neon_noir")
        quality = tk.StringVar(value="enhanced")
        creative = tk.StringVar(value="enhanced_homebrew")
        scale = tk.IntVar(value=32)
        decor = tk.IntVar(value=24)
        reduced = tk.BooleanVar(value=False)
        contrast = tk.BooleanVar(value=False)
        colorblind = tk.BooleanVar(value=False)
        hud = tk.BooleanVar(value=True)
        parallax = tk.BooleanVar(value=True)
        enabled = {
            mode: tk.BooleanVar(value=False) for mode in HYBRID_MODES
        }
        out = tk.StringVar(value="")
        info = tk.StringVar(value="No commercial imports or cloned game assets.")
        tk.Label(
            studio, text="ORIGINAL HOME-BREW WINDOWS PORT",
            font=("Arial", 11, "bold"),
        ).pack(anchor="w")
        tk.Label(
            studio,
            text="Preserve core physics; upgrade graphics and optional mechanics.",
        ).pack(anchor="w")
        for label, value, options in (
            ("Art direction", theme, tuple(ART_DIRECTIONS)),
            ("Creative method", creative, CREATIVE_MODES),
            ("Rendering quality", quality, QUALITY),
        ):
            tk.Label(studio, text=label).pack(anchor="w")
            tk.OptionMenu(studio, value, *options).pack(fill="x")
        for label, value, low, high in (
            ("Windows tile pixels", scale, 16, 56),
            ("Generated ambient details", decor, 0, 96),
        ):
            tk.Scale(
                studio, label=label, variable=value,
                orient="horizontal", from_=low, to=high,
            ).pack(fill="x")
        tk.Label(
            studio, text="Hybrid modes (real gameplay effects)",
            font=("Arial", 10, "bold"),
        ).pack(anchor="w")
        for mode in HYBRID_MODES:
            tk.Checkbutton(
                studio, text=mode.replace("_", " ").title(),
                variable=enabled[mode],
            ).pack(anchor="w")
        for label, value in (
            ("Reduced motion", reduced),
            ("High contrast", contrast),
            ("Colorblind-safe colors", colorblind),
            ("Show enhanced HUD", hud),
            ("Original procedural parallax", parallax),
        ):
            tk.Checkbutton(studio, text=label, variable=value).pack(anchor="w")
        tk.Label(
            studio, text="New port blueprint path (.json, no overwrite)",
        ).pack(anchor="w")
        tk.Entry(studio, textvariable=out, width=48).pack(fill="x")
        tk.Label(
            studio, text="New original project path is in the main Save As field.",
        ).pack(anchor="w")

        def build_native_port() -> None:
            try:
                source = editor.export_capsule()
                selected = [m for m, v in enabled.items() if v.get()]
                blueprint = make_homebrew_port(
                    source, destination="windows-native",
                    creative_mode=creative.get(), art_direction=theme.get(),
                    quality=quality.get(), hybrids=selected,
                    seed=int(seed.get()), scale=int(scale.get()),
                    decor_budget=int(decor.get()),
                    reduced_motion=bool(reduced.get()),
                    high_contrast=bool(contrast.get()),
                    colorblind_safe=bool(colorblind.get()),
                    hud=bool(hud.get()), parallax=bool(parallax.get()),
                )
                proof = verify_port_gameplay(source, blueprint)
                if not proof["hybrid_gameplay_proven"]:
                    raise HomebrewPortError("hybrid destination did not pass gameplay replay")
                project_file = Path(saved_to.get().strip()).expanduser().absolute()
                port_file = Path(out.get().strip()).expanduser().absolute()
                if (
                    not saved_to.get().strip() or not out.get().strip()
                    or project_file == port_file
                    or project_file.exists() or project_file.is_symlink()
                    or port_file.exists() or port_file.is_symlink()
                    or not project_file.parent.is_dir()
                    or not port_file.parent.is_dir()
                ):
                    raise HomebrewPortError(
                        "choose distinct unused paths for source and port outputs"
                    )
                _write_new(project_file, source)
                # The source is already independently verifiable. If the
                # second write fails, the source remains as a new legal-
                # attribution artifact; we do NOT silently overwrite it.
                _write_new(port_file, blueprint)
                info.set("Saved verified original Windows port; replay WIN passed.")
                report(
                    "Enhanced Windows homebrew port created. "
                    "Open with SkeletonGame.exe --project <original> "
                    "--port-blueprint <blueprint>."
                )
                messagebox.showinfo(
                    "Original Windows game port created",
                    "Source: " + str(project_file)
                    + "\nPort: " + str(port_file)
                    + "\nPlayable: " + str(proof["hybrid_gameplay_proven"])
                    + "\nRelease rights: NOT INDEPENDENTLY VERIFIED",
                )
            except (HomebrewPortError, HomebrewEditorError,
                    ValueError, TypeError, OSError) as exc:
                info.set("Port rejected: " + str(exc)[:100])
                fail(exc)

        tk.Button(
            studio, text="Build Original Enhanced Windows Port",
            command=build_native_port,
        ).pack(fill="x")
        tk.Label(studio, textvariable=info, wraplength=300).pack(fill="x")

    canvas.bind("<ButtonPress-1>", on_down)
    canvas.bind("<ButtonRelease-1>", on_up)
    tk.Button(sidebar, text="Undo (Ctrl+Z)", command=undo).pack(fill="x")
    tk.Button(sidebar, text="Redo (Ctrl+Y)", command=redo).pack(fill="x")
    tk.Button(sidebar, text="Analyze controller + era costs", command=analyze).pack(fill="x")
    tk.Button(sidebar, text="Find 4 original variants", command=candidate_search).pack(fill="x")
    tk.Button(sidebar, text="Apply selected non-pointer tool",
              command=lambda: do_apply((0, 0), (0, 0))).pack(fill="x")
    tk.Button(sidebar, text="Save as NEW verified homebrew project",
              command=save_as).pack(fill="x")
    tk.Button(sidebar, text="Windows Port Studio · Hybrid Enhancements",
              command=open_windows_port_studio).pack(fill="x")
    tk.Label(sidebar, textvariable=status, wraplength=275,
             justify="left").pack(fill="x")
    root.bind("<Control-z>", lambda _evt: undo())
    root.bind("<Control-y>", lambda _evt: redo())
    root.bind("<Control-s>", lambda _evt: save_as())
    root.bind("<Control-a>", lambda _evt: analyze())
    root.bind("<Escape>", lambda _evt: root.destroy())
    render()
    root.mainloop()
    return 0


__all__ = ["open_homebrew_editor", "CELL", "TARGETS"]
