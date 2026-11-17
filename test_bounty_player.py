import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agents import AgentHarness, Decision
from scenarios.after_the_bounty import __main__ as bounty_cli
from scenarios.after_the_bounty.engine import Island
from scenarios.after_the_bounty.player import PlayerSession, earned_legacies, evaluate_goal, load_legacy


class TestPolicy(bounty_cli.IslandPolicy):
    plan = {
        (1790, "lin"): "practice_carpentry", (1791, "lin"): "practice_carpentry",
        (1790, "kai"): "practice_navigation", (1791, "kai"): "practice_navigation",
        (1792, "lin"): "repair", (1792, "kai"): "survey",
        (1796, "kai"): "shelter:kai", (1796, "mara"): "shelter:mara",
        (1798, "lin"): "teach:carpentry:mara", (1799, "mara"): "repair",
        (1804, "mara"): "shelter:mara", (1804, "kai"): "shelter:kai",
        (1805, "mara"): "repair",
    }

    def __call__(self, turn):
        resident = turn.resident_id
        phase = json.loads(turn.card)["phase"]
        if phase == "council":
            return Decision("announce:shelter:kai" if resident == "kai" else "pass")
        if phase == "contact":
            return Decision("contact" if resident == "kai" else "wait")
        if phase == "departure":
            return Decision("leave" if resident == "kai" else "stay")
        return Decision(self.plan.get((turn.round_number, resident), "wait"))


class BountyPlayerTests(unittest.TestCase):
    def test_full_player_cli_can_spend_both_interventions_and_inherit_a_card(self):
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            legacy_file = Path(directory) / "legacy.json"
            log = Path(directory) / "play.json"
            argv = ["bounty", "--play", "--legacy-file", str(legacy_file), "--log", str(log)]
            console = io.StringIO()
            with patch("sys.argv", argv), patch.object(bounty_cli, "IslandPolicy", TestPolicy), patch(
                "builtins.input", side_effect=["2", "1", "", "1", "2", "1"]
            ), redirect_stdout(console):
                bounty_cli.main()
            report = json.loads(log.read_text(encoding="utf8"))
            player = report["player"]
            self.assertEqual(len(report["years"]), 18)
            self.assertEqual(player["goal"], "legacy")
            self.assertTrue(player["goal_result"]["achieved"])
            self.assertEqual(player["interventions_left"], 0)
            self.assertEqual([choice["kind"] for choice in player["interventions"]], ["council", "postpone"])
            self.assertEqual([e["year"] for e in report["events"] if e["kind"] == "storm"], [1798, 1804])
            council_cards = [d["card"] for d in report["decisions"] if d["card"]["phase"] == "council"]
            self.assertEqual(len(council_cards), 11)
            self.assertTrue(all("council" not in card and not card["shelter_ready_for"] for card in council_cards))
            regular = next(d["card"] for d in report["decisions"]
                           if d["round"] == 1796 and d["resident"] == "mara" and d["card"]["phase"] == "year")
            self.assertIn("kai", regular["council"]["announced_intentions"])
            self.assertNotIn("kai", regular["shelter_ready_for"])
            completed = next(e for e in report["events"] if e["kind"] == "council_review")
            self.assertEqual(list(completed["followed"]), ["kai"])
            self.assertEqual(report["ending"]["left"], ["kai"])
            self.assertIn("达成", console.getvalue())
            legacy = load_legacy(legacy_file)
            self.assertEqual((legacy.influence, legacy.resident), ("apprentice", "lin"))
            self.assertEqual(legacy.source_log, str(log))
            self.assertIn(legacy.evidence[-1], player["goal_result"]["evidence"])

            next_island = Island(seed=32)
            with patch("builtins.input", side_effect=["1", "4", ""]), redirect_stdout(io.StringIO()):
                next_player = PlayerSession.start(next_island, legacy_file)
            self.assertTrue(next_player.inherited)
            self.assertEqual(next_player.resident, "tavi")
            self.assertEqual(next_player.export()["legacy_origin"]["source_log"], str(log))
            recipient = json.loads(next_island.observe("tavi", "year", next_island.present()).card)
            other = json.loads(next_island.observe("lin", "year", next_island.present()).card)
            self.assertIn("teaching a younger resident", recipient["personal_disposition"])
            self.assertNotIn("personal_disposition", other)
            self.assertEqual(recipient["people"]["tavi"]["skills"], [])
            self.assertNotIn("goal_result", recipient)

    def test_postponement_and_council_share_a_budget(self):
        island = Island(seed=17)
        player = PlayerSession(island, "survive", "protect", "bess")
        harness = AgentHarness(lambda _: Decision("pass"))
        self.assertEqual(player.available_interventions(), [])
        island.year = 1796
        player.intervene("postpone", harness)
        self.assertEqual(player.remaining, 1)
        self.assertIsNone(island.forecast())
        island.year = 1797
        self.assertEqual(player.available_interventions(), ["council"])
        player.intervene("council", harness)
        self.assertEqual(player.remaining, 0)
        with self.assertRaises(ValueError):
            player.intervene("council", harness)

    def test_archived_knowledge_credits_earlier_teachers(self):
        island = Island(seed=17)
        lesson = island.emit("taught", teacher="lin", target="sol", skill="carpentry")
        archive = island.emit("archived", refs=(lesson,), resident="sol", skill="carpentry")
        study = island.emit("studied", refs=(archive,), resident="mara", skill="carpentry")
        island.year = 1798
        exit_event = island.emit("departed", resident="lin", cause="lifespan")
        island.year = 1805
        work = island.emit("repaired", refs=(study,), resident="mara")
        island.ending = {"left": ["kai"], "stayed": ["mara"], "skills_remaining": ["carpentry", "navigation"]}
        self.assertEqual(evaluate_goal("legacy", island)["evidence"], [lesson, exit_event, work])
        self.assertTrue(evaluate_goal("stay_and_leave", island)["achieved"])
        self.assertFalse(evaluate_goal("survive", island)["achieved"])
        self.assertEqual({(card.influence, card.resident) for card in earned_legacies(island.events)},
                         {("apprentice", "lin"), ("open_archive", "sol")})

    def test_council_uses_separate_model_instructions(self):
        island = Island(seed=17)
        island.year = 1796
        turn = island.observe("kai", "council", island.present())
        request = bounty_cli.IslandPolicy().build_request(turn)
        self.assertIn("Announcing an intention", request["messages"][0]["content"])
        fields = request["format"]["properties"]
        self.assertIn("announce:shelter:kai", fields["action_id"]["enum"])
        self.assertEqual(fields["pledge"]["enum"], [""])


if __name__ == "__main__":
    unittest.main()
