from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .app_store import AppStore
from .prospects import build_run_prospects, prospects_to_csv
from .research import ResearchPipeline


ASSET_DIR = Path(__file__).with_name("web_assets")
APP_VERSION = "0.1.0"


class GTMApp:
    def __init__(
        self,
        store: AppStore | None = None,
        pipeline: ResearchPipeline | None = None,
        admin_token: str | None = None,
    ) -> None:
        self.store = store or AppStore()
        self.pipeline = pipeline or ResearchPipeline(self.store)
        self.admin_token = (admin_token if admin_token is not None else os.environ.get("ICP_ADMIN_TOKEN", "")).strip()


def make_handler(app: GTMApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Knowledge2ICPWeb/0.1"

        def do_HEAD(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_asset_headers("index.html")
                return
            if parsed.path == "/healthz":
                self._send_json_headers()
                return
            if parsed.path.startswith("/assets/"):
                self._send_asset_headers(parsed.path.removeprefix("/assets/"))
                return
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_asset("index.html")
                return
            if parsed.path.startswith("/assets/"):
                self._send_asset(parsed.path.removeprefix("/assets/"))
                return
            if parsed.path == "/healthz":
                self._send_json(_health_payload(app, detailed=False))
                return
            if parsed.path.startswith("/api/") and not self._authorize_api():
                self._send_unauthorized()
                return
            if parsed.path == "/api/health":
                self._send_json(_health_payload(app, detailed=True))
                return
            if parsed.path == "/api/state":
                self._send_json(app.store.state())
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/k2-manifest"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json(app.pipeline.k2.build_manifest(run))
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/prospects"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json(build_run_prospects(run))
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/prospects.csv"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_text(
                    prospects_to_csv(build_run_prospects(run)),
                    content_type="text/csv; charset=utf-8",
                    filename=f"{run_id}-prospects.csv",
                )
                return
            if parsed.path.startswith("/api/runs/"):
                run_id = parsed.path.rsplit("/", 1)[-1]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json(run)
                return
            self._send_json({"error": "Not found."}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/") and not self._authorize_api():
                self._send_unauthorized()
                return
            if parsed.path == "/api/criteria":
                payload = self._read_json()
                markdown = str(payload.get("markdown", ""))
                if not markdown.strip():
                    self._send_json({"error": "Criteria markdown is required."}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json({"criteria": app.store.save_criteria(markdown)})
                return
            if parsed.path == "/api/search":
                payload = self._read_json()
                candidates, warnings = app.pipeline.discover(
                    str(payload.get("query", "")),
                    seed_text=str(payload.get("seed_text", "")),
                    max_companies=int(payload.get("max_companies") or 10),
                )
                self._send_json(
                    {
                        "candidates": [
                            {
                                "company": item.company,
                                "domain": item.domain,
                                "source_url": item.source_url,
                                "source_title": item.source_title,
                                "notes": item.notes,
                                "github_urls": item.github_urls,
                                "linkedin_urls": item.linkedin_urls,
                                "other_urls": item.other_urls,
                            }
                            for item in candidates
                        ],
                        "warnings": warnings,
                    }
                )
                return
            if parsed.path == "/api/runs":
                payload = self._read_json()
                candidate_payloads = payload.get("candidates")
                try:
                    run = app.pipeline.create_run(
                        query=str(payload.get("query", "")),
                        seed_text=str(payload.get("seed_text", "")),
                        candidate_payloads=candidate_payloads if isinstance(candidate_payloads, list) else None,
                        max_companies=int(payload.get("max_companies") or 8),
                        fetch=bool(payload.get("fetch", True)),
                        max_pages=int(payload.get("max_pages") or 8),
                        include_github=bool(payload.get("include_github", True)),
                        use_apollo=bool(payload.get("use_apollo", False)),
                    )
                except Exception as exc:
                    self._send_json({"error": f"Run failed: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                    return
                self._send_json(run)
                return
            if parsed.path == "/api/research":
                payload = self._read_json()
                answer = app.pipeline.answer_question(
                    run_id=str(payload.get("run_id", "")),
                    question=str(payload.get("question", "")),
                )
                self._send_json(answer)
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/k2-export"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                out_path = app.store.state_dir / "k2_manifests" / f"{run_id}.json"
                self._send_json(app.pipeline.k2.export_manifest(run, out_path))
                return
            if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/k2-sync"):
                run_id = parsed.path.split("/")[3]
                run = app.store.load_run(run_id)
                if not run:
                    self._send_json({"error": "Run not found."}, status=HTTPStatus.NOT_FOUND)
                    return
                payload = self._read_json()
                result = app.pipeline.k2.sync_manifest(
                    run,
                    project_name=str(payload.get("project_name") or "Knowledge2 ICP GTM"),
                    corpus_name=str(payload.get("corpus_name") or f"ICP Run {run_id}"),
                    apply=bool(payload.get("apply", False)),
                )
                if result.get("status") == "uploaded":
                    run["k2"] = result
                    app.store.save_run(run)
                status = HTTPStatus.BAD_REQUEST if result.get("status") == "error" else HTTPStatus.OK
                self._send_json(result, status=status)
                return
            self._send_json({"error": "Not found."}, status=HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_asset(self, name: str) -> None:
            path = self._asset_path(name)
            if not path.exists() or not path.is_file():
                self._send_json({"error": "Asset not found."}, status=HTTPStatus.NOT_FOUND)
                return
            body = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_asset_headers(self, name: str) -> None:
            path = self._asset_path(name)
            if not path.exists() or not path.is_file():
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()
                return
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(path.stat().st_size))
            self.end_headers()

        def _send_json_headers(self, *, status: HTTPStatus = HTTPStatus.OK) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def _asset_path(self, name: str) -> Path:
            return ASSET_DIR / Path(name).name

        def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorize_api(self) -> bool:
            if not app.admin_token:
                return True
            auth_header = self.headers.get("Authorization", "")
            scheme, _, token = auth_header.partition(" ")
            if scheme.lower() != "bearer" or not token:
                return False
            return hmac.compare_digest(token.strip(), app.admin_token)

        def _send_unauthorized(self) -> None:
            body = json.dumps({"error": "Admin token required."}, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("WWW-Authenticate", 'Bearer realm="knowledge2-icp"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_text(
            self,
            payload: str,
            *,
            content_type: str = "text/plain; charset=utf-8",
            status: HTTPStatus = HTTPStatus.OK,
            filename: str | None = None,
        ) -> None:
            body = payload.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0:
                return {}
            body = self.rfile.read(min(length, 5_000_000))
            try:
                payload = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                return {}
            return payload if isinstance(payload, dict) else {}

    return Handler


def _health_payload(app: GTMApp, *, detailed: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "ok",
        "service": "knowledge2-icp",
        "version": APP_VERSION,
        "auth_required": bool(app.admin_token),
    }
    if detailed:
        app.store.ensure()
        payload.update(
            {
                "state_dir": str(app.store.state_dir),
                "state_dir_writable": os.access(app.store.state_dir, os.W_OK),
                "run_count": len(app.store.list_runs()),
                "provider_status": app.store.state().get("provider_status", {}),
            }
        )
    return payload


def run_server(
    host: str,
    port: int,
    store_dir: Path | None = None,
    admin_token: str | None = None,
    *,
    allow_open_api: bool | None = None,
) -> ThreadingHTTPServer:
    token = (admin_token if admin_token is not None else os.environ.get("ICP_ADMIN_TOKEN", "")).strip()
    if not token and not _open_api_allowed(host, allow_open_api):
        raise ValueError("ICP_ADMIN_TOKEN is required when binding the API to a non-loopback host.")
    store = AppStore(state_dir=store_dir) if store_dir else AppStore()
    app = GTMApp(store=store, admin_token=token)
    server = ThreadingHTTPServer((host, port), make_handler(app))
    print(f"Knowledge2 ICP web app running at http://{host}:{port}")
    server.serve_forever()
    return server


def _open_api_allowed(host: str, allow_open_api: bool | None = None) -> bool:
    if allow_open_api is None:
        allow_open_api = os.environ.get("ICP_ALLOW_OPEN_API", "").strip().lower() in {"1", "true", "yes"}
    return allow_open_api or _is_loopback_bind_host(host)


def _is_loopback_bind_host(host: str) -> bool:
    if host.lower() in {"localhost"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Knowledge2 Agentic GTM dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--admin-token", default=None, help="Optional bearer token for /api/* routes. Defaults to ICP_ADMIN_TOKEN.")
    parser.add_argument(
        "--allow-open-api",
        action="store_true",
        default=None,
        help="Allow unauthenticated /api/* routes on non-loopback hosts. Intended only for isolated local networks.",
    )
    args = parser.parse_args(argv)
    run_server(args.host, args.port, args.state_dir, admin_token=args.admin_token, allow_open_api=args.allow_open_api)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
