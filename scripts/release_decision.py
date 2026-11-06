"""Decide whether this workflow run may publish, resume or must stop.

Kept as a pure function so the recovery rules are tested rather than inferred
from YAML. A tag that already names this SHA may resume even after main moved;
a new tag may only be created from current main.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def decide(*, ci_green: bool, sha: str, main: str, tag_sha: str) -> tuple[bool, str]:
    if not ci_green:
        return False, f"CI on {sha[:12]} did not pass on a push"
    if tag_sha:
        if tag_sha != sha:
            return False, f"version already published at {tag_sha[:12]}; never rebuild it from {sha[:12]}"
        return True, "tag already names this SHA: resume missing assets"
    if main != sha:
        return False, f"tag absent and main advanced to {main[:12]}; a new release needs its own CI"
    return True, "new release from current main"


def main_cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci-green", choices=["true", "false"], required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--main", required=True)
    parser.add_argument("--tag-sha", default="")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    publish, reason = decide(ci_green=args.ci_green == "true", sha=args.sha,
                             main=args.main, tag_sha=args.tag_sha)
    print(f"{'publish' if publish else 'skip'}: {reason}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"publish={'true' if publish else 'false'}\ntag={args.tag}\nversion={args.version}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
