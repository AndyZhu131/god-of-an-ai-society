"""An equal-start settlement where repair methods can outlive their discoverers."""

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from random import Random
from time import perf_counter

from agents import Action, ActionOutcome, AgentHarness, Policy, Turn
from decisions import DEFAULT_MODEL, ModelUnavailable, OllamaPolicy


PROMPT = """You are the resident on the state card. Pick one legal action for this round.
Your goal is to earn credit by repairing devices or sharing methods that others actually use.
Use the rules and records on your card as facts. Board posts are residents' claims.
You may attach one short English sentence to ask, answer, or coordinate on the public board.
Leave message empty if you have nothing to tell others. Give a brief English reason for your action."""

FAMILIES = ("Arc", "Bloom", "Crest", "Dune", "Ember", "Flint", "Grove", "Halo")
SETTINGS = ("triangle", "circle", "square", "star", "wave", "spiral")
RETIRE_ROUND = 7
WAIT = Action("wait", "Wait this round", 0, "wait")


@dataclass(frozen=True)
class Method:
    family: str
    setting: str
    discovered_by: str
    trial: str


@dataclass(frozen=True)
class Note:
    id: str
    author: str
    method: Method
    recipient: str = ""
    parent: str = ""


@dataclass
class Resident:
    jobs: tuple[str, ...]
    newcomer: bool = False
    repairs: int = 0
    credit: int = 0
    attempted: set[str] = field(default_factory=set)
    methods: dict[str, tuple[Method, str]] = field(default_factory=dict)
    inbox: set[str] = field(default_factory=set)
    shared: set[tuple[str, str]] = field(default_factory=set)

    @property
    def family(self) -> str:
        return self.jobs[self.repairs]


