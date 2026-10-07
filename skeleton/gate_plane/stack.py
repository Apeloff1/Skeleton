"""Gate stack catalog — mirrors install_gate LIFO order."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple


@dataclass(frozen=True)
class GateLayer:
    name: str
    symbol: str
    band: str  # outer | mid | inner
    purpose: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "symbol": self.symbol,
            "band": self.band,
            "purpose": self.purpose,
        }


GATE_LAYERS: Tuple[GateLayer, ...] = (
    GateLayer("header_bound", "HeaderBoundMiddleware", "outer", "Bound request header map size"),
    GateLayer("request_seal", "RequestSealMiddleware", "outer", "HMAC seal + X-Request-Id"),
    GateLayer("write_admit", "WriteAdmitMiddleware", "mid", "AdaptiveGate + ChaosGovernor writes"),
    GateLayer("body_bound", "BodyBoundMiddleware", "mid", "Max body bytes fail-closed"),
    GateLayer("worm_audit", "WormAuditMiddleware", "mid", "WORM append before service"),
    GateLayer("auth", "AuthMiddleware", "inner", "Propagate verified attester"),
    GateLayer("policy_gate", "PolicyGateMiddleware", "inner", "Domain charter fail-closed"),
)


def install_order(*, lifo: bool = True) -> List[str]:
    """Return registration order for Starlette add_middleware (LIFO)."""
    names = [layer.name for layer in GATE_LAYERS]
    # install_gate registers innermost first so last added is outermost.
    return list(reversed(names)) if lifo else names


def describe_stack() -> List[Dict[str, str]]:
    return [layer.as_dict() for layer in GATE_LAYERS]


def check_layer_header_bound(path: str, method: str = "GET") -> Dict[str, object]:
    """Policy probe for HeaderBoundMiddleware (Bound request header map size)."""
    p = path or "/"
    m = (method or "GET").upper()
    openish = p in ("/", "/health", "/ready") or p.startswith("/api/v1/health")
    mutating = m in {"POST", "PUT", "PATCH", "DELETE"}
    return {
        "layer": "header_bound",
        "symbol": "HeaderBoundMiddleware",
        "band": "outer",
        "path": p,
        "method": m,
        "open_route_candidate": openish,
        "mutating": mutating,
        "requires_seal": (not openish),
        "requires_write_admit": (mutating and not openish),
        "purpose": "Bound request header map size",
    }


def check_layer_request_seal(path: str, method: str = "GET") -> Dict[str, object]:
    """Policy probe for RequestSealMiddleware (HMAC seal + X-Request-Id)."""
    p = path or "/"
    m = (method or "GET").upper()
    openish = p in ("/", "/health", "/ready") or p.startswith("/api/v1/health")
    mutating = m in {"POST", "PUT", "PATCH", "DELETE"}
    return {
        "layer": "request_seal",
        "symbol": "RequestSealMiddleware",
        "band": "outer",
        "path": p,
        "method": m,
        "open_route_candidate": openish,
        "mutating": mutating,
        "requires_seal": (not openish),
        "requires_write_admit": (mutating and not openish),
        "purpose": "HMAC seal + X-Request-Id",
    }


def check_layer_write_admit(path: str, method: str = "GET") -> Dict[str, object]:
    """Policy probe for WriteAdmitMiddleware (AdaptiveGate + ChaosGovernor writes)."""
    p = path or "/"
    m = (method or "GET").upper()
    openish = p in ("/", "/health", "/ready") or p.startswith("/api/v1/health")
    mutating = m in {"POST", "PUT", "PATCH", "DELETE"}
    return {
        "layer": "write_admit",
        "symbol": "WriteAdmitMiddleware",
        "band": "mid",
        "path": p,
        "method": m,
        "open_route_candidate": openish,
        "mutating": mutating,
        "requires_seal": (not openish),
        "requires_write_admit": (mutating and not openish),
        "purpose": "AdaptiveGate + ChaosGovernor writes",
    }


def check_layer_body_bound(path: str, method: str = "GET") -> Dict[str, object]:
    """Policy probe for BodyBoundMiddleware (Max body bytes fail-closed)."""
    p = path or "/"
    m = (method or "GET").upper()
    openish = p in ("/", "/health", "/ready") or p.startswith("/api/v1/health")
    mutating = m in {"POST", "PUT", "PATCH", "DELETE"}
    return {
        "layer": "body_bound",
        "symbol": "BodyBoundMiddleware",
        "band": "mid",
        "path": p,
        "method": m,
        "open_route_candidate": openish,
        "mutating": mutating,
        "requires_seal": (not openish),
        "requires_write_admit": (mutating and not openish),
        "purpose": "Max body bytes fail-closed",
    }


def check_layer_worm_audit(path: str, method: str = "GET") -> Dict[str, object]:
    """Policy probe for WormAuditMiddleware (WORM append before service)."""
    p = path or "/"
    m = (method or "GET").upper()
    openish = p in ("/", "/health", "/ready") or p.startswith("/api/v1/health")
    mutating = m in {"POST", "PUT", "PATCH", "DELETE"}
    return {
        "layer": "worm_audit",
        "symbol": "WormAuditMiddleware",
        "band": "mid",
        "path": p,
        "method": m,
        "open_route_candidate": openish,
        "mutating": mutating,
        "requires_seal": (not openish),
        "requires_write_admit": (mutating and not openish),
        "purpose": "WORM append before service",
    }


def check_layer_auth(path: str, method: str = "GET") -> Dict[str, object]:
    """Policy probe for AuthMiddleware (Propagate verified attester)."""
    p = path or "/"
    m = (method or "GET").upper()
    openish = p in ("/", "/health", "/ready") or p.startswith("/api/v1/health")
    mutating = m in {"POST", "PUT", "PATCH", "DELETE"}
    return {
        "layer": "auth",
        "symbol": "AuthMiddleware",
        "band": "inner",
        "path": p,
        "method": m,
        "open_route_candidate": openish,
        "mutating": mutating,
        "requires_seal": (not openish),
        "requires_write_admit": (mutating and not openish),
        "purpose": "Propagate verified attester",
    }


def check_layer_policy_gate(path: str, method: str = "GET") -> Dict[str, object]:
    """Policy probe for PolicyGateMiddleware (Domain charter fail-closed)."""
    p = path or "/"
    m = (method or "GET").upper()
    openish = p in ("/", "/health", "/ready") or p.startswith("/api/v1/health")
    mutating = m in {"POST", "PUT", "PATCH", "DELETE"}
    return {
        "layer": "policy_gate",
        "symbol": "PolicyGateMiddleware",
        "band": "inner",
        "path": p,
        "method": m,
        "open_route_candidate": openish,
        "mutating": mutating,
        "requires_seal": (not openish),
        "requires_write_admit": (mutating and not openish),
        "purpose": "Domain charter fail-closed",
    }

def domain_probe_forge(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `forge` charter."""
    prefix = "/api/v1/forge" if "forge" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/forge"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/forge", "/api/forge")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "forge",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_gameforge(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `gameforge` charter."""
    prefix = "/api/v1/gameforge" if "gameforge" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/gameforge"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/gameforge", "/api/gameforge")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "gameforge",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_swarm(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `swarm` charter."""
    prefix = "/api/v1/swarm" if "swarm" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/swarm"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/swarm", "/api/swarm")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "swarm",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_jeeves(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `jeeves` charter."""
    prefix = "/api/v1/jeeves" if "jeeves" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/jeeves"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/jeeves", "/api/jeeves")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "jeeves",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_memory(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `memory` charter."""
    prefix = "/api/v1/memory" if "memory" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/memory"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/memory", "/api/memory")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "memory",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_retrieval(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `retrieval` charter."""
    prefix = "/api/v1/retrieval" if "retrieval" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/retrieval"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/retrieval", "/api/retrieval")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "retrieval",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_pipeline(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `pipeline` charter."""
    prefix = "/api/v1/pipeline" if "pipeline" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/pipeline"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/pipeline", "/api/pipeline")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "pipeline",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_intelligence(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `intelligence` charter."""
    prefix = "/api/v1/intelligence" if "intelligence" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/intelligence"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/intelligence", "/api/intelligence")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "intelligence",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_resilience(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `resilience` charter."""
    prefix = "/api/v1/resilience" if "resilience" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/resilience"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/resilience", "/api/resilience")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "resilience",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_context(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `context` charter."""
    prefix = "/api/v1/context" if "context" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/context"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/context", "/api/context")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "context",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_ledger(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `ledger` charter."""
    prefix = "/api/v1/ledger" if "ledger" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/ledger"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/ledger", "/api/ledger")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "ledger",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_scheduler(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `scheduler` charter."""
    prefix = "/api/v1/scheduler" if "scheduler" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/scheduler"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/scheduler", "/api/scheduler")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "scheduler",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_genesis(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `genesis` charter."""
    prefix = "/api/v1/genesis" if "genesis" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/genesis"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/genesis", "/api/genesis")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "genesis",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_capabilities(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `capabilities` charter."""
    prefix = "/api/v1/capabilities" if "capabilities" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/capabilities"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/capabilities", "/api/capabilities")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "capabilities",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_interface(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `interface` charter."""
    prefix = "/api/v1/interface" if "interface" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/interface"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/interface", "/api/interface")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "interface",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_auth(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `auth` charter."""
    prefix = "/api/v1/auth" if "auth" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/auth"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/auth", "/api/auth")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "auth",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_cognition(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `cognition` charter."""
    prefix = "/api/v1/cognition" if "cognition" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/cognition"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/cognition", "/api/cognition")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "cognition",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_fabric(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `fabric` charter."""
    prefix = "/api/v1/fabric" if "fabric" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/fabric"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/fabric", "/api/fabric")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "fabric",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_legions(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `legions` charter."""
    prefix = "/api/v1/legions" if "legions" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/legions"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/legions", "/api/legions")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "legions",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_governance(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `governance` charter."""
    prefix = "/api/v1/governance" if "governance" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/governance"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/governance", "/api/governance")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "governance",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_lafs(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `lafs` charter."""
    prefix = "/api/v1/lafs" if "lafs" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/lafs"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/lafs", "/api/lafs")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "lafs",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_studio(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `studio` charter."""
    prefix = "/api/v1/studio" if "studio" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/studio"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/studio", "/api/studio")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "studio",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_court(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `court` charter."""
    prefix = "/api/v1/court" if "court" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/court"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/court", "/api/court")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "court",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_treasury(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `treasury` charter."""
    prefix = "/api/v1/treasury" if "treasury" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/treasury"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/treasury", "/api/treasury")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "treasury",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_reputation(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `reputation` charter."""
    prefix = "/api/v1/reputation" if "reputation" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/reputation"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/reputation", "/api/reputation")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "reputation",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_diet(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `diet` charter."""
    prefix = "/api/v1/diet" if "diet" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/diet"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/diet", "/api/diet")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "diet",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }

def domain_probe_boardroom(path: str) -> Dict[str, object]:
    """Longest-prefix domain probe for `boardroom` charter."""
    prefix = "/api/v1/boardroom" if "boardroom" not in ("fabric", "legions", "governance", "lafs", "studio", "court", "treasury", "reputation", "diet", "boardroom", "cognition", "swarm") else f"/api/boardroom"
    # Correct prefixes for empire courts
    candidates = ("/api/v1/boardroom", "/api/boardroom")
    hit = next((c for c in candidates if path == c or path.startswith(c + "/") or path.startswith(c)), None)
    return {
        "domain": "boardroom",
        "path": path,
        "matched_prefix": hit,
        "chartered": hit is not None,
    }


def audit_all_layers(path: str, method: str = "GET") -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    out.append(check_layer_header_bound(path, method))
    out.append(check_layer_request_seal(path, method))
    out.append(check_layer_write_admit(path, method))
    out.append(check_layer_body_bound(path, method))
    out.append(check_layer_worm_audit(path, method))
    out.append(check_layer_auth(path, method))
    out.append(check_layer_policy_gate(path, method))
    return out


def audit_all_domains(path: str) -> List[Dict[str, object]]:
    return [
        domain_probe_forge(path),
        domain_probe_gameforge(path),
        domain_probe_swarm(path),
        domain_probe_jeeves(path),
        domain_probe_memory(path),
        domain_probe_retrieval(path),
        domain_probe_pipeline(path),
        domain_probe_intelligence(path),
        domain_probe_resilience(path),
        domain_probe_context(path),
        domain_probe_ledger(path),
        domain_probe_scheduler(path),
        domain_probe_genesis(path),
        domain_probe_capabilities(path),
        domain_probe_interface(path),
        domain_probe_auth(path),
        domain_probe_cognition(path),
        domain_probe_fabric(path),
        domain_probe_legions(path),
        domain_probe_governance(path),
        domain_probe_lafs(path),
        domain_probe_studio(path),
        domain_probe_court(path),
        domain_probe_treasury(path),
        domain_probe_reputation(path),
        domain_probe_diet(path),
        domain_probe_boardroom(path),
    ]
