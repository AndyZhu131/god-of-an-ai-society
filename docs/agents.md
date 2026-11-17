# How residents decide

Each resident has an identity and world state owned by the scenario. The scenario gives that resident an immutable observation at the start of each round. An `Agent` receives its own observation through the `AgentHarness` and calls a decision policy. Agents in a run share the policy and model. Each call receives only the resident's own observation, and every observation is built before the first decision. No resident sees another resident's same-round action before settling.

| Component | Responsibility |
| --- | --- |
| Scenario | Stores resident resources, memories, and relationships. Builds the visible card and legal action list, then applies all decisions using the game's rules. |
| Agent | Binds a resident ID to a decision policy and verifies the card is for that resident. |
| AgentHarness | Runs the resident calls and links each submitted decision to its settled outcome. |
| OllamaPolicy | Builds a fresh system message and state-card request for the local model. Restricts the action ID to legal choices, validates the reply, and retries malformed replies once. |

## Input and output

A `Turn` contains the resident ID, round number, serialized state card, and legal actions. The state card may include current resources, remembered events, known records, and visible messages. The scenario chooses that information and controls which residents can see it.

The model returns one `Decision` with three fields.

- `action_id` selects one legal action.
- `message` is optional in-world speech. The scenario decides whether to publish or deliver it and who can see it.
- `reason` is a short explanation generated for the observer. It records what the model says about its choice. It never enters another resident's context as a verified fact.

The harness runs one decision call per resident, with a retry for malformed responses. The model selects from the provided actions. The game applies the chosen action after everyone decides. A rejected decision falls back to waiting, and a legal action can still fail under the rules or conflict with another action.

## Decision logs

Run any scenario with `--log` to export `decision_trace`. Each entry contains the resident, round, state card, allowed action IDs, submission, elapsed time, and settled outcome. Where available, the outcome references event IDs, such as a successful repair or a rejected action. The evaluator uses the same structure under `decisions`. Its fixed-card checks leave `outcome` empty because they query the model without settling a round.

The trace stores the returned explanation and dialogue. It does not capture the model's private chain of thought. Scenario event logs record mechanics such as spending resources, repairing a device, or delivering a lesson. Decision trace files are for the observer and may include private observations and messages.
