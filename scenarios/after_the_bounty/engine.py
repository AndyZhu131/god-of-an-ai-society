"""Authoritative yearly turns for After the Bounty."""

import json
from dataclasses import dataclass, field
from random import Random

from agents import Action, ActionOutcome, AgentHarness, Decision, Policy, Turn, has_non_latin_letters

from .personality import Personality


FIRST_YEAR, CONTACT_YEAR = 1790, 1808
STORM_YEARS = (1797, 1804)
MAX_HEALTH = 2
WAIT = Action("wait", "Do nothing this year. This does not restore health or prepare shelter.", 0, "wait")
SKILLS = ("carpentry", "navigation")
WORKSHOP = {"practice_carpentry", "repair"}
SHELTER_ACTIONS = {"shelter", "deliver"}
COMMUNITY = {"teach", "archive", "study"} | SHELTER_ACTIONS
PLEDGEABLE = WORKSHOP | COMMUNITY | {"practice_navigation", "survey"}
SOCIAL_EVENTS = {"taught", "studied", "took_workshop", "kept_pledge", "broke_pledge", "blocked_pledge",
                 "workshop_denied", "protected", "departed", "storm", "repaired", "surveyed", "forecast_changed"}


def health_observation(current: int) -> dict:
    return {"current": current, "maximum": MAX_HEALTH, "wait_restores_health": False}


@dataclass
class Resident:
    starting_age: int
    goal: str
    cares_about: str = ""
    last_year: int | None = None
    health: int = MAX_HEALTH
    status: str = "present"
    practice: dict[str, int] = field(default_factory=dict)
    skills: dict[str, str] = field(default_factory=dict)

    def age(self, year: int) -> int:
        return self.starting_age + year - FIRST_YEAR


@dataclass(frozen=True)
class IslandDecision(Decision):
    pledge: str = ""
    nominees: tuple[str, ...] = ()
    health_readback: dict | None = None


def starting_residents() -> dict[str, Resident]:
    return {
        "lin": Resident(51, "Pass on a skill someone will use after you are gone.", "mara", 1798),
        "ana": Resident(43, "Keep Iona safe and help the settlement remain independent.", "iona", 1802),
        "mara": Resident(10, "Learn enough to decide your own future.", "lin"),
        "iona": Resident(7, "Help the people who cared for you.", "ana"),
        "eli": Resident(25, "Preserve the option of leaving the island."),
        "tavi": Resident(24, "Protect Iona and keep access to useful tools.", "iona"),
        "ruth": Resident(28, "Make useful knowledge available to anyone."),
        "noa": Resident(21, "Find people who keep their word and work with them."),
        "bess": Resident(26, "Make sure Mara is safe before taking personal risks.", "mara"),
        "sol": Resident(23, "Gain a voice in how the workshop is run."),
        "kai": Resident(29, "Keep the small boat and the sea route usable."),
        "ada": Resident(27, "Make the community able to survive without you."),
    }


