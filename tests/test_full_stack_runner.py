"""The HTTP test runner must expose the cause of a failed server start."""
import subprocess
import sys

import pytest

from scripts.test_full_stack import wait_for_server


def test_startup_failure_includes_child_error(tmp_path):
    log_path = tmp_path / "startup.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-c",
             "import sys; print('Missing runtime dependency', file=sys.stderr); sys.exit(7)"],
            stdout=log, stderr=log,
        )
        process.wait(timeout=10)
        with pytest.raises(RuntimeError) as captured:
            wait_for_server(process, "http://127.0.0.1:1", log_path)
    message = str(captured.value)
    assert "exit code 7" in message
    assert "Missing runtime dependency" in message
    assert sys.executable in message
