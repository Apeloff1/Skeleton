"""create_app gate plan — open probes + install_gate wiring checklist."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from skeleton.gate_plane.stack import GATE_LAYERS, describe_stack, install_order


DEFAULT_OPEN_PROBES: Tuple[str, ...] = (
    "/health",
    "/ready",
    "/api/v1/health",
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/metrics",
    "/api/v1/metrics",
    "/",
    "/cortex/status",
    "/cockpit",
    "/docs",
    "/openapi.json",
    "/redoc",
)


@dataclass(frozen=True)
class CreateAppGatePlan:
    open_prefixes: Tuple[str, ...]
    layer_order_lifo: Tuple[str, ...]
    wire_install_gate: bool
    wire_write_admit: bool
    notes: Tuple[str, ...]

    def as_dict(self) -> Dict[str, object]:
        return {
            "open_prefixes": list(self.open_prefixes),
            "layer_order_lifo": list(self.layer_order_lifo),
            "wire_install_gate": self.wire_install_gate,
            "wire_write_admit": self.wire_write_admit,
            "notes": list(self.notes),
            "layers": describe_stack(),
        }


def open_probe_prefixes() -> Tuple[str, ...]:
    return DEFAULT_OPEN_PROBES


def build_create_app_gate_plan() -> CreateAppGatePlan:
    return CreateAppGatePlan(
        open_prefixes=DEFAULT_OPEN_PROBES,
        layer_order_lifo=tuple(install_order(lifo=True)),
        wire_install_gate=True,
        wire_write_admit=True,
        notes=(
            "Starlette add_middleware is LIFO",
            "Bare '/' open prefix must be exact-only",
            "Mutating verbs cross WriteAdmit after seal",
            "Sibling of Zaibatsu.Gate Program.cs gauntlet",
        ),
    )


# --- open probe validators ---

def assert_open_probe_health(path: str = "/health") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    # exact for root; prefix otherwise
    if "/health" == "/":
        ok = path == "/"
    else:
        ok = path == "/health" or path.startswith("/health/") or path.startswith("/health")
    listed = "/health" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_ready(path: str = "/ready") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    # exact for root; prefix otherwise
    if "/ready" == "/":
        ok = path == "/"
    else:
        ok = path == "/ready" or path.startswith("/ready/") or path.startswith("/ready")
    listed = "/ready" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_api_v1_health(path: str = "/api/v1/health") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    # exact for root; prefix otherwise
    if "/api/v1/health" == "/":
        ok = path == "/"
    else:
        ok = path == "/api/v1/health" or path.startswith("/api/v1/health/") or path.startswith("/api/v1/health")
    listed = "/api/v1/health" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_api_v1_health_live(path: str = "/api/v1/health/live") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    # exact for root; prefix otherwise
    if "/api/v1/health/live" == "/":
        ok = path == "/"
    else:
        ok = path == "/api/v1/health/live" or path.startswith("/api/v1/health/live/") or path.startswith("/api/v1/health/live")
    listed = "/api/v1/health/live" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_api_v1_health_ready(path: str = "/api/v1/health/ready") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    # exact for root; prefix otherwise
    if "/api/v1/health/ready" == "/":
        ok = path == "/"
    else:
        ok = path == "/api/v1/health/ready" or path.startswith("/api/v1/health/ready/") or path.startswith("/api/v1/health/ready")
    listed = "/api/v1/health/ready" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_metrics(path: str = "/metrics") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    # exact for root; prefix otherwise
    if "/metrics" == "/":
        ok = path == "/"
    else:
        ok = path == "/metrics" or path.startswith("/metrics/") or path.startswith("/metrics")
    listed = "/metrics" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_api_v1_metrics(path: str = "/api/v1/metrics") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    # exact for root; prefix otherwise
    if "/api/v1/metrics" == "/":
        ok = path == "/"
    else:
        ok = path == "/api/v1/metrics" or path.startswith("/api/v1/metrics/") or path.startswith("/api/v1/metrics")
    listed = "/api/v1/metrics" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_root(path: str = "/") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    # exact for root; prefix otherwise
    if "/" == "/":
        ok = path == "/"
    else:
        ok = path == "/" or path.startswith("//") or path.startswith("/")
    listed = "/" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_cortex_status(path: str = "/cortex/status") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    # exact for root; prefix otherwise
    if "/cortex/status" == "/":
        ok = path == "/"
    else:
        ok = path == "/cortex/status" or path.startswith("/cortex/status/") or path.startswith("/cortex/status")
    listed = "/cortex/status" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_cockpit(path: str = "/cockpit") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    # exact for root; prefix otherwise
    if "/cockpit" == "/":
        ok = path == "/"
    else:
        ok = path == "/cockpit" or path.startswith("/cockpit/") or path.startswith("/cockpit")
    listed = "/cockpit" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_docs(path: str = "/docs") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    # exact for root; prefix otherwise
    if "/docs" == "/":
        ok = path == "/"
    else:
        ok = path == "/docs" or path.startswith("/docs/") or path.startswith("/docs")
    listed = "/docs" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_openapi_json(path: str = "/openapi.json") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    # exact for root; prefix otherwise
    if "/openapi.json" == "/":
        ok = path == "/"
    else:
        ok = path == "/openapi.json" or path.startswith("/openapi.json/") or path.startswith("/openapi.json")
    listed = "/openapi.json" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_redoc(path: str = "/redoc") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    # exact for root; prefix otherwise
    if "/redoc" == "/":
        ok = path == "/"
    else:
        ok = path == "/redoc" or path.startswith("/redoc/") or path.startswith("/redoc")
    listed = "/redoc" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_layer_header_bound_planned() -> Dict[str, object]:
    order = install_order(lifo=True)
    return {"layer": "header_bound", "present": "header_bound" in order, "index": order.index("header_bound") if "header_bound" in order else -1}

def assert_layer_request_seal_planned() -> Dict[str, object]:
    order = install_order(lifo=True)
    return {"layer": "request_seal", "present": "request_seal" in order, "index": order.index("request_seal") if "request_seal" in order else -1}

def assert_layer_write_admit_planned() -> Dict[str, object]:
    order = install_order(lifo=True)
    return {"layer": "write_admit", "present": "write_admit" in order, "index": order.index("write_admit") if "write_admit" in order else -1}

def assert_layer_body_bound_planned() -> Dict[str, object]:
    order = install_order(lifo=True)
    return {"layer": "body_bound", "present": "body_bound" in order, "index": order.index("body_bound") if "body_bound" in order else -1}

def assert_layer_worm_audit_planned() -> Dict[str, object]:
    order = install_order(lifo=True)
    return {"layer": "worm_audit", "present": "worm_audit" in order, "index": order.index("worm_audit") if "worm_audit" in order else -1}

def assert_layer_auth_planned() -> Dict[str, object]:
    order = install_order(lifo=True)
    return {"layer": "auth", "present": "auth" in order, "index": order.index("auth") if "auth" in order else -1}

def assert_layer_policy_gate_planned() -> Dict[str, object]:
    order = install_order(lifo=True)
    return {"layer": "policy_gate", "present": "policy_gate" in order, "index": order.index("policy_gate") if "policy_gate" in order else -1}
