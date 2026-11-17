# Character data

The shared character data contract is implemented in [society/characters.py](../society/characters.py). It provides editable initial templates, independent live residents, and JSON save/load with schema version 1.

Personality growth and world-driven scheduling are subsequent steps in the [core simulation plan](core-simulation-plan.md). The existing scenarios continue to use their own resident models.

## Template and live state

| Record | Meaning |
| --- | --- |
| CharacterTemplate | Immutable initial conditions and the provenance of a resident's baseline |
| Character | Current health, age, remaining turns, traits, principles, goals, skills, location, and group memberships |
| Relationship | Directed trust, affinity, and references to obligations toward another resident |
| Memory | An observed event, attributed claim, or interpretation with its event reference and learning time |
| Belief | An expectation, confidence, and supporting event references |
| Emotion | Temporary intensity and an expiration tick |
| Plan | A goal reference, ordered action IDs, and the next step |

Traits and principle strengths use a 0–2 range. Runtime traits accept fractional values so later bounded updates can be evaluated. The example adaptability values are experimental defaults. They currently describe a proposed sensitivity to experience and do not execute a growth algorithm.

Relationship trust and affinity range from -1 to 1, with 0 neutral. Belief confidence ranges from 0 to 1. Emotion intensity ranges from 0 to 2. Expiration and learning times are nonnegative simulation ticks. The world will define the real duration of a tick.

The two [example templates](../society/data/character_templates.json) share initial personality, principles, goals, age, and health. Their adaptability differs.

- `adaptive_keeper` starts with adaptability 1.5.
- `steadfast_keeper` starts with adaptability 0.2.

Both begin with promise-keeping 2 and principle strength 2. Whether their later decisions diverge under repeated breaches remains an evaluation task.

## Create and inspect a character

Run these commands from the repository root. Python 3.10 or newer is sufficient. This data inspection does not invoke a model.

```powershell
python -X utf8 -m society --template adaptive_keeper --resident-id ari
python -X utf8 -m society --template steadfast_keeper --resident-id ren
```

To save and reload state, choose a local output path.

```powershell
python -X utf8 -m society --template adaptive_keeper --resident-id ari --output character-save.json
python -X utf8 -m society --load character-save.json --now 2
```

To create a character from an edited template file, pass `--templates PATH` and its template ID through `--template`. A file contains `schema_version` and an array called `templates`. Unknown schema versions fail explicitly. Duplicate template, goal, or principle IDs are rejected.

The command prints an English-field model-state view. It retains claims and speaker attribution, omits memories learned after `--now`, and omits emotions that expire at or before that tick. The complete snapshot retains these records for save/load. Author model-facing descriptions in English.

The data layer validates numeric limits and record consistency. A future world observation builder must still enforce access to private events, resolve resident and agreement IDs, and ensure world updates match the observation time.

## Verification

```powershell
python -X utf8 -m unittest test_characters -v
```

Tests exercise independent residents, immutable baselines, serialization of changed state, attributed claims, expired emotions, invalid values, unsupported versions, and the command-line create/load path.
