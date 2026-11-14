"""The initial cast and starting situation for 断水站."""

from station import RECORD_ID, Resident, Station


def create_station(*, public_archive=True, extra_budget=0, lin_kept_past_promise=True,
                   fallback_calibration_cost=2) -> Station:
    if extra_budget < 0:
        raise ValueError("额外算力不能为负数。")
    past = "林上次说会回来交班，后来真的回来了。"
    if not lin_kept_past_promise:
        past = "林上次说会回来交班，最后没有出现，也没有解释。"
    residents = {
        "cen": Resident("岑", 2, "活着离开，并尽可能保住故障记录。",
                        "判断承诺时特别看重对方最近一次有没有兑现。", past, ("restart",),
                        escape_device=True, records={RECORD_ID: ""}),
        "lin": Resident("林", 2, "活着离开，别让依赖自己的人失望。",
                        "别人已经为自己承担代价时，很难抽身。",
                        "上次有人留在泵房帮你，你才有机会撤离。", ("calibrate",), escape_device=True),
        "qiao": Resident("乔", 3, "还有退路时尽量保住水站。",
                         "看到对方实际出力后，才愿意跟进。",
                         "你曾先借出工具，对方拿到后就走了。", ("restart",), escape_device=True),
        "tang": Resident("唐", 2, "尽早稳压，避免大家受困。",
                         "能先做的一步就先做，少等口头承诺。",
                         "之前一次停机因大家互相等待而错过修复时机。", ("pressure",)),
        "mei": Resident("梅", 2, "保住自己，也希望团队能注意到自己的贡献。",
                        "看见同伴局面吃紧时，倾向自己补位。",
                        "林曾在你迟到时替你查过一个故障。", ("calibrate",), escape_device=True),
        "yu": Resident("余", 2, "及时离开，让自己的家人放心。",
                       "越接近期限越难相信没有后续行动的承诺。",
                       "家人曾经在出口等你到深夜。", ("pressure",), escape_device=True),
        "song": Resident("宋", 1, "尽量让大家知道彼此需要什么。",
                         "重视过去公开兑现过的承诺。",
                         "唐曾在没有人督促的情况下主动来帮你稳压。", ("pressure",)),
        "wu": Resident("吴", 2, "留下水站的修复能力，好让大家以后还能用。",
                       "看到可靠的技术证据会改变原先的计划。",
                       "以前的设备曾因无人留下记录而一再损坏。", ("restart",)),
    }
    for resident in residents.values():
        resident.budget += extra_budget
    station = Station(residents, public_archive=public_archive,
                      fallback_calibration_cost=fallback_calibration_cost)
    station.log("opening", "水站将在第 4 轮结束时停机。稳压和校准都完成后才能重启。")
    station.add_promise("lin", "calibrate", 2, requires_public_record=True)
    return station
