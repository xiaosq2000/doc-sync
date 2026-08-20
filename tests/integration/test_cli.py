from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from doc_sync.cli import main
from tests.support import initialize_repository, temporary_repository, temporary_root


class CliTest(unittest.TestCase):
    def test_json_check_uses_stable_status_and_exit_code(self) -> None:
        with temporary_repository() as root:
            (root / "src/app.py").write_text("v2", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(["check", "--root", str(root), "--format", "json"])

            payload = json.loads(output.getvalue())
            assert exit_code == 2
            assert payload["status"] == "review_required"
            assert payload["review_targets"] == ["README.md"]

    def test_stop_adapters_block_with_json_on_exit_zero_once(self) -> None:
        # Codex CLI implements Claude Code's Stop-hook wire format, so one
        # contract covers both adapters.
        for agent in ("claude", "codex"):
            with self.subTest(agent=agent), temporary_repository() as root:
                (root / "src/app.py").write_text("v2", encoding="utf-8")
                payload = json.dumps({"session_id": "session-1", "cwd": str(root)})
                arguments = [
                    "hook",
                    agent,
                    "--root",
                    str(root),
                    "--state-directory",
                    str(root / "state"),
                ]
                first_output = io.StringIO()
                with (
                    patch("sys.stdin", io.StringIO(payload)),
                    redirect_stdout(first_output),
                ):
                    first_exit = main(arguments)
                second_output = io.StringIO()
                with (
                    patch("sys.stdin", io.StringIO(payload)),
                    redirect_stdout(second_output),
                ):
                    second_exit = main(arguments)

                response = json.loads(first_output.getvalue())
                assert first_exit == 0
                assert response["decision"] == "block"
                assert "Documentation may need review" in response["reason"]
                assert second_exit == 0
                assert second_output.getvalue() == ""

    def test_codex_adapter_resolves_the_repository_from_the_payload_cwd(self) -> None:
        # Codex exposes no project-directory variable, so a session started in
        # a subdirectory has to reach the repository through `cwd` alone.
        with temporary_repository() as root:
            (root / "src/app.py").write_text("v2", encoding="utf-8")
            nested = root / "src"
            payload = json.dumps({"session_id": "session-1", "cwd": str(nested)})
            output = io.StringIO()
            with patch("sys.stdin", io.StringIO(payload)), redirect_stdout(output):
                exit_code = main(
                    ["hook", "codex", "--state-directory", str(root / "state")]
                )

            response = json.loads(output.getvalue())
            assert exit_code == 0
            assert response["decision"] == "block"
            assert "README.md" in response["reason"]

    def test_stop_hook_config_error_is_structured_blocking_json(self) -> None:
        with temporary_root() as root:
            initialize_repository(root)
            payload = json.dumps({"session_id": "session-1", "cwd": str(root)})
            output = io.StringIO()
            with patch("sys.stdin", io.StringIO(payload)), redirect_stdout(output):
                exit_code = main(["hook", "claude", "--root", str(root)])

            response = json.loads(output.getvalue())
            assert exit_code == 0
            assert response["decision"] == "block"
            assert "configuration file does not exist" in response["reason"]

    def test_operational_error_uses_stderr_and_exit_one(self) -> None:
        with temporary_root() as root:
            error = io.StringIO()
            with redirect_stderr(error):
                exit_code = main(["check", "--root", str(root)])

            assert exit_code == 1
            assert "doc-sync error:" in error.getvalue()
