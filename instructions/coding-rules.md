# General Coding Instructions

Status: Draft for team review. The confirmed section records the user's stated rules. Proposed additions and open decisions are not approved team requirements. This file is not automatically installed in any client.

These instructions are intended for coding agents, including ChatGPT and Claude. Apply them when they are explicitly supplied or configured for a project. They do not authorize unrelated changes.

Scope: agent implementation behavior only. Repository permissions, PR approval requirements, CI gates, and deployment controls belong in tooling configuration, not this instruction file. Tooling configuration is outside the scope of loading these instructions.

For commit history and PR communication, also read the [Commit and PR Instructions](commit-pr-rules.md). Their rules are maintained separately from the draft additions below.

## Confirmed rules

### English code and comments

- Write code, identifiers, and code comments in English.
- Localized UI text, translation resources, and test fixtures may contain non-English content when required by the feature or test. Keep the surrounding code, identifiers, and comments in English.
- This rule concerns code and comments; it does not change the language of ordinary conversation or human-facing documentation.

### Clarify unclear requests

- If requirements are unclear or conflicting in ways that affect functionality, scope, API contracts, data behavior, or acceptance, ask a specific clarification question before making the affected code changes.
- Do not silently invent requirements, resolve conflicting requirements, or expand the requested feature.
- Resolve routine implementation details using established repository conventions without asking. If a choice changes the requirements or observable behavior, clarify it first.

### Tests for features and bug fixes

- Include unit tests with every implemented feature, before declaring the feature complete. The tests must be delivered with the feature, not deferred to a later task.
- Include a regression test with every bug fix. Verify that it reproduces the defect before the fix and passes after the fix.
- Run the relevant tests and inspect their results. Writing tests without running them does not establish that the feature or fix works.
- If execution is blocked, report the blocker and mark verification incomplete. Do not claim the tests passed.

## Proposed additions

The following rules are recommendations for discussion. Do not treat them as agreed policy until the team accepts them.

### Define completion before implementation

- State the expected behavior and checkable acceptance conditions before implementing a feature. A short list is enough.
- Confirm questions that would change behavior, scope, API contracts, data handling, or acceptance. Preserve the caller's existing authorization.

### Keep changes focused and consistent

- Read the affected implementation and relevant repository instructions before editing. Reuse established architecture, naming, and tooling.
- Keep changes within the requested scope. Preserve unrelated user changes; do not mix in broad refactoring or formatting.
- Reuse existing modules before adding new ones. Give components clear responsibilities and avoid speculative abstractions.
- Justify new dependencies or frameworks; do not add them when an existing capability adequately solves the problem.

### Test behavior and important failures

- Test observable behavior, not private implementation details. Cover the main success path and relevant boundary or failure cases.
- Keep unit tests deterministic and independent of live external services. Do not use arbitrary waits to make a test pass.
- Unit tests do not establish that an entire system works. Add integration tests when correctness depends on database behavior, API boundaries, or external-service contracts.
- Do not weaken assertions, skip failing tests, or alter expected behavior merely to obtain a passing result.

### Preserve contracts and handle errors

- Validate untrusted inputs at system boundaries and handle relevant failure cases explicitly. Do not silently swallow errors.
- Keep secrets and sensitive data out of source code, test fixtures, and logs.
- Identify compatibility impacts before changing public APIs, shared data formats, or database schemas. Document required migration steps when applicable.

### Verify and report honestly

- Run relevant tests during implementation and resolve failures caused by the change. CI enforcement is maintained separately.
- Report pre-existing failures separately; do not claim a clean result or broaden the task without a reason.
- Finish with a concise report: what changed, checks run and their results, and any remaining blockers or limitations.
- Update documentation when the change affects documented behavior, interfaces, configuration, or setup. Follow the explicitly selected documentation mode.

## Open decisions

Which proposed additions should become mandatory team rules?
