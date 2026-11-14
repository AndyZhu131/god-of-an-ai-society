# The Relay Archive

Twenty residents run workshops with the same abilities and one action each per round. Each workshop repairs a series of fictional devices. Devices from the same family respond to the same setting. Nobody begins with a known method.

| Main action | Result |
| --- | --- |
| Test | Try a setting on the current device. A successful repair verifies that setting and brings a new device next round. |
| Use a method | Apply a matching public note, private lesson, or a method you already know. |
| Publish | Write a known method into the public archive. The note stays after its author leaves. |
| Teach | Send a private note to a resident whose current device matches the method. They can use it from the next round. |
| Wait | Spend the round without testing or sharing. |

A resident earns one credit per repair. A note's author earns one credit the first time each other resident repairs a device using that note while the author remains in the settlement. There are no assigned roles. Any action can include a short public board post.

All residents decide from the same round boundary. New notes and board posts become visible next round. At the start of round 7, four residents leave and four newcomers take their places. Newcomers have no memories or private lessons. They can read the existing public archive.

The log records a method's original successful trial, who published or taught it, and which repairs used it. It also marks repairs by newcomers and repairs based on discoveries or notes whose creators have left.

```powershell
python -m scenarios.archive --residents 20 --rounds 12 --seed 17 --log archive_20_12_rounds.json
```
