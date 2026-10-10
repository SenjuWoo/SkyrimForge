"""Locate the CI workflows that actually build and test this subtree.

GitHub reads `.github/workflows` only from a repository ROOT. Forge has lived
both at a repository root and as a subtree of another checkout, so the jobs
that run it are found by walking up to the nearest checkout root. Tests that assert something about CI have to look there, or they assert it
about a file that no longer exists and pass by never running.
"""

from __future__ import annotations

from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]


def workflows_dir() -> Path | None:
    """The nearest enclosing `.github/workflows`, or None outside a checkout.

    An extracted install has no `.github` anywhere above it. That is not a
    finding -- there is no CI there to be wrong about.
    """
    for parent in (FORGE_ROOT, *FORGE_ROOT.parents):
        candidate = parent / ".github" / "workflows"
        if candidate.is_dir():
            return candidate
    return None
