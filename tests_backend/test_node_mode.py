import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from fastapi.testclient import TestClient

from switchboard.defaults import DEFAULT_NODE_PORT
from switchboard.bricks import (
    build_brick_registry,
    build_keyword_registry,
    export_simple_keyword_report,
    export_small_model_packet,
    normalize_keyword_entries,
)
from switchboard.bricks import registry as brick_registry_module
from switchboard.hooks import (
    build_context_packet,
    build_hooks_registry,
    build_memory_query,
    build_user_prompt_response,
    capture_user_prompt,
    discover_existing_hooks,
    import_codex_session_prompts,
    iter_codex_session_user_prompts,
    read_timeline_summary,
)
from switchboard.node import (
    init_manager_node,
    install_node,
    manager_all_root_normalize,
    manager_install_root,
    manager_archive_old_scaffolding,
    manager_safe_action,
    manager_upgrade_root,
    node_paths,
    parse_tasks_completed,
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
            self.assertEqual(result["manifest"]["evidence_paths"]["brick_registry"], "switchboard/evidence/brick-registry.json")
            self.assertEqual(result["manifest"]["evidence_paths"]["keyword_registry"], "switchboard/evidence/keyword-registry.json")
            self.assertEqual(result["manifest"]["evidence_paths"]["hooks_registry"], "switchboard/evidence/hooks-registry.json")
            self.assertIn("Read back Pratik's request before acting.", result["manifest"]["design_principles"]["global"])
            self.assertIn("Suite Brick Rules", paths["agent_contract_md"].read_text(encoding="utf-8"))
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
                "- Brick Entries:\n"
                "  - sample-brick | docs | hybrid | done | current task | no next action\n\n"
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
            brick_registry = json.loads(paths["brick_registry"].read_text(encoding="utf-8"))
            keyword_registry = json.loads(paths["keyword_registry"].read_text(encoding="utf-8"))
            hooks_registry = json.loads(paths["hooks_registry"].read_text(encoding="utf-8"))

            self.assertEqual(len(completed["tasks"]), 2)
            self.assertEqual(completed["tasks"][0]["brick_entries"][0]["brick_id"], "sample-brick")
            self.assertEqual(result["brick_registry"]["schema_version"], "switchboard-brick-registry-v0")
            self.assertEqual(brick_registry["ui_surface"], "none")
            self.assertEqual(brick_registry["bricks"][0]["brick_id"], "sample-brick")
            self.assertEqual(brick_registry["bricks"][0]["serial_number"], "SAMPLE_SERVICE-BRICK-0001")
            self.assertEqual(brick_registry["bricks"][0]["commit"], "")
            self.assertEqual(brick_registry["bricks"][0]["computed_status"], "pending_commit")
            self.assertEqual(brick_registry["summary"]["brick_count"], 3)
            self.assertEqual(brick_registry["summary"]["explicit_count"], 1)
            self.assertEqual(brick_registry["summary"]["task_derived_count"], 2)
            self.assertEqual(brick_registry["bricks"][0]["entry_type"], "explicit")
            self.assertEqual(brick_registry["bricks"][1]["entry_type"], "task_derived")
            self.assertEqual(brick_registry["bricks"][1]["brick_id"], "sample-service-task-202604011200-standardized-docs")
            self.assertEqual(result["keyword_registry"]["schema_version"], "switchboard-keyword-registry-v0")
            self.assertEqual(keyword_registry["summary"]["keyword_count"], 0)
            self.assertEqual(result["hooks_registry"]["schema_version"], "switchboard-hooks-registry-v0")
            self.assertEqual(hooks_registry["ui_surface"], "none")
            self.assertEqual(hooks_registry["timeline"]["raw_prompt_text"], "local_private_only")
            self.assertIn("Standardized docs", paths["handoff"].read_text(encoding="utf-8"))
            self.assertIn("Updated scope", paths["runbook"].read_text(encoding="utf-8"))
            self.assertIn("Updated scope", paths["approach_history"].read_text(encoding="utf-8"))
            self.assertEqual(result["scope_snapshot"]["scope_entries"][0]["kind"], "doc")
            self.assertEqual(scope_snapshot["scope_entries"][1]["kind"], "exclude")
            self.assertEqual(result["manifest"]["managed_docs"][0]["doc_id"], "readme")
            self.assertTrue(any(entry["doc_id"] == "doc_index_json" for entry in doc_index["docs"]))
            self.assertIn("Switchboard Playbook", paths["playbook"].read_text(encoding="utf-8"))

    def test_parse_tasks_completed_redacts_private_brick_entries(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "sample-project"
            install_node(project_root, service_id="sample-service", display_name="Sample Service")
            paths = node_paths(project_root)
            paths["tasks_completed"].write_text(
                "# Tasks Completed\n\n"
                "## 2026-04-01T12:00:00+00:00 | Private brick line\n"
                "- Tags: task\n"
                "- Summary: Safe summary only.\n"
                "- Changed Paths: switchboard/local/tasks-completed.md\n"
                "- Agent: Codex\n"
                "- Tool: codex-cli\n"
                "- Read Back: Restated the request.\n"
                "- Scope Check: Scope unchanged.\n"
                "- Brick Entries:\n"
                "  - SECRET_FINANCE_ROW | docs | programmatic | done | current task | email@example.com token raw private payload\n",
                encoding="utf-8",
            )

            parsed = parse_tasks_completed(paths["tasks_completed"])
            serialized = json.dumps(parsed)

            self.assertNotIn("SECRET_FINANCE_ROW", serialized)
            self.assertNotIn("email@example.com", serialized)
            self.assertNotIn("raw private payload", serialized)
            self.assertEqual(parsed[0]["brick_entries"][0]["brick_id"], "unnamed-brick")
            self.assertEqual(parsed[0]["brick_entries"][0]["next_action"], "review")

    def test_brick_registry_without_bricks_is_empty_and_healthy(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            registry = build_brick_registry(project_root, "sample-service", [], None)

            self.assertEqual(registry["schema_version"], "switchboard-brick-registry-v0")
            self.assertEqual(registry["summary"]["brick_count"], 0)
            self.assertEqual(registry["bricks"], [])
            self.assertEqual(registry["ui_surface"], "none")
            self.assertEqual(registry["tool"]["package"], "switchboard.bricks")
            self.assertEqual(registry["tool"]["package_alias"], "switchboard.brics")
            self.assertEqual(registry["tool"]["version"], "2026-05-25")
            self.assertEqual(registry["benchmark_keyword_contract"]["keyword_id_format"], "kw_<slug>_<4_digit_serial>")
            self.assertIn("Human quick verify", " ".join(registry["benchmark_keyword_rules"]))

    def test_switchboard_seeded_brick_registry_uses_git_stats(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            def fake_git(_: Path, args: list[str]) -> str:
                if args[:2] == ["rev-parse", "HEAD"]:
                    return "headsha"
                if args[:2] == ["log", "-1"]:
                    return "Seed subject"
                if args[:3] == ["show", "--shortstat", "--format="]:
                    return " 4 files changed, 10 insertions(+), 3 deletions(-)"
                if args[:1] == ["show"] and str(args[1]).endswith(":package.json"):
                    return '{"version":"1.12.6"}'
                return ""

            with mock.patch.object(brick_registry_module, "_run_git", side_effect=fake_git):
                registry = build_brick_registry(
                    project_root,
                    "switch",
                    [],
                    {"line_noise": {"active_source_lines": 100, "noise_line_count": 25}},
                )

            self.assertEqual(registry["schema_version"], "switchboard-brick-registry-v0")
            self.assertEqual(registry["tool"]["package"], "switchboard.bricks")
            self.assertEqual(registry["ui_surface"], "none")
            self.assertIn("serial_number", registry["contract"]["computed_fields"])
            self.assertIn("contract_version", registry["contract"]["computed_fields"])
            self.assertIn("date_created", registry["contract"]["computed_fields"])
            self.assertEqual(registry["benchmark_keyword_contract"]["bucket_id_format"], "bucket_<slug>_<4_digit_serial>")
            self.assertEqual(registry["summary"]["seeded_count"], 4)
            first = registry["bricks"][0]
            self.assertEqual(first["contract_version"], "2026-05-25")
            self.assertEqual(first["serial_number"], "SWITCH-BRICK-0001")
            self.assertEqual(first["files_changed"], 4)
            self.assertEqual(first["insertions"], 10)
            self.assertEqual(first["deletions"], 3)
            self.assertEqual(first["net_lines"], 7)
            self.assertEqual(first["active_lines_after"], 100)
            self.assertEqual(first["stale_lines_after"], 25)
            self.assertEqual(first["version_introduced"], "1.12.6")

    def test_keyword_registry_generates_stable_ids_counts_and_exports(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            entries = normalize_keyword_entries(
                [
                    "source quality | Whether source evidence is clear | evidence | safety; coverage | verified | yes | source has timestamp; source has owner | bench-1, bench-2",
                    "prompt bloat | When labels are too verbose | cleanup | evidence | pending | no | long notes removed | bench-3",
                    "raw leak | email@example.com token raw private payload | secrets | evidence | verified | yes | password token | bench-4",
                ]
            )
            registry = build_keyword_registry(project_root, entries)
            packet = export_small_model_packet(registry)
            report = export_simple_keyword_report(registry)
            serialized = json.dumps(registry)

            self.assertEqual(registry["schema_version"], "switchboard-keyword-registry-v0")
            self.assertEqual(registry["summary"]["keyword_count"], 3)
            self.assertEqual(registry["summary"]["bucket_count"], 3)
            self.assertGreaterEqual(registry["summary"]["similar_bucket_count"], 2)
            self.assertEqual(registry["summary"]["human_verified_count"], 2)
            self.assertEqual(registry["summary"]["active_count"], 2)
            self.assertTrue(all(item["keyword_id"].startswith("kw_") for item in registry["keywords"]))
            self.assertTrue(all(item["bucket_id"].startswith("bucket_") for item in registry["keywords"]))
            self.assertNotIn("email@example.com", serialized)
            self.assertNotIn("raw private payload", serialized)
            self.assertNotIn("password token", serialized)
            self.assertEqual(len(packet["keywords"]), 2)
            self.assertNotIn("prompt bloat", json.dumps(packet))
            self.assertIn("Source Quality", report.title())

    def test_keyword_registry_without_entries_is_empty_and_healthy(self) -> None:
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            registry = build_keyword_registry(project_root, [])

            self.assertEqual(registry["summary"]["keyword_count"], 0)
            self.assertEqual(registry["summary"]["bucket_count"], 0)
            self.assertEqual(registry["keywords"], [])
            self.assertEqual(registry["buckets"], [])
            self.assertEqual(registry["privacy"]["existing_tags"], "candidate_evidence_only")

    def test_hooks_source_capture_stores_raw_prompt_locally_and_returns_safe_summary(self) -> None:
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "timeline.sqlite"
            prompt = "Please preserve my exact words but do not dump raw private text to builders."

            captured = capture_user_prompt(
                prompt=prompt,
                agent="codex",
                cwd="/tmp/project",
                related_brics=["SUITE-BRIC-SOURCE-0001"],
                db_path=db_path,
            )
            registry = build_hooks_registry(Path(tmpdir))
            serialized = json.dumps({**captured, "registry": registry})

            self.assertTrue(db_path.exists())
            self.assertEqual(captured["raw_prompt_included"], False)
            self.assertEqual(captured["prompt_sha256"], "3ef7e603ea8bd6de7ef658389c17a4308c611f14bab6f70e2c7adbd9390a739d")
            self.assertIn("timeline://prompt/", captured["raw_source_ref"])
            self.assertNotIn(prompt, serialized)
            self.assertEqual(registry["schema_version"], "switchboard-hooks-registry-v0")
            self.assertEqual(registry["ui_surface"], "none")

    def test_hook_context_ranks_task_rules_and_stays_under_budget(self) -> None:
        packet = build_context_packet(
            agent="codex",
            cwd="/Users/p/Desktop/work/zapp/docgenerator",
            task="zapp .114 docgenerator cleanup with server proof",
            budget=120,
        )

        self.assertLessEqual(packet["estimated_tokens"], 120)
        self.assertIn("No SSH/SFTP/SCP/rsync", packet["content"])
        self.assertIn("Do not rewrite docgenerator templates", packet["content"])
        self.assertNotIn("raw private", packet["content"].lower())

    def test_user_prompt_submit_response_captures_and_injects_context(self) -> None:
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "timeline.sqlite"
            with mock.patch.dict("os.environ", {"SWITCHBOARD_HOOKS_DB": str(db_path)}):
                response = build_user_prompt_response(
                    hook_payload={
                        "prompt": "Switchboard bric code task. No UI dumping.",
                        "cwd": "/Users/p/Desktop/dashboard",
                        "session_id": "test-session",
                    },
                    agent="codex",
                    budget=220,
                )

            self.assertEqual(response["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
            self.assertIn("additionalContext", response["hookSpecificOutput"])
            self.assertIn("No project-bric UI", response["hookSpecificOutput"]["additionalContext"])
            self.assertEqual(response["switchboard"]["raw_prompt_included"], False)
            self.assertTrue(response["switchboard"]["source_refs"][0].startswith("timeline://prompt/"))

    def test_codex_session_import_reads_user_prompts_into_local_timeline(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session_file = root / "rollout.jsonl"
            db_path = root / "timeline.sqlite"
            session_file.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "timestamp": "2026-05-26T04:00:00.000Z",
                                "type": "session_meta",
                                "payload": {
                                    "id": "session-1",
                                    "cwd": "/tmp/project",
                                    "originator": "Codex Desktop",
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp": "2026-05-26T04:01:00.000Z",
                                "type": "response_item",
                                "payload": {
                                    "type": "message",
                                    "role": "user",
                                    "content": [{"type": "input_text", "text": "record this exact codex prompt"}],
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp": "2026-05-26T04:01:02.000Z",
                                "type": "response_item",
                                "payload": {"type": "message", "role": "assistant", "content": []},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            prompts = list(iter_codex_session_user_prompts(session_file))
            self.assertEqual(len(prompts), 1)
            self.assertEqual(prompts[0]["cwd"], "/tmp/project")

            result = import_codex_session_prompts(project_root=root, session_file=session_file, db_path=db_path)
            repeat = import_codex_session_prompts(project_root=root, session_file=session_file, db_path=db_path)
            summary = read_timeline_summary(db_path)
            serialized = json.dumps(result)

            self.assertEqual(result["imported_count"], 1)
            self.assertEqual(repeat["imported_count"], 1)
            self.assertEqual(result["project_root"], str(root.resolve()))
            self.assertEqual(summary["event_count"], 1)
            self.assertEqual(summary["source_type_counts"]["codex_session_user_prompt"], 1)
            self.assertEqual(result["events"][0]["cwd"], "/tmp/project")
            self.assertNotIn("record this exact codex prompt", serialized)
            self.assertEqual(result["privacy"]["raw_prompt_output"], "excluded")

    def test_memory_query_returns_compact_source_refs_not_raw_records(self) -> None:
        query = build_memory_query(
            task="keyword benchmark small model prompt",
            cwd="/Users/p/Desktop/dashboard",
            budget=140,
        )

        self.assertLessEqual(query["estimated_tokens"], 140)
        self.assertIn("memory://benchmark-keywords", query["source_refs"])
        self.assertIn("human verification", query["content"])
        self.assertNotIn("exact words", query["content"].lower())

    def test_existing_claude_hooks_are_discovered_without_history_reads(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            home = root / "home"
            project = root / "project"
            (home / ".claude").mkdir(parents=True)
            (project / ".claude").mkdir(parents=True)
            (project / ".codex").mkdir(parents=True)
            (home / ".claude" / "settings.json").write_text(
                json.dumps(
                    {
                        "hooks": {
                            "Notification": [
                                {
                                    "matcher": "*",
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": "/Users/p/claude-voice-notify.sh",
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            (project / ".claude" / "settings.local.json").write_text(
                json.dumps(
                    {
                        "hooks": {
                            "UserPromptSubmit": [
                                {
                                    "matcher": "",
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": "python3 -m switchboard.cli hooks user-prompt-submit --agent claude --budget 700",
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch("pathlib.Path.home", return_value=home):
                discovered = discover_existing_hooks(project)
                registry = build_hooks_registry(project)

            self.assertEqual(discovered["hook_count"], 2)
            self.assertIn("Notification", discovered["events"])
            self.assertIn("UserPromptSubmit", discovered["events"])
            self.assertEqual(discovered["switchboard_managed_count"], 1)
            self.assertEqual(discovered["privacy"]["raw_history_files"], "not_read")
            self.assertEqual(registry["existing_hooks"]["hook_count"], 2)
            self.assertIn("claude-voice-notify.sh", json.dumps(discovered))

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
