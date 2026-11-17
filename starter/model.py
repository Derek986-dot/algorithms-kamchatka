from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Job:
    id: str
    title: str
    start: int
    end: int
    work_seconds: int
    vehicle_types: tuple[str, ...]


@dataclass(frozen=True)
class Vehicle:
    id: str
    type: str
    start: int


@dataclass(frozen=True)
class Scenario:
    name: str
    shift_seconds: int
    access_deadline: int
    access_jobs: tuple[str, ...]
    transit: tuple[tuple[float | None, ...], ...]
    fleet: tuple[Vehicle, ...]
    jobs: tuple[Job, ...]


@dataclass(frozen=True)
class Candidate:
    job: Job
    vehicle: str
    from_point: int
    depart: float
    transit: float
    critical: bool

    @property
    def finish(self) -> float:
        return self.depart + self.transit + self.job.work_seconds


@dataclass(frozen=True)
class Plan:
    steps: tuple[Candidate, ...]
    unfinished: dict[str, str]
    access_ready: float | None
    lateness: float | None

    @property
    def completed(self) -> int:
        return len(self.steps)

    @property
    def deadhead(self) -> float:
        return sum(step.transit for step in self.steps)


Priority = Callable[[Candidate], tuple]


def run_plan(scenario: Scenario, priority: Priority | None = None) -> Plan:
    positions = {vehicle.id: vehicle.start for vehicle in scenario.fleet}
    available_at = dict.fromkeys(positions, 0.0)
    pending = {job.id: job for job in scenario.jobs}
    job_order = {job.id: index for index, job in enumerate(scenario.jobs)}
    steps = []

    if priority is None:
        def priority(candidate):
            return job_order[candidate.job.id], candidate.finish

    while pending:
        candidates = []
        unfinished = {}
        for job in pending.values():
            compatible = [v for v in scenario.fleet if v.type in job.vehicle_types]
            reachable = []
            for vehicle in compatible:
                position = positions[vehicle.id]
                transit = scenario.transit[position][job.start]
                if transit is None:
                    continue
                step = Candidate(
                    job, vehicle.id, position, available_at[vehicle.id],
                    transit, job.id in scenario.access_jobs,
                )
                reachable.append(step)
                if step.finish <= scenario.shift_seconds:
                    candidates.append(step)

            if not compatible:
                unfinished[job.id] = "no_compatible_vehicle"
            elif not reachable:
                unfinished[job.id] = "unreachable"
            elif all(step.finish > scenario.shift_seconds for step in reachable):
                unfinished[job.id] = "shift_limit"

        if not candidates:
            break
        selected = min(candidates, key=priority)
        steps.append(selected)
        del pending[selected.job.id]
        positions[selected.vehicle] = selected.job.end
        available_at[selected.vehicle] = selected.finish
    else:
        unfinished = {}

    finishes = {step.job.id: step.finish for step in steps}
    access_ready = None
    lateness = None
    if all(job in finishes for job in scenario.access_jobs):
        access_ready = max(finishes[job] for job in scenario.access_jobs)
        lateness = max(0, access_ready - scenario.access_deadline)

    return Plan(tuple(steps), unfinished, access_ready, lateness)
