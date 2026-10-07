"""Provider registry: registration, lookup and capability-aware selection."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Iterable, Iterator

from .errors import DuplicateRegistrationError, NoProviderAvailableError, ProviderNotFoundError
from .provider import Provider, ProviderInfo
from .types import ChatRequest, ProviderCapability

__all__ = ["ProviderRegistry", "SelectionPolicy", "ProviderFactory"]

ProviderFactory = Callable[[], Provider]


@dataclass(frozen=True)
class SelectionPolicy:
    """How candidate providers are ordered for a request.

    ``prefer_local`` puts local providers first (privacy / offline mode);
    ``local_only`` excludes anything that is not local; ``allow`` / ``deny``
    filter by name; ``prefer_cheapest`` sorts by cost before priority.
    """

    prefer_local: bool = False
    local_only: bool = False
    prefer_cheapest: bool = False
    allow: frozenset[str] = frozenset()
    deny: frozenset[str] = frozenset()
    required_tags: frozenset[str] = frozenset()

    def admits(self, info: ProviderInfo) -> bool:
        if self.local_only and not info.local:
            return False
        if self.allow and info.name not in self.allow:
            return False
        if info.name in self.deny:
            return False
        if self.required_tags and not self.required_tags.issubset(info.tags):
            return False
        return True

    def sort_key(self, info: ProviderInfo) -> tuple[int, float, int, str]:
        local_rank = 0 if (self.prefer_local and info.local) else 1
        cost = info.cost_per_1k_tokens if self.prefer_cheapest else 0.0
        return (local_rank, cost, info.priority, info.name)


class ProviderRegistry:
    """Thread-safe registry of providers keyed by unique name.

    Providers may be registered eagerly (an instance) or lazily (a factory
    plus its :class:`ProviderInfo`), so optional SDK-backed adapters are only
    constructed when actually selected.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._instances: dict[str, Provider] = {}
        self._factories: dict[str, tuple[ProviderInfo, ProviderFactory]] = {}
        self._infos: dict[str, ProviderInfo] = {}
        self._fallback: str | None = None
        self._disabled: set[str] = set()

    # -- registration ------------------------------------------------------
    def register(self, provider: Provider, *, replace: bool = False, fallback: bool = False) -> Provider:
        info = provider.info
        with self._lock:
            self._check_free(info.name, replace)
            self._factories.pop(info.name, None)
            self._instances[info.name] = provider
            self._infos[info.name] = info
            if fallback:
                self._fallback = info.name
        return provider

    def register_factory(
        self,
        info: ProviderInfo,
        factory: ProviderFactory,
        *,
        replace: bool = False,
        fallback: bool = False,
    ) -> None:
        with self._lock:
            self._check_free(info.name, replace)
            self._instances.pop(info.name, None)
            self._factories[info.name] = (info, factory)
            self._infos[info.name] = info
            if fallback:
                self._fallback = info.name

    def _check_free(self, name: str, replace: bool) -> None:
        if not replace and name in self._infos:
            raise DuplicateRegistrationError(f"provider {name!r} is already registered")

    def unregister(self, name: str) -> None:
        with self._lock:
            if name not in self._infos:
                raise ProviderNotFoundError(f"provider {name!r} is not registered")
            self._instances.pop(name, None)
            self._factories.pop(name, None)
            self._infos.pop(name, None)
            self._disabled.discard(name)
            if self._fallback == name:
                self._fallback = None

    def set_fallback(self, name: str | None) -> None:
        with self._lock:
            if name is not None and name not in self._infos:
                raise ProviderNotFoundError(f"provider {name!r} is not registered")
            self._fallback = name

    def disable(self, name: str) -> None:
        with self._lock:
            if name not in self._infos:
                raise ProviderNotFoundError(f"provider {name!r} is not registered")
            self._disabled.add(name)

    def enable(self, name: str) -> None:
        with self._lock:
            self._disabled.discard(name)

    # -- lookup ------------------------------------------------------------
    @property
    def fallback_name(self) -> str | None:
        return self._fallback

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._infos)

    def infos(self) -> list[ProviderInfo]:
        with self._lock:
            return [self._infos[name] for name in sorted(self._infos)]

    def info(self, name: str) -> ProviderInfo:
        with self._lock:
            try:
                return self._infos[name]
            except KeyError:
                raise ProviderNotFoundError(f"provider {name!r} is not registered") from None

    def __contains__(self, name: object) -> bool:
        with self._lock:
            return name in self._infos

    def __len__(self) -> int:
        with self._lock:
            return len(self._infos)

    def __iter__(self) -> Iterator[str]:
        return iter(self.names())

    def get(self, name: str) -> Provider:
        with self._lock:
            provider = self._instances.get(name)
            if provider is not None:
                return provider
            entry = self._factories.get(name)
            if entry is None:
                raise ProviderNotFoundError(f"provider {name!r} is not registered")
            info, factory = entry
        built = factory()
        if built.info.name != info.name:
            raise DuplicateRegistrationError(
                f"factory for {info.name!r} built a provider named {built.info.name!r}"
            )
        with self._lock:
            existing = self._instances.get(name)
            if existing is not None:
                return existing
            if name in self._factories:
                self._factories.pop(name)
                self._instances[name] = built
        return built

    # -- selection ---------------------------------------------------------
    def candidates(
        self,
        request: ChatRequest | None = None,
        *,
        required: Iterable[ProviderCapability] = (),
        policy: SelectionPolicy | None = None,
        include_fallback: bool = True,
        exclude: Iterable[str] = (),
    ) -> list[ProviderInfo]:
        """Ordered providers able to serve ``request``; fallback goes last."""

        pol = policy or SelectionPolicy()
        need = set(required)
        model: str | None = None
        if request is not None:
            need |= set(request.required_capabilities)
            model = request.model
        excluded = set(exclude)
        with self._lock:
            infos = [i for n, i in self._infos.items() if n not in self._disabled and n not in excluded]
            fallback = self._fallback
        primary = [
            i
            for i in infos
            if i.name != fallback and pol.admits(i) and i.supports(frozenset(need)) and i.serves_model(model)
        ]
        primary.sort(key=pol.sort_key)
        if include_fallback and fallback is not None and fallback not in excluded:
            fb = next((i for i in infos if i.name == fallback), None)
            if fb is not None and fb.supports(frozenset(need - {ProviderCapability.TOOLS})):
                if not pol.local_only or fb.local:
                    primary.append(fb)
        return primary

    def select(self, request: ChatRequest, *, policy: SelectionPolicy | None = None) -> Provider:
        found = self.candidates(request, policy=policy)
        if not found:
            raise NoProviderAvailableError(
                "no registered provider satisfies "
                + ", ".join(sorted(c.value for c in request.required_capabilities))
            )
        return self.get(found[0].name)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "providers": [self._infos[n].as_dict() for n in sorted(self._infos)],
                "fallback": self._fallback,
                "disabled": sorted(self._disabled),
                "instantiated": sorted(self._instances),
            }

    async def aclose(self) -> None:
        with self._lock:
            instances = list(self._instances.values())
        for provider in instances:
            await provider.aclose()
