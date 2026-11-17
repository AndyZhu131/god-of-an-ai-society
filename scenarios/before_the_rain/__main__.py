"""Run and score a model on Before the Rain."""

import argparse
import json
from collections import Counter
from dataclasses import asdict
from math import ceil
from pathlib import Path
from statistics import median
from time import perf_counter

from agents import AgentHarness
from decisions import DEFAULT_MODEL

from .cases import fixed_cases
from .engine import LAST_ROUND, RESIDENTS, Warehouse
from .providers import ModelPolicy, ProviderError


def latency(values: list[float]) -> dict:
    if not values:
        return {}
    ordered = sorted(values)
    return {"median": round(median(ordered), 3), "p95": round(ordered[ceil(len(ordered) * 0.95) - 1], 3)}


def save(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + ".tmp")
    pending.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def run(args) -> dict:
    report = {"scenario": "before_the_rain", "benchmark_version": 2, "backend": args.backend,
              "model": args.model, "mode": args.mode, "effort": args.effort or None,
              "seed": args.seed, "case_seeds": args.case_seeds, "max_output": args.max_output,
              "fixed": [], "games": [], "attempts": [], "status": "running"}
    started = perf_counter()
    try:
        policy = ModelPolicy(args.backend, args.model, args.mode, args.host, args.seed, args.max_output, args.effort)
        report["attempts"] = policy.attempts
        for case_seed in args.case_seeds:
            for case in fixed_cases(case_seed):
                decision_started = perf_counter()
                decision = policy(case.turn)
                report["fixed"].append({"name": case.name, "seed": case_seed, "seconds": round(perf_counter() - decision_started, 3),
                                        "card": json.loads(case.turn.card), "decision": asdict(decision),
                                        "expected": {"earliest": case.earliest, "alone": case.alone, "evidence": case.evidence},
                                        "marks": case.grade(decision)})
            save(args.out, report)
        report["runtime"] = policy.runtime()
        policy.fixed = False
        for seed in (() if args.fixed_only else args.game_seeds):
            print(f"  full game, seed {seed}", flush=True)
            engine = Warehouse(seed)
            harness = AgentHarness(policy)
            rounds = []
            game_start = perf_counter()
            for _ in range(LAST_ROUND):
                round_start = perf_counter()
                decisions = harness.collect(engine.observe(resident) for resident in RESIDENTS)
                harness.settle(engine.settle(decisions))
                rounds.append(round(perf_counter() - round_start, 3))
            report["games"].append({"seed": seed, "seconds": round(perf_counter() - game_start, 3),
                                    "round_seconds": rounds, "summary": engine.summary(), "events": engine.events,
                                    "decisions": harness.export()})
            save(args.out, report)
        report["status"] = "complete"
    except ProviderError as error:
        report["status"] = "incomplete" if report["fixed"] else "unavailable"
        report["error"] = str(error)
    except KeyboardInterrupt:
        report["status"] = "interrupted"

    rows = report["fixed"]
    counts = Counter(key for row in rows for key, value in row["marks"].items() if value)
    attempts = report["attempts"]
    live = [row for game in report["games"] for row in game["decisions"]]
    report["summary"] = {
        "fixed_cases": len(rows), "points": sum(counts.values()), "points_available": len(rows) * 4,
        "action": counts["action"], "earliest": counts["earliest"], "alone": counts["alone"], "evidence": counts["evidence"],
        "fixed_warm_seconds": latency([row["seconds"] for row in rows[1:]]),
        "live_seconds": latency([row["seconds"] for row in live]),
        "load_seconds_first_request": attempts[0].get("load_seconds") if attempts else None,
        "requests": len(attempts), "invalid_requests": sum(not row["valid"] for row in attempts),
        "retries": sum(row["retry"] for row in attempts),
        "truncations": sum(row.get("finish") in ("length", "MAX_TOKENS", "max_output_tokens") for row in attempts),
        "input_tokens": sum(row.get("input_tokens") or 0 for row in attempts),
        "output_tokens": sum(row.get("output_tokens") or 0 for row in attempts),
        "seconds": round(perf_counter() - started, 3),
    }
    save(args.out, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("ollama", "openai", "gemini"), default="ollama")
    parser.add_argument("--model", help=f"Model ID (local fast default: {DEFAULT_MODEL})")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--mode", choices=("fast", "deep"), default="fast")
    parser.add_argument("--effort", default="", help="Optional model-specific reasoning level")
    parser.add_argument("--max-output", type=int, help="Generation budget, including reasoning tokens where applicable")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--case-seeds", type=int, nargs="+", default=[17, 41])
    parser.add_argument("--game-seeds", type=int, nargs="+", default=[17])
    parser.add_argument("--fixed-only", action="store_true")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.model is None:
        if args.backend != "ollama" or args.mode != "fast":
            parser.error("--model is required for the selected backend or mode")
        args.model = DEFAULT_MODEL
    if args.max_output is None:
        args.max_output = 384 if args.mode == "fast" else 1024
    if args.max_output < 32:
        parser.error("--max-output must be at least 32")
    print(f"{args.backend}/{args.model} {args.mode}", flush=True)
    report = run(args)
    print(json.dumps({"model": report["model"], "status": report["status"], "error": report.get("error"),
                      "summary": report["summary"], "games": [game["summary"] for game in report["games"]]},
                     ensure_ascii=True), flush=True)
    return int(report["status"] != "complete")


if __name__ == "__main__":
    raise SystemExit(main())
