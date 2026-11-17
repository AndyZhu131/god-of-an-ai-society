"""Character templates, independent runtime state, and versioned serialization."""

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path


SCHEMA_VERSION = 1


def bounded(value: float, field_name: str, minimum: float = 0, maximum: float = 2) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{field_name} must be a finite number between {minimum} and {maximum}.")


def required_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be nonempty text.")


def nonnegative_integer(value: int, field_name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a nonnegative integer.")


@dataclass(frozen=True)
class Traits:
    contention: float = 1
    care: float = 1
    promise_keeping: float = 1

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            bounded(value, name)


@dataclass(frozen=True)
class Principle:
    id: str
    description: str
    strength: float = 1

    def __post_init__(self) -> None:
        required_text(self.id, "principle.id")
        required_text(self.description, "principle.description")
        bounded(self.strength, "principle.strength")


@dataclass(frozen=True)
class Goal:
    id: str
    description: str
    priority: float = 1

    def __post_init__(self) -> None:
        required_text(self.id, "goal.id")
        required_text(self.description, "goal.description")
        bounded(self.priority, "goal.priority")


@dataclass(frozen=True)
class CharacterTemplate:
    id: str
    name: str
    age: int = 25
    max_health: int = 2
    initial_health: int = 2
    remaining_turns: int | None = None
    traits: Traits = field(default_factory=Traits)
    adaptability: float = 1
    principles: tuple[Principle, ...] = ()
    goals: tuple[Goal, ...] = ()
    skills: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        required_text(self.id, "template.id")
        required_text(self.name, "template.name")
        nonnegative_integer(self.age, "age")
        nonnegative_integer(self.max_health, "max_health")
        nonnegative_integer(self.initial_health, "initial_health")
        if self.max_health == 0 or not 0 < self.initial_health <= self.max_health:
            raise ValueError("A new character needs positive health within its maximum.")
        if self.remaining_turns is not None:
            nonnegative_integer(self.remaining_turns, "remaining_turns")
            if self.remaining_turns == 0:
                raise ValueError("A new character needs at least one remaining turn.")
        bounded(self.adaptability, "adaptability")
        if not isinstance(self.traits, Traits):
            raise ValueError("traits must be a Traits record.")
        for name, values, record_type in (
            ("principles", self.principles, Principle), ("goals", self.goals, Goal), ("skills", self.skills, str),
        ):
            if not isinstance(values, tuple) or not all(isinstance(value, record_type) for value in values):
                raise ValueError(f"{name} must be a tuple of {record_type.__name__} records.")
            identifiers = [value if record_type is str else value.id for value in values]
            for identifier in identifiers:
                required_text(identifier, name)
            if len(set(identifiers)) != len(identifiers):
                raise ValueError(f"{name} must have unique IDs.")

    @classmethod
    def from_dict(cls, data: dict) -> "CharacterTemplate":
        if not isinstance(data, dict):
            raise ValueError("A template must be an object.")
        values = dict(data)
        for name in ("principles", "goals", "skills"):
            if not isinstance(values.get(name, []), (list, tuple)):
                raise ValueError(f"{name} must be an array.")
        values["traits"] = Traits(**values.get("traits", {}))
        values["principles"] = tuple(Principle(**item) for item in values.get("principles", []))
        values["goals"] = tuple(Goal(**item) for item in values.get("goals", []))
        values["skills"] = tuple(values.get("skills", []))
        return cls(**values)

    def create(self, resident_id: str) -> "Character":
        return Character(
            id=resident_id, template=self, age=self.age, health=self.initial_health, remaining_turns=self.remaining_turns,
            traits=self.traits, principles={item.id: item for item in self.principles},
            goals={item.id: item for item in self.goals}, skills=dict.fromkeys(self.skills, "initial"),
        )


@dataclass(frozen=True)
class Relationship:
    trust: float = 0
    affinity: float = 0
    obligations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        bounded(self.trust, "trust", -1, 1)
        bounded(self.affinity, "affinity", -1, 1)
        if not isinstance(self.obligations, tuple):
            raise ValueError("obligations must be a tuple of agreement IDs.")
        for agreement in self.obligations:
            required_text(agreement, "agreement")


@dataclass(frozen=True)
class Memory:
    event_id: str
    description: str
    learned_at: int
    source: str = "observed"
    speaker_id: str | None = None

    def __post_init__(self) -> None:
        required_text(self.event_id, "memory.event_id")
        required_text(self.description, "memory.description")
        nonnegative_integer(self.learned_at, "learned_at")
        if self.source not in {"observed", "claim", "interpretation"}:
            raise ValueError("Memory source must be observed, claim, or interpretation.")
        if self.source == "claim":
            required_text(self.speaker_id, "claim.speaker_id")


@dataclass(frozen=True)
class Belief:
    description: str
    confidence: float
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        required_text(self.description, "belief.description")
        bounded(self.confidence, "confidence", 0, 1)
        if not isinstance(self.evidence, tuple):
            raise ValueError("evidence must be a tuple of event IDs.")
        for ref in self.evidence:
            required_text(ref, "evidence")


@dataclass(frozen=True)
class Emotion:
    intensity: float
    expires_at: int

    def __post_init__(self) -> None:
        bounded(self.intensity, "intensity")
        nonnegative_integer(self.expires_at, "expires_at")


@dataclass(frozen=True)
class Plan:
    goal_id: str
    steps: tuple[str, ...]
    next_step: int = 0

    def __post_init__(self) -> None:
        required_text(self.goal_id, "plan.goal_id")
        if not isinstance(self.steps, tuple) or not self.steps:
            raise ValueError("A plan needs a tuple of action IDs.")
        for step in self.steps:
            required_text(step, "plan.step")
        nonnegative_integer(self.next_step, "next_step")
        if self.next_step > len(self.steps):
            raise ValueError("next_step cannot exceed the number of plan steps.")


@dataclass
class Character:
    id: str
    template: CharacterTemplate
    age: int
    health: int
    remaining_turns: int | None
    traits: Traits
    principles: dict[str, Principle] = field(default_factory=dict)
    goals: dict[str, Goal] = field(default_factory=dict)
    skills: dict[str, str] = field(default_factory=dict)
    relationships: dict[str, Relationship] = field(default_factory=dict)
    beliefs: dict[str, Belief] = field(default_factory=dict)
    memories: list[Memory] = field(default_factory=list)
    emotions: dict[str, Emotion] = field(default_factory=dict)
    location_id: str | None = None
    group_ids: list[str] = field(default_factory=list)
    status: str = "active"
    plan: Plan | None = None

    def validate(self) -> None:
        required_text(self.id, "character.id")
        if not isinstance(self.template, CharacterTemplate) or not isinstance(self.traits, Traits):
            raise ValueError("A character needs a template and traits.")
        nonnegative_integer(self.age, "age")
        nonnegative_integer(self.health, "health")
        if self.health > self.template.max_health:
            raise ValueError("Health exceeds the template maximum.")
        if self.remaining_turns is not None:
            nonnegative_integer(self.remaining_turns, "remaining_turns")
        if self.status not in {"active", "departed", "dead"}:
            raise ValueError("Unknown character status.")
        if self.status == "active" and (not self.health or self.remaining_turns == 0):
            raise ValueError("An active character needs positive health and remaining lifespan.")
        for name, values, record_type in (
            ("principles", self.principles, Principle), ("goals", self.goals, Goal),
            ("skills", self.skills, str), ("relationships", self.relationships, Relationship),
            ("beliefs", self.beliefs, Belief), ("emotions", self.emotions, Emotion),
        ):
            if not isinstance(values, dict):
                raise ValueError(f"{name} must be a mapping.")
            for identifier, value in values.items():
                required_text(identifier, name)
                if not isinstance(value, record_type):
                    raise ValueError(f"{name} contains an invalid {record_type.__name__} record.")
                if name == "skills":
                    required_text(value, "skill provenance")
                if name in {"principles", "goals"} and value.id != identifier:
                    raise ValueError(f"{name} ID does not match its mapping key.")
        if self.id in self.relationships:
            raise ValueError("A relationship needs another resident.")
        if not isinstance(self.memories, list) or not all(isinstance(item, Memory) for item in self.memories):
            raise ValueError("memories must be a list of Memory records.")
        if not isinstance(self.group_ids, list):
            raise ValueError("group_ids must be a list.")
        for group in self.group_ids:
            required_text(group, "group_id")
        if len(set(self.group_ids)) != len(self.group_ids):
            raise ValueError("group_ids must be unique.")
        if self.location_id is not None:
            required_text(self.location_id, "location_id")
        if self.plan is not None:
            if not isinstance(self.plan, Plan) or self.plan.goal_id not in self.goals:
                raise ValueError("The plan must reference one of this character's goals.")

    def __post_init__(self) -> None:
        self.validate()

    def to_dict(self) -> dict:
        self.validate()
        return {"schema_version": SCHEMA_VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, data: dict) -> "Character":
        if not isinstance(data, dict):
            raise ValueError("A character snapshot must be an object.")
        values = dict(data)
        version = values.pop("schema_version", None)
        if type(version) is not int or version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported character schema version {version!r}.")
        values["template"] = CharacterTemplate.from_dict(values["template"])
        values["traits"] = Traits(**values["traits"])
        values["principles"] = {key: Principle(**item) for key, item in values.get("principles", {}).items()}
        values["goals"] = {key: Goal(**item) for key, item in values.get("goals", {}).items()}
        values["relationships"] = {
            key: Relationship(**{**item, "obligations": tuple(item.get("obligations", []))})
            for key, item in values.get("relationships", {}).items()
        }
        values["beliefs"] = {
            key: Belief(**{**item, "evidence": tuple(item.get("evidence", []))})
            for key, item in values.get("beliefs", {}).items()
        }
        values["emotions"] = {key: Emotion(**item) for key, item in values.get("emotions", {}).items()}
        values["memories"] = [Memory(**item) for item in values.get("memories", [])]
        if values.get("plan") is not None:
            plan = values["plan"]
            values["plan"] = Plan(**{**plan, "steps": tuple(plan["steps"])})
        return cls(**values)

    def model_state(self, now: int) -> dict:
        nonnegative_integer(now, "now")
        state = self.to_dict()
        state.pop("schema_version")
        template = state.pop("template")
        state["name"] = template["name"]
        state["your_health"] = {"current": self.health, "maximum": self.template.max_health}
        state.pop("health")
        state["baseline_traits"] = template["traits"]
        state["adaptability"] = template["adaptability"]
        state["emotions"] = {key: value for key, value in state["emotions"].items() if value["expires_at"] > now}
        state["memories"] = [memory for memory in state["memories"] if memory["learned_at"] <= now]
        return state


def load_templates(path: Path) -> dict[str, CharacterTemplate]:
    data = json.loads(path.read_text(encoding="utf8"))
    if (not isinstance(data, dict) or type(data.get("schema_version")) is not int
            or data["schema_version"] != SCHEMA_VERSION):
        raise ValueError("Unsupported template schema version.")
    if not isinstance(data.get("templates"), list):
        raise ValueError("templates must be an array.")
    records = [CharacterTemplate.from_dict(item) for item in data["templates"]]
    templates = {item.id: item for item in records}
    if len(templates) != len(records):
        raise ValueError("Template IDs must be unique.")
    return templates
