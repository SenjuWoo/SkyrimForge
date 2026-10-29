# Forge 6.6.0 MCM Helper skill, data frameworks, houseCARL fallback (2026-10-29)

- Goal: the AI should know MCM Helper and the other installed SKSE data frameworks without checking online, and Forge must not depend on houseCARL alone.
- Done: `mcm-helper-authoring` (grammar from schema v1.6.3/code 15 + parser source + wiki; `validate_mcm.py` tuned on 50 shipped menus; 14 tests), `skyrim-data-frameworks` (Light Placer, AOS, EAE, DSD, SRD, SKSE HTTP from wiki/Nexus/docs/shipped examples; authority map for the rest), `load-order` / `record-conflicts` / `seq-build` with MCP tools and 10 tests, `docs/HOUSECARL-PARITY.md`, router/tooling-stack/frameworks-index routing, 50-skill pack.
- Verified: IronSword winner and providers equal houseCARL's tree on a 2,957-plugin MO2 order; `seq-build` 229/257 byte-identical and 251/257 set-identical against shipped SEQ files.
- Not done / limits: no record schema, field-level reads, predicates, reverse-reference index, forward/override writer, compaction/merge or NIF tools (roadmap in the parity doc); other installed frameworks (Prisma UI, SKSE Menu Framework, DAV, OIF/CIF, DEF, MTD, Inventory Injector) only have an authority map; the MO2 instance must be added to `extra_read_roots` before the CLI will read it (not changed here). Nothing loaded in Skyrim.
- Shipped and installed: pushed e83e14c, exact-SHA CI 15/15, 0 open Dependabot/code-scanning/secret-scanning alerts; v6.6.0 published (8 assets, bytes match SHA256SUMS and GitHub digests, tag on e83e14c). Live install updated 6.5.1 -> 6.6.0 with `Update-Forge.ps1` (full setup, last good release kept in `.forge-backup-004a42ad...`): doctor PASS with 0 warnings, five SDKs `current`, external processes still off, config.toml changed only in the installer-owned tool version string 6.5.1 -> 6.6.0 (backup `config.toml.before-reverse-2026-10-29T17-23-34Z.bak`), the two new skills present in `~/.claude/skills`; Codex, Claude, Grok and Hermes MCP registration DEFERRED to the bundle toolbox (Kimi not installed). A first attempt failed harmlessly because the shell's working directory was inside the live root; run the updater from another folder.

# Resume verification: 6.4.0 work through 6.5.1 (2026-10-29)

