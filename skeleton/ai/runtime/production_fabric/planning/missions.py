"""Mission objective progression with no skipped prerequisites."""
from ..contracts.graph import topological
from ..contracts.errors import ConflictError

def progress(graph: dict[str, list[str]], done: set[str], objective: str) -> set[str]:
    order = topological(graph)
    if objective not in graph or objective in done:
        raise ConflictError('objective missing or already completed')
    if not set(graph[objective]).issubset(done):
        raise ConflictError('objective dependency incomplete')
    return set(done) | {objective}
