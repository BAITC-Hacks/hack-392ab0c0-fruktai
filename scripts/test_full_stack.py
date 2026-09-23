"""Start an isolated REAL HTTP server, smoke-test it, restart and verify SQLite.

Uses a temporary database, never the developer's working database or API key.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.smoke_test import run
from agent.api_client import recalculate, get_item


def wait_for_server(process, base: str, log_path: Path, timeout: float = 20) -> None:
    """Report the child process error instead of hiding its temporary log."""
    deadline = time.monotonic() + timeout
    while True:
        exit_code = process.poll()
        if exit_code is not None:
            reason = f"Server exited during startup (exit code {exit_code})"
            break
        try:
            with urlopen(base + "/health", timeout=1) as response:
                if json.load(response) == {"status": "ok"}:
                    return
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            reason = f"Server readiness timeout at {base}"
            break
        time.sleep(0.1)
    output = log_path.read_text(encoding="utf-8", errors="replace").strip()
    raise RuntimeError(
        f"{reason}\nPython: {sys.executable}\n"
        f"--- Uvicorn startup log ---\n{output or '(no server output)'}\n"
        "--- End startup log ---"
    )


def main():
    with tempfile.TemporaryDirectory(prefix="fruktai-http-") as temp:
        env = dict(
            os.environ,
            OPENAI_EXPLANATIONS_ENABLED="false",
            PYTHONIOENCODING="utf-8",
            PYTHONUNBUFFERED="1",
            FRUKTAI_DATA_ROOT=str(ROOT / "data"),
            FRUKTAI_DATABASE_PATH=str(Path(temp) / "db.sqlite"),
            FRUKTAI_RUNS_DIR=str(Path(temp) / "runs"),
        )
        previous = None
        for iteration in range(2):
            # The restart verifies the same DB, not reuse of a particular port.
            # Choose a fresh port to avoid a recently closed Windows socket.
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            base = f"http://127.0.0.1:{port}"
            log_path = Path(temp) / f"server-{iteration}.log"
            with log_path.open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "backend.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                    ],
                    cwd=ROOT,
                    env=env,
                    stdout=log,
                    stderr=log,
                )
                try:
                    wait_for_server(process, base, log_path)
                    if iteration == 0:
                        run(base, "demo")
                        result = recalculate(base)
                        previous = get_item(base, result["recommendations"][0]["sku"])
                    else:
                        assert get_item(base, previous["sku"]) == previous
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
        print("Full HTTP workflow + SQLite restart persistence: OK (AI disabled)")


if __name__ == "__main__":
    main()
