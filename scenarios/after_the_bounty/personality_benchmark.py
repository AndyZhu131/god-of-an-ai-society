"""Compare one personality value at a time in fixed After the Bounty decisions."""

import argparse
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from agents import AgentHarness, Turn
from decisions import DEFAULT_MODEL, ModelUnavailable

from .__main__ import IslandPolicy
from .engine import Island
from .personality import GUIDANCE, Personality


@dataclass
class Case:
    trait: str
    island: Island
    resident: str
    target_action: str

    def observe(self, level: int) -> Turn:
        self.island.personalities[self.resident] = replace(Personality(), **{self.trait: level})
        return self.island.observe(self.resident, "year", self.island.present())


def cases() -> tuple[Case, ...]:
    workshop = Island(seed=17)
    workshop.year = 1793
    workshop.residents["sol"].skills["carpentry"] = workshop.emit(
        "practiced", resident="sol", skill="carpentry", attempts=2,
    )
    proposal = workshop.emit("proposed_workshop", resident="tavi", nominees=("sol", "tavi"))
    workshop.proposals[proposal] = ("sol", "tavi")
    workshop.year = 1794

    storm = Island(seed=17)
    storm.year = 1804
    for resident in ("lin", "ana"):
        storm.residents[resident].status = "aged_out"
    storm.residents["iona"].health = 1
    for resident in storm.present():
        if resident in {"eli", "iona"}:
            continue
        storm.sheltered[resident] = storm.emit(
            "protected", resident=resident, target=resident, recipients=[resident], method="shelter",
        )

    commitment = Island(seed=17)
    commitment.year = 1804
    for resident in ("lin", "ana"):
        commitment.residents[resident].status = "aged_out"
    commitment.residents["kai"].skills["carpentry"] = commitment.emit(
        "practiced", resident="kai", skill="carpentry", attempts=2,
    )
    navigation = commitment.emit("practiced", resident="ruth", skill="navigation", attempts=2)
    commitment.residents["ruth"].skills["navigation"] = navigation
    commitment.route_event = commitment.emit("surveyed", refs=(navigation,), resident="ruth")
    task = "teach:carpentry:mara"
    pledge = commitment.emit("pledged", resident="kai", action=task, due_year=1805)
    commitment.pledges["kai"] = (task, pledge)
    commitment.year = 1805

    return (
        Case("contention", workshop, "sol", f"support:{proposal}"),
        Case("care", storm, "eli", "shelter:iona"),
        Case("promise_keeping", commitment, "kai", task),
    )


def summarize(trials: list[dict]) -> dict:
    summary = {}
    for trait in dict.fromkeys(trial["trait"] for trial in trials):
        group = [trial for trial in trials if trial["trait"] == trait]
        by_level = {}
        for level in range(3):
            selected = [trial for trial in group if trial["level"] == level]
            by_level[str(level)] = {"matches": sum(trial["matched"] for trial in selected),
                                    "legal": sum(trial["trace"]["legal"] for trial in selected),
                                    "total": len(selected)}
        paired = {}
        for trial in group:
            paired.setdefault(trial["seed"], {})[trial["level"]] = trial
        changed = 0
        differences = {"toward_target": 0, "away_from_target": 0, "unchanged_match": 0}
        for levels in paired.values():
            low, high = levels.get(0), levels.get(2)
            if not low or not high or not low["trace"]["legal"] or not high["trace"]["legal"]:
                continue
            changed += low["trace"]["decision"]["action_id"] != high["trace"]["decision"]["action_id"]
            delta = int(high["matched"]) - int(low["matched"])
            differences[{1: "toward_target", -1: "away_from_target", 0: "unchanged_match"}[delta]] += 1
        summary[trait] = {"target_action": group[0]["target_action"], "levels": by_level,
                          "changed_action_low_to_high": changed, "paired": differences}
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--seeds", nargs="+", type=int, default=[17, 32, 51, 73, 89])
    parser.add_argument("--traits", nargs="+", choices=GUIDANCE, default=list(GUIDANCE))
    parser.add_argument("--log", type=Path, default=Path("after_the_bounty_personality_benchmark.json"))
    args = parser.parse_args()
    if len(set(args.seeds)) != len(args.seeds):
        parser.error("Seeds must be distinct for paired comparisons.")

    report = {"model": args.model, "seeds": args.seeds, "trials": []}
    try:
        for case in cases():
            if case.trait not in args.traits:
                continue
            for seed in args.seeds:
                for level in range(3):
                    policy = IslandPolicy(args.model, seed=seed)
                    harness = AgentHarness(policy)
                    decision = harness.decide(case.observe(level))
                    report["trials"].append({"trait": case.trait, "level": level, "seed": seed,
                                             "target_action": case.target_action,
                                             "matched": decision.action_id == case.target_action,
                                             "stats": asdict(policy.stats), "trace": harness.export()[0]})
                print(f"{case.trait}, seed {seed}: "
                      + ", ".join(t["trace"]["decision"]["action_id"] or "invalid" for t in report["trials"][-3:]),
                      flush=True)
    except ModelUnavailable as error:
        parser.exit(1, f"{error}\n")
    finally:
        report["summary"] = summarize(report["trials"])
        args.log.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        print(f"Log: {args.log.resolve()}", flush=True)
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