class Island:
    def __init__(self, seed: int, delay_storm: int | None = None):
        self.residents = starting_residents()
        self.priority = list(self.residents)
        Random(seed).shuffle(self.priority)
        self.year = FIRST_YEAR
        self.storm_years = set(STORM_YEARS)
        self.delay_storm = delay_storm
        self.storm_postponed = False
        self.dispositions: dict[str, str] = {}
        self.personalities: dict[str, Personality] = {}
        self.council_event = ""
        self.council_intents: dict[str, dict] = {}
        self.hull_event = ""
        self.route_event = ""
        self.archive: dict[str, str] = {}
        self.sheltered: dict[str, str] = {}
        self.reservations: tuple[str, ...] = ()
        self.pledges: dict[str, tuple[str, str]] = {}
        self.proposals: dict[str, tuple[str, ...]] = {}
        self.events: list[dict] = []
        self.ending: dict | None = None

    def emit(self, kind: str, *, refs=(), **details) -> str:
        event_id = f"E{len(self.events) + 1:04}"
        self.events.append({"id": event_id, "year": self.year, "kind": kind, "refs": list(refs), **details})
        return event_id

    @property
    def boat_ready(self) -> bool:
        return bool(self.hull_event and self.route_event)

    def present(self) -> dict[str, Resident]:
        return {key: resident for key, resident in self.residents.items() if resident.status == "present"}

    def adults(self) -> dict[str, Resident]:
        return {key: resident for key, resident in self.present().items() if resident.age(self.year) >= 16}

    def order(self) -> list[str]:
        offset = (self.year - FIRST_YEAR) % len(self.priority)
        return self.priority[offset:] + self.priority[:offset]

    def forecast(self) -> int | None:
        return next((year for year in (self.year, self.year + 1) if year in self.storm_years), None)

    def postpone_storm(self) -> str:
        forecast = self.forecast()
        if forecast is None or self.storm_postponed:
            raise ValueError("Only one forecast storm can be postponed.")
        self.storm_years.remove(forecast)
        self.storm_years.add(forecast + 1)
        self.storm_postponed = True
        return self.emit("forecast_changed", from_year=forecast, to_year=forecast + 1)

    def can_deliver(self, key: str) -> bool:
        return self.boat_ready and key not in self.sheltered and "navigation" in self.residents[key].skills

    def shelter_actions(self, key: str, people: dict[str, Resident]) -> list[Action]:
        actions = []
        for other in people:
            if other in self.sheltered:
                continue
            recipient = "yourself" if other == key else other
            actions.append(Action(f"shelter:{other}", f"Prepare storm shelter for {recipient} only", 1,
                                  "shelter", target=other))
            if other != key and self.can_deliver(key):
                actions.append(Action(f"deliver:{other}", f"Use the boat to shelter yourself and {other}", 1,
                                      "deliver", target=other))
        return actions

    def pledge_options(self, actions: tuple[Action, ...]) -> list[str]:
        if self.year >= CONTACT_YEAR - 1:
            return []
        storm_next_year = self.forecast() == self.year + 1
        return [action.id for action in actions if action.kind in PLEDGEABLE
                and (action.kind not in SHELTER_ACTIONS or storm_next_year)]

    def storm_plan(self, people: dict[str, Resident]) -> dict:
        uncovered = {key: resident for key, resident in people.items() if key not in self.sheltered}
        planned = {}
        for volunteer, (action_id, event_id) in self.pledges.items():
            kind, _, target = action_id.partition(":")
            if kind not in SHELTER_ACTIONS or volunteer not in people or target not in uncovered:
                continue
            recipients = (target,)
            if kind == "deliver":
                if not self.can_deliver(volunteer):
                    continue
                recipients = (volunteer, target)
            for recipient in recipients:
                planned.setdefault(recipient, []).append({"volunteer": volunteer, "event": event_id})
        return {
            "pledges_by_target": planned,
            "uncovered_without_pledge": [key for key in uncovered if key not in planned],
            "would_die_if_unprotected": [key for key, resident in uncovered.items() if resident.health == 1],
        }

    def actions_for(self, key: str, phase: str, people: dict[str, Resident]) -> tuple[Action, ...]:
        actor = people[key]
        if phase == "council":
            return (Action("pass", "Make no announcement", 0, "pass"), *(
                Action(f"announce:{action.id}", f"Announce your intention: {action.label}", 0,
                       "announce", target=action.target)
                for action in self.shelter_actions(key, people)
            ))
        if phase == "contact":
            actions = [Action("wait", "Stay ashore and decline to launch the boat today", 0, "wait")]
            if self.boat_ready and "navigation" in actor.skills:
                actions.append(Action("contact", "Volunteer to navigate to Topaz now", 0, "contact"))
            return tuple(actions)
        if phase == "departure":
            return (Action("stay", "Remain on the island", 0, "stay"),
                    Action("leave", "Accept a place aboard Topaz", 0, "leave"))

        actions = [WAIT]
        if self.proposals:
            actions.append(Action("guard", "Defend open workshop access", 1, "guard"))
            profile = self.personalities.get(key)
            for proposal, nominees in self.proposals.items():
                if profile and profile.no_self_reservation and key in nominees:
                    continue
                actions.append(Action(f"support:{proposal}", f"Support workshop proposal {proposal}", 1, "support",
                                      target=proposal))
        for skill in SKILLS:
            if skill not in actor.skills:
                action_id = f"practice_{skill}"
                actions.append(Action(action_id, f"Practice {skill}", 1, action_id, step=skill))
                if skill in self.archive:
                    actions.append(Action(f"study:{skill}", f"Learn {skill} from the archive", 1, "study", step=skill))
                continue
            if skill not in self.archive:
                actions.append(Action(f"archive:{skill}", f"Archive your {skill} knowledge", 1, "archive", step=skill))
            for other, student in people.items():
                if other != key and skill not in student.skills:
                    actions.append(Action(f"teach:{skill}:{other}", f"Teach {skill} to {other}", 1, "teach",
                                          target=other, step=skill))
        if "carpentry" in actor.skills and not self.hull_event:
            actions.append(Action("repair", "Use one workshop seat to repair the hull", 1, "repair"))
        if "navigation" in actor.skills and not self.route_event:
            actions.append(Action("survey", "Survey the sea route from shore", 1, "survey"))
        if self.forecast() is not None:
            actions.extend(self.shelter_actions(key, people))
        return tuple(actions)

    def observe(self, key: str, phase: str, people: dict[str, Resident]) -> Turn:
        actor = people[key]
        actions = self.actions_for(key, phase, people)
        social = [event for event in self.events if event["kind"] in SOCIAL_EVENTS]
        relevant = {key, actor.cares_about} - {""}
        personal = [event for event in social
                    if relevant.intersection(event.get(field) for field in ("resident", "target", "teacher"))][-4:]
        recent = {event["id"]: event for event in [*social[-5:], *personal]}
        messages = [event for event in self.events if event["kind"] == "message"][-4:]
        board = [{"resident": event["resident"],
                  "text": "[Message omitted: non-Latin text.]" if has_non_latin_letters(event["text"]) else event["text"]}
                 for event in messages]
        card = {
            "year": self.year, "phase": phase, "you": key, "your_health": health_observation(actor.health),
            "goal": actor.goal, "care_about": actor.cares_about,
            "your_last_year": actor.last_year, "practice_done": actor.practice,
            "people": {person: {"age": resident.age(self.year), "health": resident.health, "skills": list(resident.skills)}
                       for person, resident in people.items()},
            "hull_repaired": bool(self.hull_event), "route_surveyed": bool(self.route_event),
            "archive": self.archive, "storm_forecast_year": self.forecast(), "shelter_ready_for": list(self.sheltered),
            "workshop_seats": 2, "reserved_this_year": self.reservations, "priority": self.order(),
            "proposals_to_vote_on": self.proposals, "pledges_due_this_year": self.pledges,
            "recent_events": sorted(recent.values(), key=lambda event: event["id"]), "notice_board": board,
            "legal_actions": {action.id: action.label for action in actions},
            "pledge_action_ids": self.pledge_options(actions),
        }
        if key in self.dispositions:
            card["personal_disposition"] = self.dispositions[key]
        if key in self.personalities:
            card["personality"] = self.personalities[key].describe()
        if card["storm_forecast_year"] is not None and phase in {"year", "council"}:
            card["storm_plan"] = self.storm_plan(people)
        if phase == "year" and self.council_event:
            covered = {person for plan in self.council_intents.values() for person in plan["covers"]}
            card["council"] = {
                "event": self.council_event,
                "announced_intentions": self.council_intents,
                "unprotected_without_intention": [
                    person for person in people if person not in self.sheltered and person not in covered
                ],
            }
        if phase == "contact":
            card["encounter"] = {
                "ship": "Topaz", "visible_now": True, "boat_ready": self.boat_ready,
                "decision": "One willing navigator can make contact today. Launching does not cost health. Contact "
                            "gives every adult a later choice to leave or stay. Volunteering does not require leaving. "
                            "If nobody volunteers, the ship passes and there is no later chance to board.",
            }
        elif phase == "departure":
            card["encounter"] = {
                "ship": "Topaz", "contact_made": True,
                "decision": "Topaz offers you a place aboard. Choose now whether to leave or stay.",
            }
        return Turn(key, json.dumps(card, ensure_ascii=False, separators=(",", ":")), actions, self.year)

    def collect(self, harness: AgentHarness, phase: str) -> tuple[dict[str, Turn], dict[str, Decision], dict[str, Action]]:
        people = self.present()
        turns = {key: self.observe(key, phase, people) for key in self.adults()}
        decisions = harness.collect(turns.values())
        chosen = {}
        for key, turn in turns.items():
            action = turn.action_for(decisions[key])
            if action is not None:
                chosen[key] = action
        return turns, decisions, chosen

    def hold_council(self, policy: Policy | AgentHarness) -> str:
        if self.forecast() is None or self.council_event:
            raise ValueError("A council can be held once per year while a storm is forecast.")
        harness = AgentHarness.wrap(policy)
        self.council_event = self.emit("council_called", storm_year=self.forecast())
        turns, _, chosen = self.collect(harness, "council")
        outcomes = {}
        for resident in turns:
            action = chosen.get(resident)
            if action is not None and action.kind == "announce":
                intended_action = action.id.removeprefix("announce:")
                covers = [resident, action.target] if intended_action.startswith("deliver:") else [action.target]
                event = self.emit("shelter_intent", refs=(self.council_event,), resident=resident,
                                  action=intended_action, covers=covers)
                self.council_intents[resident] = {"event": event, "action": intended_action, "covers": covers}
                outcomes[resident] = ActionOutcome(action.id, "announced", (event,))
            else:
                outcomes[resident] = ActionOutcome("pass", "passed" if action else "fallback", (self.council_event,))
        harness.settle(outcomes)
        return self.council_event

    def review_council(self, outcomes: dict[str, ActionOutcome]) -> None:
        if not self.council_event:
            return
        followed = {}
        for resident, plan in self.council_intents.items():
            outcome = outcomes[resident]
            if outcome.action_id == plan["action"] and outcome.status == "applied":
                followed[resident] = outcome.event_ids[0]
        refs = [self.council_event, *(plan["event"] for plan in self.council_intents.values()), *followed.values()]
        self.emit("council_review", refs=refs, announced=len(self.council_intents),
                  followed=followed, shelter_ready_for=list(self.sheltered))
        self.council_event = ""
        self.council_intents.clear()

    def advance(self, policy: Policy | AgentHarness) -> None:
        if self.year >= CONTACT_YEAR:
            raise ValueError("All yearly turns are complete.")
        if self.year == self.delay_storm:
            self.postpone_storm()
        harness = AgentHarness.wrap(policy)
        turns, decisions, chosen = self.collect(harness, "year")
        outcomes = {}
        workers = []
        priority = list(dict.fromkeys([*self.reservations, *self.order()]))
        for key in priority:
            if key not in turns:
                continue
            action = chosen.get(key)
            if action is None:
                event = self.emit("invalid_decision", resident=key, submitted=decisions[key].action_id)
                outcomes[key] = ActionOutcome("wait", "fallback", (event,))
                continue
            outcomes[key] = self.apply_work(key, action, workers)
        self.review_council(outcomes)
        self.review_pledges(turns, chosen, outcomes)
        self.resolve_proposals(chosen)
        self.post_notices(turns, decisions, chosen)
        if self.year in self.storm_years:
            self.resolve_storm()
        for key, resident in self.present().items():
            if resident.last_year == self.year:
                resident.status = "aged_out"
                self.emit("departed", resident=key, cause="lifespan")
        harness.settle(outcomes)
        self.year += 1

    def apply_work(self, key: str, action: Action, workers: list[str]) -> ActionOutcome:
        actor = self.residents[key]
        kind, skill = action.kind, action.step
        target = self.residents.get(action.target)
        redundant = ((kind == "repair" and self.hull_event) or (kind == "survey" and self.route_event)
                     or (kind == "archive" and skill in self.archive)
                     or (kind == "teach" and skill in target.skills)
                     or ((kind == "study" or kind.startswith("practice_")) and skill in actor.skills))
        if redundant:
            event = self.emit("duplicate_work", resident=key, action=action.id)
            return ActionOutcome(action.id, "conflict", (event,))
        if kind in WORKSHOP:
            if len(workers) >= 2:
                event = self.emit("workshop_denied", resident=key, action=action.id, reserved=self.reservations,
                                  admitted=tuple(workers))
                return ActionOutcome(action.id, "conflict", (event,))
            workers.append(key)
        if kind.startswith("practice_"):
            attempts = actor.practice.get(skill, 0) + 1
            actor.practice[skill] = attempts
            event = self.emit("practiced", resident=key, skill=skill, attempts=attempts)
            if attempts == 2:
                actor.skills.setdefault(skill, event)
        elif kind == "teach":
            event = self.emit("taught", refs=(actor.skills[skill],), teacher=key, target=action.target, skill=skill)
            target.skills[skill] = event
        elif kind == "archive":
            event = self.emit("archived", refs=(actor.skills[skill],), resident=key, skill=skill)
            self.archive[skill] = event
        elif kind == "study":
            event = self.emit("studied", refs=(self.archive[skill],), resident=key, skill=skill)
            actor.skills.setdefault(skill, event)
        elif kind == "repair":
            event = self.hull_event = self.emit("repaired", refs=(actor.skills["carpentry"],), resident=key)
        elif kind == "survey":
            event = self.route_event = self.emit("surveyed", refs=(actor.skills["navigation"],), resident=key)
        elif kind in SHELTER_ACTIONS:
            offered = (key, action.target) if kind == "deliver" else (action.target,)
            recipients = [person for person in offered if person not in self.sheltered]
            if not recipients:
                event = self.emit("duplicate_work", resident=key, action=action.id)
                return ActionOutcome(action.id, "conflict", (event,))
            event = self.emit("protected", resident=key, target=action.target, recipients=recipients, method=kind)
            self.sheltered.update(dict.fromkeys(recipients, event))
        else:
            data = {"proposal": action.target} if kind == "support" else {}
            event = self.emit(kind, resident=key, **data)
        return ActionOutcome(action.id, "waited" if kind == "wait" else "applied", (event,))

    def review_pledges(self, turns: dict[str, Turn], chosen: dict[str, Action], outcomes: dict[str, ActionOutcome]) -> None:
        for key, (action_id, pledge) in self.pledges.items():
            result = outcomes.get(key)
            refs = (pledge, *result.event_ids) if result else (pledge,)
            if key not in turns or not turns[key].action_for(Decision(action_id)):
                kind = "blocked_pledge"
                cause = "no_legal_opportunity"
            elif key not in chosen:
                kind = "blocked_pledge"
                cause = "invalid_decision"
            elif result.action_id != action_id:
                kind = "broke_pledge"
                cause = "chose_other_action"
            elif result.status == "conflict":
                kind = "blocked_pledge"
                cause = "attempt_conflicted"
            else:
                kind = "kept_pledge"
                cause = "completed"
            self.emit(kind, refs=refs, resident=key, action=action_id, cause=cause)
        self.pledges.clear()

    def resolve_proposals(self, chosen: dict[str, Action]) -> None:
        self.reservations = ()
        if not self.proposals:
            return
        support = {proposal: [key for key, action in chosen.items() if action.target == proposal
                              and action.kind == "support"] for proposal in self.proposals}
        guards = [key for key, action in chosen.items() if action.kind == "guard"]
        winner = max(support, key=lambda proposal: len(support[proposal]))
        other_votes = [len(guards), 1, *(len(voters) for proposal, voters in support.items() if proposal != winner)]
        if len(support[winner]) > max(other_votes):
            self.reservations = self.proposals[winner]
            self.emit("took_workshop", refs=(winner,), supporters=support[winner], guards=guards,
                      reserved=self.reservations, reserved_year=self.year + 1)
        else:
            self.emit("kept_workshop_open", refs=support, votes=support, guards=guards)
        self.proposals.clear()

    def post_notices(self, turns: dict[str, Turn], decisions: dict[str, Decision], chosen: dict[str, Action]) -> None:
        for key in chosen:
            decision = decisions[key]
            if decision.message.strip():
                self.emit("message", resident=key, text=decision.message.strip()[:140])
            if not isinstance(decision, IslandDecision):
                continue
            if decision.pledge:
                if decision.pledge in self.pledge_options(turns[key].actions):
                    event = self.emit("pledged", resident=key, action=decision.pledge, due_year=self.year + 1)
                    self.pledges[key] = (decision.pledge, event)
                else:
                    self.emit("invalid_notice", resident=key, field="pledge", value=decision.pledge)
            if decision.nominees:
                nominees = decision.nominees
                if (self.year < CONTACT_YEAR - 2 and len(set(nominees)) == 2 and len(nominees) == 2
                        and all(person in self.adults() for person in nominees)):
                    event = self.emit("proposed_workshop", resident=key, nominees=nominees)
                    self.proposals[event] = nominees
                else:
                    self.emit("invalid_notice", resident=key, field="nominees", value=nominees)

    def resolve_storm(self) -> None:
        storm = self.emit("storm", refs=tuple(filter(None, (self.hull_event,))),
                          hull_damaged=bool(self.hull_event), sheltered=list(self.sheltered))
        self.hull_event = ""
        for key, resident in self.present().items():
            if key in self.sheltered:
                continue
            resident.health -= 1
            damage = self.emit("storm_injury", refs=(storm,), resident=key, health=resident.health)
            if resident.health == 0:
                resident.status = "lost_to_storm"
                self.emit("departed", refs=(damage,), resident=key, cause="storm")
        self.sheltered.clear()

    def finish(self, policy: Policy | AgentHarness) -> dict:
        if self.year != CONTACT_YEAR or self.ending is not None:
            raise ValueError("The finale requires eighteen completed years and can run once.")
        harness = AgentHarness.wrap(policy)
        arrival = self.emit("topaz_arrived")
        volunteers = self.finale_phase(harness, "contact", arrival)
        representative = next((key for key in self.order() if key in volunteers), None)
        leaving = []
        if representative is not None:
            resident = self.residents[representative]
            contact = self.emit("made_contact", refs=(arrival, self.hull_event, self.route_event,
                                                      resident.skills["navigation"], volunteers[representative]),
                                resident=representative)
            leaving = list(self.finale_phase(harness, "departure", contact))
            for key in leaving:
                self.residents[key].status = "left_on_topaz"
        self.ending = {"representative": representative, "left": leaving, "stayed": list(self.present()),
                       "boat_ready": self.boat_ready,
                       "skills_remaining": sorted({skill for adult in self.adults().values() for skill in adult.skills}),
                       "archive_skills": sorted(self.archive)}
        return self.ending

    def finale_phase(self, harness: AgentHarness, phase: str, trigger: str) -> dict[str, str]:
        turns, decisions, chosen = self.collect(harness, phase)
        outcomes, volunteers = {}, {}
        for key in turns:
            action = chosen.get(key)
            action_id = action.id if action else ("wait" if phase == "contact" else "stay")
            event = self.emit("finale_choice", refs=(trigger,), resident=key, phase=phase, action=action_id,
                              valid=action is not None)
            outcomes[key] = ActionOutcome(action_id, "applied" if action else "fallback", (event,))
            if action_id in {"contact", "leave"}:
                volunteers[key] = event
            if action and decisions[key].message.strip():
                self.emit("message", refs=(event,), resident=key, text=decisions[key].message.strip()[:140])
        harness.settle(outcomes)
        return volunteers
