"""One night and the first day of 12-player Seer, Witch, Hunter, Fool Werewolf."""

import argparse
import json
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from random import Random
from time import perf_counter

from agents import Action, ActionOutcome, AgentHarness, Decision, Policy, Turn
from decisions import ModelUnavailable, OllamaPolicy


DECK = ("wolf",) * 4 + ("villager",) * 4 + ("seer", "witch", "hunter", "fool")
GODS = {"seer", "witch", "hunter", "fool"}
PHASES = ("night", "candidacy", "speech", "vote")
PROMPT = """Play only the seat on this Werewolf card. Win for your faction.
Read the current step, private information, public events and legal actions. Public speech is a player's
claim. A claim can be true, mistaken, or a bluff. Judge it against the evidence you actually have.
Choose exactly one action ID. When invited to speak, use message for a short in-character statement
in English of at most 200 characters, naming seats where helpful. At other steps leave message empty. Give the observer a brief
reason in English. The reason is never shown to players. Use only the information on your card."""

RULES = (
    "The deck has 4 wolves, 4 villagers, a seer, a witch, a hunter and a fool. "
    "Town wins when all wolves are out. Wolves win by removing all villagers or all special town roles. "
    "The sheriff has a 1.5 vote in exile and speaks last in the normal day discussion. "
    "Only players who stayed off the initial sheriff ballot can elect the sheriff. "
    "An exile tie gets one runoff. A revealed fool can speak but cannot vote. "
    "The first wolf reveal during the election defers the election and ends day voting."
)

ROLE_RULES = {
    "wolf": "You know your pack. Coordinate privately at night and deceive the town if useful. "
            "A legal self-reveal eliminates you and ends the day without an exile ballot.",
    "villager": "You have no night power. Judge claims and votes.",
    "seer": "Check a seat at night. The result tells you town or wolf, never the exact role.",
    "witch": "You have one antidote and one poison. Use at most one tonight. You cannot save yourself.",
    "hunter": "If killed by wolves or exiled, you can shoot a living player unless you are the last special "
              "town role. Poison prevents the shot.",
    "fool": "The first exile reveals your role and leaves you alive, but you lose your vote. "
            "The immunity only applies to exile. If you held the badge, it is discarded.",
}


@dataclass
class Player:
    role: str
    alive: bool = True
    revealed: bool = False

    @property
    def can_vote(self) -> bool:
        return self.alive and not (self.revealed and self.role == "fool")


@dataclass(frozen=True)
class Event:
    id: str
    phase: str
    step: str
    kind: str
    data: dict
    audience: tuple[str, ...] | None = None

    def visible_to(self, seat: str) -> bool:
        return self.audience is None or seat in self.audience

    def observation(self) -> dict:
        return {"id": self.id, "step": self.step, "kind": self.kind, **self.data}


def option(action_id: str, label: str, *, target: str = "") -> Action:
    return Action(action_id, label, 0, action_id, target=target)


PASS = option("pass", "Decline or abstain")
SPEAK = option("speak", "Make your statement")
EXPLODE = option("explode", "Reveal as a wolf, leave play, and immediately end ordinary daytime play")


