"""Player choices, objectives, and carryover for After the Bounty."""

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from agents import AgentHarness

from .engine import SKILLS, Island


@dataclass(frozen=True)
class Influence:
    title: str
    tradeoff: str
    guidance: str


GOALS = {
    "survive": ("风暴之后", "至少 8 名居民活到迎船终章。"),
    "legacy": ("技艺有人接手", "一位老师或存档者离场后，有人用他留下的技艺修艇或复核航道。"),
    "stay_and_leave": ("有路可走，也有人留下", "至少 1 人登上外船，留岛成年人仍掌握两种技艺。"),
}
INFLUENCES = {
    "teach": Influence(
        "重视传承",
        "优先教人或存档，可能错过当年的修艇与自保。",
        "Value passing on skills, especially when only a few people know them. Consider using your year to "
        "teach someone who can carry on the work or to archive the skill, even at a cost to your own plans.",
    ),
    "protect": Influence(
        "愿意替人挡风",
        "优先照顾还有空缺的人，可能花掉自己的准备时间。",
        "When someone still lacks storm shelter, consider spending your own year to protect them. "
        "Give weight to the people you care about and to people who have no other help.",
    ),
    "keep_word": Influence(
        "把承诺当回事",
        "优先履行仍有用的承诺，可能放弃新出现的好机会。",
        "Make promises sparingly. If a promise is due and the promised action is still useful and legal, "
        "give following through extra weight when a competing opportunity appears.",
    ),
}
LEGACY_INFLUENCES = {
    "apprentice": Influence(
        "先带出接班人", "愿为年轻人的长期能力投资，可能推迟眼前工程。",
        "When only a few people know an important skill, favour teaching a younger resident with years left to use it. "
        "Consider doing this before taking another year of workshop work for yourself.",
    ),
    "open_archive": Influence(
        "让陌生人也能接手", "公开存档能穿过人际关系，也会花掉当年的教学或工程机会。",
        "If an important skill has no public archive, favour leaving a record others can study, including someone "
        "you do not know well. Let urgent needs override this preference.",
    ),
    "fill_shelter_gap": Influence(
        "给没人护的人补位", "帮全岛补空缺，可能把自己的保护交给别人。",
        "Before spending a year on shelter, look for someone who still lacks prepared shelter and has no volunteer. "
        "Favour covering a neglected person even when you had planned to help someone familiar.",
    ),
    "share_boat": Influence(
        "顺路多带一个人", "愿把个人避险变成互助，取决于船和领航条件。",
        "When the boat makes joint shelter delivery possible, favour protecting yourself and another person together. "
        "Look for a person who has not been covered by anyone else.",
    ),
    "renewed_trust": Influence(
        "答应了就留出时间", "抢先预留兑现承诺的时间，可能放弃眼前出现的便利。",
        "When making a new promise, first account for your existing commitments. Give a useful, actionable promise "
        "you have already made priority over a new opportunity, even if no one reminds you.",
    ),
}
INTERVENTIONS = {
    "council": ("召开公开议事", "居民先公开保护意向，再看着全岛计划各自选择行动。"),
    "postpone": ("推迟风暴一年", "多一年准备；等待期间，年长居民也可能离场。每局最多用一次。"),
}
INTERVENTION_BUDGET = 2


@dataclass(frozen=True)
class Legacy:
    influence: str
    resident: str
    story: str
    evidence: tuple[str, ...]
    source_log: str = ""


def load_legacy(path: Path) -> Legacy | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf8"))
    if (not isinstance(data, dict) or not isinstance(data.get("influence"), str)
            or data["influence"] not in LEGACY_INFLUENCES
            or not all(isinstance(data.get(key), str) for key in ("resident", "story"))
            or not isinstance(data.get("source_log", ""), str)
            or not isinstance(data.get("evidence"), list)
            or not all(isinstance(ref, str) for ref in data["evidence"])):
        raise ValueError("Invalid legacy record.")
    return Legacy(data["influence"], data["resident"], data["story"], tuple(data["evidence"]),
                  data.get("source_log", ""))


def choose(prompt: str, options: list[str], *, skip: str = "") -> int | None:
    print(f"\n{prompt}")
    for index, option in enumerate(options, 1):
        print(f"  {index}. {option}")
    if skip:
        print(f"  0. {skip}")
    while True:
        value = input("> ").strip()
        if skip and value in {"", "0"}:
            return None
        if len(value) <= len(str(len(options))) and value.isascii() and value.isdecimal():
            index = int(value)
            if 1 <= index <= len(options):
                return index - 1
        print("请输入菜单里的编号。")


def knowledge_paths(events: list[dict]) -> list[tuple[dict, dict, dict | None]]:
    """Find where a person learned a skill they later used on the boat."""
    by_id = {event["id"]: event for event in events}
    departed = {event["resident"]: event for event in events if event["kind"] == "departed"}
    paths = []
    for use in events:
        if use["kind"] not in {"repaired", "surveyed"}:
            continue
        pending = list(use["refs"])
        seen = set()
        while pending:
            ref = pending.pop()
            if ref in seen:
                continue
            seen.add(ref)
            source = by_id[ref]
            if source["kind"] in {"taught", "archived"}:
                mentor = source.get("teacher", source.get("resident"))
                exit_event = departed.get(mentor)
                if mentor != use["resident"]:
                    paths.append((source, use, exit_event if exit_event and exit_event["year"] < use["year"] else None))
            pending.extend(source["refs"])
    return paths


