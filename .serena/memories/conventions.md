# Conventions

- Keep edits task-scoped; preserve unrelated dirty files. No README change, commit/push, discarded work, dependency install or OS change without authorization. Protected `.env` variants and PEM paths stay unread/unedited.
- Python hooks use two-space indentation, snake_case, stdlib, unittest/mock, temporary directories; preserve surrounding style. PowerShell uses two-space indentation and brace placement on following lines; shell modules use POSIX syntax and existing helper functions.
- Repo tool routes: fff for file/text search; Serena for symbol structure/whole-body edits; gk with `directory` for local Git. Go-specific operations use gopls and workflow.md sequence. Current docs use Context7; report unavailable servers before fallback.
- Serena uses cwd with codex context; do not activate another project. Project creation/onboarding and memory writes require authorization.
