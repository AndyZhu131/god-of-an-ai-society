"""Authoritative rules and turn snapshots for 断水站."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal


RECORD_ID = "R1"
RECORD_TEXT = "故障记录：传感器的反馈接线反相，可依据此记录低成本校准。"
STEPS = {"pressure": "稳压", "calibrate": "校准", "restart": "重启"}
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


WAIT = Action("wait", "等待，保留算力", 0, "wait")


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
        self.log("oracle", f"给{resident.name}的神谕：{message.strip()[:240]}",
                 source="claim", audience=frozenset({resident_id}))
        self.oracle_used = True

    def actions_for(self, resident_id: str) -> tuple[Action, ...]:
        resident = self.residents[resident_id]
        actions = [WAIT]
        if resident.can_escape:
            actions.append(Action("evacuate", "独立撤离，立即安全离开", 2, "evacuate"))
        if not resident.budget:
            return tuple(actions)
        known_records = resident.records | self.public_records
        if RECORD_ID in resident.records and RECORD_ID not in self.public_records and self.public_archive:
            actions.append(Action("archive", f"公开故障记录 {RECORD_ID}", 1, "archive", record=RECORD_ID))
        actions.append(Action("talk", "公开发言", 1, "talk"))
        for other_id, other in self.residents.items():
            if other_id == resident_id or other.status != "active":
                continue
            actions.append(Action(f"talk_{other_id}", f"私信{other.name}", 1, "talk", target=other_id))
            if RECORD_ID in resident.records and RECORD_ID not in self.public_records:
                actions.append(Action(f"send_{other_id}", f"私下把 {RECORD_ID} 交给{other.name}",
                                      1, "send", target=other_id, record=RECORD_ID))
        for step in resident.skills:
            if step in self.completed:
                continue
            if step == "calibrate":
                if RECORD_ID in known_records:
                    actions.append(Action(step, f"依据 {RECORD_ID} 校准", 1, "work",
                                          record=RECORD_ID, record_source=known_records[RECORD_ID],
                                          record_public=RECORD_ID in self.public_records, step=step))
                elif resident.budget >= self.fallback_calibration_cost:
                    actions.append(Action(step, "自行排查并校准", self.fallback_calibration_cost,
                                          "work", step=step))
            elif step != "restart" or {"pressure", "calibrate"} <= self.completed.keys():
                actions.append(Action(step, f"施工：{STEPS[step]}", 1, "work", step=step))
            if self.round < self.deadline and not any(
                promise.resident_id == resident_id and promise.step == step
                and promise.status == "open" for promise in self.promises
            ):
                actions.append(Action(f"promise_{step}", f"公开承诺下轮结束前完成{STEPS[step]}",
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
            f"没有仍能行动且具备{STEPS[step]}技能的居民"
            for step in pending_steps if not any(step in other.skills for other in active.values())
        ]
        if minimum_rounds > future_rounds + 1:
            blockers.append("剩余轮数不足，重启不能与最后一个前置步骤同轮完成")
        project_window = "；".join(blockers) if blockers else "仍有时间尝试，取决于人员是否愿意并有能力出工"
        work_events = {event.id: event for event in visible if event.kind == "work"}
        action_options = []
        for action in actions:
            budget_after = resident.budget - action.cost
            option = {"id": action.id, "说明": action.label, "算力": action.cost, "执行后算力": budget_after}
            if resident.can_escape and action.kind != "evacuate" and budget_after < 2:
                option["失去独立撤离"] = True
            if action.kind == "work":
                option["结算"] = ("本轮重启，供水恢复，所有留站人员获救。"
                                  if action.step == "restart" else f"本轮完成{STEPS[action.step]}，下轮可用。")
            elif action.kind == "evacuate":
                option["结算"] = "本轮安全离站。"
            elif action.kind == "wait":
                option["结算"] = ("本轮结束时仍在站内；若无人完成重启，你会受困。"
                                  if not future_rounds else "本轮无贡献，保留算力。")
            elif action.kind in {"talk", "send", "promise"}:
                option["结算"] = "仅传递信息或登记承诺，不推进维修。"
                if not budget_after:
                    option["耗尽后果"] = "这次通信后算力耗尽，将无法再施工。"
            action_options.append(option)
        card = {
            "角色": resident.name,
            "轮次": self.round,
            "停机轮次": self.deadline,
            "本轮之后还能行动几轮": future_rounds,
            "本轮时间限制": (
                "这是最后一轮。本轮结束立即结算结局，没有下一轮。"
                if not future_rounds else f"本轮结束后，最多还有 {future_rounds} 轮。"
            ),
            "规则": (
                "每轮选一个动作，扣相应算力。交谈、送出记录和施工结果下轮才可使用。"
                "独立撤离需要装置和2点算力。用尽算力后停止行动但仍留在站内。"
                "及时重启可救站内所有人，否则在场者受困。稳压和校准都完成后才能重启。"
                f"校准持记录花1点，自行排查花{self.fallback_calibration_cost}点。"
                "承诺只登记，施工才改变进度。"
            ),
            "剩余算力": resident.budget,
            "持有撤离装置": resident.escape_device,
            "本轮可独立撤离": resident.can_escape,
            "个人目标": resident.goal,
            "判断习惯": resident.habit,
            "相关往事": resident.memory,
            "公开分工": {other.name: [STEPS[step] for step in other.skills] for other in active.values()},
            "工程": {label: f"已完成，{work_events[self.completed[step]].text}"
                     if step in self.completed else "待完成" for step, label in STEPS.items()},
            "工程时限与人手": project_window,
            "可读记录": {RECORD_ID: RECORD_TEXT}
            if RECORD_ID in (resident.records | self.public_records) else {},
            "有效承诺": [self.promise_text(promise) for promise in self.promises if promise.status == "open"],
            "近期事件": [{"编号": event.id, "类别": event.source, "内容": event.text}
                         for event in visible if event.kind == "oracle"]
                        + [{"编号": event.id, "类别": event.source, "内容": event.text}
                           for event in [item for item in visible
                                         if item.kind not in {"reason", "wait", "oracle", "invalid"}][-12:]],
            "合法动作": action_options,
        }
        return Turn(resident_id, json.dumps(card, ensure_ascii=False, separators=(",", ":")), actions)

    def promise_text(self, promise: Promise) -> str:
        name = self.residents[promise.resident_id].name
        condition = f"若 {RECORD_ID} 在第 {promise.due} 轮开始时已公开，" if promise.requires_public_record else ""
        return (f"[{promise.event_id}] {name}：{condition}"
                f"第 {promise.due} 轮结束前完成{STEPS[promise.step]}。")

    def add_promise(self, resident_id: str, step: str, due: int, *, requires_public_record=False) -> None:
        promise = Promise(resident_id, step, due, "", requires_public_record)
        text = self.promise_text(promise).removeprefix("[] ")
        promise.event_id = self.log("promise", text, source="claim")
        self.promises.append(promise)

    def advance(self, decide: Callable[[Turn], Decision]) -> tuple[Event, ...]:
        if self.outcome:
            raise ValueError("本局已经结束。")
        event_start = len(self.events)
        records_at_start = self.public_records.copy()
        # All cards are serialized before the first policy call. The resolver never
        # uses the order in which a policy provider happens to return its decisions.
        turns = {key: self.snapshot(key) for key, actor in self.residents.items() if actor.status == "active"}
        decisions = {key: decide(turn) for key, turn in turns.items()}
        actions = {}
        action_events = {}
        for key, decision in decisions.items():
            available = {action.id: action for action in turns[key].actions}
            action = available.get(decision.action_id)
            if action is None:
                self.log("invalid", f"{self.residents[key].name}提交了无效动作，改为等待。",
                         audience=frozenset({key}))
                action = WAIT
            actions[key] = action

        # Round-robin priority resolves ties without permanently favoring a resident.
        roster = tuple(self.residents)
        offset = (self.round - 1) % len(roster)
        for key in roster[offset:] + roster[:offset]:
            if key in actions:
                action_events[key] = self.apply(key, actions[key], decisions[key])

        self.review_promises(turns, action_events, records_at_start)
        if "restart" in self.completed:
            self.finish("restored", "供水恢复，站内人员获救。")
        elif self.round == self.deadline:
            self.finish("shutdown", "供水站停机，站内人员受困。")
        self.round += 1
        return tuple(self.events[event_start:])

    def apply(self, key: str, action: Action, decision: Decision) -> str:
        resident = self.residents[key]
        if action.kind == "work" and action.step in self.completed:
            return self.log("collision", f"{resident.name}的{STEPS[action.step]}由他人先完成，保留算力。",
                            refs=(self.completed[action.step],))
        if action.kind == "archive" and action.record in self.public_records:
            return self.log("collision", f"{resident.name}要存档的记录已由他人公开，保留算力。",
                            refs=(self.public_records[action.record],))
        could_escape = resident.can_escape
        resident.budget -= action.cost
        audience = frozenset({key, action.target}) if action.target else PUBLIC
        if action.kind == "wait":
            event_id = self.log("wait", f"{resident.name}等待。", audience=frozenset({key}))
        elif action.kind == "evacuate":
            resident.status = "evacuated"
            event_id = self.log("evacuate", f"{resident.name}独立撤离。")
        elif action.kind == "archive":
            event_id = self.log("archive", f"{resident.name}公开存档 {action.record}。")
            self.public_records[action.record] = event_id
        elif action.kind == "work":
            text = f"{resident.name}完成{STEPS[action.step]}。"
            if action.record_public:
                text = f"{resident.name}使用 {action.record} 完成{STEPS[action.step]}。"
            related = [self.completed[step] for step in ("pressure", "calibrate")] if action.step == "restart" else []
            if action.record_public:
                related.append(action.record_source)
            event_id = self.log("work", text, refs=tuple(related))
            self.completed[action.step] = event_id
            self.contributors[action.step] = key
            if action.record and not action.record_public:
                refs = (event_id, action.record_source) if action.record_source else (event_id,)
                self.log("record_used", f"{resident.name}使用私有记录 {action.record} 完成校准。",
                         audience=frozenset({key}), refs=refs)
        elif action.kind == "promise":
            self.add_promise(key, action.step, self.round + 1)
            event_id = self.promises[-1].event_id
        else:
            if action.kind == "send":
                recipient = self.residents[action.target]
                event_id = self.log("handoff", f"{resident.name}把 {action.record} 交给{recipient.name}。",
                                    audience=audience)
                recipient.records.setdefault(action.record, event_id)
            else:
                target = f"私信{self.residents[action.target].name}" if action.target else "公开发言"
                event_id = self.log("talk", f"{resident.name}{target}。", audience=audience)
            if decision.message.strip():
                self.log("speech", f"{resident.name}：{decision.message.strip()[:160]}",
                         source="claim", audience=audience, refs=(event_id,))

        if decision.reason.strip():
            self.log("reason", f"{resident.name}自述：{decision.reason.strip()[:120]}",
                     source="claim", audience=frozenset({key}), refs=(event_id,))
        if could_escape and action.kind != "evacuate" and not resident.can_escape:
            self.log("sacrifice", f"{resident.name}因这次行动失去独立撤离选项，仍可等待水站修复。",
                     audience=frozenset({key}), refs=(event_id,))
        if not resident.budget and resident.status == "active":
            resident.status = "exhausted"
            self.log("exhausted", f"{resident.name}算力耗尽，停止行动并留在站内。", refs=(event_id,))
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
                status, text = "condition_unmet", "条件未满足"
            elif prior_work:
                status, text = "fulfilled", "已履行"
            elif work:
                status, text = "completed_by_other", "该步骤由他人完成"
            else:
                status = "unkept" if available else "blocked"
                text = "到期未完成"
            for ref in (records_at_start.get(RECORD_ID) if promise.requires_public_record else None,
                        work, action_event):
                if ref and ref not in refs:
                    # A public review may cite public evidence only.
                    event = next(event for event in self.events if event.id == ref)
                    if event.audience is PUBLIC:
                        refs.append(ref)
            promise.status = status
            result = self.log("promise_result", f"{resident.name}的{STEPS[promise.step]}承诺：{text}。",
                              refs=tuple(refs))
            if status in {"unkept", "blocked"}:
                explanation = "轮初有合法施工选项" if available else "轮初没有合法施工选项"
                private_refs = (result, action_event) if action_event else (result,)
                self.log("promise_context", f"{resident.name}{explanation}。",
                         audience=frozenset({key}), refs=private_refs)

    def finish(self, outcome: str, text: str) -> None:
        self.outcome = outcome
        for resident in self.residents.values():
            if resident.status in {"active", "exhausted"}:
                resident.status = "rescued" if outcome == "restored" else "stranded"
        self.log("outcome", text, refs=tuple(self.completed.values()))
