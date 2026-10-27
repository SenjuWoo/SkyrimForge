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

13. [in progress] Publish 6.2.1 with stale owner-bytecode migration protection and verified live upgrade.
