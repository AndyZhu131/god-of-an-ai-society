"""Create, inspect, save, and reload the proposed character data contract."""

import argparse
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from .characters import Character, load_templates


TEMPLATES = Path(__file__).parent / "data" / "character_templates.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--template", default="adaptive_keeper", help="Initial character template ID.")
    source.add_argument("--load", type=Path, help="Inspect a saved character.")
    parser.add_argument("--templates", type=Path, default=TEMPLATES, help="JSON file containing character templates.")
    parser.add_argument("--resident-id", help="Stable ID for a newly created resident.")
    parser.add_argument("--now", default=0, type=int, help="Current simulation tick for the model-facing view.")
    parser.add_argument("--output", type=Path, help="Save a versioned character snapshot.")
    args = parser.parse_args()
    if args.load and args.resident_id:
        parser.error("--resident-id applies when creating a new resident.")
    try:
        if args.load:
            resident = Character.from_dict(json.loads(args.load.read_text(encoding="utf8")))
        else:
            templates = load_templates(args.templates)
            if args.template not in templates:
                parser.error(f"Choose a template from {', '.join(templates)}.")
            resident = templates[args.template].create(args.resident_id or "resident-001")
        view = resident.model_state(args.now)
        if args.output:
            pending = None
            try:
                with NamedTemporaryFile("w", encoding="utf8", dir=args.output.parent, delete=False) as snapshot:
                    pending = Path(snapshot.name)
                    json.dump(resident.to_dict(), snapshot, ensure_ascii=False, indent=2, allow_nan=False)
                    snapshot.write("\n")
                os.replace(pending, args.output)
            finally:
                if pending and pending.exists():
                    pending.unlink()
        print(json.dumps(view, ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.exit(1, f"Character data error: {error}\n")


if __name__ == "__main__":
    main()
