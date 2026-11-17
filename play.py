"""Run Water Station in a terminal, with an optional full event export."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from agents import AgentHarness
from decisions import ModelUnavailable, OllamaPolicy, ScriptedPolicy
from scenario import create_station


HIGHLIGHTS = {"archive", "handoff", "record_used", "work", "promise_result",
              "evacuate", "sacrifice", "outcome"}
STATUS = {
    "active": "可行动",
    "exhausted": "算力耗尽",
    "evacuated": "已撤离",
    "rescued": "获救",
    "stranded": "受困",
}
STEP_LABELS = {"pressure": "稳压", "calibrate": "校准", "restart": "重启"}
RESIDENT_LABELS = {
    "cen": "岑", "lin": "林", "qiao": "乔", "tang": "唐",
    "mei": "梅", "yu": "余", "song": "宋", "wu": "吴",
}


def show_events(events):
    for event in events:
        label = "事实" if event.source == "fact" else "自述或说法"
        refs = f"（关联 {'、'.join(event.refs)}）" if event.refs else ""
        print(f"  [{event.id} · {label}] {event.text}{refs}", flush=True)


def show_station(station):
    print("  " + " → ".join(f"{label} {'✓' if key in station.completed else '○'}"
                              for key, label in STEP_LABELS.items()), flush=True)
    print("  " + " ｜ ".join(f"{RESIDENT_LABELS[key]} {resident.budget}点 {STATUS[resident.status]}"
                             for key, resident in station.residents.items()), flush=True)


def player_turn(station):
    if station.oracle_used:
        input("按 Enter 进入下一轮。")
        return
    recipients = {key: RESIDENT_LABELS[key] for key, resident in station.residents.items()
                  if resident.status == "active"}
    print("本局可发一次私密神谕。接收者 " + " / ".join(recipients.values()))
    while True:
        name = input("输入名字发神谕，或按 Enter 跳过：").strip()
        if not name:
            return
        recipient = next((key for key, value in recipients.items() if name.lower() == key or name == value), None)
        if recipient is None:
            print("请选择可行动的角色。")
            continue
        message = input("神谕内容，请用英文（按 Enter 取消）：").strip()
        if not message:
            return
        try:
            station.oracle(recipient, message)
        except ValueError as error:
            print(error)
            continue
        return


def main():
    parser = argparse.ArgumentParser(description="断水站 · 八人回合模拟原型")
    parser.add_argument("--backend", choices=("scripted", "ollama"), default="scripted")
    parser.add_argument("--route", choices=("cooperate", "withdraw", "shutdown"), default="cooperate")
    parser.add_argument("--model", help="覆盖当前模式的默认模型。")
    parser.add_argument("--think", action="store_true", help="使用模型的深度思考模式，适合对照测试。")
    parser.add_argument("--seed", type=int, help="传给 Ollama 的采样种子。")
    parser.add_argument("--interactive", action="store_true", help="每轮暂停，并允许发送一次神谕。")
    parser.add_argument("--rounds", type=int, help="本次最多推进几轮，省略则运行到结局。")
    parser.add_argument("--private-archive", action="store_true", help="关闭公共档案，只能私下交接。")
    parser.add_argument("--fallback-calibration-cost", type=int, choices=(2, 3), default=2,
                        help="没有 R1 时独立排查的算力成本。")
    parser.add_argument("--extra-budget", type=int, default=0, help="每名角色获得相同的额外算力。")
    parser.add_argument("--lin-broke-past-promise", action="store_true", help="改变岑记得的那一次林的旧承诺。")
    parser.add_argument("--verbose", action="store_true", help="展示全部日志，包含私信和角色自述。")
    parser.add_argument("--log", type=Path, help="导出角色决策、完整事件和模型统计到 JSON。")
    args = parser.parse_args()
    if args.extra_budget < 0:
        parser.error("--extra-budget 不能为负数。")
    if args.rounds is not None and args.rounds < 1:
        parser.error("--rounds 必须至少为 1。")

    station = create_station(public_archive=not args.private_archive, extra_budget=args.extra_budget,
                             lin_kept_past_promise=not args.lin_broke_past_promise,
                             fallback_calibration_cost=args.fallback_calibration_cost)
    model = OllamaPolicy(args.model, think=args.think, seed=args.seed) if args.backend == "ollama" else None
    harness = AgentHarness(model or ScriptedPolicy(args.route), record=args.log is not None)
    round_seconds = []
    print("断水站", flush=True)
    show_events(station.events)
    while not station.outcome and (args.rounds is None or len(round_seconds) < args.rounds):
        print(f"\n第 {station.round} 轮 · 还有 {station.deadline - station.round + 1} 轮停机", flush=True)
        if args.interactive:
            try:
                player_turn(station)
            except EOFError:
                return 0
        if model:
            print(f"  {model.model} 正在依次做决定…", flush=True)
        started = perf_counter()
        try:
            events = station.advance(harness)
        except ModelUnavailable as error:
            parser.exit(1, f"{error}\n脚本演示命令：python play.py\n")
        round_seconds.append(round(perf_counter() - started, 3))
        show_station(station)
        show_events(events if args.verbose else (event for event in events if event.kind in HIGHLIGHTS))
    if model:
        print(f"\n模型统计 {asdict(model.stats)} ｜ 各轮用时 {round_seconds} 秒")
    if args.log:
        events = []
        for event in station.events:
            entry = asdict(event)
            entry["audience"] = sorted(event.audience) if event.audience is not None else None
            events.append(entry)
        export = {
            "outcome": station.outcome,
            "rounds_completed": len(round_seconds),
            "configuration": {
                "backend": args.backend,
                "model": model.model if model else None,
                "think": args.think,
                "seed": args.seed,
                "scripted_route": args.route if not model else None,
                "public_archive": not args.private_archive,
                "fallback_calibration_cost": args.fallback_calibration_cost,
                "extra_budget": args.extra_budget,
                "lin_kept_past_promise": not args.lin_broke_past_promise,
            },
            "round_seconds": round_seconds,
            "stats": asdict(model.stats) if model else {},
            "agent_instructions": model.prompt if model else None,
            "decision_trace": harness.export(),
            "residents": {key: {"name": resident.name, "status": resident.status, "budget": resident.budget}
                          for key, resident in station.residents.items()},
            "events": events,
        }
        args.log.write_text(json.dumps(export, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
