# Handoff: general JSON Schema validation (`jsonschema`)

**For:** the Ultimate AI Starter Bundle owner
**From:** Skyrim Forge
**Type:** general tooling recommendation, not a Skyrim change

Skyrim Forge does not edit the bundle. This note records the finding and the
exact action for the bundle's own maintainer.

## Finding

Skyrim Forge validates its generated SPDX 2.3 SBOM against the official schema,
using `jsonschema>=4.18` declared as a test-only extra. The shared bundle Python
runtime does not provide it.

`jsonschema` is a general-purpose, MIT-licensed JSON Schema validator. It is not
a Skyrim tool, so it stays out of Forge's runtime dependencies. It is useful to
any bundle project that validates configs, MCP manifests, catalogs or
supply-chain documents.

## Recommendation

1. Add `jsonschema>=4.18` to the bundle's shared Python environment.
2. Optionally add a `Validate-JsonSchema.ps1` helper under `TOOLS/` wrapping
   `python -m jsonschema`.
3. Do not vendor the library into individual projects.

Skyrim Forge vendors only the *schema* it validates
(`references/spdx-2.3.schema.json`, CC-BY-3.0, provenance in
`references/SPDX-SCHEMA-PROVENANCE.md`), because schemas are project data while
the validator is a general tool.

## Current Forge state

- `pyproject.toml`: `[project.optional-dependencies] test = ["jsonschema>=4.18"]`
- Full release validation explicitly requires the library (`validate_sbom`);
  a missing validator is a release-gate failure, never a skip.
- `tests/test_sbom.py` validates the shipped SBOM against the official schema.
- CI installs it in the Python matrix, repository gate, Windows and Release jobs.

## Action for the bundle

Apply steps 1–2 in the bundle repository. No Skyrim-specific files need to move.