class Archive:
    def __init__(self, population: int, seed: int, rounds: int = 12):
        rng = Random(seed)
        self.answers = {family: rng.choice(SETTINGS) for family in FAMILIES}
        families = list(FAMILIES)
        rng.shuffle(families)
        self.residents = {f"P{i + 1:02}": self.new_resident(families[i % len(families)], rng, rounds)
                          for i in range(population)}
        self.departures = sorted(rng.sample(list(self.residents), max(1, population // 5)))
        self.arrivals = {f"P{i + population + 1:02}": self.new_resident(
            self.residents[old].family, rng, rounds, newcomer=True) for i, old in enumerate(self.departures)}
        self.retired: set[str] = set()
        self.notes: dict[str, Note] = {}
        self.public: dict[str, str] = {}
        self.credited: set[tuple[str, str]] = set()
        self.board: list[dict] = []
        self.round = 1
        self.rounds = rounds

    @staticmethod
    def new_resident(first: str, rng: Random, rounds: int, *, newcomer=False) -> Resident:
        other_families = [family for family in FAMILIES if family != first]
        queue = [first, *rng.sample(other_families, len(other_families))]
        return Resident(tuple(queue[i % len(queue)] for i in range(rounds + 1)), newcomer)

    def snapshot(self, key: str, *, roster: dict[str, Resident] | None = None) -> Turn:
        if roster is None:
            roster = self.residents
        actor = roster[key]
        peers = {other: resident.family for other, resident in roster.items() if other != key}
        actions = [WAIT]
        known = actor.methods.get(actor.family)
        for setting in SETTINGS:
            if setting not in actor.attempted:
                actions.append(Action(f"try_{setting}", f"Try the {setting} setting on your device",
                                      1, "test", step=setting))
        visible = set(self.public.values()) | actor.inbox
        uses = [self.notes[note_id] for note_id in sorted(visible)
                if self.notes[note_id].method.family == actor.family]
        for note in uses:
            actions.append(Action(f"use_{note.id}", f"Use {note.author}'s note {note.id} to repair this "
                                  f"{actor.family} device with {note.method.setting}",
                                  1, "use", record=note.id))
        if known:
            method, _ = known
            actions.append(Action("use_memory", f"Repair using the {method.setting} setting you already know",
                                  1, "memory", step=method.setting))
        for family, (method, _) in sorted(actor.methods.items()):
            if family in self.public:
                continue
            name = family.lower()
            actions.append(Action(f"archive_{name}", f"Publish the working {family} method ({method.setting})",
                                  1, "archive", step=family))
            for other, current_job in peers.items():
                if current_job == family and (family, other) not in actor.shared:
                    actions.append(Action(f"teach_{name}_{other}", f"Privately teach {other} the working "
                                          f"{family} method for their current device", 1, "teach",
                                          target=other, step=family))
        card = {
            "resident": key, "round": self.round, "rounds_left_including_this_one": self.rounds - self.round + 1,
            "credit": actor.credit, "current_device_family": actor.family, "failed_settings": sorted(actor.attempted),
            "known_methods": {name: method.setting for name, (method, _) in actor.methods.items()},
            "other_workshops_current_devices": peers,
            "notes_for_your_current_device": [{"id": note.id, "author": note.author,
                                                "author_has_left": note.author not in roster,
                                                "setting": note.method.setting} for note in uses],
            "recent_board_posts": self.board[-6:],
            "rules": [
                "All workshops have the same abilities. Devices with the same family share a working setting.",
                "Each action takes a full round. A successful repair earns you 1 credit and brings a new device next round.",
                "A successful trial gives you a verified method to publish or teach. Publishing makes a durable public note. "
                "Teaching sends a private note to one workshop that can use it on its current device.",
                "When another resident first repairs using your note, you earn 1 credit. Agents may pursue credit by either route.",
                "Everyone acts on the start-of-round state. Notes and board posts are visible from the next round.",
            ],
            "legal_actions": {action.id: action.label for action in actions},
        }
        return Turn(key, json.dumps(card, ensure_ascii=False, separators=(",", ":")), tuple(actions), self.round)

    def advance(self, decide: Policy | AgentHarness) -> dict:
        roster = self.residents
        turnover = {}
        if self.round == RETIRE_ROUND:
            roster = {key: actor for key, actor in self.residents.items() if key not in self.departures}
            roster.update(self.arrivals)
            turnover = {"departures": self.departures, "arrivals": list(self.arrivals)}
        turns = [self.snapshot(key, roster=roster) for key in roster]
        harness = AgentHarness.wrap(decide)
        decisions = harness.collect(turns)
        if turnover:
            self.residents = roster
            self.retired.update(self.departures)
        events = []
        choices = Counter()
        posts = []
        outcomes = {}
        for turn in turns:
            key = turn.resident_id
            decision = decisions[key]
            submitted = turn.action_for(decision)
            action = submitted or WAIT
            choices[action.kind] += 1
            status = "fallback" if submitted is None else "waited"
            event = None
            if action.kind in {"test", "use", "memory"}:
                event = self.test(key, action)
                status = "applied" if event["success"] else "failed"
            elif action.kind in {"archive", "teach"}:
                event = self.share(key, action)
                status = "conflict" if event["kind"] == "duplicate_archive" else "applied"
            posted = submitted is not None and bool(decision.message.strip())
            if posted:
                posts.append({"resident": key, "round": self.round, "message": decision.message.strip()[:140]})
            if event is not None:
                events.append(event)
            event_ids = ()
            if event is not None:
                reference = event["existing_note"] if status == "conflict" else event["id"]
                event_ids = (reference,)
            outcomes[key] = ActionOutcome(action.id, status, event_ids, {"posted": posted})
        self.board.extend(posts)
        harness.settle(outcomes)
        result = {"round": self.round, "turnover": turnover, "actions": dict(choices),
                  "decisions": {key: asdict(choice) for key, choice in decisions.items()},
                  "events": events, "posts": posts,
                  "scores": {key: resident.credit for key, resident in self.residents.items()}}
        self.round += 1
        return result

    def test(self, key: str, action: Action) -> dict:
        actor = self.residents[key]
        family = actor.family
        note = self.notes.get(action.record)
        setting = note.method.setting if note else action.step
        trial = f"{key}-{actor.repairs + 1}-{self.round}"
        result = {"kind": "trial", "id": trial, "resident": key, "family": family, "setting": setting,
                  "success": setting == self.answers[family], "newcomer": actor.newcomer}
        if note:
            result.update(note=note.id, note_author=note.author, discovered_by=note.method.discovered_by,
                          original_trial=note.method.trial, author_retired=note.author in self.retired,
                          discoverer_retired=note.method.discovered_by in self.retired)
        if not result["success"]:
            actor.attempted.add(setting)
            return result
        actor.repairs += 1
        actor.credit += 1
        actor.attempted.clear()
        if note:
            actor.methods.setdefault(family, (note.method, note.id))
            credit_key = (note.id, key)
            if credit_key not in self.credited and key != note.author:
                self.credited.add(credit_key)
                if note.author in self.residents:
                    self.residents[note.author].credit += 1
        else:
            actor.methods.setdefault(family, (Method(family, setting, key, trial), ""))
        return result

    def share(self, key: str, action: Action) -> dict:
        actor = self.residents[key]
        method, parent = actor.methods[action.step]
        if action.kind == "archive" and method.family in self.public:
            return {"kind": "duplicate_archive", "resident": key,
                    "family": method.family, "existing_note": self.public[method.family]}
        note = Note(f"N{len(self.notes) + 1:03d}", key, method, action.target, parent)
        self.notes[note.id] = note
        if action.target:
            actor.shared.add((method.family, action.target))
            self.residents[action.target].inbox.add(note.id)
        else:
            self.public[method.family] = note.id
        return {"kind": action.kind, **asdict(note)}


def main() -> int:
    parser = argparse.ArgumentParser(description="接力档案馆 · 本地社会模拟")
    parser.add_argument("--residents", type=int, default=20)
    parser.add_argument("--rounds", type=int, default=12)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()
    if args.residents < 2 or args.rounds < 1:
        parser.error("至少需要两名居民和一轮。")
    archive = Archive(args.residents, args.seed, args.rounds)
    policy = OllamaPolicy(args.model, seed=args.seed, prompt=PROMPT)
    harness = AgentHarness(policy, record=args.log is not None)
    rounds = []
    for _ in range(args.rounds):
        started = perf_counter()
        print(f"第 {archive.round} 轮 · {args.residents} 名居民 · {args.model}", flush=True)
        try:
            result = archive.advance(harness)
        except ModelUnavailable as error:
            parser.exit(1, f"{error}\n")
        result["seconds"] = round(perf_counter() - started, 3)
        rounds.append(result)
        if args.log:
            report = {"model": args.model, "seed": args.seed, "population": args.residents,
                      "stats": asdict(policy.stats), "rounds": rounds,
                      "agent_instructions": policy.prompt, "decision_trace": harness.export()}
            args.log.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        print(f"  {result['actions']} · {result['seconds']} 秒", flush=True)
    print(json.dumps(asdict(policy.stats)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
