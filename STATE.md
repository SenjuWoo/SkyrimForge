# 6.3.1 extracted-provider correction (2026-10-27)

Independent read-only review reproduced a missing runtime dependency: scripts/Provider-Skills.ps1 was omitted by the product profile. Include that exact helper; the real extracted-product gate now installs/checks all 48 skills into isolated Claude homes and reruns the dedicated Forge wrapper without retiring other skills. 6.3.1 remains unpublished until this gate and exact-SHA CI pass.

# 6.3.1 canonical-skill correction (2026-10-27)

The bundle cross-product gate found the installed pack skill still advertised 6.2 while the unused legacy copy said 6.3. Remove the unused duplicate, point version validation/tests at the installed source, and add a mutation fixture. Correct standalone/shared-runtime instructions. Previous 6.3.0 release stays unchanged; new 6.3.1 source/native/CI/release proof pending. Live installation remains last-good 6.2.1 until the forward patch is verified. Build: python scripts/validate_repository.py --scope full --write-reports; logs: Starter Bundle artifacts/final-assurance.

# Final assurance 6.3.0 candidate (2026-10-27)

Source packaging and ownership changes implemented; 49 affected tests PASS. Full source gate PASS: 208 tests (2 platform/tool availability skips), native reproducibility/race/vet, packaging and MCP. Three extracted-product tests PASS, including actual Python/native and Windows startup. Public release and approved live refresh remain pending. Last good: 6.2.1; logs: Starter Bundle artifacts/final-assurance. Build/run: python scripts/validate_repository.py --scope full --write-reports; START-HERE.bat. Nexus publication documents now use publication-docs beside release-tree, not inside the mod ZIP. Prior reports below remain historical.

# Forge 6.2.1 verified release handoff

- Goal: standalone Skyrim tooling, 48 specialist skills, safe owner updates and shared prerequisites without duplicate owners.
- Published: https://github.com/SenjuWoo/SkyrimForge/releases/tag/v6.2.1 from 7adcda288d551bf4de226b82679317087c053dc0 (PR #19). All main checks/security PASS; release workflow 40431539964 success.
- All eight public assets were downloaded and matched CI artifacts, GitHub digests and SHA256SUMS. ZIP: 5,137,963 bytes; SHA256 3d0aac570891526dfd64faface1273d1eac9dc089e1c1feb0184dd48a2a46fea.
- The live approved upgrade passes setup/native version/doctor and imports 6.2.1. All 588 owned public files match the release manifest, zero mismatches; archive CRC/path/private-cache exclusion PASS. Previous cache bytes and release trees remain recoverable.
- Fixed: deterministic mtime plus equal-size source let inherited 6.1.1 bytecode shadow 6.2.0. Generated owner caches now stay in the rollback tree; private venv/workspace trees move intact. The real compiled-bytecode regression fails before the fix and passes after, including retained cache-byte/private-venv oracles.
- Verification: full Windows validator on shared Python 3.14.10 and pinned Go 1.23.2, unit/installer tests, native reproducibility/race/vet, wheel/sdist, MCP protocol checks, exact-SHA CI and downloaded release bytes. The source release is complete. Cross-provider activation/reconnect is tracked by the bundle STATE.md.
- Last good live: 6.2.1. Rollback tags/releases 6.2.0 and 6.1.1 and deployment backups retained. Game Data, staging, saves and supplied reference folders untouched.
- Scope: CLibDT remains a discovered/documented GUI; CommonLib variants remain per-project dependencies. No supplied third-party binary or SDK source snapshot was copied into the release. General compilers belong to the optional Starter Bundle; Reverse THIS! tools are reused in place.
- Run: START-HERE.bat; validate: .venv/Scripts/python.exe scripts/validate_repository.py --scope full --write-reports. Logs: LOCALAPPDATA/Skyrim-Forge/logs and the configured Forge audit log. No game/GUI runtime certification is implied.
