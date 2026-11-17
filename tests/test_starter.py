import contextlib
import io
import importlib
import json
import tempfile
import unittest
from pathlib import Path

from starter.cli import DATA_PATH, TEAM_NAMES, load_scenario, main
from starter.model import Job, Scenario, Vehicle, run_plan


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.jobs = (
            Job("local", "Local street", 0, 1, 20, ("compact",)),
            Job("access", "Approach", 1, 2, 10, ("wide", "compact")),
            Job("gate", "Gate", 2, 1, 10, ("compact",)),
        )
        self.matrix = ((0, 6, 8), (5, 0, 3), (8, 2, 0))
        self.fleet = (Vehicle("large", "wide", 0), Vehicle("small", "compact", 0))

    def test_access_time_is_last_required_pass_and_small_vehicle_is_reserved(self):
        case = Scenario("test", 100, 25, ("access", "gate"), self.matrix, self.fleet, self.jobs)
        baseline = run_plan(case)
        priority = run_plan(case, lambda candidate: (
            not candidate.critical, candidate.finish
        ))
        self.assertGreater(baseline.access_ready, 25)
        self.assertEqual(priority.access_ready, 18)
        self.assertEqual(next(step.vehicle for step in priority.steps if step.job.id == "gate"), "small")

    def test_missing_small_vehicle_leaves_access_unopened(self):
        case = Scenario("test", 100, 25, ("access", "gate"), self.matrix, self.fleet[:1], self.jobs)
        result = run_plan(case)
        self.assertIsNone(result.access_ready)
        self.assertEqual(result.unfinished["gate"], "no_compatible_vehicle")

    def test_unreachable_transition_and_shift_limit_are_reported(self):
        matrix = ((0, None, 8), (5, 0, 3), (8, 2, 0))
        case = Scenario("test", 5, 4, ("gate",), matrix, self.fleet, self.jobs)
        result = run_plan(case)
        self.assertEqual(result.unfinished["access"], "unreachable")
        self.assertEqual(result.unfinished["gate"], "shift_limit")
        self.assertEqual(result.completed, 0)

    def test_exact_deadline_and_directional_transit(self):
        job = Job("gate", "Gate", 2, 1, 10, ("compact",))
        case = Scenario("test", 18, 18, ("gate",), self.matrix, self.fleet[1:], (job,))
        result = run_plan(case)
        self.assertEqual(result.access_ready, 18)
        self.assertEqual(result.lateness, 0)
        self.assertEqual(result.deadhead, 8)


class TeamAcceptanceTests(unittest.TestCase):
    def test_team_plans_have_legal_and_consistent_assignments(self):
        for team in TEAM_NAMES:
            policy = importlib.import_module(f"teams.{team}.policy")
            for mode in ("normal", "no_compact"):
                with self.subTest(team=team, scenario=mode):
                    case, _ = load_scenario(mode)
                    plan = policy.plan(case)
                    fleet = {vehicle.id: vehicle for vehicle in case.fleet}
                    jobs = {job.id: job for job in case.jobs}
                    position = {vehicle.id: vehicle.start for vehicle in case.fleet}
                    finished = {}
                    free_at = dict.fromkeys(fleet, 0)
                    for step in plan.steps:
                        vehicle = fleet[step.vehicle]
                        job = jobs[step.job.id]
                        self.assertEqual(step.job, job)
                        self.assertNotIn(job.id, finished)
                        self.assertIn(vehicle.type, job.vehicle_types)
                        self.assertGreaterEqual(step.depart, free_at[vehicle.id])
                        self.assertEqual(step.from_point, position[vehicle.id])
                        self.assertEqual(step.transit, case.transit[step.from_point][job.start])
                        self.assertLessEqual(step.finish, case.shift_seconds)
                        finished[job.id] = step.finish
                        free_at[vehicle.id] = step.finish
                        position[vehicle.id] = job.end
                    self.assertEqual(set(plan.unfinished), set(jobs) - set(finished))
                    if set(case.access_jobs) <= set(finished):
                        opened_at = max(finished[job] for job in case.access_jobs)
                        self.assertEqual(plan.access_ready, opened_at)
                        self.assertEqual(plan.lateness, max(0, opened_at - case.access_deadline))
                    else:
                        self.assertIsNone(plan.access_ready)
                        self.assertIsNone(plan.lateness)


class EntryPointTests(unittest.TestCase):
    def test_all_teams_start_for_both_scenarios(self):
        for number in range(1, 6):
            for scenario in ("normal", "no_compact"):
                with self.subTest(team=number, scenario=scenario):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        main(["--team", f"team_{number:02}", "--scenario", scenario])
                    self.assertIn("Базовый план", output.getvalue())
                    self.assertIn(f"План team_{number:02}", output.getvalue())

    def test_cli_uses_a_scenario_generated_by_a_team(self):
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        data["name"] = "Сценарий команды"
        data["transit_seconds"][0][2] = None
        data["access_deadline_seconds"] = 30
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "team-scenario.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with contextlib.redirect_stdout(output):
                main(["--team", "team_01", "--data", str(path)])
        result = output.getvalue()
        self.assertIn("Сценарий команды", result)
        self.assertIn("06:00:30", result)
        self.assertIn("Критический проезд · 06:43:00", result)

    def test_baseline_can_run_without_a_team(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main([])
        self.assertIn("Базовый план", output.getvalue())


if __name__ == "__main__":
    unittest.main()
