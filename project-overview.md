# Project Overview

- `template_manager/project_from_template.py` renders legacy and Jinja templates and persists generation settings in `.template_settings.toml`.
- `template_manager/reverse_sync.py` reviews committed project changes against rendered template paths. `extract` preserves the strict checkpoint-based legacy bundle; `review` adds automatic baseline discovery and agent-ready JSON/Markdown context without advancing the checkpoint.
- Reverse-sync checkpoints are custom Git refs under `refs/template-manager/`; extraction and review are read-only, while `mark-reviewed` is the only command that updates the local ref.
- `template_manager/skills/reverse-sync-review/SKILL.md` is packaged with template-manager and installed for coding agents. Keep its workflow aligned with the CLI bundle contract so agents do not repeat discovery already performed by the command.
- Reverse-sync behavior is covered by real temporary Git repositories in `tests/test_reverse_sync.py`.
