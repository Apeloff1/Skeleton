"""create_app gate plan — open probes + install_gate wiring checklist."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from skeleton.gate_plane.stack import describe_stack, install_order


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


def _matches_public_probe(path: str, prefix: str) -> bool:
    """Match a complete path segment; never treat a shared string prefix as public."""
    return type(path) is str and (path == prefix or (prefix != "/" and path.startswith(prefix + "/")))


def assert_open_probe_health(path: str = "/health") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    ok = _matches_public_probe(path, "/health")
    listed = "/health" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_ready(path: str = "/ready") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    ok = _matches_public_probe(path, "/ready")
    listed = "/ready" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_api_v1_health(path: str = "/api/v1/health") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    ok = _matches_public_probe(path, "/api/v1/health")
    listed = "/api/v1/health" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_api_v1_health_live(path: str = "/api/v1/health/live") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    ok = _matches_public_probe(path, "/api/v1/health/live")
    listed = "/api/v1/health/live" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_api_v1_health_ready(path: str = "/api/v1/health/ready") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    ok = _matches_public_probe(path, "/api/v1/health/ready")
    listed = "/api/v1/health/ready" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_metrics(path: str = "/metrics") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    ok = _matches_public_probe(path, "/metrics")
    listed = "/metrics" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_api_v1_metrics(path: str = "/api/v1/metrics") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    ok = _matches_public_probe(path, "/api/v1/metrics")
    listed = "/api/v1/metrics" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_root(path: str = "/") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    ok = _matches_public_probe(path, "/")
    listed = "/" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_cortex_status(path: str = "/cortex/status") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    ok = _matches_public_probe(path, "/cortex/status")
    listed = "/cortex/status" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_cockpit(path: str = "/cockpit") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    ok = _matches_public_probe(path, "/cockpit")
    listed = "/cockpit" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_docs(path: str = "/docs") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    ok = _matches_public_probe(path, "/docs")
    listed = "/docs" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_openapi_json(path: str = "/openapi.json") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    ok = _matches_public_probe(path, "/openapi.json")
    listed = "/openapi.json" in plan.open_prefixes
    return {"path": path, "listed": listed, "matches": ok, "ok": listed and ok}

def assert_open_probe_redoc(path: str = "/redoc") -> Dict[str, object]:
    plan = build_create_app_gate_plan()
    ok = _matches_public_probe(path, "/redoc")
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


# --- registered create_app hooks (extend-only; applied by the app factory) ---

CREATE_APP_HOOKS: Tuple[str, ...] = (
    "skeleton.gate_plane.core_mount:install_core_v1",
)


def resolve_create_app_hooks() -> List[object]:
    """Import and return the registered hook callables, in order (raises on failure)."""
    return [_resolve_hook(ref) for ref in CREATE_APP_HOOKS]


def _resolve_hook(ref: str) -> object:
    import importlib

    # Hook imports are intentionally literal: the repository policy forbids
    # importing module names assembled from runtime-controlled strings.
    if ref == "skeleton.gate_plane.core_mount:install_core_v1":
        from skeleton.gate_plane.core_mount import install_core_v1

        return install_core_v1
    raise ValueError("unregistered create_app hook")


CREATE_APP_HOOKS_ENV = "SKELETON_CREATE_APP_HOOKS"
CREATE_APP_HOOKS_STRICT_ENV = "SKELETON_CREATE_APP_HOOKS_STRICT"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_flag(name: str) -> bool:
    import os

    return os.environ.get(name, "").strip().lower() in _TRUTHY


def create_app_hooks_enabled() -> bool:
    """Opt-in: hooks run only when ``SKELETON_CREATE_APP_HOOKS`` is 1/true/yes/on."""
    return _env_flag(CREATE_APP_HOOKS_ENV)


def create_app_hooks_strict() -> bool:
    """Opt-in fail-closed mode: ``SKELETON_CREATE_APP_HOOKS_STRICT`` is 1/true/yes/on."""
    return _env_flag(CREATE_APP_HOOKS_STRICT_ENV)


def apply_create_app_hooks(app, hooks: Optional[Sequence[object]] = None) -> Dict[str, object]:
    """Run registered hooks on ``app`` at factory time (never in a lifespan).

    - Off unless ``SKELETON_CREATE_APP_HOOKS`` is set: the app boots unchanged.
    - On (default, error-isolated): a hook that fails to import or install is
      logged, recorded in the report and skipped; the app still boots.
    - On + ``SKELETON_CREATE_APP_HOOKS_STRICT``: any import or install failure
      raises ``RuntimeError`` and aborts app construction (fail-closed); the
      app is not marked as hooked.

    Idempotent per app (``app.state.create_app_hooks_applied``).
    """
    import logging

    log = logging.getLogger(__name__)
    state = getattr(app, "state", None)
    if not create_app_hooks_enabled():
        return {"enabled": False, "strict": False, "applied": [], "errors": {}}
    strict = create_app_hooks_strict()
    if state is not None and getattr(state, "create_app_hooks_applied", False):
        return {"enabled": True, "strict": strict, "applied": [], "errors": {},
                "skipped": "already-applied"}
    applied: List[str] = []
    errors: Dict[str, str] = {}
    if hooks is not None:
        resolved = [(getattr(h, "__qualname__", repr(h)), h) for h in hooks]
    else:
        resolved = []
        for ref in CREATE_APP_HOOKS:
            try:
                resolved.append((ref, _resolve_hook(ref)))
            except Exception as exc:
                if strict:
                    log.error("create_app hook %s failed to resolve: %s", ref, type(exc).__name__)
                    raise RuntimeError("required create_app hooks failed to resolve") from exc
                errors[ref] = f"{type(exc).__name__}: {exc}"
                log.warning("create_app hook %s failed to resolve; skipped: %s", ref, errors[ref])
    for ref_name, hook in resolved:
        name = getattr(hook, "__qualname__", ref_name)
        try:
            hook(app)
            applied.append(name)
        except Exception as exc:
            if strict:
                # Never serve a partially mounted/gated app in strict mode.
                log.error("required create_app hook %s failed: %s", name, type(exc).__name__)
                raise RuntimeError(f"required create_app hook {name} failed") from exc
            errors[name] = f"{type(exc).__name__}: {exc}"
            log.warning("create_app hook %s failed; skipped: %s", name, errors[name])
    report = {"enabled": True, "strict": strict, "applied": applied, "errors": errors}
    if state is not None:
        state.create_app_hooks_applied = True
        state.create_app_hooks_report = report
    return report