- Verified after a pause, on disk and remote: main 1b7a978 equals origin/main, 15/15 checks success on that SHA, no open Dependabot, code-scanning or secret-scanning alerts; v6.5.1 is published (8 assets, tag 012765b); the live install under `%LOCALAPPDATA%\Skyrim-Tools\Skyrim-Forge` is 6.5.1 with doctor PASS, 0 warnings and all five SDK vault entries `current`.
- Open, not blocking: `native-build` has never run end to end because `allow_external_processes` is false (the user's switch); the scaffold compile proof was a by-hand build. A full update attempt on 2026-10-27 rolled back because Hermes, an unrelated provider, could not register: its interpreter `hermes	ools\python-*` has no dependencies installed (`ruamel` missing), so the Hermes CLI is unusable until Hermes is repaired. `Register-MCP.ps1` still assumes `python.exe` beside `hermes.exe` (current Hermes uses a launcher shim), reachable only with `-Global` since 6.4.2 defers to the bundle toolbox, which Hermes' config has. One `.forge-stage-*-failed` directory and eight `.forge-backup-*` rollback directories remain beside the live root.

# Forge 6.5.1 houseCARL discovery and contract tests (2026-10-29)

- Done: removed the drive-letter scan; Forge-side tests for the doctor fields and UABS_TOOL_ROOTS. Released by the self-publishing workflow from the pushed SHA.
- After 6.5.1: `release.yml` decides inside the job (no job-level `if`), so a CI run cancelled by a newer push ends as a no-op release run instead of a skipped one that GitHub files under main's newest commit and that reads as a failed exact-SHA verdict; `tests/test_ci_validation.py` pins it. CI-only, no release.

# Forge 6.5.0 independent releases (2026-10-29)

- Goal: release without a manual tag; nothing in Forge restates a version the bundle would also need to bump.
- Parent: main 9a568aa (6.4.2). Pushed straight to main after the full local gate.
- Done: self-publishing `release.yml` (exact SHA, every check, attestation, no asset replacement, re-download compare); Dependabot auto-merge; version-free skill; README fixes.
- Next: CI on the pushed SHA, the workflow publishes 6.5.0, verify the downloaded bytes.

# Forge 6.4.2 bundle toolbox deferral (2026-10-29)

- Goal: stop Forge and the Ultimate AI Starter Bundle from undoing each other's MCP registration.
- Parent: main 31ab30c, public 6.4.1; branch fix/defer-to-bundle-toolbox.
- Done: `Register-MCP.ps1` defers per provider when the bundle toolbox serves Forge (`-Global` overrides); helpers rebuilt with Go 1.23.2; bridge tests 9/9.
- Next: full gate, exact-SHA CI/security, release 6.4.2, bundle pin and live update.

# Forge 6.4.1 SDK staging safety audit (2026-10-28)

- Goal: preserve existing SDK partial/recovery directories and isolate concurrent fetches.
- Parent: clean main 4b95e8d, public 6.4.0; active branch codex/sdk-staging-safety.
- Scope: SDK fetch staging, regression tests, forward version/changelog, full source gate and release proof.
- Baseline: 35 SDK/native/standalone tests PASS; exact-main 15 checks success.
- Done: deletion regression failed before fix; 17 focused tests and full gate (247 tests, native/Go/reproducibility/packaging/MCP) PASS. Both Windows PowerShell5.1 and7 parser gates PASS.
- Next: exact-SHA PR/main CI and security, immutable6.4.1 release-byte proof, then approved backed-up live update.
- No live config, SDK pins, game Data or provider settings will be changed by source tests.

# Skyrim Forge 6.4.0 SDK vault and scaffold migration (2026-10-27)

- Goal: give AI everything to make/edit/rework mods through Forge. Done in source: `sdk-status` / approval-gated `sdk-install` (`skyrim_forge/sdk.py`, `references/SDK-LOCK.json`), SDK state in `toolchain-status`, docs and skill pointers, 7 new tests (`tests/test_sdk_vault.py`). Released as 6.4.0 from a pull request with exact-SHA CI (published assets and their digests are on the GitHub release); the live installation under `%LOCALAPPDATA%\Skyrim-Tools\Skyrim-Forge` was updated afterwards (6.4.0 payload swap on 2026-10-27 with `-SkipSetup`, later 6.5.1).
- Provisioned on this machine (user config backed up first as `config.toml.before-sdk-vault-*.bak`): CommonLibSSE-NG alandtse ng v14.1.0 at `~/.skyrim-forge/sdk-vault/commonlibsse_ng` (HEAD == pin 896f6d02, clean, `current`); tool vault gained bsarch, dmscan, Cathedral Assets Optimizer, xEdit (SSEEdit64); Champollion and the game-folder PapyrusCompiler configured in place with SHA pins; cmake, ninja, xmake pinned; `skyrim_data`, `papyrus.imports`/`flags` set. `allow_external_processes` and `allow_ui_automation` left false (user's switches).
- Also provisioned after user approval: vcpkg (tag 2026.10.16, commit 9eec002, bootstrapped; vcpkg.exe SHA-256 2a4ae146… pinned in config) and the libxse (4506c63), powerof3 dev (11a8074) and libxse template (117325d) lineages; `sdk-status` reports all five `current`. A first bootstrap attempt failed because `cmd /c <script>` ignores the current directory under NoDefaultCurrentDirectoryInExePath; fixed with `.\` and a regression test. Address Library and SKSE are already installed in the game folder (not vault-managed).
- Scaffold migrated in source: `native-scaffold`/`native-audit`/`native-build` now target the maintained alandtse CommonLibSSE-NG v14.1.0 from the SDK vault (`add_subdirectory`, locked vcpkg dependencies, `logger` alias fix, clean-pin refusal, imported VC++ environment, 3600 s floor); legacy colorglass projects only warn. Build proof: after the user chose a direct build, a scaffolded probe compiled 525/525 with no errors on MSVC 19.51.36260 against the vault v14.1.0 (11 vcpkg packages, x64-windows-static-md; DLL 551,936 bytes, SHA-256 e3161544…, exports SKSEPlugin_Load/Query/Version, imports only system/CRT DLLs, `native-binary-audit` PASS). It was run by hand because `allow_external_processes` stays false (a throwaway-config bypass was refused), so `native-build` end to end and its imported VC++ environment remain untested, and nothing was loaded in Skyrim. A missing `-DVCPKG_TARGET_TRIPLET` would have produced DLL dependencies; fixed by setting x64-windows-static-md in the generated CMake before `project()`.
- Evidence: audit of upstream via `gh api` on 2026-10-27 (alandtse/CommonLibSSE-NG v14.1.0 release the same day; libxse main 4506c63; powerof3 dev 11a8074; vcpkg 2026.10.16 = 9eec002). Build/validate: `.venv/Scripts/python.exe scripts/validate_repository.py --scope full --write-reports`.

# Skyrim Forge 6.3.2 verified handoff

- 6.3.2 (forward patch; 6.3.1 stays immutable): injected pack text trimmed (no ownership prose or maintainer path), root .ignore for agent searches, delivery test decoding hardened. Details below are the 6.3.1 evidence it builds on.

- Goal complete: standalone Skyrim tooling and its specialist skill pack, with optional Starter Bundle orchestration and Reverse THIS! reuse. General compilers remain shared prerequisites; Skyrim-only tools stay with this owner. Historical checkout names do not identify installed versions.
- Published: https://github.com/SenjuWoo/SkyrimForge/releases/tag/v6.3.1 from immutable commit 533f399c7eded2fa75c0bc2dabd809ec999ccc50. All 13 exact-commit checks and CI/CodeQL workflows passed before tagging; release workflow 40533276764 passed. Fresh Dependabot, code-scanning and secret-scanning queries found zero open alerts; code quality unavailable and left off.
- All eight public assets were downloaded and match the Actions release-assets build, GitHub digests and SHA256SUMS. Product ZIP: 4,818,789 bytes; SHA256 ff6f4e04dcb362cd3ceb65d0d17292c4d2ed715e8558b093e3f635578d890fa4. Two frozen Windows builds were byte-identical. All 540 uncompressed files and executable metadata match the Linux release; compressed containers differ across Python toolchains.
- Before publication, the approved live 6.3.1 installation passed native version/self-test, doctor, descriptor MCP (53 tools), and all 539 manifest hashes. Private workspace identity and thirteen model/permission fingerprints were preserved; config changed only installer-owned tools.ui_worker.version. The final combined Bundle 8.25.0 / Forge 6.3.1 / Reverse THIS! 1.5.0 installed-state doctor passed with zero errors/warnings; fifteen selected-provider core MCP probes and houseCARL transport (31 tools) passed. Public Forge payload hashes also match that live owner.
- Thirteen stale generated Hermes Skyrim-profile skills were proven against historical published inventories, backed up and refreshed through the owner installer; all 48 specialist skills check. General ai-tooling-stack remains separately owned by the bundle. Fresh provider backups and previous Forge owner rollback trees remain intact.
- Fixed and verified: canonical installed skill version, missing runtime Provider-Skills.ps1, hash-bound source/product inventories, extracted full-pack installation/wrapper preservation, and release reruns that verify existing bytes and upload only missing assets. Published 6.3.0 stays immutable and is superseded by 6.3.1.
- Workspace ownership is explicit in WORKSPACE_OWNERSHIP.md; STATE.md is progress. New work stays local/private until publication is requested. Explicit GitHub publication defaults to public/MIT for original work subject to rights/terms; preserve existing licences. Skyrim publication normally targets Nexus; uncompiled mods do not receive duplicate GitHub repositories by default.
- Mod ZIPs contain runtime product files and required licences. Changelogs, ownership/progress/validation ledgers and publication paperwork remain outside mod payloads; toolkit deliveries retain installers, diagnostics, skills, templates and usable help. Nexus publication documents are siblings of release-tree in publication-docs.
- CLibDT remains discovered/documented; CommonLib variants stay pinned per project. Supplied third-party tool/SDK snapshots were not redistributed. Game Data, staging, saves and reference folders were not changed.
- Evidence owner: Starter Bundle artifacts/final-assurance/forge631-final (build.local.json, verified/final.local.json, cross-platform-payload-proof.local.json), forge631-live-*.local.json, pre-publication-local-proof.local.json, and preference/profile migration receipts. Source audit history remains in Git. Last good current live/public: 6.3.1; prior tags/assets and deployment backups retained.
- Build/validate: .venv/Scripts/python.exe scripts/validate_repository.py --scope full --write-reports; run: START-HERE.bat. Logs: LOCALAPPDATA/Skyrim-Forge/logs and configured private Forge audit log. Next: no implementation/deployment work remains in this owner; reopen AI apps once to reload active instructions/MCP state. Bundle publication is tracked by its own STATE.md.
- Limits: actual Skyrim/gameplay, GUI targets, paid inference/APIs, absent-provider installations and guest Sandbox are not runtime-certified. Structural validation is not game-load proof.
