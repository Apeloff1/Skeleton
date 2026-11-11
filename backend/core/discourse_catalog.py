"""Tenant-authorized execution model selection for creative deliberation.

Legacy planning model names are not executable identity. The canonical engine
alone declares available provider/model pairs and the backend must not invent
multi-model work when only one model is admitted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.engine_client import EngineClient, EngineClientError
from core.model_catalog import model_catalog


class PanelUnavailable(ValueError):
    """A requested panel is not supported by current engine authority."""


@dataclass(frozen=True, slots=True)
class DeclaredModel:
    key: str
    provider_id: str
    model_id: str
    active: bool


@dataclass(frozen=True, slots=True)
class DeclaredPanel:
    models: tuple[DeclaredModel, ...]
    judge: DeclaredModel
    mode: str
    provider_diverse: bool
    independent_judge: bool
    source: str = "tenant_model_inventory"
    available_models: tuple[str, ...] = ()


def _model_row(item: object) -> DeclaredModel | None:
    if (
        not isinstance(item, Mapping)
        or item.get("available") is not True
        or item.get("selectable") is not True
    ):
        return None
    provider = item.get("provider_id")
    model = item.get("model_id")
    key = item.get("id")
    if (
        not isinstance(provider, str) or not 1 <= len(provider) <= 128
        or not isinstance(model, str) or not 1 <= len(model) <= 256
        or not isinstance(key, str) or key != provider + ":" + model
    ):
        return None
    return DeclaredModel(key, provider, model, item.get("active") is True)


def _validate_panel_request(
    selected: list[str] | tuple[str, ...] | None,
    judge_key: str | None,
    maximum: int,
) -> None:
    """Reject malformed direct callers before engine or catalog I/O."""
    if type(maximum) is not int or not 1 <= maximum <= 5:
        raise PanelUnavailable("invalid_panel_limit")
    if selected is not None and (
        type(selected) not in (list, tuple)
        or len(selected) > maximum
        or any(type(key) is not str or not 1 <= len(key) <= 385 for key in selected)
    ):
        raise PanelUnavailable("invalid_panel_selection")
    if judge_key is not None and (
        type(judge_key) is not str or len(judge_key) > 385
    ):
        raise PanelUnavailable("invalid_judge_selection")


def _catalog_panel(
    catalog: Mapping[str, Any],
    *,
    selected: list[str] | None,
    judge_key: str | None,
    maximum: int = 5,
) -> DeclaredPanel:
    _validate_panel_request(selected, judge_key, maximum)
    rows = catalog.get("models")
    if not isinstance(rows, list):
        raise PanelUnavailable("engine_model_inventory_unavailable")
    ready: dict[str, DeclaredModel] = {}
    for item in rows[:64]:
        model = _model_row(item)
        if model is not None:
            if model.key in ready:
                raise PanelUnavailable("duplicate_declared_model_identity")
            ready[model.key] = model
    if not ready:
        raise PanelUnavailable("no_executable_models")

    if selected:
        if len(selected) > maximum or len(set(selected)) != len(selected):
            raise PanelUnavailable("invalid_panel_selection")
        if any(model not in ready for model in selected):
            raise PanelUnavailable("requested_model_not_declared")
        models = tuple(ready[model] for model in selected)
    else:
        pool = sorted(ready.values(), key=lambda item: (not item.active, item.provider_id, item.model_id))
        ordered: list[DeclaredModel] = [pool[0]]
        # Prefer genuinely distinct providers before filling multiple seats
        # from one provider; never label a placeholder as an executed model.
        diverse = [item for item in pool[1:] if item.provider_id not in {pool[0].provider_id}]
        for item in diverse + pool[1:]:
            if item not in ordered and len(ordered) < maximum:
                ordered.append(item)
        models = tuple(ordered)

    if judge_key:
        if judge_key not in ready:
            raise PanelUnavailable("requested_judge_not_declared")
        judge = ready[judge_key]
    else:
        independent = [m for m in ready.values() if m.key not in {x.key for x in models}]
        # An available outside judge is better; otherwise use an explicitly
        # disclosed candidate model for self-review.
        judge = sorted(independent, key=lambda x: (not x.active, x.key))[0] if independent else models[0]
    unique_providers = {model.provider_id for model in models}
    mode = (
        "single_model_self_review"
        if len(models) == 1 else
        "cross_provider" if len(unique_providers) > 1 else
        "multiple_models_one_provider"
    )
    return DeclaredPanel(
        models=models,
        judge=judge,
        mode=mode,
        provider_diverse=len(unique_providers) > 1,
        independent_judge=judge.key not in {model.key for model in models},
        available_models=tuple(sorted(ready)),
    )


async def tenant_panel(
    *,
    tenant_id: str,
    actor_id: str,
    selected: list[str] | None = None,
    judge_key: str | None = None,
    maximum: int = 5,
) -> DeclaredPanel:
    """Resolve one model snapshot from explicit engine-side authorization."""
    # Direct Python callers do not pass through the HTTP admission layer.
    # Invalid identities must not instantiate the engine or query inventory.
    _validate_panel_request(selected, judge_key, maximum)
    try:
        client = EngineClient.from_env()
        catalog = await model_catalog(client, tenant_id=tenant_id, actor_id=actor_id)
    except (EngineClientError, TypeError, ValueError, TimeoutError) as exc:
        raise PanelUnavailable("engine_model_inventory_unavailable") from exc
    if not isinstance(catalog, Mapping):
        raise PanelUnavailable("engine_model_inventory_unavailable")
    return _catalog_panel(catalog, selected=selected, judge_key=judge_key, maximum=maximum)
