---
name: skyrim-versioned-workspace
description: Mandatory workspace ownership and version-snapshot workflow for Skyrim mod creation or editing. Use before the
  first write so agents do not overwrite deployed files or duplicate another agent's project.
compatibility: Windows 10/11; Skyrim Special Edition or Anniversary Edition; PowerShell and Python 3 when bundled scripts
  are used
metadata:
  version: 4.3.0
  updated: '2026-07-22'
  library: overseer-skyrim-agent-skills
  provider: claude
  provider_pack_version: 1.0.0
  base_library: Skyrim-Agent-Skills-v6
  error_registry_revision: 4.3.0
when_to_use: Use for mandatory workspace ownership and version-snapshot workflow for skyrim mod creation or editing.
---

# Versioned Skyrim workspace

## Workspace selection

The workspace root is the directory the user opened, supplied, or explicitly selected.
Do not assume a drive letter, username, folder name, or separate provider-owned workspace.

Several AI applications may work in the same workspace. They share one authoritative
project root and one active version. Switching applications is not a reason to clone
or relocate the project.

## Project layout (snapshot-based mods only)

```text
<WORKSPACE_ROOT>\<Mod Display Name>\
  WORKSPACE_OWNERSHIP.md
  CHANGELOG.txt
  CURRENT.txt
  PLAN.md
  STATE.md
  VALIDATION.md
  MEMORY\
  <Mod Display Name> 1.0.0\
    VERSION.txt
  <Mod Display Name> 1.0.1\
    VERSION.txt
```

## Canonical ownership and publication

Before the first substantive write, read or create `WORKSPACE_OWNERSHIP.md` at the settled project root. Run this skill's `scripts/ensure_ownership.py <project-root>` (or `--check`); it preserves existing records, aliases and source layout and creates no Git remote. WORKSPACE.md is a workspace map, STATE.md is progress, and neither replaces ownership.

New work stays local/private until publication is requested. "Put it on GitHub" means public and MIT for original work by default, subject to third-party rights and platform terms; preserve existing licences and explicit choices. Generic publication uses the appropriate destination (normally Nexus Mods for Skyrim). A mod needing no compilation does not get a duplicate GitHub repository by default; add source hosting when requested or needed for development.

Source ledgers, CHANGELOG.txt, ownership, validation and publication documents stay outside the staged mod payload. A release ZIP contains only the runtime mod/product and required licensing; retain actual runtime TXT/INI/JSON and FOMOD assets.

## Before editing

1. Resolve the authoritative project from `CURRENT.txt`, ownership records,
   supplied archives, and read-only installed evidence.
2. Reject deployed, staging, save, profile, and installed-tool paths as writable roots.
3. Read `CURRENT.txt`, `CHANGELOG.txt`, `STATE.md`, and known-good records.
4. Preserve established Git layouts and tags; do not copy a Git project into nested version folders. For a snapshot-based project, choose the semantic version bump.
5. For snapshot-based projects only, fully copy the current snapshot into the new version folder.
6. Update `CURRENT.txt`.
7. Create or update the new snapshot's `VERSION.txt`.
8. Start the changelog entry before modifying the new snapshot.
9. Edit only the active source owner (the new snapshot for snapshot-based projects).

## Preflight guard

`scripts/guard.py` is bundled with this skill. It refuses the three failures that
prose alone has not prevented: writing into a read-only realm, launching a GUI
tool, and destroying UTF-8 through a PowerShell round-trip.

Run it before the write, not after:

```text
python scripts/guard.py path "<intended write target>"
python scripts/guard.py cmd  "<intended shell command>"
```

Exit `0` allows the action. Exit `2` blocks it and prints the reason and the
supported alternative. `python scripts/guard.py --selftest` verifies the rules.

The guard identifies deployed and managed realms from filesystem evidence
(`SkyrimSE.exe`, `ModOrganizer.ini`, `Vortex.exe` in an ancestor directory), so no
drive letter, username, or folder name is assumed. Set `SKYRIM_GUARD=off` only when
the user explicitly asks to bypass it, and report that you did.

Claude Code installs this same script as a `PreToolUse` hook and it blocks
automatically. Every other application must call it explicitly before the action.

## Rules

- Never overwrite the previous version.
- Never mark a partial copy as current.
- Record the AI application, model, reasoning mode, parent version, intended
  changes, changed files, commands, validation, runtime status, and unresolved risks.
- Regenerate disposable build caches after moving or duplicating projects.
- Scan generated projects for stale absolute paths.
- Preserve the previous version for rollback and binary comparison.
- Record ownership transfers explicitly. A transfer changes the owner record,
  not the physical workspace merely because another AI is used.

## Completion

Report the workspace root, project root, parent version, active version, copied
file count, changelog status, build status, final package hash, and remaining risks.

## Claude Code execution adapter

- Keep `CLAUDE.md` concise and use this skill for procedural detail.
- Load only the skills needed for the current milestone because invoked skill content remains in context.
- Use high or xhigh effort for risky architecture, plugins, DLLs, and hostile review.
- Before compaction or a usage boundary, persist exact state, commands, uncommitted changes, and remaining validation.
- Treat auto memory as candidate learning, not verified truth, until it passes the memory-promotion protocol.

### Skill-specific provider control

Resolve authoritative ownership before the first write and never author inside deployed game or manager paths.

## Authority and handoff gate

Before copying a version, inventory the active project, supplied archives, and
read-only installed/deployed evidence. Explain which parent is authoritative.

After a move or copy, regenerate disposable build caches and scan for absolute
paths outside the active snapshot. Cross-application handoffs record exact paths,
hashes, active version, last successful build, and next required command.
