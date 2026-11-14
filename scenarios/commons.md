# Equal Start Settlement

Twenty residents share a source of food and a public board. They start with the same abilities and two food units each. The common stock starts at 30. There are no assigned groups or roles.

| Action | Effect |
| --- | --- |
| Harvest | Take two food units from the common stock into your own reserve, if available. |
| Maintain | Add two extra food units to the common stock at the end of the round. |
| Wait | Take no action. |

Each resident chooses once from their start-of-round card. The game resolves harvests in a rotating order, replenishes the common stock by 12 plus maintenance contributions up to a cap of 36, then deducts one food unit per resident for their meal. A resident without food misses that meal and can still act next round.

Residents can attach a short public board post to any action at no cost. Posts become visible from the next round. Each state card shows the 12 most recent posts.

`commons.py` in this folder defines the scenario and sends English instructions, state cards, and action descriptions to the local model. Run it from the project root with `python -X utf8 -m scenarios.commons --residents 20 --rounds 1`.
