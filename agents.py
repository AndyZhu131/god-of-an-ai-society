"""Shared contracts and harness for residents that act on a frozen observation."""

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from time import perf_counter
from unicodedata import name


def has_non_latin_letters(text: str) -> bool:
    return any(char.isalpha() and not char.isascii() and not name(char, "").startswith("LATIN ")
               for char in text)


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    cost: int
    kind: str
    target: str = ""
    record: str = ""
    record_source: str = ""
    record_public: bool = False
    step: str = ""


@dataclass(frozen=True)
class Decision:
    action_id: str
    message: str = ""
    reason: str = ""


@dataclass(frozen=True)
class Turn:
    resident_id: str
    card: str
    actions: tuple[Action, ...]
    round_number: int | None = None

    def action_for(self, decision: Decision) -> Action | None:
        return next((action for action in self.actions if action.id == decision.action_id), None)


Policy = Callable[[Turn], Decision]


@dataclass(frozen=True)
class Agent:
    resident_id: str
    policy: Policy

    def decide(self, observation: Turn) -> Decision:
        if observation.resident_id != self.resident_id:
            raise ValueError("The observation belongs to another resident.")
        return self.policy(observation)


@dataclass(frozen=True)
class ActionOutcome:
    action_id: str
    status: str
    event_ids: tuple[str, ...] = ()
    details: dict[str, object] = field(default_factory=dict)


@dataclass
class DecisionTrace:
    turn: Turn
    decision: Decision
    legal: bool
    seconds: float
    outcome: ActionOutcome | None = None

    def to_dict(self) -> dict:
        return {
            "round": self.turn.round_number,
            "resident": self.turn.resident_id,
            "card": json.loads(self.turn.card),
            "legal_action_ids": [action.id for action in self.turn.actions],
            "decision": asdict(self.decision),
            "legal": self.legal,
            "seconds": self.seconds,
            "outcome": asdict(self.outcome) if self.outcome is not None else None,
        }


class AgentHarness:
    """Run a shared policy separately for each resident and record its world outcome."""

    def __init__(self, policy: Policy, *, record: bool = True,
                 on_decision: Callable[[DecisionTrace], None] | None = None):
        self.policy = policy
        self.record = record
        self.on_decision = on_decision
        self.agents: dict[str, Agent] = {}
        self.traces: list[DecisionTrace] = []
        self._round_traces: dict[str, DecisionTrace] = {}

    @classmethod
    def wrap(cls, policy: "Policy | AgentHarness") -> "AgentHarness":
        return policy if isinstance(policy, cls) else cls(policy, record=False)

    def collect(self, observations: Iterable[Turn]) -> dict[str, Decision]:
        frozen = tuple(observations)
        self._round_traces = {}
        return {turn.resident_id: self.decide(turn) for turn in frozen}

    def decide(self, turn: Turn) -> Decision:
        agent = self.agents.get(turn.resident_id)
        if agent is None:
            agent = Agent(turn.resident_id, self.policy)
            self.agents[turn.resident_id] = agent
        started = perf_counter()
        decision = agent.decide(turn)
        if self.record or self.on_decision:
            trace = DecisionTrace(turn, decision, turn.action_for(decision) is not None,
                                  round(perf_counter() - started, 3))
            if self.record:
                self.traces.append(trace)
                self._round_traces[turn.resident_id] = trace
            if self.on_decision:
                self.on_decision(trace)
        return decision

    def settle(self, outcomes: Mapping[str, ActionOutcome]) -> None:
        for resident_id, trace in self._round_traces.items():
            trace.outcome = outcomes[resident_id]
        self._round_traces.clear()

    def export(self) -> list[dict]:
        return [trace.to_dict() for trace in self.traces]
