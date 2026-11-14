import json
import unittest

from decisions import ScriptedPolicy
from scenario import create_station
from station import Decision, RECORD_ID


class StationTests(unittest.TestCase):
    def test_same_round_uses_frozen_cards(self):
        station = create_station()
        cards = {}

        def decide(turn):
            cards[turn.resident_id] = turn
            choice = {"cen": "archive", "lin": "calibrate", "tang": "pressure", "qiao": "restart"}
            return Decision(choice.get(turn.resident_id, "wait"))

        station.advance(decide)
        self.assertNotIn(RECORD_ID, json.loads(cards["lin"].card)["可读记录"])
        self.assertEqual(next(action.cost for action in cards["lin"].actions if action.id == "calibrate"), 2)
        self.assertNotIn("restart", station.completed)
        self.assertEqual(station.residents["lin"].budget, 0)
        self.assertIn(RECORD_ID, json.loads(station.snapshot("qiao").card)["可读记录"])

    def test_oracle_and_private_handoff_are_scoped(self):
        station = create_station(public_archive=False)
        station.oracle("cen", "只有岑能看到。")
        self.assertIn("只有岑能看到", station.snapshot("cen").card)
        self.assertNotIn("只有岑能看到", station.snapshot("lin").card)
        decide = ScriptedPolicy("cooperate")
        station.advance(decide)
        self.assertIn(RECORD_ID, json.loads(station.snapshot("lin").card)["可读记录"])
        self.assertNotIn(RECORD_ID, json.loads(station.snapshot("mei").card)["可读记录"])
        events = station.advance(decide)
        self.assertEqual(station.promises[0].status, "condition_unmet")
        public_events = {event.id for event in station.events if event.audience is None}
        for event in events:
            if event.audience is None:
                self.assertLessEqual(set(event.refs), public_events)

    def test_simultaneous_work_only_charges_the_contributor(self):
        station = create_station()
        station.advance(lambda turn: Decision("pressure" if turn.resident_id in {"tang", "yu"} else "wait"))
        self.assertEqual(station.residents["tang"].budget, 1)
        self.assertEqual(station.residents["yu"].budget, 2)
        self.assertEqual(station.contributors["pressure"], "tang")

    def test_card_shows_terminal_consequences_and_action_cost(self):
        station = create_station()
        station.round = station.deadline
        card = json.loads(station.snapshot("cen").card)
        self.assertEqual(card["本轮之后还能行动几轮"], 0)
        actions = {action["id"]: action for action in card["合法动作"]}
        self.assertIn("受困", actions["wait"]["结算"])
        self.assertTrue(actions["talk"]["失去独立撤离"])
        self.assertEqual(actions["talk"]["执行后算力"], 1)
        self.assertIn("轮数不足", card["工程时限与人手"])
        self.assertEqual(card["公开分工"]["林"], ["校准"])

    def test_expensive_fallback_makes_shared_record_change_available_actions(self):
        station = create_station(fallback_calibration_cost=3)
        self.assertNotIn("calibrate", {action.id for action in station.actions_for("mei")})
        station.advance(lambda turn: Decision("archive" if turn.resident_id == "cen" else "wait"))
        calibration = next(action for action in station.actions_for("mei") if action.id == "calibrate")
        self.assertEqual(calibration.cost, 1)

    def test_scripted_outcomes(self):
        cases = (("cooperate", "restored", 3, "fulfilled"),
                 ("withdraw", "restored", 4, "unkept"),
                 ("shutdown", "shutdown", 4, "unkept"))
        for route, outcome, rounds, promise_status in cases:
            with self.subTest(route=route):
                station = create_station()
                decide = ScriptedPolicy(route)
                while not station.outcome:
                    station.advance(decide)
                self.assertEqual(station.outcome, outcome)
                self.assertEqual(station.round - 1, rounds)
                self.assertEqual(station.promises[0].status, promise_status)


if __name__ == "__main__":
    unittest.main()
