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


def main():
    with tempfile.TemporaryDirectory(prefix="fruktai-http-") as temp:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = dict(os.environ, OPENAI_EXPLANATIONS_ENABLED="false",
                   FRUKTAI_DATA_ROOT=str(ROOT / "data"),
                   FRUKTAI_DATABASE_PATH=str(Path(temp) / "db.sqlite"),
                   FRUKTAI_RUNS_DIR=str(Path(temp) / "runs"))
        previous = None
        for iteration in range(2):
            with (Path(temp) / f"server-{iteration}.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [sys.executable, "-m", "uvicorn", "backend.main:app",
                     "--host", "127.0.0.1", "--port", str(port)],
                    cwd=ROOT, env=env, stdout=log, stderr=log,
                )
                try:
                    deadline = time.monotonic() + 20
                    while True:
                        if process.poll() is not None:
                            raise RuntimeError("Server exited during startup")
                        try:
                            with urlopen(base + "/health", timeout=1) as response:
                                assert json.load(response) == {"status": "ok"}
                            break
                        except OSError:
                            if time.monotonic() >= deadline:
                                raise RuntimeError("Server readiness timeout")
                            time.sleep(0.1)
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
