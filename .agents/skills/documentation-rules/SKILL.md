---
name: documentation-rules
description: Write, edit, or review documentation through explicit human or ai mode. Human mode emphasizes concise communication in any language; ai mode emphasizes accurate, specific English documentation. Does not authorize changing requirements or implementing code.
---

# Documentation rules

Human-facing docs help people understand and decide quickly. AI-facing docs enable accurate understanding and execution. Both must be accurate and concise; length is not a quality measure.

## Explicit invocation

Use one shared skill with two portable entrypoints:

- [docs-human](references/docs-human.md) selects `human` mode.
- [docs-ai](references/docs-ai.md) selects `ai` mode.

Provide the selected entrypoint and this skill's contents to the assistant, or let a local agent read both files. These plain-text requests are equivalent when the skill is available:

```text
Use documentation-rules in human mode: <documentation task>
Use documentation-rules in ai mode: <documentation task>
```

- `human` selects the shared rules and human-facing rules. Any language is allowed.
- `ai` selects the shared rules and AI-facing rules. English is required.
- These entrypoints are prompt templates, not automatically registered slash commands. They do not require ChatGPT-specific or Claude-specific syntax. Clients with native skill support may expose their own invocation syntax.
- Require an explicit mode for each documentation request. Do not infer it from the topic, requested language, file name, existing document, or earlier requests.
- If the mode is missing or conflicting, ask only: "Which mode: human or ai?" before drafting or editing documentation.
- If both versions are requested, require an explicit mode for each output and apply the corresponding rules separately. Do not automatically generate both versions.

## Language rules

- **Human readers:** Follow the human-facing rules. Any language is allowed; use the requested language or the document's existing language.
- **AI readers:** Follow the AI-facing rules. Write all explanatory prose, headings, instructions, and template labels in English only. This skill must also remain in English.
- When both versions are explicitly requested, keep their audiences clear through separate sections or linked documents. The human-facing version may use any language; the AI-facing version must use English.
- Preserve exact identifiers, paths, commands, and source literals when translation would change their meaning or break execution. Explain them in English in AI-facing docs; do not add non-English prose or bilingual instruction blocks.
- These rules govern documentation, not the language of ordinary conversation.
- The optional `agents/openai.yaml` file contains Codex invocation metadata. ChatGPT and Claude can consume this skill as plain text without that file.

## Shared rules

- Lead with the conclusion and most important information, not a chronological account of the work.
- Distinguish facts, confirmed requirements, proposals, and unknowns. Do not present proposals as team decisions.
- Do not invent details, data, completion status, or verification results. Implemented code is not proof of verified behavior.
- Use concrete verbs. Remove filler, repetition, slogans, and irrelevant background.
- Retain limitations, risks, and open questions that affect decisions or execution.
- Use consistent terminology and preserve exact API names, field names, and commands.
- When editing, preserve valid content and the existing presentation. Avoid unrelated rewrites. Translate AI-facing prose into English when needed to meet the language rule.

## Human-facing docs

**Priority: clear main points, then brevity, then supporting detail. Factual accuracy is required. No language restriction.**

- Start with the conclusion, current status, or decision needed.
- Follow with the impact, key reasons, and next steps. Omit sections that add no value.
- Keep one point per paragraph. Use one sentence when it is enough.
- Do not list every implementation detail, file, parameter, or operation. Link to details when needed.
- Use tables for comparisons, status, or responsibilities; otherwise prefer short paragraphs or simple lists.
- Include only the background needed to understand the conclusion.

Use this structure when helpful, adapting its language to the reader. Not every item is required:

```text
Conclusion: Current situation and recommended action.
Key points: Why it matters, including material impacts or limitations.
Next steps: Who does what; include timing when already agreed.
Open decisions: Questions the team needs to resolve.
```

## AI-facing docs

**Priority: accuracy, then unambiguous meaning, then necessary completeness, then brevity. English only.**

- Start with the objective, scope, and completion conditions. State whether the document describes current behavior, requirements, or a proposal.
- Specify inputs, outputs, prerequisites, rules, and boundaries that affect execution. Omit unrelated detail.
- Locate referenced implementations using repo-relative paths, symbols, or document links. Avoid machine-specific absolute paths.
- For executable commands, provide the working directory, required configuration, and expected result. Use placeholders instead of real secrets.
- For APIs or data, specify relevant fields, types, units, required values, and error behavior. Do not leave critical contracts to inference.
- Replace vague requirements such as "fast," "suitable," or "correct" with checkable conditions. Label unagreed thresholds as proposals or open decisions; do not invent commitments.
- Explain critical branches: when to act, when not to act, and what to do with missing data or failures.
- Support factual claims with verifiable sources. Include verification commands, results, and dates when relevant. Explicitly label unverified claims.
- Identify conflicting sources instead of silently choosing one. Ask a specific question when a critical gap prevents accurate execution.

Use this structure when helpful. Not every item is required:

```text
Objective and scope: What to accomplish and where it applies.
Status and evidence: Confirmed information, sources, and unverified claims.
Execution contract: Inputs, outputs, prerequisites, and critical rules.
Exceptions and boundaries: When not to act and how to handle failure.
Acceptance: How to verify completion and the expected results.
Open questions: Gaps that prevent accurate execution.
```

## Keep both audiences aligned

- Maintain each fact in one authoritative location; use summaries and links elsewhere to avoid conflicting copies.
- Use human summaries for understanding and decisions, and AI details for precise execution. Summaries must not change the meaning of confirmed rules.
- When scope, behavior, or status changes, update affected summaries and detailed rules. Mark superseded decisions and link to replacements.
- Resolve conflicts using the relevant evidence: active decisions for requirements, code for implementation, and verification records for observed behavior.

## Final check

- Was the mode explicitly selected for this request?
- Does the opening establish the main point and current status?
- Can any sentence be removed without losing useful information?
- Are proposals, unknowns, or unverified claims presented as facts?
- Do human-facing docs contain unnecessary detail?
- Are all AI-facing prose, instructions, headings, and template labels in English?
- Does AI execution still depend on guessing critical rules?
- Are links, names, and sources accurate, and related docs consistent?
