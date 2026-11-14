"""The Skyrim pack restates no content policy; the host's instructions (the bundle) own it.

A restated rule here gets copied into every provider's instruction file and drifts from the
bundle's wording, so the two conflict. This walks every pack text file, including ones added later.
The one kept line is the AOS note beside the engine's `C` (child) trait: it names a flag the game
itself sets and matches the host's rule, so it never asks a model to judge an age.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

PACK = Path(__file__).resolve().parents[1] / "integrations" / "skyrim-pack"
TEXT = {".md", ".txt", ".json", ".yaml", ".yml", ".py", ".ps1"}
POLICY = re.compile(
    r"age[- ]ambiguous|real[- ]person|likenesses? of real people|stop and refuse|"
    r"\bexclude\b[^.\n]{0,60}\bchild",
    re.IGNORECASE,
)


def policy_hits(text: str) -> list[str]:
    return [match.group(0) for match in POLICY.finditer(text)]


class PackContentPolicyTests(unittest.TestCase):
    def test_pattern_catches_the_removed_wording_and_spares_technical_text(self):
        for line in (
            "exclude child or age-ambiguous actors and real people.",
            "Adult systems must exclude child races, child actors",
            "Stop and refuse only these:",
        ):
            self.assertTrue(policy_hits(line), line)
        for line in (
            "Traits: `M`, `F`, `C` (child), negated (`-C`)",
            "**Do not target child actors with adult content.**",
            "child/RaceChild actors (unique child TRI)",
            "Keep explicit fictional adult-only content and identifiers intact.",
        ):
            self.assertFalse(policy_hits(line), line)

    def test_no_pack_file_restates_a_content_rule(self):
        offenders = []
        for path in sorted(PACK.rglob("*")):
            if path.is_file() and path.suffix.lower() in TEXT:
                hits = policy_hits(path.read_text(encoding="utf-8-sig", errors="replace"))
                if hits:
                    offenders.append(f"{path.relative_to(PACK).as_posix()}: {hits[:3]}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
