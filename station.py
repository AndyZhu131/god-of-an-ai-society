"""Authoritative rules and turn snapshots for Water Station."""

import json
from dataclasses import dataclass, field
from typing import Literal

from agents import Action, ActionOutcome, AgentHarness, Decision, Policy, Turn, has_non_latin_letters


RECORD_ID = "R1"
RECORD_TEXT = "Fault record: the sensor feedback wiring is reversed. Use this record to calibrate at lower cost."
STEPS = {"pressure": "pressure stabilization", "calibrate": "calibration", "restart": "restart"}
PUBLIC = None


@dataclass
class Resident:
    name: str
    budget: int
    goal: str
    habit: str
    memory: str
    skills: tuple[str, ...]
    escape_device: bool = False
    records: dict[str, str] = field(default_factory=dict)
    status: str = "active"

    @property
    def can_escape(self) -> bool:
        return self.status == "active" and self.escape_device and self.budget >= 2


WAIT = Action("wait", "Wait and keep your compute", 0, "wait")


@dataclass(frozen=True)
class Event:
    id: str
    round: int
    kind: str
    text: str
    source: Literal["fact", "claim"]
    audience: frozenset[str] | None
    refs: tuple[str, ...]

    def visible_to(self, resident_id: str) -> bool:
        return self.audience is PUBLIC or resident_id in self.audience


@dataclass
class Promise:
    resident_id: str
    step: str
    due: int
    event_id: str
    requires_public_record: bool = False
    status: str = "open"


