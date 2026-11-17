"""Run the After the Bounty simulation with a local Ollama model."""

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from agents import AgentHarness, Turn
from decisions import ModelUnavailable, OllamaPolicy

from .engine import CONTACT_YEAR, FIRST_YEAR, STORM_YEARS, Island, IslandDecision
from .personality import PRESETS
from .player import PlayerSession


PROMPT = """You are one resident on an isolated island after the Bounty burned. Play only the resident on
this card. Consider your own goal, the people you care about, your remaining years, and what others
actually did. The card's events are facts. Notice-board messages and pledges are claims.

Copy your_health into health_readback before choosing an action. Even at 1 health, every
listed action remains available. Explain why your selected action serves your goal. Use a public
message for a plan, request, or reply. Leave it empty when you have nothing to tell others.
Choose exactly one ID from legal_actions. All residents choose from the start-of-year state.
You need two successful practices to learn a skill. Teaching, studying, and archiving take a year.
Carpentry practice and hull repair compete for two workshop seats. Reserved residents who apply go
first, then the listed priority. Only the first hull repair counts. A storm costs any unsheltered
person 1 health and damages a repaired hull. At 0 health the person is lost. Rest does not restore
health. Shelter can be prepared in the forecast year or the storm year and persists until the storm.
During a forecast, compare shelter_ready_for with storm_plan. A promise does not protect anyone
until it is carried out. Consider unprotected people with no volunteer, especially those with
only 1 health. A shelter action for someone else covers that person alone.
A working boat needs a repaired hull and surveyed sea route. During yearly turns you do not know when
a ship might appear. In the contact or departure phase, use the encounter on your card.

Alongside your action, you may send an English public message, pledge to take a legal work action
next year, or propose reserving the workshop. Use an exact ID from pledge_action_ids or leave it
empty. You can publicly volunteer to protect someone next year by pledging a shelter or delivery
action during the year before a storm. To propose a takeover, nominate exactly two distinct
adults using their IDs in nominees. People can vote next year. A proposal needs at least two
supporters and must beat the guards and each rival proposal. It reserves seats for one year.
Use [] when making no proposal. In the contact and departure phases, leave pledge and nominees empty.
Give one short English reason for the observer and keep message short or empty."""

COUNCIL_PROMPT = """Play the named resident in a public storm council. Copy your_health into health_readback.
Choose one ID from legal_actions. Announcing an intention spends no yearly action and shelters nobody.
After everyone has spoken you will see their plans, then choose your real action. You can change your
mind. Take your goal, people you care about, and personal_disposition into account. Choose pass if
you have no plan to announce. Give a short English reason. Leave message and pledge empty and
nominees as []. All listed actions remain available at your current health."""


class IslandPolicy(OllamaPolicy):
    def __init__(self, model=None, *, seed=None, prompt=PROMPT, **options):
        super().__init__(model, seed=seed, prompt=prompt, **options)
        self.health_rejections: list[dict] = []

    def build_request(self, turn: Turn) -> dict:
        request = super().build_request(turn)
        card = json.loads(turn.card)
        if card["phase"] == "council":
            request["messages"][0]["content"] = COUNCIL_PROMPT
        else:
            if "personal_disposition" in card:
                request["messages"][0]["content"] += (
                    "\nYour personal_disposition is a preference to weigh alongside your goal and the circumstances."
                )
            if "council" in card:
                request["messages"][0]["content"] += (
                    "\nThe council contains public intentions. Compare them with actual shelter and remaining gaps. "
                    "You can keep your plan or change it. Only successful shelter actions provide protection."
                )
        if "personality" in card:
            request["messages"][0]["content"] += (
                "\nWeigh the preferences in your personality alongside your goal and the facts of this situation."
            )
        response_format = request["format"]
        response_format["properties"] = {
            "health_readback": {
                "type": "object",
                "properties": {
                    "current": {"type": "integer"},
                    "maximum": {"type": "integer"},
                    "wait_restores_health": {"type": "boolean"},
                },
                "required": ["current", "maximum", "wait_restores_health"],
                "additionalProperties": False,
            },
            **response_format["properties"],
        }
        response_format["properties"].update(
            pledge={"type": "string", "enum": ["", *card["pledge_action_ids"]]},
            nominees={"type": "array", "items": {"type": "string"}, "maxItems": 2},
        )
        response_format["required"] = ["health_readback", *response_format["required"], "pledge", "nominees"]
        return request

    def decode_decision(self, output: dict) -> IslandDecision:
        base = super().decode_decision(output)
        pledge, nominees, health = output["pledge"], output["nominees"], output["health_readback"]
        if not isinstance(pledge, str) or not isinstance(nominees, list) or not all(
            isinstance(person, str) for person in nominees
        ):
            raise ValueError("Pledge must be text and nominees must be a list of resident IDs.")
        if (not isinstance(health, dict) or type(health.get("current")) is not int
                or type(health.get("maximum")) is not int
                or type(health.get("wait_restores_health")) is not bool):
            raise ValueError("Invalid health_readback fields.")
        return IslandDecision(base.action_id, base.message, base.reason, pledge, tuple(nominees), health)

    def validation_error(self, turn: Turn, decision: IslandDecision) -> str | None:
        error = super().validation_error(turn, decision)
        if error is not None:
            return error
        card = json.loads(turn.card)
        health = card["your_health"]
        if decision.health_readback != health:
            check = "readback"
        else:
            check = health_claim_error(turn.resident_id, decision, current=health["current"], maximum=health["maximum"])
        if check is None:
            return None
        self.health_rejections.append({"year": turn.round_number, "phase": card["phase"],
                                       "resident": turn.resident_id, "check": check,
                                       "expected_health": health, "decision": asdict(decision)})
        return (f"Your round-start health is {health['current']}/{health['maximum']}. "
                "Waiting does not restore health. Every action in legal_actions is available at your health. "
                "Copy your_health exactly and explain the action you choose using your goal and its effects.")