class Werewolf:
    def __init__(self, seed: int):
        self.rng = Random(seed)
        deck = list(DECK)
        self.rng.shuffle(deck)
        self.players = {f"P{number:02}": Player(role) for number, role in enumerate(deck, 1)}
        self.events: list[Event] = []
        self.phase = self.step = ""
        self.sheriff: str | None = None
        self.badge_pending = False
        self.antidote = self.poison = True
        self.night_deaths: dict[str, str] = {}
        self.wolf_target: str | None = None
        self.exile_target: str | None = None
        self.exploded: str | None = None
        self.winner: str | None = None
        self.status = "running"

    @property
    def living(self) -> list[str]:
        return [seat for seat, player in self.players.items() if player.alive]

    def role_seat(self, role: str) -> str:
        return next(seat for seat, player in self.players.items() if player.role == role)

    def emit(self, kind: str, *, audience: tuple[str, ...] | None = None, **data) -> Event:
        event = Event(f"E{len(self.events) + 1:03}", self.phase, self.step, kind, data, audience)
        self.events.append(event)
        return event

    def enter(self, phase: str, step: str) -> None:
        self.phase = phase
        self.step = step
        self.emit("phase")

    def observe(self, seat: str, actions: tuple[Action, ...], instruction: str) -> Turn:
        player = self.players[seat]
        private = [event.observation() for event in self.events
                   if event.audience is not None and event.visible_to(seat)]
        card = {
            "seat": seat,
            "role": player.role,
            "faction": "wolves" if player.role == "wolf" else "town",
            "role_rules": ROLE_RULES[player.role],
            "rules": RULES,
            "phase": self.phase,
            "step": self.step,
            "task": instruction,
            "living_seats": self.living,
            "sheriff": self.sheriff,
            "private_information": private,
            "public_events": [event.observation() for event in self.events if event.audience is None],
            "legal_actions": {action.id: action.label for action in actions},
        }
        return Turn(seat, json.dumps(card, ensure_ascii=False, separators=(",", ":")),
                    actions, PHASES.index(self.phase) + 1)

    def ask(self, harness: AgentHarness, choices: Mapping[str, tuple[Action, ...]],
            instruction: str, *, fallback: Action = PASS) -> dict[str, tuple[Action, Decision]]:
        turns = [self.observe(seat, actions, instruction) for seat, actions in choices.items()]
        decisions = harness.collect(turns)
        selected = {}
        outcomes = {}
        for turn in turns:
            seat = turn.resident_id
            decision = decisions[seat]
            action = turn.action_for(decision)
            selected[seat] = (action, decision) if action else (fallback, Decision(fallback.id))
            chosen = selected[seat][0]
            event = self.emit("selection", audience=(), seat=seat, action=chosen.id,
                              submitted=decision.action_id, target=chosen.target or None)
            outcomes[seat] = ActionOutcome(chosen.id, "accepted" if action else "fallback", (event.id,))
        harness.settle(outcomes)
        return selected

    def ask_one(self, harness: AgentHarness, seat: str, actions: tuple[Action, ...],
                instruction: str, *, fallback: Action = PASS) -> tuple[Action, Decision]:
        return self.ask(harness, {seat: actions}, instruction, fallback=fallback)[seat]

    def targets(self, prefix: str, label: str, seats: list[str]) -> tuple[Action, ...]:
        return (PASS, *(option(f"{prefix}_{seat}", f"{label} {seat}", target=seat) for seat in seats))

    def run(self, decide: Policy | AgentHarness, on_phase: Callable[[str], None] | None = None) -> None:
        if self.phase:
            raise ValueError("This first-day scenario has already started.")
        harness = AgentHarness.wrap(decide)
        stages = (self.resolve_night, self.elect_sheriff, self.discuss, self.exile)
        for phase, stage in zip(PHASES, stages):
            if self.exploded or self.winner:
                break
            if on_phase:
                on_phase(phase)
            stage(harness)
        self.status = "win" if self.winner else "day_ended_by_reveal" if self.exploded else "day_complete"
        self.emit("scenario_end", status=self.status, winner=self.winner)

    def resolve_night(self, harness: AgentHarness) -> None:
        self.enter("night", "wolf_discussion")
        wolves = tuple(seat for seat in self.living if self.players[seat].role == "wolf")
        self.emit("pack", audience=wolves, seats=list(wolves))
        for seat in wolves:
            action, decision = self.ask_one(harness, seat, (PASS, SPEAK),
                                            "Discuss the night target privately with your pack.")
            if action.id == "speak":
                self.emit("wolf_speech", audience=wolves, seat=seat, message=decision.message.strip()[:220])
        self.step = "wolf_ballot"
        leaders = self.ballot(harness, list(wolves), self.living, audience=wolves)
        self.wolf_target = self.rng.choice(leaders) if leaders else None
        self.emit("wolf_target", audience=wolves, target=self.wolf_target)

        self.step = "witch"
        witch = self.role_seat("witch")
        self.emit("witch_information", audience=(witch,), wolf_target=self.wolf_target,
                  antidote=self.antidote, poison=self.poison)
        choices = self.targets("poison", "Poison", [seat for seat in self.living if seat != witch])
        if self.wolf_target and self.wolf_target != witch:
            choices += (option("save", f"Save the wolf target {self.wolf_target}", target=self.wolf_target),)
        action, _ = self.ask_one(harness, witch, choices, "Choose at most one potion.")
        self.antidote = action.id != "save"
        if self.wolf_target and self.antidote:
            self.night_deaths[self.wolf_target] = "wolves"
        if action.id.startswith("poison_"):
            self.poison = False
            self.night_deaths[action.target] = "poison"
        self.emit("potion", audience=(witch,), action=action.id, target=action.target or None)

        self.step = "seer"
        seer = self.role_seat("seer")
        checks = self.targets("check", "Check the faction of", [seat for seat in self.living if seat != seer])[1:]
        action, _ = self.ask_one(harness, seer, checks, "Check one other seat.", fallback=checks[0])
        faction = "wolves" if self.players[action.target].role == "wolf" else "town"
        self.emit("check_result", audience=(seer,), target=action.target, faction=faction)
        hunter = self.role_seat("hunter")
        self.emit("hunter_status", audience=(hunter,), may_shoot=self.night_deaths.get(hunter) != "poison")
        self.emit("night_resolution", audience=(), deaths=self.night_deaths.copy())

    def ballot(self, harness: AgentHarness, voters: list[str], targets: list[str], *,
               audience: tuple[str, ...] | None = None, weighted: bool = False) -> list[str]:
        wolves_only = self.step == "wolf_ballot"
        choices = {}
        for voter in voters:
            valid = targets if wolves_only else [target for target in targets if target != voter]
            choices[voter] = self.targets("vote", "Vote for", valid)
        if wolves_only:
            instruction = "Choose the pack's night target. Only the wolves will see the votes."
        elif weighted:
            instruction = "Vote to exile a living seat. Votes are revealed together after all voters decide."
        else:
            instruction = "Vote for sheriff. Votes are revealed together after all voters decide."
        ballots = self.ask(harness, choices, instruction)
        tally: Counter[str] = Counter()
        public_ballots = {}
        for voter, (action, _) in ballots.items():
            weight = 3 if weighted and voter == self.sheriff else 2
            public_ballots[voter] = {"target": action.target or None, "weight": weight / 2}
            if action.target:
                tally[action.target] += weight
        high = max(tally.values(), default=0)
        leaders = sorted(seat for seat, score in tally.items() if score == high)
        self.emit("ballot", audience=audience, ballots=public_ballots,
                  totals={seat: score / 2 for seat, score in tally.items()}, leaders=leaders)
        return leaders

    def elect_sheriff(self, harness: AgentHarness) -> None:
        self.enter("candidacy", "registration")
        run = option("run", "Run for sheriff")
        registration = self.ask(harness, {seat: (PASS, run) for seat in self.living},
                                "Decide whether to run for sheriff before the first-night deaths are announced.")
        candidates = [seat for seat, (action, _) in registration.items() if action.id == "run"]
        voters = [seat for seat in self.living if seat not in candidates]
        self.emit("candidates", seats=candidates.copy())
        self.step = "campaign_speech"
        self.speeches(harness, candidates, "Give your sheriff campaign speech or withdraw.", withdrawal=candidates)
        if not self.exploded and candidates:
            self.step = "withdrawal"
            withdrawals = self.ask(harness, {seat: (PASS, option("withdraw", "Withdraw your candidacy"))
                                             for seat in candidates}, "Stay in the race or withdraw.")
            for seat, (action, _) in withdrawals.items():
                if action.id == "withdraw":
                    candidates.remove(seat)
                    self.emit("withdrawal", seat=seat)
            if not self.reveal_window(harness):
                self.sheriff = self.election_result(harness, candidates, voters)
        self.step = "sheriff_result"
        if self.exploded:
            self.badge_pending = True
        self.emit("sheriff_result", seat=self.sheriff, deferred=self.badge_pending)
        self.announce_dawn(harness)

    def election_result(self, harness: AgentHarness, candidates: list[str], voters: list[str]) -> str | None:
        if len(candidates) < 2:
            return candidates[0] if candidates else None
        self.step = "sheriff_ballot"
        leaders = self.ballot(harness, voters, candidates)
        if len(leaders) > 1:
            self.step = "sheriff_runoff_speech"
            self.speeches(harness, leaders, "Make your sheriff runoff case.")
            if self.exploded or self.reveal_window(harness):
                return None
            self.step = "sheriff_runoff_ballot"
            leaders = self.ballot(harness, voters, leaders)
        return leaders[0] if len(leaders) == 1 else None

    def reveal_window(self, harness: AgentHarness) -> bool:
        wolves = [seat for seat in self.living if self.players[seat].role == "wolf"]
        choice = self.ask(harness, {seat: (PASS, EXPLODE) for seat in wolves},
                          "Consider whether giving up your own seat to cancel this ballot benefits the pack. "
                          "You may self-reveal now or let play continue.")
        for seat, (action, _) in choice.items():
            if action.id == "explode":
                self.explode(seat)
                return True
        return False

    def explode(self, seat: str) -> None:
        self.players[seat].alive = False
        self.players[seat].revealed = True
        self.exploded = seat
        self.emit("wolf_reveal", seat=seat, role="wolf")

    def speeches(self, harness: AgentHarness, seats: list[str], instruction: str, *,
                 withdrawal: list[str] | None = None, allow_explode: bool = True) -> None:
        for seat in tuple(seats):
            options = (PASS, SPEAK)
            if withdrawal is not None:
                options += (option("withdraw", "Withdraw from the sheriff race"),)
            if allow_explode and self.players[seat].alive and self.players[seat].role == "wolf":
                options += (EXPLODE,)
            action, decision = self.ask_one(harness, seat, options, instruction)
            if action.id == "explode":
                self.explode(seat)
                return
            if action.id == "withdraw":
                if withdrawal is not None:
                    withdrawal.remove(seat)
                self.emit("withdrawal", seat=seat)
            self.emit("speech", seat=seat, message=decision.message.strip()[:200] if action.id == "speak" else "")

    def announce_dawn(self, harness: AgentHarness) -> None:
        self.step = "dawn"
        dead = [seat for seat in self.night_deaths if self.players[seat].alive]
        for seat in dead:
            self.players[seat].alive = False
        self.emit("dawn", dead=dead.copy())
        for seat in tuple(dead):
            shot = self.hunter_shot(harness, seat, self.night_deaths[seat])
            if shot:
                dead.append(shot)
        self.transfer_badge(harness)
        self.step = "first_night_last_words"
        self.speeches(harness, dead, "Give your first-night last words.", allow_explode=False)
        self.check_winner()

    def discuss(self, harness: AgentHarness) -> None:
        self.enter("speech", "speech_order")
        seats = self.living
        if self.sheriff:
            clockwise = option("clockwise", "Speak clockwise around the sheriff, who speaks last")
            reverse = option("counterclockwise", "Speak counterclockwise around the sheriff, who speaks last")
            action, _ = self.ask_one(harness, self.sheriff, (clockwise, reverse),
                                     "Choose the discussion order.", fallback=clockwise)
            pivot = seats.index(self.sheriff)
            ring = seats[pivot + 1:] + seats[:pivot]
            seats = (ring if action.id == "clockwise" else ring[::-1]) + [self.sheriff]
        self.emit("speech_order", seats=seats)
        self.step = "day_speech"
        self.speeches(harness, seats, "Give your view on the evidence and who should be exiled.")
        if self.exploded:
            self.transfer_badge(harness)
            self.check_winner()

    def exile(self, harness: AgentHarness) -> None:
        self.enter("vote", "before_exile")
        if self.reveal_window(harness):
            self.transfer_badge(harness)
            self.check_winner()
            return
        self.step = "exile_ballot"
        voters = [seat for seat in self.living if self.players[seat].can_vote]
        candidates = [seat for seat in self.living if self.players[seat].can_vote]
        leaders = self.ballot(harness, voters, candidates, weighted=True)
        if len(leaders) > 1:
            self.step = "exile_runoff_speech"
            self.speeches(harness, leaders, "Respond to the exile tie.", allow_explode=False)
            self.step = "exile_runoff_ballot"
            leaders = self.ballot(harness, [seat for seat in voters if seat not in leaders], leaders, weighted=True)
        self.step = "exile_result"
        self.exile_target = leaders[0] if len(leaders) == 1 else None
        self.emit("exile_result", seat=self.exile_target)
        if self.exile_target:
            self.resolve_exile(harness, self.exile_target)
        self.check_winner()

    def resolve_exile(self, harness: AgentHarness, seat: str) -> None:
        player = self.players[seat]
        if player.role == "fool" and not player.revealed:
            player.revealed = True
            self.emit("fool_reveal", seat=seat, role="fool")
            if self.sheriff == seat:
                self.sheriff = None
                self.emit("badge", previous=seat, seat=None)
            return
        player.alive = False
        self.emit("death", seat=seat)
        shot = self.hunter_shot(harness, seat, "exile")
        self.transfer_badge(harness)
        self.step = "exile_last_words"
        self.speeches(harness, [seat, shot] if shot else [seat], "Give your last words.", allow_explode=False)

    def hunter_shot(self, harness: AgentHarness, seat: str, cause: str) -> str | None:
        if self.players[seat].role != "hunter" or cause not in {"wolves", "exile"}:
            return None
        if not any(self.players[living].role in GODS for living in self.living):
            return None
        previous = self.step
        self.step = "hunter"
        action, _ = self.ask_one(harness, seat, self.targets("shoot", "Shoot", self.living),
                                 "You may use your final hunter shot or pass.")
        if action.target:
            self.players[seat].revealed = True
            self.players[action.target].alive = False
            self.emit("hunter_shot", seat=seat, role="hunter", target=action.target)
        self.step = previous
        return action.target or None

    def transfer_badge(self, harness: AgentHarness) -> None:
        if self.sheriff and not self.players[self.sheriff].alive:
            old = self.sheriff
            previous = self.step
            self.step = "badge_transfer"
            targets = [seat for seat in self.living if self.players[seat].can_vote]
            action, _ = self.ask_one(harness, old, self.targets("pass_badge", "Pass the badge to", targets),
                                     "Pass the sheriff badge to an eligible living seat or discard it.")
            self.sheriff = action.target or None
            self.emit("badge", previous=old, seat=self.sheriff)
            self.step = previous

    def check_winner(self) -> None:
        roles = {self.players[seat].role for seat in self.living}
        if "wolf" not in roles:
            self.winner = "town"
        elif "villager" not in roles or not roles & GODS:
            self.winner = "wolves"

    def summary(self) -> dict:
        return {"status": self.status, "winner": self.winner, "sheriff": self.sheriff,
                "badge_pending": self.badge_pending, "exile_target": self.exile_target,
                "wolf_reveal": self.exploded, "living": self.living,
                "players": {key: asdict(player) for key, player in self.players.items()}}


