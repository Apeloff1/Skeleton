from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class ResearchRecord:
    source: str
    query: str
    summary: str
    refs: list[str]
    collected_at: datetime
    metadata: dict[str, Any]


class ResearchBroker:
    """Collects bounded research for plan generation.

    A source adapter is a callable taking the project context and returning an
    iterable of dictionaries. Adapters can wrap GitHub, web/search, telemetry,
    issue trackers, test reports, or internal indexes. This class intentionally
    does not contain credentials or provider-specific clients.
    """

    def __init__(self, sources: dict[str, Callable[[dict[str, Any]], Iterable[dict[str, Any]]]]) -> None:
        self.sources = dict(sources)

    def collect(self, project_context: dict[str, Any], *, per_source_limit: int = 50) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for source_name, source in self.sources.items():
            try:
                for index, record in enumerate(source(project_context)):
                    if index >= per_source_limit:
                        break
                    if not isinstance(record, dict):
                        continue
                    normalized = dict(record)
                    normalized.setdefault("source", source_name)
                    normalized.setdefault("collected_at", datetime.now(timezone.utc).isoformat())
                    results.append(normalized)
            except Exception as exc:  # source isolation is intentional
                results.append(
                    {
                        "source": source_name,
                        "error": type(exc).__name__,
                        "message": str(exc),
                        "collected_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
        return results
