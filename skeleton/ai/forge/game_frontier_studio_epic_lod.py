"""Fair, deterministic spatial LOD for real multi-layer Godot Studio terrain.

The existing renderer supports 8192 visual MultiMesh cells. Previously the
first dense layer could consume every instance, silently hiding Epic sky or
underground layers. Quotas now guarantee representation of every nonempty
owned layer while preserving original coordinate space and source lineage.
No gameplay collision, navigability or path geometry is fabricated by LOD.
"""
from __future__ import annotations

import math
from typing import Any

from .game_frontier_studio import StudioError, MapLayer


def allocate_visual_budgets(counts: tuple[int, ...], limit: int = 8192
                            ) -> tuple[int, ...]:
    """Deterministically apportion a hard global cap with no layer starvation.

    First grant every nonempty source a representation slot. Extra slots are
    distributed by sqrt(density), producing detail in broad megaworlds
    without eliminating smaller but story-critical original locations.
    """
    if (type(counts) is not tuple or type(limit) is not int
            or not 1 <= limit <= 8192 or len(counts) > 128
            or any(type(value) is not int or value < 0 or value > 65536
                   for value in counts)):
        raise StudioError("visual LOD quotas need bounded canonical tile counts")
    active = [i for i, number in enumerate(counts) if number > 0]
    if len(active) > limit:
        raise StudioError("renderer budget cannot preserve all original layers")
    if sum(counts) <= limit:
        return counts
    quotas = [int(number > 0) for number in counts]
    remaining = limit - len(active)
    # Water filling accounts for tiny layers reaching their full source count.
    # Each pass saturates at least one cap or consumes every remaining slot.
    while remaining:
        eligible = [i for i in active if quotas[i] < counts[i]]
        if not eligible:
            break
        weights = [math.sqrt(counts[i]) for i in eligible]
        total_weight = sum(weights)
        allocations = []
        for i, weight in zip(eligible, weights):
            raw = remaining * weight / total_weight
            take = min(counts[i] - quotas[i], int(math.floor(raw)))
            allocations.append((i, take, raw - math.floor(raw)))
        consumed = sum(n for _, n, _ in allocations)
        for i, n, _ in allocations:
            quotas[i] += n
        remaining -= consumed
        if not remaining:
            break
        # Largest remainder, deterministic original-layer index tie break.
        progressed = 0
        for i, _, fraction in sorted(allocations,
                                    key=lambda x: (-x[2], x[0])):
            if not remaining:
                break
            if quotas[i] < counts[i]:
                quotas[i] += 1
                remaining -= 1
                progressed += 1
        if consumed == 0 and progressed == 0:
            raise StudioError("visual quota allocator could not converge")
    if sum(quotas) > limit or any(q > c for q, c in zip(quotas, counts)):
        raise StudioError("visual quota violates original layer source bounds")
    return tuple(quotas)


def sample_visual_layer(layer: MapLayer, quota: int) -> list[int]:
    """Deterministic spatially distributed sparse *visual* map, same geometry.

    Choose a first representative from each 2D block, then sample remaining
    positions at quantiles of the original nonempty sequence. Never alias
    palette indices, move tiles, or mark an empty original cell as occupied.
    """
    if (not isinstance(layer, MapLayer) or type(quota) is not int
            or quota < 0 or quota > layer.width * layer.height):
        raise StudioError("invalid bounded Epic LOD layer budget")
    original = layer.data
    nonempty = [index for index, value in enumerate(original) if value >= 0]
    if quota > len(nonempty):
        raise StudioError("Epic LOD cannot invent terrain where source is blank")
    if quota == len(nonempty):
        return list(original)
    output = [-1] * len(original)
    if quota == 0:
        return output
    # Keep coherent large-scale coverage even for the most uneven terrain.
    stride = max(1, math.ceil(math.sqrt(len(nonempty) / quota)))
    representatives = []
    for y in range(0, layer.height, stride):
        for x in range(0, layer.width, stride):
            # Select closest valid tile to cell center within this block.
            tx = min(layer.width - 1, x + stride // 2)
            ty = min(layer.height - 1, y + stride // 2)
            options = (
                (abs(px - tx) + abs(py - ty), py, px,
                 py * layer.width + px)
                for py in range(y, min(y + stride, layer.height))
                for px in range(x, min(x + stride, layer.width))
                if original[py * layer.width + px] >= 0
            )
            candidate = min(options, default=None)
            if candidate is not None:
                representatives.append(candidate[3])
    # Quantiles over all spatial blocks rather than taking only the first
    # occupied blocks: preserve visual coverage at every map extremity.
    chosen: set[int] = (
        {representatives[(position * len(representatives)) // quota]
         for position in range(quota)}
        if len(representatives) > quota else set(representatives)
    )
    # Add deterministically distributed positions without source mutation.
    missing = quota - len(chosen)
    if missing:
        available = [index for index in nonempty if index not in chosen]
        for position in range(missing):
            chosen.add(available[(position * len(available)) // missing])
    if len(chosen) != quota:
        raise StudioError("Epic spatial sampler violated exact visual quota")
    for index in chosen:
        output[index] = original[index]
    return output


def planned_native_visual_layers(layers: tuple[MapLayer, ...],
                                 budget: int = 8192) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Materialize source-faithful Godot visual layers within renderer budget."""
    if (type(layers) is not tuple or len(layers) > 128
            or any(not isinstance(v, MapLayer) for v in layers)):
        raise StudioError("Epic native sampler requires exact existing map layers")
    counts = tuple(sum(value >= 0 for value in layer.data) for layer in layers)
    quotas = allocate_visual_budgets(counts, budget)
    records = []
    for layer, source_count, visual_count in zip(layers, counts, quotas):
        if source_count == 0:
            continue
        sparse = sample_visual_layer(layer, visual_count)
        records.append({
            "id": layer.layer_id,
            "width": layer.width,
            "height": layer.height,
            "elevation_m": layer.elevation_m,
            "palette": list(layer.palette),
            "tiles": sparse,
            "source_nonempty_cells": source_count,
            "rendered_cells": visual_count,
            "lod_strategy": "exact_source" if visual_count == source_count
                            else "balanced_spatial_v2",
        })
    rendered = sum(quotas)
    info = {
        "source_layer_count": len(layers),
        "rendered_layer_count": len(records),
        "visual_instance_budget": budget,
        "rendered_cells": rendered,
        "source_cells": sum(counts),
        "lod_ratio": round(rendered / max(1, sum(counts)), 8),
        "visual_lod_only": True, "collision_unmodified": True,
        "all_nonempty_layers_represented": all(q > 0 for q, c in zip(quotas, counts) if c > 0),
    }
    return records, info
