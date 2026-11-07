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
`modifies_existing`, `performance_sensitive`, `save_sensitive` and
`avoid` (an array of route names such as `SPID`, `Papyrus` or `SKSE`).
Explicit exclusions override keyword matches; contradictory requests return
`NEEDS_INPUT`. `components` names complementary routes when a request needs
more than one system.

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

Each dimension has `status`, optional `evidence` and optional `notes`. A bare
string is a self-report and cannot produce a verified `PASS`. To establish a
verified PASS, provide a known Forge verifier receipt bound to the same subject
and dimension, with an artifact that records the verifier's actual scope:

```json
{
  "type": "forge-tool",
  "tool": "texture-inspect",
  "dimension": "assets",
  "subject": "my-texture-mod",
  "scope": "texture-file",
  "result": "PASS",
  "artifact": "Workspaces/my-mod/reports/assets.json",
  "sha256": "64 lowercase or uppercase hex characters"
}
```

The quality report itself must include the same `subject`. The artifact must
contain `schema: skyrim-forge-quality-evidence/1`, the same tool, dimension,
subject and scope, and its own `result: PASS`. A hash alone proves only artifact
integrity; a general `VALIDATION.json` or a bare `{"result":"PASS"}` is not
accepted as universal mod proof. Supported verifier/scope pairs are declared in
`skyrim_forge/quality.py` (for example `lint`/`framework-source`,
`texture-inspect`/`texture-file`, `release-validate`/`release-package`).
`NOT_APPLICABLE` is permitted only for optional dimensions and needs a specific
reason; functional, installation, reproducibility and publication are never
waived. Missing required dimensions are `NOT_RUN`.

Overall verdicts: `PASS`, `WARNING`, `REVIEW_REQUIRED`, `INCOMPLETE`, `FAIL` or
`UNVERIFIED`. Bare-string evidence returns `REVIEW_REQUIRED`; an all-waived
report cannot pass. There is no single quality score. Static workspace evidence
never becomes runtime proof.

## Performance evidence

PresentMon-style CSV capture plus a metadata file. The measurement must be
selected explicitly with `--metric`; Forge never picks `MsGPUActive` merely
because it is present. Use `--process` for a multi-process capture:

```powershell
forge perf-ingest capture.csv imported.json --scenario scenario.json --metric msBetweenPresents --process SkyrimSE.exe --approve
forge perf-compare baseline.json candidate.json
```

The scenario metadata must be identical for a comparison: name, game version,
load order, resolution, graphics preset, hardware and metric. GPU-active time
and presented-frame interval are different measurements and are rejected as
incompatible. Fewer than 120 frames is `INSUFFICIENT`; mismatched scenarios or
metrics are `INCOMPATIBLE`; only a matching comparison can report
`IMPROVEMENT`, `REGRESSION` or `NO_MEASURABLE_CHANGE`. Even then the verification
label is `FRAME_TIME_COMPARISON_ONLY`: the arithmetic is real, but an in-game
performance win is not proven.

Capture provenance includes the selected process and process ID when available.
The PID is provenance, not a stable scenario identity: baseline and candidate
sessions may have different PIDs. Within one filtered capture, multiple PIDs
for the same executable are rejected unless one PID is selected explicitly.
Keep the raw capture, scenario metadata and report together.

## Limits

- Architecture selection is keyword/constraint routing, not semantic proof.
- Knowledge probes report presence, not API compatibility or version. The
  SKSE row names the locally observed executable (`1.6.1170`) rather than a
  permanent "current 1.6.x" range; AE is not one build.
- Quality audit distinguishes artifact integrity from verifier execution: only
  known verifiers, bound to the report subject, dimension and declared scope,
  with a hash-matching JSON artifact whose own result is PASS, count as verified.
  A general repository report cannot verify unrelated mod dimensions. This is
  local integrity, not cryptographic signing or proof that the game behaved
  correctly.
- Performance comparison consumes external captures and reports frame-time
  arithmetic, not an in-game FPS win, visual quality or gameplay correctness.
- Forge does not capture PresentMon data or profile Papyrus automatically.
- No texture, mesh, behavior or LOD optimizer is implemented by this layer;
  it only plans, validates and compares supplied evidence.
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
