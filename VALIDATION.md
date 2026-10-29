# Bundle toolbox deferral candidate 6.4.2 (2026-10-29)

Provider bridge suite 9/9 with the installed runtime: detection matches the live machine (Codex, Grok, Claude, Hermes deferred; Kimi without a toolbox registers), a Kimi config with a toolbox entry is left byte-identical and reported DEFERRED, and `-Global` writes Forge beside the toolbox.

# SDK staging safety candidate 6.4.1 (2026-10-28)

The new preexisting-partial regression failed before the fix (sentinel deleted). After unique staging and destination-preservation changes: 17 SDK/native-integration tests pass, including a real local-Git concurrent fetch and injected fetch failure. Full gate PASS: 247 tests; native/Go/race/reproducibility, product packaging and MCP checks pass. Windows PowerShell5.1 and7 parser gates pass. Exact-SHA CI/release proof pending; no game runtime or live-config change.

# Unreleased SDK vault validation (2026-10-27)

Full source gate PASS from a UTF-8 console: 237 tests (3 platform/tool skips) including 7 new SDK-vault tests (fixture repository, idempotent fetch, approval, wrong-commit cleanup, modified/foreign directory refusal, lock rejection of unpinned/unsafe entries), Go, MCP, native, PowerShell screening, version sync and wheel/sdist packaging. Live evidence: CommonLibSSE-NG v14.1.0 fetched by `forge sdk-install commonlibsse_ng --approve`, HEAD equals pin 896f6d02, clean tree, `sdk-status` reports `current`; `toolchain-status` PASS with 9 configured tools. Scaffold migration: 24 targeted tests pass (`test_native_sdk_integration`, `test_v41_engineering`, `test_sdk_vault`) including lock agreement, manifest dependencies, legacy warning, clean-pin refusal and VC++ environment import from a path with spaces; a Python-level scaffold plus audit of a probe project passes under `-W error`. Direct compile proof (run by hand, same arguments as native-build): probe plugin 525/525 steps, zero compiler errors, MSVC 19.51.36260, 11 vcpkg packages under x64-windows-static-md, DLL 551,936 bytes SHA-256 e3161544c038c80787eb12a0e42668b678ffdc50225053a7c9973f2abc4c22bf, exports SKSEPlugin_Load/Query/Version, imports only system and CRT DLLs, Forge PE audit PASS; vault checkout stayed clean. `native-build` itself and in-game loading were not run. Later live evidence: vcpkg, libxse, powerof3 and template fetched and `current`; vcpkg bootstrapped (`vcpkg version` 2026-09-26-51bf87ca) after a cmd current-directory fix covered by a new test (8 SDK tests pass; the full gate has not been re-run since that fix). Not validated: any native plugin build against the vault copy, runtime in Skyrim. Note: a run from a non-UTF-8 OEM console fails `test_actual_product_entrypoints_outside_git` on cmd output containing the temp-path character U+03A9; the same test passes under `chcp 65001`.

# 6.3.1 extracted-provider correction (2026-10-27)

Independent read-only review reproduced a missing runtime dependency: scripts/Provider-Skills.ps1 was omitted by the product profile. Include that exact helper; the real extracted-product gate now installs/checks all 48 skills into isolated Claude homes and reruns the dedicated Forge wrapper without retiring other skills. 6.3.1 remains unpublished until this gate and exact-SHA CI pass.

# 6.3.1 canonical-skill correction (2026-10-27)

The bundle cross-product gate found the installed pack skill still advertised 6.2 while the unused legacy copy said 6.3. Remove the unused duplicate, point version validation/tests at the installed source, and add a mutation fixture. Correct standalone/shared-runtime instructions. Previous 6.3.0 release stays unchanged; new 6.3.1 source/native/CI/release proof pending. Live installation remains last-good 6.2.1 until the forward patch is verified. Build: python scripts/validate_repository.py --scope full --write-reports; logs: Starter Bundle artifacts/final-assurance.

# Final assurance 6.3.0 candidate (2026-10-27)

Source packaging and ownership changes implemented; 49 affected tests PASS. Full source gate PASS: 208 tests (2 platform/tool availability skips), native reproducibility/race/vet, packaging and MCP. Three extracted-product tests PASS, including actual Python/native and Windows startup. Public release and approved live refresh remain pending. Last good: 6.2.1; logs: Starter Bundle artifacts/final-assurance. Build/run: python scripts/validate_repository.py --scope full --write-reports; START-HERE.bat. Nexus publication documents now use publication-docs beside release-tree, not inside the mod ZIP. Prior reports below remain historical.

# Published 6.2.1 proof and tooling ship gate

Exact main 7adcda288d551bf4de226b82679317087c053dc0 passed all attached checks/security; release workflow 40431539964 succeeded. All eight public assets match CI artifacts, GitHub digests and checksums. ZIP 5,137,963 bytes, SHA256 3d0aac570891526dfd64faface1273d1eac9dc089e1c1feb0184dd48a2a46fea. The approved live owner matches all 588 public file hashes and passes setup/native version/import/doctor. This handoff does not change tag/assets.

