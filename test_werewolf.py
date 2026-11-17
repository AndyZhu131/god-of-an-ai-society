import json
import unittest
from collections import Counter

from agents import AgentHarness, Decision
from scenarios.werewolf import DECK, DemoPolicy, Werewolf


class WerewolfTests(unittest.TestCase):
    def test_demo_runs_all_phases_and_preserves_private_information(self):
        game = Werewolf(17)
        harness = AgentHarness(DemoPolicy())
        game.run(harness)
        self.assertEqual(Counter(player.role for player in game.players.values()), Counter(DECK))
        self.assertEqual(game.status, "day_complete")
        self.assertIsNone(game.winner)
        self.assertEqual({event.phase for event in game.events}, {"night", "candidacy", "speech", "vote"})
        self.assertTrue(all(trace.outcome for trace in harness.traces))
        registration = [entry["card"] for entry in harness.export() if entry["card"]["step"] == "registration"]
        self.assertEqual(len(registration), 12)
        for card in registration:
            self.assertFalse(any(event["kind"] in {"dawn", "night_resolution"} for event in card["public_events"]))
            private = {event["kind"] for event in card["private_information"]}
            self.assertEqual("check_result" in private, card["role"] == "seer")
            self.assertEqual("witch_information" in private, card["role"] == "witch")
            self.assertEqual("pack" in private, card["role"] == "wolf")
        speeches = [entry["card"] for entry in harness.export() if entry["card"]["step"] == "day_speech"]
        first, second = speeches[:2]
        self.assertFalse(any(event["step"] == "day_speech" for event in first["public_events"]))
        self.assertTrue(any(event["step"] == "day_speech" and event["seat"] == first["seat"]
                            for event in second["public_events"]))

    def test_sheriff_runoff_excludes_all_initial_candidates_and_publishes_votes_together(self):
        game = Werewolf(17)
        first, second, withdrawn, voter_a, voter_b, *_ = game.living
        scheduled = {
            "registration": {first: "run", second: "run", withdrawn: "run"},
            "withdrawal": {withdrawn: "withdraw"},
            "sheriff_ballot": {voter_a: f"vote_{first}", voter_b: f"vote_{second}"},
            "sheriff_runoff_ballot": {voter_a: f"vote_{second}"},
        }

        def decide(turn):
            return Decision(scheduled.get(json.loads(turn.card)["step"], {}).get(turn.resident_id, "pass"))

        harness = AgentHarness(decide)
        game.elect_sheriff(harness)
        self.assertEqual(game.sheriff, second)
        ballots = [event for event in game.events if event.kind == "ballot"]
        self.assertEqual(len(ballots), 2)
        for event in ballots:
            self.assertTrue({first, second, withdrawn}.isdisjoint(event.data["ballots"]))
        for entry in harness.export():
            card = entry["card"]
            if card["step"] == "sheriff_ballot":
                self.assertFalse(any(event["step"] == "sheriff_ballot" for event in card["public_events"]))

    def test_sheriff_weight_and_fool_immunity(self):
        game = Werewolf(17)
        fool = game.role_seat("fool")
        other, sheriff, voter_a, *_ = [seat for seat in game.living if seat != fool]
        game.sheriff = sheriff
        scheduled = {sheriff: f"vote_{fool}", voter_a: f"vote_{other}"}

        def decide(turn):
            if json.loads(turn.card)["step"] == "exile_ballot":
                return Decision(scheduled.get(turn.resident_id, "pass"))
            return Decision("pass")

        harness = AgentHarness(decide)
        game.exile(harness)
        ballot, = [event for event in game.events if event.kind == "ballot"]
        self.assertEqual(ballot.data["totals"], {fool: 1.5, other: 1.0})
        self.assertEqual(game.exile_target, fool)
        self.assertTrue(game.players[fool].alive)
        self.assertTrue(game.players[fool].revealed)
        self.assertFalse(game.players[fool].can_vote)

    def test_hunter_can_shoot_after_wolf_attack_but_not_after_poison(self):
        for cause in ("wolves", "poison"):
            with self.subTest(cause=cause):
                game = Werewolf(17)
                hunter = game.role_seat("hunter")
                wolf = game.role_seat("wolf")
                game.night_deaths = {hunter: cause}
                game.enter("candidacy", "sheriff_result")
                def decide(turn):
                    if json.loads(turn.card)["step"] == "hunter":
                        return Decision(f"shoot_{wolf}")
                    return Decision("pass")

                harness = AgentHarness(decide)
                game.announce_dawn(harness)
                self.assertFalse(game.players[hunter].alive)
                self.assertEqual(game.players[wolf].alive, cause == "poison")
                dawn, = [event for event in game.events if event.kind == "dawn"]
                self.assertEqual(dawn.data, {"dead": [hunter]})

    def test_campaign_reveal_defers_badge_and_cancels_exile(self):
        game = Werewolf(17)
        wolf = game.role_seat("wolf")
        demo = DemoPolicy()

        def decide(turn):
            allowed = {action.id for action in turn.actions}
            if turn.resident_id == wolf:
                if "run" in allowed:
                    return Decision("run")
                if "explode" in allowed:
                    return Decision("explode")
            return demo(turn)

        game.run(AgentHarness(decide))
        self.assertEqual(game.status, "day_ended_by_reveal")
        self.assertEqual(game.exploded, wolf)
        self.assertTrue(game.badge_pending)
        self.assertIsNone(game.sheriff)
        self.assertFalse(any(event.phase == "vote" for event in game.events))
        self.assertTrue(any(event.kind == "dawn" for event in game.events))

    def test_side_elimination_win_conditions(self):
        for side, winner in (("wolf", "town"), ("villager", "wolves")):
            game = Werewolf(17)
            for player in game.players.values():
                if player.role == side:
                    player.alive = False
            game.check_winner()
            self.assertEqual(game.winner, winner)


if __name__ == "__main__":
    unittest.main()
