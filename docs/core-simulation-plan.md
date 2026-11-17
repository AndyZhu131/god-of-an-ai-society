# Core simulation plan

Status — Proposed development plan. The contracts and acceptance conditions below are design proposals. They have not been implemented or validated as a general simulation core.

## Objective

Build a configurable social simulation in which residents execute ordinary plans, make consequential social decisions, and change through experiences they can actually observe. Support both adaptable residents and residents whose costly consistency can influence others.

Begin with character templates, live character state, world state, and their shared event contract. Validate them with small situations before designing the next complete scenario.

## Existing foundation

- [agents.py](../agents.py) provides resident identity, frozen observations, decision policies, decision traces, and action outcomes.
- [The island engine](../scenarios/after_the_bounty/engine.py) implements authoritative yearly actions, visibility cards, commitments, scarce workshop access, knowledge transfer, and event references.
- [Personality definitions](../scenarios/after_the_bounty/personality.py) provide three discrete preferences and one explicit action constraint.
- [Player sessions](../scenarios/after_the_bounty/player.py) provide objectives, influence cards, interventions, and evidence-backed carryover.
- Existing personality tests have shown weak or inconsistent control of model actions. The proposed growth system needs its own evaluation.

## Phase 1 — Define the shared data contracts

### Character templates

A template specifies initial conditions for creating residents. A running resident gets its own copy of mutable data. Editing a template affects subsequent creation.

| Group | Initial scope |
| --- | --- |
| Identity | Template ID, display text, optional background |
| Physical setup | Initial age, health with explicit maximum, lifespan policy |
| Capabilities | Initial skills and available ordinary activities |
| Disposition | Contention, care, and promise-keeping baselines |
| Principles | A small set of concrete principles, each with an initial commitment strength |
| Adaptability | How strongly repeated relevant experiences can affect a disposition or principle |
| Motivation | Initial goals and priorities |
| Social setup | References to starting relationships and group membership |

Retain the existing 0–2 personality presentation for the first prototype. Select internal update precision and thresholds after testing repeated events. Additional granularity must produce observable behavior before it becomes an exposed player setting.

Principle strength governs willingness to bear a cost to uphold a value. Explicit prohibitions use a separate field with clearly enforced action constraints.

### Running character state

| Group | Required meaning |
| --- | --- |
| Identity | Stable resident ID and originating template ID |
| Physical state | Current age, health, location, and participation status |
| Resources | Possessions, access rights, and active reservations |
| Skills | Ability and provenance of acquired knowledge |
| Disposition | Baseline values, current values, principle strengths, adaptability |
| Temporary state | Short-lived fear, anger, or confidence with an expiry or decay rule |
| Goals and plan | Current objective, chosen plan, next step, and interruption conditions |
| Relationships | Directed trust, affinity, and obligations toward specific residents |
| Beliefs | Expectations about cooperation and the reliability of social practices |
| Memory | Observed events, attributed claims, relevant interpretations, and source IDs |

Represent trust from A toward B separately from trust from B toward A. Group membership increases opportunities for interaction and observation. It does not automatically synchronize members' personalities.

Baseline templates, changed personality, temporary emotions, and relationships must be distinguishable in saved data and in the player explanation.

### World configuration and world state

| Configuration defines | Runtime state records |
| --- | --- |
| Clock units and action durations | Current time and pending actions |
| Location definitions and capacities | Occupancy and reservations |
| Resource types and production or consumption rules | Quantities, owners, and transfers |
| Skill and activity definitions | Actual knowledge, work orders, and progress |
| Action prerequisites, costs, effects, and visibility | Submitted plans, resolved effects, and conflicts |
| Event triggers and environmental rules | Scheduled and completed events |
| Player powers and objective definitions | Interventions spent and objective evidence |

An action needs an actor, targets, prerequisites, costs, duration, effects, and a rule for interruption or conflict. A proposal or promise needs parties, an exact obligation, a deadline, and observable completion conditions.

A scenario assembles these definitions with a cast and initial state. Keep historical dates, named storms, and particular ship arrivals in scenario content.

## Phase 2 — Define evidence and observation

Use stable IDs for characters, objects, agreements, and events. Save formats need a schema version.

An event records time, action and participants, actual effects, causally relevant references, and who can observe it. Record conflicts and rejected model submissions explicitly.

A resident receives the authoritative state they can perceive, their memories, and attributed messages. A claim remains attributable to its speaker until the resident obtains supporting evidence. An observer-facing model explanation is not a public world event.

Commitment review should distinguish completion, a valid opportunity declined, an attempt blocked by a conflict, and a condition that never became possible. Technical model failures must be visible to evaluation and handled without manufacturing intentional betrayal.

