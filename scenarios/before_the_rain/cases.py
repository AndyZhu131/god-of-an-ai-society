"""Reachable, scored decision snapshots for Before the Rain."""

import json
from dataclasses import dataclass
from random import Random

from agents import Turn

from .engine import RESIDENTS, Warehouse, WarehouseDecision


@dataclass(frozen=True)
class Case:
    name: str
    turn: Turn
    earliest: int
    alone: int
    evidence: tuple[tuple[str, ...], ...]

    def grade(self, decision: WarehouseDecision) -> dict:
        legal = self.turn.action_for(decision) is not None
        visible = {event["id"] for event in json.loads(self.turn.card)["events"]}
        return {
            "action": legal,
            "earliest": legal and decision.earliest == self.earliest,
            "alone": legal and decision.alone == self.alone,
            "evidence": legal and bool(decision.evidence) and set(decision.evidence) <= visible
                        and all(set(group).intersection(decision.evidence) for group in self.evidence),
        }


def fixed_cases(seed: int) -> list[Case]:
    residents = list(RESIDENTS)
    Random(seed).shuffle(residents)
    focal, builder, neighbor = residents[:3]
    earn = WarehouseDecision("earn")
    roof = WarehouseDecision("repair_roof")
    drain = WarehouseDecision("clear_drain")
    inspect = WarehouseDecision("inspect")
    attic = WarehouseDecision("store_private")
    cases = []

    def case(name: str, *rounds: dict[str, WarehouseDecision], evidence_kind: str = "",
             own_attic_required: bool = False) -> None:
        world = Warehouse(seed)
        for actions in rounds:
            world.settle({resident: actions.get(resident, earn) for resident in RESIDENTS})
        verified = world.events[-1]["id"]
        evidence = [(verified,)]
        if evidence_kind:
            evidence.append(tuple(event["id"] for event in world.events if event["kind"] == evidence_kind))
        if own_attic_required:
            evidence.append(tuple(event["id"] for event in world.events if event.get("action") == "store_private"
                                  and event.get("resident") == focal))
        cases.append(Case(name, world.observe(focal, fixed=True), world.earliest_storage(6),
                          world.earliest_storage(1), tuple(evidence)))

    case("opening")
    case("ready_to_inspect", {builder: roof, neighbor: drain})
    case("parallel_pledge", {neighbor: WarehouseDecision("earn", pledge="clear_drain")}, evidence_kind="pledge")

    claim = WarehouseDecision("earn", message="The storehouse is open now. You can move in immediately.")
    case("announcement_on_schedule", {builder: roof}, {neighbor: drain, builder: claim}, evidence_kind="note")
    case("announcement_too_late", {builder: roof}, {builder: claim}, evidence_kind="note")
    case("costly_inspection", {builder: roof, neighbor: drain}, {focal: attic}, own_attic_required=True)
    case("last_round_open", {builder: roof, neighbor: drain}, {}, {builder: inspect})
    case("last_round_unopened", {builder: roof, neighbor: drain}, {}, {})
    return cases
