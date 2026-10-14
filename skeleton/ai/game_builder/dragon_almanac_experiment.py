"""Original, reproducible pathfinding experiment and a tiny learned cost model.

Demonstrates project -> measurements -> machine almanac, without representing
synthetic maze behavior as player evidence or a general industry breakthrough.
"""
from __future__ import annotations

import heapq
from random import Random
from statistics import mean

from .contracts import canonical_digest


def _solve(width, walls, heuristic):
    goal = width * width - 1
    frontier = [(0, 0, 0)]
    costs = {0: 0}
    expanded = 0
    while frontier:
        _, cost, node = heapq.heappop(frontier)
        if cost != costs.get(node):
            continue
        expanded += 1
        if node == goal:
            return cost, expanded
        x, y = node % width, node // width
        for xx, yy in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)):
            nxt = yy * width + xx
            if not 0 <= xx < width or not 0 <= yy < width or nxt in walls:
                continue
            if cost + 1 >= costs.get(nxt, 10**9):
                continue
            costs[nxt] = cost + 1
            distance = (width - 1 - xx + width - 1 - yy) if heuristic else 0
            heapq.heappush(frontier, (cost + 1 + distance, cost + 1, nxt))
    return None, expanded


def run_original_experiment(*, samples: int = 160) -> dict:
    if type(samples) is not int or not 40 <= samples <= 1000:
        raise ValueError("40 to 1000 bounded samples required")
    records = []
    for seed in range(samples):
        rng = Random(seed)
        width = rng.choice((12, 16, 20, 24, 28))
        density = rng.choice((.1, .2, .3, .4))
        walls = {i for i in range(1, width * width - 1) if rng.random() < density}
        uniform, uniform_nodes = _solve(width, walls, False)
        astar, astar_nodes = _solve(width, walls, True)
        if uniform != astar:
            raise AssertionError("shortest-path parity regression")
        records.append({"seed": seed, "width": width, "requested_density": density,
                        "free_cells": width * width - len(walls), "walls_digest": canonical_digest(sorted(walls)),
                        "path_cost": astar, "uniform_cost_expansions": uniform_nodes,
                        "astar_expansions": astar_nodes,
                        "split": "holdout" if seed % 5 == 0 else "train"})
    train = [r for r in records if r["split"] == "train"]
    holdout = [r for r in records if r["split"] == "holdout"]
    xbar, ybar = mean(r["free_cells"] for r in train), mean(r["astar_expansions"] for r in train)
    denominator = sum((r["free_cells"] - xbar)**2 for r in train)
    slope = sum((r["free_cells"] - xbar) * (r["astar_expansions"] - ybar) for r in train) / denominator
    intercept = ybar - slope * xbar
    mae = mean(abs(max(0, intercept + slope*r["free_cells"]) - r["astar_expansions"]) for r in holdout)
    baseline = mean(abs(ybar-r["astar_expansions"]) for r in holdout)
    model = {"kind": "least_squares_expansion_cost_predictor", "feature": "free_cells",
             "intercept": intercept, "slope": slope, "holdout_mae_nodes": mae,
             "constant_baseline_mae_nodes": baseline, "beats_constant_on_this_holdout": mae < baseline,
             "train_samples": len(train), "holdout_samples": len(holdout),
             "neural_model": False, "production_approved": False}
    body = {"schema": "skeleton.dragon.original_experiment.v1",
            "experiment": "original_four_neighbor_grid_search_v1", "records": records,
            "source_code_owner": "original_repository_experiment", "model": model,
            "summary": {"sample_count": samples,
                "reachable": sum(r["path_cost"] is not None for r in records),
                "path_cost_parity": True,
                "uniform_cost_total_expansions": sum(r["uniform_cost_expansions"] for r in records),
                "astar_total_expansions": sum(r["astar_expansions"] for r in records)},
            "limitations": ["Synthetic grids, not finished games or human playtests",
                "Single implementation and generator; no independent replication",
                "Holdout shares the generator distribution; no out-of-distribution guarantee",
                "Node expansions are not wall-clock latency or player enjoyment",
                "No claim of a novel algorithm or superiority over official documentation"],
            "training_authorized_for_external_corpus": False,
            "memory_promotion_authorized": False, "release_authorized": False}
    return {**body, "experiment_digest": canonical_digest(body)}
