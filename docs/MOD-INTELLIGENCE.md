# Mod intelligence: architecture, knowledge, quality and performance

Skyrim Forge can help an AI choose a route before it writes files, cite the
sources behind that route, decide which quality checks actually apply, and
compare captured frame times. These are evidence aids, not automatic proof that
a mod works in the game.

## Plain-English workflow

1. Describe the behaviour you want in ordinary language.
2. `forge architect-recommend request.json` ranks the smallest suitable route
   (data distribution, record patch, Papyrus, native plugin, UI, animation,
   texture, mesh, LOD, audio or packaging).
3. `forge knowledge-status` shows which pinned/curated sources are present
   locally. A file being present is `DETECTED`, not a verified version.
4. Build in a versioned workspace using the existing framework, record, Papyrus
   or native commands.
5. `forge quality-plan --types <types>` lists only the checks that apply.
6. Supply evidence and run `forge quality-audit report.json`; anything without
   evidence stays `NOT_RUN` or `UNVERIFIED`.
7. Capture frame times externally if performance matters, then compare baseline
   and candidate reports with the same scenario metadata.

## Architecture recommendation

Write a request:

```json
{
  "schema": "skyrim-forge-architecture-request/1",
  "description": "Distribute spells and perks to NPCs with SPID",
  "edition": "ae",
  "runtime_frequency": "event",
  "save_sensitive": false
}
```

```powershell
forge architect-recommend request.json
```

The result ranks known routes with a reason, complexity, runtime cost, save
risk, required checks and open questions. It reports `NEEDS_INPUT` rather than
inventing an architecture when the description is too vague. It never claims a
framework is installed.

Useful constraint fields: `edition` (`se`, `ae`, `vr`, `unknown`),
`runtime_frequency` (`event`, `occasional`, `frame`, `unknown`),
`modifies_existing`, `performance_sensitive`, `save_sensitive`.

## Source and API registry

```powershell
forge knowledge-status
forge knowledge-lookup commonlibsse_ng
```

The registry lives at `references/SKYRIM-KNOWLEDGE.json`. Each entry records the
official URL, category, version scope or pin, provenance and limitations. Local
probes use configured paths such as the Skyrim Data folder or tool vault.

Statuses:

| Status | Meaning |
|---|---|
| `VERIFIED_SOURCE` | Source pin is recorded and the matching local source is present |
| `DETECTED` | A configured local file/directory exists; version not independently proven |
| `DOCUMENTED` | Upstream/source description only; no local probe |
| `MISSING` | Probe configured but absent |
| `UNKNOWN` | No registry entry exists; do not invent it |

This registry does not contain Papyrus signatures, C++ methods or FormIDs. Read
the exact `.psc`/header at the pinned revision when writing code.

## Quality gate

```powershell
forge quality-plan --types papyrus,native
forge quality-audit report.json
```

A report is a JSON object with `mod_types` and a `checks` map. Required
dimensions depend on the mod type, so a Papyrus mod does not trigger texture or
mesh checks and a texture mod does not require native binary analysis.

Each dimension has `status`, optional `evidence` and optional `notes`. `PASS`
requires at least one evidence item. `NOT_APPLICABLE` requires a reason. Missing
required dimensions are `NOT_RUN`.

Overall verdicts: `PASS`, `WARNING`, `FAIL` or `UNVERIFIED`. There is no single
quality score. Static workspace evidence never becomes runtime proof.

## Performance evidence

PresentMon-style CSV capture (a column named `msBetweenPresents`,
`msBetweenDisplayChange` or `MsGPUActive`) plus a metadata file:

```powershell
forge perf-ingest capture.csv imported.json --scenario scenario.json --approve
forge perf-compare baseline.json candidate.json
```

The scenario metadata must be identical for a comparison: name, game version,
load order, resolution, graphics preset and hardware. The report gives mean,
median, p95, p99, slow-frame ratio and percentage deltas. Fewer than 120 frames
is `INSUFFICIENT`; mismatched scenarios are `INCOMPATIBLE`; only a matching
comparison can report `IMPROVEMENT`, `REGRESSION` or `NO_MEASURABLE_CHANGE`.

These are frame-time numbers, not an FPS or visual-quality claim. Capture the
same repeatable scene, settings and hardware, and keep the raw files shown in
the report.

## Limits

- Architecture selection is keyword/constraint routing, not semantic proof.
- Knowledge probes report presence, not API compatibility.
- Quality audit evaluates supplied evidence; it cannot run the game for you.
- Performance comparison consumes external captures; Forge does not record or
  control PresentMon by default.
- In-game loading, visuals, saves, hooks and gameplay remain human-gated.

## Commands and MCP tools

| CLI | MCP |
|---|---|
| `architect-recommend` | `forge_architect_recommend` |
| `knowledge-status` | `forge_knowledge_status` |
| `knowledge-lookup` | `forge_knowledge_lookup` |
| `quality-plan` | `forge_quality_plan` |
| `quality-audit` | `forge_quality_audit` |
| `perf-compare` | `forge_performance_compare` |
| `perf-ingest` | `forge_performance_ingest` |

All are read-only except `perf-ingest`, which writes a report in the Forge
workspace and requires approval.
