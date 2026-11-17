# Shared resource rules

Apply these rules when creating or maintaining resources in this library.

- Write AI-facing commands, instructions, skills, and examples in English.
- Keep shared resources independent of any single application repository or model provider. Put necessary client-specific metadata or adapters in clearly identified files.
- Give each rule one canonical location. Command entrypoints select a mode and reference the skill instead of copying its rules.
- Use paths relative to this library. Do not include machine-specific paths, credentials, private conversations, or application-specific requirements in reusable instructions.
- State required inputs, dependencies, and how an assistant obtains referenced files. A link alone does not make a file available to every client.
- Do not imply that saving a file registers a native command or installs a skill. Document any client-specific setup separately when it is actually provided.
- Preserve the caller's task scope. A shared instruction does not authorize unrelated changes or external actions.
- When moving resources, update internal references and check that the library remains usable on its own.
