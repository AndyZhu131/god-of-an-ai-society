"""Behavioral preferences and explicit personal limits for residents."""

from dataclasses import dataclass


GUIDANCE = {
    "contention": (
        "Prefer working within the current arrangement. Spend your year contesting control only when its cost is justified.",
        "Weigh changing control against practical work. Contest an arrangement that no longer serves your goals.",
        "Actively organize or back a credible change of control that serves your goals, even when it costs your year.",
    ),
    "care": (
        "Prioritize your own safety and work. Help others when doing so costs you little.",
        "Spend time helping someone in serious need when the cost or risk to you is manageable.",
        "Give urgent unmet needs extra weight. Be willing to spend your year helping even if it costs your own progress or safety.",
    ),
    "promise_keeping": (
        "Treat a past promise as one consideration. Give a better current opportunity priority when the two conflict.",
        "Keep a useful, feasible promise when possible. Reconsider it if an important new need arises.",
        "Give a useful, feasible promise strong priority. Be willing to give up a good new opportunity to follow through.",
    ),
}


@dataclass(frozen=True)
class Personality:
    contention: int = 1
    care: int = 1
    promise_keeping: int = 1
    no_self_reservation: bool = False

    def __post_init__(self) -> None:
        for trait in GUIDANCE:
            value = getattr(self, trait)
            if type(value) is not int or not 0 <= value <= 2:
                raise ValueError(f"{trait} must be 0, 1, or 2.")

    def describe(self) -> dict:
        profile = {trait: {"level": getattr(self, trait), "guidance": levels[getattr(self, trait)]}
                   for trait, levels in GUIDANCE.items()}
        if self.no_self_reservation:
            profile["boundary"] = "You will not vote for a proposal that reserves a workshop seat for you."
        return profile


PRESETS = {
    "mediator": Personality(contention=0, care=2),
    "keeper": Personality(promise_keeping=2),
    "organizer": Personality(contention=2, care=2, no_self_reservation=True),
}
