from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from sharp_lab.app import SharpLabApplication

LOGGER = logging.getLogger(__name__)
STATIC_ROOT = files("sharp_lab.ui").joinpath("static")


class SharpLabHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], app: SharpLabApplication) -> None:
        self.app = app
        super().__init__(server_address, SharpLabRequestHandler)


class SharpLabRequestHandler(BaseHTTPRequestHandler):
    server: SharpLabHTTPServer

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({"status": "ok"}, send_body=False)
            return
        if parsed.path == "/api/config":
            self._send_json(self._build_config_payload(), send_body=False)
            return
        if parsed.path == "/api/runs":
            self._send_json({"runs": [self._serialize_run(run) for run in self.server.app.sharp_runs()]}, send_body=False)
            return
        if parsed.path == "/api/release":
            self._send_json(self.server.app.release_status(), send_body=False)
            return
        if parsed.path.startswith("/api/setup/downloads/"):
            try:
                payload = self._download_status_payload(parsed.path)
            except FileNotFoundError:
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            self._send_json(payload, send_body=False)
            return
        if parsed.path.startswith("/artifacts/"):
            self._serve_artifact(parsed.path, send_body=False)
            return
        if parsed.path.startswith("/assets/"):
            self._serve_static(parsed.path.removeprefix("/assets/"), send_body=False)
            return
        if parsed.path in {"/", "/index.html", "/studio", "/setup"}:
            self._serve_static(_resolve_page(self.server.app, parsed.path), send_body=False)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            self._send_json(self._build_config_payload())
            return
        if parsed.path == "/api/runs":
            self._send_json({"runs": [self._serialize_run(run) for run in self.server.app.sharp_runs()]})
            return
        if parsed.path == "/api/release":
            self._send_json(self.server.app.release_status())
            return
        if parsed.path.startswith("/api/setup/downloads/"):
            try:
                payload = self._download_status_payload(parsed.path)
            except FileNotFoundError:
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            self._send_json(payload)
            return
        if parsed.path == "/health":
            self._send_json({"status": "ok"})
            return
        if parsed.path.startswith("/artifacts/"):
            self._serve_artifact(parsed.path)
            return
        if parsed.path.startswith("/assets/"):
            self._serve_static(parsed.path.removeprefix("/assets/"))
            return
        if parsed.path in {"/", "/index.html", "/studio", "/setup"}:
            self._serve_static(_resolve_page(self.server.app, parsed.path))
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/setup/install-runtime":
            self._handle_install_runtime()
            return
        if parsed.path == "/api/setup/download-checkpoint":
            self._handle_download_checkpoint()
            return

        if parsed.path == "/api/predict":
            self._handle_predict()
            return

        if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/decimate"):
            self._handle_decimate(parsed.path)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("%s - %s", self.client_address[0], format % args)

    def _build_config_payload(self) -> dict[str, object]:
        status = self.server.app.sharp_status()
        return {
            "workspace": str(self.server.app.config.paths.workspace),
            "runs_dir": str(self.server.app.config.paths.runs),
            "sharp": status,
            "release": self.server.app.release_status(),
            "web": {
                "host": self.server.app.config.web.host,
                "port": self.server.app.config.web.port,
            },
        }

    def _serialize_run(self, run: Any) -> dict[str, object]:
        payload = run.to_dict() if hasattr(run, "to_dict") else dict(run)
        payload["viewer_urls"] = [
            f"/artifacts/{payload['run_id']}/{filename}"
            for filename in payload.get("ply_files", [])
        ]
        return payload

    def _read_json(self) -> dict[str, object]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _send_json(
        self,
        payload: dict[str, object],
        status: HTTPStatus = HTTPStatus.OK,
        send_body: bool = True,
    ) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def _serve_static(self, relative_path: str, send_body: bool = True) -> None:
        relative = relative_path or "index.html"
        target = STATIC_ROOT.joinpath(relative)
        if not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Static asset not found")
            return

        data = target.read_bytes()
        content_type = _guess_content_type(target.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def _serve_artifact(self, path: str, send_body: bool = True) -> None:
        parts = [part for part in path.split("/") if part]
        if len(parts) != 3:
            self.send_error(HTTPStatus.NOT_FOUND, "Artifact not found")
            return

        _, run_id, filename = parts
        try:
            artifact = self.server.app.sharp_service.artifact_path(run_id, unquote(filename))
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND, "Artifact not found")
            return

        data = artifact.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", _guess_content_type(artifact.name))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def _handle_predict(self) -> None:
        payload = self._read_json()
        input_path_raw = payload.get("input_path")
        if not isinstance(input_path_raw, str) or not input_path_raw.strip():
            self._send_json({"error": "input_path is required."}, status=HTTPStatus.BAD_REQUEST)
            return

        device_raw = payload.get("device")
        device = device_raw.strip() if isinstance(device_raw, str) and device_raw.strip() else None

        try:
            run = self.server.app.sharp_predict(Path(input_path_raw).expanduser(), device=device)
        except Exception as exc:
            LOGGER.exception("SHARP predict request failed")
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_json({"run": self._serialize_run(run)}, status=HTTPStatus.CREATED)

    def _handle_download_checkpoint(self) -> None:
        try:
            task = self.server.app.start_model_download()
        except Exception as exc:
            LOGGER.exception("SHARP checkpoint download failed")
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_json(
            {
                "task": task,
                "sharp": self.server.app.sharp_status(),
            },
            status=HTTPStatus.ACCEPTED,
        )

    def _handle_install_runtime(self) -> None:
        try:
            task = self.server.app.start_runtime_install()
        except Exception as exc:
            LOGGER.exception("SHARP runtime install failed")
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_json(
            {
                "task": task,
                "sharp": self.server.app.sharp_status(),
                "release": self.server.app.release_status(),
            },
            status=HTTPStatus.ACCEPTED,
        )

    def _handle_decimate(self, path: str) -> None:
        parts = [part for part in path.split("/") if part]
        if len(parts) != 4:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        _, _, run_id, _ = parts
        payload = self._read_json()
        filename = payload.get("filename")
        ratio_raw = payload.get("ratio")
        if not isinstance(filename, str) or not filename.strip():
            self._send_json({"error": "filename is required."}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            ratio = float(ratio_raw)
        except (TypeError, ValueError):
            self._send_json({"error": "ratio must be a number between 0 and 1."}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            run, decimation = self.server.app.sharp_decimate(run_id, filename=filename.strip(), ratio=ratio)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except FileNotFoundError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
            return
        except Exception as exc:
            LOGGER.exception("SHARP decimation request failed")
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_json(
            {"run": self._serialize_run(run), "decimation": decimation},
            status=HTTPStatus.CREATED,
        )

    def _download_status_payload(self, path: str) -> dict[str, object]:
        kind = path.removeprefix("/api/setup/downloads/").strip("/")
        if kind not in {"runtime", "model"}:
            raise FileNotFoundError(f"Unknown download kind: {kind}")
        return {
            "task": self.server.app.download_status(kind),
            "sharp": self.server.app.sharp_status(),
            "release": self.server.app.release_status(),
        }


def serve(app: SharpLabApplication, host: str, port: int) -> None:
    server = SharpLabHTTPServer((host, port), app)
    LOGGER.info("sharp_lab web UI listening on http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Stopping sharp_lab web UI")
    finally:
        server.server_close()


def _guess_content_type(filename: str) -> str:
    lower_name = filename.lower()
    if lower_name.endswith(".html"):
        return "text/html; charset=utf-8"
    if lower_name.endswith(".css"):
        return "text/css; charset=utf-8"
    if lower_name.endswith(".js"):
        return "application/javascript; charset=utf-8"
    if lower_name.endswith(".json"):
        return "application/json; charset=utf-8"
    if lower_name.endswith(".ply"):
        return "application/octet-stream"
    return "application/octet-stream"


def _resolve_page(app: SharpLabApplication, path: str) -> str:
    if path == "/setup":
        return "setup.html"
    if path == "/studio":
        return "index.html"
    if path == "/":
        return "setup.html" if app.release.is_lite else "index.html"
    return "index.html"