def health_claim_error(resident: str, decision: IslandDecision, *, current: int, maximum: int) -> str | None:
    text = f"{decision.reason}\n{decision.message}".lower().replace("’", "'")
    own_health = rf"(?:\bmy |\b{re.escape(resident)}'s |(?:^|[.!?]\s+))(?:current )?health(?: status)?"
    low = r"(?:currently |still |very |too |fully )*(?:low|poor|injured|wounded)\b"
    if current == maximum and (
        re.search(rf"{own_health} (?:is|remains) {low}", text, re.MULTILINE)
        or re.search(r"\bi(?: am|'m) (?:currently )?(?:injured|wounded|low on health)\b|\bi have low health\b", text)
        or re.search(r"(?:^|[.!?]\s+)low health makes\b", text, re.MULTILINE)
        or re.search(r"cannot take on (?:any )?new tasks(?: this year)? due to injury\b", text)
    ):
        return "low_health_claim"
    if current < maximum and (
        re.search(rf"{own_health} (?:is|remains) (?:currently |at )?(?:full|maximum)\b", text, re.MULTILINE)
        or re.search(r"\bi (?:have|am at) full health\b|\bi'm at full health\b", text)
    ):
        return "full_health_claim"
    if re.search(
        r"\b(?:injured|injur(?:y|ies)|health(?: status| condition)?)\b[^.!?\n]{0,80}"
        r"\b(?:prevents?|cannot|can't|unable)\b[^.!?\n]{0,38}"
        r"\b(?:act(?:ion|ions)?|participate|perform|take on|take any action|undertake|navigating)\b", text
    ):
        return "health_blocks_action_claim"
    if decision.action_id == "wait" and (
        re.search(r"\b(?:to|will|can) (?:fully )?(?:recover|regain|restore|replenish) "
                  r"(?:(?:my|some|lost) )*health\b", text)
        or re.search(r"\b(?:rest(?:ing)?|wait(?:ing)?)(?: this year)? to (?:fully )?(?:recover|heal)\b", text)
        or re.search(r"\b(?:need to|must) (?:fully )?(?:recover|heal)\b|\brest(?:ing)? (?:and |is necessary for |"
                     r"is essential for |is crucial for )recovery\b|\b(?:on|for|and) health recovery\b", text)
        or re.search(r"\b(?:rest(?:ing)?|wait(?:ing)?)(?: this year)? (?:will|would|can|may|might) "
                     r"[^.!?\n]{0,90}\b(?:recover|heal)\b", text)
        or re.search(r"\b(?:rest(?:ing)? and|give (?:me|us) time to|rest(?:ing)? is necessary to) "
                     r"(?:fully )?(?:recover|heal)\b", text)
    ):
        return "wait_recovery_claim"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="Override the default fast local model.")
    parser.add_argument("--seed", default=17, type=int, help="Workshop priority and model seed.")
    parser.add_argument("--rounds", type=int, choices=range(1, CONTACT_YEAR - FIRST_YEAR + 1),
                        metavar="1-18", help="Stop after this many yearly turns. Omit to run the finale.")
    parser.add_argument("--delay-storm", type=int, choices=STORM_YEARS, help="Delay one forecast storm by a year.")
    parser.add_argument("--play", action="store_true", help="Choose an objective, influence card, and interventions.")
    parser.add_argument("--personality", action="append", default=[], metavar="RESIDENT=PRESET",
                        help=f"Assign a personality to a resident. Presets: {', '.join(PRESETS)}.")
    parser.add_argument("--legacy-file", type=Path, default=Path("after_the_bounty_legacy.json"),
                        help="Load or save one legacy card in player mode.")
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()

    args.log = args.log or Path("after_the_bounty_play.json" if args.play else "after_the_bounty.json")
    if args.play and args.delay_storm:
        parser.error("Choose any storm postponement in the player menu when using --play.")
    if args.play and args.legacy_file.resolve() == args.log.resolve():
        parser.error("The game log and legacy card need separate paths.")
    island = Island(args.seed, args.delay_storm)
    for assignment in args.personality:
        resident, _, preset = assignment.partition("=")
        if resident not in island.residents or preset not in PRESETS or resident in island.personalities:
            parser.error(f"Invalid personality assignment {assignment!r}. Use one RESIDENT=PRESET per resident.")
        island.personalities[resident] = PRESETS[preset]
    try:
        player = PlayerSession.start(island, args.legacy_file) if args.play else None
    except (EOFError, KeyboardInterrupt):
        parser.exit(1, "\n已退出开局选择。\n")
    policy = IslandPolicy(args.model, seed=args.seed, prompt=PROMPT)
    harness = AgentHarness(policy)
    report = {"scenario": "after_the_bounty", "model": policy.model, "seed": args.seed,
              "delay_storm": args.delay_storm, "agent_instructions": policy.prompt, "years": []}
    if island.personalities:
        report["personalities"] = {resident: asdict(profile) for resident, profile in island.personalities.items()}

    def save() -> None:
        report.update(
            events=island.events, decisions=harness.export(), ending=island.ending, stats=asdict(policy.stats),
            health_rejections=policy.health_rejections,
            residents={key: asdict(person) for key, person in island.residents.items()},
        )
        if player:
            report["player"] = {**player.export(), "council_instructions": COUNCIL_PROMPT}
        temp_log = args.log.with_name(args.log.name + ".tmp")
        temp_log.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        temp_log.replace(args.log)

    try:
        for _ in range(args.rounds or CONTACT_YEAR - FIRST_YEAR):
            year = island.year
            intervention = player.choose_intervention() if player else None
            start = perf_counter()
            first_trace = len(harness.traces)
            print(f"{year} · {len(island.adults())} agents · {policy.model}", flush=True)
            if intervention:
                if intervention == "council":
                    print("  召开公开议事，正在收集保护意向…", flush=True)
                player.intervene(intervention, harness)
            island.advance(harness)
            elapsed = round(perf_counter() - start, 3)
            report["years"].append({"year": year, "seconds": elapsed, "decisions": len(harness.traces) - first_trace})
            save()
            print(f"  {elapsed} s · {len(island.present())} residents · boat ready: {island.boat_ready}", flush=True)
            if player:
                player.show_year(year)
        if args.rounds is None:
            print(f"{CONTACT_YEAR} · Topaz arrives", flush=True)
            start = perf_counter()
            ending = island.finish(harness)
            report["finale_seconds"] = round(perf_counter() - start, 3)
            print(json.dumps(ending), flush=True)
            if player:
                player.conclude()
            save()
            if player:
                player.save_legacy(args.legacy_file, args.log)
                save()
    except ModelUnavailable as error:
        parser.exit(1, f"{error} (Last completed year is recorded in {args.log}.)\n")
    except (EOFError, KeyboardInterrupt):
        parser.exit(1, f"\n已停止。已完成的年度和终章保存在 {args.log}。\n")
    except OSError as error:
        parser.exit(1, f"\n无法保存文件。{error}\n")
    print(f"Log: {args.log.resolve()}", flush=True)


if __name__ == "__main__":
    main()
