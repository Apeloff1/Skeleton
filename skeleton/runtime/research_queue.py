from dataclasses import dataclass


_ALLOWED_CLASSES = frozenset({"research", "experiment", "reproduction", "benchmark"})


@dataclass(frozen=True)
class ResearchComputeJob:
    job_id: str
    priority: int
    quota: int
    provenance: str
    workload_class: str = "research"

    def __post_init__(self) -> None:
        if not self.job_id or not self.provenance:
            raise ValueError("research job identity and provenance required")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise ValueError("integer research priority required")
        if (
            isinstance(self.quota, bool)
            or not isinstance(self.quota, int)
            or self.quota <= 0
        ):
            raise ValueError("positive research quota required")
        if self.workload_class not in _ALLOWED_CLASSES:
            raise ValueError("invalid research workload class")


@dataclass(frozen=True)
class ResearchAllocation:
    job_id: str
    units: int

    def __post_init__(self) -> None:
        if (
            not self.job_id
            or isinstance(self.units, bool)
            or not isinstance(self.units, int)
            or self.units <= 0
        ):
            raise ValueError("positive research allocation required")


@dataclass(frozen=True)
class ResearchQueue:
    jobs: tuple[ResearchComputeJob, ...]

    def __post_init__(self) -> None:
        if any(not isinstance(job, ResearchComputeJob) for job in self.jobs):
            raise ValueError("research jobs required")
        ids = [job.job_id for job in self.jobs]
        if len(ids) != len(set(ids)):
            raise ValueError("unique research jobs required")

    def allocate(self, capacity: int, production_reserved: int) -> tuple[ResearchAllocation, ...]:
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (capacity, production_reserved)
        ) or production_reserved > capacity:
            raise ValueError("valid compute capacity required")

        free = capacity - production_reserved
        allocations: list[ResearchAllocation] = []
        for job in sorted(self.jobs, key=lambda item: (-item.priority, item.job_id)):
            units = min(job.quota, free)
            if units:
                allocations.append(ResearchAllocation(job.job_id, units))
                free -= units
            if free == 0:
                break
        return tuple(allocations)
