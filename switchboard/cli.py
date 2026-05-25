"""CLI entrypoints for Switchboard."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import typer

from .collectors import CollectionCoordinator
from .bricks import build_brick_registry, build_keyword_registry, normalize_keyword_entries
from .config import ROOT_DIR, get_settings
from .defaults import DEFAULT_NODE_PORT
from .hooks import (
    build_context_packet,
    build_hooks_registry,
    build_memory_query,
    build_user_prompt_response,
    capture_user_prompt,
    discover_existing_hooks,
)
from .manifests import ManifestStore
from .models import CollectRequest, GitHubBackupRequest
from .node import (
    init_manager_node,
    install_node,
    list_manager_roots,
    manager_all_root_normalize,
    manager_all_root_upgrade,
    manager_all_root_snapshot,
    manager_all_root_verify_update,
    manager_archive_old_scaffolding,
    manager_install_root,
    normalize_manager_root,
    manager_upgrade_root,
    manager_safe_action,
    load_node_manifest,
    node_paths,
    parse_tasks_completed,
    register_manager_root,
    snapshot_node,
    upgrade_node,
    verify_node_update,
)
from .node_api import create_manager_node_app, create_node_app
from .node_runtime import (
    manager_runtime_paths,
    manager_status,
    node_status,
    runtime_paths,
    start_manager_runtime,
    start_node_runtime,
    stop_manager_runtime,
    stop_node_runtime,
)
from .storage import SnapshotStore


app = typer.Typer(help="Switchboard control-center commands.")
node_app = typer.Typer(help="Switchboard node-mode commands.")
bricks_app = typer.Typer(help="Programmatic brick registry tools.")
memory_app = typer.Typer(help="Compact local memory query tools.")
hooks_app = typer.Typer(help="Codex/Claude hook adapters and source-capture tools.")
release_app = typer.Typer(help="Build releasable Switchboard artifacts.")
export_app = typer.Typer(help="Export Switchboard state.")
app.add_typer(node_app, name="node")
bricks_app.add_typer(memory_app, name="memory")
app.add_typer(bricks_app, name="bricks")
app.add_typer(bricks_app, name="brics")
app.add_typer(hooks_app, name="hooks")
app.add_typer(release_app, name="release")
app.add_typer(export_app, name="export")


def _runtime_passwords(pairs: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in pairs:
        if "=" not in item:
            continue
        server_id, password = item.split("=", 1)
        result[server_id] = password
    return result


def _run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


@app.command()
def seed_snapshots() -> None:
    settings = get_settings()
    manifests = ManifestStore(settings)
    snapshots = SnapshotStore(settings, manifests)
    seeded = snapshots.seed_flat_files()
    typer.echo(json.dumps(seeded, indent=2))


@app.command()
def collect(
    workspace_id: str,
    service: list[str] = typer.Option(None, "--service"),
    password: list[str] = typer.Option(None, "--password"),
) -> None:
    settings = get_settings()
    manifests = ManifestStore(settings)
    snapshots = SnapshotStore(settings, manifests)
    coordinator = CollectionCoordinator(settings, manifests, snapshots)
    payload = CollectRequest(
        service_ids=service or [],
        runtime_passwords=_runtime_passwords(password or []),
    )
    result = coordinator.collect_workspace(workspace_id, payload)
    typer.echo(json.dumps(result, indent=2))


@app.command("github-backup")
def github_backup(
    workspace_id: str | None = typer.Option(None, "--workspace-id"),
    service_id: list[str] = typer.Option(None, "--service-id"),
    password: list[str] = typer.Option(None, "--password"),
    run: bool = typer.Option(False, "--run/--dry-run"),
    remote: str = typer.Option("origin", "--remote"),
) -> None:
    settings = get_settings()
    manifests = ManifestStore(settings)
    snapshots = SnapshotStore(settings, manifests)
    coordinator = CollectionCoordinator(settings, manifests, snapshots)
    request = GitHubBackupRequest(
        workspace_id=workspace_id,
        service_ids=service_id or [],
        runtime_passwords=_runtime_passwords(password or []),
        remote=remote,
        dry_run=not run,
    )
    result = coordinator.github_backup_run(request)
    typer.echo(json.dumps(result, indent=2))
    if result.get("status") == "permission_limited":
        raise typer.Exit(1)


@app.command("export-palimpsest")
def export_palimpsest(
    out: str = typer.Option(..., "--out"),
) -> None:
    settings = get_settings()
    manifests = ManifestStore(settings)
    snapshots = SnapshotStore(settings, manifests)
    coordinator = CollectionCoordinator(settings, manifests, snapshots)
    payload = coordinator.export_palimpsest_state()
    output_path = Path(out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    typer.echo(json.dumps({"status": "ok", "path": str(output_path)}, indent=2))


@export_app.command("palimpsest")
def export_palimpsest_nested(
    out: str = typer.Option(..., "--out"),
) -> None:
    export_palimpsest(out=out)


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8009,
    reload: bool = False,
) -> None:
    import uvicorn

    uvicorn.run("switchboard.api:app", host=host, port=port, reload=reload)


@app.command()
def scaffold(
    service_id: str,
    path: str,
    display_name: str | None = None,
) -> None:
    """Compatibility alias for node install."""
    result = install_node(path, service_id=service_id, display_name=display_name)
    typer.echo(json.dumps(result, indent=2))


@node_app.command("install")
def node_install(
    project_root: str = typer.Option(..., "--project-root"),
    service_id: str | None = typer.Option(None, "--service-id"),
    display_name: str | None = typer.Option(None, "--display-name"),
) -> None:
    result = install_node(project_root, service_id=service_id, display_name=display_name)
    typer.echo(json.dumps(result, indent=2))


@node_app.command("upgrade")
def node_upgrade(
    project_root: str = typer.Option(..., "--project-root"),
) -> None:
    result = upgrade_node(project_root)
    typer.echo(json.dumps(result, indent=2))


@node_app.command("snapshot")
def node_snapshot(
    project_root: str = typer.Option(..., "--project-root"),
) -> None:
    result = snapshot_node(project_root)
    typer.echo(json.dumps(result, indent=2))


@node_app.command("verify-update")
def node_verify_update(
    project_root: str = typer.Option(..., "--project-root"),
) -> None:
    result = verify_node_update(project_root)
    typer.echo(json.dumps(result, indent=2))
    if result.get("status") != "ok":
        raise typer.Exit(1)


@bricks_app.command("registry")
def bricks_registry(
    project_root: str = typer.Option(..., "--project-root"),
    write: bool = typer.Option(False, "--write/--no-write"),
) -> None:
    root = Path(project_root).resolve()
    paths = node_paths(root)
    manifest = load_node_manifest(root) if paths["manifest"].exists() else snapshot_node(root)["manifest"]
    tasks = parse_tasks_completed(paths["tasks_completed"])
    foundation_path = paths["node_root"] / "evidence" / "foundation-projection.json"
    foundation_projection = {}
    if foundation_path.exists():
        try:
            foundation_projection = json.loads(foundation_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            foundation_projection = {}
    payload = build_brick_registry(root, str(manifest.get("service_id") or root.name), tasks, foundation_projection)
    if write:
        paths["brick_registry"].parent.mkdir(parents=True, exist_ok=True)
        paths["brick_registry"].write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    typer.echo(json.dumps(payload, indent=2))


@bricks_app.command("keywords")
def brics_keywords(
    project_root: str = typer.Option(..., "--project-root"),
    input_file: str | None = typer.Option(None, "--input"),
    write: bool = typer.Option(False, "--write/--no-write"),
) -> None:
    root = Path(project_root).resolve()
    paths = node_paths(root)
    lines: list[str] = []
    if input_file:
        input_path = Path(input_file).expanduser().resolve()
        lines = input_path.read_text(encoding="utf-8").splitlines()
    payload = build_keyword_registry(root, normalize_keyword_entries(lines))
    if write:
        paths["keyword_registry"].parent.mkdir(parents=True, exist_ok=True)
        paths["keyword_registry"].write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    typer.echo(json.dumps(payload, indent=2))


@memory_app.command("query")
def brics_memory_query(
    task: str = typer.Option(..., "--task"),
    cwd: str = typer.Option("", "--cwd"),
    budget: int = typer.Option(800, "--budget"),
) -> None:
    payload = build_memory_query(task=task, cwd=cwd, budget=budget)
    typer.echo(json.dumps(payload, indent=2))


def _read_stdin_json() -> dict[str, object]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"stdin is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise typer.BadParameter("stdin JSON must be an object")
    return payload


def _hook_python_command(project_root: Path, agent: str, budget: int) -> str:
    return f"python3 -m switchboard.cli hooks user-prompt-submit --agent {agent} --budget {budget}"


def _codex_hooks_config(command: str) -> dict[str, object]:
    return {
        "hooks": {
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command,
                        }
                    ]
                }
            ]
        }
    }


def _claude_hooks_config(command: str) -> dict[str, object]:
    return {
        "hooks": {
            "UserPromptSubmit": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command,
                        }
                    ],
                }
            ]
        }
    }


def _merge_user_prompt_hook_config(path: Path, command: str) -> tuple[dict[str, object], str]:
    payload: dict[str, object] = {}
    status = "written"
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}, "preserved_invalid_json"
        if isinstance(existing, dict):
            payload = existing
    hooks = payload.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    entries = hooks.get("UserPromptSubmit")
    if not isinstance(entries, list):
        entries = []
    command_exists = command in json.dumps(entries)
    if not command_exists:
        entries.append(
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                    }
                ],
            }
        )
    else:
        status = "already_present"
    hooks["UserPromptSubmit"] = entries
    payload["hooks"] = hooks
    return payload, status


@hooks_app.command("build-context")
def hooks_build_context(
    agent: str = typer.Option("codex", "--agent"),
    cwd: str = typer.Option("", "--cwd"),
    task: str = typer.Option("", "--task"),
    budget: int = typer.Option(800, "--budget"),
) -> None:
    payload = build_context_packet(agent=agent, cwd=cwd, task=task, budget=budget)
    typer.echo(json.dumps(payload, indent=2))


@hooks_app.command("capture")
def hooks_capture(
    agent: str = typer.Option("codex", "--agent"),
    cwd: str = typer.Option("", "--cwd"),
    prompt: str = typer.Option("", "--prompt"),
    related_bric: list[str] = typer.Option(None, "--related-bric"),
) -> None:
    text = prompt or sys.stdin.read()
    payload = capture_user_prompt(prompt=text, agent=agent, cwd=cwd, related_brics=related_bric or [])
    typer.echo(json.dumps(payload, indent=2))


@hooks_app.command("user-prompt-submit")
def hooks_user_prompt_submit(
    agent: str = typer.Option("codex", "--agent"),
    budget: int = typer.Option(800, "--budget"),
    capture: bool = typer.Option(True, "--capture/--no-capture"),
) -> None:
    payload = _read_stdin_json()
    response = build_user_prompt_response(hook_payload=payload, agent=agent, budget=budget, capture=capture)
    typer.echo(json.dumps(response, separators=(",", ":")))


@hooks_app.command("registry")
def hooks_registry(
    project_root: str = typer.Option(..., "--project-root"),
    write: bool = typer.Option(False, "--write/--no-write"),
) -> None:
    root = Path(project_root).resolve()
    payload = build_hooks_registry(root)
    if write:
        paths = node_paths(root)
        paths["hooks_registry"].parent.mkdir(parents=True, exist_ok=True)
        paths["hooks_registry"].write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    typer.echo(json.dumps(payload, indent=2))


@hooks_app.command("discover")
def hooks_discover(
    project_root: str = typer.Option(..., "--project-root"),
) -> None:
    root = Path(project_root).resolve()
    payload = discover_existing_hooks(root)
    typer.echo(json.dumps(payload, indent=2))


@hooks_app.command("install")
def hooks_install(
    project_root: str = typer.Option(..., "--project-root"),
    agent: list[str] = typer.Option(None, "--agent"),
    budget: int = typer.Option(800, "--budget"),
    write: bool = typer.Option(False, "--write/--dry-run"),
) -> None:
    root = Path(project_root).resolve()
    requested = agent or ["codex", "claude"]
    outputs: dict[str, object] = {"project_root": str(root), "write": write, "installed": []}
    for item in requested:
        normalized = item.strip().lower()
        command = _hook_python_command(root, normalized, budget)
        if normalized == "codex":
            path = root / ".codex" / "hooks.json"
            config = _codex_hooks_config(command)
        elif normalized in {"claude", "claude-code"}:
            path = root / ".claude" / "settings.local.json"
            config = _claude_hooks_config(command)
        else:
            continue
        if write:
            config, status = _merge_user_prompt_hook_config(path, command)
            if status != "preserved_invalid_json":
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        else:
            status = "dry_run"
        outputs["installed"].append(
            {
                "agent": normalized,
                "path": str(path),
                "command": command,
                "status": status,
            }
        )
    typer.echo(json.dumps(outputs, indent=2))


@node_app.command("serve")
def node_serve(
    project_root: str = typer.Option(..., "--project-root"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(DEFAULT_NODE_PORT, "--port"),
) -> None:
    import uvicorn

    app_instance = create_node_app(project_root)
    uvicorn.run(app_instance, host=host, port=port)


@node_app.command("manager-init")
def node_manager_init(
    manager_root: str = typer.Option(..., "--manager-root"),
    project_root: list[str] = typer.Option(None, "--project-root"),
    port: int = typer.Option(DEFAULT_NODE_PORT, "--port"),
    snapshot: bool = typer.Option(False, "--snapshot/--no-snapshot"),
) -> None:
    result = init_manager_node(manager_root, project_roots=project_root or [], runtime_port=port, snapshot=snapshot)
    typer.echo(json.dumps(result, indent=2))


@node_app.command("manager-register")
def node_manager_register(
    manager_root: str = typer.Option(..., "--manager-root"),
    project_root: str = typer.Option(..., "--project-root"),
    root_id: str | None = typer.Option(None, "--root-id"),
    role: str = typer.Option("minion", "--role"),
    snapshot: bool = typer.Option(True, "--snapshot/--no-snapshot"),
) -> None:
    result = register_manager_root(manager_root, project_root, root_id=root_id, role=role, snapshot=snapshot)
    typer.echo(json.dumps(result, indent=2))


@node_app.command("manager-install-root")
def node_manager_install_root(
    manager_root: str = typer.Option(..., "--manager-root"),
    project_root: str = typer.Option(..., "--project-root"),
    root_id: str | None = typer.Option(None, "--root-id"),
    role: str = typer.Option("minion", "--role"),
    service_id: str | None = typer.Option(None, "--service-id"),
    display_name: str | None = typer.Option(None, "--display-name"),
) -> None:
    result = manager_install_root(
        manager_root,
        project_root,
        root_id=root_id,
        role=role,
        service_id=service_id,
        display_name=display_name,
    )
    typer.echo(json.dumps(result, indent=2))


@node_app.command("normalize-root")
def node_normalize_root(
    manager_root: str = typer.Option(..., "--manager-root"),
    project_root: str = typer.Option(..., "--project-root"),
    root_id: str | None = typer.Option(None, "--root-id"),
    role: str = typer.Option("minion", "--role"),
    service_id: str | None = typer.Option(None, "--service-id"),
    display_name: str | None = typer.Option(None, "--display-name"),
) -> None:
    result = normalize_manager_root(
        manager_root,
        project_root,
        root_id=root_id,
        role=role,
        service_id=service_id,
        display_name=display_name,
    )
    typer.echo(json.dumps(result, indent=2))
    if result.get("status") != "ok":
        raise typer.Exit(1)


@node_app.command("manager-list")
def node_manager_list(
    manager_root: str = typer.Option(..., "--manager-root"),
) -> None:
    result = list_manager_roots(manager_root)
    typer.echo(json.dumps(result, indent=2))


@node_app.command("manager-snapshot-all")
def node_manager_snapshot_all(
    manager_root: str = typer.Option(..., "--manager-root"),
) -> None:
    result = manager_all_root_snapshot(manager_root)
    typer.echo(json.dumps(result, indent=2))
    if result.get("status") != "ok":
        raise typer.Exit(1)


@node_app.command("manager-upgrade")
def node_manager_upgrade(
    manager_root: str = typer.Option(..., "--manager-root"),
    root_id: str | None = typer.Option(None, "--root-id"),
) -> None:
    result = manager_upgrade_root(manager_root, root_id) if root_id else manager_all_root_upgrade(manager_root)
    typer.echo(json.dumps(result, indent=2))
    if result.get("status") != "ok":
        raise typer.Exit(1)


@node_app.command("manager-normalize-all")
def node_manager_normalize_all(
    manager_root: str = typer.Option(..., "--manager-root"),
) -> None:
    result = manager_all_root_normalize(manager_root)
    typer.echo(json.dumps(result, indent=2))
    if result.get("status") != "ok":
        raise typer.Exit(1)


@node_app.command("manager-verify-all")
def node_manager_verify_all(
    manager_root: str = typer.Option(..., "--manager-root"),
) -> None:
    result = manager_all_root_verify_update(manager_root)
    typer.echo(json.dumps(result, indent=2))
    if result.get("status") != "ok":
        raise typer.Exit(1)


@node_app.command("manager-archive-old-scaffolding")
def node_manager_archive_old_scaffolding(
    manager_root: str = typer.Option(..., "--manager-root"),
    root_id: str | None = typer.Option(None, "--root-id"),
) -> None:
    result = manager_archive_old_scaffolding(manager_root, root_id=root_id)
    typer.echo(json.dumps(result, indent=2))


@node_app.command("manager-safe-action")
def node_manager_safe_action(
    manager_root: str = typer.Option(..., "--manager-root"),
    action: str = typer.Option(..., "--action"),
    root_id: str | None = typer.Option(None, "--root-id"),
) -> None:
    result = manager_safe_action(manager_root, action, root_id=root_id)
    typer.echo(json.dumps(result, indent=2))
    if result.get("status") == "permission_limited":
        raise typer.Exit(1)


@node_app.command("manager-serve")
def node_manager_serve(
    manager_root: str = typer.Option(..., "--manager-root"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(DEFAULT_NODE_PORT, "--port"),
) -> None:
    import uvicorn

    app_instance = create_manager_node_app(manager_root, runtime_port=port)
    uvicorn.run(app_instance, host=host, port=port)


@node_app.command("manager-start")
def node_manager_start(
    manager_root: str = typer.Option(..., "--manager-root"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(DEFAULT_NODE_PORT, "--port"),
) -> None:
    result = start_manager_runtime(manager_root, host=host, port=port)
    typer.echo(json.dumps(result, indent=2))


@node_app.command("manager-stop")
def node_manager_stop(
    manager_root: str = typer.Option(..., "--manager-root"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    result = stop_manager_runtime(manager_root, port=port)
    typer.echo(json.dumps(result, indent=2))


@node_app.command("manager-status")
def node_manager_status(
    manager_root: str = typer.Option(..., "--manager-root"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    result = manager_status(manager_root, port=port)
    typer.echo(json.dumps(result, indent=2))


@node_app.command("start")
def node_start(
    project_root: str = typer.Option(..., "--project-root"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(DEFAULT_NODE_PORT, "--port"),
) -> None:
    result = start_node_runtime(project_root, host=host, port=port)
    typer.echo(json.dumps(result, indent=2))


@node_app.command("stop")
def node_stop(
    project_root: str = typer.Option(..., "--project-root"),
    port: int = typer.Option(DEFAULT_NODE_PORT, "--port"),
) -> None:
    result = stop_node_runtime(project_root, port=port)
    typer.echo(json.dumps(result, indent=2))


@node_app.command("status")
def node_runtime_status(
    project_root: str = typer.Option(..., "--project-root"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    result = node_status(project_root, port=port)
    typer.echo(json.dumps(result, indent=2))


@node_app.command("logs")
def node_logs(
    project_root: str = typer.Option(..., "--project-root"),
    lines: int = typer.Option(40, "--lines"),
) -> None:
    log_file = runtime_paths(project_root)["log"]
    if not log_file.exists():
        typer.echo("")
        return
    text = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = "\n".join(text[-lines:])
    typer.echo(tail)


@node_app.command("manager-logs")
def node_manager_logs(
    manager_root: str = typer.Option(..., "--manager-root"),
    lines: int = typer.Option(40, "--lines"),
) -> None:
    log_file = manager_runtime_paths(manager_root)["log"]
    if not log_file.exists():
        typer.echo("")
        return
    text = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = "\n".join(text[-lines:])
    typer.echo(tail)


@release_app.command("build")
def release_build(
    wheel_out: str = typer.Option("release", "--wheel-out"),
) -> None:
    """
    Build the frontend, bundle static assets into the Python package, and build a wheel.
    """
    root = ROOT_DIR
    dist_dir = root / "dist"
    build_dir = root / "build"
    static_app_dir = root / "switchboard" / "static" / "app"
    wheel_dir = root / wheel_out

    _run(["npm", "run", "build"], root)

    if build_dir.exists():
        shutil.rmtree(build_dir)
    if static_app_dir.exists():
        shutil.rmtree(static_app_dir)
    static_app_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(dist_dir, static_app_dir)

    wheel_dir.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "uv",
            "build",
            "--wheel",
            "--no-build-isolation",
            "--offline",
            "--python",
            sys.executable,
            "--out-dir",
            str(wheel_dir),
        ],
        root,
    )
    typer.echo(str(wheel_dir))


if __name__ == "__main__":
    app()
