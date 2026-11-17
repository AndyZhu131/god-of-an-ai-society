import json
import unittest
from unittest.mock import patch

from agents import Agent, AgentHarness, Decision
from decisions import ModelUnavailable, OllamaPolicy
from scenario import create_station
from scenarios.archive import RETIRE_ROUND, Archive
from scenarios.commons import Commons


class AgentHarnessTests(unittest.TestCase):
    def test_agent_rejects_another_residents_card(self):
        world = Commons(2)
        agent = Agent("P01", lambda turn: Decision("wait"))
        with self.assertRaisesRegex(ValueError, "another resident"):
            agent.decide(world.snapshot("P02"))

    def test_trace_records_frozen_inputs_messages_and_settlement(self):
        world = Commons(2)

        def decide(turn):
            if turn.resident_id == "P01":
                return Decision("maintain", message="The stock needs help.", reason="I have enough food.")
            return Decision("harvest", reason="I am low on food.")

        harness = AgentHarness(decide)
        world.advance(harness)
        first, second = harness.export()
        self.assertEqual(first["round"], 1)
        self.assertEqual(first["decision"]["reason"], "I have enough food.")
        self.assertEqual(first["outcome"]["status"], "applied")
        self.assertTrue(first["outcome"]["details"]["posted"])
        self.assertEqual(second["card"]["recent_board_posts"], [])
        self.assertEqual(second["outcome"]["details"]["food_after_meal"], 3)
        next_card = json.loads(world.snapshot("P02").card)
        self.assertEqual(next_card["recent_board_posts"][0]["message"], "The stock needs help.")
        self.assertNotIn("I have enough food.", world.snapshot("P02").card)

    def test_station_trace_links_rejected_actions_and_conflicts(self):
        world = create_station()
        choices = {"tang": "pressure", "yu": "pressure", "cen": "unknown"}
        harness = AgentHarness(lambda turn: Decision(choices.get(turn.resident_id, "wait")))
        events = {event.id: event for event in world.advance(harness)}
        records = {entry["resident"]: entry for entry in harness.export()}
        rejected = records["cen"]
        self.assertFalse(rejected["legal"])
        self.assertEqual(rejected["decision"]["action_id"], "unknown")
        self.assertEqual(rejected["outcome"]["action_id"], "wait")
        self.assertEqual(events[rejected["outcome"]["event_ids"][0]].kind, "invalid")
        collision = records["yu"]["outcome"]
        self.assertEqual(collision["status"], "conflict")
        self.assertEqual(collision["details"]["budget_spent"], 0)
        self.assertEqual(events[collision["event_ids"][0]].kind, "collision")

    def test_archive_turnover_can_be_retried_after_a_provider_error(self):
        world = Archive(4, seed=17)
        world.round = RETIRE_ROUND

        def unavailable(turn):
            if turn.resident_id in world.arrivals:
                raise ModelUnavailable("offline")
            return Decision("wait")

        with self.assertRaises(ModelUnavailable):
            world.advance(AgentHarness(unavailable))
        self.assertEqual(world.round, RETIRE_ROUND)
        self.assertTrue(set(world.departures) <= world.residents.keys())
        harness = AgentHarness(lambda turn: Decision("wait"))
        result = world.advance(harness)
        self.assertEqual(result["turnover"]["departures"], world.departures)
        self.assertEqual(set(result["turnover"]["arrivals"]), set(world.arrivals))
        self.assertTrue(set(world.departures).isdisjoint(world.residents.keys()))
        self.assertEqual(len(harness.export()), 4)

    def test_model_retries_invalid_action_and_exposes_only_returned_explanation(self):
        turn = Commons(2).snapshot("P01")
        policy = OllamaPolicy(prompt="Choose one legal action.")
        invalid = {"message": {"content": '{"action_id":"unknown","message":"","reason":""}'}}
        valid = {"message": {"content": '{"action_id":"wait","message":"","reason":"I can wait."}',
                             "thinking": "provider-internal text"}}
        requests = []

        def chat(body):
            requests.append(json.loads(json.dumps(body)))
            return (invalid, valid)[len(requests) - 1]

        harness = AgentHarness(policy)
        with patch.object(policy, "chat", side_effect=chat):
            harness.decide(turn)
        first, retry = requests
        self.assertEqual(first["messages"], [{"role": "system", "content": policy.prompt},
                                             {"role": "user", "content": turn.card}])
        self.assertEqual(first["format"]["properties"]["action_id"]["enum"],
                         [action.id for action in turn.actions])
        self.assertIn("required schema", retry["messages"][0]["content"])
        self.assertEqual((policy.stats.calls, policy.stats.invalid, policy.stats.retries), (2, 1, 1))
        trace, = harness.export()
        self.assertEqual(trace["decision"]["reason"], "I can wait.")
        self.assertNotIn("provider-internal text", json.dumps(trace))


if __name__ == "__main__":
    unittest.main()