Acceptance for phases 1 and 2:

- A template can create independent residents with different later experiences.
- World and character state can be saved and loaded with IDs and references intact.
- A private experience does not appear in an uninformed resident's observation.
- The same recorded submitted actions resolve to the same outcomes.
- Changing a basic resource, skill, or location definition does not require rewriting the event log or resident memory format.

## Phase 3 — Assign decision responsibilities

| Responsibility | Owner |
| --- | --- |
| Facts, arithmetic, legal actions, costs, visibility, and conflict resolution | Simulation core |
| Continuing an accepted ordinary plan | Programmatic execution |
| Comparing immediate feasible plans | Programmatic priorities informed by needs, personality, and obligations |
| Costly social choices and responses to requests | Model decision with explicit available consequences |
| Proposing cooperation or institutional changes | Model proposal compiled into supported agreement or rule types |
| Recording and applying an agreement | Simulation core after acceptance |
| Interpreting an experience | Bounded model interpretation when the interpretation matters |
| Applying character updates | Programmatic update with provenance and configured limits |

Trigger reconsideration when a goal finishes, a plan becomes impossible, a material need changes, an obligation becomes due, or a relevant social event occurs. Avoid requesting a new life plan for every ordinary execution step.

A preference can affect routine priorities as well as model input. Evaluate those two contributions independently before choosing their balance.

Acceptance:

- Ordinary work continues between significant decisions.
- Models see actual costs and outcomes that the engine can calculate.
- A model can decline a costly contribution while respecting the world facts.
- Personality influence can be measured separately from hard action restrictions.

## Phase 4 — Add event-driven character change

For each relevant experience:

1. Determine the actual outcome, available opportunities, visibility, and attribution.
2. Update the observer's relationship toward the participants and their immediate emotional state.
3. Accumulate evidence affecting that observer's beliefs about cooperation.
4. Consider a bounded disposition or principle change when repeated evidence justifies it.
5. Include the updated state in a subsequent decision and record whether behavior changed.

Use principle strength and adaptability to control resistance to change. Include counterevidence, recovery, and opportunities to rebuild trust. Prevent one event from being applied repeatedly through repeated summaries or loading a save.

For influence on bystanders, require direct observation or an attributed communication. Preserve uncertainty about motives. Receiving help, witnessing costly consistency, and merely hearing a promise should have distinct evidence strength.

Acceptance:

- Betrayal by one partner first changes the relationship and relevant expectations.
- A blocked attempt is distinguishable from a feasible promise intentionally declined.
- Repeated relevant experiences can change an adaptable resident's later decisions.
- A resident with strong principles can retain their values while changing trust and cooperation partners.
- An uninformed bystander does not change in response to a hidden event.
- A model or parser failure does not train a character to be less moral.
- A saved and restored run does not apply the same experience twice.

## Phase 5 — Validate small social situations

Use fixed situations to test the contracts before writing a full narrative.

| Situation | What to observe |
| --- | --- |
| Repeated deliberate breaches | Changes in targeted trust, wider beliefs, and a later costly commitment |
| Repeated blocked attempts | Whether the resident can distinguish obstruction from refusal |
| Costly consistency | Whether a firm resident keeps a principle under increasing pressure |
| Witnessed cooperation | Whether informed bystanders respond differently from uninformed residents |
| Repairing a relationship | Whether subsequent trustworthy action can reverse some distrust |

Compare matched initial characters, different adaptability or principle strength, and multiple seeds. Include a programmatic policy control and a model policy. Score observed decisions and costs, alongside factual mistakes, failures, inference time, and token use.

Treat desired behavioral tendencies as hypotheses. Do not script a mandatory corruption or redemption ending.

## Phase 6 — Build one scenario and its Unity interface

Once the data contracts and small social tests are workable, configure one persistent settlement with a small cast, a few resources, a scarce facility, and a public project.

The Unity prototype should let a player edit an initial character template, change a few world parameters, observe a consequential decision, intervene, and inspect a causal explanation of character change.

The first scenario checks playability. A second small scenario checks that character, action, memory, and growth contracts are reusable.

## Immediate deliverables

1. Character template and character-state field definitions with one adaptable and one firm-principled example.
2. World definition and world-state fields with one shared activity and one exchange.
3. Event, observation, and commitment contracts covering success, obstruction, refusal, and technical failure.
4. An execution walkthrough in which the same event changes two observers differently.
5. A runnable small social test after those contracts have been reviewed.

The next design step is deliverable 1. Numeric update rates, internal scales, and timing units remain proposals until the small tests establish useful behavior.