def evaluate_goal(goal: str, island: Island) -> dict:
    ending = island.ending
    if ending is None:
        raise ValueError("The objective is scored at the finale.")
    if goal == "survive":
        arrivals = len(ending["left"]) + len(ending["stayed"])
        return {"achieved": arrivals >= 8, "progress": f"{arrivals}/8 名居民活到终章"}
    if goal == "legacy":
        for source, use, exit_event in knowledge_paths(island.events):
            if exit_event:
                return {"achieved": True, "progress": f"{use['resident']} 在导师离场后使用了继承的技艺",
                        "evidence": [source["id"], exit_event["id"], use["id"]]}
        return {"achieved": False, "progress": "尚无导师离场后使用继承技艺的记录"}
    skill_count = len(set(ending["skills_remaining"]) & set(SKILLS))
    return {"achieved": bool(ending["left"]) and skill_count == len(SKILLS),
            "progress": f"{len(ending['left'])} 人登船，留岛者掌握 {skill_count}/{len(SKILLS)} 种技艺"}


def earned_legacies(events: list[dict]) -> list[Legacy]:
    teaching = []
    paths = sorted(knowledge_paths(events), key=lambda path: path[2] is None)
    for source, use, exit_event in paths:
        mentor = source.get("teacher", source.get("resident"))
        refs = (source["id"], exit_event["id"], use["id"]) if exit_event else (source["id"], use["id"])
        work = "修艇" if use["kind"] == "repaired" else "复核航道"
        influence = "apprentice" if source["kind"] == "taught" else "open_archive"
        teaching.append(Legacy(influence, mentor, f"{source['year']} 年留下技艺，{use['resident']} "
                                                f"在 {use['year']} 年用这门技艺完成{work}。", refs))
    protection = []
    prepared = []
    promises = defaultdict(list)
    for event in events:
        if event["kind"] == "protected":
            prepared.append(event)
        elif event["kind"] == "storm":
            for prep in prepared:
                others = [person for person in prep["recipients"]
                          if person != prep["resident"] and person in event["sheltered"]]
                if others:
                    influence = "share_boat" if prep["method"] == "deliver" else "fill_shelter_gap"
                    protection.append(Legacy(influence, prep["resident"],
                                             f"花了一轮为 {'、'.join(others)} 准备避风，保护在 "
                                             f"{event['year']} 年风暴中生效。", (prep["id"], event["id"])))
            prepared.clear()
        elif event["kind"] == "kept_pledge":
            promises[event["resident"]].append(event)
    kept_word = [
        Legacy("renewed_trust", resident, f"实际兑现了 {len(fulfilled)} 项承诺。",
               tuple(event["id"] for event in fulfilled[:2]))
        for resident, fulfilled in promises.items() if len(fulfilled) >= 2
    ]
    candidates = {}
    for item in [*teaching, *protection, *kept_word]:
        candidates.setdefault((item.resident, item.influence), item)
    return list(candidates.values())


