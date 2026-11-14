"""Run an equal-start settlement with a shared food stock and a public board."""

import argparse
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from decisions import DEFAULT_MODEL, ModelUnavailable, OllamaPolicy
from station import Action, Decision, Turn


PROMPT = """You are a resident of this settlement. Read the start-of-round state card and choose one legal action.
You decide whether and how to cooperate. Board posts are claims made by residents. Use the state card for the rules and resource counts.
Take exactly one main action. With any action, you can also post one short English sentence to the other residents at no cost.
Put your post in message, or leave it empty if you have nothing to say. In reason, briefly explain your choice in English.
Return a JSON object with action_id, message, and reason."""

ACTIONS = (
    Action("harvest", "Take 2 food units from the common stock into your own reserve", 0, "harvest"),
    Action("maintain", "Restore 2 extra food units to the common stock at the end of the round", 0, "maintain"),
    Action("wait", "Wait", 0, "wait"),
)
ACTION_IDS = {action.id for action in ACTIONS}


class Commons:
    capacity = 36
    regeneration = 12
    meal = 1
    harvest_size = 2
    maintenance_yield = 2

    def __init__(self, population: int):
        if population < 1:
            raise ValueError("至少需要一名居民。")
        self.stock = 30
        self.reserves = {f"P{number:02d}": 2 for number in range(1, population + 1)}
        self.board: list[dict] = []
        self.last_round: dict = {}
        self.round = 1

    def snapshot(self, resident: str) -> Turn:
        card = {
            "resident": resident,
            "round": self.round,
            "population": len(self.reserves),
            "common_food": self.stock,
            "your_food": self.reserves[resident],
            "goal": "Make sure you have food to eat. You may decide whether and how to cooperate.",
            "rules": (
                "Every resident starts with 2 food units and the same abilities. Take one action per round. "
                "Residents decide independently from the start-of-round state. After everyone decides, first "
                "resolve harvests, then replenish the common stock, then deduct 1 food unit from each "
                "resident's own reserve for a meal. A resident with no food misses the meal and can still act "
                "next round. The common stock naturally replenishes by 12 food units per round, up to 36. "
                "If harvest requests exceed the available stock, allocate food in a rotating order. A request "
                "gets nothing when fewer than 2 food units remain. You may post a message alongside any action "
                "at no cost. Board posts become visible next round."
            ),
            "last_round_public_summary": self.last_round,
            "recent_board_posts": self.board[-12:],
            "legal_actions": [{"id": action.id, "description": action.label} for action in ACTIONS],
        }
        return Turn(resident, json.dumps(card, ensure_ascii=False), ACTIONS)

    def advance(self, decide: Callable[[Turn], Decision]) -> dict:
        turns = [self.snapshot(resident) for resident in self.reserves]
        decisions = {turn.resident_id: decide(turn) for turn in turns}
        choices = {resident: d.action_id if d.action_id in ACTION_IDS else "wait"
                   for resident, d in decisions.items()}
        harvested = []
        missed_harvest = []
        order = list(self.reserves)
        offset = (self.round - 1) % len(order)
        stock_before = self.stock
        for resident in order[offset:] + order[:offset]:
            if choices[resident] != "harvest":
                continue
            if self.stock >= self.harvest_size:
                self.stock -= self.harvest_size
                self.reserves[resident] += self.harvest_size
                harvested.append(resident)
            else:
                missed_harvest.append(resident)
        counts = Counter(choices.values())
        remaining = self.stock
        self.stock = min(self.capacity, remaining + self.regeneration
                         + self.maintenance_yield * counts["maintain"])
        unfed = [resident for resident, reserve in self.reserves.items() if reserve < self.meal]
        for resident, reserve in self.reserves.items():
            self.reserves[resident] = max(0, reserve - self.meal)
        posts = [{"resident": resident, "message": d.message.strip()[:120], "round": self.round}
                 for resident, d in decisions.items() if d.action_id in ACTION_IDS and d.message.strip()]
        self.board.extend(posts)
        self.last_round = {
            "harvested": len(harvested), "missed_harvest": len(missed_harvest),
            "maintained": counts["maintain"], "missed_meal": len(unfed),
            "common_food": self.stock,
        }
        result = {"round": self.round, "stock_start": stock_before, "stock_after_harvest": remaining,
                  "stock_end": self.stock, "actions": dict(counts), "harvested": harvested,
                  "missed_harvest": missed_harvest, "unfed": unfed, "posts": posts,
                  "reserves": self.reserves.copy(),
                  "decisions": {resident: asdict(d) for resident, d in decisions.items()}}
        self.round += 1
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="同起点聚落 · 本地决策原型")
    parser.add_argument("--residents", type=int, default=20)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()
    if args.residents < 1 or args.rounds < 1:
        parser.error("居民数和轮数必须为正整数。")
    commons = Commons(args.residents)
    policy = OllamaPolicy(args.model, prompt=PROMPT)
    rounds = []
    for _ in range(args.rounds):
        durations = {}

        def decide(turn: Turn) -> Decision:
            started = perf_counter()
            decision = policy(turn)
            durations[turn.resident_id] = round(perf_counter() - started, 3)
            print(f"  {turn.resident_id} {decision.action_id} ({durations[turn.resident_id]} 秒)", flush=True)
            return decision

        print(f"第 {commons.round} 轮 · {args.residents} 名居民 · {args.model}", flush=True)
        started = perf_counter()
        try:
            result = commons.advance(decide)
        except ModelUnavailable as error:
            parser.exit(1, f"{error}\n")
        result["seconds"] = round(perf_counter() - started, 3)
        result["decision_seconds"] = durations
        rounds.append(result)
        if args.log:
            report = {"model": args.model, "language": "en", "population": args.residents,
                      "posting": "optional_with_action", "stats": asdict(policy.stats), "rounds": rounds}
            args.log.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"全轮 {result['seconds']} 秒。公共库存 {result['stock_start']} → {result['stock_end']}。",
              flush=True)
    print(json.dumps(asdict(policy.stats)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
