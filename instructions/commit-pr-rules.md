# Commit and PR Instructions

Apply these rules when this file is supplied or configured for an agent. They govern commit history and PR communication; they do not grant permission to push, merge, deploy, or change repository settings. This file is not automatically installed.

## Commit messages

- Use English and the format `type: short explanation`. Scope is optional: `type(scope): short explanation`.
- Use `feat` for features, `fix` for bug fixes, `docs` for documentation, `refactor` for restructuring, `test` for independent test work, `chore` for maintenance, and `build` or `ci` for tooling changes.
- Describe the result with a specific verb. Avoid messages such as `update`, `fix stuff`, or `address feedback`. Add a body only when the reason or compatibility impact needs explanation.
- Mark breaking changes with `!` before the colon and explain the impact.

## Focus and squash

- Keep each PR focused on one independently reviewable change. Include its related tests and documentation. Link an existing Issue when available; do not require a new ticket for every small change.
- Squash implementation attempts, follow-up fixes, and review corrections for the same item into one final commit before it reaches the target branch. Prefer Squash and merge for a PR covering one item.
- Write the final squash message from the complete change, using the PR title as its subject. Do not concatenate the temporary commit messages.
- Keep unrelated work separate. Do not rewrite the default branch or another contributor's commits to clean up history. If cleanup requires changing a shared branch, clarify the scope first; use existing authorization when it covers the operation.

## PR communication

- Use English, plain language, and the same title format as commits.
- Briefly explain what changed, why, and how it was verified. Add risks, migration steps, or rollback limitations only when relevant.
- Report actual check commands and outcomes. State skipped or unrun checks and blockers. Passing local checks do not establish that CI passed.
- Explain behavior or contract changes that affect another component or repository, and link related work when available.
- Describe the final implementation. Update the title and description when the PR changes during review; omit the conversation history and file-by-file narration.

## Before publishing

- Inspect the staged diff and final PR diff. Exclude secrets, personal data, unrelated edits, and accidental generated files; retain generated files required by the project.
- Resolve failures introduced by the change before marking it ready for review. Disclose pre-existing failures separately. Keep incomplete work in a Draft PR when one is needed.

## Example

Title: `fix(auth): reject expired login tokens`

Reject expired tokens before creating a session so users must sign in again.

Validation: `<command>` — `<actual result>`. Note any unrun checks or remaining limitations.

## References

The message format follows [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). Squash behavior is described by [GitHub](https://docs.github.com/en/pull-requests/reference/pull-request-merges). Clear descriptions and focused changes follow Google's [description guidance](https://google.github.io/eng-practices/review/developer/cl-descriptions.html) and [small-change guidance](https://google.github.io/eng-practices/review/developer/small-cls.html). The operational details above are team rules adapted from these sources.
