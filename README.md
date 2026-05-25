# Switchboard

Switchboard is a project-first control center for tracking services, servers, projects, project environments, bundle pulls, node state, and agent-generated system context from one canonical node file:

```text
switchboard/local/tasks-completed.md
```

Current release: `1.12.8`

## What 1.12.8 Adds

- Adds the suite hooks layer for Codex and Claude prompt context.
- Captures exact `UserPromptSubmit` text in a local-private timeline DB while keeping git evidence to hashes, timestamps, source refs, and counts.
- Adds compact mistake-pattern and memory-query brics for task-specific prompt snippets without raw prompt dumps.
- Keeps hook/bric/memory state out of the front-page UI.

## What 1.12.7 Fixes

- The main dashboard is clean again: work activity map plus Tech Stack, How To Use, and Companies.
- The work map uses task-ledger density as the source; branch/head is metadata only.
- Front-page foundation, sidecar, harness, user-story, agent-note, server, and backup panels are no longer mounted by default.
- API Lab is removed from the visible product surface.

## What 1.12.6 Fixed

- Collect is the primary company refresh action: node-managed locations sync from node first, then inventory refreshes.
- Workspace/service freshness now flows back to the app-level latest cache after Collect.
- The primary Run All Health Checks UI path is gone; the endpoint remains as a legacy diagnostic.
- New Switchboard node and manager defaults use port `8020`.
- Old `.47:870x` per-project node-health flows are disabled locally while real app ports stay visible.

## Core Idea

The control center is the operator surface.

Nodes are lightweight metadata companions installed inside project roots under:

```text
<project-root>/switchboard/
```

Agents still edit only one project-local canonical file:

```text
switchboard/local/tasks-completed.md
```

Everything else is derived from that file or from control-center state:

- managed docs
- completed tasks JSON
- scope snapshots
- node manifest metadata
- task ledger summaries
- dependency and cross-dependency views

In manager mode, common agent rules are manager-owned. Minion roots should not carry every CLI file by default; optional files such as `CLAUDE.md`, `GEMINI.md`, `QWEN.md`, and `opencode.json` are generated only when that tool is enabled for that root.

## Main Concepts

### Companies / Workspaces

Top-level umbrellas such as `ZAPP` and `PESU`.

They group:

- servers
- services
- projects

### Servers

Servers live in `switchboard/manifests/servers.json`.

Each server can track:

- company/workspace ownership
- connection type
- deploy mode:
  - `native_agent`
  - `local_bundle_only`
- `vpn_required`
- notes

Passwords are local-only and resolved from `.env` or `.env.local`. They are not stored in tracked manifests.

### Services

Services live in `switchboard/manifests/services.json`.

Each service tracks:

- service kind
- execution mode
- locations
- scope entries
- managed docs
- repo policies
- task ledger
- node viewer state
- pull bundle history

Execution mode matters:

- `networked`: ports and health checks are first-class
- `batch`: command-oriented runtime, ports optional
- `lambda`: deploy-root and dependency tracking without pretending there is a local app server
- `docs_only`: docs/scope/dependency tracking with minimal runtime chrome

### Projects and Environments

Projects group services.

Project environments track deployment views like:

- `test`
- `prod`
- `staging`
- `qa`
- custom

An environment can point the same service to:

- different roots
- different locations
- different servers
- different versions
- different dependency endpoints

This is how the control center tracks real test/prod differences without duplicating the whole service model.

## Repository Layout

```text
switchboard/                     Python backend, CLI, node logic, manifests
switchboard/manifests/           Tracked service/server/workspace/project data
switchboard/manifests/project-environments.json
src/                             React control-center UI
src/components/                  Shared control-center panels
src/pages/                       Main dashboard pages
tests/                           Frontend/live API tests
tests_backend/                   Backend tests
README.md                        Main framework/operator guide
pyproject.toml                   Python package metadata
package.json                     Frontend package metadata
```

## Control Center Setup

```bash
git clone https://github.com/pratikreddy9/switchboard.git
cd switchboard
python3 -m venv .venv
./.venv/bin/pip install -e .
npm install
```

Set local secrets in `.env.local`:

```dotenv
SWITCHBOARD_SERVER_PESU_DEV_47_HOST=192.168.3.47
SWITCHBOARD_SERVER_PESU_DEV_47_USERNAME=pesu
SWITCHBOARD_SERVER_PESU_DEV_47_PORT=22
SWITCHBOARD_SERVER_PESU_DEV_47_PASSWORD=
```

Supported server key pattern:

```text
SWITCHBOARD_SERVER_<SERVER_ID>_HOST
SWITCHBOARD_SERVER_<SERVER_ID>_USERNAME
SWITCHBOARD_SERVER_<SERVER_ID>_PORT
SWITCHBOARD_SERVER_<SERVER_ID>_PASSWORD
```

Start the control center:

```bash
./run.sh
```

Or directly:

```bash
./framework.sh start
./framework.sh status
./framework.sh logs
```

Default local URLs:

- UI: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8009/api/health`

## Canonical Node Flow

Normal agent work should update only:

```text
switchboard/local/tasks-completed.md
```

Then snapshot on the node:

```bash
switchboard node snapshot --project-root <path>
```

That regenerates:

- `switchboard/local/control-center-handoff.md`
- `switchboard/local/runbook.md`
- `switchboard/local/approach-history.md`
- `switchboard/local/doc-index.md`
- `switchboard/evidence/completed-tasks.json`
- `switchboard/evidence/scope.snapshot.json`
- `switchboard/evidence/doc-index.json`
- `switchboard/node.manifest.json`

## Pull Bundles

Each bundle is a versioned local mirror of the selected service scope.

Bundle behavior:

- starts from saved scope
- supports one-run includes and excludes
- preserves original relative paths
- stores checksums and per-file metadata
- compares against the previous bundle for the same service/server
- stores diff summary counts:
  - added
  - removed
  - changed
  - unchanged
- stores exposure findings without storing raw secrets
- stores dependency and cross-dependency notes

Local layout:

```text
downloads/<workspace>/<service>/<bundle_id>/
  source_tree/
  bundle-manifest.json
```

## Safe Node Operations

The control center can:

- inspect node presence/version/runtime state
- register or normalize a root through the manager
- check manager status
- sync from a node before pull-bundle creation

Safety rules:

- actions are location-scoped
- action locks prevent duplicate runs
- sync stays blocked until bootstrap is ready
- node deploy/update is manager-root normalization, not app deploy and not a per-project runtime start

## Managed Docs

Managed docs are configured per service and derived from the canonical task file.

Managed doc ids:

- `readme`
- `api`
- `changelog`
- `handoff`
- `runbook`
- `approach_history`
- `doc_index_md`
- `doc_index_json`

If a managed doc is disabled, Switchboard must not rewrite it.

## Release and Build

Frontend:

```bash
npm run build
```

Frontend tests:

```bash
npm test -- --run
```

Backend syntax check:

```bash
python3 -m py_compile switchboard/models.py switchboard/manifests.py switchboard/api.py switchboard/collectors.py switchboard/storage.py
```

Build a wheel:

```bash
./.venv/bin/switchboard release build --wheel-out release
```

## Constraints

- `tasks-completed.md` remains the single agent-edited canonical file
- passwords stay local-only
- project, workspace, server, service, and location ids are stable identifiers
- project environments are deployment views, not separate services
- project-level pull summaries are derived from service bundle history
- dependencies and cross dependencies are sourced from task-ledger context and environment deployment refs
