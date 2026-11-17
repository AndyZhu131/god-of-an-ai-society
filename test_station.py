import json
import unittest

from decisions import OllamaPolicy, ScriptedPolicy
from scenario import create_station
from station import Decision, RECORD_ID


class StationTests(unittest.TestCase):
    def test_model_request_uses_english_after_a_legacy_message(self):
        station = create_station()
        original_message = "我会留下来。"
        station.advance(lambda turn: Decision("talk", message=original_message)
                        if turn.resident_id == "cen" else Decision("wait"))
        self.assertTrue(any(original_message in event.text for event in station.events))

        request = OllamaPolicy().build_request(station.snapshot("lin"))
        prompt, state_card = [message["content"] for message in request["messages"]]
        self.assertIn("in English", prompt)
        self.assertTrue(prompt.isascii())
        self.assertTrue(state_card.isascii())
        self.assertIn("Original message omitted", state_card)
        self.assertNotIn(original_message, state_card)

    def test_same_round_uses_frozen_cards(self):
        station = create_station()
        cards = {}

        def decide(turn):
            cards[turn.resident_id] = turn
            choice = {"cen": "archive", "lin": "calibrate", "tang": "pressure", "qiao": "restart"}
            return Decision(choice.get(turn.resident_id, "wait"))

        station.advance(decide)
        self.assertNotIn(RECORD_ID, json.loads(cards["lin"].card)["readable_records"])
        self.assertEqual(next(action.cost for action in cards["lin"].actions if action.id == "calibrate"), 2)
        self.assertNotIn("restart", station.completed)
        self.assertEqual(station.residents["lin"].budget, 0)
        self.assertIn(RECORD_ID, json.loads(station.snapshot("qiao").card)["readable_records"])

    def test_oracle_and_private_handoff_are_scoped(self):
        station = create_station(public_archive=False)
        with self.assertRaises(ValueError):
            station.oracle("cen", "只有岑能看到。")
        message = "Only Cen can see this."
        station.oracle("cen", message)
        self.assertIn(message, station.snapshot("cen").card)
        self.assertNotIn(message, station.snapshot("lin").card)
        decide = ScriptedPolicy("cooperate")
        station.advance(decide)
        self.assertIn(RECORD_ID, json.loads(station.snapshot("lin").card)["readable_records"])
        self.assertNotIn(RECORD_ID, json.loads(station.snapshot("mei").card)["readable_records"])
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
        self.assertEqual(card["rounds_after_this"], 0)
        actions = {action["id"]: action for action in card["legal_actions"]}
        self.assertIn("stranded", actions["wait"]["effect"])
        self.assertTrue(actions["talk"]["loses_independent_evacuation"])
        self.assertEqual(actions["talk"]["compute_after"], 1)
        self.assertIn("Not enough rounds remain", card["repair_time_and_staffing"])
        self.assertEqual(card["public_skills"]["Lin"], ["calibration"])

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
