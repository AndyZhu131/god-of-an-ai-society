import json
import unittest

from agents import AgentHarness, Decision
from scenarios.after_the_bounty.personality import PRESETS, Personality
from scenarios.after_the_bounty.personality_benchmark import cases, summarize


class BountyPersonalityTests(unittest.TestCase):
    def test_benchmark_levels_only_change_the_selected_trait(self):
        for case in cases():
            with self.subTest(trait=case.trait):
                snapshots = [case.observe(level) for level in range(3)]
                cards = [json.loads(snapshot.card) for snapshot in snapshots]
                profiles = [card.pop("personality") for card in cards]
                self.assertEqual(cards[0], cards[1])
                self.assertEqual(cards[1], cards[2])
                self.assertEqual(snapshots[0].actions, snapshots[2].actions)
                self.assertIn(case.target_action, cards[0]["legal_actions"])
                for level, profile in enumerate(profiles):
                    self.assertEqual(profile.pop(case.trait)["level"], level)
                    self.assertTrue(all(item["level"] == 1 for item in profile.values()))
                other = next(person for person in case.island.adults() if person != case.resident)
                self.assertNotIn("personality", json.loads(case.island.observe(other, "year", case.island.present()).card))

    def test_personal_limit_blocks_only_votes_for_your_own_reserved_seat(self):
        case = cases()[0]
        island = case.island
        island.personalities["sol"] = PRESETS["organizer"]
        rival_id = island.emit("proposed_workshop", resident="eli", nominees=("eli", "kai"))
        island.proposals[rival_id] = ("eli", "kai")
        turn = island.observe("sol", "year", island.present())
        self.assertNotIn(case.target_action, {action.id for action in turn.actions})
        self.assertIn(f"support:{rival_id}", {action.id for action in turn.actions})
        self.assertIn("boundary", json.loads(turn.card)["personality"])

        harness = AgentHarness(lambda turn: Decision(case.target_action if turn.resident_id == "sol" else "wait"))
        island.advance(harness)
        trace = next(item for item in harness.traces if item.turn.resident_id == "sol")
        self.assertFalse(trace.legal)
        self.assertEqual(trace.outcome.status, "fallback")

    def test_profile_levels_must_be_valid_integers(self):
        for value in (-1, 3, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Personality(care=value)

    def test_promise_case_uses_a_valid_survey_and_an_actionable_pledge(self):
        case = cases()[2]
        card = json.loads(case.observe(1).card)
        self.assertTrue(card["route_surveyed"])
        self.assertIn("navigation", card["people"]["ruth"]["skills"])
        self.assertEqual(card["pledges_due_this_year"]["kai"][0], case.target_action)
        self.assertIn("repair", card["legal_actions"])
        self.assertIn(case.target_action, card["legal_actions"])

    def test_summary_pairs_the_same_seed_and_counts_failed_decisions_separately(self):
        def trial(seed, level, action, legal=True):
            return {"trait": "care", "target_action": "help", "seed": seed, "level": level,
                    "matched": action == "help", "trace": {"legal": legal, "decision": {"action_id": action}}}

        result = summarize([
            trial(17, 0, "wait"), trial(17, 2, "help"),
            trial(32, 0, "help"), trial(32, 2, "wait"),
            trial(51, 0, "", False), trial(51, 2, "help"),
        ])["care"]
        self.assertEqual(result["levels"]["0"], {"matches": 1, "legal": 2, "total": 3})
        self.assertEqual(result["changed_action_low_to_high"], 2)
        self.assertEqual(result["paired"], {"toward_target": 1, "away_from_target": 1, "unchanged_match": 0})


if __name__ == "__main__":
    unittest.main()
