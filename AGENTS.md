# Working on Skyrim Forge

Short runbook for agents. The repository is the product; a release is a separate, gated act.

## Source of truth

| What | Where |
|---|---|
| Product version | `skyrim_forge/version.py` (mirrored in `VERSION.txt`, `CURRENT.txt`, `server.json`, `START-HERE.bat`) |
| houseCARL runtime pin | `integrations/skyrim-pack/housecarl-pin.json` (installer, `PACK.json` and the test must agree) |
| Native SDK pins | `references/NATIVE-SOURCE-LOCK.json`, `references/SDK-LOCK.json` |
| Go toolchain | `go-version` in `.github/workflows/ci.yml` and `release.yml` |
| MCP protocol revisions | `MODERN_PROTOCOL` / `LEGACY_PROTOCOLS` in `skyrim_forge/mcp_server.py` |
| Current state | `STATE.md` (version, done, gaps, evidence) |

Never bump a pin because a newer tag exists. Change one only with the gate named in `scripts/check_freshness.py --online`.

## Where the logic lives

| Area | File |
|---|---|
| FOMOD parse/validate/simulate/xml | `skyrim_forge/fomod.py` |
| Sandbox install test, branch enumeration | `skyrim_forge/vfs_sandbox.py` |
| Native scaffold/CMake/PE | `skyrim_forge/native.py`, `skse_pe.py` |
| Maintenance, roots, scheduled task | `skyrim_forge/maintenance.py` |
| MCP surface, annotations, spill | `skyrim_forge/mcp_server.py` |
| Release publication | `scripts/publish_release.py`, `.github/workflows/release.yml` |

## Loop

```powershell
.\forge self-test                       # seconds
python scripts/preflight.py             # versions, control chars, manifest, critical tests
python -m unittest discover -s tests -q   # SBOM schema test needs: pip install .[test]
python scripts/validate_repository.py --scope full --write-reports
```

`preflight.py` is the cheap gate; `validate_repository.py --scope full` is the release gate and writes `VALIDATION.json`. Do not claim `PASS` for a category that was skipped or blocked.

## Boundaries

- Live `Data`, saves, Vortex/MO2 staging, the tool vault and the installed Forge copy are inputs, not scratch space.
- Writes go through the workspace and need `approved: true`; tests use temp directories under the repository.
- Windows-only paths: symlink/junction creation, Task Scheduler, MSVC/CMake native builds.
- `.bat`/`.cmd`/`.ps1` are CRLF; every other text file is LF. The manifest hashes normalized bytes.
- No generated file may carry control characters; `preflight.py` and the validator both check.

## Adding a fix

1. Reproduce it with a failing test beside the existing suite.
2. Fix the root cause in the shared function, not at a call site.
3. Re-run the focused module, then the full suite.
4. Record user-visible behaviour in `CHANGELOG.md`/`CHANGELOG.txt` and `STATE.md`; record a policy choice in `DECISIONS.md`.

## Release

1. Bump the five version mirrors together.
2. Run the full gate; fix until `VALIDATION.json` is `PASS`.
3. Commit, push, wait for every check on that exact SHA.
4. The workflow tags and publishes. Rerunning it resumes a partial release when the tag names the same SHA, even if `main` has advanced; it never rebuilds an existing tag and never publishes an untagged commit that is no longer `main`.
5. Verify the downloaded ZIP against `SHA256SUMS.txt`, extract it, and run `forge.cmd version`, `doctor` and an MCP handshake from outside the install root.
6. Update the live install with `Update-Forge.ps1`; never assume it happened.

If the original run can no longer be rerun, `gh run rerun <run-id>` is the manual recovery path for the same SHA. Do not move the tag or rebuild it from newer source.

In the final report state: starting and ending SHA, version, what was verified by execution, what was skipped, and every remaining risk. Do not call a Windows, CMake or in-game test passed if it did not run.
