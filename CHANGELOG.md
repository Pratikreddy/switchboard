# Changelog

## Unreleased - Manager Corrections

- Recorded that the 2026-05-14 Palimpsest projection/export code change was made from the manager lane and must be reviewed by a separate Switchboard code agent before release.
- Reclassified Agent Ops as a coordination/control-plane root: manager work may track state, docs, decisions, ledgers, freshness, and handoffs, but sibling code changes must be delegated.
- Added a handoff requirement for the Palimpsest export redaction work so the current local exporter/test edits are not silently treated as accepted release work.
- Added Agent Ops manager-presence instructions: Source Status is the first bridge surface, project agents report through Pratik back to Codex manager, and Switchboard remains the control plane while Palimpsest owns personal/source/evidence data.
- Made those manager-presence rules durable in the shared Switchboard agent contract instead of relying on hand-edited generated `AGENTS.md` files.
- Recorded the CEO/project-manager operating model: Pratik talks to Codex manager, Codex manager routes implementation agents, and local/future `.47` manager states sync through Switchboard/Palimpsest projections.
- Added the CEO prompt-factory and Apple Notes intake rule: Codex manager turns rough notes into scoped prompts, asks questions when unclear, and keeps raw Notes private unless explicitly approved.
- Added the source-language rule: Pratik's wording is the primary truth, must be preserved first in prompt packets, and overrides cleaned prompts or agent interpretation until clarified.

## 1.12.6

- Made Collect the primary company refresh action: node-managed locations sync from node first, local-bundle-only servers are skipped, and the response includes node sync results plus refreshed workspace/latest data.
- Removed the primary Run All Health Checks UI path while keeping the backend endpoint as a legacy diagnostic.
- Fixed workspace freshness propagation so Collect updates the app-level latest cache that service detail pages read.
- Standardized new Switchboard node and manager runtime defaults on port `8020`.
- Disabled old `.47:870x` per-project node-health API flows locally and removed those old node-health ports from project-environment runtime notes.
- Added release/static checks for stale packaged UI labels before treating a build as shippable.

## 1.12.5

- Made manager-owned roots inherit common agent rules from the manager and require only enabled agent entrypoints.
- Added pull-bundle preflight with explicit location, source authority, scope freshness, unsafe-path checks, and stale remote-scope blocking.
- Added redacted Palimpsest state export for mainboard handoff.
- Tightened service UI wording around manager root normalization, added view presets, and made task ledger rows compact by default.
- Simplified project grouping copy toward company -> project -> services.

## 1.12.4

- Added manager-wide normalization so all registered roots can refresh manifests, snapshots, verification, and safe archive from one command.
- Clarified manager-owned service cards so they show manager version separately from stale root manifest version.

## 1.12.3

- Added `switchboard node normalize-root` as the canonical manager update gateway.
- Routed local node actions through manager registration, snapshot, verify, and safe archive.
- Blocked remote service-level node deploy, upgrade, and restart actions in favor of remote manager workflows.
- Updated Control Center node-action labels and previews for the one-port manager model.

## 1.12.2

- changed the service detail page to treat root project docs as tracked project files even when framework writes are disabled for them
- changed the project snapshot to prefer real project context over framework bootstrap/maintenance entries when both exist in the task ledger
- clarified framework doc ownership in the UI so `managed_docs` only means write permission, not whether a project doc exists
- changed node release checks and viewer metadata to compare exact GitHub release asset identity, not just the semver string
- pulled project-facing root docs from node doc indexes into control-center scope suggestions while excluding Switchboard overhead paths

## 1.12.1

- fixed self-conflicting control-center action locks that made `sync-from-node` and pull bundles report themselves as already running
- changed action-lock API conflicts to return HTTP `409` instead of a misleading success response
- made runtime-cache writes atomic so lock polling does not intermittently fail with JSON decode errors under concurrent reads and writes

## 0.1.7

- made `switchboard/local/tasks-completed.md` the single canonical node update file for normal agent work
- added `switchboard/core/playbook.md` as the only primary node rulebook
- changed the older node instruction files into compatibility stubs that point back to the playbook
- added managed-doc config for opt-in framework-owned root docs:
  - `README.md`
  - `API.md`
  - `CHANGELOG.md`
- added managed-doc defaults and doc-index metadata to `switchboard/node.manifest.json`
- made `switchboard node snapshot` regenerate:
  - handoff
  - runbook
  - approach history
  - doc index markdown
  - completed tasks json
  - scope snapshot json
  - doc index json
  - any enabled root derived docs
- added node/control-center sync support for managed-doc configuration and doc-index metadata
- added managed-doc and doc-index visibility to the control-center service page and the node dashboard
- updated the public docs to describe the canonical-file model and the explicit `v2` boundary for broader project-management views

## 0.1.6

- fixed explicit exclude handling for bundle pulls so exact paths like `.DS_Store` are not copied when excluded
- added collapsible bundle history cards in the control center
- added per-bundle copied-file and missed-scope detail in history views
- added resolved-file preview under saved scope entries using the latest bundle detail

## 0.1.5

- fixed node/control-center scope sync so seed-only node scope does not overwrite explicit control-center scope choices
- added runtime parsing from `switchboard/local/tasks-completed.md` `Runtime:` blocks into node manifest snapshots
- added pulled-file and missed-scope detail to bundle records
- added mirrored pull-bundle history and latest pulled bundle detail to the node dashboard
- changed scope suggestions so code files default to `repo` and plain directories default to `doc` unless they contain repo markers

## 0.1.4

- fixed the node root HTML page crash caused by a local variable shadowing the `html` module
- keeps `/` working for the minimal node dashboard while `/api/health` and `/api/node` continue to work

## 0.1.3

- fixed background node startup in installed wheels by making `python -m switchboard.cli ...` execute the Typer app
- keeps `switchboard node start` aligned with the direct `switchboard node serve` foreground path

## 0.1.2

- added a single interactive startup entrypoint with `run.sh` / `start.sh`
- added package-level node runtime commands:
  - `switchboard node start`
  - `switchboard node stop`
  - `switchboard node status`
  - `switchboard node logs`
- added generated `switchboard/start.sh` and `switchboard/run.sh` inside node installs
- changed node startup so background runtime state is stored under `switchboard/runtime/`
- kept foreground `switchboard node serve` available only for direct terminal use

## 0.1.1

- added per-location runtime config for expected ports, health-check commands, run-command hints, monitoring mode, and notes
- added runtime-check API and UI actions
- added manual node sync actions:
  - `sync-from-node`
  - `sync-to-node`
- extended node manifest support to mirror runtime config
- added minimal node UI/API status view for runtime, docs pack, and snapshot state
- rewrote the public docs for:
  - control-center setup
  - runtime monitoring
  - node install and sync rules
- documented the v1 control-center-only sync model explicitly

## 0.1.0

- established the first control-center backend and React UI
- added workspace and service manifests
- added path-first project onboarding
- added editable scope entries
- added pull bundles with preserved source-tree layout
- added repo actions and basic evidence/history files
- packaged initial node install, upgrade, snapshot, and serve commands

## Planned For v2

- day-wise task views across projects
- project and workspace task calendars
- richer agent-management and multi-project reporting
- broader project-management dashboard features across nodes and the control center
- more advanced deploy-readiness, safety, and operational views
