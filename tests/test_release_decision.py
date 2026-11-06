"""Release recovery rules, tested instead of inferred from workflow YAML."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.release_decision import decide

A = "a" * 40
B = "b" * 40
C = "c" * 40


class ReleaseDecisionTests(unittest.TestCase):
    def test_untagged_current_main_starts_a_new_release(self) -> None:
        self.assertTrue(decide(ci_green=True, sha=A, main=A, tag_sha="")[0])

    def test_untagged_but_main_advanced_is_skipped(self) -> None:
        self.assertFalse(decide(ci_green=True, sha=A, main=B, tag_sha="")[0])

    def test_tag_on_same_sha_resumes_on_current_main(self) -> None:
        self.assertTrue(decide(ci_green=True, sha=A, main=A, tag_sha=A)[0])

    def test_tag_on_same_sha_resumes_after_main_advanced(self) -> None:
        publish, reason = decide(ci_green=True, sha=A, main=C, tag_sha=A)
        self.assertTrue(publish)
        self.assertIn("resume", reason)

    def test_tag_on_another_sha_is_never_rebuilt(self) -> None:
        publish, reason = decide(ci_green=True, sha=B, main=B, tag_sha=A)
        self.assertFalse(publish)
        self.assertIn("never rebuild", reason)

    def test_partial_release_recovery_is_allowed_after_main_moved(self) -> None:
        # Tag at A, assets incomplete, main now C: rerunning A must still work.
        self.assertTrue(decide(ci_green=True, sha=A, main=C, tag_sha=A)[0])

    def test_cli_writes_only_valid_github_output_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out"
            env = {**os.environ, "GITHUB_OUTPUT": str(output)}
            subprocess.run([sys.executable, "scripts/release_decision.py", "--ci-green", "true",
                            "--sha", A, "--main", A, "--tag", "v1.2.3", "--version", "1.2.3"],
                           check=True, capture_output=True, text=True, env=env)
            lines = output.read_text(encoding="utf-8").splitlines()
            self.assertTrue(all("=" in line for line in lines), lines)
            self.assertIn("publish=true", lines)
            self.assertIn("tag=v1.2.3", lines)
            self.assertIn("version=1.2.3", lines)

    def test_failed_ci_never_publishes(self) -> None:
        self.assertFalse(decide(ci_green=False, sha=A, main=A, tag_sha=A)[0])
        self.assertFalse(decide(ci_green=False, sha=A, main=A, tag_sha="")[0])


if __name__ == "__main__":
    unittest.main()
