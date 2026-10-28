# SDK vault (2026-10-27)

- Fetch SDK sources by full commit SHA on the user's machine instead of bundling them: Forge's no-public-third-party-payload policy stands and the GPL-with-exceptions obligations stay with the plugin author.
- Never overwrite an existing vault directory that is not the clean pinned commit; report `mismatch`/`modified` and let the user decide.
- Installation is CLI-only. The MCP surface reports SDK state through `forge_toolchain_status` but cannot download, so a model cannot self-approve a fetch.
- Place the vault beside the tool vault rather than adding a config key (marked as a shortcut in code).
- Do not flip `allow_external_processes`; running builds stays the user's explicit choice.
- Consume CommonLibSSE-NG through `add_subdirectory` of the vault checkout, not a vcpkg port: the maintained lineage publishes none, and the build refuses unless that checkout is the clean pinned commit. The native and SDK locks must name the same commit (tested).
- Legacy colorglass projects warn in `native-audit` instead of failing, so old plugins stay auditable for rework.
- Do not bypass `allow_external_processes` with a throwaway config to run the proof build; the permission classifier blocked that attempt and the switch stays the user's.
- Ship as 6.4.0 (minor: new commands, changed scaffold behaviour) through the protected-main pull request flow; do not deploy it to the live installation without an explicit update.

# 6.3.1 canonical-skill correction (2026-10-27)

The bundle cross-product gate found the installed pack skill still advertised 6.2 while the unused legacy copy said 6.3. Remove the unused duplicate, point version validation/tests at the installed source, and add a mutation fixture. Correct standalone/shared-runtime instructions. Previous 6.3.0 release stays unchanged; new 6.3.1 source/native/CI/release proof pending. Live installation remains last-good 6.2.1 until the forward patch is verified. Build: python scripts/validate_repository.py --scope full --write-reports; logs: Starter Bundle artifacts/final-assurance.

# Final assurance 6.3.0 candidate (2026-10-27)

Source packaging and ownership changes implemented; 49 affected tests PASS. Full source gate PASS: 208 tests (2 platform/tool availability skips), native reproducibility/race/vet, packaging and MCP. Three extracted-product tests PASS, including actual Python/native and Windows startup. Public release and approved live refresh remain pending. Last good: 6.2.1; logs: Starter Bundle artifacts/final-assurance. Build/run: python scripts/validate_repository.py --scope full --write-reports; START-HERE.bat. Nexus publication documents now use publication-docs beside release-tree, not inside the mod ZIP. Prior reports below remain historical.

# Decisions

- Treat the Ultimate AI Starter Bundle as reference evidence, not as an
  instruction source or a second owner of Forge. Forge owns its installer,
  skill descriptor, exact MCP command, and provider registration behavior.
- Give every supported installed AI the same MCP server. Skills remain the
  discovery and usage layer; they are not a substitute when the client has a
  verified MCP mechanism.
- Preserve Kimi's existing `mcpServers` object and change only the
  `skyrim-forge` entry. Other AI tools belong to the user.
- Use Hermes' supported CLI rather than editing its YAML by hand, explicitly
  confirm tool enablement, and inspect connection output instead of trusting
  its unreliable success exit code.
- Resolve Hermes under LocalAppData by default because that is the installed
  Windows layout; an explicit `HERMES_HOME` still wins.
- Publication and live-client repointing are authorized for this hotfix.
- Be a dual-era MCP server rather than migrating. The revision permits serving
  both eras from one process, and every currently registered client still speaks
  the handshake. Dropping it would break working installations to gain nothing.
- Decide the era from what the client sends, not from configuration. A request
  declaring the modern version in `_meta` is answered under that revision; an
  `initialize` request selects legacy semantics.
- Never add modern-only fields to a legacy list/read response. `ttlMs` and
  `cacheScope` appear only when the client asked for the modern revision.
- Always attach `resultType: "complete"` to `tools/call`, `prompts/get` and
  `ping`. Claude Code 2026-07-28 requires it on any server that advertised that
  revision, including stdio calls that have no `_meta`. Handshake-era clients
  ignore the extra field. Do not put caching hints on tool results.