class PlayerSession:
    def __init__(self, island: Island, goal: str, influence: str, resident: str, *,
                 inherited: Legacy | None = None):
        choices = LEGACY_INFLUENCES if inherited else INFLUENCES
        if goal not in GOALS or influence not in choices or resident not in island.adults():
            raise ValueError("Choose an available objective, influence, and starting adult.")
        self.island = island
        self.goal = goal
        self.influence = influence
        self.resident = resident
        self.inherited = inherited
        self.interventions: list[dict] = []
        self.goal_result: dict | None = None
        self.candidates: list[Legacy] = []
        self.saved: Legacy | None = None
        island.dispositions[resident] = choices[influence].guidance

    @classmethod
    def start(cls, island: Island, legacy_file: Path) -> "PlayerSession":
        try:
            legacy = load_legacy(legacy_file)
        except (ValueError, OSError):
            print("遗产文件无法读取，本局使用预设影响卡。")
            legacy = None
        goals = tuple(GOALS)
        goal = choose("选一个开局目标", [f"{title} · {description}" for title, description in GOALS.values()])
        cards = tuple(INFLUENCES)
        labels = [f"{card.title} · {card.tradeoff}" for card in INFLUENCES.values()]
        if legacy:
            guidance = LEGACY_INFLUENCES[legacy.influence]
            labels.append(f"继承 {legacy.resident} 的「{guidance.title}」 · {guidance.tradeoff} {legacy.story}")
        card = choose("选一张影响卡", labels)
        people = tuple(island.adults())
        default_people = {"teach": "lin", "protect": "bess", "keep_word": "noa"}
        inherited = legacy is not None and card == len(cards)
        influence = legacy.influence if inherited else cards[card]
        suggested = default_people.get(influence, "tavi")
        resident = choose(f"把卡交给一名成年居民。按 Enter 选择 {suggested}", list(people), skip=f"选择 {suggested}")
        return cls(island, goals[goal], influence, suggested if resident is None else people[resident],
                   inherited=legacy if inherited else None)

    @property
    def remaining(self) -> int:
        return INTERVENTION_BUDGET - len(self.interventions)

    def available_interventions(self) -> list[str]:
        if self.island.forecast() is None or not self.remaining:
            return []
        return [kind for kind in INTERVENTIONS
                if kind == "council" and not self.island.council_event
                or kind == "postpone" and not self.island.storm_postponed]

    def intervene(self, kind: str, harness: AgentHarness) -> None:
        if kind not in self.available_interventions():
            raise ValueError("That intervention is unavailable.")
        if kind == "council":
            event = self.island.hold_council(harness)
        else:
            event = self.island.postpone_storm()
        self.interventions.append({"kind": kind, "year": self.island.year, "event": event})

    def choose_intervention(self) -> str | None:
        options = self.available_interventions()
        if not options:
            return None
        people = self.island.present()
        plan = self.island.storm_plan(people)
        at_risk = "、".join(plan["would_die_if_unprotected"]) or "暂无"
        print(f"\n{self.island.year} 年 · 风暴预警 {self.island.forecast()} 年 · "
              f"已备避风 {len(self.island.sheltered)}/{len(people)} 人 · 未保护即会死亡 {at_risk}", flush=True)
        selection = choose(f"剩余 {self.remaining} 次干预机会",
                           [f"{INTERVENTIONS[k][0]} · {INTERVENTIONS[k][1]}" for k in options], skip="保留机会")
        return options[selection] if selection is not None else None

    def show_year(self, year: int) -> None:
        highlights = []
        for event in self.island.events:
            if event["year"] != year:
                continue
            kind = event["kind"]
            if kind == "storm":
                highlights.append((0, event["id"], f"风暴到来，{len(event['sheltered'])} 人已有避风准备。"))
            elif kind == "departed":
                cause = "寿命结束" if event["cause"] == "lifespan" else "未能熬过风暴"
                highlights.append((1, event["id"], f"{event['resident']} {cause}。"))
            elif kind == "repaired":
                highlights.append((2, event["id"], f"{event['resident']} 修好了小艇。"))
            elif kind == "surveyed":
                highlights.append((2, event["id"], f"{event['resident']} 复核了航道。"))
            elif kind == "taught":
                skill = "船木工" if event["skill"] == "carpentry" else "领航"
                highlights.append((3, event["id"], f"{event['teacher']} 教了 {event['target']} {skill}。"))
            elif kind == "took_workshop":
                holders = "、".join(event["reserved"])
                highlights.append((2, event["id"], f"{holders} 获得了下一年的工位优先权。"))
        for _, event_id, text in sorted(highlights)[:2]:
            print(f"  [{event_id}] {text}", flush=True)

    def conclude(self) -> None:
        self.goal_result = evaluate_goal(self.goal, self.island)
        self.candidates = earned_legacies(self.island.events)
        result = "达成" if self.goal_result["achieved"] else "未达成"
        print(f"\n目标「{GOALS[self.goal][0]}」{result} · {self.goal_result['progress']}")
        for choice in self.interventions:
            event = next(item for item in self.island.events if item["id"] == choice["event"])
            if choice["kind"] == "postpone":
                print(f"  [{event['id']}] 风暴从 {event['from_year']} 年改到 {event['to_year']} 年。")
            else:
                review = next(item for item in self.island.events
                              if item["kind"] == "council_review" and event["id"] in item["refs"])
                print(f"  [{event['id']} → {review['id']}] 议事有 {review['announced']} 人表态，"
                      f"{len(review['followed'])} 人实际完成了所声明的行动。")
        if self.candidates:
            item = self.candidates[0]
            print(f"  [{' → '.join(item.evidence)}] {item.resident} · {item.story}")

    def save_legacy(self, legacy_file: Path, source_log: Path) -> None:
        if not self.candidates:
            print("这局还没有足够的事件证据可以生成遗产。")
            return
        selection = choose("选一张留给下局的遗产牌",
                           [f"{item.resident} · {LEGACY_INFLUENCES[item.influence].title} · {item.story} "
                            f"[{' → '.join(item.evidence)}]" for item in self.candidates],
                           skip="保留已有遗产")
        if selection is None:
            return
        candidate = replace(self.candidates[selection], source_log=str(source_log))
        pending = legacy_file.with_name(legacy_file.name + ".tmp")
        pending.write_text(json.dumps(asdict(candidate), ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        pending.replace(legacy_file)
        self.saved = candidate
        print(f"已保存遗产 {legacy_file.resolve()}")

    def export(self) -> dict:
        return {"goal": self.goal, "influence": self.influence, "recipient": self.resident,
                "inherited": self.inherited is not None,
                "legacy_origin": asdict(self.inherited) if self.inherited else None,
                "interventions_left": self.remaining, "interventions": self.interventions, "goal_result": self.goal_result,
                "legacy_candidates": [asdict(item) for item in self.candidates],
                "saved_legacy": asdict(self.saved) if self.saved else None}
