from starter.model import Candidate, Plan, Scenario, run_plan


def rank(candidate: Candidate) -> tuple[bool, float]:
    return not candidate.critical, candidate.finish


def plan(scenario: Scenario) -> Plan:
    return run_plan(scenario, rank)
