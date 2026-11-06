from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Iterable

from .errors import ApprovalError, SafetyError, ValidationError
from .util import sha256_file

FORBIDDEN_NAMES = {"data", "mods", "overwrite", "profiles", "saves"}


def resolve_existing_or_parent(path: Path) -> Path:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).absolute()
    missing: list[str] = []
    current = candidate
    while not current.exists() and current != current.parent:
        missing.append(current.name)
        current = current.parent
    resolved = current.resolve(strict=current.exists())
    for name in reversed(missing):
        resolved = resolved / name
    return resolved


def is_within(path: Path, roots: Iterable[Path]) -> bool:
    candidate = resolve_existing_or_parent(path)
    for root in roots:
        try:
            candidate.relative_to(resolve_existing_or_parent(root))
            return True
        except ValueError:
            continue
    return False


def _is_reparse_link(item: Path) -> bool:
    """True for symlinks (including dangling ones) and Windows junctions.

    `exists() and is_symlink()` misses a dangling link, because exists() follows the
    target and returns False when the target is gone. is_symlink() itself uses lstat,
    so it answers for the link even when the target is missing.
    """
    try:
        if item.is_symlink():
            return True
    except OSError:
        pass
    is_junction = getattr(item, "is_junction", None)
    if is_junction is not None:
        try:
            if is_junction():
                return True
        except OSError:
            pass
    try:
        attributes = item.lstat().st_file_attributes
    except (AttributeError, OSError):
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def reject_symlink_chain(path: Path, *, stop: Path | None = None) -> None:
    candidate = path.expanduser().absolute()
    stop_resolved = stop.expanduser().absolute() if stop else None
    chain: list[Path] = []
    current = candidate
    while True:
        chain.append(current)
        if stop_resolved and current == stop_resolved:
            break
        if current == current.parent:
            break
        current = current.parent
    for item in chain:
        if _is_reparse_link(item):
            raise SafetyError(f"Symlink/reparse-point path is not allowed for writes: {item}")


def require_within(path: Path, root: Path, *, must_exist: bool = False) -> Path:
    candidate = resolve_existing_or_parent(path)
    root_resolved = resolve_existing_or_parent(root)
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise SafetyError(f"Path escapes configured workspace: {path}") from exc
    reject_symlink_chain(path, stop=root)
    if must_exist and not path.exists():
        raise FileNotFoundError(path)
    return candidate


def require_read(path: Path, roots: Iterable[Path]) -> Path:
    if not path.exists():
        raise FileNotFoundError(path)
    if not is_within(path, roots):
        raise SafetyError(f"Read denied outside configured roots: {path}")
    return path.resolve(strict=True)


def require_approval(approved: bool, operation: str) -> None:
    if not approved:
        raise ApprovalError(f"Explicit approval is required for {operation}")


def validate_filename(name: str, suffixes: set[str] | None = None) -> None:
    if not name or name in {".", ".."} or Path(name).name != name:
        raise ValidationError(f"Unsafe filename: {name!r}")
    if any(c in name for c in '<>:"/\\|?*') or name.endswith((" ", ".")):
        raise ValidationError(f"Unsafe Windows filename: {name!r}")
    if suffixes and Path(name).suffix.casefold() not in {x.casefold() for x in suffixes}:
        raise ValidationError(f"Filename must use one of {sorted(suffixes)}: {name}")


__all__ = [
    "ApprovalError", "SafetyError", "sha256_file", "resolve_existing_or_parent", "is_within",
    "require_within", "require_read", "require_approval", "validate_filename",
]
