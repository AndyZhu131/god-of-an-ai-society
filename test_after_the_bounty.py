import json
import unittest
from unittest.mock import patch

from agents import AgentHarness, Decision
from scenarios.after_the_bounty.__main__ import IslandPolicy, PROMPT, health_claim_error
from scenarios.after_the_bounty.engine import CONTACT_YEAR, Island, IslandDecision


class AfterTheBountyTests(unittest.TestCase):
    def test_votes_reserve_next_years_seats_and_block_work(self):
        island = Island(seed=17)
        first_cards = {}

        def propose(turn):
            first_cards[turn.resident_id] = json.loads(turn.card)
            if turn.resident_id == "sol":
                return IslandDecision("wait", pledge="practice_carpentry", nominees=("ana", "sol"))
            return Decision("wait")

        island.advance(propose)
        self.assertEqual(len(first_cards), 10)
        self.assertTrue(all(not card["proposals_to_vote_on"] for card in first_cards.values()))
        proposal = next(iter(island.proposals))

        def vote(turn):
            if turn.resident_id in {"ana", "sol"}:
                return Decision(f"support:{proposal}")
            if turn.resident_id == "lin":
                return Decision("guard")
            if turn.resident_id == "noa":
                return IslandDecision("wait", pledge="practice_carpentry")
            return Decision("wait")

        island.advance(vote)
        self.assertEqual(island.reservations, ("ana", "sol"))
        result = next(event for event in island.events if event["kind"] == "took_workshop")
        self.assertEqual(result["refs"], [proposal])
        self.assertEqual(result["reserved_year"], 1792)
        self.assertTrue(any(event["kind"] == "broke_pledge" and event["resident"] == "sol"
                            for event in island.events))

        applicants = {"ana", "sol", "lin", "noa"}
        island.advance(lambda turn: Decision("practice_carpentry" if turn.resident_id in applicants else "wait"))
        self.assertEqual({key for key in applicants if "carpentry" in island.residents[key].practice}, {"ana", "sol"})
        self.assertEqual(island.reservations, ())
        blocked = [event for event in island.events if event["kind"] == "blocked_pledge"]
        self.assertEqual([(event["resident"], event["cause"]) for event in blocked], [("noa", "attempt_conflicted")])

    def test_last_year_lesson_is_used_after_teachers_exit_and_contact_can_succeed(self):
        island = Island(seed=17)
        plan = {
            (1790, "lin"): "practice_carpentry", (1791, "lin"): "practice_carpentry",
            (1790, "kai"): "practice_navigation", (1791, "kai"): "practice_navigation",
            (1792, "lin"): "repair", (1792, "kai"): "survey",
            (1797, "mara"): "shelter:mara", (1797, "kai"): "shelter:kai",
            (1798, "lin"): "teach:carpentry:mara", (1799, "mara"): "repair",
            (1804, "mara"): "shelter:mara", (1804, "kai"): "shelter:kai",
            (1805, "mara"): "repair",
        }

        def decide(turn):
            key = turn.resident_id
            phase = json.loads(turn.card)["phase"]
            if phase == "contact":
                return Decision("contact" if key == "kai" else "wait")
            if phase == "departure":
                return Decision("leave" if key == "kai" else "stay")
            return Decision(plan.get((turn.round_number, key), "wait"))

        harness = AgentHarness(decide)
        while island.year < CONTACT_YEAR:
            island.advance(harness)
        lesson = next(event for event in island.events if event["kind"] == "taught")
        repair = next(event for event in island.events if event["kind"] == "repaired" and event["year"] == 1805)
        self.assertEqual(lesson["year"], 1798)
        self.assertEqual(repair["refs"], [lesson["id"]])
        self.assertEqual(island.residents["lin"].status, "aged_out")
        frozen = next(trace for trace in harness.traces
                      if trace.turn.round_number == 1798 and trace.turn.resident_id == "mara")
        self.assertNotIn("repair", {action.id for action in frozen.turn.actions})

        ending = island.finish(harness)
        self.assertEqual(ending["representative"], "kai")
        self.assertEqual(ending["left"], ["kai"])
        self.assertEqual(ending["skills_remaining"], ["carpentry"])

    def test_forecast_delay_preserves_shelter_until_the_storm(self):
        island = Island(seed=17, delay_storm=1797)
        island.year = 1796
        island.advance(lambda turn: Decision("shelter:iona" if turn.resident_id == "ana" else "wait"))
        island.advance(lambda _: Decision("wait"))
        self.assertIn("iona", island.sheltered)
        self.assertEqual(island.residents["lin"].health, 2)
        island.advance(lambda _: Decision("wait"))
        self.assertEqual(island.residents["iona"].health, 2)
        self.assertEqual(island.residents["lin"].health, 1)
        self.assertFalse(island.sheltered)

    def test_local_request_carries_the_island_contract(self):
        island = Island(seed=17)
        turn = island.observe("lin", "year", island.present())
        policy = IslandPolicy(prompt=PROMPT)
        request = policy.build_request(turn)
        self.assertTrue(all(message["content"].isascii() for message in request["messages"]))
        self.assertEqual(request["format"]["required"][0], "health_readback")
        self.assertEqual(set(request["format"]["required"]),
                         {"health_readback", "action_id", "message", "reason", "pledge", "nominees"})
        health = json.loads(turn.card)["your_health"]
        self.assertEqual(health, {"current": 2, "maximum": 2, "wait_restores_health": False})
        self.assertIn("does not restore health", json.loads(turn.card)["legal_actions"]["wait"])
        decision = policy.decode_decision({"action_id": "wait", "message": "", "reason": "Rest.",
                                           "pledge": "", "nominees": ["ana", "sol"], "health_readback": health})
        self.assertEqual(decision.nominees, ("ana", "sol"))

    def test_false_health_readback_gets_corrected_before_accepting_action(self):
        island = Island(seed=17)
        turn = island.observe("kai", "year", island.present())
        policy = IslandPolicy(prompt=PROMPT)
        correct = {"current": 2, "maximum": 2, "wait_restores_health": False}
        output = {"action_id": "practice_navigation", "message": "", "reason": "Keep the sea route usable.",
                  "pledge": "", "nominees": [], "health_readback": correct}
        responses = iter(({**output, "health_readback": {**correct, "current": 1}}, output))
        prompts = []

        def respond(request):
            prompts.append(request["messages"][0]["content"])
            return {"message": {"content": json.dumps(next(responses))}}

        with patch.object(policy, "chat", side_effect=respond):
            decision = policy(turn)
        self.assertEqual(decision.action_id, "practice_navigation")
        self.assertEqual(decision.health_readback, correct)
        self.assertEqual(policy.stats.retries, 1)
        self.assertEqual(policy.health_rejections[0]["check"], "readback")
        self.assertIn("2/2", prompts[1])
        self.assertIn("does not restore health", prompts[1])

    def test_correct_readback_does_not_allow_false_health_claims_in_either_text_field(self):
        island = Island(seed=17)
        island.residents["mara"].health = 1
        turn = island.observe("kai", "year", island.present())
        policy = IslandPolicy(prompt=PROMPT)
        output = {"action_id": "wait", "message": "", "reason": "I will stay put.", "pledge": "", "nominees": [],
                  "health_readback": {"current": 2, "maximum": 2, "wait_restores_health": False}}
        responses = [
            {**output, "message": "Health is currently low, and it's risky to work on carpentry."},
            {**output, "reason": "I need to regain some health before taking any further actions."},
        ]
        with patch.object(policy, "chat", side_effect=[
            {"message": {"content": json.dumps(response)}} for response in responses
        ]):
            decision = policy(turn)
        self.assertEqual(decision.action_id, "")
        self.assertEqual(policy.stats.invalid, 2)
        self.assertEqual([item["check"] for item in policy.health_rejections], ["low_health_claim", "wait_recovery_claim"])

        response = {**output, "action_id": "practice_navigation",
                    "reason": "Mara's health is low. I have the strength to learn navigation."}
        with patch.object(policy, "chat", return_value={"message": {"content": json.dumps(response)}}):
            self.assertEqual(policy(turn).action_id, "practice_navigation")

    def test_rejects_real_playtest_health_claims_but_allows_cautious_waiting(self):
        cases = (
            (2, "My health is currently injured and I cannot take on any new tasks this year.", "low_health_claim"),
            (2, "My health is at full capacity and I'm currently injured.", "low_health_claim"),
            (1, "Current health status prevents any productive actions for this year.", "health_blocks_action_claim"),
            (1, "Focus on rest and recovery this year.", "wait_recovery_claim"),
            (1, "I must rest this year to fully recover before taking further actions.", "wait_recovery_claim"),
            (1, "Waiting this year would allow her health to potentially recover next year.", "wait_recovery_claim"),
            (2, "I need to rest and recover fully before taking any further actions.", "wait_recovery_claim"),
            (1, "This will give me time to recover and conserve resources.", "wait_recovery_claim"),
            (1, "Resting will help me recover and prepare for crucial actions next year.", "wait_recovery_claim"),
            (1, "Rest is necessary to recover before taking any significant risks.", "wait_recovery_claim"),
            (1, "I have full health.", "full_health_claim"),
            (1, "My health is low. I do not want to volunteer.", None),
            (1, "Waiting does not restore health. I prefer to stay on the island.", None),
        )
        for current, reason, expected in cases:
            with self.subTest(reason=reason):
                self.assertEqual(health_claim_error("kai", IslandDecision("wait", reason=reason),
                                                   current=current, maximum=2), expected)

    def test_shelter_plan_separates_completed_work_and_next_year_pledges(self):
        island = Island(seed=17)
        island.year = 1796
        island.residents["iona"].health = 1
        island.residents["kai"].health = 1
        cards = {}

        def forecast_year(turn):
            cards[turn.resident_id] = json.loads(turn.card)
            if turn.resident_id == "ana":
                return IslandDecision("shelter:mara", pledge="shelter:iona")
            return Decision("wait")

        island.advance(forecast_year)
        self.assertFalse(cards["kai"]["storm_plan"]["pledges_by_target"])
        turn = island.observe("kai", "year", island.present())
        card = json.loads(turn.card)
        plan = card["storm_plan"]
        self.assertEqual(card["shelter_ready_for"], ["mara"])
        self.assertEqual(plan["pledges_by_target"]["iona"][0]["volunteer"], "ana")
        self.assertNotIn("iona", island.sheltered)
        self.assertNotIn("iona", plan["uncovered_without_pledge"])
        self.assertIn("kai", plan["uncovered_without_pledge"])
        self.assertEqual(plan["would_die_if_unprotected"], ["iona", "kai"])
        self.assertIn("shelter:iona", card["legal_actions"])
        self.assertNotIn("shelter:kai", card["pledge_action_ids"])

        island.advance(lambda turn: Decision("shelter:kai" if turn.resident_id == "kai" else "wait"))
        self.assertEqual(island.residents["iona"].status, "lost_to_storm")
        self.assertEqual(island.residents["kai"].health, 1)
        failure = next(event for event in island.events if event["kind"] == "broke_pledge")
        self.assertEqual(failure["resident"], "ana")

    def test_model_pledge_schema_uses_the_cards_allowed_actions(self):
        island = Island(seed=17)
        island.year = 1796
        turn = island.observe("lin", "year", island.present())
        request = IslandPolicy(prompt=PROMPT).build_request(turn)
        allowed = request["format"]["properties"]["pledge"]["enum"]
        self.assertIn("", allowed)
        self.assertIn("shelter:mara", allowed)
        self.assertNotIn("wait", allowed)
        self.assertNotIn("my own words", allowed)

    def test_arrival_is_visible_only_in_the_finale(self):
        island = Island(seed=17)
        annual_card = json.loads(island.observe("lin", "year", island.present()).card)
        self.assertNotIn("encounter", annual_card)
        island.year = CONTACT_YEAR
        contact_card = json.loads(island.observe("eli", "contact", island.present()).card)
        self.assertTrue(contact_card["encounter"]["visible_now"])
        self.assertIn("no later chance", contact_card["encounter"]["decision"])
        self.assertIn("does not cost health", contact_card["encounter"]["decision"])
        self.assertIn("Rest does not restore", PROMPT)
        departure_card = json.loads(island.observe("eli", "departure", island.present()).card)
        self.assertTrue(departure_card["encounter"]["contact_made"])


if __name__ == "__main__":
    unittest.main()
