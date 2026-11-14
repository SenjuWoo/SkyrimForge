# Self-publishing releases and version-free skill (2026-10-29)

- A green, untagged version on main is the release request; nobody pushes tags. The bundle installs Forge's latest release (it pins none), so Forge releases never need a bundle release, and Forge's skill no longer restates a version that would need bumping in both.

# Defer global MCP registration to the bundle toolbox (2026-10-29)

- Where the Ultimate AI Starter Bundle toolbox serves `skyrim-forge` to a provider, Forge does not also register it globally. The bundle installer removes global Forge entries in favour of the on-demand toolbox, so a global write here was undone on every bundle install and re-added on every Forge registration. Detection reads the bundle's own catalog (`toolbox-profiles.json`) and the provider's MCP config; unreadable config falls back to registering as before. `-Global` keeps an explicit machine-wide choice available.

# SDK staging safety (2026-10-28)

- A fetch owns only its uniquely created temporary directory. Existing partial/recovery data is never disposable merely because its name matches an old transaction convention. A concurrently created destination is retained; the losing fetch reports incomplete instead of overwriting it.
- Forward patch 6.4.1 preserves the SDK pins and user approval/external-process policy from 6.4.0. No SDK source is bundled.

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

- 6.9.0: Pack skills derived from houseCARL keep their own GPL-3.0-only licence (NOTICE.md); generated data (`mutagen-reference`) is refreshed from the installed houseCARL, while hand-tuned skills that are ahead of upstream (KID 4.0.6, SPID 7.3.1 authorities) stay Forge's. `papyrus-reference` is not resynced: upstream differs only by fallback contents tables and both indexes resolve all 7,345 entries. A generic executable name (`papyrus.exe`) is never auto-discovered; it is configured explicitly.

- 6.11.0: Go moves to 1.27.3 because 1.23.2 is past support; both shipped helpers are rebuilt from the same toolchain the workflows pin, and the reproducible gate compares the result. houseCARL's installer pin moves to 2.1.2 (upstream asset `houseCARL-2.1.2.zip` verified), while the bundled skill snapshot stays at 2.1.1 until it is re-snapshotted and tested as a set. CommonLibSSE-NG stays pinned at v14.1.0: v15.7.0 (`cd21580`) is a new API line and no representative native plugin build is available in this environment, so upgrading would be an unverified claim. vcpkg's 2026.10.16 baseline is unchanged.
- 6.11.0: A scheduled check may only report. `forge maintain --schedule` registers a task that never passes `--apply` or `--fix-roots`, because an unattended job that rewrites a live install is how an MCP server disappears between sessions.

- 6.11.2: CommonLibSSE-NG stays pinned at v14.1.0 (`896f6d0`). v15.7.1 is a new API line and no representative scaffold was built with the pinned MSVC/vcpkg inputs in this environment, so changing the lock would be an untested claim. The freshness report names the drift and the gate instead.
- 6.11.2: Dependency freshness is a read-only report (`scripts/check_freshness.py`). It may name an update and its required gate; it may never rewrite a pin, install a tool or trigger a release.
- 6.11.2: Scheduled-task ownership is proven from structured task objects plus a registration marker and an exact check-only action. A task whose ownership cannot be proven is never replaced or deleted, even if its name matches.

- 6.11.3: A FOMOD sweep can PASS only when at least one branch installed and every group type in the plan was enumerated. Anything less is `PARTIAL`; `INFEASIBLE` is reserved for enumerated combinations the group constraints reject.
- 6.11.3: Native metadata containing a quote or backslash is rejected. The pinned CommonLibSSE-NG CMake helper interpolates NAME/AUTHOR/EMAIL into generated C++ raw, so Forge cannot make those characters safe by quoting CMake alone.
- 6.11.3: A published tag is immutable. If it points at the current SHA the workflow resumes missing assets; if it points elsewhere the commit is post-release and publication is skipped, never rebuilt from newer code.
- 6.11.3: Scheduled-task ownership is an exact structural match (task path, one action, executable, arguments), not a name or substring.

- 6.11.4: Preflight reports a release state, not a boolean tag conflict. POST_RELEASE is healthy; STALE_VERSION means product files changed after the tag without a bump.
- 6.11.4: A scheduled task with a matching command line is still not owned. Only the canonical marker + exact action authorizes replacement or deletion; legacy shapes are candidates for a manual takeover.
- 6.11.4: Release resumability is independent of `main` for an existing tag that names the validated SHA. New releases still require current `main`.
- 6.11.4: The SBOM reports per-package licences from the notices, with CONTAINS relationships and commit-specific metadata; MIT is not declared for GPL-derived skills.
- 6.11.4: FOMOD coverage may honestly be PARTIAL. `SelectAtLeastOne`, `SelectAny` and `SelectAll` are not enumerated and never counted as tested.

- 6.11.5: Ship the SPDX schema as project data, not the validator. `jsonschema` is a general test-only dependency declared in `[project.optional-dependencies]`; CI enforces it, the runtime does not need it.

- 6.11.6: Raw execution transcripts are diagnostics, not release evidence. Checksums are computed over stable summaries (result, counts, hashes), never over timings or temp paths.
- 6.11.6: A full gate passes only when every selected category reports PASS. NOT-RUN, FAIL and MISSING are release blockers; platform-limited checks must be proven by the job that can run them.
- 6.11.6: The full gate validates the shipped SBOM itself, so the test-only schema dependency is mandatory for releases but not for the runtime.
- 6.11.6: Remote tag state is captured before evaluation; a lookup failure aborts instead of being mistaken for an absent tag.
- 6.11.6: Handoffs to other projects live under Forge docs. Skyrim Forge never edits another repository or bundle.
- 6.12.6: Content policy belongs to the host's instructions (the bundle), not to Forge. The pack restates no exclusions, so its copied instructions cannot contradict the host's rule; a test keeps it that way. Kept: the Anim Object Swapper note beside the engine's `C` (child) trait, because it points at a flag the game sets and matches the host's rule without asking a model to judge an age.
