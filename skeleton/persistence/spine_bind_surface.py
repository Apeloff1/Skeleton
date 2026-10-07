"""Join a bind card to unread provider and PR probe cards.

A claimed or green flag on either probe fails closed. The join does not
write claimed=1, does not start a dispatcher, and does not merge.
"""

from __future__ import annotations

from typing import Any


class SpineBindSurfaceError(RuntimeError):
    """Bind surface rejected its inputs. Not a maturity signal."""


_PROBE_FLAGS = ("claimed", "green", "ci_green", "merged")


class SpineBindSurface:
    """Keep the bind card off the provider and PR surfaces."""

    def card(
        self,
        *,
        bind: dict[str, Any],
        provider: dict[str, Any],
        pr: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(bind, dict) or bind.get("kind") != "spine_bind_card":
            raise SpineBindSurfaceError("bind must be a spine_bind_card")
        if bind.get("hit") is not False or bind.get("apply_landed") is not False:
            raise SpineBindSurfaceError("bind card is not dark")
        if bind.get("moved") is not False:
            raise SpineBindSurfaceError("bind card moved the fence")
        tenant_id = bind.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindSurfaceError("bind tenant missing")
        self._require_probe(provider, "spine_provider_probe", tenant_id)
        self._require_probe(pr, "spine_pr_probe", tenant_id)
        return {
            "kind": "spine_bind_surface",
            "hit": False,
            "law": "bind-surface-stays-unread",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "bind_digest": bind.get("digest"),
            "provider_claimed": 0,
            "pr_claimed": 0,
            "green": False,
            "ci_green": False,
            "merged": False,
            "apply_landed": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def _require_probe(self, probe: dict[str, Any], kind: str, tenant_id: str) -> None:
        if not isinstance(probe, dict) or probe.get("kind") != kind:
            raise SpineBindSurfaceError(f"probe must be a {kind} card")
        if probe.get("tenant_id") not in (None, tenant_id):
            raise SpineBindSurfaceError("probe tenant does not match")
        for flag in _PROBE_FLAGS:
            value = probe.get(flag, 0 if flag == "claimed" else False)
            if flag == "claimed":
                if value not in (0, False):
                    raise SpineBindSurfaceError("probe claimed a surface")
            elif value is True:
                raise SpineBindSurfaceError("probe is not unread")
