"""FastAPI app for node mode."""

from __future__ import annotations

import html
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .defaults import DEFAULT_NODE_PORT
from .node import (
    list_manager_roots,
    list_node_files,
    load_manager_manifest,
    load_node_manifest,
    load_pull_bundle_history,
    manager_all_root_health,
    manager_all_root_snapshot,
    manager_all_root_upgrade,
    manager_all_root_verify_update,
    manager_archive_old_scaffolding,
    manager_install_root,
    manager_root_health,
    manager_root_manifest,
    manager_root_snapshot,
    manager_root_verify_update,
    manager_safe_action,
    manager_upgrade_root,
    resolve_static_app_dir,
    snapshot_node,
)


def create_node_app(project_root: str | Path | None = None) -> FastAPI:
    project_root_value = project_root or os.environ.get("SWITCHBOARD_NODE_PROJECT_ROOT")
    if not project_root_value:
        raise RuntimeError("Node project root not provided.")
    project_root = Path(project_root_value).resolve()
    app = FastAPI(title="Switchboard Node", version=__version__)
    static_dir = resolve_static_app_dir()
    assets_dir = static_dir / "assets" if static_dir else None

    def _current_snapshot() -> dict[str, object]:
        snapshot = snapshot_node(project_root)
        manifest = snapshot["manifest"]
        return {
            "manifest": manifest,
            "scope_snapshot": snapshot["scope_snapshot"],
            "doc_index": snapshot.get("doc_index", manifest.get("doc_index", {})),
            "files": list_node_files(project_root),
            "pull_bundle_history": load_pull_bundle_history(project_root),
            "last_snapshot_at": snapshot["scope_snapshot"].get("generated") or manifest.get("updated_at"),
            "runtime": manifest.get("runtime", {}),
        }

    @app.get("/api/health")
    def health() -> dict[str, object]:
        manifest = load_node_manifest(project_root) if (project_root / "switchboard" / "node.manifest.json").exists() else snapshot_node(project_root)["manifest"]
        return {
            "status": "ok",
            "mode": "node",
            "version": __version__,
            "service_id": manifest["service_id"],
            "project_root": str(project_root),
        }

    @app.get("/api/node")
    def node_info() -> dict[str, object]:
        return _current_snapshot()

    @app.post("/api/node/snapshot")
    def refresh_snapshot() -> dict[str, object]:
        return snapshot_node(project_root)

    if assets_dir and assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def root() -> HTMLResponse:
        snapshot = _current_snapshot()
        manifest = snapshot["manifest"]
        runtime = snapshot["runtime"]
        files = snapshot["files"]
        scope_snapshot = snapshot["scope_snapshot"]
        doc_index = snapshot.get("doc_index", {})
        pull_bundle_history = snapshot["pull_bundle_history"]
        managed_docs = manifest.get("managed_docs", [])
        display_name = html.escape(str(manifest.get("display_name", manifest.get("service_id", "Node"))))
        service_id = html.escape(str(manifest.get("service_id", "")))
        project_root_text = html.escape(str(manifest.get("project_root", "")))
        last_snapshot = html.escape(str(snapshot.get("last_snapshot_at", "")))
        monitoring_mode = html.escape(str(runtime.get("monitoring_mode", "manual")))
        expected_ports = html.escape(", ".join(str(port) for port in runtime.get("expected_ports", [])) or "none")
        healthcheck_command = html.escape(str(runtime.get("healthcheck_command", "") or "Not configured"))
        run_command_hint = html.escape(str(runtime.get("run_command_hint", "") or "Not configured"))
        installed_version = html.escape(str(manifest.get("installed_version", __version__)))
        bootstrap_version = html.escape(str(manifest.get("bootstrap_version", "") or "not recorded"))
        generated = html.escape(str(scope_snapshot.get("generated", "")))
        doc_index_generated = html.escape(str(doc_index.get("generated", "")))
        project_root_command = html.escape(str(project_root))
        bundles = pull_bundle_history.get("bundles", [])
        latest_bundle = bundles[0] if bundles else None
        latest_bundle_files_html = ""
        latest_bundle_skipped_html = ""
        if latest_bundle:
            latest_bundle_files_html = "".join(
                f"<li><code>{html.escape(str(item.get('relative_path', '')))}</code> · {html.escape(str(item.get('kind', '')))}</li>"
                for item in latest_bundle.get("files", [])[:20]
            ) or "<li>No copied files recorded.</li>"
            latest_bundle_skipped_html = "".join(
                f"<li><code>{html.escape(str(item.get('path', '')))}</code> · {html.escape(str(item.get('reason', '')))}</li>"
                for item in latest_bundle.get("skipped_entries", [])[:20]
            ) or "<li>No missed entries.</li>"
        page = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Switchboard Node</title>
    <style>
      body {{ font-family: ui-sans-serif, system-ui, sans-serif; background: #020617; color: #e5e7eb; margin: 0; }}
      .wrap {{ max-width: 980px; margin: 0 auto; padding: 24px; }}
      .hero {{ border: 1px solid #1f2937; background: linear-gradient(135deg, #111827, #020617); border-radius: 18px; padding: 24px; }}
      .muted {{ color: #94a3b8; }}
      .grid {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); margin-top: 20px; }}
      .card {{ border: 1px solid #1f2937; background: #0f172a; border-radius: 16px; padding: 16px; }}
      code, pre {{ background: #020617; border: 1px solid #1f2937; border-radius: 10px; }}
      code {{ padding: 2px 6px; }}
      pre {{ padding: 12px; overflow-x: auto; color: #93c5fd; }}
      ul {{ padding-left: 18px; }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <section class="hero">
        <div class="muted">Switchboard Node</div>
        <h1>{display_name}</h1>
        <p class="muted">Minimal local node dashboard for identity, docs pack, runtime config, and snapshot status.</p>
        <p><strong>Service:</strong> <code>{service_id}</code></p>
        <p><strong>Project root:</strong> <code>{project_root_text}</code></p>
        <p><strong>Last snapshot:</strong> <code>{last_snapshot}</code></p>
        <p><strong>Installed version:</strong> <code>{installed_version}</code></p>
        <p><strong>Bootstrap version:</strong> <code>{bootstrap_version}</code></p>
      </section>
        <section class="grid">
        <div class="card">
          <h2>Runtime</h2>
          <p><strong>Monitoring mode:</strong> {monitoring_mode}</p>
          <p><strong>Expected ports:</strong> {expected_ports}</p>
          <p><strong>Health check:</strong></p>
          <pre>{healthcheck_command}</pre>
          <p><strong>Run command hint:</strong></p>
          <pre>{run_command_hint}</pre>
        </div>
        <div class="card">
          <h2>Scope Snapshot</h2>
          <p><strong>Scope entries:</strong> {len(scope_snapshot.get("scope_entries", []))}</p>
          <p><strong>Scope updates:</strong> {len(scope_snapshot.get("scope_updates", []))}</p>
          <p><strong>Generated:</strong> <code>{generated}</code></p>
        </div>
        <div class="card">
          <h2>Docs Pack</h2>
          <p><strong>Tracked node files:</strong> {len(files)}</p>
          <ul>
            <li><code>switchboard/node.manifest.json</code></li>
            <li><code>switchboard/core/playbook.md</code></li>
            <li><code>switchboard/core/</code></li>
            <li><code>switchboard/local/</code></li>
            <li><code>switchboard/evidence/</code></li>
          </ul>
        </div>
      </section>
      <section class="card" style="margin-top: 16px;">
        <h2>Managed Docs</h2>
        <p><strong>Doc index generated:</strong> <code>{doc_index_generated or "not yet"}</code></p>
        <ul>
          {"".join(
              f"<li><code>{html.escape(str(entry.get('doc_id', '')))}</code> → "
              f"<code>{html.escape(str(entry.get('path', '')))}</code> · "
              f"{'enabled' if entry.get('enabled') else 'disabled'} · "
              f"generated <code>{html.escape(str(entry.get('last_generated_at') or ''))}</code></li>"
              for entry in managed_docs
          ) or "<li>No managed docs configured.</li>"}
        </ul>
      </section>
      <section class="card" style="margin-top: 16px;">
        <h2>Pull Bundle History</h2>
        <p><strong>Bundles:</strong> {len(bundles)}</p>
        <ul>
          {"".join(
              f"<li><code>{html.escape(str(bundle.get('bundle_id', '')))}</code> · "
              f"{html.escape(str(bundle.get('file_count', 0)))} files · "
              f"{html.escape(str(bundle.get('created_at', '')))}</li>"
              for bundle in bundles[:8]
          ) or "<li>No pulled bundles mirrored to this node yet.</li>"}
        </ul>
      </section>
      <section class="card" style="margin-top: 16px;">
        <h2>Latest Pulled Bundle Detail</h2>
        {
          (
            f"<p><strong>Bundle:</strong> <code>{html.escape(str(latest_bundle.get('bundle_id', '')))}</code></p>"
            f"<p><strong>Pulled files:</strong> {html.escape(str(latest_bundle.get('file_count', 0)))}</p>"
            f"<p><strong>Missed scope entries:</strong> {html.escape(str(latest_bundle.get('skipped_entry_count', 0)))}</p>"
            f"<ul>{latest_bundle_files_html}</ul>"
            f"<h3>Missed</h3><ul>{latest_bundle_skipped_html}</ul>"
          )
          if latest_bundle
          else "<p>No pulled bundle detail mirrored to this node yet.</p>"
        }
      </section>
      <section class="card" style="margin-top: 16px;">
        <h2>Operator Notes</h2>
        <ul>
          <li>Node sync is manual and control-center initiated.</li>
          <li>This node does not push into the control center and does not SSH back to it.</li>
          <li>Update <code>switchboard/local/tasks-completed.md</code> and run <code>switchboard node snapshot --project-root {project_root_command}</code>.</li>
        </ul>
      </section>
    </div>
  </body>
</html>"""
        return HTMLResponse(page)

    if static_dir and (static_dir / "index.html").exists():

        @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
        def static_asset(full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            candidate = static_dir / full_path
            if candidate.exists() and candidate.is_file():
                return FileResponse(candidate)
            return JSONResponse({"detail": "Not Found"}, status_code=404)

    return app


def create_manager_node_app(manager_root: str | Path, runtime_port: int | None = None) -> FastAPI:
    manager_root = Path(manager_root).resolve()
    app = FastAPI(title="Switchboard Manager Node", version=__version__)

    def _reported_runtime_port(manifest: dict[str, object]) -> object:
        return runtime_port if runtime_port is not None else manifest.get("runtime_port", DEFAULT_NODE_PORT)

    def _not_found(error: Exception) -> HTTPException:
        return HTTPException(status_code=404, detail=str(error))

    @app.get("/api/health")
    def health() -> dict[str, object]:
        manifest = load_manager_manifest(manager_root)
        roots = manifest.get("managed_roots", [])
        enabled_roots = [root for root in roots if isinstance(root, dict) and root.get("enabled", True)]
        return {
            "status": "ok",
            "mode": "manager",
            "version": __version__,
            "manager_id": manifest.get("manager_id", ""),
            "manager_root": str(manager_root),
            "runtime_port": _reported_runtime_port(manifest),
            "manifest_runtime_port": manifest.get("runtime_port", DEFAULT_NODE_PORT),
            "root_count": len(enabled_roots),
        }

    @app.get("/api/manager")
    def manager_info() -> dict[str, object]:
        return list_manager_roots(manager_root)

    @app.get("/api/manager/roots")
    def manager_roots() -> dict[str, object]:
        return {"roots": list_manager_roots(manager_root)["roots"]}

    @app.post("/api/manager/actions/status")
    def manager_status() -> dict[str, object]:
        return manager_all_root_health(manager_root)

    @app.post("/api/manager/actions/snapshot")
    def manager_snapshot() -> dict[str, object]:
        return manager_all_root_snapshot(manager_root)

    @app.post("/api/manager/actions/install")
    def manager_install(payload: dict[str, object]) -> dict[str, object]:
        project_root = str(payload.get("project_root", "")).strip()
        if not project_root:
            raise HTTPException(status_code=422, detail="project_root is required")
        return manager_install_root(
            manager_root,
            project_root,
            root_id=str(payload.get("root_id") or "") or None,
            role=str(payload.get("role") or "minion"),
            service_id=str(payload.get("service_id") or "") or None,
            display_name=str(payload.get("display_name") or "") or None,
        )

    @app.post("/api/manager/actions/upgrade")
    def manager_upgrade() -> dict[str, object]:
        return manager_all_root_upgrade(manager_root)

    @app.post("/api/manager/actions/verify-update")
    def manager_verify_update() -> dict[str, object]:
        return manager_all_root_verify_update(manager_root)

    @app.post("/api/manager/actions/archive-old-scaffolding")
    def manager_archive() -> dict[str, object]:
        return manager_archive_old_scaffolding(manager_root)

    @app.post("/api/manager/actions/{action}")
    def manager_action(action: str) -> dict[str, object]:
        result = manager_safe_action(manager_root, action)
        if result.get("status") == "permission_limited":
            raise HTTPException(status_code=403, detail=result)
        return result

    @app.get("/api/manager/roots/{root_id}/health")
    def root_health(root_id: str) -> dict[str, object]:
        try:
            return manager_root_health(manager_root, root_id)
        except (FileNotFoundError, KeyError) as error:
            raise _not_found(error) from error

    @app.get("/api/manager/roots/{root_id}/manifest")
    def root_manifest(root_id: str) -> dict[str, object]:
        try:
            return manager_root_manifest(manager_root, root_id)
        except (FileNotFoundError, KeyError) as error:
            raise _not_found(error) from error

    @app.post("/api/manager/roots/{root_id}/snapshot")
    def root_snapshot(root_id: str) -> dict[str, object]:
        try:
            return manager_root_snapshot(manager_root, root_id)
        except (FileNotFoundError, KeyError) as error:
            raise _not_found(error) from error

    @app.post("/api/manager/roots/{root_id}/verify-update")
    def root_verify_update(root_id: str) -> dict[str, object]:
        try:
            return manager_root_verify_update(manager_root, root_id)
        except (FileNotFoundError, KeyError) as error:
            raise _not_found(error) from error

    @app.post("/api/manager/roots/{root_id}/upgrade")
    def root_upgrade(root_id: str) -> dict[str, object]:
        try:
            return manager_upgrade_root(manager_root, root_id)
        except (FileNotFoundError, KeyError) as error:
            raise _not_found(error) from error

    @app.post("/api/manager/roots/{root_id}/archive-old-scaffolding")
    def root_archive_old_scaffolding(root_id: str) -> dict[str, object]:
        try:
            return manager_archive_old_scaffolding(manager_root, root_id=root_id)
        except (FileNotFoundError, KeyError) as error:
            raise _not_found(error) from error

    @app.get("/", include_in_schema=False)
    def root() -> HTMLResponse:
        manifest = load_manager_manifest(manager_root)
        roots = manifest.get("managed_roots", [])
        root_rows = "".join(
            "<tr>"
            f"<td><code>{html.escape(str(item.get('root_id', '')))}</code></td>"
            f"<td>{html.escape(str(item.get('display_name', '')))}</td>"
            f"<td><code>{html.escape(str(item.get('project_root', '')))}</code></td>"
            f"<td>{html.escape(str(item.get('verify_status', 'not_run')))}</td>"
            "</tr>"
            for item in roots
            if isinstance(item, dict)
        )
        page = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Switchboard Manager Node</title>
    <style>
      body {{ font-family: ui-sans-serif, system-ui, sans-serif; background: #020617; color: #e5e7eb; margin: 0; }}
      .wrap {{ max-width: 1080px; margin: 0 auto; padding: 24px; }}
      .hero, table {{ border: 1px solid #1f2937; background: #0f172a; border-radius: 12px; }}
      .hero {{ padding: 20px; }}
      table {{ width: 100%; border-collapse: collapse; margin-top: 16px; overflow: hidden; }}
      th, td {{ border-bottom: 1px solid #1f2937; padding: 10px; text-align: left; }}
      code {{ color: #93c5fd; }}
      .muted {{ color: #94a3b8; }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <section class="hero">
        <div class="muted">Switchboard Manager Node</div>
        <h1>{html.escape(str(manifest.get("manager_id", "manager")))}</h1>
        <p><strong>Manager root:</strong> <code>{html.escape(str(manager_root))}</code></p>
        <p><strong>Runtime port:</strong> <code>{html.escape(str(_reported_runtime_port(manifest)))}</code></p>
        <p class="muted"><strong>Manifest runtime port:</strong> <code>{html.escape(str(manifest.get("runtime_port", DEFAULT_NODE_PORT)))}</code></p>
      </section>
      <table>
        <thead><tr><th>Root ID</th><th>Project</th><th>Root</th><th>Verify</th></tr></thead>
        <tbody>{root_rows or "<tr><td colspan='4'>No managed roots registered.</td></tr>"}</tbody>
      </table>
    </div>
  </body>
</html>"""
        return HTMLResponse(page)

    return app
