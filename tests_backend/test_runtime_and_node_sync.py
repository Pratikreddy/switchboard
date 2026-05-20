import json
import socket
import subprocess
import sys
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from pydantic import ValidationError

from switchboard import __version__
from switchboard.collectors import CollectionCoordinator
from switchboard.config import Settings
from switchboard.manifests import ManifestStore, save_json
from switchboard.models import CollectRequest, NodeActionRequest, NodeSyncRequest, PullBundleRequest, RuntimeActionRequest, RuntimeConfig
from switchboard.node import init_manager_node, install_node, node_paths, register_manager_root
from switchboard.node_runtime import manager_runtime_paths, manager_status, node_status, start_manager_runtime, stop_manager_runtime
from switchboard.storage import SnapshotStore


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for 127.0.0.1:{port}")


def _settings(root: Path) -> Settings:
    manifest_dir = root / "switchboard" / "manifests"
    evidence_dir = root / "docs" / "evidence"
    archive_dir = evidence_dir / "archive"
    private_state_dir = root / "state" / "private"
    downloads_dir = root / "downloads"
    return Settings(
        manifest_dir=manifest_dir,
        evidence_dir=evidence_dir,
        archive_dir=archive_dir,
        private_state_dir=private_state_dir,
        downloads_dir=downloads_dir,
    )


def _write_local_fixture(root: Path, project_root: Path, runtime: dict, scope_entries: list[dict]) -> tuple[ManifestStore, SnapshotStore, CollectionCoordinator]:
    settings = _settings(root)
    save_json(
        settings.manifest_dir / "servers.json",
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
        settings.manifest_dir / "workspaces.json",
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
                        "location_id": "svc-local",
                        "server_id": "local_mac",
                        "access_mode": "local",
                        "root": str(project_root),
                        "role": "primary",
                        "is_primary": True,
                        "path_aliases": [],
                        "runtime": runtime,
                    }
                ],
                "scope_entries": scope_entries,
            }
        ],
    )
    manifests = ManifestStore(settings)
    snapshots = SnapshotStore(settings, manifests)
    coordinator = CollectionCoordinator(settings, manifests, snapshots)
    return manifests, snapshots, coordinator


def _write_remote_fixture(root: Path, *, vpn_required: bool = False) -> tuple[ManifestStore, SnapshotStore, CollectionCoordinator]:
    settings = _settings(root)
    save_json(
        settings.manifest_dir / "servers.json",
        [
            {
                "server_id": "remote_box",
                "name": "Remote Box",
                "connection_type": "ssh",
                "host": "203.0.113.47",
                "username": "pesu",
                "port": 22,
                "vpn_required": vpn_required,
                "tags": [],
            }
        ],
    )
    save_json(
        settings.manifest_dir / "workspaces.json",
        [
            {
                "workspace_id": "pesu",
                "name": "PESU",
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
                "workspace_id": "pesu",
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
                        "runtime": {
                            "expected_ports": [8720],
                            "healthcheck_command": "",
                            "run_command_hint": "",
                            "monitoring_mode": "detect",
                            "notes": "",
                        },
                    }
                ],
                "scope_entries": [
                    {
                        "entry_id": "code-1",
                        "kind": "code",
                        "path": "/srv/svc/app.py",
                        "path_type": "file",
                        "source": "user_added",
                        "enabled": True,
                    }
                ],
            }
        ],
    )
    manifests = ManifestStore(settings)
    snapshots = SnapshotStore(settings, manifests)
    coordinator = CollectionCoordinator(settings, manifests, snapshots)
    return manifests, snapshots, coordinator


@contextmanager
def _closed_ssh_connection():
    yield None


def _write_complete_update(project_root: Path) -> None:
    node_paths(project_root)["tasks_completed"].write_text(
        "# Tasks Completed\n\n"
        "## 2026-05-05T00:00:00+00:00 | Normalize root\n"
        "- Tags: task, scope\n"
        "- Summary: Normalized Switchboard through the manager path.\n"
        "- Changed Paths: switchboard/local/tasks-completed.md\n"
        "- Agent: Codex\n"
        "- Tool: codex-cli\n"
        "- Read Back: Restated the request before editing.\n"
        "- Scope Check: Project root remains tracked by manager scope.\n"
        "- Scope Entries:\n"
        f"  - repo | dir | {project_root.resolve()} | true\n",
        encoding="utf-8",
    )


