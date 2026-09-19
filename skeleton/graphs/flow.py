"""Edge flow on the house graph. Conservation: sum_in == sum_out except source/sink."""

from __future__ import annotations

from skeleton.graphs.cards import graph_card
from skeleton.graphs.law import HOUSE_N


def unit_path_flow(src: int = 0, dst: int = HOUSE_N // 2) -> dict[tuple[int, int], float]:
    flow: dict[tuple[int, int], float] = {}
    step = 1 if (dst - src) % HOUSE_N <= HOUSE_N // 2 else -1
    i = src
    while i != dst:
        j = (i + step) % HOUSE_N
        flow[(i, j)] = flow.get((i, j), 0.0) + 1.0
        i = j
    return flow


def residual(flow: dict[tuple[int, int], float], src: int, dst: int) -> list[float]:
    net = [0.0] * HOUSE_N
    for (i, j), val in flow.items():
        net[i] -= val
        net[j] += val
    net[src] += 1.0
    net[dst] -= 1.0
    return net


def conserved(flow: dict[tuple[int, int], float], src: int = 0, dst: int = HOUSE_N // 2, eps: float = 1e-9) -> bool:
    net = residual(flow, src, dst)
    return all(abs(v) <= eps for v in net)


def flow_card() -> dict:
    src, dst = 0, HOUSE_N // 2
    fl = unit_path_flow(src, dst)
    ok = conserved(fl, src, dst)
    return graph_card(
        kind="flow",
        hit=1 if ok else 0,
        law="flow conserved",
        extra={"src": src, "dst": dst, "edges": len(fl), "ok": int(ok)},
    )