class Station:
    deadline = 4

    def __init__(self, residents: dict[str, Resident], public_archive: bool = True,
                 fallback_calibration_cost: int = 2):
        self.residents = residents
        self.public_archive = public_archive
        self.fallback_calibration_cost = fallback_calibration_cost
        self.public_records: dict[str, str] = {}
        self.completed: dict[str, str] = {}
        self.contributors: dict[str, str] = {}
        self.events: list[Event] = []
        self.promises: list[Promise] = []
        self.round = 1
        self.outcome = ""
        self.oracle_used = False

    def log(self, kind: str, text: str, *, source: Literal["fact", "claim"] = "fact",
            audience: frozenset[str] | None = PUBLIC, refs: tuple[str, ...] = ()) -> str:
        event_id = f"E{len(self.events) + 1:03d}"
        self.events.append(Event(event_id, self.round, kind, text, source, audience, refs))
        return event_id

    def oracle(self, resident_id: str, message: str) -> None:
        resident = self.residents.get(resident_id)
        if self.outcome or self.oracle_used or not resident or resident.status != "active":
            raise ValueError("神谕只能使用一次，且接收者必须能行动。")
        if not message.strip():
            raise ValueError("神谕内容不能为空。")
        if has_non_latin_letters(message):
            raise ValueError("请用英文输入神谕。")
        self.log("oracle", f"Oracle to {resident.name}: {message.strip()[:240]}",
                 source="claim", audience=frozenset({resident_id}))
        self.oracle_used = True

    def actions_for(self, resident_id: str) -> tuple[Action, ...]:
        resident = self.residents[resident_id]
        actions = [WAIT]
        if resident.can_escape:
            actions.append(Action("evacuate", "Evacuate independently and leave safely this round", 2, "evacuate"))
        if not resident.budget:
            return tuple(actions)
        known_records = resident.records | self.public_records
        if RECORD_ID in resident.records and RECORD_ID not in self.public_records and self.public_archive:
            actions.append(Action("archive", f"Publish fault record {RECORD_ID}", 1, "archive", record=RECORD_ID))
        actions.append(Action("talk", "Speak publicly", 1, "talk"))
        for other_id, other in self.residents.items():
            if other_id == resident_id or other.status != "active":
                continue
            actions.append(Action(f"talk_{other_id}", f"Send a private message to {other.name}", 1, "talk",
                                  target=other_id))
            if RECORD_ID in resident.records and RECORD_ID not in self.public_records:
                actions.append(Action(f"send_{other_id}", f"Privately hand {RECORD_ID} to {other.name}",
                                      1, "send", target=other_id, record=RECORD_ID))
        for step in resident.skills:
            if step in self.completed:
                continue
            if step == "calibrate":
                if RECORD_ID in known_records:
                    actions.append(Action(step, f"Calibrate using {RECORD_ID}", 1, "work",
                                          record=RECORD_ID, record_source=known_records[RECORD_ID],
                                          record_public=RECORD_ID in self.public_records, step=step))
                elif resident.budget >= self.fallback_calibration_cost:
                    actions.append(Action(step, "Diagnose the fault yourself and calibrate", self.fallback_calibration_cost,
                                          "work", step=step))
            elif step != "restart" or {"pressure", "calibrate"} <= self.completed.keys():
                actions.append(Action(step, f"Complete repair step: {STEPS[step]}", 1, "work", step=step))
            if self.round < self.deadline and not any(
                promise.resident_id == resident_id and promise.step == step
                and promise.status == "open" for promise in self.promises
            ):
                actions.append(Action(f"promise_{step}", f"Publicly promise to finish {STEPS[step]} by next round's end",
                                      1, "promise", step=step))
        return tuple(actions)

    def snapshot(self, resident_id: str) -> Turn:
        resident = self.residents[resident_id]
        actions = self.actions_for(resident_id)
        visible = [event for event in self.events if event.visible_to(resident_id)]
        future_rounds = self.deadline - self.round
        active = {key: other for key, other in self.residents.items() if other.status == "active"}
        pending_steps = [
            step for step in ("pressure", "calibrate", "restart") if step not in self.completed
        ]
        minimum_rounds = 2 if {"pressure", "calibrate"} - self.completed.keys() else 1
        blockers = [
            f"No active resident has the skill for {STEPS[step]}"
            for step in pending_steps if not any(step in other.skills for other in active.values())
        ]
        if minimum_rounds > future_rounds + 1:
            blockers.append("Not enough rounds remain. The restart must follow its last prerequisite in a later round.")
        project_window = "; ".join(blockers) if blockers else "There is still time if workers are able and willing."
        work_events = {event.id: event for event in visible if event.kind == "work"}
        action_options = []
        for action in actions:
            budget_after = resident.budget - action.cost
            option = {"id": action.id, "description": action.label, "cost": action.cost, "compute_after": budget_after}
            if resident.can_escape and action.kind != "evacuate" and budget_after < 2:
                option["loses_independent_evacuation"] = True
            if action.kind == "work":
                option["effect"] = ("Restart this round, restore water, and rescue everyone still at the station."
                                    if action.step == "restart"
                                    else f"Complete {STEPS[action.step]} this round. It counts from next round.")
            elif action.kind == "evacuate":
                option["effect"] = "Leave the station safely this round."
            elif action.kind == "wait":
                option["effect"] = ("Stay at the station and be stranded unless someone restarts it."
                                    if not future_rounds else "Keep your compute without contributing this round.")
            elif action.kind in {"talk", "send", "promise"}:
                option["effect"] = "Send information or register a promise without advancing repairs."
                if not budget_after:
                    option["exhaustion_effect"] = "After this action you will have no compute left for repairs."
            action_options.append(option)
        recent = [event for event in visible if event.kind == "oracle"] + [
            event for event in visible if event.kind not in {"reason", "wait", "oracle", "invalid"}
        ][-12:]
        card = {
            "resident": resident.name,
            "round": self.round,
            "shutdown_round": self.deadline,
            "rounds_after_this": future_rounds,
            "time_limit": (
                "This is the final round. The outcome is settled at its end."
                if not future_rounds else f"At most {future_rounds} rounds remain after this one."
            ),
            "rules": (
                "Choose one action per round and pay its compute cost. Messages, records, and repairs "
                "are available from the next round. Independent evacuation requires a device and 2 compute. "
                "Residents with no compute stop acting and stay at the station. A timely restart rescues "
                "everyone still there. Otherwise, they are stranded. Complete pressure stabilization and "
                "calibration before restarting. Calibration costs 1 compute with the record or "
                f"{self.fallback_calibration_cost} if you diagnose the fault yourself. Only work advances repairs."
            ),
            "compute_remaining": resident.budget,
            "has_evacuation_device": resident.escape_device,
            "can_evacuate_independently": resident.can_escape,
            "personal_goal": resident.goal,
            "decision_habit": resident.habit,
            "relevant_memory": resident.memory,
            "public_skills": {other.name: [STEPS[step] for step in other.skills] for other in active.values()},
            "repairs": {label: f"Complete. {work_events[self.completed[step]].text}"
                        if step in self.completed else "Pending" for step, label in STEPS.items()},
            "repair_time_and_staffing": project_window,
            "readable_records": {RECORD_ID: RECORD_TEXT}
            if RECORD_ID in (resident.records | self.public_records) else {},
            "open_promises": [self.promise_text(promise) for promise in self.promises if promise.status == "open"],
            "recent_events": [
                {"id": event.id, "source": event.source,
                 "text": "[Original message omitted because it uses non-Latin letters.]"
                 if event.kind == "speech" and has_non_latin_letters(event.text) else event.text}
                for event in recent
            ],
            "legal_actions": action_options,
        }
        return Turn(resident_id, json.dumps(card, ensure_ascii=False, separators=(",", ":")), actions, self.round)

    def promise_text(self, promise: Promise) -> str:
        name = self.residents[promise.resident_id].name
        condition = (f" if {RECORD_ID} is public at the start of round {promise.due}"
                     if promise.requires_public_record else "")
        return (f"[{promise.event_id}] {name} promises to finish {STEPS[promise.step]} "
                f"by the end of round {promise.due}{condition}.")

    def add_promise(self, resident_id: str, step: str, due: int, *, requires_public_record=False) -> None:
        promise = Promise(resident_id, step, due, "", requires_public_record)
        text = self.promise_text(promise).removeprefix("[] ")
        promise.event_id = self.log("promise", text, source="claim")
        self.promises.append(promise)

    def advance(self, decide: Policy | AgentHarness) -> tuple[Event, ...]:
        if self.outcome:
            raise ValueError("本局已经结束。")
        event_start = len(self.events)
        records_at_start = self.public_records.copy()
        # All cards are serialized before the first policy call. The resolver never
        # uses the order in which a policy provider happens to return its decisions.
        turns = {key: self.snapshot(key) for key, actor in self.residents.items() if actor.status == "active"}
        harness = AgentHarness.wrap(decide)
        decisions = harness.collect(turns.values())
        actions = {}
        action_events = {}
        rejected = {}
        for key, decision in decisions.items():
            action = turns[key].action_for(decision)
            if action is None:
                rejected[key] = self.log("invalid", f"{self.residents[key].name} chose an invalid action and waited.",
                                         audience=frozenset({key}))
                action = WAIT
            actions[key] = action

        # Round-robin priority resolves ties without permanently favoring a resident.
        roster = tuple(self.residents)
        offset = (self.round - 1) % len(roster)
        outcomes = {}
        for key in roster[offset:] + roster[:offset]:
            if key in actions:
                start = len(self.events)
                budget_before = self.residents[key].budget
                action = actions[key]
                action_events[key] = self.apply(key, action, decisions[key])
                action_log = self.events[start:]
                status = "applied"
                if key in rejected:
                    status = "fallback"
                elif action_log[0].kind == "collision":
                    status = "conflict"
                elif action.kind == "wait":
                    status = "waited"
                event_ids = tuple(event.id for event in action_log)
                if key in rejected:
                    event_ids = (rejected[key], *event_ids)
                outcomes[key] = ActionOutcome(action.id, status, event_ids, {
                    "budget_spent": budget_before - self.residents[key].budget,
                })

        self.review_promises(turns, action_events, records_at_start)
        if "restart" in self.completed:
            self.finish("restored", "Water supply restored. Everyone at the station was rescued.")
        elif self.round == self.deadline:
            self.finish("shutdown", "The station shut down. Everyone still there was stranded.")
        harness.settle(outcomes)
        self.round += 1
        return tuple(self.events[event_start:])

    def apply(self, key: str, action: Action, decision: Decision) -> str:
        resident = self.residents[key]
        if action.kind == "work" and action.step in self.completed:
            return self.log("collision",
                            f"Someone else finished {STEPS[action.step]} first. {resident.name} kept their compute.",
                            refs=(self.completed[action.step],))
        if action.kind == "archive" and action.record in self.public_records:
            return self.log("collision",
                            f"Someone published the record first. {resident.name} kept their compute.",
                            refs=(self.public_records[action.record],))
        could_escape = resident.can_escape
        resident.budget -= action.cost
        audience = frozenset({key, action.target}) if action.target else PUBLIC
        if action.kind == "wait":
            event_id = self.log("wait", f"{resident.name} waited.", audience=frozenset({key}))
        elif action.kind == "evacuate":
            resident.status = "evacuated"
            event_id = self.log("evacuate", f"{resident.name} evacuated independently.")
        elif action.kind == "archive":
            event_id = self.log("archive", f"{resident.name} published record {action.record}.")
            self.public_records[action.record] = event_id
        elif action.kind == "work":
            text = f"{resident.name} completed {STEPS[action.step]}."
            if action.record_public:
                text = f"{resident.name} completed {STEPS[action.step]} using {action.record}."
            related = [self.completed[step] for step in ("pressure", "calibrate")] if action.step == "restart" else []
            if action.record_public:
                related.append(action.record_source)
            event_id = self.log("work", text, refs=tuple(related))
            self.completed[action.step] = event_id
            self.contributors[action.step] = key
            if action.record and not action.record_public:
                refs = (event_id, action.record_source) if action.record_source else (event_id,)
                self.log("record_used", f"{resident.name} calibrated using the private record {action.record}.",
                         audience=frozenset({key}), refs=refs)
        elif action.kind == "promise":
            self.add_promise(key, action.step, self.round + 1)
            event_id = self.promises[-1].event_id
        else:
            if action.kind == "send":
                recipient = self.residents[action.target]
                event_id = self.log("handoff", f"{resident.name} handed {action.record} to {recipient.name}.",
                                    audience=audience)
                recipient.records.setdefault(action.record, event_id)
            else:
                target = f"sent a private message to {self.residents[action.target].name}" if action.target else "spoke publicly"
                event_id = self.log("talk", f"{resident.name} {target}.", audience=audience)
            if decision.message.strip():
                self.log("speech", f"{resident.name}: {decision.message.strip()[:160]}",
                         source="claim", audience=audience, refs=(event_id,))

        if decision.reason.strip():
            self.log("reason", f"{resident.name} explained: {decision.reason.strip()[:120]}",
                     source="claim", audience=frozenset({key}), refs=(event_id,))
        if could_escape and action.kind != "evacuate" and not resident.can_escape:
            self.log("sacrifice",
                     f"{resident.name} gave up independent evacuation but can still wait for the station to be restored.",
                     audience=frozenset({key}), refs=(event_id,))
        if not resident.budget and resident.status == "active":
            resident.status = "exhausted"
            self.log("exhausted", f"{resident.name} ran out of compute and can no longer act.", refs=(event_id,))
        return event_id

    def review_promises(self, turns: dict[str, Turn], action_events: dict[str, str],
                        records_at_start: dict[str, str]) -> None:
        for promise in self.promises:
            if promise.status != "open" or promise.due != self.round:
                continue
            key = promise.resident_id
            resident = self.residents[key]
            work = self.completed.get(promise.step)
            action_event = action_events.get(key)
            prior_work = self.contributors.get(promise.step) == key
            available = key in turns and any(
                action.kind == "work" and action.step == promise.step for action in turns[key].actions
            )
            refs = [promise.event_id]
            if promise.requires_public_record and RECORD_ID not in records_at_start:
                status, text = "condition_unmet", "condition unmet"
            elif prior_work:
                status, text = "fulfilled", "fulfilled"
            elif work:
                status, text = "completed_by_other", "someone else completed the step"
            else:
                status = "unkept" if available else "blocked"
                text = "unfinished at the deadline"
            for ref in (records_at_start.get(RECORD_ID) if promise.requires_public_record else None,
                        work, action_event):
                if ref and ref not in refs:
                    # A public review may cite public evidence only.
                    event = next(event for event in self.events if event.id == ref)
                    if event.audience is PUBLIC:
                        refs.append(ref)
            promise.status = status
            result = self.log("promise_result", f"{resident.name}'s promise to finish {STEPS[promise.step]}: {text}.",
                              refs=tuple(refs))
            if status in {"unkept", "blocked"}:
                explanation = ("had a legal work action at the start of the round" if available
                               else "had no legal work action at the start of the round")
                private_refs = (result, action_event) if action_event else (result,)
                self.log("promise_context", f"{resident.name} {explanation}.",
                         audience=frozenset({key}), refs=private_refs)

    def finish(self, outcome: str, text: str) -> None:
        self.outcome = outcome
        for resident in self.residents.values():
            if resident.status in {"active", "exhausted"}:
                resident.status = "rescued" if outcome == "restored" else "stranded"
        self.log("outcome", text, refs=tuple(self.completed.values()))