class RuntimeAndNodeSyncTests(unittest.TestCase):
    def test_runtime_config_dedupes_ports_and_rejects_invalid_values(self) -> None:
        runtime = RuntimeConfig(expected_ports=[8000, 8000, 8500], monitoring_mode="detect")
        self.assertEqual(runtime.expected_ports, [8000, 8500])
        with self.assertRaises(ValidationError):
            RuntimeConfig(expected_ports=[0])

    def test_vpn_required_ssh_failures_are_classified_as_vpn_blocked(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, snapshots, coordinator = _write_remote_fixture(root, vpn_required=True)
            snapshots.persist_node_sync(
                "svc",
                "svc-remote",
                {
                    "service_id": "svc",
                    "location_id": "svc-remote",
                    "direction": "from_node",
                    "timestamp": "2099-01-01T00:00:00+00:00",
                    "status": "ok",
                },
            )

            with mock.patch.object(coordinator, "_open_ssh", side_effect=lambda _server: _closed_ssh_connection()):
                sync_from = coordinator.sync_from_node("svc", NodeSyncRequest(location_id="svc-remote"))
                sync_to = coordinator.sync_to_node("svc", NodeSyncRequest(location_id="svc-remote"))
                pull_bundle = coordinator.pull_bundle(
                    "svc",
                    PullBundleRequest(location_id="svc-remote", extra_includes=[], extra_excludes=[]),
                )
                runtime = coordinator.runtime_check("svc", RuntimeActionRequest(location_id="svc-remote"))
                inspect = coordinator.node_inspect("svc", NodeActionRequest(location_id="svc-remote"))

            self.assertEqual(sync_from["status"], "vpn_or_network_blocked")
            self.assertEqual(sync_to["status"], "vpn_or_network_blocked")
            self.assertEqual(runtime["status"], "vpn_or_network_blocked")
            self.assertEqual(inspect["status"], "vpn_or_network_blocked")
            self.assertEqual(pull_bundle["status"], "vpn_or_network_blocked")
            self.assertIn("VPN is off or network blocked", sync_from["message"])
            self.assertIn("VPN is off or network blocked", runtime["notes"])
            self.assertEqual(inspect["node"]["connection_status"], "vpn_or_network_blocked")
            self.assertEqual(inspect["node"]["freshness_state"], "VPN/network blocked")

    def test_non_vpn_ssh_failures_remain_unreachable(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, _, coordinator = _write_remote_fixture(root, vpn_required=False)

            with mock.patch.object(coordinator, "_open_ssh", side_effect=lambda _server: _closed_ssh_connection()):
                sync_from = coordinator.sync_from_node("svc", NodeSyncRequest(location_id="svc-remote"))
                runtime = coordinator.runtime_check("svc", RuntimeActionRequest(location_id="svc-remote"))

            self.assertEqual(sync_from["status"], "unreachable")
            self.assertEqual(runtime["status"], "unreachable")
            self.assertEqual(sync_from["message"], "SSH connection failed.")

    def test_pull_bundle_preflight_blocks_stale_remote_authority(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, snapshots, coordinator = _write_remote_fixture(root, vpn_required=True)
            snapshots.persist_node_sync(
                "svc",
                "svc-remote",
                {
                    "service_id": "svc",
                    "location_id": "svc-remote",
                    "direction": "from_node",
                    "timestamp": "2026-04-25T01:39:59+00:00",
                    "status": "ok",
                },
            )
            snapshots.persist_runtime_check(
                "svc",
                "svc-remote",
                {
                    "service_id": "svc",
                    "location_id": "svc-remote",
                    "checked_at": "2026-05-13T11:10:23+00:00",
                    "status": "ok",
                },
            )

            result = coordinator.pull_bundle_preflight(
                "svc",
                PullBundleRequest(location_id="svc-remote", extra_includes=[], extra_excludes=[]),
            )

            self.assertEqual(result["status"], "partial")
            self.assertTrue(result["authority_stale"])
            self.assertEqual(result["node_local_scope_timestamp"], "2026-04-25T01:39:59+00:00")
            self.assertTrue(result["control_center_scope_timestamp"])
            self.assertIn("Node-local pull authority is older", result["message"])
            self.assertIn("Run Sync From Node with VPN on", result["message"])
            self.assertNotIn("VPN is off or network blocked", result["message"])

    def test_pull_bundle_preflight_blocks_missing_remote_sync_authority(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, _, coordinator = _write_remote_fixture(root, vpn_required=False)

            result = coordinator.pull_bundle_preflight(
                "svc",
                PullBundleRequest(location_id="svc-remote", extra_includes=[], extra_excludes=[]),
            )

            self.assertEqual(result["status"], "partial")
            self.assertTrue(result["authority_stale"])
            self.assertTrue(result["missing_remote_sync"])
            self.assertIn("Remote bundles require node-local authority", result["message"])

    def test_sync_from_node_normalizes_legacy_scope_kinds(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, _, coordinator = _write_remote_fixture(root)

            normalized = coordinator._normalize_imported_scope_entries(
                [
                    {"kind": "source", "path": "/srv/svc/app.py", "path_type": "file", "source": "node_manifest"},
                    {"kind": "ui", "path": "/srv/svc/ui.py", "path_type": "file", "source": "node_manifest"},
                    {"kind": "asset", "path": "/srv/svc/static", "path_type": "dir", "source": "node_manifest"},
                    {"kind": "config", "path": "/srv/svc/requirements.txt", "path_type": "file", "source": "node_manifest"},
                    {"kind": "meta", "path": "/srv/svc/switchboard/node.manifest.json", "path_type": "file", "source": "manual_codex_handoff"},
                    {"kind": "exclude", "path": "/srv/svc/**/*.log", "path_type": "pattern", "source": "node_manifest"},
                ]
            )

            self.assertEqual([entry["kind"] for entry in normalized], ["code", "code", "code", "code", "doc", "exclude"])
            self.assertEqual(normalized[4]["source"], "tasks_completed")
            self.assertEqual(normalized[-1]["path_type"], "glob")

    def test_sync_from_node_normalizes_legacy_managed_doc_ids(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, _, coordinator = _write_remote_fixture(root)

            normalized = coordinator._normalize_imported_managed_docs(
                [
                    {"doc_id": "readme", "path": "README.md", "enabled": True},
                    {"doc_id": "streamlit_changelog", "path": "streamlit/docs/CHANGELOG.md", "enabled": False},
                    {"doc_id": "unknown_doc", "path": "docs/UNKNOWN.md", "enabled": True},
                ]
            )

            self.assertEqual([entry["doc_id"] for entry in normalized], ["readme", "changelog"])

    def test_pull_bundle_preflight_uses_per_location_import_timestamp_after_node_sync(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, snapshots, coordinator = _write_remote_fixture(root, vpn_required=True)
            snapshots.persist_node_sync(
                "svc",
                "svc-remote",
                {
                    "service_id": "svc",
                    "location_id": "svc-remote",
                    "direction": "from_node",
                    "timestamp": "2026-05-14T09:00:00+00:00",
                    "scope_snapshot_generated_at": "2026-05-12T13:00:00+00:00",
                    "status": "ok",
                },
            )
            snapshots.persist_runtime_check(
                "other",
                "other-remote",
                {
                    "service_id": "other",
                    "location_id": "other-remote",
                    "checked_at": "2026-05-14T09:05:00+00:00",
                    "status": "ok",
                },
            )

            result = coordinator.pull_bundle_preflight(
                "svc",
                PullBundleRequest(location_id="svc-remote", extra_includes=[], extra_excludes=[]),
            )

            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["authority_stale"])
            self.assertEqual(result["node_local_scope_timestamp"], "2026-05-14T09:00:00+00:00")
            self.assertEqual(result["node_scope_generated_at"], "2026-05-12T13:00:00+00:00")
            self.assertEqual(result["control_center_scope_timestamp"], "2026-05-14T09:00:00+00:00")

    def test_runtime_check_local_uses_runtime_config_and_preserves_manual_hint(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "project"
            project_root.mkdir(parents=True)
            install_node(project_root, service_id="svc", display_name="Svc")

            port = _free_port()
            server = subprocess.Popen(
                [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                cwd=project_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                _wait_for_port(port)
                manifests, snapshots, coordinator = _write_local_fixture(
                    root,
                    project_root,
                    runtime={
                        "expected_ports": [port],
                        "healthcheck_command": f"{sys.executable} -c \"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:{port}').status)\"",
                        "run_command_hint": "python -m http.server",
                        "monitoring_mode": "detect",
                        "notes": "Local runtime check fixture",
                    },
                    scope_entries=[
                        {
                            "entry_id": "repo-1",
                            "kind": "repo",
                            "path": str(project_root),
                            "path_type": "dir",
                            "source": "user_added",
                            "enabled": True,
                        },
                        {
                            "entry_id": "doc-1",
                            "kind": "doc",
                            "path": str(project_root / "switchboard" / "node.manifest.json"),
                            "path_type": "file",
                            "source": "user_added",
                            "enabled": True,
                        },
                    ],
                )
                self.assertIsNotNone(manifests.get_service("svc"))
                with mock.patch.object(coordinator, "_lookup_process_command", return_value=""):
                    result = coordinator.runtime_check("svc", RuntimeActionRequest(location_id="svc-local"))

                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["configured_ports"], [port])
                self.assertIn(port, [entry["port"] for entry in result["detected_ports"]])
                self.assertEqual(result["healthcheck_status"], "ok")
                self.assertEqual(result["detected_process_command"], "")
                self.assertEqual(result["run_command_hint"], "python -m http.server")
                self.assertTrue(result["node_present"])
                runtime_state = snapshots.get_service_runtime_state("svc")
                self.assertEqual(runtime_state["runtime_checks"][0]["location_id"], "svc-local")
            finally:
                server.terminate()
                server.wait(timeout=5)

    def test_manager_runtime_start_status_and_stop_use_manager_runtime_files(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manager_root = root / "manager"
            port = _free_port()
            init_manager_node(manager_root, runtime_port=port)
            runtime = manager_runtime_paths(manager_root)

            started = start_manager_runtime(manager_root, port=port)
            try:
                _wait_for_port(port)
                status = manager_status(manager_root, port=port)

                self.assertEqual(started["status"], "running")
                self.assertEqual(status["status"], "running")
                self.assertEqual(Path(status["pid_file"]), runtime["pid"])
                self.assertEqual(Path(status["log_file"]), runtime["log"])
            finally:
                stopped = stop_manager_runtime(manager_root, port=port)

            self.assertIn(started["pid"], stopped["stopped_pids"])

    def test_node_status_marks_manager_owned_port_separately(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            install_node(project_root, service_id="svc", display_name="Svc")

            with (
                mock.patch("switchboard.node_runtime._port_listener_pid", return_value=12345),
                mock.patch("switchboard.node_runtime._process_command", return_value="python -m switchboard.cli node manager-serve --port 8010"),
            ):
                status = node_status(project_root, port=8010)

            self.assertEqual(status["status"], "stopped_manager_owned")

    def test_local_node_actions_use_manager_not_per_project_runtime(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "project"
            install_node(project_root, service_id="svc", display_name="Svc")
            _write_complete_update(project_root)
            init_manager_node(root, runtime_port=8010)
            register_manager_root(root, project_root, root_id="svc", snapshot=False)
            _, snapshots, coordinator = _write_local_fixture(
                root,
                project_root,
                runtime={"expected_ports": [8010], "monitoring_mode": "manual"},
                scope_entries=[],
            )
            request = NodeActionRequest(location_id="svc-local")

            deploy = coordinator.node_deploy("svc", request)
            upgrade = coordinator.node_upgrade("svc", request)

            with mock.patch("switchboard.collectors.manager_status", return_value={"status": "running", "pid": 123, "runtime_dir": "", "log_file": ""}):
                restart = coordinator.node_restart("svc", request)

            self.assertEqual(deploy["status"], "ok")
            self.assertEqual(upgrade["status"], "ok")
            self.assertEqual(restart["status"], "ok")
            self.assertTrue(deploy["node"]["manager_managed"])
            self.assertEqual(deploy["node"]["manager_version"], __version__)
            self.assertEqual(deploy["node"]["runtime_status"], "missing")
            self.assertEqual(restart["node"]["runtime_status"], "manager_running")
            self.assertEqual(snapshots.get_service_node_viewer("svc")[0]["runtime_status"], "manager_running")

    def test_runtime_check_remote_mocked_ssh_uses_manual_hint_when_detection_missing(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = _settings(root)
            save_json(
                settings.manifest_dir / "servers.json",
                [
                    {
                        "server_id": "ssh_box",
                        "name": "SSH Box",
                        "connection_type": "ssh",
                        "host": "10.0.0.5",
                        "username": "tester",
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
                        "servers": ["ssh_box"],
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
                        "locations": [
                            {
                                "location_id": "svc-ssh",
                                "server_id": "ssh_box",
                                "access_mode": "ssh",
                                "root": "/srv/app",
                                "role": "primary",
                                "is_primary": True,
                                "path_aliases": [],
                                "runtime": {
                                    "expected_ports": [9001],
                                    "healthcheck_command": "curl -fsS http://127.0.0.1:9001/health",
                                    "run_command_hint": "uvicorn app:app --port 9001",
                                    "monitoring_mode": "detect",
                                    "notes": "SSH runtime fixture",
                                },
                            }
                        ],
                        "scope_entries": [],
                    }
                ],
            )
            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            coordinator = CollectionCoordinator(settings, manifests, snapshots)

            @contextmanager
            def fake_open_ssh(_server):
                yield (object(), object())

            with (
                mock.patch.object(coordinator, "_open_ssh", side_effect=lambda server: fake_open_ssh(server)),
                mock.patch.object(
                    coordinator,
                    "_collect_remote_listener_details",
                    return_value=[{"port": 9001, "protocol": "tcp", "process": "", "pid": None, "state": "LISTEN"}],
                ),
                mock.patch.object(coordinator, "_remote_exists", return_value=True),
                mock.patch.object(coordinator, "_run_healthcheck_remote", return_value={"status": "ok", "output": "healthy"}),
                mock.patch.object(coordinator, "_lookup_process_command", return_value=""),
            ):
                result = coordinator.runtime_check("svc", RuntimeActionRequest(location_id="svc-ssh"))

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["detected_ports"][0]["port"], 9001)
            self.assertEqual(result["detected_process_command"], "")
            self.assertEqual(result["run_command_hint"], "uvicorn app:app --port 9001")
            self.assertTrue(result["node_present"])

    def test_sync_to_node_and_sync_from_node_round_trip_runtime_and_scope(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "project"
            install_node(project_root, service_id="svc", display_name="Svc")
            paths = node_paths(project_root)

            manifests, snapshots, coordinator = _write_local_fixture(
                root,
                project_root,
                runtime={
                    "expected_ports": [8000],
                    "healthcheck_command": "curl -fsS http://127.0.0.1:8000/health",
                    "run_command_hint": "uvicorn main:app --port 8000",
                    "monitoring_mode": "manual",
                    "notes": "Control center runtime",
                },
                scope_entries=[
                    {
                        "entry_id": "repo-1",
                        "kind": "repo",
                        "path": str(project_root),
                        "path_type": "dir",
                        "source": "user_added",
                        "enabled": True,
                    },
                    {
                        "entry_id": "doc-1",
                        "kind": "doc",
                        "path": str(paths["manifest"]),
                        "path_type": "file",
                        "source": "user_added",
                        "enabled": True,
                    },
                    {
                        "entry_id": "exclude-1",
                        "kind": "exclude",
                        "path": "venv",
                        "path_type": "glob",
                        "source": "user_added",
                        "enabled": True,
                    },
                ],
            )

            pushed = coordinator.sync_to_node("svc", NodeSyncRequest(location_id="svc-local"))
            self.assertEqual(pushed["status"], "ok")

            node_manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            scope_snapshot = json.loads(paths["scope_snapshot"].read_text(encoding="utf-8"))
            self.assertEqual(node_manifest["runtime"]["expected_ports"], [8000])
            self.assertEqual(node_manifest["runtime"]["run_command_hint"], "uvicorn main:app --port 8000")
            self.assertEqual(scope_snapshot["scope_entries"][0]["kind"], "repo")
            self.assertTrue(any(entry["doc_id"] == "readme" for entry in node_manifest["managed_docs"]))

            node_manifest["runtime"] = {
                "expected_ports": [8100],
                "healthcheck_command": "curl -fsS http://127.0.0.1:8100/health",
                "run_command_hint": "python node_runner.py",
                "monitoring_mode": "node_managed",
                "notes": "Node override",
            }
            paths["manifest"].write_text(json.dumps(node_manifest, indent=2) + "\n", encoding="utf-8")
            paths["scope_snapshot"].write_text(
                json.dumps(
                    {
                        "generated": "2026-04-01T00:00:00+00:00",
                        "service_id": "svc",
                        "project_root": str(project_root),
                        "scope_entries": [
                            {
                                "kind": "doc",
                                "path_type": "file",
                                "path": str(paths["manifest"]),
                                "enabled": True,
                                "source": "tasks_completed",
                            },
                            {
                                "kind": "exclude",
                                "path_type": "glob",
                                "path": "venv",
                                "enabled": True,
                                "source": "tasks_completed",
                            },
                            {
                                "kind": "doc",
                                "path_type": "file",
                                "path": str(project_root / "legacy-handoff.md"),
                                "enabled": True,
                                "source": "manual_codex_handoff",
                            },
                            {
                                "kind": "code",
                                "path_type": "file",
                                "path": str(project_root / "app.py"),
                                "enabled": True,
                                "source": "tasks_completed",
                            },
                        ],
                        "scope_updates": [],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            pulled = coordinator.sync_from_node("svc", NodeSyncRequest(location_id="svc-local"))
            self.assertEqual(pulled["status"], "ok")
            self.assertEqual(pulled["service"]["locations"][0]["runtime"]["expected_ports"], [8100])
            self.assertEqual(pulled["service"]["locations"][0]["runtime"]["monitoring_mode"], "node_managed")
            self.assertTrue(any(entry["doc_id"] == "readme" for entry in pulled["service"]["managed_docs"]))

            stored_service = manifests.get_service("svc")
            self.assertIn(str(paths["manifest"]), stored_service.docs_paths)
            self.assertIn(str(project_root / "README.md"), stored_service.docs_paths)
            self.assertIn(str(project_root / "API.md"), stored_service.docs_paths)
            self.assertIn(str(project_root / "CHANGELOG.md"), stored_service.docs_paths)
            self.assertTrue(
                any(
                    entry.path == str(project_root / "legacy-handoff.md") and entry.source == "tasks_completed"
                    for entry in stored_service.scope_entries
                )
            )
            self.assertTrue(
                any(
                    entry.path == str(project_root / "app.py") and entry.kind == "code"
                    for entry in stored_service.scope_entries
                )
            )
            self.assertEqual(stored_service.exclude_globs, ["venv"])
            self.assertEqual(stored_service.allowed_git_pull_paths, [])
            sync_state = snapshots.get_service_runtime_state("svc")["node_sync"]
            self.assertEqual(sync_state[0]["direction"], "from_node")
            self.assertTrue(sync_state[0]["timestamp"])
            self.assertIn("doc_index", sync_state[0])

    def test_sync_from_node_replaces_stale_control_center_scope_with_node_scope(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "project"
            project_root.mkdir(parents=True)
            (project_root / "app.py").write_text("print('ok')\n", encoding="utf-8")
            install_node(project_root, service_id="svc", display_name="Svc")
            paths = node_paths(project_root)
            paths["scope_snapshot"].write_text(
                json.dumps(
                    {
                        "generated": "2026-05-10T00:00:00+00:00",
                        "service_id": "svc",
                        "project_root": str(project_root),
                        "scope_entries": [
                            {
                                "kind": "repo",
                                "path_type": "file",
                                "path": str(project_root / "app.py"),
                                "enabled": True,
                                "source": "node_manifest",
                            },
                            {
                                "kind": "exclude",
                                "path_type": "glob",
                                "path": "runtime",
                                "enabled": True,
                                "source": "node_manifest",
                            },
                        ],
                        "scope_updates": [],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            manifests, _, coordinator = _write_local_fixture(
                root,
                project_root,
                runtime={},
                scope_entries=[
                    {
                        "entry_id": "stale-runtime",
                        "kind": "doc",
                        "path": str(project_root / "runtime"),
                        "path_type": "dir",
                        "source": "user_added",
                        "enabled": True,
                    },
                    {
                        "entry_id": "stale-logs",
                        "kind": "log",
                        "path": str(project_root / "logs"),
                        "path_type": "dir",
                        "source": "user_added",
                        "enabled": True,
                    },
                ],
            )

            pulled = coordinator.sync_from_node("svc", NodeSyncRequest(location_id="svc-local"))

            self.assertEqual(pulled["status"], "ok")
            stored_service = manifests.get_service("svc")
            stored_paths = {entry.path for entry in stored_service.scope_entries}
            self.assertIn(str(project_root / "app.py"), stored_paths)
            self.assertNotIn(str(project_root / "runtime"), stored_paths)
            self.assertNotIn(str(project_root / "logs"), stored_paths)

    def test_collect_with_service_filter_only_resolves_relevant_servers(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "project"
            project_root.mkdir(parents=True)

            settings = _settings(root)
            save_json(
                settings.manifest_dir / "servers.json",
                [
                    {
                        "server_id": "local_mac",
                        "name": "Local Mac",
                        "connection_type": "local",
                        "host": "localhost",
                        "username": "p",
                        "port": 22,
                        "tags": [],
                    },
                    {
                        "server_id": "ssh_box",
                        "name": "SSH Box",
                        "connection_type": "ssh",
                        "host": "10.0.0.5",
                        "username": "tester",
                        "port": 22,
                        "tags": [],
                    },
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
                        "servers": ["local_mac", "ssh_box"],
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
                        "scope_entries": [],
                    }
                ],
            )

            manifests = ManifestStore(settings)
            snapshots = SnapshotStore(settings, manifests)
            coordinator = CollectionCoordinator(settings, manifests, snapshots)
            result = coordinator.collect_workspace("zapp", CollectRequest(service_ids=["svc"]))

            self.assertEqual([entry["server_id"] for entry in result["servers"]], ["local_mac"])

    def test_collect_bulk_syncs_node_managed_local_service_before_inventory(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "project"
            project_root.mkdir(parents=True)
            app_file = project_root / "app.py"
            app_file.write_text("print('ok')\n", encoding="utf-8")
            install_node(project_root, service_id="svc", display_name="Svc")
            save_json(
                node_paths(project_root)["scope_snapshot"],
                {
                    "generated": "2026-05-12T00:00:00+00:00",
                    "scope_entries": [
                        {
                            "entry_id": "code-app",
                            "kind": "code",
                            "path": str(app_file),
                            "path_type": "file",
                            "source": "node_manifest",
                            "enabled": True,
                        }
                    ],
                },
            )
            _, _, coordinator = _write_local_fixture(root, project_root, {"expected_ports": []}, [])

            result = coordinator.collect_workspace("zapp", CollectRequest())
            stored = coordinator.manifests.get_service("svc")

            self.assertEqual(result["node_sync_results"][0]["status"], "ok")
            self.assertEqual(result["summary"]["node_sync_count"], 1)
            self.assertIn(str(app_file), {entry.path for entry in stored.scope_entries})

    def test_collect_skips_local_bundle_only_servers(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "project"
            project_root.mkdir(parents=True)
            settings = _settings(root)
            save_json(
                settings.manifest_dir / "servers.json",
                [
                    {
                        "server_id": "zapp_prod",
                        "name": "ZAPP Prod",
                        "connection_type": "ssh",
                        "deployment_mode": "local_bundle_only",
                        "host": "203.0.113.99",
                        "username": "deploy",
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
                        "servers": ["zapp_prod"],
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
                                "location_id": "svc-prod",
                                "server_id": "zapp_prod",
                                "access_mode": "ssh",
                                "root": "/srv/svc",
                                "role": "primary",
                                "is_primary": True,
                                "path_aliases": [],
                            }
                        ],
                        "scope_entries": [],
                    }
                ],
            )
            manifests = ManifestStore(settings)
            coordinator = CollectionCoordinator(settings, manifests, SnapshotStore(settings, manifests))

            with (
                mock.patch.object(coordinator, "sync_from_node", side_effect=AssertionError("local_bundle_only should not sync")),
                mock.patch.object(
                    coordinator,
                    "_collect_server_summary",
                    return_value={
                        "server_id": "zapp_prod",
                        "name": "ZAPP Prod",
                        "status": "unverified",
                        "connection_type": "ssh",
                        "host": "203.0.113.99",
                        "username": "deploy",
                        "hostname": "203.0.113.99",
                        "ports": [],
                        "firewall": "unverified",
                        "services": [],
                        "docker": [],
                    },
                ),
                mock.patch.object(
                    coordinator,
                    "_collect_service",
                    return_value={
                        "service": {
                            "service_id": "svc",
                            "workspace_id": "zapp",
                            "display_name": "Svc",
                            "status": "unverified",
                            "location_count": 1,
                            "doc_count": 0,
                            "log_count": 0,
                            "secret_path_count": 0,
                            "path_aliases": [],
                            "notes": "",
                        },
                        "repos": [],
                        "docs": [],
                        "logs": [],
                        "secrets": [],
                    },
                ),
            ):
                result = coordinator.collect_workspace("zapp", CollectRequest())

            self.assertTrue(result["node_sync_results"][0]["skipped"])
            self.assertEqual(result["node_sync_results"][0]["server_id"], "zapp_prod")


if __name__ == "__main__":
    unittest.main()
