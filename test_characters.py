import json
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from society.characters import (
    Belief, Character, CharacterTemplate, Emotion, Memory, Plan, Relationship, Traits, load_templates,
)
from society.__main__ import TEMPLATES


class CharacterDataTests(unittest.TestCase):
    def setUp(self):
        self.templates = load_templates(TEMPLATES)
        self.template = self.templates["adaptive_keeper"]

    def test_example_templates_share_values_and_differ_in_adaptability(self):
        other = self.templates["steadfast_keeper"]
        self.assertEqual(self.template.traits, other.traits)
        self.assertEqual(self.template.principles, other.principles)
        self.assertEqual(self.template.goals, other.goals)
        self.assertGreater(self.template.adaptability, other.adaptability)

    def test_residents_do_not_mutate_each_other_or_their_template(self):
        ari = self.template.create("ari")
        ren = self.template.create("ren")
        ari.relationships["kai"] = Relationship(trust=-0.5)
        ari.memories.append(Memory("E1", "Kai chose another task.", 1))
        ari.traits = replace(ari.traits, promise_keeping=1.5)
        ari.principles.clear()
        self.assertFalse(ren.relationships)
        self.assertFalse(ren.memories)
        self.assertEqual(ren.traits.promise_keeping, 2)
        self.assertEqual(self.template.traits.promise_keeping, 2)
        self.assertTrue(ren.principles)
        with self.assertRaises(FrozenInstanceError):
            self.template.adaptability = 0

    def test_json_roundtrip_preserves_live_state_and_baseline(self):
        ari = self.template.create("ari")
        ari.health = 1
        ari.traits = replace(ari.traits, contention=1.5)
        ari.skills["repair"] = "E2"
        ari.relationships["kai"] = Relationship(-0.5, 0.2, ("P1",))
        ari.memories.append(Memory("E3", "Kai promised to return the tool.", 3, "claim", "kai"))
        ari.beliefs["cooperation"] = Belief("Promises need evidence.", 0.6, ("E3",))
        ari.emotions["anger"] = Emotion(1.2, 5)
        ari.location_id = "workshop"
        ari.group_ids.append("settlement")
        ari.plan = Plan("sustainable_cooperation", ("repair", "teach"), 1)
        restored = Character.from_dict(json.loads(json.dumps(ari.to_dict())))
        self.assertEqual(restored, ari)
        restored.memories.clear()
        self.assertEqual(len(ari.memories), 1)
        self.assertEqual(restored.template.traits.contention, 1)
        self.assertEqual(restored.traits.contention, 1.5)

    def test_observation_retains_attribution_and_filters_future_memory_and_expired_emotions(self):
        ari = self.template.create("ari")
        ari.memories = [
            Memory("E1", "A tool changed hands.", 1),
            Memory("E2", "Kai says he will return it.", 2, "claim", "kai"),
            Memory("E3", "The tool was returned.", 3),
        ]
        ari.emotions = {"fear": Emotion(1, 2), "anger": Emotion(1, 4)}
        ari.traits = replace(ari.traits, care=1.5)
        view = ari.model_state(2)
        self.assertEqual(view["your_health"], {"current": 2, "maximum": 2})
        self.assertEqual([item["event_id"] for item in view["memories"]], ["E1", "E2"])
        self.assertEqual(view["memories"][1]["source"], "claim")
        self.assertEqual(view["memories"][1]["speaker_id"], "kai")
        self.assertEqual(set(view["emotions"]), {"anger"})
        self.assertEqual(view["baseline_traits"]["care"], 1)
        self.assertEqual(view["traits"]["care"], 1.5)
        self.assertTrue(json.dumps(view, ensure_ascii=False).isascii())
        self.assertEqual(len(ari.memories), 3)
        self.assertIn("fear", ari.emotions)

    def test_invalid_data_is_rejected_at_creation_and_before_saving(self):
        for value in (-0.1, 2.1, True, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Traits(care=value)
        with self.assertRaises(ValueError):
            replace(self.template, initial_health=3)
        with self.assertRaises(ValueError):
            replace(self.template, goals=(*self.template.goals, *self.template.goals))
        with self.assertRaises(ValueError):
            CharacterTemplate.from_dict({**asdict(self.template), "skills": "carpentry"})
        with self.assertRaises(ValueError):
            Memory("E1", "A promise.", 1, "claim")
        ari = self.template.create("ari")
        ari.health = 0
        with self.assertRaises(ValueError):
            ari.to_dict()
        ari.status = "dead"
        Character.from_dict(ari.to_dict())
        ari.health = 1
        ari.plan = Plan("missing_goal", ("repair",))
        with self.assertRaises(ValueError):
            ari.to_dict()

    def test_future_schema_is_rejected_and_missing_optional_state_defaults(self):
        data = self.template.create("ari").to_dict()
        for version in (True, 2, None):
            with self.subTest(version=version), self.assertRaises(ValueError):
                Character.from_dict({**data, "schema_version": version})
        for field in ("relationships", "memories", "beliefs", "emotions", "goals", "plan"):
            data.pop(field)
        restored = Character.from_dict(data)
        self.assertEqual(restored.relationships, {})
        self.assertIsNone(restored.plan)
        self.assertEqual(restored.template.id, self.template.id)

    def test_cli_creates_and_reloads_a_custom_character(self):
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            output = Path(directory) / "ari.json"
            templates = Path(directory) / "templates.json"
            custom = replace(self.template, id="custom_keeper", name="Custom", adaptability=0.4)
            templates.write_text(json.dumps({"schema_version": 1, "templates": [asdict(custom)]}), encoding="utf8")
            create = subprocess.run(
                [sys.executable, "-X", "utf8", "-m", "society", "--templates", str(templates),
                 "--template", "custom_keeper", "--resident-id", "ari", "--output", str(output)],
                capture_output=True, text=True, encoding="utf8",
            )
            self.assertEqual(create.returncode, 0, create.stderr)
            self.assertEqual(json.loads(create.stdout)["adaptability"], 0.4)
            inspect = subprocess.run(
                [sys.executable, "-X", "utf8", "-m", "society", "--load", str(output)],
                capture_output=True, text=True, encoding="utf8",
            )
            self.assertEqual(inspect.returncode, 0, inspect.stderr)
            self.assertEqual(json.loads(create.stdout), json.loads(inspect.stdout))


if __name__ == "__main__":
    unittest.main()
