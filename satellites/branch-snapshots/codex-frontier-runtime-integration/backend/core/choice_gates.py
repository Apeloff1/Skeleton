"""
╔════════════════════════════════════════════════════════════════════════╗
║  CHOICE GATES — every advanced choice must be reflected in every step.  ║
║  ────────────────────────────────────────────────────────────────────  ║
║  For each locked advanced choice, verifies that EVERY forged gamefile    ║
║  AND every asset across EVERY snowball stage carries the matching        ║
║  applied-choice stamp. A single drifting item fails the gate.            ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from core import build_config


def build(config: dict, items: list[dict], assets: list[dict]) -> dict:
    """Gate each choice against the forged items + assets."""
    derived = build_config.derive(config)
    spec = {k: (label, kind, target) for k, label, kind, target in build_config.CHOICE_SPECS}
    gates = []
    for key, want in derived.items():
        _label, _kind, target = spec.get(key, (key, "style", "visual"))
        # which surfaces must carry this choice
        check_assets = target in ("visual", "audio", "geometry")
        item_ok = all((it.get("skin") or {}).get("applied_choices", {}).get(key) == want
                      for it in items)
        asset_ok = True
        if check_assets and assets:
            asset_ok = all(a.get("applied_choices", {}).get(key) == want for a in assets)
        ok = item_ok and asset_ok
        gates.append({
            "key": key, "label": _label, "target": target, "want": want,
            "passed": ok,
            "reflected_in": ["gamefiles"] + (["assets"] if check_assets else []),
            "detail": "reflected in every step" if ok
            else f"missing/mismatched on some {'assets' if not asset_ok else 'gamefiles'}",
        })
    passed = sum(1 for g in gates if g["passed"])
    return {
        "choices_gated": len(gates),
        "gates": gates,
        "passed": passed,
        "total": len(gates),
        "conformance_pct": round(100 * passed / max(1, len(gates))) if gates else 100,
        "all_reflected": passed == len(gates),
    }