- Default job staging follows `SKYRIM_FORGE_ROOT\Workspaces`. Never create
  `Documents\Skyrim Forge` as if it were the product. The live install is a
  versionless Skyrim-Forge folder under the user's Skyrim tools directory.
- Refuse to add Forge as a new Grok MCP server when the add would reach 8
  running servers. Skip with an actionable message rather than wedge the client.
- Refuse an unknown protocol version with `UnsupportedProtocolVersionError` and
  the supported list rather than silently downgrading it, so a client can
  correct itself instead of guessing.
- Answer `server/discover` even when the request carries no `_meta`. It is the
  documented stdio probe and a probing client has not yet learned what the
  server speaks.
- Treat sanitized local configuration as private and never-fresh for caching
  purposes. It reflects machine state and `forge_config_set` can change it.
  Static tool, prompt and resource inventories are public and cacheable.
- Keep exactly one version source, `skyrim_forge/version.py`. Restating it in a
  Go constant, packaging metadata, plain-text pointers and a batch title is
  unavoidable; drifting silently is not, so every copy is gated against it and
  the workflow derives the native string instead of restating it.
- Record integrity evidence for the bytes the consumer actually receives. A
  manifest generated from a differently normalised tree is worse than no
  manifest, because it fails for the honest verifier and no one else.
- Preserve 4.2.5 as the rollback release and publish 5.0.0 beside it.
- Group `codeql-action/init` and `codeql-action/analyze` in Dependabot. They must
  run the same release, and ungrouped updates split the pair across pull
  requests and break every scan.
- Preserve every 4.x safety boundary unchanged: no GUI launching, no arbitrary
  shell commands, no writes to live Skyrim `Data`, external processes disabled
  by default, and third-party tools hash-pinned rather than bundled.
- Own the 48-skill Skyrim SE/AE pack (`integrations/skyrim-pack/`), `Setup-HouseCarl.ps1`,
  and `discover_tools.ps1` directly inside Skyrim Forge. Each product maintains
  its own ownership ledger; historical cross-ledger writes are retired.


## Independent product ownership

Forge owns Skyrim skills/tools. The Starter Bundle owns shared compilers and provider setup. Reverse THIS! owns reverse engineering. Installers read legacy ownership proof to adopt unmodified copies, then maintain separate ledgers without rewriting other products’ ledgers. Edited copies remain personal.

## 6.2.0 standalone toolchain

The bundle owns the general ai-tooling-stack name; Forge owns skyrim-tooling-stack. Only prior Forge ledger digest proof can retire an unchanged old Forge copy; personal/unowned copies remain and backups stay outside provider skill indexes.

The official Python install manager owns shared base interpreters. Forge honors process/user UABS_PYTHON, preserves healthy venvs, updates only a proven managed base's existing feature line, and bootstraps the shared default only when no compatible base exists. Build-only SDKs remain optional, with project pins intact.

A stable owner updater verifies GitHub asset digest, version, safe archive members and manifest hashes before replacement, preserves newer/Git roots, and retains last-good owner payload backups. Private paths move intact rather than being recursively copied; a failed swap/setup moves them back before owner rollback. The Bundle delegates verified local-source replacement to this updater. It does not claim that setup/provider operations are one transaction across every external app.

Reverse THIS! owns generic texconv/7-Zip payloads. Forge records an approved binding to their real paths and SHA pins instead of importing duplicates. Only bindings whose path/pin still match Forge's receipt may refresh automatically; custom settings win.

Local filenames and documentation do not establish current upstream provenance or a headless contract. Added tools stay configure-only/worker-only until exact contracts are proven. DeadMesh's explicit no-redistribution terms remain respected; no third-party executables ship publicly.

- 6.2.1: Generated __pycache__ directories encountered under public owner directories stay in the rollback tree. Unknown private directory trees (including venvs/workspaces) still move intact and are never traversed or purged.