class DemoPolicy:
    """Exercises the opening as a rules and logging check."""

    def __call__(self, turn: Turn) -> Decision:
        card = json.loads(turn.card)
        step, role = card["step"], card["role"]
        actions = {action.id for action in turn.actions}
        if step == "registration" and role == "seer":
            return Decision("run")
        if step == "witch" and "save" in actions:
            return Decision("save")
        if step in {"wolf_ballot", "seer", "exile_ballot", "exile_runoff_ballot"}:
            return Decision(next((action.id for action in turn.actions if action.target), "pass"))
        if "speak" in actions:
            return Decision("speak", message="I am weighing the available votes and claims.")
        return Decision("clockwise" if "clockwise" in actions else "pass")


def main() -> int:
    parser = argparse.ArgumentParser(description="12 人狼人杀 · 首夜与首日")
    parser.add_argument("--backend", choices=("ollama", "scripted"), default="ollama")
    parser.add_argument("--model", help="覆盖当前模式的默认模型。")
    parser.add_argument("--think", action="store_true", help="开启 Ollama 模型的推理模式。")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--log", type=Path, default=Path("werewolf_day1.json"))
    args = parser.parse_args()
    game = Werewolf(args.seed)
    policy = OllamaPolicy(args.model, think=args.think, seed=args.seed, prompt=PROMPT) if args.backend == "ollama" else None
    harness = AgentHarness(policy or DemoPolicy())
    started = perf_counter()
    failed = False
    try:
        labels = {"night": "首夜", "candidacy": "警长竞选", "speech": "白天发言", "vote": "放逐投票"}
        game.run(harness, on_phase=lambda phase: print(labels[phase], flush=True))
    except (ModelUnavailable, KeyboardInterrupt) as error:
        game.status = "interrupted"
        print(str(error) or "运行中止。", flush=True)
        failed = True
    finally:
        report = {"scenario": "werewolf12_day1", "seed": args.seed, "backend": args.backend,
                  "model": policy.model if policy else None, "think": policy.think if policy else None,
                  "agent_instructions": policy.prompt if policy else None,
                  "seconds": round(perf_counter() - started, 3), "model_stats": asdict(policy.stats) if policy else {},
                  "summary": game.summary(), "events": [asdict(event) for event in game.events],
                  "decision_trace": harness.export()}
        args.log.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"结果 {game.status} ｜ 警长 {game.sheriff or '无'} ｜ 放逐目标 {game.exile_target or '无'} "
          f"｜ 用时 {report['seconds']} 秒")
    print(f"复盘日志 {args.log.resolve()}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
