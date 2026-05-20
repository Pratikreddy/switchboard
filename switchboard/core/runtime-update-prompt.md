# Runtime Update Prompt

For regular maintenance work:
- Read `switchboard/core/playbook.md` first.
- Inspect system docs for dependencies and record agent/tool used.
- Update only `switchboard/local/tasks-completed.md`.
- Use one entry per meaningful update.
- Include timestamp, title, summary, changed paths, and routing tags.
- Include `Agent`, `Tool`, `Read Back`, and `Scope Check`.
- Use only these routing tags: `task`, `handoff`, `runbook`, `decision`, `scope`.
- If project-facing docs changed, add `Version`, `Readme`, `API`, and `Changelog` blocks as needed.
- If scope changed, include a `Scope Entries` block in the entry.
- If runtime config changed, include a `Runtime:` block in the entry.
- Finish by running `switchboard node snapshot --project-root <path>` and `switchboard node verify-update --project-root <path>`.

Entry format:
## 2026-04-01T12:00:00+00:00 | Example title
- Tags: task, handoff
- Summary: Short summary.
- Changed Paths: src/app.py, switchboard/local/tasks-completed.md
- Agent: Codex
- Tool: codex-cli
- Read Back: Restated the request before editing.
- Scope Check: Project shape did not change; existing scope remains valid.
- Version: 1.1
- Readme:
  ## Overview
  Updated high-level project notes.
- API:
  ## Endpoints
  Added `/health`.
- Changelog:
  - Added health endpoint.
- Notes:
  - Optional detail line.
- Scope Entries:
  - doc | file | /abs/path/to/file.md
  - exclude | glob | venv
- Runtime:
  - expected_ports: 8020, 8000
  - healthcheck_command: curl http://127.0.0.1:8020/api/health
  - run_command_hint: uvicorn main:app --port 8020
  - monitoring_mode: manual
