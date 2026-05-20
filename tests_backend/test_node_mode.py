import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from fastapi.testclient import TestClient

from switchboard.defaults import DEFAULT_NODE_PORT
from switchboard.node import (
    init_manager_node,
    install_node,
    manager_all_root_normalize,
    manager_install_root,
    manager_archive_old_scaffolding,
    manager_safe_action,
    manager_upgrade_root,
    node_paths,
    normalize_manager_root,
    register_manager_root,
    snapshot_node,
    verify_node_update,
)
from switchboard.node_api import create_manager_node_app, create_node_app
from switchboard.node_runtime import node_status


def _write_complete_update(project_root: Path, title: str = "Normalize root") -> None:
    paths = node_paths(project_root)
    paths["tasks_completed"].write_text(
        "# Tasks Completed\n\n"
        f"## 2026-05-05T00:00:00+00:00 | {title}\n"
        "- Tags: task, scope\n"
        "- Summary: Normalized Switchboard through the canonical manager path.\n"
        "- Changed Paths: switchboard/local/tasks-completed.md\n"
        "- Agent: Codex\n"
        "- Tool: codex-cli\n"
        "- Read Back: Restated the request before editing.\n"
        "- Scope Check: Project root remains tracked by manager scope.\n"
        "- Scope Entries:\n"
        f"  - repo | dir | {project_root.resolve()} | true\n",
        encoding="utf-8",
    )


