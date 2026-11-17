import argparse
import importlib
import json
import math
from pathlib import Path

from starter.model import Job, Plan, Scenario, Vehicle, run_plan

TEAM_NAMES = tuple(f"team_{number:02}" for number in range(1, 6))
DATA_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "district.json"
REASONS = {
    "no_compatible_vehicle": "нет подходящей машины",
    "unreachable": "в матрице нет переезда из текущих точек",
    "shift_limit": "в этом плане работа выходит за конец смены",
}


def load_scenario(mode: str) -> tuple[Scenario, str]:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    fleet = tuple(
        Vehicle(**vehicle)
        for vehicle in data["fleet"]
        if mode != "no_compact" or vehicle["type"] != "compact"
    )
    jobs = tuple(
        Job(**{**job, "vehicle_types": tuple(job["vehicle_types"])})
        for job in data["jobs"]
    )
    scenario = Scenario(
        data["name"],
        data["shift_seconds"],
        data["access_deadline_seconds"],
        tuple(data["access_jobs"]),
        tuple(tuple(row) for row in data["transit_seconds"]),
        fleet,
        jobs,
    )
    return scenario, data["start_time"]


def clock(start_time: str, seconds: float) -> str:
    hour, minute = map(int, start_time.split(":"))
    total = (hour * 60 + minute) * 60 + math.ceil(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def print_plan(label: str, plan: Plan, scenario: Scenario, start_time: str) -> None:
    print(f"\n{label}")
    for vehicle in scenario.fleet:
        print(f"  {vehicle.id}")
        for step in plan.steps:
            if step.vehicle != vehicle.id:
                continue
            start = clock(start_time, step.depart + step.transit)
            finish = clock(start_time, step.finish)
            print(f"    {start}–{finish}  {step.job.title}  ({step.job.start} → {step.job.end})")
    if plan.access_ready is None:
        print("  Критический проезд не открыт")
    else:
        status = f"опоздание {plan.lateness / 60:.1f} мин" if plan.lateness else "в срок"
        print(f"  Критический проезд · {clock(start_time, plan.access_ready)} ({status})")
    print(f"  Выполнено работ · {plan.completed}/{len(scenario.jobs)}")
    print(f"  Холостые переезды · {plan.deadhead / 60:.1f} мин")
    for job in scenario.jobs:
        if job.id in plan.unfinished:
            print(f"  Осталось · {job.title} — {REASONS[plan.unfinished[job.id]]}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Сравнение планов уборки одной смены")
    parser.add_argument("--team", choices=TEAM_NAMES, help="Команда для сравнения с базовым планом")
    parser.add_argument("--scenario", choices=("normal", "no_compact"), default="normal")
    args = parser.parse_args(argv)
    scenario, start_time = load_scenario(args.scenario)
    mode = "малая машина отсутствует" if args.scenario == "no_compact" else "полный парк"
    print(f"{scenario.name} · {mode}")
    print(f"Срок открытия критического проезда · {clock(start_time, scenario.access_deadline)}")

    baseline = run_plan(scenario)
    print_plan("Базовый план", baseline, scenario, start_time)
    if args.team:
        policy = importlib.import_module(f"teams.{args.team}.policy")
        team_plan = policy.plan(scenario)
        print_plan(f"План {args.team}", team_plan, scenario, start_time)
        if baseline.access_ready is None or team_plan.access_ready is None:
            print("\nСравнение времени · в одном или обоих планах проезд не открыт")
        else:
            gain_minutes = (baseline.access_ready - team_plan.access_ready) / 60
            change = "без изменения" if abs(gain_minutes) < 0.05 else (
                f"на {abs(gain_minutes):.1f} мин {'раньше' if gain_minutes > 0 else 'позже'}"
            )
            print(f"\nОткрытие проезда по плану команды · {change}")


if __name__ == "__main__":
    main()
