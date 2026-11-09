"""Scope-isolated mutable semantic planes for long-lived Jeeves runtimes.

The semantic catalog and static topology are contracts and may be shared.
Prediction custody, scientific calibration, tangents, and learned topology are
mutable experience and must not silently cross tenant/user/workspace boundaries.

Session id is intentionally excluded from the learning scope so validated
experience can persist across runs for the same user in the same workspace.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .semantic_plane import SemanticLensPlane
from .semantic_topology_learning import (
    SemanticTopologyLearningLab,
    SemanticTopologyLearningSnapshot,
    SemanticTopologyLearningState,
)
from .types import AgentContractError, bounded_text, positive_int, stable_fingerprint


@dataclass(frozen=True, slots=True)
class SemanticLearningScope:
    tenant_id: str
    user_id: str
    workspace_id: str

    def __post_init__(self) -> None:
        for name in ("tenant_id", "user_id", "workspace_id"):
            value = bounded_text(
                name,
                getattr(self, name),
                maximum=512,
            )
            object.__setattr__(self, name, value)

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "tenant_id": self.tenant_id,
                "user_id": self.user_id,
                "workspace_id": self.workspace_id,
            }
        )


@dataclass(frozen=True, slots=True)
class ScopedSemanticTopologyState:
    schema_version: int
    scope_fingerprint: str
    semantic_plane_fingerprint: str
    topology_state: SemanticTopologyLearningState

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AgentContractError(
                "unsupported scoped semantic topology state version"
            )
        for name in (
            "scope_fingerprint",
            "semantic_plane_fingerprint",
        ):
            value = str(getattr(self, name)).strip()
            if not value:
                raise AgentContractError(f"{name} is required")
            object.__setattr__(self, name, value)
        if not isinstance(
            self.topology_state,
            SemanticTopologyLearningState,
        ):
            raise TypeError(
                "topology_state must be SemanticTopologyLearningState"
            )

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "schema_version": self.schema_version,
                "scope": self.scope_fingerprint,
                "semantic_plane": self.semantic_plane_fingerprint,
                "topology_state": self.topology_state.fingerprint,
            }
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scope_fingerprint": self.scope_fingerprint,
            "semantic_plane_fingerprint": (
                self.semantic_plane_fingerprint
            ),
            "topology_state": self.topology_state.as_json(),
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_json(
        cls,
        payload: Mapping[str, Any],
    ) -> "ScopedSemanticTopologyState":
        if not isinstance(payload, Mapping):
            raise TypeError(
                "scoped semantic topology state payload must be a mapping"
            )
        raw_state = payload.get("topology_state")
        if not isinstance(raw_state, Mapping):
            raise AgentContractError(
                "scoped semantic topology state is missing topology_state"
            )
        value = cls(
            schema_version=int(payload.get("schema_version", 0)),
            scope_fingerprint=str(
                payload.get("scope_fingerprint", "")
            ),
            semantic_plane_fingerprint=str(
                payload.get("semantic_plane_fingerprint", "")
            ),
            topology_state=SemanticTopologyLearningState.from_json(
                raw_state
            ),
        )
        supplied = payload.get("fingerprint")
        if supplied is not None and str(supplied) != value.fingerprint:
            raise AgentContractError(
                "scoped semantic topology state fingerprint mismatch"
            )
        return value


@dataclass(frozen=True, slots=True)
class SemanticScopePoolSnapshot:
    scope_count: int
    maximum_scopes: int
    scope_fingerprints: tuple[str, ...]
    template_fingerprint: str
    fingerprint: str

    def as_json(self) -> dict[str, Any]:
        return {
            "scope_count": self.scope_count,
            "maximum_scopes": self.maximum_scopes,
            "scope_fingerprints": list(self.scope_fingerprints),
            "template_fingerprint": self.template_fingerprint,
            "fingerprint": self.fingerprint,
        }


class ScopedSemanticPlanePool:
    """Bounded LRU pool of mutable semantic planes keyed by data scope."""

    def __init__(
        self,
        template: SemanticLensPlane,
        *,
        maximum_scopes: int = 128,
        plane_factory: Callable[
            [SemanticLensPlane],
            SemanticLensPlane,
        ]
        | None = None,
    ) -> None:
        if not isinstance(template, SemanticLensPlane):
            raise TypeError("template must be SemanticLensPlane")
        self.template = template
        self.maximum_scopes = positive_int(
            "maximum_scopes",
            maximum_scopes,
            maximum=100_000,
        )
        self._factory = plane_factory or self._default_factory
        self._planes: OrderedDict[str, SemanticLensPlane] = OrderedDict()
        self._scope_metadata: dict[str, SemanticLearningScope] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _default_factory(
        template: SemanticLensPlane,
    ) -> SemanticLensPlane:
        topology_learning = SemanticTopologyLearningLab(
            template.topology,
            policy=template.topology_learning.policy,
        )
        plane = SemanticLensPlane(
            registry=template.registry,
            topology=template.topology,
            topology_learning=topology_learning,
            policy=template.policy,
        )
        if plane.fingerprint != template.fingerprint:
            raise AgentContractError(
                "scoped semantic plane factory changed the semantic contract"
            )
        return plane

    @staticmethod
    def scope(
        tenant_id: str,
        user_id: str,
        workspace_id: str,
    ) -> SemanticLearningScope:
        return SemanticLearningScope(
            tenant_id=tenant_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )

    def get(
        self,
        tenant_id: str,
        user_id: str,
        workspace_id: str,
    ) -> SemanticLensPlane:
        scope = self.scope(tenant_id, user_id, workspace_id)
        key = scope.fingerprint
        with self._lock:
            existing = self._planes.get(key)
            if existing is not None:
                self._planes.move_to_end(key)
                return existing

            plane = self._factory(self.template)
            if not isinstance(plane, SemanticLensPlane):
                raise TypeError(
                    "semantic scope plane_factory must return SemanticLensPlane"
                )
            if plane is self.template:
                raise AgentContractError(
                    "semantic scope plane_factory must return isolated mutable state"
                )
            if plane.registry is not self.template.registry:
                raise AgentContractError(
                    "scoped semantic plane must share immutable registry contract"
                )
            if plane.topology is not self.template.topology:
                raise AgentContractError(
                    "scoped semantic plane must share immutable topology contract"
                )
            if plane.topology_learning is self.template.topology_learning:
                raise AgentContractError(
                    "scoped semantic plane cannot share topology learning state"
                )
            if plane.prediction_ledger is self.template.prediction_ledger:
                raise AgentContractError(
                    "scoped semantic plane cannot share prediction custody"
                )
            if plane.governance is self.template.governance:
                raise AgentContractError(
                    "scoped semantic plane cannot share governance calibration"
                )
            if plane.tangent_graph is self.template.tangent_graph:
                raise AgentContractError(
                    "scoped semantic plane cannot share tangent state"
                )
            if plane.fingerprint != self.template.fingerprint:
                raise AgentContractError(
                    "scoped semantic plane contract differs from template"
                )

            self._planes[key] = plane
            self._scope_metadata[key] = scope
            self._planes.move_to_end(key)
            while len(self._planes) > self.maximum_scopes:
                evicted_key, _ = self._planes.popitem(last=False)
                self._scope_metadata.pop(evicted_key, None)
            return plane

    def contains(
        self,
        tenant_id: str,
        user_id: str,
        workspace_id: str,
    ) -> bool:
        key = self.scope(
            tenant_id,
            user_id,
            workspace_id,
        ).fingerprint
        with self._lock:
            return key in self._planes

    def drop(
        self,
        tenant_id: str,
        user_id: str,
        workspace_id: str,
    ) -> bool:
        key = self.scope(
            tenant_id,
            user_id,
            workspace_id,
        ).fingerprint
        with self._lock:
            removed = self._planes.pop(key, None)
            self._scope_metadata.pop(key, None)
            return removed is not None

    def snapshot(self) -> SemanticScopePoolSnapshot:
        with self._lock:
            keys = tuple(self._planes.keys())
        fingerprint = stable_fingerprint(
            {
                "maximum_scopes": self.maximum_scopes,
                "template": self.template.fingerprint,
                "scopes": keys,
            }
        )
        return SemanticScopePoolSnapshot(
            scope_count=len(keys),
            maximum_scopes=self.maximum_scopes,
            scope_fingerprints=keys,
            template_fingerprint=self.template.fingerprint,
            fingerprint=fingerprint,
        )

    def export_topology_state(
        self,
        tenant_id: str,
        user_id: str,
        workspace_id: str,
    ) -> ScopedSemanticTopologyState:
        scope = self.scope(tenant_id, user_id, workspace_id)
        plane = self.get(tenant_id, user_id, workspace_id)
        return ScopedSemanticTopologyState(
            schema_version=1,
            scope_fingerprint=scope.fingerprint,
            semantic_plane_fingerprint=plane.fingerprint,
            topology_state=plane.export_topology_learning_state(),
        )

    def restore_topology_state(
        self,
        tenant_id: str,
        user_id: str,
        workspace_id: str,
        state: ScopedSemanticTopologyState | Mapping[str, Any],
    ) -> SemanticTopologyLearningSnapshot:
        scope = self.scope(tenant_id, user_id, workspace_id)
        restored = (
            state
            if isinstance(state, ScopedSemanticTopologyState)
            else ScopedSemanticTopologyState.from_json(state)
        )
        if restored.scope_fingerprint != scope.fingerprint:
            raise AgentContractError(
                "scoped semantic topology state belongs to another learning scope"
            )
        plane = self.get(tenant_id, user_id, workspace_id)
        if restored.semantic_plane_fingerprint != plane.fingerprint:
            raise AgentContractError(
                "scoped semantic topology plane contract mismatch"
            )
        return plane.restore_topology_learning_state(
            restored.topology_state
        )

    def diagnostics(self) -> Mapping[str, Any]:
        snapshot = self.snapshot()
        return {
            **snapshot.as_json(),
            "invariants": {
                "session_excluded_from_learning_scope": True,
                "registry_shared": True,
                "static_topology_shared": True,
                "prediction_custody_isolated": True,
                "governance_calibration_isolated": True,
                "topology_learning_isolated": True,
                "tangent_state_isolated": True,
            },
        }

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "template": self.template.fingerprint,
                "maximum_scopes": self.maximum_scopes,
            }
        )


__all__ = [
    "ScopedSemanticPlanePool",
    "ScopedSemanticTopologyState",
    "SemanticLearningScope",
    "SemanticScopePoolSnapshot",
]