class NodeModeTests(unittest.TestCase):
    def test_install_node_creates_switchboard_pack_only(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "sample-project"
            project_root.mkdir(parents=True)
            readme = project_root / "README.md"
            readme.write_text("existing root readme\n", encoding="utf-8")

            result = install_node(project_root, service_id="sample-service", display_name="Sample Service")
            paths = node_paths(project_root)

            self.assertEqual(readme.read_text(encoding="utf-8"), "existing root readme\n")
            self.assertTrue(paths["node_root"].exists())
            self.assertTrue(paths["core_readme"].exists())
            self.assertTrue(paths["bootstrap_prompt"].exists())
            self.assertTrue(paths["runtime_prompt"].exists())
            self.assertTrue(paths["agent_contract_md"].exists())
            self.assertTrue(paths["agent_contract_json"].exists())
            self.assertTrue(paths["tasks_completed"].exists())
            self.assertTrue(paths["completed_tasks_json"].exists())
            self.assertTrue(paths["start_script"].exists())
            self.assertTrue(paths["run_script"].exists())
            self.assertTrue((project_root / "AGENTS.md").exists())
            self.assertFalse((project_root / "CLAUDE.md").exists())
            self.assertFalse((project_root / "GEMINI.md").exists())
            self.assertFalse((project_root / "QWEN.md").exists())
            self.assertFalse((project_root / "opencode.json").exists())
            self.assertFalse((project_root / ".opencode" / "agents" / "switchboard.md").exists())
            self.assertEqual(result["manifest"]["agent_contract"]["enabled_entrypoints"], ["agents"])
            self.assertEqual(result["manifest"]["service_id"], "sample-service")
            self.assertEqual(result["manifest"]["evidence_paths"]["update_gate"], "switchboard/evidence/update-gate.json")
            self.assertIn("Read back Pratik's request before acting.", result["manifest"]["design_principles"]["global"])
            top_level = sorted(path.name for path in project_root.iterdir())
            self.assertIn("README.md", top_level)
            self.assertIn("switchboard", top_level)
            self.assertIn("AGENTS.md", top_level)

    def test_manager_root_inherits_common_agent_contract(self) -> None:
        with TemporaryDirectory() as tmpdir:
            manager_root = Path(tmpdir) / "manager"
            project_root = Path(tmpdir) / "child-project"
            manager_root.mkdir(parents=True)
            project_root.mkdir(parents=True)
            install_node(manager_root, service_id="manager", display_name="Manager")
            _write_complete_update(manager_root, "Manager contract")
            snapshot_node(manager_root)

            result = manager_install_root(manager_root, project_root, root_id="child")
            paths = node_paths(project_root)

            self.assertEqual(result["installed"]["manifest"]["agent_contract"]["mode"], "manager_inherited")
            self.assertFalse(paths["agent_contract_md"].exists())
            self.assertTrue((project_root / "AGENTS.md").exists())
            self.assertIn(str(manager_root / "switchboard" / "core" / "agent-contract.md"), (project_root / "AGENTS.md").read_text(encoding="utf-8"))

    def test_snapshot_splits_tasks_into_derived_docs_and_json(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "sample-project"
            install_node(project_root, service_id="sample-service", display_name="Sample Service")
            paths = node_paths(project_root)
            paths["tasks_completed"].write_text(
                "# Tasks Completed\n\n"
                "## 2026-04-01T12:00:00+00:00 | Standardized docs\n"
                "- Tags: task, handoff\n"
                "- Summary: Standardized the local docs.\n"
                "- Changed Paths: switchboard/core/README.md, switchboard/local/tasks-completed.md\n"
                "- Version: 1.1\n"
                "- Readme:\n"
                "  ## Overview\n"
                "  Standardized the project docs.\n"
                "- API:\n"
                "  ## Surface\n"
                "  Added /health.\n"
                "- Changelog:\n"
                "  - Standardized the project docs.\n"
                "- Notes:\n"
                "  - Added the first handoff entry.\n\n"
                "## 2026-04-01T13:00:00+00:00 | Updated scope\n"
                "- Tags: task, decision, runbook, scope\n"
                "- Summary: Updated the tracked scope and runbook.\n"
                "- Changed Paths: switchboard/local/tasks-completed.md\n"
                "- Scope Entries:\n"
                "  - doc | file | /tmp/sample-project/README.md | true\n"
                "  - exclude | glob | venv | true\n",
                encoding="utf-8",
            )

            result = snapshot_node(project_root)
            completed = json.loads(paths["completed_tasks_json"].read_text(encoding="utf-8"))
            scope_snapshot = json.loads(paths["scope_snapshot"].read_text(encoding="utf-8"))
            doc_index = json.loads(paths["doc_index_json"].read_text(encoding="utf-8"))

            self.assertEqual(len(completed["tasks"]), 2)
            self.assertIn("Standardized docs", paths["handoff"].read_text(encoding="utf-8"))
            self.assertIn("Updated scope", paths["runbook"].read_text(encoding="utf-8"))
            self.assertIn("Updated scope", paths["approach_history"].read_text(encoding="utf-8"))
            self.assertEqual(result["scope_snapshot"]["scope_entries"][0]["kind"], "doc")
            self.assertEqual(scope_snapshot["scope_entries"][1]["kind"], "exclude")
            self.assertEqual(result["manifest"]["managed_docs"][0]["doc_id"], "readme")
            self.assertTrue(any(entry["doc_id"] == "doc_index_json" for entry in doc_index["docs"]))
            self.assertIn("Switchboard Playbook", paths["playbook"].read_text(encoding="utf-8"))

    def test_verify_update_gate_requires_agent_contract_fields(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "sample-project"
            install_node(project_root, service_id="sample-service", display_name="Sample Service")
            paths = node_paths(project_root)
            paths["tasks_completed"].write_text(
                "# Tasks Completed\n\n"
                "## 2000-01-01T00:00:00+00:00 | Incomplete update\n"
                "- Tags: task\n"
                "- Summary: Missing gate fields.\n"
                "- Changed Paths: switchboard/local/tasks-completed.md\n",
                encoding="utf-8",
            )

            snapshot_node(project_root)
            incomplete = verify_node_update(project_root)

            self.assertEqual(incomplete["status"], "incomplete")
            self.assertTrue((paths["update_gate"]).exists())
            self.assertTrue(
                any(check["check_id"] == "latest_task_required_fields" and check["status"] == "failed" for check in incomplete["checks"])
            )

            paths["tasks_completed"].write_text(
                "# Tasks Completed\n\n"
                "## 2000-01-01T00:00:00+00:00 | Complete update\n"
                "- Tags: task\n"
                "- Summary: Updated Switchboard canonically.\n"
                "- Changed Paths: switchboard/local/tasks-completed.md\n"
                "- Agent: Codex\n"
                "- Tool: codex-cli\n"
                "- Read Back: Restated the request before editing.\n"
                "- Scope Check: Project shape did not change; existing scope remains valid.\n",
                encoding="utf-8",
            )

            snapshot_node(project_root)
            complete = verify_node_update(project_root)

            self.assertEqual(complete["status"], "ok")

    def test_snapshot_only_rewrites_opted_in_root_docs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "sample-project"
            install_node(project_root, service_id="sample-service", display_name="Sample Service")
            paths = node_paths(project_root)
            root_readme = project_root / "README.md"
            root_readme.write_text("manual root readme\n", encoding="utf-8")

            manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            for entry in manifest["managed_docs"]:
                if entry["doc_id"] == "readme":
                    entry["enabled"] = False
            paths["manifest"].write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

            paths["tasks_completed"].write_text(
                "# Tasks Completed\n\n"
                "## 2026-04-01T12:00:00+00:00 | Update readme\n"
                "- Tags: task\n"
                "- Summary: Update readme block.\n"
                "- Changed Paths: switchboard/local/tasks-completed.md\n"
                "- Readme:\n"
                "  Updated readme text.\n",
                encoding="utf-8",
            )

            snapshot_node(project_root)
            self.assertEqual(root_readme.read_text(encoding="utf-8"), "manual root readme\n")

            manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            for entry in manifest["managed_docs"]:
                if entry["doc_id"] == "readme":
                    entry["enabled"] = True
            paths["manifest"].write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

            snapshot_node(project_root)
            self.assertIn("Updated readme text.", root_readme.read_text(encoding="utf-8"))

    def test_node_api_exposes_health_and_manifest(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "sample-project"
            install_node(project_root, service_id="sample-service", display_name="Sample Service")
            client = TestClient(create_node_app(project_root))

            health = client.get("/api/health")
            info = client.get("/api/node")

            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["mode"], "node")
            self.assertEqual(info.status_code, 200)
            self.assertEqual(info.json()["manifest"]["service_id"], "sample-service")
            self.assertIn("runtime", info.json())
            self.assertIn("last_snapshot_at", info.json())
            self.assertEqual(info.json()["runtime"]["monitoring_mode"], "manual")

    def test_manager_node_registers_roots_and_exposes_api(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manager_root = root / "manager"
            project_root = root / "sample-project"
            install_node(project_root, service_id="sample-service", display_name="Sample Service")

            init_result = init_manager_node(manager_root, runtime_port=8711)
            register_result = register_manager_root(manager_root, project_root, snapshot=True)
            client = TestClient(create_manager_node_app(manager_root))

            health = client.get("/api/health")
            roots = client.get("/api/manager/roots")
            root_health = client.get("/api/manager/roots/sample-service/health")
            root_manifest = client.get("/api/manager/roots/sample-service/manifest")

            self.assertEqual(init_result["manifest"]["mode"], "manager")
            self.assertEqual(register_result["record"]["root_id"], "sample-service")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["mode"], "manager")
            self.assertEqual(health.json()["root_count"], 1)
            self.assertEqual(roots.json()["roots"][0]["project_root"], str(project_root.resolve()))
            self.assertEqual(root_health.json()["service_id"], "sample-service")
            self.assertEqual(root_manifest.json()["manifest"]["service_id"], "sample-service")

    def test_manager_node_default_port_is_standard_node_port(self) -> None:
        with TemporaryDirectory() as tmpdir:
            manager_root = Path(tmpdir) / "manager"
            init_result = init_manager_node(manager_root)
            client = TestClient(create_manager_node_app(manager_root))

            self.assertEqual(init_result["manifest"]["runtime_port"], DEFAULT_NODE_PORT)
            self.assertEqual(client.get("/api/health").json()["runtime_port"], DEFAULT_NODE_PORT)

    def test_manager_node_health_prefers_served_port_over_stale_manifest_port(self) -> None:
        with TemporaryDirectory() as tmpdir:
            manager_root = Path(tmpdir) / "manager"
            init_manager_node(manager_root, runtime_port=8010)
            client = TestClient(create_manager_node_app(manager_root, runtime_port=8020))

            health = client.get("/api/health").json()

            self.assertEqual(health["runtime_port"], 8020)
            self.assertEqual(health["manifest_runtime_port"], 8010)

    def test_manager_safe_action_archives_only_old_scaffolding(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manager_root = root / "manager"
            project_root = root / "sample-project"
            install_node(project_root, service_id="sample-service", display_name="Sample Service")
            init_manager_node(manager_root)
            register_manager_root(manager_root, project_root, snapshot=True)
            paths = node_paths(project_root)

            unsafe = manager_safe_action(manager_root, "delete-everything")
            archived = manager_archive_old_scaffolding(manager_root, root_id="sample-service")

            self.assertEqual(unsafe["status"], "permission_limited")
            self.assertFalse(paths["runtime"].exists())
            self.assertFalse(paths["start_script"].exists())
            self.assertFalse(paths["run_script"].exists())
            self.assertFalse(paths["core"].exists())
            self.assertTrue(paths["local"].exists())
            self.assertTrue(paths["evidence"].exists())
            self.assertTrue(paths["manifest"].exists())
            self.assertTrue(Path(archived["archive_root"]).exists())
            self.assertTrue(any(item["status"] == "moved" for item in archived["moved"]))

    def test_manager_install_and_upgrade_are_manager_owned_entrypoints(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manager_root = root / "manager"
            project_root = root / "sample-project"
            init_manager_node(manager_root)

            installed = manager_install_root(manager_root, project_root, service_id="sample-service", display_name="Sample Service")
            upgraded = manager_upgrade_root(manager_root, "sample-service")

            self.assertEqual(installed["status"], "ok")
            self.assertEqual(installed["registered"]["root_id"], "sample-service")
            self.assertEqual(upgraded["status"], "ok")
            self.assertEqual(upgraded["registered"]["root_id"], "sample-service")
            self.assertTrue(node_paths(project_root)["manifest"].exists())

    def test_normalize_root_runs_snapshot_verify_and_archives_after_green(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manager_root = root / "manager"
            project_root = root / "sample-project"
            install_node(project_root, service_id="sample-service", display_name="Sample Service")
            _write_complete_update(project_root)
            init_manager_node(manager_root)

            result = normalize_manager_root(
                manager_root,
                project_root,
                root_id="sample-service",
                service_id="sample-service",
                display_name="Sample Service",
            )
            paths = node_paths(project_root)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["root_id"], "sample-service")
            self.assertEqual(result["verify_update"]["status"], "ok")
            self.assertIsNotNone(result["archive"])
            self.assertFalse(paths["runtime"].exists())
            self.assertFalse(paths["start_script"].exists())
            self.assertFalse(paths["run_script"].exists())
            self.assertTrue(paths["local"].exists())
            self.assertTrue(paths["evidence"].exists())
            self.assertTrue(paths["manifest"].exists())

    def test_normalize_root_does_not_archive_when_verify_fails(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manager_root = root / "manager"
            project_root = root / "sample-project"
            install_node(project_root, service_id="sample-service", display_name="Sample Service")
            node_paths(project_root)["tasks_completed"].write_text(
                "# Tasks Completed\n\n"
                "## 2026-05-05T00:00:00+00:00 | Incomplete update\n"
                "- Tags: task\n"
                "- Summary: Missing canonical gate fields.\n"
                "- Changed Paths: switchboard/local/tasks-completed.md\n",
                encoding="utf-8",
            )
            init_manager_node(manager_root)

            result = normalize_manager_root(
                manager_root,
                project_root,
                root_id="sample-service",
                service_id="sample-service",
                display_name="Sample Service",
            )
            paths = node_paths(project_root)

            self.assertNotEqual(result["status"], "ok")
            self.assertIsNone(result["archive"])
            self.assertTrue(paths["start_script"].exists())
            self.assertTrue(paths["run_script"].exists())

    def test_manager_normalize_all_updates_every_registered_root(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manager_root = root / "manager"
            project_one = root / "project-one"
            project_two = root / "project-two"
            install_node(project_one, service_id="one", display_name="One")
            install_node(project_two, service_id="two", display_name="Two")
            _write_complete_update(project_one, "Normalize one")
            _write_complete_update(project_two, "Normalize two")
            init_manager_node(manager_root)
            register_manager_root(manager_root, project_one, root_id="one", snapshot=False)
            register_manager_root(manager_root, project_two, root_id="two", snapshot=False)

            result = manager_all_root_normalize(manager_root)

            self.assertEqual(result["status"], "ok")
            self.assertEqual({item["root_id"] for item in result["roots"]}, {"one", "two"})
            self.assertTrue(all(item["verify_update"]["status"] == "ok" for item in result["roots"]))

    def test_manager_api_exposes_all_root_safe_actions(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manager_root = root / "manager"
            project_root = root / "sample-project"
            install_node(project_root, service_id="sample-service", display_name="Sample Service")
            init_manager_node(manager_root)
            register_manager_root(manager_root, project_root, snapshot=True)
            client = TestClient(create_manager_node_app(manager_root))

            status = client.post("/api/manager/actions/status")
            upgrade = client.post("/api/manager/roots/sample-service/upgrade")
            denied = client.post("/api/manager/actions/delete")

            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["status"], "ok")
            self.assertEqual(upgrade.status_code, 200)
            self.assertEqual(upgrade.json()["status"], "ok")
            self.assertEqual(denied.status_code, 403)

    def test_node_status_detects_real_port_from_process_args(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "sample-project"
            install_node(project_root, service_id="sample-service", display_name="Sample Service")
            output = (
                "12345 /venv/bin/python -m switchboard.cli node serve "
                f"--project-root {project_root.resolve()} --host 127.0.0.1 --port 8703\n"
            )
            with mock.patch("switchboard.node_runtime.subprocess.run") as run:
                run.return_value.stdout = output
                with mock.patch("switchboard.node_runtime._pid_running", side_effect=lambda pid: bool(pid)):
                    with mock.patch("switchboard.node_runtime._port_listener_pid", return_value=12345):
                        status = node_status(project_root)

            self.assertEqual(status["port"], 8703)
            self.assertEqual(status["pid"], 12345)
            self.assertEqual(status["detected_process_port"], 8703)
            self.assertEqual(status["status"], "running")


if __name__ == "__main__":
    unittest.main()
