from dataclasses import dataclass
import math


@dataclass(frozen=True)
class GPUInterconnect:
    a: str
    b: str
    bandwidth: float
    measured: bool

    def __post_init__(self) -> None:
        if (
            not self.a
            or not self.b
            or self.a == self.b
            or isinstance(self.bandwidth, bool)
            or not isinstance(self.bandwidth, (int, float))
            or not math.isfinite(self.bandwidth)
            or self.bandwidth <= 0
            or not isinstance(self.measured, bool)
        ):
            raise ValueError("valid GPU link required")

    @property
    def pair(self) -> tuple[str, str]:
        return tuple(sorted((self.a, self.b)))


@dataclass(frozen=True)
class GPUPath:
    devices: tuple[str, ...]
    bottleneck: float


@dataclass(frozen=True)
class CollectivePlacement:
    devices: tuple[str, ...]
    evidence: tuple[GPUInterconnect, ...]

    @property
    def bottleneck(self) -> float:
        return min(link.bandwidth for link in self.evidence)


def place_collective(devices, links) -> CollectivePlacement:
    chosen = tuple(devices)
    if (
        len(chosen) < 2
        or len(chosen) != len(set(chosen))
        or any(not device for device in chosen)
    ):
        raise ValueError("distinct collective devices required")

    link_items = tuple(links)
    if any(not isinstance(link, GPUInterconnect) for link in link_items):
        raise ValueError("GPU interconnect evidence required")

    by_pair: dict[tuple[str, str], GPUInterconnect] = {}
    for link in link_items:
        previous = by_pair.get(link.pair)
        if previous is not None and previous != link:
            raise ValueError("conflicting interconnect evidence")
        by_pair[link.pair] = link

    needed: list[GPUInterconnect] = []
    for index, a in enumerate(chosen):
        for b in chosen[index + 1 :]:
            link = by_pair.get(tuple(sorted((a, b))))
            if link is None or link.measured is not True:
                raise ValueError("collective requires measured pairwise interconnect")
            needed.append(link)

    needed.sort(key=lambda link: link.pair)
    return CollectivePlacement(chosen, tuple(needed))
