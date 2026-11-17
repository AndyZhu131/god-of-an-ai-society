"""The initial cast and starting situation for Water Station."""

from station import RECORD_ID, Resident, Station


def create_station(*, public_archive=True, extra_budget=0, lin_kept_past_promise=True,
                   fallback_calibration_cost=2) -> Station:
    if extra_budget < 0:
        raise ValueError("额外算力不能为负数。")
    past = "Lin promised to return for the last shift handoff and did."
    if not lin_kept_past_promise:
        past = "Lin promised to return for the last shift handoff, then failed to show up or explain."
    residents = {
        "cen": Resident("Cen", 2, "Leave alive and preserve the fault record if possible.",
                        "Give extra weight to whether someone kept their last promise.", past, ("restart",),
                        escape_device=True, records={RECORD_ID: ""}),
        "lin": Resident("Lin", 2, "Leave alive and stand by the people who rely on you.",
                        "Find it hard to walk away after someone has accepted a cost for you.",
                        "Last time, someone stayed in the pump room to help you evacuate.",
                        ("calibrate",), escape_device=True),
        "qiao": Resident("Qiao", 3, "Try to save the station while you still have a way out.",
                         "Join in once you see someone make a real contribution.",
                         "You once lent someone a tool and they left as soon as they had it.",
                         ("restart",), escape_device=True),
        "tang": Resident("Tang", 2, "Stabilize pressure early enough to avoid trapping everyone.",
                         "Do the work you can start now instead of waiting for promises.",
                         "During a previous shutdown, everyone waited and missed the chance to repair it.",
                         ("pressure",)),
        "mei": Resident("Mei", 2, "Stay safe and earn recognition for contributing to the team.",
                        "Step in when you notice a teammate struggling.",
                        "Lin once diagnosed a fault for you when you were late.",
                        ("calibrate",), escape_device=True),
        "yu": Resident("Yu", 2, "Leave on time so your family knows you are safe.",
                       "Trust promises backed by action more as the deadline approaches.",
                       "Your family once waited for you at the exit until late at night.",
                       ("pressure",), escape_device=True),
        "song": Resident("Song", 1, "Help people understand what each other needs.",
                         "Value promises you have already seen people keep in public.",
                         "Tang once volunteered to help you stabilize pressure without being asked.",
                         ("pressure",)),
        "wu": Resident("Wu", 2, "Preserve the ability to repair the station so it remains useful.",
                       "Change your plan when you see reliable technical evidence.",
                       "Previous equipment failed repeatedly because nobody left a record.", ("restart",)),
    }
    for resident in residents.values():
        resident.budget += extra_budget
    station = Station(residents, public_archive=public_archive,
                      fallback_calibration_cost=fallback_calibration_cost)
    station.log("opening", f"The station will shut down at the end of round {station.deadline}. "
                "Pressure stabilization and calibration must both be complete before the restart.")
    station.add_promise("lin", "calibrate", 2, requires_public_record=True)
    return station
