from __future__ import annotations

import logging
import threading
import time
import webbrowser

from sharp_lab.app import SharpLabApplication
from sharp_lab.ui.server import SharpLabHTTPServer

LOGGER = logging.getLogger(__name__)


def run_desktop_app(app: SharpLabApplication, host: str, port: int) -> None:
    server = SharpLabHTTPServer((host, port), app)
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{browser_host}:{port}{app.release.landing_path}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    LOGGER.info("sharp_lab desktop server listening on %s", url)

    try:
        _open_desktop_window(url)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _open_desktop_window(url: str) -> None:
    try:
        import webview  # type: ignore[import-not-found]
    except Exception:
        LOGGER.warning("pywebview is not available; opening Sharp Lab in the default browser.")
        webbrowser.open(url)
        _wait_until_interrupted()
        return

    window = webview.create_window("Sharp Lab", url, width=1280, height=860, min_size=(960, 640))
    webview.start()
    if window is None:
        return


def _wait_until_interrupted() -> None:
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        LOGGER.info("Stopping sharp_lab desktop fallback browser session.")
