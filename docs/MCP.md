# MCP

Run:

```text
python -m skyrim_forge mcp
```

The server uses JSON-RPC over stdio and exposes inspection, framework validation, typed plugin creation, release tooling, configuration, and Automation Fabric jobs.

Mutating tools require `approved: true`. MCP does not expose arbitrary command execution.

## Protocol eras

Forge 5.0.0 is a **dual-era server**. It answers the current `2026-07-28`
revision, which carries the protocol version as per-request metadata, and it
still answers the `initialize` handshake used by `2025-11-25` and earlier.

| Supported | Era |
|---|---|
| `2026-07-28` | modern, stateless, per-request `_meta` |
| `2025-11-25`, `2025-06-18`, `2024-11-05` | legacy, `initialize` handshake |

The era is chosen by what the client sends, not by configuration. Existing
registrations keep working unchanged: a legacy response carries none of the
modern-only fields.

### Modern clients

Declare the version on every request:

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{
  "_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28"}}}
```

`server/discover` returns the supported versions, capabilities, and server
identity in one request. It is also the stdio backward-compatibility probe, so
Forge answers it even when the request carries no `_meta`:

```json
{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{}}
```

An unsupported version is refused with `-32022` and the list Forge does support,
so a client can retry rather than guess:

```json
{"error":{"code":-32022,"message":"Unsupported protocol version",
  "data":{"supported":["2026-07-28","2025-11-25","2025-06-18","2024-11-05"],
          "requested":"1900-01-01"}}}
```

### Tool results

`tools/call`, `prompts/get`, and `ping` always carry `resultType: "complete"`.
That field is required by `2026-07-28`. Clients that have seen Forge advertise
the revision (via `server/discover` or `initialize`) reject a `tools/call`
payload that omits it, even when the call itself has no `_meta`. Handshake-era
clients ignore the extra field. Caching hints are not attached to tool results.
This behaviour shipped in 5.1.5; 5.1.4 is not usable with Claude Code on that
revision.

### Grok

When the Ultimate AI Starter Bundle toolbox already serves `skyrim-forge` to a provider (its catalog lists it and that provider's MCP config has a `toolbox` entry), `Register-MCP.ps1` reports `DEFERRED` instead of writing a global entry, because the bundle installer removes global Forge entries and the two would undo each other. Pass `-Global` to register machine-wide anyway.

Grok wedges at eight **running** MCP servers. `Register-MCP.ps1 -Provider Grok`
counts `[mcp_servers.*]` in `%USERPROFILE%\.grok\config.toml` and skips the add
when Forge would be an eighth runner (7 configured, or 6 while the
`mcp-search` plugin still loads). `grok mcp disable mcp-search` frees the
plugin slot. Replacing an already-registered Forge command does not consume a
new slot.

### Caching

Complete results for `server/discover`, `tools/list`, `prompts/list`,
`resources/list`, and `resources/read` carry `ttlMs` and `cacheScope`. Forge's
tool, prompt, and resource inventories are fixed for an installed version and
identical for every caller, so they are `public`. Sanitized configuration is
`private` with a zero TTL: it reflects local machine state and `forge_config_set`
can change it.

## Tool annotations

`tools/list` attaches the standard hints to every tool:

- read-only tools (`forge_doctor`, `forge_capabilities`, `forge_papyrus_analyze`, `forge_audio_inspect`, `forge_skse_inspect_pe`, `forge_fomod_validate`, `forge_nexus_audit`, …) are `readOnlyHint: true`, `idempotentHint: true`;
- staged workspace builders (`forge_fomod_build`, `forge_papyrus_compile`, `forge_audio_create_fuz`, …) are `destructiveHint: false`;
- approval-gated actions (`forge_automation_run`, `forge_tool_import`, `forge_config_set`, …) are `destructiveHint: true`.

The hints describe the tool, not a permission: every mutating call still requires `approved: true`.

## Bounded output

A host that truncates a large JSON payload hands the agent invalid input. `tools/call` serializes the result, and when it exceeds `SKYRIM_FORGE_MAX_CHARS` (default 24000, minimum 1000) it writes the complete payload atomically to `<workspace>/.forge/spills/<tool>_<utc>_<sha8>.json` and returns:

```json
{"result": "PARTIAL_SPILL", "max_chars_overrun": true, "total_chars": 184320,
 "artifact_path": "<workspace>/.forge/spills/forge_capabilities_...json",
 "summary": {"capabilities": 40, "result": "PASS"}}
```

Read the artifact for the full data; the envelope is never truncated JSON.

## Compact surface

For hosts near a server or schema-token ceiling:

```text
python -m skyrim_forge mcp --surface compact
SKYRIM_FORGE_MCP_SURFACE=compact python -m skyrim_forge mcp
```

Compact mode registers four orthogonal meta-tools — `skyrim_forge_inspect`, `skyrim_forge_validate`, `skyrim_forge_execute`, `skyrim_forge_release` — each taking `operation` (the underlying tool name), `arguments`, and optional `approved`. Every full-surface tool belongs to exactly one group, and the underlying tool keeps its own schema and approval rule. `--surface full` (the default) is unchanged and backward compatible.
