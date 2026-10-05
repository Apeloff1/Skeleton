"""Blueprint DOT export — inspectable topology for review/docs.

materialise() emits JSON; humans codareview better with Graphviz.
`to_dot()` produces a deterministic digraph with ports on edges.
"""

from __future__ import annotations

from typing import List

from skeleton.forge.universal import Blueprint


def to_dot(blueprint: Blueprint) -> str:
    """Emit a Graphviz digraph with component nodes and labelled wires."""
    lines: List[str] = [
        "digraph blueprint {",
        "  rankdir=LR;",
        f'  label="{blueprint.name}";',
    ]
    for cid, comp in blueprint.components.items():
        shape = "box" if comp.kind != "sink" else "doubleoctagon"
        lines.append(f'  "{cid}" [shape={shape}, label="{cid}\\n({comp.kind})"];')
    for wire in blueprint.wires:
        src_comp, src_port = wire.src
        dst_comp, dst_port = wire.dst
        lines.append(
            f'  "{src_comp}" -> "{dst_comp}" '
            f'[label="{src_port}→{dst_port}"];'
        )
    lines.append("}")
    return "\n".join(lines)
