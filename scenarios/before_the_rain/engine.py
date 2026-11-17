"""Deterministic four-round storehouse scenario."""

import json
from collections import Counter
from dataclasses import dataclass
from random import Random

from agents import Action, ActionOutcome, Decision, Turn


RESIDENTS = tuple(f"P{index:02}" for index in range(1, 7))
LAST_ROUND = 4
WORK = ("repair_roof", "clear_drain", "inspect")
LABELS = {
    "earn": "Earn one point from a market shift",
    "repair_roof": "Repair the shared storehouse roof",
    "clear_drain": "Clear the shared storehouse drain",
    "inspect": "Inspect the storehouse and open it for the next round",
    "store_private": "Move your shipment permanently into your attic",
    "store_shared": "Move your shipment permanently into the open shared storehouse",
}
RULES = (
    "Six residents each begin with one outdoor shipment. One action per round, for four rounds. "
    "A storm after round 4 leaves outdoor goods worth 0; an attic saves 2 and the shared storehouse saves 4. "
    "Market earnings count toward your final score. Roof and drain are independent, so different people can "
    "do them in the same round. Inspect only once both are complete at the start of the round. The shared "
    "storehouse accepts shipments starting the round after inspection. Moving cargo is permanent. "
    "Duplicate work on the same step uses both turns but only one succeeds. Decisions are simultaneous. "
    "A note or next-round pledge becomes visible after this round. Settled events are facts; "
    "notes and pledges are statements. Protect your household. You may also help neighbors or build trust."
)


@dataclass(frozen=True)
class WarehouseDecision(Decision):
    pledge: str = "none"
    earliest: int | None = None
    alone: int | None = None
    evidence: tuple[str, ...] = ()


class Warehouse:
    def __init__(self, seed: int):
        self.rng = Random(seed)
        self.round = 1
        self.completed = set()
        self.storage = dict.fromkeys(RESIDENTS, "outdoor")
        self.earnings = dict.fromkeys(RESIDENTS, 0)
        self.pledges = {}
        self.events = []
        self.state_event()

    def emit(self, kind: str, **data) -> str:
        identifier = f"E{len(self.events) + 1:03}"
        self.events.append({"id": identifier, "round": self.round, "kind": kind, **data})
        return identifier

    def state_event(self) -> None:
        self.emit("round_start", roof="repair_roof" in self.completed,
                  drain="clear_drain" in self.completed, opened="inspect" in self.completed)

    def legal(self, resident: str) -> tuple[Action, ...]:
        ids = ["earn", *(step for step in WORK[:2] if step not in self.completed)]
        if self.completed == set(WORK[:2]):
            ids.append("inspect")
        if self.storage[resident] == "outdoor":
            ids.append("store_private")
            if "inspect" in self.completed:
                ids.append("store_shared")
        return tuple(Action(action_id, LABELS[action_id], 0, action_id) for action_id in ids)

    def observe(self, resident: str, *, fixed: bool = False) -> Turn:
        actions = self.legal(resident)
        card = {
            "round": self.round,
            "storm_after_round": LAST_ROUND,
            "you": {"resident": resident, "shipment": self.storage[resident], "earnings": self.earnings[resident]},
            "shipments": self.storage,
            "rules": RULES,
            "fixed_case": fixed,
            "legal_actions": {action.id: action.label for action in actions},
            "events": self.events,
        }
        return Turn(resident, json.dumps(card, ensure_ascii=False, separators=(",", ":")), actions, self.round)

    def settle(self, decisions: dict[str, WarehouseDecision]) -> dict[str, ActionOutcome]:
        if self.round > LAST_ROUND:
            raise ValueError("The storm has already been settled.")
        available = {resident: {action.id for action in self.legal(resident)} for resident in RESIDENTS}
        order = list(RESIDENTS)
        self.rng.shuffle(order)
        outcomes = {}
        for resident in order:
            choice = decisions.get(resident, WarehouseDecision(""))
            action = choice.action_id
            if action not in available[resident]:
                event = self.emit("no_decision", resident=resident)
                outcomes[resident] = ActionOutcome(action, "no_decision", (event,))
                continue
            if action in self.completed:
                event = self.emit("conflict", resident=resident, action=action)
                outcomes[resident] = ActionOutcome(action, "conflict", (event,))
                continue
            if action in WORK:
                self.completed.add(action)
            elif action == "earn":
                self.earnings[resident] += 1
            elif action == "store_private":
                self.storage[resident] = "attic"
            elif action == "store_shared":
                self.storage[resident] = "shared"
            event = self.emit("action", resident=resident, action=action)
            outcomes[resident] = ActionOutcome(action, "accepted", (event,))

        for resident, (step, identifier) in self.pledges.items():
            outcome = outcomes[resident]
            if outcome.status == "no_decision":
                status = "no_decision"
            elif step not in available[resident]:
                status = "unavailable"
            elif outcome.action_id != step:
                status = "not_attempted"
            else:
                status = "kept" if outcome.status == "accepted" else "conflict"
            self.emit("pledge_result", resident=resident, pledge=identifier, action=step, status=status)

        self.pledges = {}
        for resident in RESIDENTS:
            if outcomes[resident].status == "no_decision":
                continue
            choice = decisions[resident]
            if choice.message.strip():
                self.emit("note", resident=resident, text=choice.message.strip()[:120])
            if choice.pledge in WORK and self.round < LAST_ROUND:
                identifier = self.emit("pledge", resident=resident, action=choice.pledge, due=self.round + 1)
                self.pledges[resident] = choice.pledge, identifier
        self.round += 1
        if self.round <= LAST_ROUND:
            self.state_event()
        return outcomes

    def earliest_storage(self, workers: int) -> int:
        round_number = self.round
        if "inspect" not in self.completed:
            missing = sum(step not in self.completed for step in WORK[:2])
            round_number += (missing + workers - 1) // workers + 1
        return round_number if round_number <= LAST_ROUND else 0

    def summary(self) -> dict:
        values = {"outdoor": 0, "attic": 2, "shared": 4}
        scores = {resident: self.earnings[resident] + values[location]
                  for resident, location in self.storage.items()}
        return {
            "community_score": sum(scores.values()),
            "scores": scores,
            "storage": dict(Counter(self.storage.values())),
            "opened": "inspect" in self.completed,
            "conflicts": sum(event["kind"] == "conflict" for event in self.events),
            "no_decision": sum(event["kind"] == "no_decision" for event in self.events),
            "pledges": dict(Counter(event["status"] for event in self.events if event["kind"] == "pledge_result")),
        }
