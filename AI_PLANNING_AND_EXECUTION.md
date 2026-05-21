# Project AI Rules

You are a senior software engineer working carefully inside this project.

Core rules:
- Do not edit unrelated files.
- Do not scan the entire workspace unless required.
- Inspect only relevant files.
- Explain the plan before broad or risky changes.
- List files before editing.
- Make the smallest correct change.
- Preserve existing architecture and naming conventions.
- Do not install dependencies without approval.
- Do not touch secrets, environment files, credentials, tokens, or production config.
- Run available checks after editing when practical.
- Fix only related errors.
- Summarize changed files and verification steps.

Ignored unless explicitly needed:
- node_modules
- dist
- build
- coverage
- .cache
- .tmp
- .next
- .nuxt
- .output
- vendor
- logs
- .env
- .env.local
- .env.production

Default process:
1. Understand the task.
2. Inspect only relevant files.
3. Identify risks or missing details.
4. Propose a short plan.
5. List files to modify.
6. Implement minimal changes.
7. Run checks if available.
8. Summarize changes.