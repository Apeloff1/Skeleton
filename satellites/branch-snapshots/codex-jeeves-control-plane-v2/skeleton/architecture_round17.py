"""
Skeleton — Round-17 architecture addendum

Hardware-specialized OverseerEngine round: device classification,
resource governor with per-resource throttles, budget enforcement
bound to every resource consumer — usable on all devices within
their hardware limitations, optimized for stability.
"""

from __future__ import annotations

from typing import Any, Dict


NEW_MODULES: Dict[str, Dict[str, Any]] = {
    "skeleton.overseer.hardware": {
        "layer": "overseer",
        "purpose": "HardwareProbe: cross-platform capability + live-state detection (cpu, memory, thermal, battery, io, gpu, storage) with change events; never fails a boot",
        "exports": ["HardwareProbe", "HardwareProfile", "HardwareState", "HardwareChange", "DeviceClass"],
    },
    "skeleton.overseer.governor": {
        "layer": "overseer",
        "purpose": "ResourceGovernor: per-resource throttle factors from live hardware, BudgetProfile per device class, hysteresis stabilization, BudgetEnforcer applying to consumers",
        "exports": ["ResourceGovernor", "BudgetProfile", "BudgetEnforcer", "ThrottleDecision"],
    },
    "skeleton.overseer.engine": {
        "layer": "overseer",
        "purpose": "OverseerEngine: the main in-app engine — governor at the center of the facet graphs, binding budgets onto loader/queue/miner/RAG",
        "exports": ["OverseerEngine"],
    },
}

ENGINE_LOOP = [
    "Probe classifies the device (embedded → server)",
    "BudgetProfile derived from hardware capability",
    "Live state sensed every tick (cpu/mem/thermal/battery/io)",
    "Per-resource throttles computed; change events escalate",
    "Hysteresis prevents oscillation on noisy sensors",
    "BudgetEnforcer applies scaled budgets to all consumers",
    "Verdict carries device class + throttle + interventions",
]

DEVICE_CLASSES = ["embedded", "mobile", "laptop", "workstation", "server"]


def summary() -> Dict[str, Any]:
    return {
        "round17_modules": len(NEW_MODULES),
        "engine_loop_stages": len(ENGINE_LOOP),
        "engine_loop": ENGINE_LOOP,
        "device_classes": DEVICE_CLASSES,
        "governed_consumers": ["loading_queue", "priority_queue", "backlog_miner", "agentic_rag"],
        "throttle_resources": ["cpu", "memory", "thermal", "battery", "io"],
        "genesis_handles_support": ["support", "loader", "agentic_rag", "overseer", "engine"],
    }
