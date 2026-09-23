"""Run API and Vite together. Ctrl+C stops both. AI is opt-in via --ai."""
import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai", action="store_true", help="Enable OpenAI using server .env")
    args = parser.parse_args()
    vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
    node = shutil.which("node")
    if not node or not vite.is_file():
        parser.error("Install Node.js 22+ and run: npm --prefix frontend ci")
    for port in (8000, 5173):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                parser.error(f"Port {port} is already occupied; stop that server first.")
    api_env = dict(os.environ, OPENAI_EXPLANATIONS_ENABLED=str(args.ai).lower())
    command = [sys.executable, "-m", "uvicorn", "backend.main:app",
               "--host", "127.0.0.1", "--port", "8000", "--workers", "1"]
    if (ROOT / ".env").is_file():
        command.extend(["--env-file", str(ROOT / ".env")])
    web_env = {k: v for k, v in os.environ.items() if not k.startswith("OPENAI_")}
    processes = []
    try:
        processes.append(subprocess.Popen(command, cwd=ROOT, env=api_env))
        processes.append(subprocess.Popen(
            [node, str(vite), "--configLoader", "runner", "--host", "127.0.0.1"],
            cwd=ROOT / "frontend", env=web_env,
        ))
        print("Dashboard: http://127.0.0.1:5173 | API docs: http://127.0.0.1:8000/docs", flush=True)
        print("AI explanations: " + ("enabled" if args.ai else "disabled"), flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.3)
        raise RuntimeError("A server exited. See its error above.")
    except KeyboardInterrupt:
        print("Stopping FruktAI...")
    finally:
        for process in processes:
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
