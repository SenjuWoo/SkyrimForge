# Maintenance, cleanup and moved paths

Forge creates work products that are useful for a week and clutter afterwards.
`forge maintain` is the single command that finds them, reports health and
notices when a configured path no longer exists.

## What it scans

| Location | Removed when | Kept |
|---|---|---|
| `<workspace>\.forge\spills\*.json` | older than `--days` (default 7) | newer spills |
| `<workspace>\.forge\vfs-sandbox\*` | older than `--days` | newer sandbox runs |
| `<provider>\.skyrim-forge-skill-work\backup-*` | beyond the newest `--keep-backups` (default 2) per provider | the newest two per provider |

Provider homes checked: `~/.claude`, `~/.agents`, `~/.grok`, `~/.kimi`,
`~/.codex`, `~/.hermes` and `%LOCALAPPDATA%\hermes`.

Nothing else is ever deleted. The command refuses a path that resolves outside
those three Forge-owned bases, and it refuses to delete at all without
`--apply --approve`.

## Root drift

`maintain` compares the configured `workspace_root`, `skyrim_data`,
`vortex_staging`, `mo2_profiles_root` and `tools_root` with the disk. A missing
path is reported as `MISSING`; when Forge can find a replacement it reports
`MOVED` and names the candidate:

- Steam libraries parsed from `steamapps\libraryfolders.vdf` plus the two
  default Steam roots, looking for `steamapps\common\Skyrim Special Edition\Data`
- `%APPDATA%\Vortex\skyrimse\mods`
- `<install>\Workspaces`

`--fix-roots` writes a `MOVED` candidate into `config.toml`, after copying the
old file to `config.toml.bak-maintain-<timestamp>`. It never invents a path it
did not find on disk. Two matching Steam libraries produce `AMBIGUOUS` with the
candidates listed and no write, because picking one silently is how a machine
ends up pointed at the wrong `Data`.

Writing a root is a configuration change, so `--fix-roots` also requires
`--approve`. A read-only report never mutates `config.toml`.

## Commands

```powershell
forge maintain                                  # dry run, prints the plan and the self-test
forge maintain --apply --approve                # delete the planned leftovers
forge maintain --days 14 --keep-backups 1       # different retention
forge maintain --fix-roots                      # accept discovered roots
forge maintain --no-self-test                   # skip the built-in checks
```

The JSON result carries `removals`, `removals_planned`, `roots`, `applied`,
`roots_changed` and, unless `--no-self-test`, `health` (the same checks as
`forge self-test`).

## Weekly upkeep

Windows Task Scheduler, run from the install root:

```powershell
schtasks /Create /TN "Skyrim Forge maintain" /SC WEEKLY /ST 12:00 ^
  /TR "\"%LOCALAPPDATA%\Skyrim-Tools\Skyrim-Forge\.venv\Scripts\python.exe\" -m skyrim_forge maintain --apply --approve --fix-roots"
```

That prunes Forge-owned leftovers and accepts discovered roots once a week. It
does not install updates: updates stay explicit through `Update Forge.bat` or
`Update-Forge.ps1 -CheckOnly`, because swapping a running installation on a
schedule is how an MCP server disappears without anyone noticing.

## MCP

`forge_maintain` exposes the same operation. It is a dry run unless `apply` is
true, and `apply` needs `approved: true` through the normal approval path.

## Optional weekly check

`forge maintain --schedule --approve` registers a Windows task named
`SkyrimForge-Maintain` that runs `maintain --no-self-test` once a week and
appends the report to `logs\maintain.log` beside `config.toml`. It is
**check-only**: the task never passes `--apply` or `--fix-roots`, so it can
report drift but cannot change your install. `forge maintain --schedule-status`
prints whether the task exists, and `forge maintain --unschedule --approve`
removes it. Nothing is registered unless you ask.
