import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from fastapi import HTTPException
from pydantic import ValidationError

import switchboard.api as api_module
from switchboard.api import _raise_for_action_result, collect_workspace, get_workspace_latest, git_pull
from switchboard.config import Settings
from switchboard.collectors import CollectionCoordinator
from switchboard.freshness import freshen_node_viewers, freshness_envelope
from switchboard.manifests import ManifestStore, save_json
from switchboard.models import CollectRequest, GitHubBackupRequest, GitPullRequest, NodeActionRequest, ProjectCreateRequest, ProjectPatchRequest, PullBundleBackupDryRunRequest, PullBundleRequest, ResolvedServer, ScopeEntry, LocationSpec, ServiceManifest
from switchboard.node import snapshot_node
from switchboard.storage import SnapshotStore, read_json


class BackendRegressionTests(unittest.TestCase):
    def test_action_in_progress_maps_to_conflict(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            _raise_for_action_result({"status": "action_in_progress", "message": "busy"})
        self.assertEqual(ctx.exception.status_code, 409)

    def test_latest_includes_inventory_keys(self) -> None:
        body = get_workspace_latest("zapp")
        for key in ("workspace", "servers", "services", "summary", "repo_inventory", "docs_index", "logs_index"):
            self.assertIn(key, body)

    def test_latest_uses_current_manifest_service_list_over_archived_snapshot(self) -> None:
        body = get_workspace_latest("1")
        current_service_ids = set(body.get("workspace", {}).get("services", []))
        latest_service_ids = {service.get("service_id") for service in body.get("services", [])}
        self.assertEqual(latest_service_ids, current_service_ids)
        self.assertNotIn("gmail-day-to-day", latest_service_ids)

    def test_latest_marks_archive_mismatch_stale_while_manifest_services_win(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(
                manifest_dir=root / "switchboard" / "manifests",
                evidence_dir=root / "docs" / "evidence",
                archive_dir=root / "docs" / "evidence" / "archive",
                private_state_dir=root / "state" / "private",
                downloads_dir=root / "downloads",
            )
            save_json(
                settings.manifest_dir / "workspaces.json",
                [
                    {
                        "workspace_id": "1",
                        "name": "Current Company",
                        "tags": [],
                        "favorite_tier": "primary",
                        "servers": [],
                        "services": ["current-service"],
                        "notes": "",
                    }
                ],
            )
            save_json(settings.manifest_dir / "servers.json", [])
            save_json(
                settings.manifest_dir / "services.json",
                [
                    {
                        "service_id": "current-service",
                        "workspace_id": "1",
                        "display_name": "Current Service",
                    }
                ],
            )
            save_json(settings.manifest_dir / "projects.json", [])
            save_json(settings.manifest_dir / "project-environments.json", [])
            save_json(settings.manifest_dir / "api-flows.json", [])
            save_json(settings.manifest_dir.parent / "manager.manifest.json", {"managed_roots": []})
            snapshot = {
                "generated": "2026-05-10T00:00:00+00:00",
                "workspace": {
                    "workspace_id": "1",
                    "name": "Archived Company",
                    "tags": [],
                    "favorite_tier": "primary",
                    "servers": [],
                    "services": ["old-service", "deleted-service"],
                    "notes": "",
                },
                "servers": [],
                "services": [
                    {"service_id": "old-service", "status": "ok"},
                    {"service_id": "deleted-service", "status": "ok"},
                ],
                "repo_inventory": [],
                "docs_index": [],
                "logs_index": [],
                "summary": {"status": "ok", "server_count": 0, "service_count": 2},
            }
            archive_path = settings.archive_dir / "2026-05-10T00-00-00+00-00" / "workspace-1.json"
            save_json(archive_path, snapshot)
            save_json(
                settings.evidence_dir / "run-history.json",
                {
                    "generated": snapshot["generated"],
                    "runs": [
                        {
                            "workspace_id": "1",
                            "generated": snapshot["generated"],
                            "archive_path": str(archive_path.relative_to(settings.evidence_dir.parent)),
                            "status": "ok",
                            "service_count": 2,
                            "server_count": 0,
                        }
                    ],
                },
            )

            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            with (
                mock.patch.object(api_module, "settings", settings),
                mock.patch.object(api_module, "manifest_store", manifests),
                mock.patch.object(api_module, "snapshot_store", snapshots),
            ):
                body = api_module.get_workspace_latest("1")

            self.assertEqual(body["workspace"]["company_name"], "Current Company")
            self.assertEqual(body["company"]["company_id"], "1")
            self.assertEqual([service["service_id"] for service in body["services"]], ["current-service"])
            self.assertEqual(body["summary"]["service_count"], 1)
            self.assertEqual(body["freshness"]["freshness_state"], "Stale")
            self.assertEqual(body["freshness"]["stale_reason"], "archive_service_list_mismatch")
            self.assertEqual(body["archived_service_ids"], ["deleted-service", "old-service"])
            self.assertEqual(body["current_service_ids"], ["current-service"])

    def test_git_pull_rejects_non_allowlisted_path(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            git_pull("aichat", GitPullRequest(repo_path="/etc/passwd"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_git_pull_rejects_empty_path(self) -> None:
        with self.assertRaises(ValidationError):
            GitPullRequest(repo_path="   ")

    def test_collect_returns_structured_snapshot(self) -> None:
        body = collect_workspace("zapp", CollectRequest())
        self.assertIn("services", body)
        self.assertIsInstance(body["services"], list)
        for service in body["services"]:
            self.assertIn("status", service)

    def test_control_center_context_includes_data_handoff_surfaces(self) -> None:
        body = api_module.get_control_center_context()
        self.assertIn("activity_map", body)
        self.assertIn("branch_metadata", body)
        self.assertIn("feature_map", body)
        self.assertIn("harness_source_map", body)
        self.assertIn("user_story", body)
        self.assertIn("agent_usage_notes", body)
        self.assertIn("line_noise", body)
        self.assertIn("production_usage", body)
        self.assertIn("agent_handoff_quality", body)
        self.assertIn("docs_relevance", body)
        self.assertIn("suite_boundaries", body)
        self.assertIn("foundation_projection", body)
        self.assertIn("cleanup_note", body)
        self.assertIn("days", body["activity_map"])
        self.assertEqual(body["activity_map"]["source"], "task_ledgers")
        self.assertEqual(body["activity_map"]["git_metadata_role"], "branch_head_metadata_only")
        self.assertIn("branches", body["branch_metadata"])
        self.assertTrue(body["branch_metadata"]["metadata_only"])
        self.assertEqual(body["feature_map"]["role"], "data_sync_evidence_surface")
        self.assertIn("entries", body["harness_source_map"])
        self.assertGreaterEqual(body["line_noise"]["total_lines"], 1)
        self.assertIn("active_source_lines", body["line_noise"])
        self.assertIn("active_source", body["line_noise"]["taxonomy"])
        self.assertIn("harness_adapters", body["line_noise"]["taxonomy"])
        self.assertEqual(body["line_noise"]["schema_version"], "line-noise-v0")
        self.assertEqual(body["production_usage"]["schema_version"], "production-usage-v0")
        self.assertIn("tokens", body["production_usage"]["evidence_kinds"])
        self.assertEqual(body["production_usage"]["privacy"]["raw_payloads"], "excluded")
        self.assertEqual(body["agent_handoff_quality"]["schema_version"], "agent-handoff-quality-v0")
        self.assertEqual(body["docs_relevance"]["schema_version"], "docs-relevance-v0")
        self.assertEqual(body["suite_boundaries"]["schema_version"], "suite-boundaries-v0")
        boundary_ids = {entry["boundary_id"] for entry in body["suite_boundaries"]["boundaries"]}
        self.assertIn("palimpsest_deferred_boundary", boundary_ids)
        self.assertIn("client_server_47_deferred_boundary", boundary_ids)
        self.assertEqual(body["foundation_projection"]["schema_version"], "switchboard-pass1-foundation-v0")

    def test_activity_map_collects_registered_local_task_ledgers(self) -> None:
        with TemporaryDirectory() as tmpdir:
            manager_root = Path(tmpdir) / "manager"
            manifest_dir = manager_root / "switchboard" / "manifests"
            evidence_dir = manager_root / "docs" / "evidence"
            archive_dir = evidence_dir / "archive"
            private_state_dir = manager_root / "state" / "private"
            downloads_dir = manager_root / "downloads"
            alpha_root = Path(tmpdir) / "alpha"
            beta_root = Path(tmpdir) / "beta"
            missing_ledger_root = Path(tmpdir) / "missing-ledger"
            absent_root = Path(tmpdir) / "absent"
            remote_root = "/remote/not-read"
            for root in (alpha_root, beta_root, missing_ledger_root):
                (root / "switchboard" / "local").mkdir(parents=True)
                (root / "switchboard" / "evidence").mkdir(parents=True)
            (alpha_root / "switchboard" / "node.manifest.json").write_text("{}", encoding="utf-8")

            def write_ledger(root: Path, title: str, changed_path: str) -> Path:
                path = root / "switchboard" / "local" / "tasks-completed.md"
                path.write_text(
                    "\n".join(
                        [
                            f"## 2026-05-20T10:00:00+00:00 | {title}",
                            "- Tags: task, scope",
                            f"- Summary: {title} summary",
                            f"- Changed Paths: {changed_path}",
                            "- Agent: Codex",
                            "- Tool: codex-desktop",
                            "- Scope Entries:",
                            f"  - code | file | {changed_path}",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                return path

            alpha_ledger = write_ledger(alpha_root, "Alpha ledger task", "alpha.py")
            alpha_projection = alpha_root / "switchboard" / "evidence" / "completed-tasks.json"
            save_json(
                alpha_projection,
                {
                    "generated": "2026-05-20T10:05:00+00:00",
                    "tasks": [
                        {
                            "timestamp": "2026-05-20T10:05:00+00:00",
                            "title": "Alpha projection task",
                            "summary": "projection summary",
                            "tags": ["task"],
                            "changed_paths": ["alpha.py", "README.md"],
                            "scope_entries": [{"kind": "code"}],
                            "agent": "Codex",
                            "tool": "codex-desktop",
                        }
                    ],
                },
            )
            os.utime(alpha_ledger, (100, 100))
            os.utime(alpha_projection, (200, 200))

            beta_projection = beta_root / "switchboard" / "evidence" / "completed-tasks.json"
            save_json(
                beta_projection,
                {
                    "generated": "2026-05-19T10:00:00+00:00",
                    "tasks": [
                        {
                            "timestamp": "2026-05-19T10:00:00+00:00",
                            "title": "Stale beta projection",
                            "summary": "stale",
                            "changed_paths": [],
                        }
                    ],
                },
            )
            beta_ledger = write_ledger(beta_root, "Beta ledger task", "beta.py")
            os.utime(beta_projection, (100, 100))
            os.utime(beta_ledger, (200, 200))

            settings = Settings(
                manifest_dir=manifest_dir,
                evidence_dir=evidence_dir,
                archive_dir=archive_dir,
                private_state_dir=private_state_dir,
                downloads_dir=downloads_dir,
            )
            save_json(
                manifest_dir / "workspaces.json",
                [
                    {
                        "workspace_id": "ws",
                        "name": "Workspace",
                        "tags": [],
                        "favorite_tier": "primary",
                        "servers": ["local_mac", "remote"],
                        "services": ["alpha", "beta", "missing-ledger", "absent", "remote-svc"],
                        "notes": "",
                    }
                ],
            )
            save_json(
                manifest_dir / "servers.json",
                [
                    {
                        "server_id": "local_mac",
                        "name": "Local",
                        "connection_type": "local",
                        "host": "127.0.0.1",
                        "username": "p",
                    },
                    {
                        "server_id": "remote",
                        "name": "Remote",
                        "connection_type": "ssh",
                        "host": "example.invalid",
                        "username": "p",
                    },
                ],
            )
            save_json(
                manifest_dir / "services.json",
                [
                    {
                        "service_id": "alpha",
                        "workspace_id": "ws",
                        "display_name": "Alpha",
                        "locations": [
                            {
                                "location_id": "alpha-local",
                                "server_id": "local_mac",
                                "access_mode": "local",
                                "root": str(alpha_root),
                                "role": "primary",
                                "is_primary": True,
                            }
                        ],
                    },
                    {
                        "service_id": "beta",
                        "workspace_id": "ws",
                        "display_name": "Beta",
                        "locations": [
                            {
                                "location_id": "beta-local",
                                "server_id": "local_mac",
                                "access_mode": "local",
                                "root": str(beta_root),
                                "role": "primary",
                                "is_primary": True,
                            }
                        ],
                    },
                    {
                        "service_id": "missing-ledger",
                        "workspace_id": "ws",
                        "display_name": "Missing Ledger",
                        "locations": [
                            {
                                "location_id": "missing-local",
                                "server_id": "local_mac",
                                "access_mode": "local",
                                "root": str(missing_ledger_root),
                                "role": "primary",
                                "is_primary": True,
                            }
                        ],
                    },
                    {
                        "service_id": "absent",
                        "workspace_id": "ws",
                        "display_name": "Absent",
                        "locations": [
                            {
                                "location_id": "absent-local",
                                "server_id": "local_mac",
                                "access_mode": "local",
                                "root": str(absent_root),
                                "role": "primary",
                                "is_primary": True,
                            }
                        ],
                    },
                    {
                        "service_id": "remote-svc",
                        "workspace_id": "ws",
                        "display_name": "Remote",
                        "locations": [
                            {
                                "location_id": "remote-primary",
                                "server_id": "remote",
                                "access_mode": "ssh",
                                "root": remote_root,
                                "role": "primary",
                                "is_primary": True,
                            }
                        ],
                    },
                ],
            )
            save_json(manifest_dir / "projects.json", [])
            save_json(manifest_dir / "project-environments.json", [])
            save_json(manifest_dir / "api-flows.json", [])
            save_json(manifest_dir.parent / "manager.manifest.json", {"managed_roots": []})

            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            coordinator = CollectionCoordinator(settings, manifests, snapshots)

            activity = coordinator._work_activity()

            self.assertEqual(activity["source"], "task_ledgers")
            self.assertEqual(activity["primary_truth"], "registered_local_service_task_ledgers")
            self.assertEqual(activity["git_metadata_role"], "branch_head_metadata_only")
            self.assertEqual(activity["status"], "partial")
            self.assertEqual(activity["total_tasks"], 2)
            self.assertEqual(activity["total_changed_paths"], 3)
            self.assertEqual(activity["total_scope_entries"], 2)
            self.assertEqual(activity["service_count"], 2)
            self.assertEqual(activity["local_service_count"], 4)
            day = activity["days"][0]
            self.assertEqual(day["date"], "2026-05-20")
            self.assertEqual(day["daily_task_count"], 2)
            self.assertEqual(day["daily_services_touched"], 2)
            self.assertEqual(day["services"], ["alpha", "beta"])
            records = {record["service_id"]: record for record in activity["task_records"]}
            self.assertEqual(records["alpha"]["task_title"], "Alpha projection task")
            self.assertTrue(records["alpha"]["source_file"].endswith("completed-tasks.json"))
            self.assertEqual(records["alpha"]["source_projection_state"], "fresh")
            self.assertEqual(records["alpha"]["source_kind"], "completed_tasks_projection")
            self.assertEqual(records["beta"]["task_title"], "Beta ledger task")
            self.assertTrue(records["beta"]["source_file"].endswith("tasks-completed.md"))
            self.assertEqual(records["beta"]["source_projection_state"], "stale")
            self.assertEqual(records["beta"]["source_kind"], "task_ledger")
            projects = {project["service_id"]: project for project in activity["projects"]}
            self.assertEqual(projects["missing-ledger"]["collection_status"], "ledger_missing")
            self.assertEqual(projects["absent"]["collection_status"], "path_missing")
            self.assertNotIn("remote-svc", projects)

    def test_pass1_foundation_projection_excludes_private_payload_text(self) -> None:
        with TemporaryDirectory() as tmpdir:
            manager_root = Path(tmpdir) / "manager"
            manifest_dir = manager_root / "switchboard" / "manifests"
            evidence_dir = manager_root / "docs" / "evidence"
            archive_dir = evidence_dir / "archive"
            private_state_dir = manager_root / "state" / "private"
            downloads_dir = manager_root / "downloads"
            project_root = Path(tmpdir) / "private-source"
            (project_root / "switchboard" / "local").mkdir(parents=True)
            (project_root / "switchboard" / "evidence").mkdir(parents=True)
            save_json(project_root / "switchboard" / "node.manifest.json", {"service_id": "private-source"})
            (project_root / "switchboard" / "local" / "tasks-completed.md").write_text(
                "\n".join(
                    [
                        "## 2026-05-24T00:55:00+05:30 | Private payload test",
                        "- Tags: task, handoff",
                        "- Summary: SECRET_FINANCE_ROW zappinfobot@example.com raw private payload",
                        "- Changed Paths: bank.csv, transcript.txt",
                        "- Agent: Codex",
                        "- Tool: codex-desktop",
                        "- Read Back: Confirmed the task.",
                        "- Scope Check: Scope stayed small.",
                        "- Notes:",
                        "  - personal-cost-payload should not leave metadata projection",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            save_json(
                manifest_dir / "workspaces.json",
                [
                    {
                        "workspace_id": "ws",
                        "name": "Workspace",
                        "tags": [],
                        "favorite_tier": "primary",
                        "servers": ["local_mac"],
                        "services": ["private-source"],
                        "notes": "",
                    }
                ],
            )
            save_json(
                manifest_dir / "servers.json",
                [
                    {
                        "server_id": "local_mac",
                        "name": "Local",
                        "connection_type": "local",
                        "host": "127.0.0.1",
                        "username": "p",
                    }
                ],
            )
            save_json(
                manifest_dir / "services.json",
                [
                    {
                        "service_id": "private-source",
                        "workspace_id": "ws",
                        "display_name": "Private Source",
                        "locations": [
                            {
                                "location_id": "private-local",
                                "server_id": "local_mac",
                                "access_mode": "local",
                                "root": str(project_root),
                                "role": "primary",
                                "is_primary": True,
                            }
                        ],
                    }
                ],
            )
            save_json(manifest_dir / "projects.json", [])
            save_json(manifest_dir / "project-environments.json", [])
            save_json(manifest_dir / "api-flows.json", [])
            settings = Settings(
                manifest_dir=manifest_dir,
                evidence_dir=evidence_dir,
                archive_dir=archive_dir,
                private_state_dir=private_state_dir,
                downloads_dir=downloads_dir,
            )
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            coordinator = CollectionCoordinator(settings, manifests, snapshots)

            projection = coordinator.control_center_context()["foundation_projection"]
            serialized = json.dumps(projection)

            self.assertEqual(projection["privacy"]["raw_payloads"], "excluded")
            self.assertNotIn("SECRET_FINANCE_ROW", serialized)
            self.assertNotIn("zappinfobot@example.com", serialized)
            self.assertNotIn("personal-cost-payload", serialized)
            self.assertNotIn("bank.csv", serialized)
            self.assertNotIn("transcript.txt", serialized)
            self.assertEqual(projection["agent_handoff_quality"]["task_count"], 1)
            self.assertEqual(projection["agent_handoff_quality"]["with_read_back"], 1)
            self.assertEqual(projection["agent_handoff_quality"]["with_scope_check"], 1)

    def test_foundation_projection_persists_to_switchboard_evidence(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(
                manifest_dir=root / "switchboard" / "manifests",
                evidence_dir=root / "docs" / "evidence",
                archive_dir=root / "docs" / "evidence" / "archive",
                private_state_dir=root / "state" / "private",
                downloads_dir=root / "downloads",
            )
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)

            record = snapshots.persist_foundation_projection(
                {
                    "generated": "2026-05-24T00:55:00+05:30",
                    "schema_version": "switchboard-pass1-foundation-v0",
                    "privacy": {"raw_payloads": "excluded"},
                }
            )
            loaded = snapshots.get_foundation_projection()

            self.assertEqual(record["schema_version"], "switchboard-pass1-foundation-v0")
            self.assertEqual(loaded["generated"], "2026-05-24T00:55:00+05:30")
            self.assertEqual(
                read_json(root / "switchboard" / "evidence" / "foundation-projection.json", {})["privacy"]["raw_payloads"],
                "excluded",
            )

    def test_node_snapshot_generates_foundation_projection_for_manager_root(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "switchboard" / "local").mkdir(parents=True)
            save_json(
                root / "switchboard" / "node.manifest.json",
                {
                    "service_id": "switch",
                    "display_name": "Switchboard",
                    "project_root": str(root),
                    "repo_paths": [str(root)],
                    "agent_contract": {"enabled_entrypoints": ["agents"]},
                },
            )
            (root / "switchboard" / "local" / "tasks-completed.md").write_text(
                "\n".join(
                    [
                        "## 2026-05-24T01:10:00+05:30 | Snapshot foundation",
                        "- Tags: task, handoff, scope",
                        "- Summary: Add snapshot-generated foundation projection.",
                        "- Changed Paths: switchboard/node.py, switchboard/evidence/foundation-projection.json, switchboard/local/tasks-completed.md",
                        "- Agent: Codex",
                        "- Tool: codex-desktop",
                        "- Read Back: Confirmed snapshot must generate foundation evidence.",
                        "- Scope Check: Snapshot integration only.",
                        "- Scope Entries:",
                        f"  - repo | dir | {root}",
                        f"  - doc | file | {root / 'switchboard' / 'evidence' / 'foundation-projection.json'}",
                        f"  - doc | file | {root / 'switchboard' / 'local' / 'tasks-completed.md'}",
                        f"  - exclude | dir | {root / '.git'}",
                        f"  - exclude | dir | {root / 'state'}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            save_json(
                root / "switchboard" / "manifests" / "workspaces.json",
                [
                    {
                        "workspace_id": "ws",
                        "name": "Workspace",
                        "tags": [],
                        "favorite_tier": "primary",
                        "servers": ["local_mac"],
                        "services": ["switch"],
                        "notes": "",
                    }
                ],
            )
            save_json(
                root / "switchboard" / "manifests" / "servers.json",
                [
                    {
                        "server_id": "local_mac",
                        "name": "Local",
                        "connection_type": "local",
                        "host": "127.0.0.1",
                        "username": "p",
                    }
                ],
            )
            save_json(
                root / "switchboard" / "manifests" / "services.json",
                [
                    {
                        "service_id": "switch",
                        "workspace_id": "ws",
                        "display_name": "Switchboard",
                        "locations": [
                            {
                                "location_id": "switch-local",
                                "server_id": "local_mac",
                                "access_mode": "local",
                                "root": str(root),
                                "role": "primary",
                                "is_primary": True,
                            }
                        ],
                    }
                ],
            )
            save_json(root / "switchboard" / "manifests" / "projects.json", [])
            save_json(root / "switchboard" / "manifests" / "project-environments.json", [])
            save_json(root / "switchboard" / "manifests" / "api-flows.json", [])

            result = snapshot_node(root)
            projection = read_json(root / "switchboard" / "evidence" / "foundation-projection.json", {})
            manifest = read_json(root / "switchboard" / "node.manifest.json", {})

            self.assertEqual(result["foundation_projection"]["schema_version"], "switchboard-pass1-foundation-v0")
            self.assertEqual(projection["schema_version"], "switchboard-pass1-foundation-v0")
            self.assertEqual(projection["privacy"]["raw_payloads"], "excluded")
            self.assertEqual(projection["agent_handoff_quality"]["task_count"], 1)
            self.assertEqual(
                manifest["evidence_paths"]["foundation_projection"],
                "switchboard/evidence/foundation-projection.json",
            )

    def test_manual_consolidation_scope_source_loads_agent_ops_manifest(self) -> None:
        manifests = ManifestStore(Settings())
        agent_ops = next(
            service for service in manifests.load_services() if service.service_id == "agent-ops"
        )
        self.assertIn(
            "manual_consolidation",
            {entry.source for entry in agent_ops.scope_entries},
        )

    def test_node_viewer_prefers_current_manifest_over_stale_runtime_cache(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "project"
            switchboard_root = project_root / "switchboard"
            switchboard_root.mkdir(parents=True)
            save_json(
                switchboard_root / "node.manifest.json",
                {
                    "service_id": "switch",
                    "installed_version": "1.12.7",
                    "bootstrap_version": "1.12.7",
                    "runtime_port": 8010,
                    "updated_at": "2026-05-15T00:00:00+00:00",
                },
            )
            save_json(
                root / "switchboard" / "manager.manifest.json",
                {
                    "managed_roots": [
                        {
                            "root_id": "switch",
                            "service_id": "switch",
                            "project_root": str(project_root),
                            "last_seen_version": "1.12.7",
                            "manifest_updated_at": "2026-05-15T00:00:00+00:00",
                        }
                    ]
                },
            )

            with mock.patch("switchboard.freshness.port_listening", return_value=False):
                rows = freshen_node_viewers(
                    manager_root=root,
                    service_payload={
                        "service_id": "switch",
                        "locations": [
                            {
                                "location_id": "local",
                                "server_id": "local",
                                "access_mode": "local",
                                "root": str(project_root),
                            }
                        ],
                    },
                    cached_rows=[
                        {
                            "service_id": "switch",
                            "location_id": "local",
                            "installed_version": "1.12.2",
                            "runtime_port": 8010,
                            "manifest_updated_at": "2026-04-22T00:00:00+00:00",
                        }
                    ],
                    control_center_version="1.12.7",
                )

            self.assertEqual(rows[0]["installed_version"], "1.12.7")
            self.assertEqual(rows[0]["target_manager_port"], 8020)
            self.assertEqual(rows[0]["legacy_runtime_port"], 8010)
            self.assertEqual(rows[0]["freshness_state"], "Manager unreachable")
            self.assertEqual(rows[0]["refresh_action"], "Check 8020")

    def test_freshness_envelope_marks_archive_older_than_truth_stale(self) -> None:
        envelope = freshness_envelope(
            data_as_of="2026-05-14T00:00:00+00:00",
            truth_as_of="2026-05-15T00:00:00+00:00",
            source="archive_snapshot",
            refresh_action="Collect",
        )
        self.assertEqual(envelope["freshness_state"], "Stale")
        self.assertEqual(envelope["stale_reason"], "cache_older_than_truth")
        self.assertEqual(envelope["refresh_action"], "Collect")

    def test_live_manager_health_overrides_stale_runtime_cache_without_rewriting_legacy_port(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "project"
            (project_root / "switchboard").mkdir(parents=True)
            save_json(
                project_root / "switchboard" / "node.manifest.json",
                {
                    "service_id": "switch",
                    "installed_version": "1.12.7",
                    "runtime_port": 8010,
                    "updated_at": "2026-05-15T00:00:00+00:00",
                },
            )
            save_json(
                root / "switchboard" / "manager.manifest.json",
                {
                    "managed_roots": [
                        {
                            "root_id": "switch",
                            "service_id": "switch",
                            "project_root": str(project_root),
                            "last_seen_version": "1.12.7",
                            "manifest_updated_at": "2026-05-15T00:00:00+00:00",
                        }
                    ]
                },
            )

            with mock.patch(
                "switchboard.freshness.manager_health",
                return_value={
                    "status": "ok",
                    "mode": "manager",
                    "manager_root": str(root.resolve()),
                    "runtime_port": 8020,
                    "manifest_runtime_port": 8010,
                    "checked_at": "2999-05-20T00:00:00+00:00",
                },
            ):
                rows = freshen_node_viewers(
                    manager_root=root,
                    service_payload={
                        "service_id": "switch",
                        "locations": [
                            {
                                "location_id": "local",
                                "server_id": "local",
                                "access_mode": "local",
                                "root": str(project_root),
                            }
                        ],
                    },
                    cached_rows=[
                        {
                            "service_id": "switch",
                            "location_id": "local",
                            "runtime_port": 8010,
                        }
                    ],
                    control_center_version="1.12.7",
                )

            self.assertEqual(rows[0]["freshness_state"], "Fresh")
            self.assertEqual(rows[0]["freshness_source"], "manager_health")
            self.assertEqual(rows[0]["runtime_port"], 8020)
            self.assertEqual(rows[0]["runtime_port_source"], "manager_health")
            self.assertEqual(rows[0]["target_manager_port"], 8020)
            self.assertEqual(rows[0]["manager_health_runtime_port"], 8020)
            self.assertEqual(rows[0]["manager_manifest_runtime_port"], 8010)
            self.assertEqual(rows[0]["manager_health_checked_at"], "2999-05-20T00:00:00+00:00")
            self.assertEqual(rows[0]["legacy_runtime_port"], 8010)
            self.assertIn("legacy", rows[0]["legacy_runtime_port_label"])
            self.assertEqual(rows[0]["refresh_action"], "")
            self.assertEqual(rows[0]["attention_reason"], "")

    def test_legacy_47_node_health_api_flows_are_disabled(self) -> None:
        flows = json.loads(Path("switchboard/manifests/api-flows.json").read_text(encoding="utf-8"))
        legacy = [flow for flow in flows if "legacy-node-health" in flow.get("tags", [])]
        self.assertTrue(legacy)
        for flow in legacy:
            self.assertFalse(flow.get("enabled"), flow["flow_id"])
            self.assertIn("unverified", flow.get("tags", []), flow["flow_id"])
            self.assertRegex(flow.get("base_url", ""), r":870[1-9]|:8710")
        aichat_flow = next(flow for flow in legacy if flow["flow_id"] == "aichat-node-health")
        self.assertEqual(aichat_flow["base_url"], "http://192.168.3.47:8702")

    def test_legacy_47_node_health_ports_are_not_current_service_ports(self) -> None:
        services = json.loads(Path("switchboard/manifests/services.json").read_text(encoding="utf-8"))
        for service in services:
            for location in service.get("locations", []):
                if location.get("server_id") != "pesu_dev_47":
                    continue
                runtime = location.get("runtime", {})
                old_ports = [
                    port for port in runtime.get("expected_ports", []) if 8701 <= int(port) <= 8710
                ]
                self.assertEqual(old_ports, [], service["service_id"])
                self.assertNotRegex(runtime.get("healthcheck_command", ""), r"870[1-9]|8710")
                if "legacy/unverified" in runtime.get("notes", ""):
                    self.assertIn("8020", runtime["notes"])

    def test_remote_service_node_actions_are_manager_limited(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(
                manifest_dir=root / "switchboard" / "manifests",
                evidence_dir=root / "docs" / "evidence",
                archive_dir=root / "docs" / "evidence" / "archive",
                private_state_dir=root / "state" / "private",
                downloads_dir=root / "downloads",
            )
            save_json(
                settings.manifest_dir / "servers.json",
                [
                    {
                        "server_id": "remote_box",
                        "name": "Remote Box",
                        "connection_type": "ssh",
                        "host": "example.invalid",
                        "username": "pesu",
                        "port": 22,
                        "tags": [],
                    }
                ],
            )
            save_json(
                settings.manifest_dir / "workspaces.json",
                [
                    {
                        "workspace_id": "zapp",
                        "name": "ZAPP",
                        "tags": [],
                        "favorite_tier": "primary",
                        "servers": ["remote_box"],
                        "services": ["svc"],
                        "notes": "",
                    }
                ],
            )
            save_json(
                settings.manifest_dir / "services.json",
                [
                    {
                        "service_id": "svc",
                        "workspace_id": "zapp",
                        "display_name": "Svc",
                        "kind": "service",
                        "ownership_tier": "owned",
                        "tags": [],
                        "favorite_tier": "primary",
                        "locations": [
                            {
                                "location_id": "svc-remote",
                                "server_id": "remote_box",
                                "access_mode": "ssh",
                                "root": "/srv/svc",
                                "role": "primary",
                                "is_primary": True,
                                "path_aliases": [],
                            }
                        ],
                    }
                ],
            )
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            coordinator = CollectionCoordinator(settings, manifests, snapshots)
            node_record = {
                "service_id": "svc",
                "location_id": "svc-remote",
                "server_id": "remote_box",
                "root": "/srv/svc",
                "node_present": True,
                "bootstrap_ready": True,
                "runtime_status": "stopped",
                "runtime_port": 8720,
            }

            with mock.patch.object(coordinator, "_node_inspect_record", return_value=node_record):
                deploy = coordinator.node_deploy("svc", NodeActionRequest(location_id="svc-remote"))
                upgrade = coordinator.node_upgrade("svc", NodeActionRequest(location_id="svc-remote"))
                restart = coordinator.node_restart("svc", NodeActionRequest(location_id="svc-remote"))

            self.assertEqual(deploy["status"], "permission_limited")
            self.assertEqual(upgrade["status"], "permission_limited")
            self.assertEqual(restart["status"], "permission_limited")
            self.assertIn("remote manager", deploy["message"].lower())
            self.assertIn("remote manager", upgrade["message"].lower())
            self.assertIn("remote manager", restart["message"].lower())

    def test_project_service_assignment_moves_ownership_and_renames_cleanly(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(
                manifest_dir=root / "switchboard" / "manifests",
                evidence_dir=root / "docs" / "evidence",
                archive_dir=root / "docs" / "evidence" / "archive",
                private_state_dir=root / "state" / "private",
                downloads_dir=root / "downloads",
            )
            save_json(
                settings.manifest_dir / "workspaces.json",
                [
                    {
                        "workspace_id": "pesu",
                        "name": "PESU",
                        "tags": [],
                        "favorite_tier": "primary",
                        "servers": [],
                        "services": ["aichat", "aichat_test", "aichat_ingestion"],
                        "notes": "",
                    },
                    {
                        "workspace_id": "zapp",
                        "name": "ZAPP",
                        "tags": [],
                        "favorite_tier": "none",
                        "servers": [],
                        "services": ["docgen"],
                        "notes": "",
                    },
                ],
            )
            save_json(settings.manifest_dir / "servers.json", [])
            save_json(
                settings.manifest_dir / "services.json",
                [
                    {"service_id": "aichat", "workspace_id": "pesu", "display_name": "aichat"},
                    {"service_id": "aichat_test", "workspace_id": "pesu", "display_name": "aichat_test"},
                    {"service_id": "aichat_ingestion", "workspace_id": "pesu", "display_name": "aichat_ingestion"},
                    {"service_id": "docgen", "workspace_id": "zapp", "display_name": "docgen"},
                ],
            )
            save_json(
                settings.manifest_dir / "projects.json",
                [
                    {
                        "project_id": "aichat_project",
                        "workspace_id": "pesu",
                        "display_name": "aichat",
                        "parent_project_id": None,
                        "service_ids": ["aichat"],
                        "tags": [],
                        "notes": "",
                    },
                    {
                        "project_id": "aichat_test_project",
                        "workspace_id": "pesu",
                        "display_name": "aichat_test",
                        "parent_project_id": None,
                        "service_ids": ["aichat_test"],
                        "tags": [],
                        "notes": "",
                    },
                    {
                        "project_id": "aichat_child",
                        "workspace_id": "pesu",
                        "display_name": "child",
                        "parent_project_id": "aichat_project",
                        "service_ids": [],
                        "tags": [],
                        "notes": "",
                    },
                ],
            )
            save_json(
                settings.manifest_dir / "project-environments.json",
                [
                    {
                        "environment_id": "aichat_prod",
                        "project_id": "aichat_project",
                        "display_name": "aichat prod",
                        "kind": "prod",
                        "deployments": [],
                        "tags": [],
                        "notes": "",
                    }
                ],
            )

            manifests = ManifestStore(settings)

            created = manifests.create_project(
                "pesu",
                ProjectCreateRequest(
                    project_id="combined",
                    display_name="Combined",
                    service_ids=["aichat_ingestion", "aichat_ingestion"],
                ),
            )
            self.assertEqual(created.service_ids, ["aichat_ingestion"])

            moved = manifests.patch_project(
                "aichat_project",
                ProjectPatchRequest(service_ids=["aichat", "aichat_test", "aichat_ingestion"]),
            )
            self.assertEqual(moved.service_ids, ["aichat", "aichat_test", "aichat_ingestion"])
            projects_by_id = {project.project_id: project for project in manifests.load_projects()}
            self.assertEqual(projects_by_id["aichat_test_project"].service_ids, [])
            self.assertEqual(projects_by_id["combined"].service_ids, [])
            all_pesu_service_owners = [
                service_id
                for project in projects_by_id.values()
                if project.workspace_id == "pesu"
                for service_id in project.service_ids
            ]
            self.assertEqual(len(all_pesu_service_owners), len(set(all_pesu_service_owners)))

            renamed_display = manifests.patch_project(
                "aichat_project",
                ProjectPatchRequest(display_name="AI Chat Suite"),
            )
            self.assertEqual(renamed_display.project_id, "aichat_project")
            self.assertEqual(renamed_display.display_name, "AI Chat Suite")

            renamed_id = manifests.patch_project(
                "aichat_project",
                ProjectPatchRequest(project_id="ai_chat_suite"),
            )
            self.assertEqual(renamed_id.project_id, "ai_chat_suite")
            projects_by_id = {project.project_id: project for project in manifests.load_projects()}
            self.assertEqual(projects_by_id["aichat_child"].parent_project_id, "ai_chat_suite")
            environments = manifests.load_project_environments()
            self.assertEqual(environments[0].project_id, "ai_chat_suite")

            cleared_parent = manifests.patch_project(
                "aichat_child",
                ProjectPatchRequest(parent_project_id=None),
            )
            self.assertIsNone(cleared_parent.parent_project_id)
            projects_by_id = {project.project_id: project for project in manifests.load_projects()}
            self.assertIsNone(projects_by_id["aichat_child"].parent_project_id)
            raw_projects = json.loads((settings.manifest_dir / "projects.json").read_text(encoding="utf-8"))
            raw_child = next(item for item in raw_projects if item["project_id"] == "aichat_child")
            self.assertIn("parent_project_id", raw_child)
            self.assertIsNone(raw_child["parent_project_id"])

            with self.assertRaises(ValueError):
                manifests.patch_project("ai_chat_suite", ProjectPatchRequest(service_ids=["docgen"]))

    def test_delete_service_clears_active_service_data(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_dir = root / "switchboard" / "manifests"
            evidence_dir = root / "docs" / "evidence"
            archive_dir = evidence_dir / "archive"
            private_state_dir = root / "state" / "private"
            downloads_dir = root / "downloads"

            save_json(
                manifest_dir / "servers.json",
                [
                    {
                        "server_id": "local_mac",
                        "name": "Local Mac",
                        "connection_type": "local",
                        "host": "localhost",
                        "username": "p",
                        "port": 22,
                        "tags": [],
                    }
                ],
            )
            save_json(
                manifest_dir / "workspaces.json",
                [
                    {
                        "workspace_id": "pesu",
                        "name": "PESU",
                        "tags": [],
                        "favorite_tier": "primary",
                        "servers": ["local_mac"],
                        "services": ["emailagent"],
                        "notes": "",
                    }
                ],
            )
            save_json(
                manifest_dir / "services.json",
                [
                    {
                        "service_id": "emailagent",
                        "workspace_id": "pesu",
                        "display_name": "Email Agent",
                        "kind": "service",
                        "ownership_tier": "owned",
                        "tags": [],
                        "favorite_tier": "primary",
                        "locations": [
                            {
                                "location_id": "emailagent-local",
                                "server_id": "local_mac",
                                "access_mode": "local",
                                "root": "/tmp/emailagent",
                                "role": "primary",
                                "is_primary": True,
                                "path_aliases": [],
                            }
                        ],
                        "scope_entries": [
                            {
                                "entry_id": "repo-1",
                                "kind": "repo",
                                "path": "/tmp/emailagent",
                                "path_type": "dir",
                                "source": "user_added",
                                "enabled": True,
                            }
                        ],
                    }
                ],
            )

            archive_token = "2026-04-01T00-00-00+00-00"
            archive_snapshot_rel = f"evidence/archive/{archive_token}/workspace-pesu.json"
            save_json(
                evidence_dir / "workspace-registry.json",
                {
                    "generated": "2026-04-01T00:00:00+00:00",
                    "workspaces": [
                        {
                            "workspace_id": "pesu",
                            "name": "PESU",
                            "servers": ["local_mac"],
                            "services": ["emailagent"],
                            "service_count": 1,
                            "last_status": "partial",
                        }
                    ],
                },
            )
            save_json(
                evidence_dir / "service-inventory.json",
                {
                    "generated": "2026-04-01T00:00:00+00:00",
                    "services": [
                        {
                            "service_id": "emailagent",
                            "workspace_id": "pesu",
                            "display_name": "Email Agent",
                            "last_status": "ok",
                        }
                    ],
                },
            )
            save_json(
                evidence_dir / "repo-inventory.json",
                {
                    "generated": "2026-04-01T00:00:00+00:00",
                    "repos": [{"service_id": "emailagent", "repo_path": "/tmp/emailagent"}],
                },
            )
            save_json(
                evidence_dir / "docs-index.json",
                {
                    "generated": "2026-04-01T00:00:00+00:00",
                    "files": [{"service_id": "emailagent", "path": "/tmp/emailagent/README.md"}],
                },
            )
            save_json(
                evidence_dir / "logs-index.json",
                {
                    "generated": "2026-04-01T00:00:00+00:00",
                    "files": [{"service_id": "emailagent", "path": "/tmp/emailagent/server.log"}],
                },
            )
            save_json(
                evidence_dir / "pull-bundle-history.json",
                {
                    "generated": "2026-04-01T00:00:00+00:00",
                    "bundles": [{"service_id": "emailagent", "bundle_id": "bundle-1"}],
                },
            )
            save_json(
                evidence_dir / "repo-safety-history.json",
                {
                    "generated": "2026-04-01T00:00:00+00:00",
                    "checks": [{"service_id": "emailagent", "repo_path": "/tmp/emailagent"}],
                },
            )
            save_json(
                evidence_dir / "run-history.json",
                {
                    "generated": "2026-04-01T00:00:00+00:00",
                    "runs": [
                        {
                            "workspace_id": "pesu",
                            "generated": "2026-04-01T00:00:00+00:00",
                            "archive_path": archive_snapshot_rel,
                            "status": "partial",
                            "service_count": 1,
                            "server_count": 1,
                        }
                    ],
                },
            )
            save_json(
                archive_dir / archive_token / "workspace-pesu.json",
                {
                    "generated": "2026-04-01T00:00:00+00:00",
                    "workspace": {"workspace_id": "pesu", "name": "PESU"},
                    "servers": [{"server_id": "local_mac", "status": "ok"}],
                    "services": [{"service_id": "emailagent", "status": "ok"}],
                    "repo_inventory": [{"service_id": "emailagent", "repo_path": "/tmp/emailagent"}],
                    "docs_index": [{"service_id": "emailagent", "path": "/tmp/emailagent/README.md"}],
                    "logs_index": [{"service_id": "emailagent", "path": "/tmp/emailagent/server.log"}],
                    "secret_path_index": [{"service_id": "emailagent", "path": "/tmp/emailagent/.env"}],
                    "summary": {"status": "partial", "service_count": 1, "server_count": 1},
                },
            )
            save_json(
                private_state_dir / "secret-path-index.json",
                {
                    "generated": "2026-04-01T00:00:00+00:00",
                    "entries": [{"service_id": "emailagent", "path": "/tmp/emailagent/.env"}],
                },
            )
            save_json(
                private_state_dir / "repo-safety-findings.json",
                {
                    "generated": "2026-04-01T00:00:00+00:00",
                    "checks": [{"service_id": "emailagent", "findings": [{"path": ".env"}]}],
                },
            )
            save_json(
                private_state_dir / "runtime-cache.json",
                {
                    "generated": "",
                    "runtime_checks": {"emailagent": {"emailagent_local": {"service_id": "emailagent"}}},
                    "node_sync": {"emailagent": {"emailagent_local": {"service_id": "emailagent"}}},
                    "node_viewer": {"emailagent": {"emailagent_local": {"service_id": "emailagent"}}},
                    "task_ledger": {"emailagent": {"emailagent_local": {"tasks": [{"service_id": "emailagent"}]}}},
                    "environment_runtime_snapshots": {
                        "env": {
                            "locations": [{"service_id": "emailagent"}, {"service_id": "other"}],
                            "process_findings": [{"service_id": "emailagent"}, {"service_id": "other"}],
                        }
                    },
                },
            )

            bundle_dir = downloads_dir / "pesu" / "emailagent"
            bundle_dir.mkdir(parents=True, exist_ok=True)
            (bundle_dir / "marker.txt").write_text("x", encoding="utf-8")

            settings = Settings(
                manifest_dir=manifest_dir,
                evidence_dir=evidence_dir,
                archive_dir=archive_dir,
                private_state_dir=private_state_dir,
                downloads_dir=downloads_dir,
            )
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)

            removed = manifests.delete_service("emailagent")
            result = snapshots.delete_service_data("emailagent", removed.workspace_id)

            self.assertTrue(result["deleted"])
            self.assertEqual(removed.workspace_id, "pesu")
            self.assertEqual(manifests.load_services(), [])
            self.assertEqual(manifests.get_workspace("pesu").services, [])
            self.assertFalse((downloads_dir / "pesu" / "emailagent").exists())
            self.assertEqual(read_json(evidence_dir / "service-inventory.json", {"services": []})["services"], [])
            self.assertEqual(read_json(evidence_dir / "repo-inventory.json", {"repos": []})["repos"], [])
            self.assertEqual(read_json(evidence_dir / "docs-index.json", {"files": []})["files"], [])
            self.assertEqual(read_json(evidence_dir / "logs-index.json", {"files": []})["files"], [])
            self.assertEqual(read_json(evidence_dir / "pull-bundle-history.json", {"bundles": []})["bundles"], [])
            self.assertEqual(read_json(evidence_dir / "repo-safety-history.json", {"checks": []})["checks"], [])
            self.assertEqual(read_json(private_state_dir / "secret-path-index.json", {"entries": []})["entries"], [])
            self.assertEqual(read_json(private_state_dir / "repo-safety-findings.json", {"checks": []})["checks"], [])
            self.assertEqual(
                read_json(evidence_dir / "workspace-registry.json", {"workspaces": []})["workspaces"][0]["service_count"],
                0,
            )
            self.assertEqual(
                read_json(archive_dir / archive_token / "workspace-pesu.json", {})["summary"]["service_count"],
                0,
            )
            self.assertEqual(
                read_json(archive_dir / archive_token / "workspace-pesu.json", {})["services"],
                [],
            )
            runtime_cache = read_json(private_state_dir / "runtime-cache.json", {})
            self.assertNotIn("emailagent", runtime_cache.get("runtime_checks", {}))
            self.assertNotIn("emailagent", runtime_cache.get("node_sync", {}))
            self.assertNotIn("emailagent", runtime_cache.get("node_viewer", {}))
            self.assertNotIn("emailagent", runtime_cache.get("task_ledger", {}))
            self.assertEqual(runtime_cache["environment_runtime_snapshots"]["env"]["locations"], [{"service_id": "other"}])
            self.assertEqual(runtime_cache["environment_runtime_snapshots"]["env"]["process_findings"], [{"service_id": "other"}])

    def test_pull_bundle_includes_repo_entries(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "project"
            project_root.mkdir()
            (project_root / "main.py").write_text("print('ok')\n", encoding="utf-8")
            (project_root / "README.md").write_text("# test\n", encoding="utf-8")

            manifest_dir = root / "switchboard" / "manifests"
            evidence_dir = root / "docs" / "evidence"
            archive_dir = evidence_dir / "archive"
            private_state_dir = root / "state" / "private"
            downloads_dir = root / "downloads"

            save_json(
                manifest_dir / "servers.json",
                [
                    {
                        "server_id": "local_mac",
                        "name": "Local Mac",
                        "connection_type": "local",
                        "host": "localhost",
                        "username": "p",
                        "port": 22,
                        "tags": [],
                    }
                ],
            )
            save_json(
                manifest_dir / "workspaces.json",
                [
                    {
                        "workspace_id": "zapp",
                        "name": "ZAPP",
                        "tags": [],
                        "favorite_tier": "primary",
                        "servers": ["local_mac"],
                        "services": ["svc"],
                        "notes": "",
                    }
                ],
            )
            save_json(
                manifest_dir / "services.json",
                [
                    {
                        "service_id": "svc",
                        "workspace_id": "zapp",
                        "display_name": "Svc",
                        "locations": [
                            {
                                "location_id": "svc-local",
                                "server_id": "local_mac",
                                "access_mode": "local",
                                "root": str(project_root),
                                "role": "primary",
                                "is_primary": True,
                                "path_aliases": [],
                            }
                        ],
                        "scope_entries": [
                            {
                                "entry_id": "repo-1",
                                "kind": "repo",
                                "path": str(project_root / "main.py"),
                                "path_type": "file",
                                "source": "user_added",
                                "enabled": True,
                            },
                            {
                                "entry_id": "doc-1",
                                "kind": "doc",
                                "path": str(project_root / "README.md"),
                                "path_type": "file",
                                "source": "user_added",
                                "enabled": True,
                            },
                        ],
                    }
                ],
            )

            settings = Settings(
                manifest_dir=manifest_dir,
                evidence_dir=evidence_dir,
                archive_dir=archive_dir,
                private_state_dir=private_state_dir,
                downloads_dir=downloads_dir,
            )
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            coordinator = CollectionCoordinator(settings, manifests, snapshots)
            snapshots.persist_task_ledger(
                "svc",
                "svc-local",
                [
                    {
                        "timestamp": "2026-04-29T00:00:00+00:00",
                        "title": "AI dependency note",
                        "dependencies": [{"kind": "api", "name": "gpt-4.1", "notes": "LLM"}],
                        "cross_dependencies": [{"kind": "library", "name": "text-embedding-3-small", "notes": "embedding model"}],
                        "notes": ["Uses Gemini CLI handoff in docs."],
                    }
                ],
            )

            result = coordinator.pull_bundle("svc", PullBundleRequest())

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["file_count"], 2)
            self.assertEqual(result["authority"]["source"], "control-center")
            self.assertIn("composition", result["dependency_context"])
            language_names = {item["name"] for item in result["dependency_context"]["composition"]["language_percentages"]}
            self.assertIn("Python", language_names)
            model_names = {item["name"].lower() for item in result["dependency_context"]["composition"]["models"]}
            self.assertIn("gpt-4.1", model_names)
            self.assertIn("text-embedding-3-small", model_names)
            files = {Path(item["target_path"]).name: item for item in result["files"]}
            self.assertIn("main.py", files)
            self.assertIn("README.md", files)
            self.assertEqual(files["main.py"]["kind"], "repo")

    def test_scope_classifier_defaults_python_file_to_repo(self) -> None:
        settings = Settings()
        manifests = ManifestStore(settings)
        snapshots = SnapshotStore(settings, manifests)
        coordinator = CollectionCoordinator(settings, manifests, snapshots)

        self.assertEqual(coordinator._suggest_scope_kind("main.py", "/workspace/aichat/main.py", "file"), "repo")
        self.assertEqual(coordinator._suggest_scope_kind("README.md", "/workspace/aichat/README.md", "file"), "doc")
        self.assertEqual(coordinator._suggest_scope_kind("backend", "/workspace/aichat/backend", "dir"), "doc")

    def test_pull_bundle_respects_explicit_ds_store_exclude(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = Settings()
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            coordinator = CollectionCoordinator(settings, manifests, snapshots)
            root = Path(tmpdir) / "repo"
            root.mkdir(parents=True)
            (root / "main.py").write_text("print('ok')\n", encoding="utf-8")
            (root / ".DS_Store").write_text("junk\n", encoding="utf-8")

            service = ServiceManifest(
                service_id="svc",
                workspace_id="ws",
                display_name="Svc",
                locations=[
                    LocationSpec(
                        location_id="loc",
                        server_id="local_mac",
                        access_mode="local",
                        root=str(root),
                        role="primary",
                        is_primary=True,
                        path_aliases=[],
                    )
                ],
                scope_entries=[
                    ScopeEntry(kind="repo", path=str(root), path_type="dir", source="user_added", enabled=True),
                    ScopeEntry(kind="exclude", path=str(root / ".DS_Store"), path_type="file", source="user_added", enabled=True),
                ],
                repo_paths=[str(root)],
                docs_paths=[],
                log_paths=[],
                allowed_git_pull_paths=[str(root)],
                exclude_globs=[str(root / ".DS_Store")],
            )

            manifests.get_service = lambda _service_id: service  # type: ignore[assignment]
            manifests.resolve_server = lambda *_args, **_kwargs: ResolvedServer(  # type: ignore[assignment]
                server_id="local_mac",
                name="Local",
                connection_type="local",
                host="127.0.0.1",
                username="p",
                port=22,
                tags=[],
                favorite_tier="primary",
                notes="",
                password=None,
            )

            result = coordinator.pull_bundle("svc", PullBundleRequest())
            copied_names = {Path(item["target_path"]).name for item in result["files"]}

            self.assertIn("main.py", copied_names)
            self.assertNotIn(".DS_Store", copied_names)

    def test_pull_bundle_excludes_env_files_and_reports_review_state(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            root.mkdir(parents=True)
            (root / "app.py").write_text("token = 'placeholder-secret-value'\n", encoding="utf-8")
            (root / ".env.local").write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
            (root / ".npmrc").write_text("//registry.npmjs.org/:_authToken=npm-test\n", encoding="utf-8")
            outside = Path(tmpdir) / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")

            settings = Settings(
                manifest_dir=Path(tmpdir) / "switchboard" / "manifests",
                evidence_dir=Path(tmpdir) / "docs" / "evidence",
                archive_dir=Path(tmpdir) / "docs" / "evidence" / "archive",
                private_state_dir=Path(tmpdir) / "state" / "private",
                downloads_dir=Path(tmpdir) / "downloads",
            )
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            coordinator = CollectionCoordinator(settings, manifests, snapshots)
            service = ServiceManifest(
                service_id="svc",
                workspace_id="ws",
                display_name="Svc",
                locations=[
                    LocationSpec(
                        location_id="loc",
                        server_id="local_mac",
                        access_mode="local",
                        root=str(root),
                        role="primary",
                        is_primary=True,
                        path_aliases=[],
                    )
                ],
                scope_entries=[
                    ScopeEntry(kind="repo", path=str(root), path_type="dir", source="user_added", enabled=True),
                    ScopeEntry(kind="doc", path=str(outside), path_type="file", source="user_added", enabled=True),
                ],
                repo_paths=[str(root)],
            )
            manifests.get_service = lambda _service_id: service  # type: ignore[assignment]
            manifests.resolve_server = lambda *_args, **_kwargs: ResolvedServer(  # type: ignore[assignment]
                server_id="local_mac",
                name="Local",
                connection_type="local",
                host="127.0.0.1",
                username="p",
                port=22,
                tags=[],
                favorite_tier="primary",
                notes="",
                password=None,
            )

            result = coordinator.pull_bundle("svc", PullBundleRequest())

            copied_relative_paths = {item["relative_path"] for item in result["files"]}
            self.assertIn("app.py", copied_relative_paths)
            self.assertNotIn(".env.local", copied_relative_paths)
            self.assertNotIn(".npmrc", copied_relative_paths)
            self.assertFalse(Path(result["source_tree_path"], ".env.local").exists())
            self.assertFalse(Path(result["source_tree_path"], ".npmrc").exists())
            self.assertEqual(result["authority"]["source"], "control-center")
            self.assertEqual(
                result["skipped_entries"],
                [{"path": str(outside), "kind": "doc", "path_type": "file", "reason": "outside_location_root"}],
            )
            self.assertEqual(result["exposure_findings"][0]["relative_path"], "app.py")
            self.assertTrue(result["exposure_findings"][0]["redacted"])

    def test_pull_bundle_backup_clean_excludes_noise_and_summarizes_evidence(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            root.mkdir(parents=True)
            (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
            (root / "uv.lock").write_text("uv lock\n", encoding="utf-8")
            (root / "package-lock.json").write_text('{"lockfileVersion": 3}\n', encoding="utf-8")
            (root / ".DS_Store").write_text("junk\n", encoding="utf-8")
            (root / ".npm-cache" / "_logs").mkdir(parents=True)
            (root / ".npm-cache" / "_logs" / "debug.log").write_text("token in cache\n", encoding="utf-8")
            (root / ".pytest_cache").mkdir()
            (root / ".pytest_cache" / "nodeids").write_text("cached\n", encoding="utf-8")
            (root / ".claude").mkdir()
            (root / ".claude" / "settings.local.json").write_text('{"token":"local"}\n', encoding="utf-8")
            save_json(
                root / "docs" / "evidence" / "pull-bundle-history.json",
                {"generated": "2026-05-20T00:00:00+00:00", "bundles": [{"secret": "raw-history-token"}]},
            )
            save_json(
                root / "switchboard" / "evidence" / "completed-tasks.json",
                {
                    "generated": "2026-05-20T00:01:00+00:00",
                    "tasks": [
                        {
                            "timestamp": "2026-05-19T00:01:00+00:00",
                            "title": "Older task",
                            "summary": "Older summary",
                            "changed_paths": [],
                        },
                        {
                            "timestamp": "2026-05-20T00:01:00+00:00",
                            "title": "Latest task",
                            "summary": "Task summary",
                            "changed_paths": ["app.py"],
                        }
                    ],
                },
            )
            save_json(
                root / "switchboard" / "evidence" / "scope.snapshot.json",
                {
                    "generated": "2026-05-20T00:02:00+00:00",
                    "service_id": "svc",
                    "scope_entries": [{"kind": "repo"}, {"kind": "doc"}],
                },
            )
            save_json(
                root / "switchboard" / "evidence" / "update-gate.json",
                {
                    "generated": "2026-05-20T00:03:00+00:00",
                    "status": "ok",
                    "checks": [{"status": "ok"}, {"status": "ok"}],
                },
            )
            save_json(
                root / "switchboard" / "evidence" / "doc-index.json",
                {
                    "generated": "2026-05-20T00:04:00+00:00",
                    "docs": [{"enabled": True}, {"enabled": False}],
                },
            )

            settings = Settings(
                manifest_dir=Path(tmpdir) / "switchboard" / "manifests",
                evidence_dir=Path(tmpdir) / "docs" / "evidence",
                archive_dir=Path(tmpdir) / "docs" / "evidence" / "archive",
                private_state_dir=Path(tmpdir) / "state" / "private",
                downloads_dir=Path(tmpdir) / "downloads",
            )
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            coordinator = CollectionCoordinator(settings, manifests, snapshots)
            service = ServiceManifest(
                service_id="svc",
                workspace_id="ws",
                display_name="Svc",
                locations=[
                    LocationSpec(
                        location_id="loc",
                        server_id="local_mac",
                        access_mode="local",
                        root=str(root),
                        role="primary",
                        is_primary=True,
                        path_aliases=[],
                    )
                ],
                scope_entries=[
                    ScopeEntry(kind="repo", path=str(root), path_type="dir", source="user_added", enabled=True),
                    ScopeEntry(kind="doc", path=str(root / "switchboard" / "evidence" / "completed-tasks.json"), path_type="file", source="user_added", enabled=True),
                ],
                repo_paths=[str(root)],
            )
            manifests.get_service = lambda _service_id: service  # type: ignore[assignment]
            manifests.resolve_server = lambda *_args, **_kwargs: ResolvedServer(  # type: ignore[assignment]
                server_id="local_mac",
                name="Local",
                connection_type="local",
                host="127.0.0.1",
                username="p",
                port=22,
                tags=[],
                favorite_tier="primary",
                notes="",
                password=None,
            )

            result = coordinator.pull_bundle("svc", PullBundleRequest(location_id="loc"))

            copied_relative_paths = {item["relative_path"] for item in result["files"]}
            self.assertEqual(result["bundle_profile"], "backup-clean")
            self.assertTrue(result["backup_clean"])
            self.assertEqual(result["backup_readiness_status"], "review_required")
            self.assertTrue(result["review_required"])
            self.assertFalse(result["proof_only"])
            self.assertTrue(result["not_backup_ready"])
            self.assertTrue(result["authority_fresh"])
            self.assertEqual(result["unresolved_exposure_count"], 0)
            self.assertEqual(result["exposure_review_status"], "reviewed")
            self.assertTrue(result["skipped_review_required"])
            self.assertEqual(result["skipped_review_count"], 1)
            self.assertIn("skipped_entries_need_review", result["readiness_reasons"])
            self.assertIn("app.py", copied_relative_paths)
            self.assertIn("uv.lock", copied_relative_paths)
            self.assertIn("package-lock.json", copied_relative_paths)
            self.assertNotIn(".DS_Store", copied_relative_paths)
            self.assertFalse(any(path.startswith(".npm-cache/") for path in copied_relative_paths))
            self.assertFalse(any(path.startswith(".pytest_cache/") for path in copied_relative_paths))
            self.assertNotIn(".claude/settings.local.json", copied_relative_paths)
            self.assertFalse(any(path.startswith("docs/evidence/") for path in copied_relative_paths))
            self.assertFalse(any(path.startswith("switchboard/evidence/") for path in copied_relative_paths))
            self.assertIn(
                {"path": str(root / "switchboard" / "evidence" / "completed-tasks.json"), "kind": "doc", "path_type": "file", "reason": "metadata_summarized"},
                result["skipped_entries"],
            )
            summaries = result["metadata_summaries"]
            self.assertEqual(summaries["profile"], "backup-clean")
            self.assertEqual(summaries["raw_evidence_files"], "metadata_summary_only")
            self.assertEqual(summaries["completed_tasks_summary"]["latest_task"]["title"], "Latest task")
            self.assertEqual(summaries["scope_snapshot_summary"]["scope_entry_count"], 2)
            self.assertEqual(summaries["update_gate_summary"]["status"], "ok")
            self.assertEqual(summaries["doc_index_summary"]["doc_count"], 2)
            self.assertEqual(summaries["skipped_summary"]["metadata_summarized"], 1)
            self.assertEqual(result["preflight"]["bundle_profile"], "backup-clean")
            manifest = read_json(Path(result["manifest_path"]), {})
            self.assertEqual(manifest["backup_readiness_status"], "review_required")
            self.assertEqual(manifest["skipped_review_count"], 1)
            history = read_json(settings.evidence_dir / "pull-bundle-history.json", {"bundles": []})
            self.assertEqual(history["bundles"][0]["backup_readiness_status"], "review_required")
            self.assertEqual(history["bundles"][0]["exposure_summary"], {})

    def test_pull_bundle_legacy_history_normalizes_as_proof_only(self) -> None:
        settings = Settings()
        manifests = ManifestStore(settings)
        snapshots = SnapshotStore(settings, manifests)
        coordinator = CollectionCoordinator(settings, manifests, snapshots)
        legacy = {
            "bundle_id": "legacy-proof",
            "service_id": "svc",
            "server_id": "local_mac",
            "file_count": 2,
            "skipped_entry_count": 1,
            "skipped_entries": [
                {"path": "/tmp/missing", "kind": "doc", "path_type": "file", "reason": "no_files_matched"}
            ],
            "exposure_findings": [
                {
                    "relative_path": "app.py",
                    "finding_kind": "generic_token",
                    "variable_name": "API_TOKEN",
                    "line_number": 1,
                    "redacted": True,
                },
                {
                    "relative_path": "app.py",
                    "finding_kind": "generic_token",
                    "variable_name": "",
                    "line_number": 2,
                    "redacted": True,
                },
            ],
        }

        normalized = coordinator.normalize_pull_bundle_record(legacy)

        self.assertEqual(normalized["backup_readiness_status"], "proof_only")
        self.assertFalse(normalized["backup_clean"])
        self.assertNotIn("bundle_profile", normalized)
        self.assertTrue(normalized["proof_only"])
        self.assertFalse(normalized["review_required"])
        self.assertTrue(normalized["not_backup_ready"])
        self.assertFalse(normalized["authority_fresh"])
        self.assertEqual(normalized["unresolved_exposure_count"], 2)
        self.assertEqual(normalized["exposure_review_status"], "unreviewed")
        self.assertEqual(normalized["exposure_summary"], {"generic_token": 2})
        self.assertEqual(normalized["exposure_variable_summary"], {"API_TOKEN": 1})
        self.assertEqual(normalized["skipped_review_count"], 1)
        self.assertTrue(normalized["skipped_review_required"])
        self.assertIn("legacy_proof_bundle", normalized["readiness_reasons"])
        self.assertIn("not_backup_clean", normalized["readiness_reasons"])

    def test_pull_bundle_list_api_normalizes_legacy_readiness(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(
                manifest_dir=root / "switchboard" / "manifests",
                evidence_dir=root / "docs" / "evidence",
                archive_dir=root / "docs" / "evidence" / "archive",
                private_state_dir=root / "state" / "private",
                downloads_dir=root / "downloads",
            )
            save_json(
                settings.manifest_dir / "services.json",
                [
                    {
                        "service_id": "svc",
                        "workspace_id": "ws",
                        "display_name": "Svc",
                    }
                ],
            )
            save_json(
                settings.evidence_dir / "pull-bundle-history.json",
                {
                    "generated": "2026-05-20T00:00:00+00:00",
                    "bundles": [
                        {
                            "bundle_id": "legacy-proof",
                            "created_at": "2026-05-20T00:00:00+00:00",
                            "workspace_id": "ws",
                            "service_id": "svc",
                            "server_id": "local_mac",
                            "file_count": 1,
                            "docs_count": 0,
                            "logs_count": 0,
                            "manifest_path": "/tmp/missing",
                            "repo_commits": [],
                            "exposure_findings": [{"finding_kind": "generic_token"}],
                        }
                    ],
                },
            )
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            coordinator = CollectionCoordinator(settings, manifests, snapshots)
            with (
                mock.patch.object(api_module, "manifest_store", manifests),
                mock.patch.object(api_module, "snapshot_store", snapshots),
                mock.patch.object(api_module, "coordinator", coordinator),
            ):
                body = api_module.list_pull_bundles("svc")

            self.assertEqual(body["bundles"][0]["backup_readiness_status"], "proof_only")
            self.assertFalse(body["bundles"][0]["backup_clean"])
            self.assertEqual(body["bundles"][0]["unresolved_exposure_count"], 1)
            self.assertEqual(body["bundles"][0]["exposure_summary"], {"generic_token": 1})
            self.assertEqual(body["bundles"][0]["exposure_review"]["review_state_counts"]["unreviewed"], 1)

    def test_pull_bundle_exposure_review_projection_groups_findings_without_mutating_history(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(
                manifest_dir=root / "switchboard" / "manifests",
                evidence_dir=root / "docs" / "evidence",
                archive_dir=root / "docs" / "evidence" / "archive",
                private_state_dir=root / "state" / "private",
                downloads_dir=root / "downloads",
            )
            save_json(
                settings.manifest_dir / "services.json",
                [
                    {
                        "service_id": "svc",
                        "workspace_id": "ws",
                        "display_name": "Svc",
                    }
                ],
            )
            bundle = {
                "bundle_id": "bundle-1",
                "created_at": "2026-05-20T00:00:00+00:00",
                "workspace_id": "ws",
                "service_id": "svc",
                "server_id": "local_mac",
                "bundle_profile": "backup-clean",
                "backup_clean": True,
                "authority_fresh": True,
                "file_count": 1,
                "docs_count": 0,
                "logs_count": 0,
                "manifest_path": "/tmp/missing",
                "repo_commits": [],
                "exposure_findings": [
                    {
                        "relative_path": "app.py",
                        "finding_kind": "generic_token",
                        "variable_name": "API_TOKEN",
                        "line_number": 1,
                        "redacted": True,
                    },
                    {
                        "relative_path": "app.py",
                        "finding_kind": "generic_token",
                        "variable_name": "API_TOKEN",
                        "line_number": 2,
                        "redacted": True,
                    },
                    {
                        "relative_path": "settings.py",
                        "finding_kind": "generic_token",
                        "variable_name": "PASSWORD",
                        "line_number": 3,
                        "redacted": True,
                    },
                ],
            }
            save_json(
                settings.evidence_dir / "pull-bundle-history.json",
                {"generated": "2026-05-20T00:00:00+00:00", "bundles": [bundle]},
            )
            save_json(
                settings.evidence_dir / "pull-bundle-exposure-reviews.json",
                {
                    "generated": "2026-05-20T00:00:00+00:00",
                    "bundles": {
                        "bundle-1": {
                            "reviews": [
                                {
                                    "bundle_id": "bundle-1",
                                    "finding_kind": "generic_token",
                                    "relative_path": "settings.py",
                                    "variable_name": "PASSWORD",
                                    "review_state": "needs_action",
                                    "review_note": "synthetic fixture",
                                }
                            ]
                        }
                    },
                },
            )
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            coordinator = CollectionCoordinator(settings, manifests, snapshots)
            with (
                mock.patch.object(api_module, "manifest_store", manifests),
                mock.patch.object(api_module, "snapshot_store", snapshots),
                mock.patch.object(api_module, "coordinator", coordinator),
            ):
                body = api_module.list_pull_bundles("svc")
                review = api_module.get_pull_bundle_exposure_review("svc", "bundle-1")

            projected = body["bundles"][0]["exposure_review"]
            self.assertEqual(projected["total_findings"], 3)
            self.assertEqual(projected["total_groups"], 2)
            self.assertEqual(projected["review_state_counts"]["unreviewed"], 2)
            self.assertEqual(projected["review_state_counts"]["needs_action"], 1)
            self.assertEqual(projected["finding_kind_counts"], {"generic_token": 3})
            self.assertEqual(projected["path_counts"]["app.py"], 2)
            self.assertEqual(projected["variable_counts"]["API_TOKEN"], 2)
            self.assertEqual(review["review_state_counts"]["needs_action"], 1)
            stored_history = read_json(settings.evidence_dir / "pull-bundle-history.json", {"bundles": []})
            self.assertNotIn("exposure_review", stored_history["bundles"][0])

    def test_pull_bundle_github_backup_dry_run_is_report_only_from_latest_bundle(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "repo"
            source_tree = root / "downloads" / "ws" / "svc" / "bundle-1" / "source_tree"
            project_root.mkdir(parents=True)
            source_tree.mkdir(parents=True)
            settings = Settings(
                manifest_dir=root / "switchboard" / "manifests",
                evidence_dir=root / "docs" / "evidence",
                archive_dir=root / "docs" / "evidence" / "archive",
                private_state_dir=root / "state" / "private",
                downloads_dir=root / "downloads",
            )
            save_json(
                settings.manifest_dir / "services.json",
                [
                    {
                        "service_id": "svc",
                        "workspace_id": "ws",
                        "display_name": "Svc",
                        "locations": [
                            {
                                "location_id": "svc-local",
                                "server_id": "local_mac",
                                "access_mode": "local",
                                "root": str(project_root),
                                "role": "primary",
                                "is_primary": True,
                                "path_aliases": [],
                            }
                        ],
                        "repo_paths": [str(project_root)],
                    }
                ],
            )
            bundle = {
                "bundle_id": "bundle-1",
                "created_at": "2026-05-20T00:00:00+00:00",
                "workspace_id": "ws",
                "service_id": "svc",
                "server_id": "local_mac",
                "bundle_profile": "backup-clean",
                "backup_clean": True,
                "location_root": str(project_root),
                "source_tree_path": str(source_tree),
                "manifest_path": str(source_tree.parent / "bundle-manifest.json"),
                "authority": {"updated_at": "2026-05-20T00:00:00+00:00", "source": "node-local"},
                "authority_fresh": True,
                "file_count": 1,
                "docs_count": 0,
                "logs_count": 0,
                "files": [{"relative_path": "app.py", "kind": "code"}],
                "skipped_entry_count": 1,
                "skipped_entries": [{"path": "/missing", "kind": "doc", "path_type": "file", "reason": "missing"}],
                "exposure_findings": [
                    {
                        "relative_path": "app.py",
                        "finding_kind": "generic_token",
                        "variable_name": "API_TOKEN",
                        "line_number": 1,
                        "redacted": True,
                    }
                ],
                "backup_readiness_status": "review_required",
                "not_backup_ready": True,
            }
            save_json(
                settings.evidence_dir / "pull-bundle-history.json",
                {"generated": "2026-05-20T00:00:00+00:00", "bundles": [bundle]},
            )
            save_json(
                settings.evidence_dir / "pull-bundle-exposure-reviews.json",
                {"generated": "2026-05-20T00:00:00+00:00", "bundles": {}},
            )
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            coordinator = CollectionCoordinator(settings, manifests, snapshots)

            with mock.patch.object(
                coordinator,
                "_readonly_git_summary",
                return_value={
                    "repo_status": "ok",
                    "target_repo": "example/svc",
                    "target_remote": "origin\thttps://github.com/example/svc.git (push)",
                    "target_branch": "main",
                    "repo_head": "abc123",
                    "repo_dirty": True,
                },
            ):
                report = coordinator.github_backup_dry_run_from_pull_bundle("svc", PullBundleBackupDryRunRequest())

            self.assertEqual(report["status"], "blocked")
            self.assertTrue(report["not_push_ready"])
            self.assertFalse(report["push_performed"])
            self.assertFalse(report["commit_performed"])
            self.assertFalse(report["stage_performed"])
            self.assertEqual(report["source_policy"], "latest_backup_clean_pull_bundle_only")
            self.assertEqual(report["source_tree_path"], str(source_tree))
            self.assertEqual(report["would_stage_files"], ["app.py"])
            self.assertEqual(report["unresolved_exposure_count"], 1)
            self.assertEqual(report["review_state_counts"]["unreviewed"], 1)
            self.assertIn("unresolved_exposures", report["blocked_reasons"])
            self.assertIn("skipped_entries_need_review", report["blocked_reasons"])
            self.assertIn("repo_dirty", report["blocked_reasons"])
            history = read_json(settings.manifest_dir.parent / "evidence" / "github-backup-dry-runs.json", {"runs": []})
            self.assertEqual(history["runs"][0]["bundle_id"], "bundle-1")
            bundles = read_json(settings.evidence_dir / "pull-bundle-history.json", {"bundles": []})
            self.assertEqual(len(bundles["bundles"]), 1)
            overlay = read_json(settings.evidence_dir / "pull-bundle-exposure-reviews.json", {})
            self.assertEqual(overlay, {"generated": "2026-05-20T00:00:00+00:00", "bundles": {}})

    def test_pull_bundle_github_backup_dry_run_prefers_origin_over_mirror(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(
                manifest_dir=root / "switchboard" / "manifests",
                evidence_dir=root / "docs" / "evidence",
                archive_dir=root / "docs" / "evidence" / "archive",
                private_state_dir=root / "state" / "private",
                downloads_dir=root / "downloads",
            )
            coordinator = CollectionCoordinator(settings, ManifestStore(settings), SnapshotStore(settings, ManifestStore(settings)))

            def fake_run_local(command: list[str], **_kwargs: object) -> dict[str, object]:
                joined = " ".join(command)
                if "rev-parse --show-toplevel" in joined:
                    return {"returncode": 0, "stdout": str(root), "stderr": ""}
                if "status --short" in joined:
                    return {"returncode": 0, "stdout": "", "stderr": ""}
                if "remote -v" in joined:
                    return {
                        "returncode": 0,
                        "stdout": "\n".join(
                            [
                                "mirror-pratikreddy\thttps://github.com/Pratikreddy/switchboard.git (fetch)",
                                "mirror-pratikreddy\thttps://github.com/Pratikreddy/switchboard.git (push)",
                                "origin\thttps://github.com/pratikreddy9/switchboard.git (fetch)",
                                "origin\thttps://github.com/pratikreddy9/switchboard.git (push)",
                            ]
                        ),
                        "stderr": "",
                    }
                if "rev-parse HEAD" in joined:
                    return {"returncode": 0, "stdout": "abc123\n", "stderr": ""}
                if "branch --show-current" in joined:
                    return {"returncode": 0, "stdout": "main\n", "stderr": ""}
                if "diff --name-only" in joined:
                    return {"returncode": 0, "stdout": "", "stderr": ""}
                return {"returncode": 1, "stdout": "", "stderr": "unexpected command"}

            with mock.patch.object(coordinator, "_run_local", side_effect=fake_run_local):
                summary = coordinator._readonly_git_summary(str(root))

            self.assertEqual(summary["target_remote"], "origin\thttps://github.com/pratikreddy9/switchboard.git (push)")
            self.assertEqual(summary["target_repo"], "pratikreddy9/switchboard")

    def test_pull_bundle_github_backup_dry_run_projects_stale_and_superseded_reports(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "repo"
            source_tree = root / "downloads" / "ws" / "svc" / "bundle-1" / "source_tree"
            project_root.mkdir(parents=True)
            source_tree.mkdir(parents=True)
            settings = Settings(
                manifest_dir=root / "switchboard" / "manifests",
                evidence_dir=root / "docs" / "evidence",
                archive_dir=root / "docs" / "evidence" / "archive",
                private_state_dir=root / "state" / "private",
                downloads_dir=root / "downloads",
            )
            save_json(
                settings.manifest_dir / "services.json",
                [
                    {
                        "service_id": "svc",
                        "workspace_id": "ws",
                        "display_name": "Svc",
                        "locations": [
                            {
                                "location_id": "svc-local",
                                "server_id": "local_mac",
                                "access_mode": "local",
                                "root": str(project_root),
                                "role": "primary",
                                "is_primary": True,
                                "path_aliases": [],
                            }
                        ],
                        "repo_paths": [str(project_root)],
                    }
                ],
            )
            bundle = {
                "bundle_id": "bundle-1",
                "created_at": "2026-05-20T00:00:00+00:00",
                "workspace_id": "ws",
                "service_id": "svc",
                "server_id": "local_mac",
                "bundle_profile": "backup-clean",
                "backup_clean": True,
                "location_root": str(project_root),
                "source_tree_path": str(source_tree),
                "authority": {"updated_at": "2026-05-20T00:00:00+00:00", "source": "node-local"},
                "authority_fresh": False,
                "files": [{"relative_path": "app.py", "kind": "code"}],
                "exposure_review": {
                    "review_state_counts": {
                        "accepted_risk": 0,
                        "false_positive": 0,
                        "needs_action": 0,
                        "unreviewed": 1,
                    }
                },
                "backup_readiness_status": "review_required",
                "not_backup_ready": True,
            }
            save_json(settings.evidence_dir / "pull-bundle-history.json", {"bundles": [bundle]})
            save_json(
                settings.manifest_dir.parent / "evidence" / "github-backup-dry-runs.json",
                {
                    "runs": [
                        {
                            "run_id": "newer",
                            "generated_at": "2026-05-20T00:02:00+00:00",
                            "service_id": "svc",
                            "bundle_id": "bundle-1",
                            "repo_head": "oldhead",
                            "repo_dirty": True,
                            "authority_updated_at": "2026-05-20T00:00:00+00:00",
                            "review_state_counts": {"unreviewed": 1},
                        },
                        {
                            "run_id": "older",
                            "generated_at": "2026-05-20T00:01:00+00:00",
                            "service_id": "svc",
                            "bundle_id": "bundle-1",
                            "repo_head": "oldhead",
                            "repo_dirty": True,
                            "authority_updated_at": "2026-05-20T00:00:00+00:00",
                            "review_state_counts": {"unreviewed": 1},
                        },
                    ]
                },
            )
            coordinator = CollectionCoordinator(settings, ManifestStore(settings), SnapshotStore(settings, ManifestStore(settings)))

            with (
                mock.patch.object(
                    coordinator,
                    "_readonly_git_summary",
                    return_value={"repo_status": "ok", "repo_head": "newhead", "repo_dirty": False},
                ),
                mock.patch.object(coordinator, "_control_center_scope_timestamp", return_value="2026-05-21T00:00:00+00:00"),
                mock.patch.object(coordinator, "_github_backup_manager_health_checked_at", return_value="2026-05-21T00:00:01+00:00"),
            ):
                reports = coordinator.list_github_backup_dry_runs("svc")

            self.assertEqual(len(reports), 2)
            self.assertEqual(reports[0]["run_id"], "newer")
            self.assertEqual(reports[0]["freshness_state"], "stale_repo_head")
            self.assertIn("stale_repo_head", reports[0]["freshness_reasons"])
            self.assertIn("stale_authority", reports[0]["freshness_reasons"])
            self.assertEqual(reports[0]["current_repo_head"], "newhead")
            self.assertEqual(reports[0]["repo_head_at_run"], "oldhead")
            self.assertEqual(reports[1]["freshness_state"], "superseded")
            self.assertEqual(reports[1]["superseded_by"], "newer")

    def test_service_github_backup_dry_runs_route_uses_projected_reports(self) -> None:
        projected = [{"run_id": "run-1", "freshness_state": "stale_repo_head"}]
        with (
            mock.patch.object(api_module.manifest_store, "get_service", return_value=ServiceManifest(service_id="svc", workspace_id="ws", display_name="Svc")),
            mock.patch.object(api_module.coordinator, "list_github_backup_dry_runs", return_value=projected) as list_reports,
        ):
            result = api_module.list_service_github_backup_dry_runs("svc")

        self.assertEqual(result, {"service_id": "svc", "runs": projected})
        list_reports.assert_called_once_with("svc")

    def test_pull_bundle_github_backup_dry_run_artifact_write_does_not_self_invalidate(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "repo"
            source_tree = root / "downloads" / "ws" / "svc" / "bundle-1" / "source_tree"
            project_root.mkdir(parents=True)
            source_tree.mkdir(parents=True)
            settings = Settings(
                manifest_dir=root / "switchboard" / "manifests",
                evidence_dir=root / "docs" / "evidence",
                archive_dir=root / "docs" / "evidence" / "archive",
                private_state_dir=root / "state" / "private",
                downloads_dir=root / "downloads",
            )
            save_json(
                settings.manifest_dir / "services.json",
                [
                    {
                        "service_id": "svc",
                        "workspace_id": "ws",
                        "display_name": "Svc",
                        "locations": [
                            {
                                "location_id": "svc-local",
                                "server_id": "local_mac",
                                "access_mode": "local",
                                "root": str(project_root),
                                "role": "primary",
                                "is_primary": True,
                                "path_aliases": [],
                            }
                        ],
                        "repo_paths": [str(project_root)],
                    }
                ],
            )
            bundle = {
                "bundle_id": "bundle-1",
                "created_at": "2026-05-20T00:00:00+00:00",
                "workspace_id": "ws",
                "service_id": "svc",
                "server_id": "local_mac",
                "bundle_profile": "backup-clean",
                "backup_clean": True,
                "location_root": str(project_root),
                "source_tree_path": str(source_tree),
                "authority": {"updated_at": "2026-05-22T00:00:00+00:00", "source": "node-local"},
                "authority_fresh": True,
                "files": [{"relative_path": "app.py", "kind": "code"}],
                "exposure_findings": [
                    {
                        "relative_path": "app.py",
                        "finding_kind": "generic_token",
                        "variable_name": "API_TOKEN",
                        "line_number": 1,
                        "redacted": True,
                    }
                ],
                "exposure_review": {"review_state_counts": {"unreviewed": 1}},
                "backup_readiness_status": "review_required",
                "not_backup_ready": True,
            }
            save_json(settings.evidence_dir / "pull-bundle-history.json", {"bundles": [bundle]})
            save_json(
                settings.manifest_dir.parent / "evidence" / "github-backup-dry-runs.json",
                {
                    "runs": [
                        {
                            "run_id": "current",
                            "generated_at": "2026-05-22T00:01:00+00:00",
                            "service_id": "svc",
                            "bundle_id": "bundle-1",
                            "repo_head": "samehead",
                            "repo_dirty": False,
                            "repo_head_at_run": "samehead",
                            "repo_dirty_at_run": False,
                            "report_artifact_write": True,
                            "authority_updated_at": "2026-05-22T00:00:00+00:00",
                            "review_state_counts": {"unreviewed": 1},
                        }
                    ]
                },
            )
            coordinator = CollectionCoordinator(settings, ManifestStore(settings), SnapshotStore(settings, ManifestStore(settings)))

            with (
                mock.patch.object(
                    coordinator,
                    "_readonly_git_summary",
                    return_value={"repo_status": "ok", "repo_head": "samehead", "repo_dirty": True},
                ),
                mock.patch.object(coordinator, "_control_center_scope_timestamp", return_value="2026-05-21T00:00:00+00:00"),
                mock.patch.object(coordinator, "_github_backup_manager_health_checked_at", return_value="2026-05-22T00:01:01+00:00"),
            ):
                reports = coordinator.list_github_backup_dry_runs("svc")

            self.assertEqual(reports[0]["freshness_state"], "current")
            self.assertEqual(reports[0]["freshness_reasons"], [])
            self.assertFalse(reports[0]["repo_dirty_at_run"])
            self.assertTrue(reports[0]["report_artifact_write"])
            self.assertTrue(reports[0]["current_repo_dirty"])

    def test_pull_bundle_preflight_uses_check_8020_fix_for_manager_unreachable(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "repo"
            project_root.mkdir(parents=True)
            (project_root / "app.py").write_text("print('ok')\n", encoding="utf-8")
            save_json(
                project_root / "switchboard" / "node.manifest.json",
                {
                    "service_id": "svc",
                    "display_name": "Svc",
                    "project_root": str(project_root),
                    "installed_version": "1.12.7",
                    "updated_at": "2026-05-20T00:00:00+00:00",
                },
            )
            save_json(
                root / "switchboard" / "manager.manifest.json",
                {
                    "managed_roots": [
                        {
                            "root_id": "svc-local",
                            "project_root": str(project_root),
                            "manifest_updated_at": "2026-05-20T00:00:00+00:00",
                            "last_seen_version": "1.12.7",
                        }
                    ]
                },
            )
            settings = Settings(
                manifest_dir=root / "switchboard" / "manifests",
                evidence_dir=root / "docs" / "evidence",
                archive_dir=root / "docs" / "evidence" / "archive",
                private_state_dir=root / "state" / "private",
                downloads_dir=root / "downloads",
            )
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            coordinator = CollectionCoordinator(settings, manifests, snapshots)
            service = ServiceManifest(
                service_id="svc",
                workspace_id="ws",
                display_name="Svc",
                locations=[
                    LocationSpec(
                        location_id="loc",
                        server_id="local_mac",
                        access_mode="local",
                        root=str(project_root),
                        role="primary",
                        is_primary=True,
                        path_aliases=[],
                    )
                ],
                scope_entries=[
                    ScopeEntry(kind="repo", path=str(project_root), path_type="dir", source="user_added", enabled=True),
                ],
            )
            manifests.get_service = lambda _service_id: service  # type: ignore[assignment]
            manifests.resolve_server = lambda *_args, **_kwargs: ResolvedServer(  # type: ignore[assignment]
                server_id="local_mac",
                name="Local",
                connection_type="local",
                host="127.0.0.1",
                username="p",
                port=22,
                tags=[],
                favorite_tier="primary",
                notes="",
                password=None,
            )

            with mock.patch("switchboard.freshness.port_listening", return_value=False):
                result = coordinator.pull_bundle_preflight("svc", PullBundleRequest(location_id="loc"))

            self.assertEqual(result["status"], "partial")
            self.assertTrue(result["authority_stale"])
            self.assertEqual(result["fix"], "Check 8020")
            self.assertIn("Manager node 8020 is not live", result["message"])
            self.assertEqual(result["freshness"]["freshness_state"], "Manager unreachable")
            self.assertEqual(result["freshness"]["refresh_action"], "Check 8020")

    def test_pull_bundle_preflight_blocks_local_authority_older_than_manager_truth(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "repo"
            project_root.mkdir(parents=True)
            (project_root / "app.py").write_text("print('ok')\n", encoding="utf-8")
            save_json(
                project_root / "switchboard" / "node.manifest.json",
                {
                    "service_id": "svc",
                    "display_name": "Svc",
                    "project_root": str(project_root),
                    "installed_version": "1.12.7",
                    "updated_at": "2026-05-20T00:00:00+00:00",
                },
            )
            save_json(
                root / "switchboard" / "manager.manifest.json",
                {
                    "managed_roots": [
                        {
                            "root_id": "svc-local",
                            "project_root": str(project_root),
                            "manifest_updated_at": "2026-05-20T00:00:00+00:00",
                            "last_seen_version": "1.12.7",
                        }
                    ]
                },
            )
            settings = Settings(
                manifest_dir=root / "switchboard" / "manifests",
                evidence_dir=root / "docs" / "evidence",
                archive_dir=root / "docs" / "evidence" / "archive",
                private_state_dir=root / "state" / "private",
                downloads_dir=root / "downloads",
            )
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            snapshots.persist_node_sync(
                "svc",
                "loc",
                {
                    "service_id": "svc",
                    "location_id": "loc",
                    "direction": "from_node",
                    "timestamp": "2026-05-19T00:00:00+00:00",
                    "scope_snapshot_generated_at": "2026-05-19T00:00:00+00:00",
                    "status": "ok",
                },
            )
            coordinator = CollectionCoordinator(settings, manifests, snapshots)
            service = ServiceManifest(
                service_id="svc",
                workspace_id="ws",
                display_name="Svc",
                locations=[
                    LocationSpec(
                        location_id="loc",
                        server_id="local_mac",
                        access_mode="local",
                        root=str(project_root),
                        role="primary",
                        is_primary=True,
                        path_aliases=[],
                    )
                ],
                scope_entries=[
                    ScopeEntry(kind="repo", path=str(project_root), path_type="dir", source="user_added", enabled=True),
                ],
            )
            manifests.get_service = lambda _service_id: service  # type: ignore[assignment]
            manifests.resolve_server = lambda *_args, **_kwargs: ResolvedServer(  # type: ignore[assignment]
                server_id="local_mac",
                name="Local",
                connection_type="local",
                host="127.0.0.1",
                username="p",
                port=22,
                tags=[],
                favorite_tier="primary",
                notes="",
                password=None,
            )

            with mock.patch("switchboard.freshness.port_listening", return_value=True):
                result = coordinator.pull_bundle_preflight("svc", PullBundleRequest(location_id="loc"))

            self.assertEqual(result["status"], "partial")
            self.assertTrue(result["authority_stale"])
            self.assertEqual(result["fix"], "Run Sync From Node.")
            self.assertIn("Pull authority is older than current manager truth", result["message"])
            self.assertEqual(result["freshness"]["freshness_state"], "Stale")
            self.assertEqual(result["freshness"]["stale_reason"], "authority_cache_older_than_truth")

    def test_pull_bundle_preflight_requires_explicit_location_for_multi_location_service(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            one = root / "one"
            two = root / "two"
            one.mkdir()
            two.mkdir()
            service = ServiceManifest(
                service_id="svc",
                workspace_id="ws",
                display_name="Svc",
                locations=[
                    LocationSpec(location_id="one", server_id="local_mac", access_mode="local", root=str(one), role="primary", is_primary=True),
                    LocationSpec(location_id="two", server_id="local_mac", access_mode="local", root=str(two), role="secondary", is_primary=False),
                ],
                scope_entries=[
                    ScopeEntry(kind="repo", path=str(one), path_type="dir", source="user_added", enabled=True),
                    ScopeEntry(kind="repo", path=str(two), path_type="dir", source="user_added", enabled=True),
                ],
            )
            settings = Settings()
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            coordinator = CollectionCoordinator(settings, manifests, snapshots)
            manifests.get_service = lambda _service_id: service  # type: ignore[assignment]
            manifests.resolve_server = lambda *_args, **_kwargs: ResolvedServer(  # type: ignore[assignment]
                server_id="local_mac",
                name="Local",
                connection_type="local",
                host="127.0.0.1",
                username="p",
                port=22,
                tags=[],
                favorite_tier="primary",
                notes="",
                password=None,
            )

            blocked = coordinator.pull_bundle_preflight("svc", PullBundleRequest())
            ready = coordinator.pull_bundle_preflight("svc", PullBundleRequest(location_id="one"))

            self.assertEqual(blocked["status"], "partial")
            self.assertTrue(blocked["location_required"])
            self.assertEqual(ready["status"], "ok")
            self.assertEqual(ready["location_id"], "one")

    def test_github_backup_readiness_and_dry_run_are_workspace_scoped(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "project"
            project_root.mkdir()
            manifest_dir = root / "switchboard" / "manifests"
            evidence_dir = root / "docs" / "evidence"
            archive_dir = evidence_dir / "archive"
            private_state_dir = root / "state" / "private"
            downloads_dir = root / "downloads"
            save_json(
                manifest_dir / "servers.json",
                [
                    {
                        "server_id": "local_mac",
                        "name": "Local Mac",
                        "connection_type": "local",
                        "host": "localhost",
                        "username": "p",
                        "port": 22,
                        "tags": [],
                    }
                ],
            )
            save_json(
                manifest_dir / "workspaces.json",
                [
                    {
                        "workspace_id": "zapp",
                        "name": "ZAPP",
                        "tags": [],
                        "favorite_tier": "primary",
                        "servers": ["local_mac"],
                        "services": ["svc"],
                        "notes": "",
                    }
                ],
            )
            save_json(
                manifest_dir / "services.json",
                [
                    {
                        "service_id": "svc",
                        "workspace_id": "zapp",
                        "display_name": "Svc",
                        "locations": [
                            {
                                "location_id": "svc-local",
                                "server_id": "local_mac",
                                "access_mode": "local",
                                "root": str(project_root),
                                "role": "primary",
                                "is_primary": True,
                                "path_aliases": [],
                            }
                        ],
                        "repo_paths": [str(project_root)],
                        "allowed_git_pull_paths": [str(project_root)],
                        "repo_policies": [
                            {
                                "repo_path": str(project_root),
                                "push_mode": "allowed",
                                "safety_profile": "generic_python",
                                "allowed_branches": [],
                                "allowed_remotes": [],
                            }
                        ],
                    }
                ],
            )
            settings = Settings(
                manifest_dir=manifest_dir,
                evidence_dir=evidence_dir,
                archive_dir=archive_dir,
                private_state_dir=private_state_dir,
                downloads_dir=downloads_dir,
            )
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            coordinator = CollectionCoordinator(settings, manifests, snapshots)
            with mock.patch.object(
                coordinator,
                "_repo_status",
                return_value={
                    "status": "ok",
                    "repo_path": str(project_root),
                    "branch": "main",
                    "dirty": False,
                    "last_commit": "abc123\t2026-04-29T00:00:00+00:00\tmsg",
                    "remotes": ["origin\thttps://github.com/example/project.git (push)"],
                },
            ):
                dry_run = coordinator.github_backup_run(GitHubBackupRequest(workspace_id="zapp", dry_run=True))

            self.assertEqual(dry_run["eligible_count"], 1)
            self.assertEqual(dry_run["action"], "dry_run")
            history = read_json(evidence_dir / "github-backup-history.json", {"runs": []})
            self.assertEqual(history["runs"][0]["repository_count"], 1)

    def test_palimpsest_export_summarizes_sensitive_runtime_state(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_dir = root / "switchboard" / "manifests"
            evidence_dir = root / "docs" / "evidence"
            archive_dir = evidence_dir / "archive"
            private_state_dir = root / "state" / "private"
            downloads_dir = root / "downloads"
            project_root = root / "svc"
            project_root.mkdir()
            save_json(
                manifest_dir / "servers.json",
                [
                    {
                        "server_id": "local_mac",
                        "company_id": "p",
                        "name": "Local Mac",
                        "connection_type": "local",
                        "host": "127.0.0.1",
                        "username": "p",
                        "port": 22,
                        "tags": [],
                    }
                ],
            )
            save_json(
                manifest_dir / "workspaces.json",
                [
                    {
                        "workspace_id": "p",
                        "name": "P",
                        "tags": [],
                        "favorite_tier": "primary",
                        "servers": ["local_mac"],
                        "services": ["svc"],
                        "notes": "",
                    }
                ],
            )
            save_json(
                manifest_dir / "services.json",
                [
                    {
                        "service_id": "svc",
                        "workspace_id": "p",
                        "display_name": "Svc",
                        "locations": [
                            {
                                "location_id": "svc-local",
                                "server_id": "local_mac",
                                "access_mode": "local",
                                "root": str(project_root),
                                "role": "primary",
                                "is_primary": True,
                                "path_aliases": [],
                            }
                        ],
                        "repo_paths": [str(project_root)],
                        "scope_entries": [
                            {
                                "entry_id": "doc-sensitive",
                                "kind": "doc",
                                "path": "/private/source_tree/backend/poller/src/gmail_client.py",
                                "path_type": "file",
                                "source": "user_added",
                                "enabled": True,
                            }
                        ],
                    }
                ],
            )
            save_json(manifest_dir / "projects.json", [])
            save_json(manifest_dir / "project-environments.json", [])
            save_json(manifest_dir / "api-flows.json", [])
            settings = Settings(
                manifest_dir=manifest_dir,
                evidence_dir=evidence_dir,
                archive_dir=archive_dir,
                private_state_dir=private_state_dir,
                downloads_dir=downloads_dir,
            )
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            coordinator = CollectionCoordinator(settings, manifests, snapshots)
            snapshots.persist_task_ledger(
                "svc",
                "svc-local",
                [
                    {
                        "timestamp": "2026-05-14T00:00:00Z",
                        "title": "Safe title",
                        "summary": "raw body from zappinfobot@example.com to pratik.sr@example.com",
                        "notes": ["mail_test_note with Gmail ids"],
                        "tags": ["task"],
                        "agent": "Codex",
                        "tool": "codex",
                    }
                ],
            )
            snapshots.append_pull_bundle(
                {
                    "bundle_id": "bundle-1",
                    "service_id": "svc",
                    "server_id": "local_mac",
                    "location_id": "svc-local",
                    "created_at": "2026-05-14T00:01:00Z",
                    "status": "ok",
                    "files": [
                        {
                            "source_path": "/private/source_tree/backend/poller/src/gmail_client.py",
                            "target_path": "/tmp/source_tree/backend/poller/src/gmail_client.py",
                        }
                    ],
                    "diff_summary": {"added_count": 1},
                }
            )

            payload = coordinator.export_palimpsest_state()
            serialized = json.dumps(payload)

            self.assertIn("scope_summary", serialized)
            self.assertNotIn("zappinfobot@example.com", serialized)
            self.assertNotIn("pratik.sr@example.com", serialized)
            self.assertNotIn("mail_test_note", serialized)
            self.assertNotIn("backend/poller/src/gmail_client.py", serialized)
            self.assertEqual(payload["runtime_state"]["svc"]["task_ledger"]["latest"]["title"], "Safe title")
            self.assertEqual(payload["runtime_state"]["svc"]["pull_bundles"]["latest"]["bundle_id"], "bundle-1")


if __name__ == "__main__":
    unittest.main()
