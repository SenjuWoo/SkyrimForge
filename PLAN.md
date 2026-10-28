# SDK staging safety (2026-10-28)

1. [complete] Reproduce deletion of preexisting recovery data with a local-Git fixture.
2. [complete] Use unique staging; test retries, failed downloads and interleaved installs.
3. [complete] Rebuild helpers and pass full gates (247 tests; native, Go, packaging, MCP and dual-shell parsing).
4. [pending] Exact-SHA CI/security, release-byte proof, backed-up live update and companion pins.

# SDK vault (2026-10-27)

1. [complete] Audit Forge, host tools and upstream CommonLib lineages.
2. [complete] Import/configure local tools; pin host build tools.
3. [complete] Implement and test the pinned SDK vault; fetch CommonLibSSE-NG.
4. [complete] Fetch vcpkg (+ bootstrap) and reference lineages; pin vcpkg.
5. [complete] Migrate native scaffold to the maintained library; direct compile proof passed; native-build end to end still needs allow_external_processes.

# 6.3.1 extracted-provider correction (2026-10-27)

Independent read-only review reproduced a missing runtime dependency: scripts/Provider-Skills.ps1 was omitted by the product profile. Include that exact helper; the real extracted-product gate now installs/checks all 48 skills into isolated Claude homes and reruns the dedicated Forge wrapper without retiring other skills. 6.3.1 remains unpublished until this gate and exact-SHA CI pass.

# 6.3.1 canonical-skill correction (2026-10-27)

The bundle cross-product gate found the installed pack skill still advertised 6.2 while the unused legacy copy said 6.3. Remove the unused duplicate, point version validation/tests at the installed source, and add a mutation fixture. Correct standalone/shared-runtime instructions. Previous 6.3.0 release stays unchanged; new 6.3.1 source/native/CI/release proof pending. Live installation remains last-good 6.2.1 until the forward patch is verified. Build: python scripts/validate_repository.py --scope full --write-reports; logs: Starter Bundle artifacts/final-assurance.

# Final assurance 6.3.0 candidate (2026-10-27)

Source packaging and ownership changes implemented; 49 affected tests PASS. Full source gate PASS: 208 tests (2 platform/tool availability skips), native reproducibility/race/vet, packaging and MCP. Three extracted-product tests PASS, including actual Python/native and Windows startup. Public release and approved live refresh remain pending. Last good: 6.2.1; logs: Starter Bundle artifacts/final-assurance. Build/run: python scripts/validate_repository.py --scope full --write-reports; START-HERE.bat. Nexus publication documents now use publication-docs beside release-tree, not inside the mod ZIP. Prior reports below remain historical.

# Plan

1. [complete] Publish and install the validated 5.1.1 bridge release.
2. [complete] Reproduce Hermes' false-success registrar behavior against the
   real client: cancelled tool-enable prompts and missing-server tests returned
   exit code zero.
3. [complete] Deliver 5.1.2 with explicit tool enablement, output-based
   Hermes connection verification, full validation, release, and deployment.
4. [complete] Deliver 5.1.3 with idempotent release publication, a green tag
   workflow, and an exact-version active installation folder.
5. [complete] Deliver 5.1.5 so Claude Code 2026-07-28 can call Forge tools:
   `tools/call` always carries `resultType: "complete"`.
6. [complete] Deliver 5.2.0 so a fresh install cannot recreate a Documents
   copy, and so Register-MCP will not wedge Grok at 8 running servers.
7. [complete] Deliver 6.1.0 as the self-contained Skyrim AI modding repository
   owning the 48-skill Skyrim pack (`integrations/skyrim-pack/`), `Install-Skyrim-Pack.ps1`,
   `Setup-HouseCarl.ps1`, and parallel-development compatibility with Ultimate-AI-Starter-Bundle.

8. [complete] Deliver 6.1.1 with independent skill ownership, safe provider paths, retained rollback backups and Forge-owned houseCARL installation.

9. [complete] Separate the general and Skyrim-specific routing skill names with ownership-proven migration.
10. [complete] Add shared runtime selection/update, verified owner updater and in-place Reverse tool reuse.
11. [complete] Reject false-success output and document actual local tools/licensing boundaries.
12. [complete] Validate 6.2.0, regenerate reports and hand off source to parent for exact-SHA CI/publication. No live deployment in this workstream.

13. [complete] Publish 6.2.1 with stale owner-bytecode migration protection and verified live upgrade.
