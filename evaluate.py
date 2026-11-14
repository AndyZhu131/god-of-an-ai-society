"""Repeat local decision checks and export playable-scenario evidence."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from decisions import DEFAULT_MODEL, OllamaPolicy, ScriptedPolicy
from scenario import create_station
from station import Decision


def historical_cases(source):
    history = {(entry["round"], entry["resident"]): Decision(**entry["decision"])
               for entry in source["decisions"]}
    station = create_station()
    station.advance(lambda turn: history[1, turn.resident_id])
    cases = [station.snapshot("mei"), station.snapshot("tang"), station.snapshot("lin")]
    for round_number in (2, 3):
        station.advance(lambda turn: history[round_number, turn.resident_id])
    cases.append(station.snapshot("qiao"))

    # A separate terminal position with a feasible rescue, to catch needless waiting.
    station = create_station()
    decide = ScriptedPolicy("cooperate")
    station.advance(decide)
    station.advance(decide)
    station.advance(lambda turn: Decision("wait"))
    return cases + [station.snapshot("wu")]


def decide_with_trace(policy, turn):
    start = perf_counter()
    decision = policy(turn)
    entry = {"resident": turn.resident_id, "card": json.loads(turn.card),
             "decision": asdict(decision), "seconds": round(perf_counter() - start, 3)}
    print(f"  {entry['card']['角色']} {decision.action_id} ({entry['seconds']}s)", flush=True)
    return decision, entry


def run_case_batch(policy, cases):
    decisions = [decide_with_trace(policy, turn)[1] for turn in cases]
    return {"mode": "cases", "stats": asdict(policy.stats), "decisions": decisions}


def run_game(policy, *, public_archive=True, lin_kept_past_promise=True, fallback_calibration_cost=2):
    station = create_station(public_archive=public_archive, lin_kept_past_promise=lin_kept_past_promise,
                             fallback_calibration_cost=fallback_calibration_cost)
    decisions = []
    rounds = []

    def decide(turn):
        decision, entry = decide_with_trace(policy, turn)
        decisions.append(entry)
        return decision

    while not station.outcome:
        print(f"Round {station.round}", flush=True)
        start = perf_counter()
        station.advance(decide)
        rounds.append(round(perf_counter() - start, 3))
        print(f"  Completed: {station.contributors}; outcome: {station.outcome or 'ongoing'}", flush=True)
    events = [dict(asdict(event), audience=sorted(event.audience) if event.audience is not None else None)
              for event in station.events]
    return {"mode": "game", "outcome": station.outcome, "stats": asdict(policy.stats),
            "public_archive": public_archive, "lin_kept_past_promise": lin_kept_past_promise,
            "fallback_calibration_cost": fallback_calibration_cost,
            "times": rounds, "decisions": decisions, "events": events,
            "promises": [asdict(promise) for promise in station.promises],
            "residents": {key: {"status": resident.status, "budget": resident.budget}
                          for key, resident in station.residents.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--seeds", type=int, nargs="+", default=[17, 32, 51])
    parser.add_argument("--think", action="store_true")
    parser.add_argument("--cases", type=Path, help="Read the original game's decisions to rebuild exact world states.")
    parser.add_argument("--private-archive", action="store_true")
    parser.add_argument("--lin-broke-past-promise", action="store_true")
    parser.add_argument("--fallback-calibration-cost", type=int, choices=(2, 3), default=2)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cases = historical_cases(json.loads(args.cases.read_text(encoding="utf8"))) if args.cases else None
    results = []
    for seed in args.seeds:
        print(f"{args.model} / seed {seed}", flush=True)
        policy = OllamaPolicy(args.model, seed=seed, think=args.think)
        result = run_case_batch(policy, cases) if cases else run_game(
            policy, public_archive=not args.private_archive,
            lin_kept_past_promise=not args.lin_broke_past_promise,
            fallback_calibration_cost=args.fallback_calibration_cost)
        results.append(dict(result, seed=seed, model=args.model, think=args.think))
        args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


if __name__ == "__main__":
    main()