INPUTS: source and supplied tool evidence present.
MEMORY CHECK: existing global lessons applied to owner separation, preserved settings, runtime discovery and evidence limits.
AUTHORITY: installed=resolved SKYRIM_FORGE_ROOT parent=6.2.0 active=6.2.1 RESULT=PASS
VERSION GATE: changelog, native helpers, metadata and ownership agree; public owned files=588 RESULT=PASS
EXACT BUILD: scripts/rebuild_native_helpers.py --target all; Go 1.23.2; full native reproducibility/race/vet RESULT=PASS
FRAMEWORK VALIDATION: full existing grammar/production-path fixtures PASS; no plugin, Papyrus, FOMOD or game asset changes.
SEMANTIC TEST: stale cache regression and actual live module import/setup/native doctor RESULT=PASS; in-game behavior=UNTESTED
SHIP GATE: scripts/validate_repository.py --scope full --write-reports plus exact-SHA CI/release/CRC/manifest RESULT=PASS
FINAL ARCHIVE: Skyrim-Forge-6.2.1.zip sha256=3d0aac570891526dfd64faface1273d1eac9dc089e1c1feb0184dd48a2a46fea version_strings=PASS
RUNTIME STATUS: tool-validated
SSEEDIT/CK: not launched
UNRESOLVED: actual game/app GUI targets, paid APIs and guest sessions untested; cross-provider activation and host reconnect tracked by bundle STATE.md.

# 6.2.1 bytecode migration regression

A real timestamp-based compiled module reproduces stale bytecode promotion with equal-size source and deterministic mtimes. The new regression fails before the updater fix; it also checks old cache bytes remain in the backup and private venv caches remain unchanged. Full patch validator PASS on Windows with shared Python 3.14.10 and pinned Go 1.23.2: native builds/reproducibility, race/vet, unit/installer tests, wheel/sdist and MCP protocols. Exact-SHA CI/publication and live upgrade remain pending.

# Published 6.2.0 proof

Release source/tag aefa1a2d222801a4953e6fe39b65983750dc7997 passed exact main checks and clean security queries. Release workflow 40421709024 succeeded after recovery of a transient GitHub publication failure. All eight public assets match GitHub digests and the published SHA256SUMS; ZIP SHA256 is 2c66c6bdf79473a68e95b749e12489e0fa14db876cc583184e77b20370d1b175 (5,137,601 bytes). Only generated validation/build receipts differ from the first CI attempt; payload manifest, wheel and sdist match. This post-publication change updates handoff documentation/integrity only; the release tag and public assets remain immutable. Machine integration is tracked by the Starter Bundle, not claimed by source validation.

# Validation - 6.2.0 source

Authority: the existing source owner, branch `codex/standalone-toolchain-6-2`; parent `efe9de1bb33babbfc3042899cd15b43a0f2bd07c` (public 6.1.1). Live tools, application/provider configuration, game Data, staging and saves remain untouched.

Observed source checks:

- `python -m unittest discover -s tests -p test_standalone_toolchain.py -v`: 19 real/offline runtime, updater and Reverse reuse fixtures PASS. They verify SHA rejection, version/Git preservation, owner-swap failure, post-swap setup rollback, private collision refusal, workspace junction preservation without copying source-only `.git`/`.venv` exclusions, edited-owner-file refusal, same-version mismatch refusal, nonzero setup-exit rollback and a held concurrent-update lock and game-target refusal before even creating its sibling lock. Private file identity is retained through successful update and rollback.
- Full repository validator Python suite: 199 tests PASS, with two documented platform skips. This includes 12 real Windows skill ownership/migration fixtures and four real child-process output acceptance fixtures.
- Pinned Go 1.23.2 test/vet/race and deterministic two-build comparison PASS; Windows native version/self-test and mirrored package-copy integrity PASS. Windows helper SHA-256 `83b33b9fd198f8dd9873b8247c42839bb5f8d26eb3ac1efe0e0add76ffedcb43`; Linux helper SHA-256 `bacb9b8085d3347a81be4f620317929c0b0cd917599692d78da990cda2a7ad36`.
- Deterministic wheel/source distribution, JSON/schema/source hygiene and dual-era MCP checks PASS. The initial full run rejected an intentional old-version fixture literal in the version sweep; fixture formatting was corrected using the existing test convention. `VALIDATION.json` records the final full result.
- The shipped Windows PowerShell parser is also exercised directly; static screening alone is not its runtime proof.

Final source command: `.venv/Scripts/python.exe scripts/validate_repository.py --scope full --write-reports`, with `SKYRIM_FORGE_GO` set to the existing pinned compiler. Final full command returned exit 0 with 199 tests (two platform skips), all selected checks PASS and no errors. Afterwards, only two stale houseCARL documentation routes were corrected to Forge's actual `Install-HouseCarl.ps1`; source/file/version checks and manifest/SBOM regeneration cover that documentation-only change without repeating unchanged code tests. No third-party executables were executed or publicly bundled.

Scope gate: source-only PASS. Plugin/Papyrus/framework/FOMOD content changes: N/A. Runtime evidence: tool-validated. SSEEdit/CK: not launched. Final public archive and exact-SHA CI/alert checks, Git publication and live installation are the parent's next phase; no final archive/hash is claimed here. GUI/game/save/animation/navmesh testing was not performed.

PR #16 CI portability correction: the initial Windows matrix exposed a lexical comparison against a resolved temporary-directory alias and Python 3.11 lacking `Path.is_junction()`. The fixture now asserts actual same-file identity and Windows reparse metadata plus the resolved target. Product code is unchanged; focused offline tests and regenerated file/version/manifest checks cover this correction locally, with the full remote matrix required on the new pushed SHA.
